"""Exercise companion class choices with real WeiDU and authored game data.

These tests never read or write an installed game. Their binary CRE fixtures
include unrelated character state so class conversion and rollback are checked
through the public installer, rather than by inspecting implementation text.
"""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path

import pytest

from tests.test_utility_xp_installer import (
    SETUP_NAME, WEIDU, SyntheticGame, _file_tree, _is_weidu_artifact,
)


pytestmark = pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")

# Deliberately different from the unmodded KITLIST ordering.
KIT_IDS = {
    "TRUECLASS": 0x4000,
    "SHADOWDANCER": 0x4011,
    "SWASHBUCKLER": 0x4012,
    "ASSASIN": 0x4017,
    "BOUNTY_HUNTER": 0x4018,
}
CHOICES = ((220, "SWASHBUCKLER", 4), (221, "SHADOWDANCER", 4),
           (222, "TRUECLASS", 9), (223, "ASSASIN", 4))
YOSHIMO = ("YOSHI7", "YOSHI8", "YOSHI10", "YOSHI11", "YOSHI12")
HEXXAT = ("OHHEX8", "OHHEX9", "OHHEX10", "OHHEX11", "OHHEX13", "OHHEX15", "OHHEX25")
CLARA = ("OHHFAK8", "OHHFAK9", "OHHFAK10", "OHHFAK11", "OHHFAK13", "OHHFAK15")
VAMPIRE_INNATES = (b"OHHDRAIN", b"OHHSUMM", b"SPIN883")
SKILL_OFFSETS = (0x6A, 0x67, 0x69, 0x68, 0x45, 0x64, 0x65)
PROFICIENCIES = {
    "BASTARDSWORD": 89, "LONGSWORD": 90, "SHORTSWORD": 91, "AXE": 92,
    "TWOHANDEDSWORD": 93, "KATANA": 94, "SCIMITARWAKISASHININJATO": 95,
    "DAGGER": 96, "WARHAMMER": 97, "SPEAR": 98, "HALBERD": 99,
    "FLAILMORNINGSTAR": 100, "MACE": 101, "QUARTERSTAFF": 102,
    "CROSSBOW": 103, "LONGBOW": 104, "SHORTBOW": 105, "DART": 106,
    "SLING": 107, "2HANDED": 111, "SWORDANDSHIELD": 112,
    "SINGLEWEAPON": 113, "2WEAPON": 114, "CLUB": 115,
}
SCRIPT = """IF
  Global("ohh_dom","LOCALS",0)
  LevelGT(Myself,13)
THEN
  RESPONSE #100
    AddSpecialAbility("SPIN883")
    SetGlobal("ohh_dom","LOCALS",1)
END
IF
  Global("ohh_dom","LOCALS",1)
  LevelGT(Myself,23)
THEN
  RESPONSE #100
    AddSpecialAbility("SPIN883")
    SetGlobal("ohh_dom","LOCALS",2)
END
IF
  Global("UnrelatedQuest","LOCALS",0)
  LevelGT(Myself,13)
  LevelGT(Myself,23)
THEN
  RESPONSE #100
    SetGlobal("UnrelatedQuest","LOCALS",1)
END
"""


def table(columns: tuple[str, ...], rows: dict[str, tuple[object, ...]],
          default: str = "0") -> str:
    return "2DA V1.0\n" + default + "\n    " + " ".join(columns) + "\n" + "".join(
        name + " " + " ".join(map(str, cells)) + "\n" for name, cells in rows.items()
    )


