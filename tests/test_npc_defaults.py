from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TP2 = ROOT / "setup-chriz-bg-modpack.tp2"
VICONIA_TPA = ROOT / "chriz-bg-modpack/lib/cbm_viconia_cleric_thief.tpa"
VICONIA_HARNESS = ROOT / "tests/weidu/viconia_cleric_thief_harness.tp2"
SHARTEEL_TPA = ROOT / "chriz-bg-modpack/lib/cbm_sharteel_wizard_slayer.tpa"
SHARTEEL_HARNESS = ROOT / "tests/weidu/sharteel_wizard_slayer_harness.tp2"

VICONIA_COMPONENT = 192
SHARTEEL_COMPONENT = 193
CLERIC_CLASS = 3
# Deliberately differs from the engine's usual value (15). This proves that
# production code resolves CLERIC_THIEF from the installed CLASS.IDS.
CLERIC_THIEF_CLASS = 73
FIGHTER_CLASS = 2
TRUECLASS_KIT = 0x40000000

SHARTEEL_VARIANTS = ("SHARTE", "SHARTE4", "SHARTE6")
SHARTEEL_DUEL_RESOURCE = "SHARTD"
LEGACY_WIZARD_SLAYER_ID = 0x4002
# Deliberately differs from the stock/legacy 0x4002. With KIT.IDS values stored
# as the CRE kit high word, this must become 0x40A20000 in the CRE dword.
SYNTHETIC_WIZARD_SLAYER_ID = 0x40A2
SYNTHETIC_WIZARD_SLAYER_KIT = SYNTHETIC_WIZARD_SLAYER_ID << 16
SHARTEEL_KIT_OFFSETS = set(range(0x244, 0x248))

VICONIA_VARIANTS = {
    "VICONI": (1_603, 1, 1),
    "VICONI4": (6_134, 3, 3),
    "VICONI6_": (27_628, 5, 5),
    "VICONI6": (161_000, 7, 8),
    "VICONI7": (64_000, 6, 6),
    "VICONI8": (161_000, 7, 8),
    "VICONI9": (400_000, 8, 10),
    "VICONI11": (800_000, 9, 11),
    "VICONI13": (1_200_000, 10, 12),
    "VICONI16": (2_500_000, 13, 15),
}

CLERIC_XP = {
    1: 0,
    2: 1_500,
    3: 3_000,
    4: 6_000,
    5: 13_000,
    6: 27_500,
    7: 55_000,
    8: 110_000,
    9: 225_000,
    10: 450_000,
    11: 675_000,
    12: 900_000,
    13: 1_125_000,
    14: 1_350_000,
    15: 1_575_000,
    16: 1_800_000,
    17: 2_025_000,
    18: 2_250_000,
    19: 2_475_000,
    20: 2_700_000,
}
for _level in range(21, 51):
    CLERIC_XP[_level] = CLERIC_XP[_level - 1] + 225_000
THIEF_XP = {
    1: 0,
    2: 1_250,
    3: 2_500,
    4: 5_000,
    5: 10_000,
    6: 20_000,
    7: 40_000,
    8: 70_000,
    9: 110_000,
    10: 160_000,
    11: 220_000,
    12: 440_000,
    13: 660_000,
    14: 880_000,
    15: 1_100_000,
    16: 1_320_000,
    17: 1_540_000,
    18: 1_760_000,
    19: 1_980_000,
    20: 2_200_000,
}
for _level in range(21, 51):
    THIEF_XP[_level] = THIEF_XP[_level - 1] + 220_000

THIEF_SKILLS = {
    1: (0, 0, 20, 20),
    2: (0, 0, 35, 30),
    3: (0, 0, 45, 45),
    4: (0, 0, 60, 55),
    5: (0, 0, 70, 70),
    6: (0, 0, 85, 80),
    7: (0, 0, 95, 95),
    8: (0, 0, 110, 105),
    9: (0, 0, 120, 120),
    10: (0, 0, 135, 130),
    11: (0, 0, 145, 145),
    12: (0, 0, 160, 155),
    13: (0, 0, 170, 170),
    14: (0, 0, 185, 180),
    15: (0, 0, 195, 195),
}

# Synthetic installed priest-slot progression. The recruitment case under
# discussion intentionally matches the shipped EE table at Cleric 5: 3/3/1.
# Later rows only need to remain complete and deterministic so the production
# code can prove that it reads the installed table rather than hardcoding it.
PRIEST_SLOTS = {
    1: (1, 0, 0, 0, 0, 0, 0),
    2: (2, 0, 0, 0, 0, 0, 0),
    3: (2, 1, 0, 0, 0, 0, 0),
    4: (3, 2, 0, 0, 0, 0, 0),
    5: (3, 3, 1, 0, 0, 0, 0),
    6: (3, 3, 2, 0, 0, 0, 0),
    7: (3, 3, 2, 1, 0, 0, 0),
    8: (3, 3, 3, 2, 0, 0, 0),
    9: (4, 4, 3, 2, 1, 0, 0),
    10: (4, 4, 3, 3, 2, 0, 0),
    11: (5, 4, 4, 3, 2, 1, 0),
    12: (6, 5, 5, 3, 2, 2, 0),
    13: (6, 6, 6, 4, 2, 2, 0),
}
for _level in range(14, 51):
    PRIEST_SLOTS[_level] = PRIEST_SLOTS[13]


