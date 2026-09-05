"""Exercise component 610 through real WeiDU using disposable synthetic games.

No licensed game files or running game are needed. Set WEIDU to a WeiDU binary,
put weidu/weidu.exe on PATH, or place weidu.exe in the repository root.
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP_NAME = "setup-chriz-bg-modpack.tp2"
MOD_NAME = "chriz-bg-modpack"
COMPONENT = 610
PUBLICATIONS = (
    "M_CBMUXP.lua",
    "CBMUXP.lua",
    "CBMUXRT.lua",
    "CBMUXPC.lua",
    "CBMUXP.menu",
)
SOURCE_DIR = ROOT / MOD_NAME / "utility-xp"
RESOURCE_TYPES = {"ARE": 1010, "2DA": 1012}
ONE_EMPTY_STRING_TLK = (
    struct.pack("<8sHII", b"TLK V1  ", 0, 1, 0x2C)
    + struct.pack("<H8siiII", 0, b"\0" * 8, 0, 0, 0, 0)
)
XP_TABLES = {
    "XPBONUS.2DA": (
        b"2DA V1.0\r\n0\r\n  1 2 3\r\n"
        b"PICK_LOCK 10 20 30\r\nDISARM_TRAP 20 40 60\r\n"
        b"LEARN_SPELL 50 100 150\r\n"
    ),
    "XPLEVEL.2DA": (
        b"2DA V1.0\r\n-1\r\n  1 2 3\r\n"
        b"FIGHTER 0 2000 4000\r\nMAGE 0 2500 5000\r\n"
        b"THIEF 0 1250 2500\r\n"
    ),
}


def _find_weidu() -> Path | None:
    configured = os.environ.get("WEIDU") or os.environ.get("WEIDU_BIN")
    if configured:
        candidate = shutil.which(configured) or configured
        path = Path(candidate).expanduser()
        if not path.is_file():
            raise RuntimeError(f"WEIDU does not name an executable file: {configured}")
        return path.resolve()
    found = shutil.which("weidu") or shutil.which("weidu.exe")
    if found:
        return Path(found).resolve()
    local = ROOT / "weidu.exe"
    return local if local.is_file() else None


WEIDU = _find_weidu()


def _file_tree(root: Path) -> dict[str, bytes]:
    """Case-fold paths while preserving exact file bytes on every platform."""
    tree: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if path.is_file():
            key = path.relative_to(root).as_posix().upper()
            if key in tree:
                raise AssertionError(f"case-colliding fixture paths: {key}")
            tree[key] = path.read_bytes()
    return tree


def _is_weidu_artifact(relative: str) -> bool:
    return relative.startswith("WEIDU_EXTERNAL/") or relative in {
        "WEIDU.LOG",
        "WEIDU.CONF",
        "SETUP-CHRIZ-BG-MODPACK.DEBUG",
    }


def _write_key_and_bif(
    root: Path, resources: list[tuple[str, str, bytes]]
) -> None:
    """Write KEY V1 and one uncompressed BIFF V1 with indexed resources."""
    bif_path = root / "data" / "cbmxp.bif"
    bif_path.parent.mkdir()
    table_offset = 0x14
    payload_offset = table_offset + len(resources) * 0x10
    table = bytearray()
    payloads = bytearray()
    for index, (resref, extension, payload) in enumerate(resources):
        if not 1 <= len(resref.encode("ascii")) <= 8:
            raise ValueError(f"invalid fixture resref: {resref}")
        table.extend(
            struct.pack(
                "<IIIHH",
                index,
                payload_offset + len(payloads),
                len(payload),
                RESOURCE_TYPES[extension],
                0,
            )
        )
        payloads.extend(payload)
    bif_path.write_bytes(
        struct.pack("<4s4sIII", b"BIFF", b"V1  ", len(resources), 0, table_offset)
        + table
        + payloads
    )

    bif_name = b"data\\cbmxp.bif\0"
    bif_table_offset = 0x18
    resource_table_offset = bif_table_offset + 0x0C
    names_offset = resource_table_offset + len(resources) * 0x0E
    key = bytearray(
        struct.pack(
            "<4s4sIIII",
            b"KEY ",
            b"V1  ",
            1,
            len(resources),
            bif_table_offset,
            resource_table_offset,
        )
    )
    key.extend(
        struct.pack("<IIHH", bif_path.stat().st_size, names_offset, len(bif_name), 0)
    )
    for index, (resref, extension, _) in enumerate(resources):
        key.extend(
            struct.pack(
                "<8sHI",
                resref.encode("ascii"),
                RESOURCE_TYPES[extension],
                index,
            )
        )
    key.extend(bif_name)
    (root / "chitin.key").write_bytes(key)


class SyntheticGame:
    def __init__(
        self,
        root: Path,
        *,
        game: str = "bg2ee",
        eeex: bool = True,
        table_location: str = "bif",
        missing_tables: tuple[str, ...] = (),
        existing_publications: bool = False,
        custom_config: bytes | None = None,
    ) -> None:
        self.root = root
        root.mkdir()
        self.override = root / "override"
        self.override.mkdir()
        shutil.copy2(ROOT / SETUP_NAME, root / SETUP_NAME)
        shutil.copytree(ROOT / MOD_NAME, root / MOD_NAME)
        self.source_dir = root / MOD_NAME / "utility-xp"
        if custom_config is not None:
            (self.source_dir / "cbmuxpc.lua").write_bytes(custom_config)

        # WeiDU GAME_IS uses resource existence, so stub ARE bytes suffice.
        # EET additionally needs eet.flag; OH6000 alone selects BG2EE, not EET.
        # https://github.com/WeiDUorg/weidu/blob/master/src/tppe.ml
        marker = {"bg2ee": "OH6000", "eet": "OH6000", "bgee": "OH1000"}[game]
        resources = [(marker, "ARE", b"synthetic engine marker")]
        if game == "eet":
            (self.override / "eet.flag").write_bytes(b"synthetic EET marker\r\n")
        for name, payload in XP_TABLES.items():
            if name in missing_tables:
                continue
            if table_location == "bif":
                resources.append((Path(name).stem, "2DA", payload))
            elif table_location == "override":
                (self.override / name.lower()).write_bytes(payload)
            else:
                raise ValueError(f"unknown fixture table location: {table_location}")
        _write_key_and_bif(root, resources)

        lang_tlk = root / "lang" / "en_us" / "dialog.tlk"
        lang_tlk.parent.mkdir(parents=True)
        lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        (root / "dialog.tlk").write_bytes(ONE_EMPTY_STRING_TLK)
        (root / "Baldur.lua").write_bytes(b"-- Existing game settings must survive.\r\n")
        (self.override / "foreign.2da").write_bytes(b"foreign resource\x00\xff\r\n")
        if eeex:
            (self.override / "m___eeex.lua").write_bytes(b"-- synthetic EEex marker\r\n")
        if existing_publications:
            for name in PUBLICATIONS:
                (self.override / name.lower()).write_bytes(
                    f"-- pre-existing {name}\r\n".encode("ascii") + b"\x00\xff"
                )
        self.before = _file_tree(root)
        self.override_before = _file_tree(self.override)

    def run(self, *, uninstall: bool = False) -> subprocess.CompletedProcess[str]:
        assert WEIDU is not None
        return subprocess.run(
            [
                str(WEIDU),
                # WeiDU records this argument between ~ delimiters in its log.
                # A Windows short temp path (RUNNER~1) must not enter that field.
                SETUP_NAME,
                "--game",
                str(self.root),
                "--force-uninstall-list" if uninstall else "--force-install-list",
                str(COMPONENT),
                "--language",
                "0",
                "--use-lang",
                "en_us",
                "--no-exit-pause",
                "--noautoupdate",
                "--quick-log",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )

    def active_log(self) -> str:
        path = next(
            (candidate for candidate in self.root.iterdir() if candidate.name.lower() == "weidu.log"),
            None,
        )
        if path is None:
            return ""
        return "\n".join(
            line
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if not line.lstrip().startswith("//")
        )


class UtilityXPResourceNamesTests(unittest.TestCase):
    def test_all_published_engine_resources_have_at_most_eight_character_resrefs(self) -> None:
        actual_names = {path.name for path in SOURCE_DIR.iterdir()}
        for name in PUBLICATIONS:
            with self.subTest(resource=name):
                self.assertLessEqual(len(Path(name).stem), 8)
                self.assertIn(name.lower(), actual_names, "Linux WeiDU needs lowercase source paths")


@unittest.skipUnless(WEIDU, "WeiDU unavailable; set WEIDU or put weidu on PATH")
class UtilityXPPublicInstallerTests(unittest.TestCase):
    def _make_game(self, **kwargs: object) -> SyntheticGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbm-utility-xp-installer-")
        self.addCleanup(temporary.cleanup)
        return SyntheticGame(Path(temporary.name) / "game", **kwargs)

    def _assert_game_files(self, game: SyntheticGame, *, installed: bool) -> None:
        expected = dict(game.before)
        if installed:
            for name in PUBLICATIONS:
                expected[f"OVERRIDE/{name.upper()}"] = (game.source_dir / name.lower()).read_bytes()
        actual = _file_tree(game.root)
        actual = {name: data for name, data in actual.items() if not _is_weidu_artifact(name)}
        self.assertEqual(set(expected), set(actual), "installer wrote outside its allowlist")
        for name, payload in expected.items():
            self.assertEqual(payload, actual[name], f"unexpected bytes in {name}")

    def _assert_installed(self, game: SyntheticGame) -> None:
        result = game.run()
        transcript = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        self._assert_game_files(game, installed=True)

    def _assert_uninstalled(self, game: SyntheticGame) -> None:
        result = game.run(uninstall=True)
        transcript = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(0, result.returncode, transcript)
        self.assertNotRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        self._assert_game_files(game, installed=False)
        self.assertEqual(game.override_before, _file_tree(game.override))

    def _assert_skipped(self, game: SyntheticGame, reason: str) -> None:
        result = game.run()
        transcript = f"{result.stdout}\n{result.stderr}"
        self.assertIn("SKIPPING:", transcript)
        self.assertRegex(transcript, reason)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotIn("NOT INSTALLED DUE TO ERRORS", transcript)
        self.assertNotRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        self._assert_game_files(game, installed=False)
        self.assertEqual(game.override_before, _file_tree(game.override))

    def test_bg2ee_biff_tables_install_and_uninstall_without_materializing_tables(self) -> None:
        game = self._make_game()
        self._assert_installed(game)
        self._assert_uninstalled(game)

    def test_uninstall_survives_tilde_in_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbm~utility-xp-installer-") as temporary:
            game = SyntheticGame(Path(temporary) / "game")
            self._assert_installed(game)
            self.assertIn("~SETUP-CHRIZ-BG-MODPACK.TP2~", game.active_log().upper())
            self._assert_uninstalled(game)

    def test_eet_installs_and_uninstalls_without_changing_effective_override_tables(self) -> None:
        game = self._make_game(game="eet", table_location="override")
        self._assert_installed(game)
        self._assert_uninstalled(game)

    def test_uninstall_restores_every_preexisting_owned_resource_byte_exactly(self) -> None:
        game = self._make_game(existing_publications=True)
        self._assert_installed(game)
        self._assert_uninstalled(game)

    def test_user_config_is_copied_byte_exactly_without_evaluate_buffer(self) -> None:
        custom_config = (
            b"-- User settings: 125%, literal %LANGUAGE%, CRLF preserved.\r\n"
            b"CBM_UtilityXP_Config = { spellMultiplier = 1.25, lockMultiplier = 0.8 }\r\n"
        )
        game = self._make_game(custom_config=custom_config)
        self._assert_installed(game)
        self.assertEqual(custom_config, (game.override / "cbmuxpc.lua").read_bytes())
        self._assert_uninstalled(game)

    def test_bgee_is_skipped_without_changes(self) -> None:
        self._assert_skipped(self._make_game(game="bgee"), r"(?i)BG2|EET")

    def test_missing_eeex_is_skipped_without_changes(self) -> None:
        self._assert_skipped(self._make_game(eeex=False), r"(?i)EEex")

    def test_missing_xpbonus_is_skipped_without_changes(self) -> None:
        self._assert_skipped(
            self._make_game(missing_tables=("XPBONUS.2DA",)), r"(?i)XPBONUS"
        )

    def test_missing_xplevel_is_skipped_without_changes(self) -> None:
        self._assert_skipped(
            self._make_game(missing_tables=("XPLEVEL.2DA",)), r"(?i)XPLEVEL"
        )


if __name__ == "__main__":
    unittest.main()