def _creature(*, xp: int = 1_000_001, level: int = 14, kit: str = "TRUECLASS",
              death_variable: str = "HEXXAT") -> bytes:
    """Build a CRE V1.0 with a racial innate, inventory and permanent effect."""
    header = bytearray(0x2D4)
    header[:8] = b"CRE V1.0"
    struct.pack_into("<II", header, 0x08, 0, 0)
    struct.pack_into("<III", header, 0x14, 19000, xp, 123)
    struct.pack_into("<HHI", header, 0x24, 73, 81, 0x6100)
    header[0x33] = 1  # Embedded EFF V2 records.
    header[0x52:0x59] = bytes((12, 1, 8, 10, 9, 11, 12))
    header[0x66] = 42
    for offset, score in zip(SKILL_OFFSETS, (40, 90, 90, 75, 65, 20, 30)):
        header[offset] = score
    header[0x234:0x237] = bytes((level, 0, 0))
    header[0x238:0x23F] = bytes((16, 0, 18, 14, 18, 16, 14))
    struct.pack_into("<I", header, 0x244, KIT_IDS[kit] << 16)
    for offset, resref in zip(range(0x248, 0x270, 8),
                              (b"OHHEXOV", b"CBMAI", b"VAMPRACE", b"OHHEXGEN", b"THIEF3")):
        header[offset:offset + 8] = resref.ljust(8, b"\0")
    header[0x270:0x276] = bytes((128, 1, 1, 4, 0, 2))
    header[0x27B] = 0x23
    header[0x280:0x2A0] = death_variable.encode("ascii").ljust(32, b"\0")
    header[0x2CC:0x2D4] = b"OHHEXDLG"

    spells = (*VAMPIRE_INNATES, b"CBMQUEST", b"SPCL414" if kit == "BOUNTY_HUNTER" else b"SPCL412")
    known = b"".join(struct.pack("<8sHH", spell, 0, 2) for spell in spells)
    memory = struct.pack("<HHHHII", 0, len(spells), len(spells), 2, 0, len(spells))
    memorized = b"".join(struct.pack("<8sI", spell, 1) for spell in spells)
    slots = bytearray(b"\xff\xff" * 40)
    struct.pack_into("<H", slots, 17 * 2, 0)  # Vampire cloak remains equipped.
    struct.pack_into("<HH", slots, 38 * 2, 1000, 0)
    items = struct.pack("<8sHHHHI", b"CBMCLOAK", 0, 3, 0, 0, 0x9)
    effect = bytearray(0x108)
    struct.pack_into("<III", effect, 0x08, 101, 1, 0)
    struct.pack_into("<II", effect, 0x14, 0, 5)
    struct.pack_into("<I", effect, 0x1C, 9)
    effect[0x24:0x26] = bytes((100, 0))
    effect[0x30:0x38] = b"CBMVAMP\0"
    effect[0x90:0x98] = b"CBMVAMP\0"
    proficiency = bytearray(0x108)
    struct.pack_into("<III", proficiency, 0x08, 233, 1, 0)
    struct.pack_into("<III", proficiency, 0x14, 1, 105, 9)
    proficiency[0x24:0x26] = bytes((100, 0))
    clab_effect = bytearray(0x108)
    struct.pack_into("<III", clab_effect, 0x08, 0, 1, 0)
    struct.pack_into("<II", clab_effect, 0x14, 1, 0)
    struct.pack_into("<I", clab_effect, 0x1C, 9)
    struct.pack_into("<I", clab_effect, 0x88, 1)
    clab_effect[0x8C:0x94] = b"CLABFX\0\0"
    chunks = (known, memory, memorized, slots, items, effect + proficiency + clab_effect)
    cursor = len(header)
    for pointer, count, chunk in zip((0x2A0, 0x2A8, 0x2B0, 0x2B8, 0x2BC, 0x2C4),
                                      (len(spells), 1, len(spells), None, 1, 3), chunks):
        struct.pack_into("<I", header, pointer, cursor)
        if count is not None:
            struct.pack_into("<I", header, pointer + 4, count)
        cursor += len(chunk)
    return bytes(header) + b"".join(chunks)


def _resource_records(creature: bytes, pointer: int, count_pointer: int,
                      size: int) -> list[bytes]:
    offset = struct.unpack_from("<I", creature, pointer)[0]
    count = struct.unpack_from("<I", creature, count_pointer)[0]
    return [creature[offset + index * size:offset + (index + 1) * size]
            for index in range(count)]


