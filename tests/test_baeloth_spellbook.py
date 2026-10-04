"""Baeloth known-spell normalization with real WeiDU and authored game fixtures.

These tests do not load the engine or touch a real game or save. Recruitment and
level-up assertions below are a spellbook/allowance model, not live acceptance.
"""

from __future__ import annotations

from collections import Counter
import struct
import subprocess

import pytest

from tests.test_utility_xp_installer import (
    SETUP_NAME, WEIDU, SyntheticGame, _file_tree, _is_weidu_artifact,
)


pytestmark = pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
COMPONENT = 235
SORCERER = 29  # Deliberately relocated CLASS.IDS symbol.
TARGETS = ("BAELOTH", "BAELOT7")
CURRENT = (
    ("SPOOK", "SHIELD", "MAGIC_MISSILE", "LARLOCH_MINOR_DRAIN",
     "CHROMATIC_ORB", "IDENTIFY", "BURNING_HANDS"),
    ("WEB", "RAY_OF_ENFEEBLEMENT", "MIRROR_IMAGE", "MELF_ACID_ARROW",
     "DETECT_INVISIBILITY"),
    ("HASTE", "FIREBALL", "DISPEL_MAGIC", "DIRE_CHARM"),
)
TIER7_EXTRA = ("BLINDNESS", "HORROR", "SLOW")
ALLOWANCES = {
    6: (4, 2, 1, 0, 0, 0, 0, 0, 0),
    7: (5, 3, 2, 0, 0, 0, 0, 0, 0),
    10: (5, 4, 3, 2, 1, 0, 0, 0, 0),
}


def known(resref: str, level: int, kind: int = 1) -> bytes:
    return struct.pack("<8sHH", resref.encode("ascii"), level, kind)


def memo(resref: str, ready: int) -> bytes:
    return struct.pack("<8sI", resref.encode("ascii"), ready)


def resref(row: bytes) -> str:
    return row[:8].rstrip(b"\0").decode("ascii").upper()


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def records(data: bytes, pointer: int, stride: int) -> list[bytes]:
    start, count = struct.unpack_from("<II", data, pointer)
    return [data[start + i * stride:start + (i + 1) * stride] for i in range(count)]


def groups(data: bytes) -> list[tuple[bytes, list[bytes]]]:
    entries = records(data, 0x2B0, 12)
    result = []
    for info in records(data, 0x2A8, 16):
        start, count = struct.unpack_from("<II", info, 8)
        result.append((info[:8], entries[start:start + count]))
    return result


def wizard_known(data: bytes) -> Counter[tuple[str, int]]:
    return Counter((resref(row), struct.unpack_from("<H", row, 8)[0])
                   for row in records(data, 0x2A0, 12) if row[10:12] == b"\1\0")


def picks(spells: dict[str, str], sr: bool, allowance: tuple[int, ...]) -> list[tuple[str, ...]]:
    priorities = (
        ("MAGIC_MISSILE", "SHIELD", "SPOOK", "CHROMATIC_ORB",
         "IDENTIFY" if sr else "BLINDNESS"),
        ("MIRROR_IMAGE", "WEB", "MELF_ACID_ARROW"),
        ("FIREBALL", "HASTE"),
    )
    return [tuple(spells[name] for name in pool[:allowance[level]])
            for level, pool in enumerate(priorities)] + [()] * 6


