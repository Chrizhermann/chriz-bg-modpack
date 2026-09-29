"""Real WeiDU tests of Evandra's build using authored, disposable game data."""

from __future__ import annotations

from collections import Counter
import struct
import subprocess

import pytest

from tests.test_utility_xp_installer import (
    SETUP_NAME, WEIDU, SyntheticGame, _file_tree, _is_weidu_artifact,
)


pytestmark = pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
COMPONENT = 224
CLASS_ID = 29  # Relocated on purpose: conversion must use CLASS.IDS.
KIT_ID = 0x4100
KNOWN = {
    6: (4, 2, 1, 0, 0, 0, 0, 0, 0),
    10: (5, 4, 3, 2, 1, 0, 0, 0, 0),
    14: (5, 5, 4, 4, 3, 2, 1, 0, 0),
    18: (5, 5, 4, 4, 4, 3, 3, 2, 1),
}
SLOTS = {
    6: (6, 5, 3, 0, 0, 0, 0, 0, 0),
    10: (6, 6, 6, 5, 3, 0, 0, 0, 0),
    14: (6, 6, 6, 6, 6, 5, 3, 0, 0),
    18: (6, 6, 6, 6, 6, 6, 6, 5, 3),
}
SPELLS = (
    ("MAGIC_MISSILE", "DIMENSION_JUMP", "SHIELD", "IDENTIFY", "SPOOK"),
    ("MIRROR_IMAGE", "INVISIBILITY", "DETECT_INVISIBILITY", "GLITTERDUST", "BLUR"),
    ("SLOW", "SPELL_THRUST", "FIREBALL", "HASTE"),
    ("IMPROVED_INVISIBILITY", "STONE_SKIN", "SPIRIT_ARMOR", "VITRIOLIC_SPHERE"),
    ("BREACH", "SPELL_SHIELD", "SUMMON_SHADOW"),
    ("MISLEAD", "PROTECTION_FROM_MAGIC_WEAPONS"),
    ("PROJECT_IMAGE",),
    (), (),
)
FALLBACKS = {"DIMENSION_JUMP": "COLOR_SPRAY", "VITRIOLIC_SPHERE": "GREATER_MALISON",
             "SUMMON_SHADOW": "ANIMATE_DEAD"}


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def records(data: bytes, pointer: int, stride: int) -> list[bytes]:
    start, count = struct.unpack_from("<II", data, pointer)
    return [data[start + i * stride:start + (i + 1) * stride] for i in range(count)]


def spellbook(data: bytes) -> list[tuple[bytes, tuple[bytes, ...]]]:
    memorized = records(data, 0x2B0, 12)
    result = []
    for info in records(data, 0x2A8, 16):
        first, count = struct.unpack_from("<II", info, 8)
        result.append((info[:8], tuple(memorized[first:first + count])))
    return result