def _write_tables(game: SyntheticGame) -> None:
    tables = {
        "CLASS.IDS": "IDS V1.0\n1 MAGE\n2 FIGHTER\n4 THIEF\n9 FIGHTER_THIEF\n",
        "KIT.IDS": "IDS V1.0\n" + "".join(
            f"{value:#x} {symbol}\n" for symbol, value in KIT_IDS.items()),
        "STATS.IDS": "IDS V1.0\n44 XP\n" + "".join(
            f"{stat} PROFICIENCY{row}\n" for row, stat in PROFICIENCIES.items()),
        "THIEFSKL.2DA": table(("START_POINTS", "LEVEL_POINTS"), {
            "THIEF": (40, 25), "SWASHBUCKLER": (40, 25),
            "SHADOWDANCER": (30, 20), "ASSASIN": (40, 15),
            "BOUNTY_HUNTER": (40, 20), "FIGHTER_THIEF": (40, 25),
        }),
        "THIEFSCL.2DA": table(("THIEF", "FIGHTER_THIEF", "ASSASIN", "BOUNTY_HUNTER",
                               "SWASHBUCKLER", "SHADOWDANCER"), {
            "PICK_POCKETS": (100, 100, 100, 100, 100, 100),
            "OPEN_LOCKS": (100, 100, 100, 100, 100, 100),
            "FIND_TRAPS": (100, 100, 100, 100, 100, 100),
            "MOVE_SILENTLY": (100, 100, 100, 100, 100, 100),
            "HIDE_IN_SHADOWS": (100, 100, 100, 100, 100, 100),
            "DETECT_ILLUSION": (100, 100, 100, 100, 100, 100),
            "SET_TRAPS": (100, 100, 100, 100, 100, 0),
            "STEALTH": (0, 0, 0, 0, 0, 0),
        }),
        "XPLEVEL.2DA": table(tuple(str(n) for n in range(1, 41)), {
            "FIGHTER": (0, 2000, 4000, 8000, 16000, 32000, 64000, 125000,
                        250000, 500000, 750000, 1000000, 1250000, 1500000,
                        1750000, 2000000, 2250000, 2500000, 2750000, 3000000,
                        *(3_250_000 + 250_000 * n for n in range(20))),
            "THIEF": (0, 1250, 2500, 5000, 10000, 20000, 40000, 70000,
                      110000, 160000, 220000, 440000, 660000, 880000,
                      1100000, 1320000, 1540000, 1760000, 1980000, 2200000,
                      *(2_420_000 + 220_000 * n for n in range(20))),
        }, "-1"),
        "KITLIST.2DA": table(("ROWNAME", "LOWER", "MIXED", "HELP", "ABILITIES",
                              "PROFICIENCY", "UNUSABLE", "CLASS", "KITIDS"), {
            str(index): (symbol, 0, 0, 0, f"CBMCL{index}",
                                   0, "0x00000000", 4, f"{value:#x}")
            for index, (symbol, value) in enumerate(KIT_IDS.items())
        }),
        "HPCLASS.2DA": table(("TABLE",), {
            "FIGHTER": ("HPWAR",), "THIEF": ("HPROG",),
            "ASSASIN": ("HPROG",), "BOUNTY_HUNTER": ("HPROG",),
            "SWASHBUCKLER": ("HPROG",), "SHADOWDANCER": ("HPROG",),
            "FIGHTER_THIEF": ("HPFT",),
        }, "HPWAR"),
        "HPWAR.2DA": table(("SIDES", "ROLLS", "MODIFIER"), {
            str(level): (10, 1, 0) if level <= 9 else (0, 0, 3)
            for level in range(1, 41)
        }),
        "HPROG.2DA": table(("SIDES", "ROLLS", "MODIFIER"), {
            str(level): (6, 1, 0) if level <= 10 else (0, 0, 2)
            for level in range(1, 41)
        }),
        "THAC0.2DA": table(tuple(str(n) for n in range(1, 51)), {
            "FIGHTER": tuple(max(0, 21 - level) for level in range(1, 51)),
            "THIEF": tuple(max(10, 20 - (level - 1) // 2) for level in range(1, 51)),
        }),
        "SAVEWAR.2DA": table(tuple(str(n) for n in range(1, 51)), {
            "DEATH": tuple(max(3, 14 - 2 * ((level - 1) // 2)) for level in range(1, 51)),
            "WANDS": tuple(max(5, 16 - 2 * ((level - 1) // 2)) for level in range(1, 51)),
            "POLY": tuple(max(4, 15 - 2 * ((level - 1) // 2)) for level in range(1, 51)),
            "BREATH": tuple(max(4, 17 - 2 * ((level - 1) // 2)) for level in range(1, 51)),
            "SPELL": tuple(max(6, 17 - 2 * ((level - 1) // 2)) for level in range(1, 51)),
        }),
        "SAVEROG.2DA": table(tuple(str(n) for n in range(1, 51)), {
            "DEATH": tuple(max(8, 13 - (level - 1) // 4) for level in range(1, 51)),
            "WANDS": tuple(max(4, 14 - (level - 1) // 4) for level in range(1, 51)),
            "POLY": tuple(max(7, 12 - (level - 1) // 4) for level in range(1, 51)),
            "BREATH": tuple(max(11, 16 - (level - 1) // 4) for level in range(1, 51)),
            "SPELL": tuple(max(5, 15 - (level - 1) // 4) for level in range(1, 51)),
        }),
        "LORE.2DA": table(("RATE",), {"FIGHTER": (1,), "THIEF": (3,)}, "1"),
        "PROFS.2DA": table(("FIRST_LEVEL", "RATE"), {
            "FIGHTER": (4, 3), "THIEF": (2, 4), "FIGHTER_THIEF": (4, 3),
        }),
        "WEAPPROF.2DA": table(("ID", "NAME_REF", "DESC_REF", "FIGHTER", "THIEF",
                               "FIGHTER_THIEF", "ASSASIN", "BOUNTY_HUNTER",
                               "SWASHBUCKLER", "SHADOWDANCER"), {
            row: (stat, 0, 0, 5 if stat < 111 else 3, 1, 2, 1, 1, 2, 1)
            for row, stat in PROFICIENCIES.items()
        }),
    }
    for index in range(len(KIT_IDS)):
        ability = "GA_SPCL414" if index == 4 else "GA_SPCL412" if index == 0 else "****"
        tables[f"CBMCL{index}.2DA"] = table(tuple(str(n) for n in range(1, 41)), {
            "ABILITY1": (ability, *("****",) * 39),
            "ABILITY2": ("AP_CLABFX", *("****",) * 39),
        }, "****")
    tables["CLABTH01.2DA"] = tables["CBMCL0.2DA"]
    tables.update({
        "ACTION.IDS": "IDS V1.0\n30 SetGlobal(S:Name*,S:Area*,I:Value*)\n"
                      "147 AddSpecialAbility(S:ResRef*)\n",
        "TRIGGER.IDS": "IDS V1.0\n0x400F Global(S:Name*,S:Area*,I:Value*)\n"
                       "0x4016 LevelGT(O:Object*,I:Level*)\n"
                       "0x4034 XPGT(O:Object*,I:XP*)\n",
        "OBJECT.IDS": "IDS V1.0\n1 Myself\n",
    })
    for name in ("EA", "GENERAL", "RACE", "SPECIFIC", "GENDER", "ALIGN"):
        tables[f"{name}.IDS"] = "IDS V1.0\n"
    for name, payload in tables.items():
        (game.override / name.lower()).write_text(payload, encoding="ascii")


def _run(game: SyntheticGame, component: int, *, uninstall: bool = False):
    result = subprocess.run(
        [str(WEIDU), SETUP_NAME, "--noautoupdate", "--no-exit-pause",
         "--game", str(game.root), "--use-lang", "en_us", "--language", "0",
         "--force-uninstall-list" if uninstall else "--force-install-list", str(component)],
        cwd=game.root, capture_output=True, text=True, timeout=60,
    )
    return result, result.stdout + result.stderr


def _assert_restored(game: SyntheticGame) -> None:
    actual = {name: data for name, data in _file_tree(game.root).items()
              if not _is_weidu_artifact(name)}
    expected = {name: data for name, data in game.before.items()
                if not _is_weidu_artifact(name)}
    assert actual == expected


def _compile(game: SyntheticGame, source: str, directory: Path) -> bytes:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "test.baf").write_text(source, encoding="ascii")
    result = subprocess.run(
        [str(WEIDU), "--noautoupdate", "--no-auto-tp2", "--no-exit-pause", "--game", str(game.root),
         "--use-lang", "en_us", "--out", ".", "test.baf"],
        cwd=directory, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return next(path for path in directory.iterdir() if path.name.lower() == "test.bcs").read_bytes()


def _thief_threshold(game: SyntheticGame, level: int) -> int:
    rows = (game.override / "xplevel.2da").read_text(encoding="ascii").splitlines()
    column = rows[2].split().index(str(level)) + 1
    thief = next(row.split() for row in rows[3:] if row.startswith("THIEF "))
    return int(thief[column])


def _make_game(tmp_path: Path, *, game_type: str = "bg2ee",
               absent: tuple[str, ...] = ()) -> SyntheticGame:
    game = SyntheticGame(tmp_path / "game", game=game_type, eeex=False)
    _write_tables(game)
    for name in (*YOSHIMO, *HEXXAT, *CLARA, "OTHER", "YOSHI99", "OHHEX99"):
        if name in absent:
            continue
        is_yoshimo = name.startswith("YOSHI")
        creature = _creature(
            xp=2_500_000 if name == "OHHEX25" else 1_000_001,
            level=15 if name == "OHHEX25" else 14,
            kit="BOUNTY_HUNTER" if is_yoshimo else "TRUECLASS",
            death_variable="YOSHIMO" if is_yoshimo else "OHHFAK" if name in CLARA else "HEXXAT",
        )
        (game.override / f"{name.lower()}.cre").write_bytes(creature)
    sword = bytearray(0x72)
    sword[:8] = b"ITM V1  "
    sword[0x2B] = 0xB0
    (game.override / "npsw02.itm").write_bytes(sword)
    script = _compile(game, SCRIPT, tmp_path / "compiled-original")
    for name in ("HEXXAT", "HEXXA25"):
        (game.override / f"{name.lower()}.bcs").write_bytes(script)
    game.before = _file_tree(game.root)
    game.override_before = _file_tree(game.override)
    return game


def _assert_preserved_character_state(before: bytes, after: bytes) -> None:
    for start, end in ((0x00, 0x24), (0x28, 0x45), (0x46, 0x52), (0x238, 0x244), (0x248, 0x273),
                       (0x274, 0x2A0), (0x2CC, 0x2D4)):
        assert after[start:end] == before[start:end], f"character metadata changed at {start:#x}"
    # Offsets may legitimately move as a kit's memorized innate is removed.
    assert _resource_records(after, 0x2BC, 0x2C0, 20) == _resource_records(before, 0x2BC, 0x2C0, 20)
    old_slots = struct.unpack_from("<I", before, 0x2B8)[0]
    new_slots = struct.unpack_from("<I", after, 0x2B8)[0]
    assert after[new_slots:new_slots + 80] == before[old_slots:old_slots + 80]
    vampire_effect = _resource_records(before, 0x2C4, 0x2C8, 0x108)[0]
    assert vampire_effect in _resource_records(after, 0x2C4, 0x2C8, 0x108)
    for pointer, count in ((0x2A0, 0x2A4), (0x2B0, 0x2B4)):
        spell_names = {record[:8].rstrip(b"\0") for record in _resource_records(after, pointer, count, 12)}
        assert set(VAMPIRE_INNATES) | {b"CBMQUEST"} <= spell_names


def _assert_installed_choice(
    game: SyntheticGame, tmp_path: Path, component: int, kit: str, class_id: int,
) -> None:
    """Check transformed bytes and a strict allowlist for source and ZIP installs."""
    assert f"#{component} " in game.active_log()
    expected_targets = YOSHIMO if component == 220 else HEXXAT
    after = _file_tree(game.root)
    changed = {name for name in set(after) | set(game.before)
               if after.get(name) != game.before.get(name) and not _is_weidu_artifact(name)}
    expected_changes = {f"OVERRIDE/{name}.CRE" for name in expected_targets}
    if component == 220:
        expected_changes.add("OVERRIDE/NPSW02.ITM")
        assert after["OVERRIDE/NPSW02.ITM"][0x2B] == 0xA0
    if component == 222:
        expected_changes.update(("OVERRIDE/HEXXAT.BCS", "OVERRIDE/HEXXA25.BCS"))
        expected_source = SCRIPT.replace(
            'Global("ohh_dom","LOCALS",0)\n  LevelGT(Myself,13)',
            f'Global("ohh_dom","LOCALS",0)\n  XPGT(Myself,{_thief_threshold(game, 14) - 1})',
        ).replace(
            'Global("ohh_dom","LOCALS",1)\n  LevelGT(Myself,23)',
            f'Global("ohh_dom","LOCALS",1)\n  XPGT(Myself,{_thief_threshold(game, 24) - 1})',
        )
        expected_script = _compile(game, expected_source, tmp_path / "compiled-expected")
        assert after["OVERRIDE/HEXXAT.BCS"] == expected_script
        assert after["OVERRIDE/HEXXA25.BCS"] == expected_script
    assert changed == expected_changes
    for name in expected_targets:
        original = game.before[f"OVERRIDE/{name}.CRE"]
        creature = after[f"OVERRIDE/{name}.CRE"]
        assert creature[0x273] == class_id
        assert struct.unpack_from("<I", creature, 0x244)[0] == KIT_IDS[kit] << 16
        assert struct.unpack_from("<I", creature, 0x18)[0] == struct.unpack_from("<I", original, 0x18)[0]
        assert creature[0x234:0x237] == (bytes((10, 12, 0)) if component == 222 else original[0x234:0x237])
        _assert_preserved_character_state(original, creature)
        effects = _resource_records(creature, 0x2C4, 0x2C8, 0x108)
        assert all(effect[0x8C:0x94] != b"CLABFX\0\0" for effect in effects)
        thief_level = creature[0x235 if component == 222 else 0x234]
        start, rate = (30, 20) if component == 221 else (40, 15) if component == 223 else (40, 25)
        assert sum(creature[offset] for offset in SKILL_OFFSETS) == start + (thief_level - 1) * rate + (0 if component == 220 else 45)
        if component == 221:
            assert creature[0x65] == 0  # Shadowdancers have no Set Traps allocation.
        if component == 222:
            profs = {struct.unpack_from("<I", effect, 0x18)[0]: struct.unpack_from("<I", effect, 0x14)[0] & 7
                     for effect in effects if struct.unpack_from("<I", effect, 0x08)[0] == 233}
            assert profs[105] == 1  # Keep her existing legal shortbow proficiency.
            assert sum(profs.values()) == 7
            # The fixture's combat tables differ from vanilla, so these verify
            # use of effective progression while retaining its NPC modifiers.
            assert creature[0x52] == (10 if name == "OHHEX25" else 9)
            assert creature[0x54:0x59] == bytes((4, 7, 7, 7, 9))
            assert creature[0x66] == (33 if name == "OHHEX25" else 36)
            assert struct.unpack_from("<HH", creature, 0x24) == (
                (75, 84) if name == "OHHEX25" else (79, 88)
            )
        else:
            assert creature[0x24:0x28] == original[0x24:0x28]
            assert creature[0x52:0x59] == original[0x52:0x59]
        if component == 220:
            for pointer, count in ((0x2A0, 0x2A4), (0x2B0, 0x2B4)):
                assert b"SPCL414\0" not in {record[:8] for record in _resource_records(creature, pointer, count, 12)}


@pytest.mark.parametrize("component,kit,class_id", CHOICES)
@pytest.mark.parametrize("game_type", ("bg2ee", "eet"))
def test_public_choices_preserve_character_state_and_uninstall_exactly(
    tmp_path, component, kit, class_id, game_type,
):
    game = _make_game(tmp_path, game_type=game_type)
    result, transcript = _run(game, component)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    _assert_installed_choice(game, tmp_path, component, kit, class_id)
    result, transcript = _run(game, component, uninstall=True)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY REMOVED" in transcript
    assert f"#{component} " not in game.active_log()
    _assert_restored(game)


@pytest.mark.parametrize("component,kit,class_id", CHOICES)
def test_absent_companion_is_skipped_without_writes(tmp_path, component, kit, class_id):
    game = _make_game(tmp_path, absent=YOSHIMO if component == 220 else HEXXAT)
    _, transcript = _run(game, component)
    assert "SKIPPING:" in transcript
    assert "SUCCESSFULLY INSTALLED" not in transcript
    assert "NOT INSTALLED DUE TO ERRORS" not in transcript
    _assert_restored(game)


def test_unsupported_game_is_skipped_without_writes(tmp_path):
    game = _make_game(tmp_path, game_type="bgee")
    _, transcript = _run(game, 221)
    assert "SKIPPING:" in transcript
    assert "SUCCESSFULLY INSTALLED" not in transcript
    _assert_restored(game)


def test_late_wrong_class_rolls_back_every_already_patched_companion(tmp_path):
    game = _make_game(tmp_path)
    path = game.override / "ohhex25.cre"
    creature = bytearray(path.read_bytes())
    creature[0x273] = 2
    path.write_bytes(creature)
    game.before = _file_tree(game.root)
    _, transcript = _run(game, 221)
    assert "NOT INSTALLED DUE TO ERRORS" in transcript
    assert "SUCCESSFULLY INSTALLED" not in transcript
    assert "single-class thief" in transcript
    _assert_restored(game)


def test_missing_progression_table_fails_cleanly(tmp_path):
    game = _make_game(tmp_path)
    (game.override / "thiefskl.2da").unlink()
    game.before = _file_tree(game.root)
    _, transcript = _run(game, 221)
    assert "THIEFSKL" in transcript.upper()
    assert "SUCCESSFULLY INSTALLED" not in transcript
    _assert_restored(game)


def test_hexxat_choices_are_exclusive_and_switch_without_compounding(tmp_path):
    game = _make_game(tmp_path)
    result, transcript = _run(game, 221)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    installed = _file_tree(game.override)
    result, transcript = _run(game, 223)
    assert result.returncode == 0, transcript
    assert "another subcomponent" in transcript
    assert "#221 " in game.active_log()
    assert "#223 " not in game.active_log()
    assert _file_tree(game.override) == installed
    result, transcript = _run(game, 221, uninstall=True)
    assert result.returncode == 0, transcript
    _assert_restored(game)
    result, transcript = _run(game, 223)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    assert "#221 " not in game.active_log()
    assert "#223 " in game.active_log()
    creature = (game.override / "ohhex8.cre").read_bytes()
    assert struct.unpack_from("<I", creature, 0x244)[0] == KIT_IDS["ASSASIN"] << 16
    assert sum(creature[offset] for offset in SKILL_OFFSETS) == 40 + 13 * 15 + 45
    result, transcript = _run(game, 223, uninstall=True)
    assert result.returncode == 0, transcript
    _assert_restored(game)


def test_effective_kit_skill_restrictions_are_honored_without_artisan_dependency(tmp_path):
    game = _make_game(tmp_path)
    budget_path = game.override / "thiefskl.2da"
    budget_path.write_text(
        budget_path.read_text(encoding="ascii").replace("SWASHBUCKLER 40 25", "SWASHBUCKLER 40 15"),
        encoding="ascii",
    )
    path = game.override / "thiefscl.2da"
    rows = path.read_text(encoding="ascii").splitlines()
    for index, row in enumerate(rows):
        cells = row.split()
        if cells and cells[0] in {"MOVE_SILENTLY", "HIDE_IN_SHADOWS", "SET_TRAPS"}:
            cells[5] = "0"  # Swashbuckler's actual column in this fixture.
            rows[index] = " ".join(cells)
    path.write_text("\n".join(rows) + "\n", encoding="ascii")
    game.before = _file_tree(game.root)
    result, transcript = _run(game, 220)
    assert result.returncode == 0, transcript
    creature = (game.override / "yoshi7.cre").read_bytes()
    assert creature[0x68] == creature[0x45] == creature[0x65] == 0
    assert sum(creature[offset] for offset in SKILL_OFFSETS) == 40 + 13 * 15
    result, transcript = _run(game, 220, uninstall=True)
    assert result.returncode == 0, transcript
    _assert_restored(game)


@pytest.mark.parametrize("source_xp,source_level,levels,pips", (
    (90_000, 8, (6, 7, 0), 6),
    (800_000, 13, (9, 11, 0), 7),
))
def test_fighter_proficiency_points_arrive_at_levels_six_and_nine(
    tmp_path, source_xp, source_level, levels, pips,
):
    game = _make_game(tmp_path)
    (game.override / "ohhex8.cre").write_bytes(_creature(xp=source_xp, level=source_level))
    game.before = _file_tree(game.root)
    result, transcript = _run(game, 222)
    assert result.returncode == 0, transcript
    creature = (game.override / "ohhex8.cre").read_bytes()
    assert creature[0x234:0x237] == bytes(levels)
    effects = _resource_records(creature, 0x2C4, 0x2C8, 0x108)
    assert sum(struct.unpack_from("<I", effect, 0x14)[0] & 7 for effect in effects
               if struct.unpack_from("<I", effect, 0x08)[0] == 233) == pips
    result, transcript = _run(game, 222, uninstall=True)
    assert result.returncode == 0, transcript
    _assert_restored(game)


def test_changed_domination_script_rolls_back_creatures_and_first_script(tmp_path):
    game = _make_game(tmp_path)
    altered = _compile(game, SCRIPT.replace("LevelGT(Myself,23)", "LevelGT(Myself,22)", 1),
                       tmp_path / "compiled-altered")
    (game.override / "hexxa25.bcs").write_bytes(altered)
    game.before = _file_tree(game.root)
    _, transcript = _run(game, 222)
    assert "NOT INSTALLED DUE TO ERRORS" in transcript
    assert "second Domination progression block" in transcript
    _assert_restored(game)
