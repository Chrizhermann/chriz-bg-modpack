from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH_HARNESS = ROOT / "tests/weidu/priority_npc_patch_harness.tp2"
KIVAN_HARNESS = ROOT / "tests/weidu/priority_npc_kivan_harness.tp2"
FADE_TPA = ROOT / "chriz-bg-modpack/lib/cbm_fade_ft_fix.tpa"
MAZZY_TPA = ROOT / "chriz-bg-modpack/lib/cbm_mazzy_prof_fix.tpa"
SKIE_TPA = ROOT / "chriz-bg-modpack/lib/cbm_skie_skill_fix.tpa"
XAN_TPA = ROOT / "chriz-bg-modpack/lib/cbm_xan_ek_fix.tpa"
KIVAN_BAFS = (
    ROOT / "chriz-bg-modpack/baf/cbm_kivan_saha01.baf",
    ROOT / "chriz-bg-modpack/baf/cbm_kivan_saha02.baf",
)

EFFECT_SIZE = 0x108
TRUECLASS = 0x40000000
ENCHANTER_KIT_ID = 0x0200
ENCHANTER_KIT = ENCHANTER_KIT_ID << 16
ELDRITCH_KNIGHT_KIT_ID = 0x4123
ELDRITCH_KNIGHT_KIT = ELDRITCH_KNIGHT_KIT_ID << 16
SWASHBUCKLER_KIT_ID = 0x412C
SWASHBUCKLER_KIT = SWASHBUCKLER_KIT_ID << 16
ONE_EMPTY_STRING_TLK = (
    struct.pack("<8sHII", b"TLK V1  ", 0, 1, 0x2C)
    + struct.pack("<H8siiII", 0, b"\0" * 8, 0, 0, 0, 0)
)


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def make_effect(opcode: int, parameter1: int, parameter2: int, seed: int) -> bytes:
    effect = bytearray(EFFECT_SIZE)
    effect[:8] = b"EFF V2.0"
    struct.pack_into("<I", effect, 0x08, opcode)
    struct.pack_into("<I", effect, 0x14, parameter1)
    struct.pack_into("<I", effect, 0x18, parameter2)
    effect[0x20:0x28] = f"CBM{seed:05d}".encode("ascii")[:8]
    effect[0x100:0x108] = bytes((seed + index) & 0xFF for index in range(8))
    return bytes(effect)


def make_cre(
    *,
    death_variable: str,
    xp: int,
    class_id: int,
    kit: int,
    levels: tuple[int, int, int],
    hp: tuple[int, int] = (37, 41),
    thac0: int = 13,
    skills: dict[int, int] | None = None,
    proficiencies: dict[int, int] | None = None,
    seed: int = 1,
) -> bytes:
    """Build a deterministic, game-byte-free CRE V1.0 fixture."""
    header = bytearray(0x2D4)
    header[:8] = b"CRE V1.0"
    header[0x33] = 1
    header[0x80:0xA0] = bytes((seed + index * 3) & 0xFF for index in range(0x20))
    struct.pack_into("<I", header, 0x18, xp)
    struct.pack_into("<H", header, 0x24, hp[0])
    struct.pack_into("<H", header, 0x26, hp[1])
    header[0x52] = thac0
    header[0x234:0x237] = bytes(levels)
    struct.pack_into("<I", header, 0x244, kit)
    header[0x273] = class_id
    encoded_dv = death_variable.encode("ascii")
    if len(encoded_dv) > 31:
        raise ValueError("death variable too long")
    header[0x280 : 0x280 + len(encoded_dv)] = encoded_dv
    for offset, value in (skills or {}).items():
        header[offset] = value

    item_slots_offset = len(header)
    item_slots = b"\xff" * 80
    effects_offset = item_slots_offset + len(item_slots)
    effects = [make_effect(326, 700 + seed, 105, seed)]
    effects.extend(
        make_effect(233, value, stat, seed + stat)
        for stat, value in sorted((proficiencies or {}).items())
    )
    for offset in (0x2A0, 0x2A8, 0x2B0, 0x2B8, 0x2BC):
        struct.pack_into("<I", header, offset, item_slots_offset)
    struct.pack_into("<I", header, 0x2C4, effects_offset)
    struct.pack_into("<I", header, 0x2C8, len(effects))
    return bytes(header) + item_slots + b"".join(effects)


