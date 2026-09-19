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
BUILD_HELPERS_TPA = ROOT / "chriz-bg-modpack/lib/cbm_npc_build_helpers.tpa"
KIVAN_BAFS = (
    ROOT / "chriz-bg-modpack/baf/cbm_kivan_saha01.baf",
    ROOT / "chriz-bg-modpack/baf/cbm_kivan_saha02.baf",
)

EFFECT_SIZE = 0x108
STANDARD_PROFICIENCIES = set(range(89, 109)) | set(range(111, 116))
TRUECLASS = 0x40000000
ENCHANTER_KIT_ID = 0x0200
ENCHANTER_KIT = ENCHANTER_KIT_ID << 16
ELDRITCH_KNIGHT_KIT_ID = 0x4123
ELDRITCH_KNIGHT_KIT = ELDRITCH_KNIGHT_KIT_ID << 16
SWASHBUCKLER_KIT_ID = 0x412C
SWASHBUCKLER_KIT = SWASHBUCKLER_KIT_ID << 16
BOUNTY_HUNTER_KIT = 0x40180000
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
    effect_size = EFFECT_SIZE if data[0x33] == 1 else 0x30
    end = offset + count * effect_size
    if len(data) < 0x2D4 or end > len(data):
        raise AssertionError("invalid synthetic CRE effect table")
    return [
        data[start : start + effect_size]
        for start in range(offset, end, effect_size)
    ]


def proficiency_map(data: bytes) -> dict[int, int]:
    result: dict[int, int] = {}
    for effect in effect_records(data):
        v2 = len(effect) == EFFECT_SIZE
        if (u32(effect, 0x08) if v2 else u16(effect, 0)) != 233:
            continue
        stat = u32(effect, 0x18 if v2 else 0x08) & 0xFFFF
        if stat in STANDARD_PROFICIENCIES:
            if stat in result:
                raise AssertionError(f"duplicate proficiency stat {stat}")
            result[stat] = u32(effect, 0x14 if v2 else 0x04)
    return result


def unrelated_effects(data: bytes) -> list[bytes]:
    opcode_offset, stat_offset = (0x08, 0x18) if data[0x33] else (0x00, 0x08)
    return [
        effect
        for effect in effect_records(data)
        if not (
            (u32(effect, opcode_offset) if data[0x33] else u16(effect, opcode_offset)) == 233
            and (u32(effect, stat_offset) & 0xFFFF) in STANDARD_PROFICIENCIES
        )
    ]


def replace_effects(data: bytes, effects: list[bytes]) -> bytes:
    """Rebuild the synthetic fixture's final effect block, preserving its header."""
    output = bytearray(data[:u32(data, 0x2C4)])
    struct.pack_into("<I", output, 0x2C8, len(effects))
    return bytes(output) + b"".join(effects)


def use_v1_effects(source: bytes) -> bytes:
    v1_effects = []
    for effect in effect_records(source):
        v1 = bytearray(0x30)
        struct.pack_into("<H", v1, 0x00, u32(effect, 0x08))
        struct.pack_into("<I", v1, 0x04, u32(effect, 0x14))
        struct.pack_into("<I", v1, 0x08, u32(effect, 0x18))
        v1[0x0C] = 9
        v1[0x12] = 100
        v1[0x14:0x1C] = effect[0x20:0x28]
        v1_effects.append(bytes(v1))
    output = bytearray(replace_effects(source, v1_effects))
    output[0x33] = 0
    return bytes(output)


def fixture_template(component: int, source: bytes) -> str:
    """Convenience for original fixtures only; compatibility cases name their tier."""
    if component == 1:
        return {660_000: "E3FADE13", 2_500_000: "E3FADE25"}[u32(source, 0x18)]
    if component == 3:
        return {
            161_000: "MAZZY8", 400_000: "MAZZY9",
            1_200_000: "MAZZY12", 2_500_000: "MAZZY15",
        }[u32(source, 0x18)]
    if component == 5:
        if source[0x280:0x285].upper() == b"TTXAN":
            return "TTXAN"
        return {10_042: "XAN4", 41_549: "XAN6", 2_561: "XAN_"}[u32(source, 0x18)]
    return "unused"