def make_cre(*, level=10, xp=250_000, hp=37, kit=0x04000000,
             variant=0, shuffled=False, v1_effects=False) -> bytes:
    header = bytearray((i * 13 + 7) % 256 for i in range(0x2D4))
    header[:8] = b"CRE V1.0"
    header[0x33] = 0 if v1_effects else 1
    struct.pack_into("<I", header, 0x18, xp)
    struct.pack_into("<HH", header, 0x24, hp, hp + 3)
    header[0x234:0x237] = bytes((level, 2, 3))
    struct.pack_into("<I", header, 0x244, kit)
    header[0x273] = 17  # Arbitrary incoming class is not a fingerprint.
    header[0x280:0x2A0] = b"rh#evandra".ljust(32, b"\0")
    personal = [(b"PERSONAL", 0, 2), (b"PRIEST", 2, 0), (b"SPWI161", 0, 2)]
    wizard = [(b"OLDWIZ", 0, 1)] * variant + [(b"HIDDEN", 8, 1)]
    known_rows = [personal[0], *wizard, personal[1], (b"OLDKIT", 0, 2), personal[2]]
    known = b"".join(struct.pack("<8sHH", *row) for row in known_rows)
    # Non-wizard slices intentionally interleave wizard ones. Include exhausted
    # copies and an innate sharing the exact resref of a desired wizard spell.
    groups = ((0, 2, 3, 2, ((b"PERSONAL", 0), (b"OLDKIT", 1))),
              (0, 11, 12, 1, ((b"OLDWIZ", 1), (b"OLDWIZ", 0))),
              (2, 4, 5, 0, ((b"PRIEST", 0), (b"PRIEST", 1))),
              (8, 7, 8, 1, ((b"HIDDEN", 1),)),
              (0, 1, 2, 2, ((b"SPWI161", 1),)))
    memory = bytearray()
    memorized = bytearray()
    for spl_level, base, maximum, kind, spells in groups:
        memory.extend(struct.pack("<HHHHII", spl_level, base, maximum, kind,
                                  len(memorized) // 12, len(spells)))
        memorized.extend(b"".join(struct.pack("<8sI", *spell) for spell in spells))
    slots = struct.pack("<40H", *([0xFFFF] * 21 + [0] + [0xFFFF] * 16 + [1000, 3]))
    items = struct.pack("<8sHHHHI", b"EVITEM", 1, 2, 3, 4, 9)
    effects = []
    for opcode, parent, parent_type in ((142, b"PERSONAL", 1), (233, b"PIP", 1),
                                        (0, b"OLDKIT", 1), (0, b"OLDKIT", 2)):
        effect = bytearray(0x30 if v1_effects else 0x108)
        if v1_effects:
            struct.pack_into("<HBBII", effect, 0, opcode, 1, 0, 2, 105)
            effect[0x14:0x1C] = parent.ljust(8, b"\0")
        else:
            struct.pack_into("<IIIIII", effect, 8, opcode, 1, 0, 2, 105, 9)
            struct.pack_into("<I", effect, 0x88, parent_type)
            effect[0x8C:0x94] = parent.ljust(8, b"\0")
        effects.append(bytes(effect))
    blocks = {
        0x2A0: (known, len(known_rows)), 0x2A8: (bytes(memory), len(groups)),
        0x2B0: (bytes(memorized), len(memorized) // 12), 0x2B8: (slots, None),
        0x2BC: (items, 1), 0x2C4: (b"".join(effects), len(effects)),
    }
    order = (0x2B0, 0x2C4, 0x2B8, 0x2A0, 0x2BC, 0x2A8) if shuffled else tuple(blocks)
    body = bytearray()
    for pointer in order:
        payload, count = blocks[pointer]
        struct.pack_into("<I", header, pointer, len(header) + len(body))
        if count is not None:
            struct.pack_into("<I", header, pointer + 4, count)
        body.extend(payload)
    return bytes(header + body)


def make_game(tmp_path, *, sr=True, game_type="bg2ee", levels=(10, 14),
              shuffled=False, v1_effects=False, changed_rules=False):
    game = SyntheticGame(tmp_path / "game", game=game_type, eeex=False)
    ov = game.override
    (ov / "class.ids").write_text(f"IDS V1.0\n{CLASS_ID} SORCERER\n1 MAGE\n")
    (ov / "kit.ids").write_text(f"IDS V1.0\n{KIT_ID:#x} TRUECLASS\n0x0400 MAGESCHOOL_ILLUSIONIST\n")
    (ov / "kitlist.2da").write_text(
        "2DA V1.0\n0\n NAME ABILITIES KITIDS\n0 ILLUSIONIST CBMEOLD 0x0400\n"
    )
    (ov / "cbmeold.2da").write_text("2DA V1.0\n****\n 1 2\nA GA_OLDKIT AP_OLDKIT\n")
    for table, budgets in (("splsrckn", KNOWN), ("mxsplsrc", SLOTS)):
        # Reverse columns and rows to prove labels, not incidental positions,
        # identify both stored character level and spell level.
        rows = "2DA V1.0\n0\n 9 8 7 6 5 4 3 2 1\n"
        for level, values in reversed(tuple(budgets.items())):
            if changed_rules and level == 10:
                values = (2, 1, 1, 0, 0, 0, 0, 0, 0) if table == "splsrckn" else (4, 3, 2, 0, 0, 0, 0, 0, 0)
            rows += f"{level} " + " ".join(map(str, reversed(values))) + "\n"
        (ov / f"{table}.2da").write_text(rows)
    symbols = "IDS V1.0\n"
    resolved = []
    for level, picks in enumerate(SPELLS, 1):
        level_resrefs = []
        for index, name in enumerate(picks, 1):
            name = name if sr else FALLBACKS.get(name, name)
            slot = level * 100 + 60 + index
            resref = f"SPWI{slot}"
            symbols += f"{slot + 2000} WIZARD_{name}\n"
            spl = bytearray(0x72)
            spl[:8] = b"SPL V1  "
            struct.pack_into("<H", spl, 0x1C, 1)
            struct.pack_into("<I", spl, 0x34, level)
            (ov / f"{resref.lower()}.spl").write_bytes(spl)
            level_resrefs.append(resref)
        resolved.append(tuple(level_resrefs))
    # Misleading fixed resrefs exist but must never be chosen.
    for resref in ("SPWI104", "SPWI105", "SPWI121", "SPWI426", "SPWI501"):
        (ov / f"{resref.lower()}.spl").write_bytes(b"incorrect fixed resource")
    (ov / "spell.ids").write_text(symbols)
    (ov / "stats.ids").write_text("IDS V1.0\n")
    (ov / "hidespl.2da").write_text(
        "2DA V1.0\n0\n IS_REMOVED IS_FINAL IS_HIDDEN\nHIDDEN 1 0 1\nSPWI104 0 0 1\n"
    )
    for index, name in enumerate(("rh#eva", "rh#ev25")):
        (ov / f"{name}.cre").write_bytes(make_cre(
            level=levels[index], xp=(678_901, 2_500_007)[index], hp=(2, 109)[index],
            variant=index * 3, shuffled=shuffled, v1_effects=v1_effects,
        ))
    (ov / "rh#ev99.cre").write_bytes(make_cre())
    game.before = _file_tree(game.root)
    return game, tuple(resolved)


def run(game, *, uninstall=False, twice=False):
    setup = SETUP_NAME
    component = COMPONENT
    if twice:
        setup = "evandra-repeat.tp2"
        component = 1
        (game.root / setup).write_text(
            "BACKUP ~weidu_external/backup/evandra-repeat~\nAUTHOR ~test~\n"
            "BEGIN ~Evandra repeat application~ DESIGNATED 1\n"
            "INCLUDE ~chriz-bg-modpack/lib/cbm_collection_defaults.tpa~\n"
            "INCLUDE ~chriz-bg-modpack/lib/cbm_npc_build_helpers.tpa~\n"
            "INCLUDE ~chriz-bg-modpack/lib/cbm_evandra_sorcerer.tpa~\n"
            "LAF cbm_evandra_install END\n"
        )
    result = subprocess.run(
        [str(WEIDU), setup, "--noautoupdate", "--no-auto-tp2", "--no-exit-pause",
         "--game", str(game.root), "--use-lang", "en_us", "--language", "0",
         "--force-uninstall-list" if uninstall else "--force-install-list", str(component)],
        cwd=game.root, capture_output=True, text=True, timeout=60,
    )
    return result, result.stdout + result.stderr


def assert_restored(game):
    actual = {name: data for name, data in _file_tree(game.root).items()
              if not _is_weidu_artifact(name)}
    expected = {name: data for name, data in game.before.items()
                if not _is_weidu_artifact(name)}
    assert actual == expected


def assert_conversion(before, after, resolved, *, changed_rules=False):
    assert after[0x273] == CLASS_ID
    assert u32(after, 0x244) == KIT_ID << 16
    for start, end in ((0, 0x244), (0x248, 0x273), (0x274, 0x2A0), (0x2CC, 0x2D4)):
        assert before[start:end] == after[start:end]
    assert records(before, 0x2BC, 20) == records(after, 0x2BC, 20)
    a, b = u32(before, 0x2B8), u32(after, 0x2B8)
    assert before[a:a + 80] == after[b:b + 80]
    stride = 0x108 if before[0x33] else 0x30
    expected_effects = [row for row in records(before, 0x2C4, stride)
                        if stride == 0x30 or row[0x88:0x94] != struct.pack("<I8s", 1, b"OLDKIT")]
    assert expected_effects == records(after, 0x2C4, stride)
    known = records(after, 0x2A0, 12)
    original_nonwizard = [row for row in records(before, 0x2A0, 12)
                          if row[10:12] != b"\1\0" and row[:8].rstrip(b"\0") != b"OLDKIT"]
    assert original_nonwizard == [row for row in known if row[10:12] != b"\1\0"]
    original_groups = []
    for info, spells in spellbook(before):
        if info[6:8] != b"\1\0":
            original_groups.append((info, tuple(row for row in spells if row[:8].rstrip(b"\0") != b"OLDKIT")))
    # Existing helper removes OLDKIT's copies but preserves slot metadata.
    assert original_groups == [(info, spells) for info, spells in spellbook(after) if info[6:8] != b"\1\0"]
    level = before[0x234]
    budgets, slots = KNOWN[level], SLOTS[level]
    if changed_rules and level == 10:
        budgets, slots = (2, 1, 1, 0, 0, 0, 0, 0, 0), (4, 3, 2, 0, 0, 0, 0, 0, 0)
    expected_known = []
    wizard_groups = [(info, spells) for info, spells in spellbook(after) if info[6:8] == b"\1\0"]
    assert len(wizard_groups) == 9
    for index, picks in enumerate(resolved):
        expected = picks[:budgets[index]] if slots[index] else ()
        expected_known.extend(struct.pack("<8sHH", pick.encode(), index, 1) for pick in expected)
        info, spells = wizard_groups[index]
        assert struct.unpack("<HHHH", info) == (index, slots[index], slots[index], 1)
        assert Counter(spells) == Counter({struct.pack("<8sI", pick.encode(), 1): slots[index]
                                          for pick in expected})
    assert expected_known == [row for row in known if row[10:12] == b"\1\0"]


@pytest.mark.parametrize("sr", (False, True))
@pytest.mark.parametrize("game_type", ("bg2ee", "eet"))
def test_public_install_spell_lists_preservation_and_exact_uninstall(tmp_path, sr, game_type):
    game, resolved = make_game(tmp_path, sr=sr, game_type=game_type)
    result, transcript = run(game)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    after = _file_tree(game.root)
    changed = {name for name in set(after) | set(game.before)
               if after.get(name) != game.before.get(name) and not _is_weidu_artifact(name)}
    assert changed == {"OVERRIDE/RH#EVA.CRE", "OVERRIDE/RH#EV25.CRE"}
    for name in ("RH#EVA", "RH#EV25"):
        assert_conversion(game.before[f"OVERRIDE/{name}.CRE"], after[f"OVERRIDE/{name}.CRE"], resolved)
    result, transcript = run(game, uninstall=True)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY REMOVED" in transcript
    assert_restored(game)


@pytest.mark.parametrize("shuffled,v1_effects,levels,changed_rules", (
    (True, False, (10, 14), False), (True, True, (10, 14), False),
    (False, False, (6, 18), False), (False, False, (10, 14), True),
))
def test_installed_progression_and_independent_block_layout(
    tmp_path, shuffled, v1_effects, levels, changed_rules,
):
    game, resolved = make_game(tmp_path, shuffled=shuffled, v1_effects=v1_effects,
                               levels=levels, changed_rules=changed_rules)
    result, transcript = run(game)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    for name in ("rh#eva", "rh#ev25"):
        assert_conversion(game.before[f"OVERRIDE/{name.upper()}.CRE"],
                          (game.override / f"{name}.cre").read_bytes(), resolved,
                          changed_rules=changed_rules)
    installed = _file_tree(game.override)
    result, transcript = run(game, twice=True)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    assert installed == _file_tree(game.override)


@pytest.mark.parametrize("missing", ("splsrckn.2da", "mxsplsrc.2da", "spwi162.spl", "spwi761.spl"))
def test_missing_required_resources_leave_game_unchanged(tmp_path, missing):
    game, _ = make_game(tmp_path)
    path = game.override / missing
    assert path.exists()
    path.unlink()
    game.before = _file_tree(game.root)
    _, transcript = run(game)
    assert "SUCCESSFULLY INSTALLED" not in transcript
    assert "NOT INSTALLED DUE TO ERRORS" in transcript
    assert_restored(game)


@pytest.mark.parametrize("defect", ("hidden", "removed", "type", "level", "duplicate", "bad-cre", "missing-row", "hidden-default", "hidden-heading"))
def test_invalid_spell_or_late_creature_rolls_back(tmp_path, defect):
    game, _ = make_game(tmp_path)
    if defect in ("hidden", "removed"):
        path = game.override / "hidespl.2da"
        with path.open("a") as stream:
            stream.write(f"SPWI161 {1 if defect == 'removed' else 0} 0 {1 if defect == 'hidden' else 0}\n")
    elif defect in ("hidden-default", "hidden-heading"):
        path = game.override / "hidespl.2da"
        contents = path.read_text()
        contents = contents.replace("\n0\n", "\n1\n", 1) if defect == "hidden-default" else contents.replace("IS_HIDDEN", "UNRECOGNIZED")
        path.write_text(contents)
    elif defect in ("type", "level"):
        path = game.override / "spwi161.spl"
        blob = bytearray(path.read_bytes())
        struct.pack_into("<H" if defect == "type" else "<I", blob,
                         0x1C if defect == "type" else 0x34, 2)
        path.write_bytes(blob)
    elif defect == "duplicate":
        path = game.override / "spell.ids"
        path.write_text(path.read_text().replace("2162 WIZARD_DIMENSION_JUMP", "2161 WIZARD_DIMENSION_JUMP"))
    else:
        path = game.override / "rh#ev25.cre"
        blob = bytearray(path.read_bytes())
        if defect == "bad-cre":
            struct.pack_into("<I", blob, 0x2B0, len(blob) + 8)
        else:
            blob[0x234] = 11
        path.write_bytes(blob)
    game.before = _file_tree(game.root)
    _, transcript = run(game)
    assert "SUCCESSFULLY INSTALLED" not in transcript
    assert "NOT INSTALLED DUE TO ERRORS" in transcript
    assert "Evandra:" in transcript
    assert_restored(game)


@pytest.mark.parametrize("zero_offsets", (False, True))
@pytest.mark.parametrize("incoming_kit", (0, KIT_ID << 16))
def test_empty_spell_sections_and_already_trueclass_are_supported(tmp_path, zero_offsets, incoming_kit):
    game, resolved = make_game(tmp_path)
    for name in ("rh#eva", "rh#ev25"):
        path = game.override / f"{name}.cre"
        original = path.read_bytes()
        header = bytearray(original[:0x2D4])
        struct.pack_into("<I", header, 0x244, incoming_kit)
        body = bytearray()
        for pointer, stride in ((0x2B8, 80), (0x2BC, 20), (0x2C4, 0x108)):
            if pointer == 0x2B8:
                start = u32(original, pointer)
                payload = original[start:start + 80]
            else:
                payload = b"".join(records(original, pointer, stride))
            struct.pack_into("<I", header, pointer, 0x2D4 + len(body))
            body.extend(payload)
        for pointer in (0x2A0, 0x2A8, 0x2B0):
            struct.pack_into("<II", header, pointer, 0 if zero_offsets else 0x2D4, 0)
        path.write_bytes(header + body)
    game.before = _file_tree(game.root)
    result, transcript = run(game)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    for name in ("rh#eva", "rh#ev25"):
        before = game.before[f"OVERRIDE/{name.upper()}.CRE"]
        after = (game.override / f"{name}.cre").read_bytes()
        assert after[0x234:0x237] == before[0x234:0x237]
        assert after[0x18:0x1C] == before[0x18:0x1C]
        assert records(before, 0x2BC, 20) == records(after, 0x2BC, 20)
        assert records(before, 0x2C4, 0x108) == records(after, 0x2C4, 0x108)
        expected = [struct.pack("<8sHH", pick.encode(), index, 1)
                    for index, picks in enumerate(resolved)
                    for pick in picks[:KNOWN[before[0x234]][index]]]
        assert records(after, 0x2A0, 12) == expected
    installed = _file_tree(game.override)
    result, transcript = run(game, twice=True)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    assert installed == _file_tree(game.override)