def make_item(*, fighter_thief_blocked: bool = True, seed: int = 1) -> bytes:
    item = bytearray(0x72)
    item[:8] = b"ITM V1  "
    item[0x08:0x18] = bytes((seed + index * 7) & 0xFF for index in range(0x10))
    item[0x1E:0x22] = bytes((0xB6, 0xFD, 0xBF, 0xFF))
    if fighter_thief_blocked:
        item[0x20] |= 0x02
    else:
        item[0x20] &= 0xFD
    item[0x40:0x60] = bytes((seed + 100 + index) & 0xFF for index in range(0x20))
    struct.pack_into("<I", item, 0x64, 0x72)
    struct.pack_into("<H", item, 0x68, 0)
    struct.pack_into("<I", item, 0x6A, 0x72)
    struct.pack_into("<H", item, 0x6E, 0)
    struct.pack_into("<H", item, 0x70, 0)
    return bytes(item)


def effect_records(data: bytes) -> list[bytes]:
    offset = u32(data, 0x2C4)
    count = u32(data, 0x2C8)
    end = offset + count * EFFECT_SIZE
    if len(data) < 0x2D4 or end > len(data):
        raise AssertionError("invalid synthetic CRE effect table")
    return [
        data[start : start + EFFECT_SIZE]
        for start in range(offset, end, EFFECT_SIZE)
    ]


def proficiency_map(data: bytes) -> dict[int, int]:
    result: dict[int, int] = {}
    for effect in effect_records(data):
        if u32(effect, 0x08) != 233:
            continue
        stat = u32(effect, 0x18)
        if 89 <= stat <= 115:
            if stat in result:
                raise AssertionError(f"duplicate proficiency stat {stat}")
            result[stat] = u32(effect, 0x14)
    return result


def unrelated_effects(data: bytes) -> list[bytes]:
    return [
        effect
        for effect in effect_records(data)
        if not (u32(effect, 0x08) == 233 and 89 <= u32(effect, 0x18) <= 115)
    ]


def find_weidu() -> str | None:
    configured = os.environ.get("WEIDU_BIN")
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("weidu") or shutil.which("weidu.exe")


def resource_path(root: Path, name: str) -> Path:
    """Return the lowercase on-disk path WeiDU uses on case-sensitive hosts."""
    return root / name.lower()


def xplevel_row(label: str, values: list[int]) -> str:
    if len(values) != 50:
        raise ValueError("XPLEVEL rows need levels 1 through 50")
    return f"{label} " + " ".join(str(value) for value in values) + " -1"


def make_xplevel() -> bytes:
    fighter = [
        0, 2_000, 4_000, 8_000, 16_000, 32_000, 64_000, 125_000,
        250_000, 500_000, 750_000, 1_000_000, 1_250_000, 1_500_000,
    ]
    thief = [
        0, 1_250, 2_500, 5_000, 10_000, 20_000, 40_000, 70_000,
        110_000, 160_000, 220_000, 440_000, 660_000, 880_000,
        1_100_000, 1_320_000,
    ]
    mage = [0, 2_500, 5_000, 10_000, 20_000, 40_000]
    for values in (fighter, thief, mage):
        while len(values) < 50:
            values.append(values[-1] + 1_000_000)
    text = "\n".join(
        (
            "2DA V1.0",
            "-1",
            " ".join(str(level) for level in range(1, 52)),
            xplevel_row("FIGHTER", fighter),
            xplevel_row("THIEF", thief),
            xplevel_row("MAGE", mage),
            "",
        )
    )
    return text.encode("ascii")