def add_previous_kit_grants(source: bytes) -> bytes:
    """Give a synthetic CRE old CLAB grants and unrelated personal abilities."""
    clab_effect = bytearray(make_effect(0, 1, 0, 15))
    struct.pack_into("<I", clab_effect, 0x88, 1)
    clab_effect[0x8C:0x94] = b"CBMKAP\0\0"
    item_effect = bytearray(clab_effect)
    struct.pack_into("<I", item_effect, 0x88, 2)
    unrelated_effect = bytearray(make_effect(177, 0, 0, 16))
    unrelated_effect[0x30:0x38] = b"CBMKAP\0\0"
    source = replace_effects(
        source, effect_records(source) + [bytes(clab_effect), bytes(item_effect), bytes(unrelated_effect)],
    )
    spells = (b"CBMPERS", b"CBMKGA", b"CBMQUEST", b"CBMKAP")
    known = b"".join(struct.pack("<8sHH", spell, 0, 2) for spell in spells)
    memory = struct.pack("<HHHHII", 0, len(spells), len(spells), 2, 0, len(spells))
    memorized = b"".join(struct.pack("<8sI", spell, 1) for spell in spells)
    added = known + memory + memorized
    header = bytearray(source[:0x2D4])
    for pointer in (0x2A0, 0x2A8, 0x2B0, 0x2B8, 0x2BC, 0x2C4):
        struct.pack_into("<I", header, pointer, u32(header, pointer) + len(added))
    struct.pack_into("<II", header, 0x2A0, 0x2D4, len(spells))
    struct.pack_into("<II", header, 0x2A8, 0x2D4 + len(known), 1)
    struct.pack_into("<II", header, 0x2B0, 0x2D4 + len(known) + len(memory), len(spells))
    struct.pack_into("<I", header, 0x10, 0x2000 | 0x1F8)
    return bytes(header) + added + source[0x2D4:]


