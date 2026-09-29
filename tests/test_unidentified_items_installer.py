"""Real WeiDU smoke tests for the optional unidentified-item appearance installer.

All runs target disposable synthetic games. The executable contains only toy
pattern snippets; no game executable, item, save, or profile is copied here.
"""

from __future__ import annotations

import os
import hashlib
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
SETUP_NAME = "setup-chriz-bg-modpack.tp2"
MOD_NAME = "chriz-bg-modpack"
COMPONENT = 630
SOURCE = ROOT / MOD_NAME / "unidentified-items"
PUBLICATIONS = ("M_CBMID.lua", "CBMID.lua", "CBMIDCFG.lua", "CBMID.MRK")
TLK = struct.pack("<8sHII", b"TLK V1  ", 0, 1, 0x2C) + struct.pack(
    "<H8siiII", 0, b"\0" * 8, 0, 0, 0, 0
)
LOADER_DB = (
    b"; synthetic pre-existing loader data\r\n"
    b"[Foreign::Hook]\r\nPattern=DEADBEEF\r\nOperations=ADD 0\r\n"
    b"CachedAddress=12345\r\n"
)


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
    if local.is_file():
        return local.resolve()
    return None


WEIDU_SOURCE = _find_weidu()
LUA = shutil.which("lua") or shutil.which("luajit")