def _save_progression(values: tuple[int, ...], widths: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(
        value
        for value, width in zip(values, widths)
        for _ in range(width)
    )


PRIEST_SAVES = {
    "DEATH": _save_progression((10, 9, 7, 6, 5, 4, 2), (3, 3, 3, 3, 3, 3, 32)),
    "WANDS": _save_progression((14, 13, 11, 10, 9, 8, 6), (3, 3, 3, 3, 3, 3, 32)),
    "POLY": _save_progression((13, 12, 10, 9, 8, 7, 5), (3, 3, 3, 3, 3, 3, 32)),
    "BREATH": _save_progression((16, 15, 13, 12, 11, 10, 8), (3, 3, 3, 3, 3, 3, 32)),
    "SPELL": _save_progression((15, 14, 12, 11, 10, 9, 7), (3, 3, 3, 3, 3, 3, 32)),
}
ROGUE_SAVES = {
    "DEATH": _save_progression((13, 12, 11, 10, 9, 8), (4, 4, 4, 4, 4, 30)),
    "WANDS": _save_progression((14, 12, 10, 8, 6, 4), (4, 4, 4, 4, 4, 30)),
    "POLY": _save_progression((12, 11, 10, 9, 8, 7), (4, 4, 4, 4, 4, 30)),
    "BREATH": _save_progression((16, 15, 14, 13, 12, 11), (4, 4, 4, 4, 4, 30)),
    "SPELL": _save_progression((15, 13, 11, 9, 7, 5), (4, 4, 4, 4, 4, 30)),
}
LORE_RATES = {"MAGE": 3, "FIGHTER": 1, "CLERIC": 1, "THIEF": 3, "BARD": 10}
CLERIC_THAC0 = tuple(max(6, 20 - (2 * ((level - 1) // 3))) for level in range(1, 51))
THIEF_THAC0 = tuple(max(10, 20 - ((level - 1) // 2)) for level in range(1, 51))

SKILL_OFFSETS = {
    "hide": 0x45,
    "detect_illusion": 0x64,
    "set_traps": 0x65,
    "open_locks": 0x67,
    "move_silently": 0x68,
    "find_traps": 0x69,
    "pick_pockets": 0x6A,
}
MUTABLE_OFFSETS = {
    0x52,
    *range(0x54, 0x59),
    0x66,
    0x234,
    0x235,
    0x236,
    0x273,
    *SKILL_OFFSETS.values(),
}

ONE_EMPTY_STRING_TLK = (
    struct.pack("<8sHII", b"TLK V1  ", 0, 1, 0x2C)
    + struct.pack("<H8siiII", 0, b"\0" * 8, 0, 0, 0, 0)
)


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def priest_meminfo(data: bytes) -> dict[int, tuple[int, int, int, int]]:
    info_offset = u32(data, 0x2A8)
    info_count = u32(data, 0x2AC)
    rows: dict[int, tuple[int, int, int, int]] = {}
    for index in range(info_count):
        entry = info_offset + (index * 16)
        spell_level, base, effective, spell_type, first, count = struct.unpack_from(
            "<HHHHII", data, entry
        )
        if spell_type == 0:
            rows[spell_level + 1] = (base, effective, first, count)
    return rows


def memorized_flags(data: bytes, first: int, count: int) -> tuple[int, ...]:
    memorized_offset = u32(data, 0x2B0)
    return tuple(
        u32(data, memorized_offset + ((first + index) * 12) + 8)
        for index in range(count)
    )


def find_weidu() -> str | None:
    configured = os.environ.get("WEIDU_BIN")
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("weidu") or shutil.which("weidu.exe")


def file_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix().upper(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def tp2_component_block(source: str, component: int) -> str:
    start = re.search(rf"(?m)^[ \t]*BEGIN\s+@{component}\b", source)
    if start is None:
        raise AssertionError(f"component {component} is absent from the public TP2")
    following = source[start.end() :]
    next_component = re.search(r"(?m)^[ \t]*BEGIN\s+@\d+\b", following)
    end = len(source) if next_component is None else start.end() + next_component.start()
    return source[start.start() : end]


def level_for_xp(xp: int, thresholds: dict[int, int]) -> int:
    legal = [level for level, minimum in thresholds.items() if minimum <= xp]
    if not legal:
        raise AssertionError(f"no level supports {xp} XP")
    return max(legal)


def class_ids_text() -> str:
    return (
        "IDS V1.0\n"
        "0 NONE\n"
        f"{CLERIC_CLASS} CLERIC\n"
        f"{CLERIC_THIEF_CLASS} CLERIC_THIEF\n"
    )


def kit_ids_text() -> str:
    return (
        "IDS V1.0\n"
        "0x4000 TRUECLASS\n"
        f"0x{SYNTHETIC_WIZARD_SLAYER_ID:04X} WIZARDSLAYER\n"
        "0x40B1 BERSERKER\n"
    )


def xplevel_text(
    *,
    cleric: dict[int, int] | None = None,
    thief: dict[int, int] | None = None,
) -> str:
    cleric = CLERIC_XP if cleric is None else cleric
    thief = THIEF_XP if thief is None else thief
    levels = range(1, 52)

    def cells(thresholds: dict[int, int]) -> str:
        # Production XPLEVEL.2DA has one class per row, level columns 1..51,
        # and -1 after the final supported threshold.
        return " ".join(str(thresholds.get(level, -1)) for level in levels)

    filler = {level: max(0, level - 1) * 2_000 for level in range(1, 51)}
    rows = [
        "2DA V1.0",
        "-1",
        "           " + " ".join(str(level) for level in levels),
        f"FIGHTER    {cells(filler)}",
        f"MAGE       {cells(filler)}",
        f"CLERIC     {cells(cleric)}",
        f"THIEF      {cells(thief)}",
    ]
    return "\n".join(rows) + "\n"


def mxsplprs_text(*, rows: dict[int, tuple[int, ...]] | None = None) -> str:
    rows = PRIEST_SLOTS if rows is None else rows
    lines = [
        "2DA V1.0",
        "0",
        "        1 2 3 4 5 6 7",
    ]
    for level in range(1, 51):
        slots = rows[level]
        if len(slots) != 7:
            raise ValueError("priest slot rows must contain seven spell levels")
        lines.append(f"{level}       " + " ".join(str(slot) for slot in slots))
    return "\n".join(lines) + "\n"


def save_table_text(rows: dict[str, tuple[int, ...]]) -> str:
    lines = [
        "2DA V1.0",
        "0",
        "        " + " ".join(str(level) for level in range(1, 51)),
    ]
    for save_type in ("DEATH", "WANDS", "POLY", "BREATH", "SPELL"):
        values = rows[save_type]
        if len(values) != 50:
            raise ValueError("save rows must contain fifty levels")
        lines.append(f"{save_type} " + " ".join(str(value) for value in values))
    return "\n".join(lines) + "\n"


def saveprs_text() -> str:
    return save_table_text(PRIEST_SAVES)


def saverog_text() -> str:
    return save_table_text(ROGUE_SAVES)


def cleric_thief_saves(cleric_level: int, thief_level: int) -> tuple[int, ...]:
    return tuple(
        min(
            PRIEST_SAVES[save_type][cleric_level - 1],
            ROGUE_SAVES[save_type][thief_level - 1],
        )
        for save_type in ("DEATH", "WANDS", "POLY", "BREATH", "SPELL")
    )


def lore_text(*, rates: dict[str, int] | None = None) -> str:
    rates = LORE_RATES if rates is None else rates
    lines = ["2DA V1.0", "1", "        RATE"]
    lines.extend(f"{name} {rate}" for name, rate in rates.items())
    return "\n".join(lines) + "\n"


def thac0_text(
    *,
    cleric: tuple[int, ...] | None = None,
    thief: tuple[int, ...] | None = None,
) -> str:
    cleric = CLERIC_THAC0 if cleric is None else cleric
    thief = THIEF_THAC0 if thief is None else thief
    if len(cleric) != 50 or len(thief) != 50:
        raise ValueError("THAC0 rows must contain fifty levels")
    fighter = tuple(max(0, 21 - level) for level in range(1, 51))
    lines = [
        "2DA V1.0",
        "0",
        "        " + " ".join(str(level) for level in range(1, 51)),
        "FIGHTER " + " ".join(str(value) for value in fighter),
        "CLERIC " + " ".join(str(value) for value in cleric),
        "THIEF " + " ".join(str(value) for value in thief),
    ]
    return "\n".join(lines) + "\n"


def cleric_thief_thac0(cleric_level: int, thief_level: int) -> int:
    return min(CLERIC_THAC0[cleric_level - 1], THIEF_THAC0[thief_level - 1])


def make_viconia_cre(
    xp: int,
    *,
    dv: str = "VICONIA",
    class_id: int = CLERIC_CLASS,
    kit: int = TRUECLASS_KIT,
    seed: int = 17,
) -> bytes:
    """Build a synthetic, structurally safe CRE V1.0 with sentinel payload."""
    size = 0x334
    data = bytearray(((index * 73 + seed) & 0xFF) for index in range(size))
    data[0:8] = b"CRE V1.0"
    data[0x33] = 0
    struct.pack_into("<I", data, 0x18, xp)

    for offset in SKILL_OFFSETS.values():
        data[offset] = 0xC7
    data[0x234:0x237] = bytes((0x31, 0x32, 0x33))
    struct.pack_into("<I", data, 0x244, kit)
    data[0x273] = class_id
    data[0x280:0x2A0] = b"\0" * 32
    encoded_dv = dv.encode("ascii")
    if len(encoded_dv) > 31:
        raise ValueError("synthetic DV exceeds CRE field")
    data[0x280 : 0x280 + len(encoded_dv)] = encoded_dv

    # Empty variable-length tables and a real 40-word item-slot table make the
    # fixture safe for both raw COPY and CRE-aware WeiDU helpers.
    variable_data_offset = 0x324
    for offset in (0x2A0, 0x2A8, 0x2B0, 0x2BC, 0x2C4):
        struct.pack_into("<I", data, offset, variable_data_offset)
    for offset in (0x2A4, 0x2AC, 0x2B4, 0x2C0):
        struct.pack_into("<I", data, offset, 0)
    struct.pack_into("<I", data, 0x2B8, 0x2D4)
    struct.pack_into("<I", data, 0x2C8, 0)
    data[0x2D4:0x324] = b"\xFF" * 0x50
    return bytes(data)


def make_viconia_spellbook_cre(
    xp: int,
    *,
    base_slots: tuple[int, ...],
    effective_slots: tuple[int, ...] | None = None,
    memorized_flags: tuple[tuple[int, ...], ...] | None = None,
    seed: int = 211,
) -> bytes:
    """Build a tiled CRE with seven priest and nine wizard meminfo rows."""
    if len(base_slots) != 7:
        raise ValueError("base_slots must contain seven spell levels")
    if effective_slots is None:
        effective_slots = base_slots
    if len(effective_slots) != 7:
        raise ValueError("effective_slots must contain seven spell levels")
    if memorized_flags is None:
        memorized_flags = tuple(
            tuple(1 for _ in range(slot_count)) for slot_count in effective_slots
        )
    if len(memorized_flags) != 7:
        raise ValueError("memorized_flags must contain seven spell levels")

    header = bytearray(make_viconia_cre(xp, seed=seed)[:0x2D4])
    meminfo = bytearray()
    memorized = bytearray()
    memorized_index = 0
    for spell_level, (base, effective, flags) in enumerate(
        zip(base_slots, effective_slots, memorized_flags)
    ):
        meminfo.extend(
            struct.pack(
                "<HHHHII",
                spell_level,
                base,
                effective,
                0,
                memorized_index,
                len(flags),
            )
        )
        for entry_index, flag in enumerate(flags):
            resref = f"P{spell_level + 1}{entry_index:06d}".encode("ascii")
            memorized.extend(struct.pack("<8sI", resref, flag))
        memorized_index += len(flags)

    # A normal EE CRE also carries one wizard row per spell level. They are
    # unrelated sentinels here and must remain byte-identical.
    for spell_level in range(9):
        meminfo.extend(struct.pack("<HHHHII", spell_level, 0, 0, 1, memorized_index, 0))

    meminfo_offset = 0x2D4
    memorized_offset = meminfo_offset + len(meminfo)
    slots_offset = memorized_offset + len(memorized)
    end_offset = slots_offset + 0x50
    data = header + meminfo + memorized + (b"\xFF" * 0x50)

    struct.pack_into("<I", data, 0x2A0, meminfo_offset)
    struct.pack_into("<I", data, 0x2A4, 0)
    struct.pack_into("<I", data, 0x2A8, meminfo_offset)
    struct.pack_into("<I", data, 0x2AC, 16)
    struct.pack_into("<I", data, 0x2B0, memorized_offset)
    struct.pack_into("<I", data, 0x2B4, memorized_index)
    struct.pack_into("<I", data, 0x2B8, slots_offset)
    struct.pack_into("<I", data, 0x2BC, end_offset)
    struct.pack_into("<I", data, 0x2C0, 0)
    struct.pack_into("<I", data, 0x2C4, end_offset)
    struct.pack_into("<I", data, 0x2C8, 0)
    return bytes(data)


def make_sharteel_cre(
    *,
    dv: str = "sharteel",
    class_id: int = FIGHTER_CLASS,
    kit: int = TRUECLASS_KIT,
    xp: int = 32_123,
    seed: int = 131,
) -> bytes:
    """Build a synthetic Shar-Teel fixture with distinct sentinel payload."""
    return make_viconia_cre(
        xp,
        dv=dv,
        class_id=class_id,
        kit=kit,
        seed=seed,
    )


def write_marker_key_and_bif(game_root: Path) -> Path:
    """Create the smallest KEY/BIFF pair needed for BG2EE game detection."""
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
            "<4s4sIIII",
            b"KEY ",
            b"V1  ",
            1,
            1,
            bif_table_offset,
            resource_table_offset,
        )
    )
    key.extend(
        struct.pack(
            "<IIHH",
            bif_path.stat().st_size,
            names_offset,
            len(encoded_name),
            0,
        )
    )
    key.extend(struct.pack("<8sHI", b"OH6000\0\0", 1010, 0))
    key.extend(encoded_name)
    (game_root / "chitin.key").write_bytes(key)
    return bif_path


class SyntheticGame:
    def __init__(
        self,
        root: Path,
        *,
        table_text: str | None = None,
        priest_slots_text: str | None = None,
        priest_saves_text: str | None = None,
        rogue_saves_text: str | None = None,
        lore_rates_text: str | None = None,
        thac0_table_text: str | None = None,
    ) -> None:
        self.root = root
        self.root.mkdir(parents=True)
        (self.root / "WeiDU.log").write_text("", encoding="ascii")
        self.override = self.root / "override"
        self.override.mkdir()
        self.bif = write_marker_key_and_bif(self.root)
        self.lang_tlk = self.root / "lang/en_US/dialog.tlk"
        self.lang_tlk.parent.mkdir(parents=True)
        self.lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.root_tlk = self.root / "dialog.tlk"
        self.root_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        (self.override / "CLASS.IDS").write_text(class_ids_text(), encoding="ascii")
        (self.override / "XPLEVEL.2DA").write_text(
            xplevel_text() if table_text is None else table_text,
            encoding="ascii",
        )
        (self.override / "MXSPLPRS.2DA").write_text(
            mxsplprs_text() if priest_slots_text is None else priest_slots_text,
            encoding="ascii",
        )
        (self.override / "SAVEPRS.2DA").write_text(
            saveprs_text() if priest_saves_text is None else priest_saves_text,
            encoding="ascii",
        )
        (self.override / "SAVEROG.2DA").write_text(
            saverog_text() if rogue_saves_text is None else rogue_saves_text,
            encoding="ascii",
        )
        (self.override / "LORE.2DA").write_text(
            lore_text() if lore_rates_text is None else lore_rates_text,
            encoding="ascii",
        )
        (self.override / "THAC0.2DA").write_text(
            thac0_text() if thac0_table_text is None else thac0_table_text,
            encoding="ascii",
        )

    def stable_hashes(self) -> dict[Path, str]:
        return {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                self.root / "chitin.key",
                self.bif,
                self.lang_tlk,
                self.root_tlk,
            )
        }


class SyntheticViconiaPublicGame(SyntheticGame):
    def __init__(self, root: Path, *, missing: str | None = None) -> None:
        super().__init__(root)
        shutil.copy2(TP2, self.root / TP2.name)
        shutil.copytree(ROOT / "chriz-bg-modpack", self.root / "chriz-bg-modpack")
        dv_spellings = ("VICONIA", "viconia", "ViCoNiA")
        for index, (resref, (xp, _, _)) in enumerate(VICONIA_VARIANTS.items()):
            if resref == missing:
                continue
            (self.override / f"{resref}.CRE").write_bytes(
                make_viconia_cre(
                    xp,
                    dv=dv_spellings[index % len(dv_spellings)],
                    seed=17 + index,
                )
            )
        self.initial_override = file_tree(self.override)
        self.initial_stable_hashes = self.stable_hashes()

    def run(self, weidu: str, operation: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                weidu,
                TP2.name,
                "--no-auto-tp2",
                "--game",
                str(self.root),
                operation,
                str(VICONIA_COMPONENT),
                "--language",
                "0",
                "--use-lang",
                "en_US",
                "--no-exit-pause",
                "--quick-log",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )

    def transcript(self, result: subprocess.CompletedProcess[str]) -> str:
        return result.stdout + result.stderr

    def active_log(self) -> str:
        log = self.root / "WeiDU.log"
        if not log.exists():
            return ""
        return "\n".join(
            line
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines()
            if not line.lstrip().startswith("//")
        )

    def assert_stable_inputs(self, testcase: unittest.TestCase) -> None:
        testcase.assertEqual(self.initial_stable_hashes, self.stable_hashes())


class SyntheticSharTeelGame(SyntheticGame):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        (self.override / "KIT.IDS").write_text(kit_ids_text(), encoding="ascii")


class SyntheticSharTeelPublicGame(SyntheticSharTeelGame):
    def __init__(self, root: Path, *, missing: str | None = None) -> None:
        super().__init__(root)
        shutil.copy2(TP2, self.root / TP2.name)
        shutil.copytree(ROOT / "chriz-bg-modpack", self.root / "chriz-bg-modpack")

        dv_spellings = ("sharteel", "SHARTEEL", "ShArTeEl")
        for index, resref in enumerate(SHARTEEL_VARIANTS):
            if resref == missing:
                continue
            (self.override / f"{resref}.CRE").write_bytes(
                make_sharteel_cre(
                    dv=dv_spellings[index],
                    xp=32_123 + (index * 41_111),
                    seed=131 + index,
                )
            )

        # SHARTD is the nonjoinable duel creature. It deliberately has no
        # Shar-Teel DV and acts as a byte-exact exclusion sentinel.
        (self.override / f"{SHARTEEL_DUEL_RESOURCE}.CRE").write_bytes(
            make_sharteel_cre(dv="", xp=777, seed=191)
        )
        self.initial_override = file_tree(self.override)
        self.initial_stable_hashes = self.stable_hashes()

    def run(self, weidu: str, operation: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                weidu,
                TP2.name,
                "--no-auto-tp2",
                "--game",
                str(self.root),
                operation,
                str(SHARTEEL_COMPONENT),
                "--language",
                "0",
                "--use-lang",
                "en_US",
                "--no-exit-pause",
                "--quick-log",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )

    def transcript(self, result: subprocess.CompletedProcess[str]) -> str:
        return result.stdout + result.stderr

    def active_log(self) -> str:
        log = self.root / "WeiDU.log"
        if not log.exists():
            return ""
        return "\n".join(
            line
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines()
            if not line.lstrip().startswith("//")
        )

    def assert_stable_inputs(self, testcase: unittest.TestCase) -> None:
        testcase.assertEqual(self.initial_stable_hashes, self.stable_hashes())


class ViconiaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.weidu = find_weidu()

    def run_harness(
        self,
        source: bytes,
        *,
        source_name: str = "VICONI.CRE",
        table_text: str | None = None,
        priest_slots_text: str | None = None,
        priest_saves_text: str | None = None,
        rogue_saves_text: str | None = None,
        lore_rates_text: str | None = None,
        thac0_table_text: str | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], bytes | None]:
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        with tempfile.TemporaryDirectory(prefix="cbm-viconia-") as raw_temp:
            run_dir = Path(raw_temp)
            game = SyntheticGame(
                run_dir / "game",
                table_text=table_text,
                priest_slots_text=priest_slots_text,
                priest_saves_text=priest_saves_text,
                rogue_saves_text=rogue_saves_text,
                lore_rates_text=lore_rates_text,
                thac0_table_text=thac0_table_text,
            )
            initial_context = file_tree(game.override)
            (run_dir / "WeiDU.log").write_text("", encoding="ascii")
            harness = run_dir / VICONIA_HARNESS.name
            source_path = run_dir / source_name
            output_path = run_dir / "output.cre"
            shutil.copy2(VICONIA_HARNESS, harness)
            source_path.write_bytes(source)
            result = subprocess.run(
                [
                    self.weidu,
                    harness.name,
                    "--no-auto-tp2",
                    "--game",
                    str(game.root),
                    "--force-install-list",
                    "1",
                    "--args",
                    VICONIA_TPA.as_posix(),
                    "--args",
                    source_path.as_posix(),
                    "--args",
                    output_path.as_posix(),
                    "--language",
                    "0",
                    "--use-lang",
                    "en_US",
                    "--no-exit-pause",
                    "--quick-log",
                ],
                cwd=run_dir,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(
                initial_context,
                file_tree(game.override),
                "context loading must not publish or rewrite installed 2DA/IDS inputs",
            )
            output = output_path.read_bytes() if output_path.is_file() else None
            return result, output

    @staticmethod
    def transcript(result: subprocess.CompletedProcess[str]) -> str:
        return result.stdout + result.stderr

    def transform(
        self,
        source: bytes,
        *,
        source_name: str = "VICONI.CRE",
        table_text: str | None = None,
        priest_slots_text: str | None = None,
        priest_saves_text: str | None = None,
        rogue_saves_text: str | None = None,
        lore_rates_text: str | None = None,
        thac0_table_text: str | None = None,
    ) -> bytes:
        result, output = self.run_harness(
            source,
            source_name=source_name,
            table_text=table_text,
            priest_slots_text=priest_slots_text,
            priest_saves_text=priest_saves_text,
            rogue_saves_text=rogue_saves_text,
            lore_rates_text=lore_rates_text,
            thac0_table_text=thac0_table_text,
        )
        transcript = self.transcript(result)
        self.assertEqual(0, result.returncode, transcript)
        self.assertIsNotNone(output, transcript)
        return output

    def assert_conversion(
        self,
        source: bytes,
        transformed: bytes,
        *,
        cleric_level: int,
        thief_level: int,
        extra_mutable_offsets: set[int] | None = None,
    ) -> None:
        self.assertEqual(len(source), len(transformed))
        self.assertEqual(b"CRE V1.0", transformed[:8])
        self.assertEqual(CLERIC_THIEF_CLASS, transformed[0x273])
        self.assertEqual((cleric_level, thief_level, 0), tuple(transformed[0x234:0x237]))
        self.assertEqual(u32(source, 0x18), u32(transformed, 0x18))
        self.assertEqual(TRUECLASS_KIT, u32(transformed, 0x244))
        self.assertEqual(
            cleric_thief_thac0(cleric_level, thief_level),
            transformed[0x52],
            "the final split levels require table-correct Cleric/Thief THAC0",
        )

        hide, move, find, locks = THIEF_SKILLS[thief_level]
        self.assertEqual(hide, transformed[SKILL_OFFSETS["hide"]])
        self.assertEqual(move, transformed[SKILL_OFFSETS["move_silently"]])
        self.assertEqual(find, transformed[SKILL_OFFSETS["find_traps"]])
        self.assertEqual(locks, transformed[SKILL_OFFSETS["open_locks"]])
        self.assertEqual(0, transformed[SKILL_OFFSETS["pick_pockets"]])
        self.assertEqual(0, transformed[SKILL_OFFSETS["detect_illusion"]])
        self.assertEqual(0, transformed[SKILL_OFFSETS["set_traps"]])
        self.assertEqual(40 + 25 * (thief_level - 1), hide + move + find + locks)
        self.assertEqual(cleric_level + (3 * thief_level), transformed[0x66])
        self.assertEqual(
            cleric_thief_saves(cleric_level, thief_level),
            tuple(transformed[0x54:0x59]),
        )

        approved_offsets = MUTABLE_OFFSETS | (extra_mutable_offsets or set())
        for offset, (before, after) in enumerate(zip(source, transformed)):
            if offset not in approved_offsets:
                self.assertEqual(
                    before,
                    after,
                    f"unapproved CRE byte changed at 0x{offset:03x}",
                )

    def assert_conversion_with_spellbook(
        self,
        source: bytes,
        transformed: bytes,
        *,
        cleric_level: int,
        thief_level: int,
    ) -> None:
        self.assertEqual(
            tuple(u32(source, offset) for offset in range(0x2A0, 0x2CC, 4)),
            tuple(u32(transformed, offset) for offset in range(0x2A0, 0x2CC, 4)),
            "spellbook/table layout and counts must remain size-preserving",
        )
        approved: set[int] = set()
        info_offset = u32(source, 0x2A8)
        info_count = u32(source, 0x2AC)
        for index in range(info_count):
            entry = info_offset + (index * 16)
            if u16(source, entry + 6) == 0:
                approved.update(range(entry + 2, entry + 6))

        memorized_offset = u32(source, 0x2B0)
        memorized_count = u32(source, 0x2B4)
        self.assertEqual(
            source[memorized_offset : memorized_offset + (memorized_count * 12)],
            transformed[memorized_offset : memorized_offset + (memorized_count * 12)],
            "known memorized records and every active flag must remain unchanged",
        )

        self.assert_conversion(
            source,
            transformed,
            cleric_level=cleric_level,
            thief_level=thief_level,
            extra_mutable_offsets=approved,
        )

    def assert_failed_closed(
        self,
        source: bytes,
        *,
        expected_pattern: str,
        table_text: str | None = None,
    ) -> None:
        result, output = self.run_harness(source, table_text=table_text)
        transcript = self.transcript(result)
        self.assertNotEqual(0, result.returncode, transcript)
        self.assertIsNone(output, transcript)
        self.assertRegex(transcript.lower(), expected_pattern)

    def test_harness_uses_the_installed_context_loader_once(self):
        harness = VICONIA_HARNESS.read_text(encoding="utf-8")
        self.assertEqual(
            1,
            len(re.findall(r"(?im)^\s*LAF\s+cbm_viconia_load_context\b", harness)),
        )
        self.assertIn("RET_ARRAY", harness)
        self.assertEqual(1, harness.count("LPF cbm_viconia_make_cleric_thief END"))
        self.assertIn("INCLUDE ~%argv[0]%~", harness)

    def test_synthetic_xplevel_matches_the_production_table_orientation(self):
        lines = xplevel_text().splitlines()
        self.assertEqual([str(level) for level in range(1, 52)], lines[2].split())
        rows = {tokens[0]: tokens[1:] for line in lines[3:] if (tokens := line.split())}
        self.assertEqual({"FIGHTER", "MAGE", "CLERIC", "THIEF"}, set(rows))
        for cells in rows.values():
            self.assertEqual(51, len(cells))
        self.assertEqual("0", rows["CLERIC"][0])
        self.assertEqual("1500", rows["CLERIC"][1])
        self.assertEqual("0", rows["THIEF"][0])
        self.assertEqual("1250", rows["THIEF"][1])
        for class_name in ("FIGHTER", "MAGE", "CLERIC", "THIEF"):
            self.assertTrue(
                all(
                    int(rows[class_name][index]) < int(rows[class_name][index + 1])
                    for index in range(49)
                )
            )
            self.assertEqual("-1", rows[class_name][50])

    def test_all_ten_eet_variants_use_current_xp_not_filename_levels(self):
        dv_spellings = ("VICONIA", "viconia", "ViCoNiA")
        for index, (resref, (xp, cleric_level, thief_level)) in enumerate(
            VICONIA_VARIANTS.items()
        ):
            with self.subTest(resref=resref, xp=xp):
                half_xp = xp // 2
                self.assertEqual(cleric_level, level_for_xp(half_xp, CLERIC_XP))
                self.assertEqual(thief_level, level_for_xp(half_xp, THIEF_XP))
                source = make_viconia_cre(
                    xp,
                    dv=dv_spellings[index % len(dv_spellings)],
                    seed=31 + index,
                )
                transformed = self.transform(source, source_name=f"{resref}.CRE")
                self.assert_conversion(
                    source,
                    transformed,
                    cleric_level=cleric_level,
                    thief_level=thief_level,
                )

    def test_corrected_thief_skill_policy_covers_every_level_one_through_fifteen(self):
        self.assertEqual(set(range(1, 16)), set(THIEF_SKILLS))
        for thief_level in range(1, 16):
            with self.subTest(thief_level=thief_level):
                budget = 40 + 25 * (thief_level - 1)
                hide, move, find, locks = THIEF_SKILLS[thief_level]
                self.assertEqual((0, 0), (hide, move))
                self.assertEqual(5 * ((budget + 5) // 10), find)
                self.assertEqual(budget - find, locks)
                total_xp = THIEF_XP[thief_level] * 2
                half_xp = total_xp // 2
                cleric_level = level_for_xp(half_xp, CLERIC_XP)
                source = make_viconia_cre(total_xp, dv="vIcOnIa", seed=70 + thief_level)
                transformed = self.transform(source, source_name="VICONI16.CRE")
                self.assert_conversion(
                    source,
                    transformed,
                    cleric_level=cleric_level,
                    thief_level=thief_level,
                )

    def test_recruitment_boost_to_32926_xp_uses_find_traps_and_open_locks_only(self):
        source = make_viconia_cre(32_926, dv="viconia", seed=99)
        transformed = self.transform(source, source_name="VICONI6_.CRE")
        self.assert_conversion(
            source,
            transformed,
            cleric_level=5,
            thief_level=5,
        )
        self.assertEqual(0, transformed[SKILL_OFFSETS["hide"]])
        self.assertEqual(0, transformed[SKILL_OFFSETS["move_silently"]])
        self.assertEqual(70, transformed[SKILL_OFFSETS["find_traps"]])
        self.assertEqual(70, transformed[SKILL_OFFSETS["open_locks"]])

    def test_recruitment_boost_reconciles_priest_slots_to_cleric_level_five(self):
        # This mirrors the save under repair: the single-class Cleric-6 source
        # has 3/3/2 slots, but the approved 32,926-XP C/T split is Cleric 5 and
        # therefore must use the installed 3/3/1 row. The one active level-3
        # spell remains active, and no known/memorized spell entry is removed.
        source = make_viconia_spellbook_cre(
            32_926,
            base_slots=(3, 3, 2, 0, 0, 0, 0),
            memorized_flags=(
                (1, 1, 1, 0, 0),
                (1, 1, 1, 0, 0),
                (0, 0, 1),
                (),
                (),
                (),
                (),
            ),
        )
        transformed = self.transform(source, source_name="VICONI6_.CRE")
        self.assert_conversion_with_spellbook(
            source,
            transformed,
            cleric_level=5,
            thief_level=5,
        )
        rows = priest_meminfo(transformed)
        self.assertEqual((3, 3, 1, 0, 0, 0, 0), tuple(rows[level][0] for level in range(1, 8)))
        self.assertEqual((3, 3, 1, 0, 0, 0, 0), tuple(rows[level][1] for level in range(1, 8)))
        first, count = rows[3][2:]
        self.assertEqual((0, 0, 1), memorized_flags(transformed, first, count))

    def test_priest_slot_bonus_delta_and_all_active_flags_are_preserved(self):
        source = make_viconia_spellbook_cre(
            1_603,
            base_slots=(2, 0, 0, 0, 0, 0, 0),
            effective_slots=(4, 0, 0, 0, 0, 0, 0),
            memorized_flags=((1, 1, 1, 1), (), (), (), (), (), ()),
        )
        transformed = self.transform(source)
        self.assert_conversion_with_spellbook(
            source,
            transformed,
            cleric_level=1,
            thief_level=1,
        )
        base, effective, first, count = priest_meminfo(transformed)[1]
        self.assertEqual((1, 3), (base, effective))
        self.assertEqual((1, 1, 1, 1), memorized_flags(transformed, first, count))

    def test_priest_slot_progression_comes_from_installed_mxsplprs(self):
        altered = dict(PRIEST_SLOTS)
        altered[5] = (4, 2, 1, 0, 0, 0, 0)
        source = make_viconia_spellbook_cre(
            32_926,
            base_slots=(3, 3, 2, 0, 0, 0, 0),
            memorized_flags=((1, 1, 1), (1, 1), (1,), (), (), (), ()),
        )
        transformed = self.transform(
            source,
            priest_slots_text=mxsplprs_text(rows=altered),
        )
        rows = priest_meminfo(transformed)
        self.assertEqual((4, 2, 1, 0, 0, 0, 0), tuple(rows[level][0] for level in range(1, 8)))

    def test_saving_throws_come_from_both_installed_class_tables(self):
        altered_rogue = {name: list(values) for name, values in ROGUE_SAVES.items()}
        altered_rogue["WANDS"][4] = 11
        altered_text = save_table_text(
            {name: tuple(values) for name, values in altered_rogue.items()}
        )
        source = make_viconia_cre(32_926, dv="VICONIA", seed=227)
        transformed = self.transform(source, rogue_saves_text=altered_text)
        self.assertEqual((9, 11, 11, 15, 13), tuple(transformed[0x54:0x59]))

    def test_thac0_comes_from_both_installed_class_progressions(self):
        cleric = list(CLERIC_THAC0)
        thief = list(THIEF_THAC0)
        cleric[8] = 17
        thief[10] = 12
        source = make_viconia_cre(800_000, dv="VICONIA", seed=144)
        transformed = self.transform(
            source,
            thac0_table_text=thac0_text(cleric=tuple(cleric), thief=tuple(thief)),
        )
        self.assertEqual(12, transformed[0x52])

    def test_lore_uses_both_installed_class_rates_cumulatively(self):
        altered_rates = dict(LORE_RATES)
        altered_rates["CLERIC"] = 2
        altered_rates["THIEF"] = 4
        source = make_viconia_cre(32_926, dv="VICONIA", seed=228)
        transformed = self.transform(
            source,
            lore_rates_text=lore_text(rates=altered_rates),
        )
        self.assertEqual(30, transformed[0x66])

    def test_malformed_save_table_fails_before_output(self):
        malformed = "\n".join(
            line
            for line in saveprs_text().splitlines()
            if not line.startswith("SPELL ")
        )
        source = make_viconia_cre(32_926, dv="VICONIA", seed=229)
        result, output = self.run_harness(source, priest_saves_text=malformed)
        transcript = self.transcript(result)
        self.assertNotEqual(0, result.returncode, transcript)
        self.assertIsNone(output, transcript)
        self.assertRegex(transcript.lower(), r"save|throw")

    def test_malformed_thac0_table_fails_before_output(self):
        malformed = "\n".join(
            line
            for line in thac0_text().splitlines()
            if not line.startswith("THIEF ")
        )
        source = make_viconia_cre(32_926, dv="VICONIA", seed=230)
        result, output = self.run_harness(source, thac0_table_text=malformed)
        transcript = self.transcript(result)
        self.assertNotEqual(0, result.returncode, transcript)
        self.assertIsNone(output, transcript)
        self.assertRegex(transcript.lower(), r"thac0")

    def test_malformed_priest_meminfo_fails_before_output(self):
        source = bytearray(
            make_viconia_spellbook_cre(
                32_926,
                base_slots=(3, 3, 2, 0, 0, 0, 0),
            )
        )
        info_offset = u32(source, 0x2A8)
        struct.pack_into("<H", source, info_offset + 6, 9)
        result, output = self.run_harness(bytes(source))
        transcript = self.transcript(result)
        self.assertNotEqual(0, result.returncode, transcript)
        self.assertIsNone(output, transcript)
        self.assertRegex(transcript.lower(), r"memorization|priest|spell")

    def test_same_resref_changes_levels_only_when_xp_changes(self):
        low_source = make_viconia_cre(VICONIA_VARIANTS["VICONI4"][0], seed=101)
        high_source = make_viconia_cre(VICONIA_VARIANTS["VICONI16"][0], seed=102)
        low = self.transform(low_source, source_name="VICONI8.CRE")
        high = self.transform(high_source, source_name="VICONI8.CRE")
        self.assertEqual((3, 3), tuple(low[0x234:0x236]))
        self.assertEqual((13, 15), tuple(high[0x234:0x236]))

    def test_valid_altered_xplevel_thresholds_change_both_derived_levels(self):
        altered_cleric = dict(CLERIC_XP)
        altered_cleric[9] = 190_000
        altered_thief = dict(THIEF_XP)
        altered_thief[10] = 210_000
        self.assertTrue(
            all(
                altered_cleric[level] < altered_cleric[level + 1]
                for level in range(1, 50)
            )
        )
        self.assertTrue(
            all(
                altered_thief[level] < altered_thief[level + 1]
                for level in range(1, 50)
            )
        )
        source = make_viconia_cre(400_000)
        transformed = self.transform(
            source,
            source_name="VICONI9.CRE",
            table_text=xplevel_text(
                cleric=altered_cleric,
                thief=altered_thief,
            ),
        )
        # The stock table yields Cleric 8 / Thief 10 at 200,000 split XP.
        # This valid installed table lowers Cleric 9's threshold but raises
        # Thief 10's, so hardcoding either stock progression is observable.
        self.assert_conversion(
            source,
            transformed,
            cleric_level=9,
            thief_level=9,
        )

    def test_odd_total_xp_is_split_with_floor_division(self):
        source = make_viconia_cre((THIEF_XP[8] * 2) - 1)
        transformed = self.transform(source, source_name="VICONI8.CRE")
        # floor(139999 / 2) = 69999, one point below Thief 8. Rounding up
        # would incorrectly produce Thief 8 and the level-8 skill allocation.
        self.assert_conversion(
            source,
            transformed,
            cleric_level=7,
            thief_level=7,
        )

    def test_patch_is_byte_idempotent(self):
        source = make_viconia_cre(400_000, dv="viCONia")
        first = self.transform(source)
        second = self.transform(first)
        self.assertEqual(first, second)

    def test_identity_class_and_kit_guards_fail_closed(self):
        bad_signature = bytearray(make_viconia_cre(400_000))
        bad_signature[0:8] = b"BAD V1.0"
        cases = (
            (bytes(bad_signature), r"signature|cre v1\.0"),
            (make_viconia_cre(400_000, dv="NOTVICONIA"), r"death.?variable|\bdv\b"),
            (make_viconia_cre(400_000, class_id=2), r"\bclass\b"),
            (make_viconia_cre(400_000, kit=0x40010000), r"\bkit\b"),
        )
        for source, pattern in cases:
            with self.subTest(expected=pattern):
                self.assert_failed_closed(source, expected_pattern=pattern)

    def test_malformed_xplevel_tables_fail_before_cre_publication(self):
        # Corrupt the Cleric cell itself; unrelated filler columns may legally
        # contain values the narrow loader never needs to inspect.
        non_numeric = xplevel_text().replace(
            "CLERIC     0 1500 3000 6000 13000",
            "CLERIC     0 1500 3000 6000 BROKEN",
            1,
        )
        descending_thief = dict(THIEF_XP)
        descending_thief[8] = descending_thief[7] - 1
        missing_level = dict(THIEF_XP)
        del missing_level[11]
        malformed_tables = (
            non_numeric,
            xplevel_text(thief=descending_thief),
            xplevel_text(thief=missing_level),
        )
        source = make_viconia_cre(400_000)
        for index, table in enumerate(malformed_tables):
            with self.subTest(case=index):
                self.assert_failed_closed(
                    source,
                    expected_pattern=r"xplevel\.2da|xp.?table",
                    table_text=table,
                )

    def test_derived_thief_level_above_supported_table_fails_closed(self):
        source = make_viconia_cre(THIEF_XP[16] * 2)
        result, output = self.run_harness(source)
        transcript = self.transcript(result)
        self.assertNotEqual(0, result.returncode, transcript)
        self.assertIsNone(output, transcript)
        self.assertRegex(transcript.lower(), r"unsupported|outside|level.+(?:15|16)")

    def test_public_component_installs_all_variants_and_uninstalls_byte_exactly(self):
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        with tempfile.TemporaryDirectory(prefix="cbm-viconia-public-") as raw_temp:
            game = SyntheticViconiaPublicGame(Path(raw_temp) / "game")
            install = game.run(self.weidu, "--force-install-list")
            transcript = game.transcript(install)
            self.assertEqual(0, install.returncode, transcript)
            self.assertIn("SUCCESSFULLY INSTALLED", transcript)
            self.assertRegex(game.active_log(), r"(?m)#0\s+#192\b")
            game.assert_stable_inputs(self)
            for context_resource in (
                "CLASS.IDS",
                "XPLEVEL.2DA",
                "MXSPLPRS.2DA",
                "SAVEPRS.2DA",
                "SAVEROG.2DA",
                "LORE.2DA",
                "THAC0.2DA",
            ):
                self.assertEqual(
                    game.initial_override[context_resource],
                    (game.override / context_resource).read_bytes(),
                )

            for resref, (xp, cleric_level, thief_level) in VICONIA_VARIANTS.items():
                source = game.initial_override[f"{resref}.CRE"]
                transformed = (game.override / f"{resref}.CRE").read_bytes()
                self.assertEqual(xp, u32(transformed, 0x18))
                self.assert_conversion(
                    source,
                    transformed,
                    cleric_level=cleric_level,
                    thief_level=thief_level,
                )

            uninstall = game.run(self.weidu, "--force-uninstall-list")
            self.assertEqual(0, uninstall.returncode, game.transcript(uninstall))
            self.assertNotRegex(game.active_log(), r"(?m)#0\s+#192\b")
            self.assertEqual(game.initial_override, file_tree(game.override))
            game.assert_stable_inputs(self)

    def test_public_component_requires_every_declared_variant_before_writes(self):
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        with tempfile.TemporaryDirectory(prefix="cbm-viconia-missing-") as raw_temp:
            game = SyntheticViconiaPublicGame(
                Path(raw_temp) / "game",
                missing="VICONI6_",
            )
            result = game.run(self.weidu, "--force-install-list")
            transcript = game.transcript(result)
            self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
            self.assertIn("VICONI6_.CRE", transcript)
            self.assertNotRegex(game.active_log(), r"(?m)#0\s+#192\b")
            self.assertEqual(game.initial_override, file_tree(game.override))
            game.assert_stable_inputs(self)

    def test_public_component_metadata_is_explicit_and_narrow(self):
        self.assertTrue(
            VICONIA_TPA.is_file(),
            f"production library is not implemented yet: {VICONIA_TPA}",
        )
        tp2 = TP2.read_text(encoding="utf-8")
        self.assertRegex(
            tp2,
            r"(?im)^[ \t]*BEGIN\s+@192\s+DESIGNATED\s+192\b",
        )
        self.assertIn("LABEL ~cbm_viconia_cleric_thief~", tp2)
        self.assertIn(
            "INCLUDE ~chriz-bg-modpack/lib/cbm_viconia_cleric_thief.tpa~",
            tp2,
        )
        component = tp2_component_block(tp2, VICONIA_COMPONENT)
        for resref in VICONIA_VARIANTS:
            self.assertIn(f"FILE_EXISTS_IN_GAME ~{resref}.CRE~", component)
            self.assertRegex(component, rf"(?m)\b{resref}\b")
        self.assertNotIn("COPY_EXISTING_REGEXP", component)

        library = VICONIA_TPA.read_text(encoding="utf-8")
        self.assertIn("DEFINE_ACTION_FUNCTION cbm_viconia_load_context", library)
        self.assertIn("DEFINE_PATCH_FUNCTION cbm_viconia_make_cleric_thief", library)

    def test_public_component_loads_context_once_before_the_variant_loop(self):
        tp2 = TP2.read_text(encoding="utf-8")
        component = tp2_component_block(tp2, VICONIA_COMPONENT)
        loader_calls = list(
            re.finditer(
                r"(?im)^\s*LAF\s+cbm_viconia_load_context\b",
                component,
            )
        )
        self.assertEqual(1, len(loader_calls))
        loader_position = loader_calls[0].start()
        patch_calls = list(
            re.finditer(
                r"(?im)^\s*LPF\s+cbm_viconia_make_cleric_thief\b",
                component,
            )
        )
        self.assertGreaterEqual(len(patch_calls), 1)
        self.assertTrue(all(loader_position < call.start() for call in patch_calls))


class SharTeelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.weidu = find_weidu()

    def run_harness(
        self,
        source: bytes,
        *,
        source_name: str = "SHARTE.CRE",
    ) -> tuple[subprocess.CompletedProcess[str], bytes | None]:
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        with tempfile.TemporaryDirectory(prefix="cbm-sharteel-") as raw_temp:
            run_dir = Path(raw_temp)
            game = SyntheticSharTeelGame(run_dir / "game")
            initial_context = file_tree(game.override)
            (run_dir / "WeiDU.log").write_text("", encoding="ascii")
            harness = run_dir / SHARTEEL_HARNESS.name
            source_path = run_dir / source_name
            output_path = run_dir / "output.cre"
            shutil.copy2(SHARTEEL_HARNESS, harness)
            source_path.write_bytes(source)
            result = subprocess.run(
                [
                    self.weidu,
                    harness.name,
                    "--no-auto-tp2",
                    "--game",
                    str(game.root),
                    "--force-install-list",
                    "1",
                    "--args",
                    SHARTEEL_TPA.as_posix(),
                    "--args",
                    source_path.as_posix(),
                    "--args",
                    output_path.as_posix(),
                    "--language",
                    "0",
                    "--use-lang",
                    "en_US",
                    "--no-exit-pause",
                    "--quick-log",
                ],
                cwd=run_dir,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(
                initial_context,
                file_tree(game.override),
                "symbolic kit resolution must not publish or rewrite KIT.IDS",
            )
            output = output_path.read_bytes() if output_path.is_file() else None
            return result, output

    @staticmethod
    def transcript(result: subprocess.CompletedProcess[str]) -> str:
        return result.stdout + result.stderr

    def transform(self, source: bytes, *, source_name: str = "SHARTE.CRE") -> bytes:
        result, output = self.run_harness(source, source_name=source_name)
        transcript = self.transcript(result)
        self.assertEqual(0, result.returncode, transcript)
        self.assertIsNotNone(output, transcript)
        return output

    def assert_conversion(self, source: bytes, transformed: bytes) -> None:
        self.assertEqual(len(source), len(transformed))
        self.assertEqual(b"CRE V1.0", transformed[:8])
        self.assertEqual(FIGHTER_CLASS, transformed[0x273])
        self.assertEqual(
            SYNTHETIC_WIZARD_SLAYER_KIT,
            u32(transformed, 0x244),
            "CRE kit dword must use the WIZARDSLAYER value resolved from KIT.IDS",
        )

        for offset, (before, after) in enumerate(zip(source, transformed)):
            if offset not in SHARTEEL_KIT_OFFSETS:
                self.assertEqual(
                    before,
                    after,
                    f"kit-only conversion changed byte 0x{offset:03x}",
                )

    def assert_failed_closed(self, source: bytes, *, expected_pattern: str) -> None:
        result, output = self.run_harness(source)
        transcript = self.transcript(result)
        self.assertNotEqual(0, result.returncode, transcript)
        self.assertIsNone(output, transcript)
        self.assertRegex(transcript.lower(), expected_pattern)

    def test_synthetic_kit_id_proves_symbolic_resolution(self):
        self.assertNotEqual(LEGACY_WIZARD_SLAYER_ID, SYNTHETIC_WIZARD_SLAYER_ID)
        self.assertIn(
            f"0x{SYNTHETIC_WIZARD_SLAYER_ID:04X} WIZARDSLAYER",
            kit_ids_text(),
        )
        self.assertEqual(
            0x40A20000,
            SYNTHETIC_WIZARD_SLAYER_KIT,
        )

    def test_harness_resolves_installed_kit_and_invokes_production_patch_once(self):
        harness = SHARTEEL_HARNESS.read_text(encoding="utf-8")
        self.assertIn("INCLUDE ~%argv[0]%~", harness)
        self.assertRegex(
            harness,
            r"IDS_OF_SYMBOL\s*\(\s*~kit~\s*~WIZARDSLAYER~\s*\)",
        )
        self.assertEqual(1, harness.count("LPF cbm_sharteel_make_wizard_slayer"))

    def test_all_three_joinable_variants_change_only_the_resolved_kit(self):
        dv_spellings = ("sharteel", "SHARTEEL", "ShArTeEl")
        for index, resref in enumerate(SHARTEEL_VARIANTS):
            with self.subTest(resref=resref):
                source = make_sharteel_cre(
                    dv=dv_spellings[index],
                    xp=32_123 + (index * 41_111),
                    seed=211 + index,
                )
                transformed = self.transform(source, source_name=f"{resref}.CRE")
                self.assert_conversion(source, transformed)

    def test_patch_is_byte_idempotent(self):
        source = make_sharteel_cre(dv="sHaRtEeL", seed=231)
        first = self.transform(source)
        second = self.transform(first)
        self.assertEqual(first, second)

    def test_signature_identity_class_and_kit_guards_fail_closed(self):
        bad_signature = bytearray(make_sharteel_cre())
        bad_signature[0:8] = b"BAD V1.0"
        cases = (
            (bytes(bad_signature), r"signature|cre v1\.0"),
            (make_sharteel_cre(dv="NOTSHARTEEL"), r"death.?variable|\bdv\b"),
            (make_sharteel_cre(class_id=CLERIC_CLASS), r"\bclass\b"),
            (make_sharteel_cre(kit=0x40B10000), r"\bkit\b"),
        )
        for source, pattern in cases:
            with self.subTest(expected=pattern):
                self.assert_failed_closed(source, expected_pattern=pattern)

    def test_public_component_installs_independently_and_uninstalls_byte_exactly(self):
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        with tempfile.TemporaryDirectory(prefix="cbm-sharteel-public-") as raw_temp:
            game = SyntheticSharTeelPublicGame(Path(raw_temp) / "game")
            for viconia_resref in VICONIA_VARIANTS:
                self.assertFalse((game.override / f"{viconia_resref}.CRE").exists())

            install = game.run(self.weidu, "--force-install-list")
            transcript = game.transcript(install)
            self.assertEqual(0, install.returncode, transcript)
            self.assertIn("SUCCESSFULLY INSTALLED", transcript)
            self.assertRegex(game.active_log(), r"(?m)#0\s+#193\b")
            game.assert_stable_inputs(self)
            self.assertEqual(
                game.initial_override["KIT.IDS"],
                (game.override / "KIT.IDS").read_bytes(),
            )

            for resref in SHARTEEL_VARIANTS:
                source = game.initial_override[f"{resref}.CRE"]
                transformed = (game.override / f"{resref}.CRE").read_bytes()
                self.assert_conversion(source, transformed)

            duel_name = f"{SHARTEEL_DUEL_RESOURCE}.CRE"
            self.assertEqual(
                game.initial_override[duel_name],
                (game.override / duel_name).read_bytes(),
                "SHARTD is a nonjoinable duel resource and must not be patched",
            )

            uninstall = game.run(self.weidu, "--force-uninstall-list")
            self.assertEqual(0, uninstall.returncode, game.transcript(uninstall))
            self.assertNotRegex(game.active_log(), r"(?m)#0\s+#193\b")
            self.assertEqual(game.initial_override, file_tree(game.override))
            game.assert_stable_inputs(self)

    def test_public_component_requires_every_joinable_variant_before_writes(self):
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        with tempfile.TemporaryDirectory(prefix="cbm-sharteel-missing-") as raw_temp:
            game = SyntheticSharTeelPublicGame(
                Path(raw_temp) / "game",
                missing="SHARTE4",
            )
            result = game.run(self.weidu, "--force-install-list")
            transcript = game.transcript(result)
            self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
            self.assertIn("SHARTE4.CRE", transcript)
            self.assertNotRegex(game.active_log(), r"(?m)#0\s+#193\b")
            self.assertEqual(game.initial_override, file_tree(game.override))
            game.assert_stable_inputs(self)

    def test_public_component_metadata_is_explicit_and_excludes_shartd(self):
        self.assertTrue(
            SHARTEEL_TPA.is_file(),
            f"production library is not implemented yet: {SHARTEEL_TPA}",
        )
        tp2 = TP2.read_text(encoding="utf-8")
        self.assertRegex(
            tp2,
            r"(?im)^[ \t]*BEGIN\s+@193\s+DESIGNATED\s+193\b",
        )
        self.assertIn("LABEL ~cbm_sharteel_wizard_slayer~", tp2)
        self.assertIn(
            "INCLUDE ~chriz-bg-modpack/lib/cbm_sharteel_wizard_slayer.tpa~",
            tp2,
        )
        component = tp2_component_block(tp2, SHARTEEL_COMPONENT)
        for resref in SHARTEEL_VARIANTS:
            self.assertIn(f"FILE_EXISTS_IN_GAME ~{resref}.CRE~", component)
            self.assertRegex(component, rf"(?m)\b{resref}\b")
        self.assertNotIn(SHARTEEL_DUEL_RESOURCE, component)
        self.assertNotIn("COPY_EXISTING_REGEXP", component)

        library = SHARTEEL_TPA.read_text(encoding="utf-8")
        self.assertIn("DEFINE_PATCH_FUNCTION cbm_sharteel_make_wizard_slayer", library)
        self.assertRegex(
            component + "\n" + library,
            r"IDS_OF_SYMBOL\s*\(\s*~kit~\s*~WIZARDSLAYER~\s*\)",
        )


if __name__ == "__main__":
    unittest.main()