def make_cre(
    spells: dict[str, str], *, recruitment_tier=6, level=None, hp=1,
    shuffled=False, reordered=False, v1_effects=False, known_state="current",
    missing_vector=None, empty_group=None, missing_group=None,
) -> bytes:
    header = bytearray((index * 13 + 7) % 256 for index in range(0x2D4))
    header[:8] = b"CRE V1.0"
    header[0x33] = 0 if v1_effects else 1
    struct.pack_into("<I", header, 0x18, 50_001 if recruitment_tier == 6 else 99_999)
    struct.pack_into("<HH", header, 0x24, hp, 63)
    header[0x234:0x237] = bytes((level or recruitment_tier, 0, 0))
    struct.pack_into("<I", header, 0x244, 0x57310000)
    header[0x273] = SORCERER
    header[0x280:0x2A0] = b"BAELOTH".ljust(32, b"\0")
    for offset, script in ((0x248, b"BAELOTH"), (0x250, b"BAELREJ"),
                           (0x258, b"BAELLEV"), (0x260, b"CUSTOM"), (0x268, b"OTHER")):
        header[offset:offset + 8] = script.ljust(8, b"\0")

    original = [list(row) for row in CURRENT]
    if recruitment_tier == 7:
        for names, extra in zip(original, TIER7_EXTRA):
            names.append(extra)
    wizard_rows = [known(spells[name], level)
                   for level, names in enumerate(original) for name in names]
    if known_state == "duplicates":
        wizard_rows += [known(spells["MAGIC_MISSILE"], 0)] * 2
    elif known_state == "missing":
        wizard_rows = [row for row in wizard_rows if resref(row) != spells["MAGIC_MISSILE"]]
    elif known_state == "none":
        wizard_rows = []
    personal_rows = [known("PERSONAL", 0, 2), known("PRIEST", 2, 0),
                     known(spells["MAGIC_MISSILE"], 0, 2)]
    known_rows = [personal_rows[0], *wizard_rows[:3], personal_rows[1],
                  *wizard_rows[3:], personal_rows[2]]

    daily_slots = (6, 5, 3) if recruitment_tier == 6 else (6, 6, 4)
    wizard_groups = []
    for spell_level, names in enumerate(original):
        if missing_group == spell_level:
            continue
        maximum = daily_slots[spell_level]
        entries = []
        for index, name in enumerate(names):
            if missing_vector == name:
                continue
            # Existing selections have different spent states. The final spell
            # has one fewer copy, exercising conservative missing-vector repair.
            total = maximum - (1 if index == len(names) - 1 else 0)
            ready = max(0, total - index % 3)
            entries += [memo(spells[name], int(copy < ready)) for copy in range(total)]
        if empty_group == spell_level:
            entries = []
        wizard_groups.append((spell_level, maximum, maximum, 1, entries))
    spell_groups = [
        (0, 2, 3, 2, [memo("PERSONAL", 0), memo("PERSONAL", 1)]),
        *wizard_groups[:1],
        (2, 4, 5, 0, [memo("PRIEST", 0), memo("PRIEST", 1)]),
        *wizard_groups[1:],
        (3, 0, 3, 1, []),  # Baeloth's existing unused fourth-level 0/3 group.
        (0, 1, 2, 2, [memo(spells["MAGIC_MISSILE"], 1)]),
    ]
    if reordered:
        known_rows.reverse()
        spell_groups.reverse()
        spell_groups = [(*group[:4], list(reversed(group[4]))) for group in spell_groups]
    memorization = bytearray()
    memorized = bytearray()
    for spell_level, base, maximum, kind, entries in spell_groups:
        memorization.extend(struct.pack("<HHHHII", spell_level, base, maximum, kind,
                                        len(memorized) // 12, len(entries)))
        memorized.extend(b"".join(entries))

    effects = []
    for index, opcode in enumerate((142, 233, 42, 171)):
        effect = bytearray(0x30 if v1_effects else 0x108)
        if v1_effects:
            struct.pack_into("<HBBII", effect, 0, opcode, 1, 0, index + 2, 105)
            effect[0x14:0x1C] = b"RACIAL".ljust(8, b"\0")
        else:
            struct.pack_into("<IIIIII", effect, 8, opcode, 1, 0, index + 2, 105, 9)
            effect[0x8C:0x94] = b"RACIAL".ljust(8, b"\0")
        effects.append(bytes(effect))
    slots = struct.pack("<40H", *([0xFFFF] * 21 + [0] + [0xFFFF] * 16 + [1000, 3]))
    blocks = {
        0x2A0: (b"".join(known_rows), len(known_rows)),
        0x2A8: (bytes(memorization), len(spell_groups)),
        0x2B0: (bytes(memorized), len(memorized) // 12),
        0x2B8: (slots, None),
        0x2BC: (struct.pack("<8sHHHHI", b"BAELITEM", 1, 2, 3, 4, 9), 1),
        0x2C4: (b"".join(effects), len(effects)),
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


def write_allowances(path, budgets, *, columns=9):
    text = "2DA V1.0\n0\n " + " ".join(map(str, reversed(range(1, columns + 1)))) + "\n"
    for level, values in reversed(tuple(budgets.items())):
        text += f"{level} " + " ".join(map(str, reversed(values[:columns]))) + "\n"
    path.write_text(text, encoding="ascii")


def make_game(tmp_path, *, sr=False, sr_marker="marker", budgets=None, levels=(6, 7), **cre_options):
    game = SyntheticGame(tmp_path / "game", game="eet", eeex=False)
    ov = game.override
    (ov / "class.ids").write_text(f"IDS V1.0\n{SORCERER} SORCERER\n1 MAGE\n")
    (ov / "hidespl.2da").write_text("2DA V1.0\n0\n IS_REMOVED IS_FINAL IS_HIDDEN\n")
    write_allowances(ov / "splsrckn.2da", budgets or ALLOWANCES)
    spells = {}
    symbols = "IDS V1.0\n"
    for spell_level, names in enumerate(CURRENT, 1):
        for index, name in enumerate((*names, TIER7_EXTRA[spell_level - 1]), 1):
            slot = 100 * spell_level + 60 + index
            if sr and name == "BLINDNESS":
                slot = 106  # SR keeps the old alias while this spell is Obscuring Mist.
            spells[name] = f"SPWI{slot}"
            symbols += f"{2000 + slot} WIZARD_{name}\n"
            spell = bytearray(0x72)
            spell[:8] = b"SPL V1  "
            struct.pack_into("<H", spell, 0x1C, 1)
            struct.pack_into("<I", spell, 0x34, spell_level)
            (ov / f"spwi{slot}.spl").write_bytes(spell)
    (ov / "spell.ids").write_text(symbols)
    if sr:
        if sr_marker == "marker":
            (ov / "dvimhere.mrk").write_bytes(b"synthetic Spell Revisions marker")
        else:
            (game.root / "WeiDU.log").write_text("~SPELL_REV/SPELL_REV.TP2~ #0 #0 // SR fixture\n")
    for index, name in enumerate(TARGETS):
        (ov / f"{name.lower()}.cre").write_bytes(make_cre(
            spells, recruitment_tier=6 + index, level=levels[index], hp=index,
            **cre_options,
        ))
    for name in ("BAELOTX", "OTHER"):
        (ov / f"{name.lower()}.cre").write_bytes(make_cre(spells))
    for name in ("baeloth", "baelrej", "baellev"):
        (ov / f"{name}.bcs").write_bytes(b"authored recruitment/rejoin script sentinel\0\xff")
    game.before = game_files(game)
    return game, spells


def game_files(game):
    return {name: data for name, data in _file_tree(game.root).items()
            if not _is_weidu_artifact(name)}


def run(game, *, uninstall=False, setup=SETUP_NAME, component=COMPONENT):
    result = subprocess.run(
        [str(WEIDU), setup, "--noautoupdate", "--no-auto-tp2", "--no-exit-pause",
         "--game", str(game.root), "--use-lang", "en_us", "--language", "0",
         "--force-uninstall-list" if uninstall else "--force-install-list", str(component)],
        cwd=game.root, capture_output=True, text=True, timeout=60,
    )
    return result, result.stdout + result.stderr


def assert_preserved(before, after, selected):
    allowed = {byte for field in (0x2A0, 0x2A4, 0x2A8, 0x2AC, 0x2B0, 0x2B4,
                                  0x2B8, 0x2BC, 0x2C4) for byte in range(field, field + 4)}
    assert bytes(value for index, value in enumerate(before[:0x2D4]) if index not in allowed) == bytes(
        value for index, value in enumerate(after[:0x2D4]) if index not in allowed
    )
    assert wizard_known(after) == Counter((name, level) for level, names in enumerate(selected) for name in names)
    assert [row for row in records(before, 0x2A0, 12) if row[10:12] != b"\1\0"] == [
        row for row in records(after, 0x2A0, 12) if row[10:12] != b"\1\0"
    ]
    for pointer, stride in ((0x2BC, 20), (0x2C4, 0x108 if before[0x33] else 0x30)):
        assert records(before, pointer, stride) == records(after, pointer, stride)
    old_slots, new_slots = u32(before, 0x2B8), u32(after, 0x2B8)
    assert before[old_slots:old_slots + 80] == after[new_slots:new_slots + 80]
    old_groups, new_groups = groups(before), groups(after)
    assert [info for info, _ in old_groups] == [info for info, _ in new_groups]
    for (info, original), (_, updated) in zip(old_groups, new_groups):
        level, _, maximum, kind = struct.unpack("<HHHH", info)
        if kind != 1:
            assert original == updated
            continue
        assert all(resref(row) in selected[level] for row in updated)
        existing = {resref(row) for row in original}
        for name in selected[level]:
            expected = [row for row in original if resref(row) == name]
            if name not in existing and original:
                totals = Counter(resref(row) for row in original)
                ready = {key: sum(bool(u32(row, 8) & 1) for row in original if resref(row) == key)
                         for key in existing}
                total = min(min(totals.values()), maximum)
                available = min(min(ready.values()), total)
                expected = [memo(name, int(index < available)) for index in range(total)]
            assert expected == [row for row in updated if resref(row) == name]


def assert_success(game, spells, *, sr=False, budgets=None, uninstall=True):
    budgets = budgets or ALLOWANCES
    result, transcript = run(game)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    after = game_files(game)
    expected = dict(game.before)
    for name in TARGETS:
        key = f"OVERRIDE/{name}.CRE"
        if key not in game.before:
            continue
        original = game.before[key]
        assert_preserved(original, after[key], picks(spells, sr, budgets[original[0x234]]))
        expected[key] = after[key]
    assert expected == after
    if uninstall:
        result, transcript = run(game, uninstall=True)
        assert result.returncode == 0, transcript
        assert "SUCCESSFULLY REMOVED" in transcript
        assert game.before == game_files(game)
    return after


@pytest.mark.parametrize("sr,sr_marker", ((False, "marker"), (True, "marker"), (True, "log")))
def test_current_books_become_authored_choices_with_exact_scope_and_uninstall(tmp_path, sr, sr_marker):
    game, spells = make_game(tmp_path, sr=sr, sr_marker=sr_marker)
    for name, counts in zip(TARGETS, ((7, 5, 4), (8, 6, 5))):
        current = wizard_known(game.before[f"OVERRIDE/{name}.CRE"])
        assert tuple(sum(count for (_, level), count in current.items() if level == tier)
                     for tier in range(3)) == counts
    after = assert_success(game, spells, sr=sr)
    tier7 = wizard_known(after["OVERRIDE/BAELOT7.CRE"])
    assert (spells["IDENTIFY" if sr else "BLINDNESS"], 0) in tier7
    assert (spells["BLINDNESS" if sr else "IDENTIFY"], 0) not in tier7


@pytest.mark.parametrize("shuffled,reordered,v1_effects,known_state", (
    (True, False, False, "current"), (True, True, False, "current"),
    (True, True, True, "duplicates"), (False, True, False, "missing"),
    (False, False, False, "none"),
))
def test_layout_order_duplicates_and_missing_known_records_are_supported(
    tmp_path, shuffled, reordered, v1_effects, known_state,
):
    game, spells = make_game(tmp_path, sr=True, shuffled=shuffled, reordered=reordered,
                             v1_effects=v1_effects, known_state=known_state)
    normalized = assert_success(game, spells, sr=True)
    # A second public install starts from already-normalized CREs, not a WeiDU
    # no-op for an already-installed component or a restore of original bytes.
    for name in TARGETS:
        (game.override / f"{name.lower()}.cre").write_bytes(normalized[f"OVERRIDE/{name}.CRE"])
    game.before = game_files(game)
    assert assert_success(game, spells, sr=True) == normalized


@pytest.mark.parametrize("options", (
    {"missing_vector": "FIREBALL"}, {"empty_group": 2}, {"missing_group": 2},
))
def test_missing_spell_vectors_do_not_create_free_casts_or_new_slot_groups(tmp_path, options):
    game, spells = make_game(tmp_path, **options)
    assert_success(game, spells)


@pytest.mark.parametrize("budgets,levels", (
    ({**ALLOWANCES, 6: (2, 1, 0, 0, 0, 0, 0, 0, 0)}, (6, 7)),
    ({**ALLOWANCES, 6: (7, 6, 5, 2, 0, 0, 0, 0, 0)}, (6, 7)),
    (ALLOWANCES, (10, 10)),
))
def test_installed_allowance_and_custom_levels_cap_the_authored_pool(tmp_path, budgets, levels):
    game, spells = make_game(tmp_path, budgets=budgets, levels=levels)
    assert_success(game, spells, budgets=budgets)


@pytest.mark.parametrize("columns,large_budget", ((3, False), (9, True)))
def test_only_authored_columns_are_required_and_large_allowances_still_cap_picks(
    tmp_path, columns, large_budget,
):
    budgets = {
        level: (1_000_000, 1_000_000, 1_000_000, *values[3:]) if large_budget else values
        for level, values in ALLOWANCES.items()
    }
    game, spells = make_game(tmp_path, budgets=budgets)
    write_allowances(game.override / "splsrckn.2da", budgets, columns=columns)
    game.before = game_files(game)
    assert_success(game, spells, budgets=budgets)


@pytest.mark.parametrize("empty_all_spell_blocks", (False, True))
@pytest.mark.parametrize("stale_pointer", ("inside-effects", "beyond-eof"))
def test_empty_spell_blocks_ignore_unused_stale_offsets_and_remain_stable(
    tmp_path, empty_all_spell_blocks, stale_pointer,
):
    game, spells = make_game(tmp_path, shuffled=True)
    for name in TARGETS:
        path = game.override / f"{name.lower()}.cre"
        creature = bytearray(path.read_bytes())
        unused = u32(creature, 0x2C4) + 24 if stale_pointer == "inside-effects" else len(creature) + 4096
        # A zero count makes its offset unused, even when it is stale. Keep the
        # now-unreferenced old payload in place; other indexed blocks stay valid.
        pointers = (0x2A0, 0x2A8, 0x2B0) if empty_all_spell_blocks else (0x2A0,)
        for pointer in pointers:
            struct.pack_into("<II", creature, pointer, unused, 0)
        path.write_bytes(creature)
    game.before = game_files(game)
    normalized = assert_success(game, spells)
    for name in TARGETS:
        (game.override / f"{name.lower()}.cre").write_bytes(normalized[f"OVERRIDE/{name}.CRE"])
    game.before = game_files(game)
    assert assert_success(game, spells) == normalized


@pytest.mark.parametrize("survivor", TARGETS)
def test_a_single_present_recruitment_variant_is_patched(tmp_path, survivor):
    game, spells = make_game(tmp_path)
    missing = next(name for name in TARGETS if name != survivor)
    (game.override / f"{missing.lower()}.cre").unlink()
    game.before = game_files(game)
    result, transcript = run(game)
    assert result.returncode in (0, 3), transcript
    assert "SUCCESSFULLY INSTALLED" in transcript or "INSTALLED WITH WARNINGS" in transcript
    assert "NOT INSTALLED DUE TO ERRORS" not in transcript
    assert "#235 " in game.active_log()
    assert f"{missing}.CRE" in transcript.upper()
    assert "warning" in transcript.lower()
    after = game_files(game)
    key = f"OVERRIDE/{survivor}.CRE"
    assert_preserved(game.before[key], after[key], picks(spells, False, ALLOWANCES[game.before[key][0x234]]))
    expected = dict(game.before)
    expected[key] = after[key]
    assert expected == after
    result, transcript = run(game, uninstall=True)
    assert result.returncode == 0, transcript
    assert game.before == game_files(game)


def test_absent_targets_are_reported_without_loading_spell_dependencies(tmp_path):
    game, _ = make_game(tmp_path)
    for name in ("baeloth.cre", "baelot7.cre", "class.ids", "spell.ids", "splsrckn.2da", "hidespl.2da"):
        (game.override / name).unlink()
    for path in game.override.glob("*.spl"):
        path.unlink()
    game.before = game_files(game)
    result, transcript = run(game)
    assert result.returncode in (0, 3), transcript
    assert "SUCCESSFULLY INSTALLED" in transcript or "INSTALLED WITH WARNINGS" in transcript
    assert "NOT INSTALLED DUE TO ERRORS" not in transcript
    assert "#235 " in game.active_log()
    assert "no resources changed" in transcript.lower()
    assert "ERROR locating resource" not in transcript
    assert game.before == game_files(game)


@pytest.mark.parametrize("defect", (
    "missing-spell", "spell-type", "spell-level", "hidden", "duplicate-resolution",
    "missing-allowance", "bad-signature", "short-header", "bad-block", "wrong-class",
))
def test_invalid_spell_rules_or_late_target_fail_with_complete_rollback(tmp_path, defect):
    game, spells = make_game(tmp_path)
    spell_path = game.override / f"{spells['FIREBALL'].lower()}.spl"
    if defect == "missing-spell":
        spell_path.unlink()
    elif defect in ("spell-type", "spell-level"):
        data = bytearray(spell_path.read_bytes())
        struct.pack_into("<H" if defect == "spell-type" else "<I", data,
                         0x1C if defect == "spell-type" else 0x34, 2)
        spell_path.write_bytes(data)
    elif defect == "hidden":
        (game.override / "hidespl.2da").write_text(
            f"2DA V1.0\n0\n IS_REMOVED IS_FINAL IS_HIDDEN\n{spells['FIREBALL']} 0 0 1\n"
        )
    elif defect == "duplicate-resolution":
        path = game.override / "spell.ids"
        path.write_text(path.read_text().replace("2162 WIZARD_SHIELD", "2163 WIZARD_SHIELD"))
    elif defect == "missing-allowance":
        write_allowances(game.override / "splsrckn.2da", {6: ALLOWANCES[6]})
    else:
        path = game.override / "baelot7.cre"
        data = bytearray(path.read_bytes())
        if defect == "bad-signature":
            data[:8] = b"BAD V1.0"
        elif defect == "short-header":
            data = data[:0x2D3]
        elif defect == "bad-block":
            struct.pack_into("<I", data, 0x2B0, len(data) + 8)
        else:
            data[0x273] = 1
        path.write_bytes(data)
    game.before = game_files(game)
    result, transcript = run(game)
    assert result.returncode != 0, transcript
    assert "NOT INSTALLED DUE TO ERRORS" in transcript
    assert "baeloth" in transcript.lower()
    assert game.before == game_files(game)


def test_an_earlier_npc_spellbook_writer_is_normalized_afterward(tmp_path):
    game, spells = make_game(tmp_path, sr=True)
    writer = game.root / "earlier-npc-spellbook-writer.tp2"
    writer.write_text(
        "BACKUP ~weidu_external/backup/earlier-npc-spellbook-writer~\nAUTHOR ~fixture~\n"
        "BEGIN ~Earlier NPC spellbook writer~ DESIGNATED 0\n"
        "COPY_EXISTING ~BAELOTH.CRE~ ~override~ ~BAELOT7.CRE~ ~override~\n"
        "  ADD_KNOWN_SPELL ~EXTRAWIZ~ #0 ~wizard~\n"
        "  ADD_KNOWN_SPELL ~MOREWIZ~ #1 ~wizard~\nBUT_ONLY\n"
    )
    result, transcript = run(game, setup=writer.name, component=0)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    for name in TARGETS:
        current = wizard_known((game.override / f"{name.lower()}.cre").read_bytes())
        assert ("EXTRAWIZ", 0) in current and ("MOREWIZ", 1) in current
    # The writer's debug log is fixture evidence, not a component235 publication.
    game.before = game_files(game)
    assert_success(game, spells, sr=True)


def test_recruitment_level7_choice_budget_remains_open_without_script_writers(tmp_path):
    game, spells = make_game(tmp_path)
    after = assert_success(game, spells)
    recruited = wizard_known(after["OVERRIDE/BAELOTH.CRE"])
    counts = tuple(sum(count for (_, level), count in recruited.items() if level == tier)
                   for tier in range(3))
    assert tuple(allowed - current for allowed, current in zip(ALLOWANCES[7], counts)) == (1, 1, 1)
    # Model legal player choices independently of the authored fresh-SoD preset.
    for level, choice in enumerate(("IDENTIFY", "DETECT_INVISIBILITY", "SLOW")):
        recruited[(spells[choice], level)] += 1
    assert tuple(sum(count for (_, level), count in recruited.items() if level == tier)
                 for tier in range(3)) == ALLOWANCES[7][:3]
    assert (spells["DETECT_INVISIBILITY"], 1) in recruited
    for name in ("BAELOTH", "BAELREJ", "BAELLEV"):
        assert game.before[f"OVERRIDE/{name}.BCS"] == after[f"OVERRIDE/{name}.BCS"]