def write_marker_key_and_bif(game_root: Path) -> Path:
    payload = b"synthetic BG2EE marker"
    bif_relative = Path("DATA/CBMTEST.BIF")
    bif_path = game_root / bif_relative
    bif_path.parent.mkdir(parents=True)
    table_offset = 0x14
    payload_offset = table_offset + 0x10
    bif_path.write_bytes(
        struct.pack("<4s4sIII", b"BIFF", b"V1  ", 1, 0, table_offset)
        + struct.pack("<IIIHH", 0, payload_offset, len(payload), 1010, 0)
        + payload
    )
    encoded_name = (str(bif_relative).replace("/", "\\") + "\0").encode("ascii")
    bif_table_offset = 0x18
    resource_table_offset = bif_table_offset + 0x0C
    names_offset = resource_table_offset + 0x0E
    key = bytearray(
        struct.pack(
            "<4s4sIIII", b"KEY ", b"V1  ", 1, 1,
            bif_table_offset, resource_table_offset,
        )
    )
    key.extend(
        struct.pack(
            "<IIHH", bif_path.stat().st_size, names_offset, len(encoded_name), 0
        )
    )
    key.extend(struct.pack("<8sHI", b"OH6000\0\0", 1010, 0))
    key.extend(encoded_name)
    (game_root / "chitin.key").write_bytes(key)
    return bif_path


class SyntheticGame:
    def __init__(self, temporary: tempfile.TemporaryDirectory[str]):
        self.root = Path(temporary.name) / "game"
        self.root.mkdir()
        self.override = self.root / "override"
        self.override.mkdir()
        self.bif = write_marker_key_and_bif(self.root)
        self.lang_tlk = self.root / "lang/en_us/dialog.tlk"
        self.lang_tlk.parent.mkdir(parents=True)
        self.lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.root_tlk = self.root / "dialog.tlk"
        self.root_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        resource_path(self.override, "CLASS.IDS").write_text(
            "IDS V1.0\n1 MAGE\n2 FIGHTER\n4 THIEF\n7 FIGHTER_MAGE\n"
            "9 FIGHTER_THIEF\n",
            encoding="ascii",
        )
        resource_path(self.override, "KIT.IDS").write_text(
            "IDS V1.0\n0x0200 ENCHANTER\n0x4000 TRUECLASS\n"
            f"0x{ELDRITCH_KNIGHT_KIT_ID:04X} C0EK\n"
            f"0x{SWASHBUCKLER_KIT_ID:04X} SWASHBUCKLER\n",
            encoding="ascii",
        )
        resource_path(self.override, "XPLEVEL.2DA").write_bytes(make_xplevel())
        resource_path(self.override, "TRIGGER.IDS").write_text(
            "IDS V1.0\n0x400F Global(S:Name*,S:Area*,I:Value*)\n",
            encoding="ascii",
        )
        resource_path(self.override, "ACTION.IDS").write_text(
            "IDS V1.0\n0 NoAction()\n", encoding="ascii"
        )
        resource_path(self.override, "OBJECT.IDS").write_text(
            "IDS V1.0\n1 Myself\n", encoding="ascii"
        )
        self.stable_paths = (
            self.root / "chitin.key",
            self.bif,
            self.lang_tlk,
            self.root_tlk,
            resource_path(self.override, "CLASS.IDS"),
            resource_path(self.override, "KIT.IDS"),
            resource_path(self.override, "XPLEVEL.2DA"),
            resource_path(self.override, "TRIGGER.IDS"),
            resource_path(self.override, "ACTION.IDS"),
            resource_path(self.override, "OBJECT.IDS"),
        )
        self.stable_hashes = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.stable_paths
        }

    def assert_context_unchanged(self, testcase: unittest.TestCase) -> None:
        for path, digest in self.stable_hashes.items():
            testcase.assertEqual(
                digest,
                hashlib.sha256(path.read_bytes()).hexdigest(),
                f"harness changed installed context {path.name}",
            )


class PriorityNpcHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.weidu = find_weidu()

    def test_cre_effect_counts_use_the_full_dword_field(self):
        for library in (FADE_TPA, MAZZY_TPA, XAN_TPA):
            with self.subTest(library=library.name):
                source = library.read_text(encoding="utf-8")
                self.assertIn("READ_LONG 0x2c8", source)
                self.assertNotIn("READ_SHORT 0x2c8", source)

    def transform(
        self,
        tpa: Path,
        component: int,
        source: bytes,
        *,
        suffix: str = ".cre",
        expect_success: bool = True,
    ) -> tuple[bytes | None, str]:
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        with tempfile.TemporaryDirectory(prefix="cbm-priority-npc-") as raw_temp:
            temporary = tempfile.TemporaryDirectory(dir=raw_temp)
            try:
                game = SyntheticGame(temporary)
                harness = game.root / PATCH_HARNESS.name
                shutil.copy2(PATCH_HARNESS, harness)
                source_path = game.root / f"source{suffix}"
                output_path = game.root / f"output{suffix}"
                source_path.write_bytes(source)
                result = subprocess.run(
                    [
                        self.weidu,
                        harness.name,
                        "--no-auto-tp2",
                        "--game",
                        str(game.root),
                        "--force-install-list",
                        str(component),
                        "--args",
                        tpa.as_posix(),
                        "--args",
                        source_path.as_posix(),
                        "--args",
                        output_path.as_posix(),
                        "--language",
                        "0",
                        "--use-lang",
                        "en_us",
                        "--no-exit-pause",
                        "--quick-log",
                    ],
                    cwd=game.root,
                    capture_output=True,
                    text=True,
                    timeout=45,
                    check=False,
                )
                transcript = result.stdout + result.stderr
                game.assert_context_unchanged(self)
                if expect_success:
                    self.assertEqual(0, result.returncode, transcript)
                    self.assertIn("SUCCESSFULLY INSTALLED", transcript)
                    self.assertTrue(output_path.is_file(), transcript)
                    return output_path.read_bytes(), transcript
                self.assertNotEqual(0, result.returncode, transcript)
                self.assertIn("NOT INSTALLED DUE TO ERRORS", transcript)
                self.assertFalse(output_path.exists(), transcript)
                return None, transcript
            finally:
                temporary.cleanup()

    def assert_cre_state_preserved(
        self,
        before: bytes,
        after: bytes,
        *,
        preserved_skills: tuple[int, ...] = (),
    ) -> None:
        self.assertEqual(before[0x52], after[0x52], "THAC0 changed")
        self.assertEqual(before[0x80:0xA0], after[0x80:0xA0])
        self.assertEqual(unrelated_effects(before), unrelated_effects(after))
        for offset in preserved_skills:
            self.assertEqual(before[offset], after[offset], f"skill {offset:#x} changed")

    def test_patch_harness_components_restore_preexisting_outputs_on_uninstall(self):
        cases = (
            (
                "fade-cre",
                FADE_TPA,
                1,
                make_cre(
                    death_variable="E3FADE",
                    xp=660_000,
                    class_id=4,
                    kit=TRUECLASS,
                    levels=(13, 0, 0),
                    skills={0x45: 85, 0x67: 80, 0x68: 80, 0x69: 95},
                    proficiencies={96: 1, 94: 1, 105: 1, 91: 1, 114: 1},
                ),
                ".cre",
            ),
            ("fade-amulet", FADE_TPA, 2, make_item(), ".itm"),
            (
                "mazzy",
                MAZZY_TPA,
                3,
                make_cre(
                    death_variable="Mazzy",
                    xp=400_000,
                    class_id=2,
                    kit=TRUECLASS,
                    levels=(9, 1, 1),
                    proficiencies={105: 5, 91: 2},
                ),
                ".cre",
            ),
            (
                "skie",
                SKIE_TPA,
                4,
                make_cre(
                    death_variable="SKIE",
                    xp=5_098,
                    class_id=4,
                    kit=SWASHBUCKLER_KIT,
                    levels=(4, 1, 1),
                    skills={0x67: 20, 0x68: 25},
                ),
                ".cre",
            ),
            (
                "xan",
                XAN_TPA,
                5,
                make_cre(
                    death_variable="XAN",
                    xp=10_042,
                    class_id=1,
                    kit=ENCHANTER_KIT,
                    levels=(4, 1, 1),
                    hp=(11, 16),
                    proficiencies={96: 1},
                ),
                ".cre",
            ),
        )
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")

        for name, tpa, component, source, suffix in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix=f"cbm-priority-uninstall-{name}-"
            ) as raw_temp:
                temporary = tempfile.TemporaryDirectory(dir=raw_temp)
                try:
                    game = SyntheticGame(temporary)
                    shutil.copy2(PATCH_HARNESS, game.root / PATCH_HARNESS.name)
                    source_path = game.root / f"source{suffix}"
                    output_path = game.root / f"output{suffix}"
                    source_path.write_bytes(source)
                    sentinel = f"preexisting {name} output".encode("ascii")
                    output_path.write_bytes(sentinel)
                    common = [
                        self.weidu,
                        PATCH_HARNESS.name,
                        "--no-auto-tp2",
                        "--game",
                        str(game.root),
                    ]
                    trailing = [
                        "--args",
                        tpa.as_posix(),
                        "--args",
                        source_path.as_posix(),
                        "--args",
                        output_path.as_posix(),
                        "--language",
                        "0",
                        "--use-lang",
                        "en_us",
                        "--no-exit-pause",
                        "--quick-log",
                    ]
                    install = subprocess.run(
                        common + ["--force-install-list", str(component)] + trailing,
                        cwd=game.root,
                        capture_output=True,
                        text=True,
                        timeout=45,
                        check=False,
                    )
                    transcript = install.stdout + install.stderr
                    self.assertEqual(0, install.returncode, transcript)
                    self.assertNotEqual(sentinel, output_path.read_bytes())

                    uninstall = subprocess.run(
                        common + ["--force-uninstall-list", str(component)] + trailing,
                        cwd=game.root,
                        capture_output=True,
                        text=True,
                        timeout=45,
                        check=False,
                    )
                    transcript = uninstall.stdout + uninstall.stderr
                    self.assertEqual(0, uninstall.returncode, transcript)
                    self.assertEqual(sentinel, output_path.read_bytes())
                    game.assert_context_unchanged(self)
                finally:
                    temporary.cleanup()

    def test_fade_uses_installed_xp_tables_and_reconciles_full_build(self):
        cases = (
            (
                660_000,
                (9, 11, 0),
                {0x45: 70, 0x67: 70, 0x68: 70, 0x69: 80},
                {96: 1, 94: 1, 105: 1, 91: 2, 114: 1},
            ),
            (
                2_500_000,
                (13, 15, 0),
                {0x45: 85, 0x67: 80, 0x68: 80, 0x69: 95},
                {96: 1, 94: 1, 105: 1, 91: 2, 114: 3},
            ),
        )
        source_skills = {
            0x45: 85, 0x64: 7, 0x65: 11, 0x66: 39,
            0x67: 80, 0x68: 80, 0x69: 95, 0x6A: 13,
        }
        source_profs = {96: 1, 94: 1, 105: 1, 91: 1, 114: 1}
        for index, (xp, levels, skills, profs) in enumerate(cases, start=1):
            with self.subTest(xp=xp):
                source = make_cre(
                    death_variable="E3FADE",
                    xp=xp,
                    class_id=4,
                    kit=TRUECLASS,
                    levels=(13, 0, 0),
                    thac0=9 + index,
                    skills=source_skills,
                    proficiencies=source_profs,
                    seed=10 + index,
                )
                transformed, _ = self.transform(FADE_TPA, 1, source)
                assert transformed is not None
                self.assertEqual(xp, u32(transformed, 0x18))
                self.assertEqual(9, transformed[0x273])
                self.assertEqual(TRUECLASS, u32(transformed, 0x244))
                self.assertEqual(levels, tuple(transformed[0x234:0x237]))
                for offset, expected in skills.items():
                    self.assertEqual(expected, transformed[offset])
                self.assertEqual(profs, proficiency_map(transformed))
                if levels[1] == 11:
                    self.assertEqual(
                        40 + 25 * (levels[1] - 1),
                        sum(
                            transformed[offset]
                            for offset in (0x45, 0x67, 0x68, 0x69)
                        ),
                    )
                else:
                    self.assertEqual(
                        340,
                        sum(
                            transformed[offset]
                            for offset in (0x45, 0x67, 0x68, 0x69)
                        ),
                        "the T15 resource must retain its authored distribution",
                    )
                self.assert_cre_state_preserved(
                    source,
                    transformed,
                    preserved_skills=(0x64, 0x65, 0x66, 0x6A),
                )
                twice, _ = self.transform(FADE_TPA, 1, transformed)
                self.assertEqual(transformed, twice)

    def test_fade_rejects_wrong_or_partially_modified_source_state(self):
        source = bytearray(
            make_cre(
                death_variable="NOTFADE",
                xp=660_000,
                class_id=4,
                kit=TRUECLASS,
                levels=(13, 0, 0),
                skills={0x45: 85, 0x67: 80, 0x68: 80, 0x69: 95},
                proficiencies={96: 1, 94: 1, 105: 1, 91: 1, 114: 1},
            )
        )
        _, transcript = self.transform(FADE_TPA, 1, bytes(source), expect_success=False)
        self.assertIn("expected death variable E3FADE", transcript)

        source[0x280:0x287] = b"E3FADE\0"
        source[0x45] = 84
        _, transcript = self.transform(FADE_TPA, 1, bytes(source), expect_success=False)
        self.assertIn("unexpected Fade source state", transcript)

    def test_fade_amulet_clears_only_fighter_thief_block_and_is_idempotent(self):
        source = make_item(fighter_thief_blocked=True, seed=17)
        transformed, _ = self.transform(FADE_TPA, 2, source, suffix=".itm")
        assert transformed is not None
        expected = bytearray(source)
        expected[0x20] &= 0xFD
        self.assertEqual(bytes(expected), transformed)
        twice, _ = self.transform(FADE_TPA, 2, transformed, suffix=".itm")
        self.assertEqual(transformed, twice)

        malformed = bytearray(source)
        malformed[:8] = b"BAD V1  "
        _, transcript = self.transform(
            FADE_TPA, 2, bytes(malformed), suffix=".itm", expect_success=False
        )
        self.assertIn("expected an ITM V1 resource", transcript)

    def test_mazzy_moves_exactly_one_pip_without_additive_reapply(self):
        cases = (
            (161_000, 3, 4),
            (400_000, 2, 3),
            (1_200_000, 3, 4),
            (2_500_000, 3, 4),
        )
        for index, (xp, source_sword, target_sword) in enumerate(cases, start=1):
            with self.subTest(xp=xp):
                source = make_cre(
                    death_variable="Mazzy",
                    xp=xp,
                    class_id=6 if index % 2 else 2,
                    kit=0x40410000 if index % 2 else TRUECLASS,
                    levels=(8 + index, 1, 1),
                    thac0=6 + index,
                    proficiencies={105: 5, 91: source_sword, 96: 1},
                    seed=30 + index,
                )
                transformed, _ = self.transform(MAZZY_TPA, 3, source)
                assert transformed is not None
                self.assertEqual(
                    {105: 4, 91: target_sword, 96: 1}, proficiency_map(transformed)
                )
                self.assertEqual(source[0x273], transformed[0x273])
                self.assertEqual(u32(source, 0x244), u32(transformed, 0x244))
                self.assert_cre_state_preserved(source, transformed)
                twice, _ = self.transform(MAZZY_TPA, 3, transformed)
                self.assertEqual(transformed, twice)

    def test_mazzy_rejects_wrong_identity_and_noncanonical_pips(self):
        source = make_cre(
            death_variable="Mazzy",
            xp=400_000,
            class_id=2,
            kit=TRUECLASS,
            levels=(9, 1, 1),
            proficiencies={105: 3, 91: 2},
        )
        _, transcript = self.transform(MAZZY_TPA, 3, source, expect_success=False)
        self.assertIn("unexpected Mazzy proficiency state", transcript)

        wrong_dv = bytearray(source)
        wrong_dv[0x280:0x285] = b"Kivan"
        _, transcript = self.transform(MAZZY_TPA, 3, bytes(wrong_dv), expect_success=False)
        self.assertIn("expected death variable MAZZY", transcript)

    def test_skie_moves_source_move_silently_pool_once_and_preserves_kit(self):
        cases = (
            ("SKIE", 5_098, 20, 25, 45),
            ("SKIE", 20_056, 30, 35, 65),
            ("BDSKIE", 64_000, 35, 35, 70),
            ("BDSKIED", 64_000, 35, 35, 70),
        )
        for index, (dv, xp, locks, move, expected_locks) in enumerate(cases, start=1):
            with self.subTest(dv=dv, xp=xp):
                source = make_cre(
                    death_variable=dv,
                    xp=xp,
                    class_id=4,
                    kit=SWASHBUCKLER_KIT,
                    levels=(3 + index, 1, 1),
                    thac0=10 + index,
                    skills={
                        0x45: 20 + index,
                        0x64: 9,
                        0x65: 12,
                        0x66: 15,
                        0x67: locks,
                        0x68: move,
                        0x69: 25,
                        0x6A: 30,
                    },
                    proficiencies={91: 1, 105: 1},
                    seed=50 + index,
                )
                transformed, _ = self.transform(SKIE_TPA, 4, source)
                assert transformed is not None
                self.assertEqual(expected_locks, transformed[0x67])
                self.assertEqual(0, transformed[0x68])
                self.assertEqual(SWASHBUCKLER_KIT, u32(transformed, 0x244))
                self.assert_cre_state_preserved(
                    source,
                    transformed,
                    preserved_skills=(0x45, 0x64, 0x65, 0x66, 0x69, 0x6A),
                )
                twice, _ = self.transform(SKIE_TPA, 4, transformed)
                self.assertEqual(transformed, twice)

    def test_skie_rejects_non_thief_and_unrecognized_skill_state(self):
        source = make_cre(
            death_variable="SKIE",
            xp=5_098,
            class_id=2,
            kit=TRUECLASS,
            levels=(4, 1, 1),
            skills={0x67: 20, 0x68: 25},
        )
        _, transcript = self.transform(SKIE_TPA, 4, source, expect_success=False)
        self.assertIn("expected Thief class", transcript)

        source = bytearray(source)
        source[0x273] = 4
        _, transcript = self.transform(SKIE_TPA, 4, bytes(source), expect_success=False)
        self.assertIn("expected installed Swashbuckler kit", transcript)

        struct.pack_into("<I", source, 0x244, SWASHBUCKLER_KIT)
        source[0x67] = 250
        _, transcript = self.transform(SKIE_TPA, 4, bytes(source), expect_success=False)
        self.assertIn("unexpected Skie skill state", transcript)

    def test_xan_reconciles_only_missing_eet_variants_and_preserves_thac0(self):
        library = XAN_TPA.read_text(encoding="utf-8")
        self.assertNotRegex(library, r"(?im)^\s*(?:READ|WRITE)_BYTE\s+0x52\b")
        cases = (
            ("XAN", 10_042, (4, 1, 1), (11, 16), (3, 3, 0), (18, 21)),
            ("XAN", 41_549, (6, 1, 1), (17, 24), (5, 5, 0), (30, 35)),
            ("TTXAN", 41_549, (6, 1, 1), (24, 24), (5, 5, 0), (35, 35)),
        )
        for index, (dv, xp, source_levels, source_hp, target_levels, target_hp) in enumerate(cases, start=1):
            with self.subTest(dv=dv, xp=xp, hp=source_hp):
                source = make_cre(
                    death_variable=dv,
                    xp=xp,
                    class_id=1,
                    kit=ENCHANTER_KIT,
                    levels=source_levels,
                    hp=source_hp,
                    thac0=15 + index,
                    skills={0x66: 9 + index},
                    proficiencies={96: 1, 107: 1} if xp == 41_549 else {96: 1},
                    seed=70 + index,
                )
                transformed, _ = self.transform(XAN_TPA, 5, source)
                assert transformed is not None
                self.assertEqual(xp, u32(transformed, 0x18))
                self.assertEqual(7, transformed[0x273])
                self.assertEqual(ELDRITCH_KNIGHT_KIT, u32(transformed, 0x244))
                self.assertEqual(target_levels, tuple(transformed[0x234:0x237]))
                self.assertEqual(target_hp, (u16(transformed, 0x24), u16(transformed, 0x26)))
                expected_profs = proficiency_map(source) | {90: 2, 113: 1}
                self.assertEqual(expected_profs, proficiency_map(transformed))
                self.assert_cre_state_preserved(
                    source, transformed, preserved_skills=(0x66,)
                )
                twice, _ = self.transform(XAN_TPA, 5, transformed)
                self.assertEqual(transformed, twice)

    def test_xan_base_variant_is_deliberately_outside_component_170(self):
        xan_base = make_cre(
            death_variable="XAN",
            xp=2_561,
            class_id=1,
            kit=ENCHANTER_KIT,
            levels=(2, 1, 1),
            hp=(6, 8),
            thac0=20,
            proficiencies={96: 1},
        )
        _, transcript = self.transform(XAN_TPA, 5, xan_base, expect_success=False)
        self.assertIn("unsupported Xan XP/DV profile", transcript)

    def test_xan_rejects_wrong_source_kit_and_partial_conversion(self):
        source = make_cre(
            death_variable="XAN",
            xp=10_042,
            class_id=1,
            kit=TRUECLASS,
            levels=(4, 1, 1),
            hp=(11, 16),
            proficiencies={96: 1},
        )
        _, transcript = self.transform(XAN_TPA, 5, source, expect_success=False)
        self.assertIn("unexpected Xan class/kit state", transcript)

        partial = bytearray(source)
        partial[0x273] = 7
        struct.pack_into("<I", partial, 0x244, ELDRITCH_KNIGHT_KIT)
        _, transcript = self.transform(XAN_TPA, 5, bytes(partial), expect_success=False)
        self.assertIn("unexpected converted Xan state", transcript)


class KivanGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.weidu = find_weidu()

    def run_harness(
        self,
        game: SyntheticGame,
        operation_args: list[str],
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                self.weidu,
                KIVAN_HARNESS.name,
                "--no-auto-tp2",
                "--game",
                str(game.root),
                *operation_args,
                "--args",
                KIVAN_BAFS[0].as_posix(),
                "--args",
                KIVAN_BAFS[1].as_posix(),
                "--language",
                "0",
                "--use-lang",
                "en_us",
                "--no-exit-pause",
                "--quick-log",
            ],
            cwd=game.root,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )

    def decompile(self, game: SyntheticGame, bcs: Path) -> str:
        decompile_dir = game.root / "decompiled"
        decompile_dir.mkdir(exist_ok=True)
        result = subprocess.run(
            [
                self.weidu,
                "--game",
                str(game.root),
                str(bcs),
                "--no-exit-pause",
            ],
            cwd=decompile_dir,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        transcript = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, transcript)
        candidates = [
            path
            for path in decompile_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".baf"
        ]
        self.assertEqual(1, len(candidates), transcript)
        return candidates[0].read_text(encoding="utf-8", errors="replace")

    def test_first_party_guards_compile_idempotently_and_uninstall_exactly(self):
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        with tempfile.TemporaryDirectory(prefix="cbm-kivan-") as raw_temp:
            temporary = tempfile.TemporaryDirectory(dir=raw_temp)
            try:
                game = SyntheticGame(temporary)
                shutil.copy2(KIVAN_HARNESS, game.root / KIVAN_HARNESS.name)
                sentinels = {
                    "X#SAHA01.BCS": b"preexisting saha01 script",
                    "X#SAHA02.BCS": b"preexisting saha02 script",
                }
                for name, payload in sentinels.items():
                    resource_path(game.override, name).write_bytes(payload)

                install = self.run_harness(
                    game, ["--force-install-list", "1"]
                )
                transcript = install.stdout + install.stderr
                self.assertEqual(0, install.returncode, transcript)
                self.assertIn("SUCCESSFULLY INSTALLED", transcript)
                first = {
                    name: resource_path(game.override, name).read_bytes()
                    for name in sentinels
                }
                self.assertEqual(first["X#SAHA01.BCS"], first["X#SAHA02.BCS"])
                self.assertNotEqual(sentinels["X#SAHA01.BCS"], first["X#SAHA01.BCS"])

                text = self.decompile(
                    game, resource_path(game.override, "X#SAHA01.BCS")
                )
                compact = "".join(text.split()).upper()
                self.assertIn('GLOBAL("X#KIVANSEA","GLOBAL",3)', compact)
                self.assertIn("NOACTION()", compact)
                self.assertEqual(1, compact.count("RESPONSE#100"))

                reinstall = self.run_harness(
                    game,
                    [
                        "--force-uninstall-list", "1",
                        "--force-install-list", "1",
                    ],
                )
                transcript = reinstall.stdout + reinstall.stderr
                self.assertEqual(0, reinstall.returncode, transcript)
                self.assertEqual(
                    first,
                    {
                        name: resource_path(game.override, name).read_bytes()
                        for name in sentinels
                    },
                )

                uninstall = self.run_harness(
                    game, ["--force-uninstall-list", "1"]
                )
                transcript = uninstall.stdout + uninstall.stderr
                self.assertEqual(0, uninstall.returncode, transcript)
                for name, payload in sentinels.items():
                    self.assertEqual(
                        payload, resource_path(game.override, name).read_bytes()
                    )
                game.assert_context_unchanged(self)
                self.assertFalse(
                    any(path.name.lower().startswith("cbm_kivan") for path in game.override.iterdir())
                )
            finally:
                temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