def _tree(root: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if path.is_file():
            key = path.relative_to(root).as_posix().upper()
            if key in result:
                raise AssertionError(f"case-colliding fixture paths: {key}")
            result[key] = path.read_bytes()
    return result


def _without_weidu_artifacts(tree: dict[str, bytes]) -> dict[str, bytes]:
    return {
        key: payload
        for key, payload in tree.items()
        if not key.startswith("WEIDU_EXTERNAL/")
        and key not in {
            "WEIDU.LOG",
            "WEIDU.CONF",
            "SETUP-CHRIZ-BG-MODPACK.DEBUG",
        }
    }


def _catalog_rows(path: Path) -> list[dict[str, str]]:
    lines = [
        line.split("//", 1)[0].strip()
        for line in path.read_text(encoding="ascii").splitlines()
    ]
    lines = [line for line in lines if line]
    if len(lines) < 4 or lines[0].upper() != "2DA V1.0":
        raise AssertionError(f"invalid fixture catalog: {path}")
    columns = lines[2].split()
    rows = []
    for line in lines[3:]:
        fields = line.split()
        if len(fields) != len(columns) + 1:
            raise AssertionError(f"malformed catalog row in {path}: {line}")
        rows.append(dict(zip(("ROW", *columns), fields)))
    return rows


def _toy_executable(patterns: list[str], *, missing: int | None = None,
                    duplicate: int | None = None,
                    wrong_opcode: int | None = None) -> bytes:
    executable = bytearray(b"synthetic Baldur.exe, no game code\0")
    call_sites = []
    for index, pattern in enumerate(patterns):
        if index == missing:
            continue
        snippet = bytes.fromhex(pattern.replace("??", "90"))
        # The catalog ends immediately before a native E8 rel32 call.
        opcode = b"\x90" if index == wrong_opcode else b"\xE8"
        hook = snippet + opcode + b"\0" * 4
        executable.extend(b"\xCC" * 29)
        call_sites.append(len(executable) + len(snippet))
        executable.extend(hook)
        if index == duplicate:
            executable.extend(b"\xCC" * 29)
            call_sites.append(len(executable) + len(snippet))
            executable.extend(hook)
    executable.extend(b"\xCC" * 97)
    common_target = len(executable)
    executable.extend(b"\xC3")  # synthetic RET target shared by all calls
    for call_site in call_sites:
        struct.pack_into("<i", executable, call_site + 1,
                         common_target - (call_site + 5))
    return bytes(executable)


def _write_key_bif(root: Path, items: dict[str, bytes], marker: str,
                   *, missing_bam: str | None = None,
                   corrupt_bam: str | None = None) -> None:
    resources = [(marker, 1010, b"synthetic engine marker")]
    resources += [(name, 1005, payload) for name, payload in items.items()]
    bam_refs = {
        payload[offset:offset + 8].split(b"\0", 1)[0].decode("ascii")
        for payload in items.values() if payload.startswith(b"ITM V1  ")
        for offset in (0x3A, 0x44, 0x58)
    }
    resources += [
        (name, 1000, b"corrupt BAM" if name == corrupt_bam
         else b"BAM V1  " + b"\0" * 0x10)
        for name in sorted(bam_refs) if name and name != missing_bam
    ]
    bif_path = root / "data" / "cbmid.bif"
    bif_path.parent.mkdir()
    payload_offset = 0x14 + len(resources) * 0x10
    table = bytearray()
    payloads = bytearray()
    for index, (_, kind, payload) in enumerate(resources):
        table.extend(struct.pack("<IIIHH", index, payload_offset + len(payloads),
                                 len(payload), kind, 0))
        payloads.extend(payload)
    bif_path.write_bytes(
        struct.pack("<4s4sIII", b"BIFF", b"V1  ", len(resources), 0, 0x14)
        + table + payloads
    )
    bif_name = b"data\\cbmid.bif\0"
    name_offset = 0x18 + 0x0C + len(resources) * 0x0E
    key = bytearray(struct.pack("<4s4sIIII", b"KEY ", b"V1  ", 1,
                                len(resources), 0x18, 0x24))
    key.extend(struct.pack("<IIHH", bif_path.stat().st_size, name_offset,
                           len(bif_name), 0))
    for index, (name, kind, _) in enumerate(resources):
        key.extend(struct.pack("<8sHI", name.encode("ascii"), kind, index))
    key.extend(bif_name)
    (root / "chitin.key").write_bytes(key)


def _toy_item(name: str, item_type: int, *, blank_picture: bool = False) -> bytes:
    """Small ITM V1 header with independent visible BAM fields."""
    item = bytearray(0x72)
    item[:8] = b"ITM V1  "
    struct.pack_into("<H", item, 0x1C, item_type)
    suffix = hashlib.sha1(name.encode("ascii")).hexdigest()[:7].upper().encode("ascii")
    item[0x3A:0x42] = b"I" + suffix
    item[0x44:0x4C] = b"G" + suffix
    if not blank_picture:
        item[0x58:0x60] = b"P" + suffix
    return bytes(item)


class SyntheticGame:
    def __init__(self, root: Path, *, game: str = "bg2ee", eeex: bool = True,
                 loader_db: bool = True, executable: bool = True,
                 missing_pattern: int | None = None,
                 duplicate_pattern: int | None = None,
                 wrong_opcode: int | None = None,
                 missing_donor: str | None = None,
                 corrupt_donor: str | None = None,
                 missing_bam_for: str | None = None,
                 corrupt_bam_for: str | None = None,
                 blank_picture_for: str | None = None,
                 marker_conflict: bool = False,
                 log_conflict: bool = False,
                 unrelated_randomiser: bool = False,
                 existing_hook_label: bool = False,
                 preexisting_publications: bool = False) -> None:
        assert WEIDU_SOURCE is not None
        root.mkdir()
        self.root = root
        self.blank_picture_for = blank_picture_for
        self.override = root / "override"
        self.override.mkdir()
        shutil.copy2(WEIDU_SOURCE, root / "weidu.exe")
        self.weidu = root / "weidu.exe"
        shutil.copy2(ROOT / SETUP_NAME, root / SETUP_NAME)
        shutil.copytree(ROOT / MOD_NAME, root / MOD_NAME)
        self.source = root / MOD_NAME / "unidentified-items"

        hooks = _catalog_rows(self.source / "hooks.2da")
        assert len(hooks) == 4
        patterns = [row["PATTERN"] for row in hooks]
        # WeiDU's Unix filesystem backend lowercases paths. Use portable names
        # so the same synthetic Windows-game inputs are discoverable in CI.
        if executable:
            (root / "baldur.exe").write_bytes(
                _toy_executable(patterns, missing=missing_pattern,
                                duplicate=duplicate_pattern,
                                wrong_opcode=wrong_opcode)
            )
        if loader_db:
            loader_bytes = LOADER_DB
            if existing_hook_label:
                loader_bytes += b"[CBMID::Inventory]\r\nPattern=CAFEBABE\r\n"
            (root / "infinityloader.db").write_bytes(loader_bytes)
        (root / "Baldur.lua").write_bytes(b"-- Existing profile settings\r\n")
        (root / "UI.menu").write_bytes(b"-- Existing UI\r\n")
        (root / "engine.lua").write_bytes(b"-- Existing mechanic\r\n")
        (root / "save" / "test").mkdir(parents=True)
        (root / "save" / "test" / "BALDUR.GAM").write_bytes(b"synthetic save sentinel")
        (root / "lang" / "en_us").mkdir(parents=True)
        (root / "lang" / "en_us" / "dialog.tlk").write_bytes(TLK)
        (root / "dialog.tlk").write_bytes(TLK)
        self.override.joinpath("foreign.2da").write_bytes(b"foreign\0\xff\r\n")
        if game == "eet":
            self.override.joinpath("eet.flag").write_bytes(b"synthetic EET marker\r\n")
        if eeex:
            self.override.joinpath("m___eeex.lua").write_bytes(b"-- synthetic EEex marker\r\n")
        if marker_conflict:
            self.override.joinpath("flrc570.mrk").write_bytes(b"foreign randomiser marker")
        if log_conflict or unrelated_randomiser:
            component = 570 if log_conflict else 569
            (root / "weidu.log").write_text(
                f"~randomiser/randomiser.tp2~ #0 #{component} // synthetic component\n",
                encoding="ascii",
            )
        if preexisting_publications:
            for name in PUBLICATIONS:
                self.override.joinpath(name.lower()).write_bytes(
                    b"-- pre-existing publication \x00\xff\r\n"
                )

        donor_rows = _catalog_rows(self.source / "donors.2da")
        donor_types = {
            row["DONOR"].upper(): int(row["ROW"])
            for row in donor_rows if row["ROW"].isdigit()
        }
        donor_types["MISC59"] = 0
        donors = {
            name: _toy_item(name, item_type,
                            blank_picture=name == blank_picture_for)
            for name, item_type in donor_types.items() if name != missing_donor
        }
        if corrupt_donor:
            donors[corrupt_donor] = b"corrupt item"
        game_marker = "OH1000" if game == "bgee" else "OH6000"
        def inventory_icon(name: str | None) -> str | None:
            if name is None:
                return None
            return _toy_item(name, 0)[0x3A:0x42].decode("ascii")

        _write_key_bif(root, donors, game_marker,
                       missing_bam=inventory_icon(missing_bam_for),
                       corrupt_bam=inventory_icon(corrupt_bam_for))
        self.before = _without_weidu_artifacts(_tree(root))
        self.override_before = _tree(self.override)

    def run(self, *, uninstall: bool = False,
            reinstall: bool = False) -> subprocess.CompletedProcess[str]:
        if uninstall and reinstall:
            raise ValueError("choose uninstall or reinstall")
        action = (
            ["--force-uninstall-list", str(COMPONENT), "--force-install-list", str(COMPONENT)]
            if reinstall else
            ["--force-uninstall-list" if uninstall else "--force-install-list",
             str(COMPONENT)]
        )
        return subprocess.run(
            [str(self.weidu), SETUP_NAME, "--game", str(self.root), *action,
             "--language", "0", "--use-lang", "en_us",
             "--no-exit-pause", "--noautoupdate", "--no-auto-tp2", "--quick-log"],
            cwd=self.root, capture_output=True, text=True, timeout=90, check=False,
        )

    def active_log(self) -> str:
        path = next((path for path in self.root.iterdir()
                     if path.name.lower() == "weidu.log"), None)
        if path is None:
            return ""
        return "\n".join(line for line in path.read_text(
            encoding="utf-8", errors="replace").splitlines()
            if not line.lstrip().startswith("//"))


@unittest.skipUnless(WEIDU_SOURCE, "WeiDU unavailable")
class UnidentifiedItemsInstallerTests(unittest.TestCase):
    def make_game(self, **kwargs: object) -> SyntheticGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbmid-installer-")
        self.addCleanup(temporary.cleanup)
        return SyntheticGame(Path(temporary.name) / "game", **kwargs)

    def assert_unchanged(self, game: SyntheticGame) -> None:
        self.assertEqual(game.before, _without_weidu_artifacts(_tree(game.root)))
        self.assertEqual(game.override_before, _tree(game.override))

    def assert_refused(self, game: SyntheticGame, reason: str) -> None:
        result = game.run()
        transcript = result.stdout + "\n" + result.stderr
        self.assertRegex(transcript, reason)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        self.assert_unchanged(game)

    def assert_installed(self, game: SyntheticGame) -> None:
        result = game.run()
        transcript = result.stdout + "\n" + result.stderr
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        after = _without_weidu_artifacts(_tree(game.root))
        allowed = {f"OVERRIDE/{name.upper()}" for name in PUBLICATIONS}
        allowed.add("INFINITYLOADER.DB")
        self.assertEqual(set(game.before) | allowed, set(after))
        for name, payload in game.before.items():
            if name != "INFINITYLOADER.DB" and name not in allowed:
                self.assertEqual(payload, after[name], name)
        self.assertIn(LOADER_DB, after["INFINITYLOADER.DB"])
        self.assertEqual(1, after["INFINITYLOADER.DB"].count(b"[Foreign::Hook]"))
        loader = after["INFINITYLOADER.DB"].decode("ascii")
        for row in _catalog_rows(game.source / "hooks.2da"):
            name = row["ROW"]
            self.assertEqual(1, loader.count(f"[CBMID::{name}]"), name)
            section = loader.split(f"[CBMID::{name}]", 1)[1].split("[", 1)[0]
            self.assertIn(f"Pattern={row['PATTERN']}", section)
            self.assertIn(f"Operations=ADD {row['CALL_OFFSET']}", section)
        self.assertEqual(
            b"-- synthetic EEex marker\r\n", after["OVERRIDE/M___EEEX.LUA"]
        )
        config = after["OVERRIDE/CBMIDCFG.LUA"]
        self.assertIn(b"CBMID_Config", config)
        self.assertIn(b"schema=1", config)
        self.assertIn(b"fallback", config)
        self.assertIn(b"types", config)
        self.assertIn(b"hooks", config)
        self.assertNotRegex(config.decode("ascii"), r"%[A-Za-z_][A-Za-z_0-9]*%")
        lua = LuaRuntime()
        lua.execute(config.decode("ascii"))
        lua.execute((SOURCE / "cbmid.lua").read_text(encoding="utf-8"))
        self.assertGreater(lua.globals().CBMID.validate(lua.globals().CBMID_Config), 0)
        if LUA:
            path = (game.override / "cbmidcfg.lua").as_posix()
            script = (
                f"assert(loadfile([=[{path}]=]))();"
                "assert(type(CBMID_Config)=='table');"
                "assert(CBMID_Config.schema==1);"
                "assert(type(CBMID_Config.fallback.inventory)=='string');"
                "assert(type(CBMID_Config.types)=='table');"
                "assert(#CBMID_Config.hooks==4)"
            )
            parsed = subprocess.run([LUA, "-e", script], cwd=game.root,
                                    capture_output=True, text=True, timeout=10,
                                    check=False)
            self.assertEqual(0, parsed.returncode, parsed.stdout + parsed.stderr)
        fallback_suffix = hashlib.sha1(b"MISC59").hexdigest()[:7].upper().encode("ascii")
        fallback_has_picture = game.blank_picture_for != "MISC59"
        for prefix in ((b"I", b"G", b"P") if fallback_has_picture else (b"I", b"G")):
            self.assertIn(prefix + fallback_suffix, config)

    def assert_uninstalled(self, game: SyntheticGame) -> None:
        result = game.run(uninstall=True)
        transcript = result.stdout + "\n" + result.stderr
        self.assertEqual(0, result.returncode, transcript)
        self.assertNotRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        self.assert_unchanged(game)

    def test_bg2ee_installs_and_uninstalls_with_exact_restoration(self) -> None:
        game = self.make_game()
        self.assert_installed(game)
        self.assert_uninstalled(game)

    def test_eet_installs_and_uninstalls(self) -> None:
        game = self.make_game(game="eet")
        self.assert_installed(game)
        self.assert_uninstalled(game)

    def test_reinstall_is_stable(self) -> None:
        game = self.make_game()
        self.assert_installed(game)
        first = _without_weidu_artifacts(_tree(game.root))
        result = game.run(reinstall=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(first, _without_weidu_artifacts(_tree(game.root)))
        self.assert_uninstalled(game)

    def test_preexisting_publications_restore_exactly(self) -> None:
        game = self.make_game(preexisting_publications=True)
        self.assert_installed(game)
        self.assert_uninstalled(game)

    def test_bgee_refused(self) -> None:
        self.assert_refused(self.make_game(game="bgee"), r"(?i)BG2|EET")

    def test_missing_eeex_refused(self) -> None:
        self.assert_refused(self.make_game(eeex=False), r"(?i)EEex")

    def test_missing_loader_database_refused(self) -> None:
        self.assert_refused(self.make_game(loader_db=False), r"(?i)InfinityLoader|loader database")

    def test_missing_native_executable_refused(self) -> None:
        self.assert_refused(self.make_game(executable=False), r"(?i)Windows game executable")

    def test_randomiser_marker_refused(self) -> None:
        self.assert_refused(self.make_game(marker_conflict=True), r"(?i)randomi[sz]er|570")

    def test_randomiser_log_refused(self) -> None:
        self.assert_refused(self.make_game(log_conflict=True), r"(?i)randomi[sz]er|570")

    def test_unrelated_randomiser_component_is_allowed(self) -> None:
        game = self.make_game(unrelated_randomiser=True)
        self.assert_installed(game)
        self.assert_uninstalled(game)

    def test_foreign_owned_hook_label_refused(self) -> None:
        self.assert_refused(self.make_game(existing_hook_label=True),
                            r"(?i)hook definitions|CBMID")

    def test_missing_native_pattern_refused(self) -> None:
        for index, row in enumerate(_catalog_rows(SOURCE / "hooks.2da")):
            with self.subTest(hook=row["ROW"]):
                self.assert_refused(self.make_game(missing_pattern=index),
                                    r"(?i)signature|display code")

    def test_duplicate_native_pattern_refused(self) -> None:
        for index, row in enumerate(_catalog_rows(SOURCE / "hooks.2da")):
            with self.subTest(hook=row["ROW"]):
                self.assert_refused(self.make_game(duplicate_pattern=index),
                                    r"(?i)ambiguous|signature")

    def test_native_call_opcode_must_follow_pattern(self) -> None:
        self.assert_refused(self.make_game(wrong_opcode=0), r"(?i)pattern|opcode|call")

    def test_missing_donor_uses_neutral_fallback(self) -> None:
        donors = _catalog_rows(SOURCE / "donors.2da")
        row = next(row for row in donors
                   if row["ROW"].isdigit() and row["DONOR"].upper() != "MISC59")
        missing = row["DONOR"].upper()
        game = self.make_game(missing_donor=missing)
        self.assert_installed(game)
        config = (game.override / "cbmidcfg.lua").read_bytes()
        missing_entry = f"[{row['ROW']}]=".encode("ascii")
        self.assertNotIn(missing_entry, config)
        self.assert_uninstalled(game)

    def test_optional_picture_may_be_blank(self) -> None:
        game = self.make_game(blank_picture_for="MISC59")
        self.assert_installed(game)
        config = (game.override / "cbmidcfg.lua").read_bytes()
        self.assertIn(b'picture=""', config)
        self.assert_uninstalled(game)

    def test_corrupt_present_donor_fails_without_publications(self) -> None:
        donors = _catalog_rows(SOURCE / "donors.2da")
        corrupt = next(row["DONOR"].upper() for row in donors
                       if row["ROW"].isdigit() and row["DONOR"].upper() != "MISC59")
        self.assert_refused(self.make_game(corrupt_donor=corrupt), r"(?i)donor|ITM|item")

    def test_missing_donor_artwork_fails_without_publications(self) -> None:
        self.assert_refused(self.make_game(missing_bam_for="MISC59"),
                            r"(?i)artwork|BAM")

    def test_corrupt_donor_artwork_fails_without_publications(self) -> None:
        self.assert_refused(self.make_game(corrupt_bam_for="MISC59"),
                            r"(?i)artwork|BAM")

    def test_missing_neutral_fallback_fails_without_publications(self) -> None:
        self.assert_refused(self.make_game(missing_donor="MISC59"),
                            r"(?i)fallback|MISC59|donor")


if __name__ == "__main__":
    unittest.main()