def previous_kit_resources() -> dict[str, bytes]:
    return {
        "KITLIST.2DA": (
            "2DA V1.0\n0\n ROWNAME LOWER MIXED HELP ABILITIES PROFICIENCY UNUSABLE CLASS KITIDS\n"
            "18 BOUNTY_HUNTER 0 0 0 CBMOLDK 0 0x00000000 4 0x4018\n"
        ).encode("ascii"),
        "CBMOLDK.2DA": b"2DA V1.0\n****\n 1 2\nABILITY1 GA_CBMKGA ****\nABILITY2 AP_CBMKAP ****\n",
    }


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
    def __init__(
        self, temporary: tempfile.TemporaryDirectory[str], *, kit_ids: str | None = None,
        class_ids: str | None = None, xplevel: bytes | None = None,
        extra_resources: dict[str, bytes] | None = None,
    ):
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
            class_ids if class_ids is not None else (
                "IDS V1.0\n1 MAGE\n2 FIGHTER\n4 THIEF\n7 FIGHTER_MAGE\n"
                "9 FIGHTER_THIEF\n"
            ),
            encoding="ascii",
        )
        resource_path(self.override, "KIT.IDS").write_text(
            kit_ids if kit_ids is not None else (
                "IDS V1.0\n0x0200 MAGESCHOOL_ENCHANTER\n0x4000 TRUECLASS\n"
                f"0x{ELDRITCH_KNIGHT_KIT_ID:04X} C0EK\n"
                f"0x{SWASHBUCKLER_KIT_ID:04X} SWASHBUCKLER\n"
            ),
            encoding="ascii",
        )
        resource_path(self.override, "XPLEVEL.2DA").write_bytes(
            make_xplevel() if xplevel is None else xplevel
        )
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
        for name, payload in (extra_resources or {}).items():
            resource_path(self.override, name).write_bytes(payload)
            self.stable_paths += (resource_path(self.override, name),)
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
        kit_ids: str | None = None,
        class_ids: str | None = None,
        xplevel: bytes | None = None,
        template: str | None = None,
        extra_resources: dict[str, bytes] | None = None,
        verify_uninstall: bool = False,
    ) -> tuple[bytes | None, str]:
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        with tempfile.TemporaryDirectory(prefix="cbm-priority-npc-") as raw_temp:
            temporary = tempfile.TemporaryDirectory(dir=raw_temp)
            try:
                game = SyntheticGame(
                    temporary, kit_ids=kit_ids, class_ids=class_ids, xplevel=xplevel,
                    extra_resources=extra_resources,
                )
                harness = game.root / PATCH_HARNESS.name
                shutil.copy2(PATCH_HARNESS, harness)
                source_path = game.root / f"source{suffix}"
                output_path = game.root / f"output{suffix}"
                source_path.write_bytes(source)
                if verify_uninstall:
                    output_path.write_bytes(source)
                command = [
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
                        "--args",
                        template if template is not None else fixture_template(component, source),
                        "--args",
                        BUILD_HELPERS_TPA.as_posix(),
                        "--language",
                        "0",
                        "--use-lang",
                        "en_us",
                        "--no-exit-pause",
                        "--quick-log",
                    ]
                result = subprocess.run(
                    command,
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
                    output = output_path.read_bytes()
                    if verify_uninstall:
                        command[command.index("--force-install-list")] = "--force-uninstall-list"
                        uninstall = subprocess.run(
                            command, cwd=game.root, capture_output=True, text=True,
                            timeout=45, check=False,
                        )
                        self.assertEqual(0, uninstall.returncode, uninstall.stdout + uninstall.stderr)
                        self.assertEqual(source, output_path.read_bytes())
                        self.assertEqual(source, source_path.read_bytes())
                        game.assert_context_unchanged(self)
                    return output, transcript
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
        before_slots, after_slots = u32(before, 0x2B8), u32(after, 0x2B8)
        self.assertEqual(before[before_slots:before_slots + 80], after[after_slots:after_slots + 80])
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
                        "--args",
                        fixture_template(component, source),
                        "--args",
                        BUILD_HELPERS_TPA.as_posix(),
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

    def test_fade_rejects_wrong_identity(self):
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

    def test_mazzy_writes_complete_allocations_without_additive_reapply(self):
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
                    {105: 4, 91: target_sword}, proficiency_map(transformed)
                )
                self.assertEqual(source[0x273], transformed[0x273])
                self.assertEqual(u32(source, 0x244), u32(transformed, 0x244))
                self.assert_cre_state_preserved(source, transformed)
                twice, _ = self.transform(MAZZY_TPA, 3, transformed)
                self.assertEqual(transformed, twice)

    def test_mazzy_rejects_wrong_identity(self):
        source = make_cre(
            death_variable="Mazzy",
            xp=400_000,
            class_id=2,
            kit=TRUECLASS,
            levels=(9, 1, 1),
            proficiencies={105: 3, 91: 2},
        )
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
            ("SKIE", 17_123, 17, 48, 65),
            ("BDSKIE", 3, 201, 54, 255),
            ("BDSKIED", 123_456, 123, 0, 123),
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

    def test_skie_rejects_non_thief_wrong_kit_and_skill_overflow(self):
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
        self.assertRegex(transcript, r"(?i)(overflow|255|range)")

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
        self.assertIn("unsupported Xan template", transcript)

    def test_xan_uses_installed_target_symbols_without_requiring_source_symbols(self):
        source = make_cre(
            death_variable="XAN", xp=10_042, class_id=1, kit=0x02000000,
            levels=(4, 1, 1), hp=(11, 16), proficiencies={96: 1},
        )
        kit_ids = (
            "IDS V1.0\n0x4033 C0EK\n"
        )
        transformed, _ = self.transform(
            XAN_TPA, 5, source, kit_ids=kit_ids,
            class_ids="IDS V1.0\n7 FIGHTER_MAGE\n",
        )
        assert transformed is not None
        self.assertEqual(0x40330000, u32(transformed, 0x244))
        self.assertEqual(7, transformed[0x273])
        self.assertEqual((3, 3, 0), tuple(transformed[0x234:0x237]))
        self.assert_cre_state_preserved(source, transformed)

    def test_xan_rejects_missing_or_invalid_target_kit_before_writes(self):
        source = make_cre(
            death_variable="XAN", xp=10_042, class_id=1, kit=0x02000000,
            levels=(4, 1, 1), hp=(11, 16), proficiencies={96: 1},
        )
        for target in ("", "0x4000 C0EK\n", "0x8000 C0EK\n"):
            with self.subTest(target=target):
                _, transcript = self.transform(
                    XAN_TPA, 5, source, expect_success=False,
                    kit_ids="IDS V1.0\n0x4000 TRUECLASS\n" + target,
                )
                self.assertIn("C0EK", transcript)

    def test_xan_public_component_with_canonical_kit_table_scopes_changes_and_uninstalls(self):
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        with tempfile.TemporaryDirectory(prefix="cbm-xan-public-") as raw_temp:
            temporary = tempfile.TemporaryDirectory(dir=raw_temp)
            with temporary:
                game = SyntheticGame(temporary, kit_ids=(
                    "IDS V1.0\n0x0200 MAGESCHOOL_ENCHANTER\n"
                    "0x4000 TRUECLASS\n0x4033 C0EK\n"
                ))
                shutil.copy2(ROOT / "setup-chriz-bg-modpack.tp2", game.root)
                shutil.copytree(ROOT / "chriz-bg-modpack", game.root / "chriz-bg-modpack")
                resource_path(game.override, "EET.FLAG").write_bytes(b"synthetic EET marker")
                (game.root / "weidu.log").write_text(
                    "~ARTISANSKITPACK/ARTISANSKITPACK.TP2~ #0 #20000 // prerequisite\n"
                    "~ARTISANSKITPACK_NPC/ARTISANSKITPACK_NPC.TP2~ #0 #20002 // prerequisite\n",
                    encoding="ascii",
                )
                profiles = (
                    ("XAN4", "XAN", 41_549, (8, 6, 2), (90, 100), (5, 5, 0), (18, 21)),
                    ("XAN6", "XAN", 10_042, (1, 1, 1), (24, 24), (3, 3, 0), (30, 35)),
                    ("TTXAN", "TTXAN", 100_001, (15, 0, 0), (1, 200), (6, 6, 0), (35, 35)),
                )
                for name, dv, xp, levels, hp, _, _ in profiles:
                    resource_path(game.override, name + ".CRE").write_bytes(make_cre(
                        death_variable=dv, xp=xp, class_id=4, kit=0x40550000,
                        levels=levels, hp=hp, thac0=17, proficiencies={115: 4},
                    ))
                resource_path(game.override, "XAN_.CRE").write_bytes(b"unrelated base Xan sentinel")

                def override_files():
                    files = {}
                    for path in game.override.iterdir():
                        if path.is_file():
                            self.assertNotIn(path.name.lower(), files)
                            files[path.name.lower()] = path.read_bytes()
                    return files

                before = override_files()
                common = [
                    self.weidu, "setup-chriz-bg-modpack.tp2", "--noautoupdate",
                    "--no-exit-pause", "--game", str(game.root),
                    "--use-lang", "en_us", "--language", "0",
                ]
                install = subprocess.run(
                    common + ["--force-install-list", "170"], cwd=game.root,
                    capture_output=True, text=True, timeout=45, check=False,
                )
                transcript = install.stdout + install.stderr
                self.assertEqual(0, install.returncode, transcript)
                self.assertIn("SUCCESSFULLY INSTALLED", transcript)
                after = override_files()
                self.assertEqual(
                    {name.lower() + ".cre" for name, *_ in profiles},
                    {name for name in set(before) | set(after) if before.get(name) != after.get(name)},
                )
                for name, _, xp, _, _, levels, hp in profiles:
                    original = before[name.lower() + ".cre"]
                    creature = after[name.lower() + ".cre"]
                    self.assertEqual(7, creature[0x273])
                    self.assertEqual(0x40330000, u32(creature, 0x244))
                    self.assertEqual(xp, u32(creature, 0x18))
                    self.assertEqual(levels, tuple(creature[0x234:0x237]))
                    self.assertEqual(hp, (u16(creature, 0x24), u16(creature, 0x26)))
                    expected = {96: 1, 90: 2, 113: 1}
                    if name != "XAN4":
                        expected[107] = 1
                    self.assertEqual(expected, proficiency_map(creature))
                    self.assert_cre_state_preserved(original, creature)
                uninstall = subprocess.run(
                    common + ["--force-uninstall-list", "170"], cwd=game.root,
                    capture_output=True, text=True, timeout=45, check=False,
                )
                transcript = uninstall.stdout + uninstall.stderr
                self.assertEqual(0, uninstall.returncode, transcript)
                self.assertIn("SUCCESSFULLY REMOVED", transcript)
                self.assertEqual(before, override_files())
                game.assert_context_unchanged(self)

    def test_presets_replace_arbitrary_allocations_and_partial_conversions(self):
        cases = (
            (FADE_TPA, 1, "E3FADE13", "E3FADE", {91: 2, 94: 1, 96: 1, 105: 1, 114: 1}),
            (FADE_TPA, 1, "E3FADE25", "E3FADE", {91: 2, 94: 1, 96: 1, 105: 1, 114: 3}),
            (MAZZY_TPA, 3, "MAZZY8", "MAZZY", {91: 4, 105: 4}),
            (MAZZY_TPA, 3, "MAZZY9", "MAZZY", {91: 3, 105: 4}),
            (MAZZY_TPA, 3, "MAZZY11", "MAZZY", {91: 4, 105: 4}),
            (MAZZY_TPA, 3, "MAZZY12", "MAZZY", {91: 4, 105: 4}),
            (MAZZY_TPA, 3, "MAZZY15", "MAZZY", {91: 4, 105: 4}),
            (XAN_TPA, 5, "XAN4", "XAN", {90: 2, 96: 1, 113: 1}),
            (XAN_TPA, 5, "XAN6", "XAN", {90: 2, 96: 1, 107: 1, 113: 1}),
            (XAN_TPA, 5, "TTXAN", "TTXAN", {90: 2, 96: 1, 107: 1, 113: 1}),
        )
        for tpa, component, template, dv, profs in cases:
            for state in ("missing", "duplicates", "reordered"):
                with self.subTest(template=template, state=state):
                    # XP, current/max HP, class, kit, skills and all level bytes
                    # deliberately differ from every historical source profile.
                    source = make_cre(
                        death_variable=dv, xp=100_001, class_id=7,
                        kit=0x40440000, levels=(17, 12, 4), hp=(91, 123),
                        skills={0x45: 11, 0x67: 12, 0x68: 13, 0x69: 14, 0x66: 29},
                        proficiencies={} if state == "missing" else {89: 4, 90: 5, 91: 1, 115: 3},
                    )
                    records = effect_records(source)
                    if state != "missing":
                        records.extend((make_effect(233, 7, 90, 8), make_effect(233, 3, 91, 9)))
                    # An opcode-233 record outside standard weapon/style stats is
                    # not part of the selected allocation and must survive intact.
                    records.append(make_effect(233, 6, 120, 10))
                    if state == "reordered":
                        records.reverse()
                    source = replace_effects(source, records)
                    transformed, _ = self.transform(tpa, component, source, template=template)
                    assert transformed is not None
                    self.assertEqual(profs, proficiency_map(transformed))
                    self.assertEqual(100_001, u32(transformed, 0x18))
                    self.assert_cre_state_preserved(source, transformed, preserved_skills=(0x66,))
                    if component == 1:
                        self.assertEqual(9, transformed[0x273])
                        self.assertEqual(TRUECLASS, u32(transformed, 0x244))
                        self.assertEqual((6, 7, 0), tuple(transformed[0x234:0x237]))
                        skills = (70, 70, 70, 80) if template == "E3FADE13" else (85, 80, 80, 95)
                        self.assertEqual(skills, tuple(transformed[o] for o in (0x45, 0x67, 0x68, 0x69)))
                        self.assertEqual(source[0x24:0x28], transformed[0x24:0x28])
                    elif component == 3:
                        self.assertEqual(source[:0x2A0], transformed[:0x2A0])
                    else:
                        self.assertEqual(7, transformed[0x273])
                        self.assertEqual(ELDRITCH_KNIGHT_KIT, u32(transformed, 0x244))
                        self.assertEqual((6, 6, 0), tuple(transformed[0x234:0x237]))
                        hp = {"XAN4": (18, 21), "XAN6": (30, 35), "TTXAN": (35, 35)}[template]
                        self.assertEqual(hp, (u16(transformed, 0x24), u16(transformed, 0x26)))
                    twice, _ = self.transform(tpa, component, transformed, template=template)
                    self.assertEqual(transformed, twice)

    def test_public_fade_mazzy_and_skie_presets_select_templates_and_uninstall_exactly(self):
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        with tempfile.TemporaryDirectory(prefix="cbm-priority-public-") as raw_temp:
            temporary = tempfile.TemporaryDirectory(dir=raw_temp)
            with temporary:
                game = SyntheticGame(temporary)
                shutil.copy2(ROOT / "setup-chriz-bg-modpack.tp2", game.root)
                shutil.copytree(ROOT / "chriz-bg-modpack", game.root / "chriz-bg-modpack")
                resources = {}
                for name in ("E3FADE13", "E3FADE25"):
                    resources[name + ".CRE"] = make_cre(
                        death_variable="E3FADE", xp=100_001, class_id=1,
                        kit=0x40550000, levels=(17, 0, 0), hp=(1, 90),
                        skills={0x45: 2, 0x67: 3, 0x68: 4, 0x69: 5},
                        proficiencies={115: 4},
                    )
                for name in ("MAZZY8", "MAZZY9", "MAZZY11", "MAZZY12", "MAZZY15"):
                    resources[name + ".CRE"] = make_cre(
                        death_variable="MAZZY", xp=5, class_id=6, kit=0x40410000,
                        levels=(1, 1, 1), proficiencies={96: 5, 114: 3},
                    )
                for name, dv in (("SKIE", "SKIE"), ("SKIE6", "SKIE"), ("BDSKIE", "BDSKIE"), ("BDSKIED", "BDSKIED")):
                    resources[name + ".CRE"] = make_cre(
                        death_variable=dv, xp=1_000_001, class_id=4,
                        kit=SWASHBUCKLER_KIT, levels=(40, 1, 1),
                        skills={0x67: 12, 0x68: 43}, proficiencies={90: 3, 115: 2},
                    )
                resources["E3AMUL01.ITM"] = make_item()
                for name, payload in resources.items():
                    resource_path(game.override, name).write_bytes(payload)
                resource_path(game.override, "UNRELATED.CRE").write_bytes(b"unrelated sentinel")

                def snapshot():
                    return {path.name.lower(): path.read_bytes() for path in game.override.iterdir() if path.is_file()}

                def run(arguments):
                    result = subprocess.run(
                        [self.weidu, "setup-chriz-bg-modpack.tp2", "--noautoupdate",
                         "--no-exit-pause", "--game", str(game.root),
                         "--use-lang", "en_us", "--language", "0", *arguments],
                        cwd=game.root, capture_output=True, text=True, timeout=45, check=False,
                    )
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)

                before = snapshot()
                run(["--force-install-list", "110", "140", "160"])
                after = snapshot()
                self.assertEqual(
                    {name.lower() for name in resources},
                    {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)},
                )
                for name in ("E3FADE13", "E3FADE25"):
                    creature = after[name.lower() + ".cre"]
                    high = name == "E3FADE25"
                    self.assertEqual(9, creature[0x273])
                    self.assertEqual(TRUECLASS, u32(creature, 0x244))
                    self.assertEqual((6, 7, 0), tuple(creature[0x234:0x237]))
                    self.assertEqual(
                        {91: 2, 94: 1, 96: 1, 105: 1, 114: 3 if high else 1},
                        proficiency_map(creature),
                    )
                    self.assertEqual(
                        (85, 80, 80, 95) if high else (70, 70, 70, 80),
                        tuple(creature[o] for o in (0x45, 0x67, 0x68, 0x69)),
                    )
                    self.assert_cre_state_preserved(before[name.lower() + ".cre"], creature)
                for name in ("MAZZY8", "MAZZY9", "MAZZY11", "MAZZY12", "MAZZY15"):
                    creature = after[name.lower() + ".cre"]
                    self.assertEqual({105: 4, 91: 3 if name == "MAZZY9" else 4}, proficiency_map(creature))
                    self.assertEqual(before[name.lower() + ".cre"][:0x2A0], creature[:0x2A0])
                    self.assert_cre_state_preserved(before[name.lower() + ".cre"], creature)
                for name in ("SKIE", "SKIE6", "BDSKIE", "BDSKIED"):
                    expected = bytearray(before[name.lower() + ".cre"])
                    expected[0x67], expected[0x68] = 55, 0
                    self.assertEqual(bytes(expected), after[name.lower() + ".cre"])
                expected_amulet = bytearray(resources["E3AMUL01.ITM"])
                expected_amulet[0x20] &= 0xFD
                self.assertEqual(bytes(expected_amulet), after["e3amul01.itm"])
                run(["--force-uninstall-list", "110", "140", "160", "--force-install-list", "110", "140", "160"])
                self.assertEqual(after, snapshot())
                run(["--force-uninstall-list", "110", "140", "160"])
                self.assertEqual(before, snapshot())
                game.assert_context_unchanged(self)

    def test_presets_reject_invalid_identity_template_and_effect_bounds(self):
        for tpa, component, template, dv in (
            (FADE_TPA, 1, "E3FADE13", "E3FADE"),
            (MAZZY_TPA, 3, "MAZZY9", "MAZZY"),
            (XAN_TPA, 5, "XAN6", "XAN"),
        ):
            source = make_cre(
                death_variable=dv, xp=12345, class_id=1, kit=TRUECLASS,
                levels=(1, 1, 1), proficiencies={91: 1},
            )
            for invalid in ("identity", "template", "truncated", "offset", "count"):
                with self.subTest(component=component, invalid=invalid):
                    changed = bytearray(source)
                    chosen = template
                    if invalid == "identity":
                        changed[0x280:0x2A0] = b"ANOTHER".ljust(32, b"\0")
                    elif invalid == "template":
                        chosen = "UNRELATED"
                    elif invalid == "truncated":
                        changed = changed[:0x100]
                    elif invalid == "offset":
                        struct.pack_into("<I", changed, 0x2C4, len(changed))
                    else:
                        # High-word corruption must not be hidden by READ_SHORT.
                        struct.pack_into("<I", changed, 0x2C8, 0x10002)
                    _, transcript = self.transform(
                        tpa, component, bytes(changed), template=chosen, expect_success=False,
                    )
                    self.assertIn(tpa.stem, transcript)

    def test_fade_and_xan_follow_changed_installed_progression(self):
        rows = make_xplevel().decode("ascii").splitlines()
        for index, row in enumerate(rows):
            fields = row.split()
            if fields and fields[0] in {"FIGHTER", "THIEF", "MAGE"}:
                fields[1:-1] = [str(int(value) // 2) for value in fields[1:-1]]
                rows[index] = " ".join(fields)
        xplevel = ("\n".join(rows) + "\n").encode("ascii")
        for tpa, component, template, dv, xp, expected in (
            (FADE_TPA, 1, "E3FADE13", "E3FADE", 660_000, (10, 13, 0)),
            (XAN_TPA, 5, "XAN4", "XAN", 10_042, (4, 4, 0)),
        ):
            with self.subTest(template=template):
                source = make_cre(
                    death_variable=dv, xp=xp, class_id=4, kit=TRUECLASS,
                    levels=(42, 39, 1), proficiencies={},
                )
                transformed, _ = self.transform(
                    tpa, component, source, template=template, xplevel=xplevel,
                )
                assert transformed is not None
                self.assertEqual(expected, tuple(transformed[0x234:0x237]))
                self.assertEqual(xp, u32(transformed, 0x18))
                twice, _ = self.transform(
                    tpa, component, transformed, template=template, xplevel=xplevel,
                )
                self.assertEqual(transformed, twice)

    def test_presets_support_v1_effects_and_empty_effect_tables(self):
        for tpa, component, template, dv, profs in (
            (FADE_TPA, 1, "E3FADE13", "E3FADE", {91: 2, 94: 1, 96: 1, 105: 1, 114: 1}),
            (MAZZY_TPA, 3, "MAZZY9", "MAZZY", {91: 3, 105: 4}),
            (XAN_TPA, 5, "XAN6", "XAN", {90: 2, 96: 1, 107: 1, 113: 1}),
        ):
            for empty in (False, True):
                with self.subTest(template=template, empty=empty):
                    source = make_cre(
                        death_variable=dv, xp=12345, class_id=4, kit=TRUECLASS,
                        levels=(1, 0, 0), proficiencies={90: 5, 115: 3},
                    )
                    source = use_v1_effects(source)
                    if empty:
                        source = replace_effects(source, [])
                    transformed, _ = self.transform(tpa, component, source, template=template)
                    assert transformed is not None
                    self.assertEqual(0, transformed[0x33])
                    self.assertEqual(profs, proficiency_map(transformed))
                    self.assert_cre_state_preserved(source, transformed)
                    twice, _ = self.transform(tpa, component, transformed, template=template)
                    self.assertEqual(transformed, twice)

    def test_presets_clear_increment_mode_proficiencies_and_preserve_spell_state_slots(self):
        for tpa, component, template, dv, profs in (
            (FADE_TPA, 1, "E3FADE13", "E3FADE", {91: 2, 94: 1, 96: 1, 105: 1, 114: 1}),
            (MAZZY_TPA, 3, "MAZZY9", "MAZZY", {91: 3, 105: 4}),
            (XAN_TPA, 5, "XAN6", "XAN", {90: 2, 96: 1, 107: 1, 113: 1}),
        ):
            for effect_version in (0, 1):
                with self.subTest(template=template, effect_version=effect_version):
                    source = make_cre(
                        death_variable=dv, xp=100_001, class_id=4, kit=TRUECLASS,
                        levels=(1, 1, 1), proficiencies={105: 5, 115: 3},
                    )
                    source = replace_effects(source, effect_records(source) + [
                        make_effect(233, 11, 109, 11),
                        make_effect(233, 12, 0x10000 | 110, 12),
                        make_effect(233, 2, 0x10000 | 106, 13),
                        make_effect(233, 3, 0x10000 | 105, 14),
                    ])
                    if effect_version == 0:
                        source = use_v1_effects(source)
                    transformed, _ = self.transform(tpa, component, source, template=template)
                    assert transformed is not None
                    self.assertEqual(profs, proficiency_map(transformed))
                    self.assert_cre_state_preserved(source, transformed)
                    opcode_offset, stat_offset = (0x08, 0x18) if effect_version else (0x00, 0x08)
                    owned = [effect for effect in effect_records(transformed)
                             if (u32(effect, opcode_offset) if effect_version else u16(effect, opcode_offset)) == 233
                             and (u32(effect, stat_offset) & 0xFFFF) in STANDARD_PROFICIENCIES]
                    self.assertEqual(len(profs), len(owned))
                    self.assertTrue(all(u32(effect, stat_offset) <= 0xFFFF for effect in owned))
                    twice, _ = self.transform(tpa, component, transformed, template=template)
                    self.assertEqual(transformed, twice)

    def test_fade_and_xan_support_short_xp_tables_with_optional_sentinel(self):
        for sentinel in (False, True):
            rows = make_xplevel().decode("ascii").splitlines()
            rows[2] = " ".join(str(level) for level in range(1, 16 if sentinel else 15))
            for index in range(3, len(rows)):
                fields = rows[index].split()
                if fields:
                    rows[index] = " ".join(fields[:15] + (["-1"] if sentinel else []))
            xplevel = ("\n".join(rows) + "\n").encode("ascii")
            for tpa, component, template, dv, xp, levels in (
                (FADE_TPA, 1, "E3FADE13", "E3FADE", 660_000, (9, 11, 0)),
                (XAN_TPA, 5, "XAN6", "XAN", 41_549, (5, 5, 0)),
            ):
                with self.subTest(template=template, sentinel=sentinel):
                    source = make_cre(
                        death_variable=dv, xp=xp, class_id=4, kit=TRUECLASS,
                        levels=(1, 0, 0), proficiencies={},
                    )
                    transformed, _ = self.transform(
                        tpa, component, source, template=template, xplevel=xplevel,
                    )
                    assert transformed is not None
                    self.assertEqual(levels, tuple(transformed[0x234:0x237]))
                    self.assertEqual(xp, u32(transformed, 0x18))
                    twice, _ = self.transform(
                        tpa, component, transformed, template=template, xplevel=xplevel,
                    )
                    self.assertEqual(transformed, twice)

                    malformed = xplevel.replace(b"FIGHTER 0 2000 ", b"FIGHTER 0 0 ")
                    self.assertNotEqual(xplevel, malformed)
                    _, transcript = self.transform(
                        tpa, component, source, template=template,
                        xplevel=malformed, expect_success=False,
                    )
                    self.assertIn("increasing", transcript)

    def test_fade_and_xan_remove_previous_kit_grants_and_dual_class_flags(self):
        for tpa, component, template, dv, target_class, target_kit, profs in (
            (FADE_TPA, 1, "E3FADE13", "E3FADE", 9, TRUECLASS,
             {91: 2, 94: 1, 96: 1, 105: 1, 114: 1}),
            (XAN_TPA, 5, "XAN6", "XAN", 7, ELDRITCH_KNIGHT_KIT,
             {90: 2, 96: 1, 107: 1, 113: 1}),
        ):
            with self.subTest(template=template):
                source = add_previous_kit_grants(make_cre(
                    death_variable=dv, xp=100_001, class_id=4,
                    kit=BOUNTY_HUNTER_KIT, levels=(12, 8, 3),
                    proficiencies={115: 3},
                ))
                options = {
                    "template": template,
                    "extra_resources": previous_kit_resources(),
                    "kit_ids": (
                        "IDS V1.0\n0x4018 BOUNTY_HUNTER\n0x4000 TRUECLASS\n"
                        f"0x{ELDRITCH_KNIGHT_KIT_ID:04X} C0EK\n"
                    ),
                }
                transformed, _ = self.transform(tpa, component, source, verify_uninstall=True, **options)
                assert transformed is not None
                self.assertEqual(0x2000, u32(transformed, 0x10))
                self.assertEqual(target_class, transformed[0x273])
                self.assertEqual(target_kit, u32(transformed, 0x244))
                self.assertEqual(profs, proficiency_map(transformed))
                self.assertEqual(100_001, u32(transformed, 0x18))

                def spell_records(creature, pointer, count):
                    offset = u32(creature, pointer)
                    return [creature[index:index + 12]
                            for index in range(offset, offset + u32(creature, count) * 12, 12)]

                for pointer, count in ((0x2A0, 0x2A4), (0x2B0, 0x2B4)):
                    before = spell_records(source, pointer, count)
                    expected = [record for record in before
                                if record[:8].rstrip(b"\0") in {b"CBMPERS", b"CBMQUEST"}]
                    self.assertEqual(2, len(expected))
                    self.assertEqual(expected, spell_records(transformed, pointer, count))
                memory = u32(transformed, 0x2A8)
                self.assertEqual(1, u32(transformed, 0x2AC))
                self.assertEqual(0, u32(transformed, memory + 8))
                self.assertEqual(2, u32(transformed, memory + 12))

                expected_effects = [effect for effect in effect_records(source)
                                    if not (u32(effect, 0x88) == 1
                                            and effect[0x8C:0x94].rstrip(b"\0") == b"CBMKAP")]
                self.assertEqual(len(effect_records(source)) - 1, len(expected_effects))
                self.assert_cre_state_preserved(replace_effects(source, expected_effects), transformed)
                twice, _ = self.transform(tpa, component, transformed, **options)
                self.assertEqual(transformed, twice)


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
