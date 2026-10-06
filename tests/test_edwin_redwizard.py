"""Public Edwin correction, exercised with authored fixtures and real WeiDU.

No game launch or licensed game data is used. CRE/ITM effects include unrelated
sentinels to catch overly broad patches; uninstall must restore the whole tree.
"""
from __future__ import annotations

import struct

import pytest

from tests.test_baeloth_spellbook import game_files, records, run, u32
from tests.test_utility_xp_installer import SyntheticGame, WEIDU

pytestmark = pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
COMPONENT = 236
KIT_ID = 0x40A7  # Deliberately not the captured live kit number.
TARGETS = ("EDWIN", "EDWIN2", "EDWIN4", "EDWIN6", "EDWIN7", "EDWIN7_",
           "EDWIN9", "EDWIN11", "EDWIN12", "EDWIN13", "EDWIN15")
FORBIDDEN = ("SPWI120", "SPWI106", "SPWI212", "SPWI201", "SPWI307", "SPWI405", "SPWI505")


def effect(opcode=42, p1=2, p2=1, timing=9, *, version=1, parent="", parent_type=0):
    value = bytearray(264 if version else 48)
    if version:
        struct.pack_into("<IIIIII", value, 8, opcode, 1, 0, p1, p2, timing)
        struct.pack_into("<I", value, 0x88, parent_type)
        value[0x8C:0x94] = parent.encode().ljust(8, b"\0")
        value[0xA8:0xB0] = b"SENTINEL"  # Unrelated metadata must remain exact.
    else:
        struct.pack_into("<HBBII", value, 0, opcode, 1, 0, p1, p2)
        value[12] = timing
        value[0x14:0x1C] = b"PAYLOAD\0"
    return bytes(value)


def make_cre(*, kit=KIT_ID << 16, version=1, shuffled=False, hp=1):
    header = bytearray((index * 17 + 9) % 256 for index in range(0x2D4))
    header[:8] = b"CRE V1.0"
    header[0x33] = version
    struct.pack_into("<HH", header, 0x24, hp, 75)
    struct.pack_into("<I", header, 0x244, kit)
    header[0x273] = 1
    header[0x280:0x2A0] = b"Edwin".ljust(32, b"\0")
    known = b"".join(struct.pack("<8sHH", name.encode(), 0, 1)
                     for name in (*FORBIDDEN, "KEEPWIZ"))
    known += struct.pack("<8sHH", b"PERSONAL", 0, 2)
    memorized = b"".join(struct.pack("<8sI", name.encode(), index % 2)
                        for index, name in enumerate((*FORBIDDEN, "KEEPWIZ", "PERSONAL")))
    groups = struct.pack("<HHHHII", 0, 9, 10, 1, 0, 8)
    groups += struct.pack("<HHHHII", 0, 1, 1, 2, 8, 1)
    effects = [effect(p2=1 << level, version=version) for level in range(9)]
    effects += [effect(142, 2, 1, version=version), effect(p1=1, version=version),
                effect(p2=3, version=version), effect(timing=0, version=version)]
    if version:
        effects += [effect(parent="FOREIGN", parent_type=1), effect(parent="KITFX")]
    items = b"".join(struct.pack("<8sHHHHI", name, 4, 1, 2, 3, flags)
                     for name, flags in ((b"MISC89", 9), (b"MISC89_", 10), (b"OTHER", 15)))
    slots = struct.pack("<40H", *([0xFFFF] * 6 + [0] + [0xFFFF] * 14 + [1, 2]
                                 + [0xFFFF] * 15 + [1000, 3]))
    blocks = {0x2A0: (known, 9), 0x2A8: (groups, 2), 0x2B0: (memorized, 9),
              0x2B8: (slots, None), 0x2BC: (items, 3), 0x2C4: (b"".join(effects), len(effects))}
    order = (0x2C4, 0x2B0, 0x2BC, 0x2B8, 0x2A8, 0x2A0) if shuffled else tuple(blocks)
    body = bytearray()
    for pointer in order:
        payload, count = blocks[pointer]
        struct.pack_into("<I", header, pointer, len(header) + len(body))
        if count is not None:
            struct.pack_into("<I", header, pointer + 4, count)
        body.extend(payload)
    return bytes(header + body)


def make_item(*, slots=True):
    header = bytearray(0x72)
    header[:8] = b"ITM V1  "
    struct.pack_into("<I", header, 0x18, 0x68 | 16)
    struct.pack_into("<I", header, 0x64, 0x72)
    struct.pack_into("<H", header, 0x68, 1)
    struct.pack_into("<IHH", header, 0x6A, 0xAA, 1, 10 if slots else 1)
    ability = bytearray(0x38)
    struct.pack_into("<HH", ability, 0x1E, 1, 0)
    # Ability slot effect is deliberately outside the equipped slice.
    effects = [effect(p1=4, version=0)]
    if slots:
        effects += [effect(p1=1, p2=1 << level, version=0) for level in range(9)]
    effects += [effect(142, version=0)]
    return bytes(header + ability + b"".join(effects))


def make_game(tmp_path, *, version=1, shuffled=False, prerequisite=True, sr60=False):
    game = SyntheticGame(tmp_path / "game", game="eet", eeex=False)
    (game.override / "kit.ids").write_text(f"IDS V1.0\n0x{KIT_ID:X} C0REDWIZ\n")
    (game.override / "c0redwiz.2da").write_bytes(
        b"2DA V1.0\r\n****\r\n 1 2 3 4 5\r\n"
        b"ABILITY1 AP_C0REDW **** **** **** ****\r\n"
        b"ABILITY2 AP_C0REDW2 **** **** AP_C0REDW2 ****\r\n"
    )
    log = "~ARTISANSKITPACK_NPC/ARTISANSKITPACK_NPC.TP2~ #0 #5102 // fixture\n" if prerequisite else ""
    if sr60:
        log += "~SPELL_REV/SETUP-SPELL_REV.TP2~ #0 #60 // fixture\n"
    (game.root / "weidu.log").write_text(log)
    for index, name in enumerate(TARGETS):
        (game.override / f"{name.lower()}.cre").write_bytes(make_cre(
            kit=0x80 if name == "EDWIN7_" else KIT_ID << 16,
            version=version, shuffled=shuffled, hp=index,
        ))
    (game.override / "other.cre").write_bytes(make_cre(version=version))
    (game.override / "misc89.itm").write_bytes(make_item())
    (game.override / "misc89_.itm").write_bytes(make_item(slots=False))
    game.before = game_files(game)
    return game


def neutralize(record, version):
    result = bytearray(record)
    fields = ((8, "I"), (20, "I"), (24, "I"), (28, "I"), (36, "I")) if version else (
        (0, "H"), (4, "I"), (8, "I"), (12, "B"), (14, "I"))
    for offset, kind in fields:
        struct.pack_into("<" + kind, result, offset, 0)
    return bytes(result)


def assert_cre(before, after, *, missing_kit=False):
    version = before[0x33]
    allowed = {byte for pointer in (0x244, 0x2A0, 0x2A4, 0x2A8, 0x2B0, 0x2B4,
                                    0x2B8, 0x2BC, 0x2C4) for byte in range(pointer, pointer + 4)}
    assert all(old == new or offset in allowed
               for offset, (old, new) in enumerate(zip(before[:0x2D4], after[:0x2D4])))
    assert u32(after, 0x244) == KIT_ID << 16
    effects = records(before, 0x2C4, 264 if version else 48)
    assert records(after, 0x2C4, 264 if version else 48) == [
        neutralize(row, version) if index < 9 else row for index, row in enumerate(effects)
    ]
    expected_items = records(before, 0x2BC, 20)
    for index in (0, 1):
        value = bytearray(expected_items[index])
        struct.pack_into("<I", value, 16, u32(value, 16) & ~8)
        expected_items[index] = bytes(value)
    assert records(after, 0x2BC, 20) == expected_items
    assert before[u32(before, 0x2B8):u32(before, 0x2B8) + 80] == after[u32(after, 0x2B8):u32(after, 0x2B8) + 80]
    for pointer in (0x2A0, 0x2B0):
        expected = records(before, pointer, 12)
        if missing_kit:
            expected = [row for row in expected if row[:8].rstrip(b"\0").decode() not in FORBIDDEN]
        assert records(after, pointer, 12) == expected
    # Slot maxima/readiness are not rewritten by this template repair.
    assert [row[:8] for row in records(before, 0x2A8, 16)] == [row[:8] for row in records(after, 0x2A8, 16)]


def assert_grant(data):
    assert data[:8] == b"SPL V1  " and len(data) == 0x24A
    assert struct.unpack_from("<H", data, 0x68)[0] == 1
    base = u32(data, 0x6A)
    assert struct.unpack_from("<HH", data, 0x90) == (9, 0)
    for level in range(9):
        effect = data[base + level * 48:base + (level + 1) * 48]
        assert struct.unpack_from("<HBBII", effect) == (42, 1, 0, 1, 1 << level)
        assert effect[12] == 9 and effect[18] == 100


def assert_success(game, *, uninstall=True):
    result, transcript = run(game, component=COMPONENT)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in transcript, transcript
    after = game_files(game)
    expected = dict(game.before)
    for name in TARGETS:
        key = f"OVERRIDE/{name}.CRE"
        if key not in game.before:
            continue
        # An intentionally different selected kit remains outside this repair.
        if u32(game.before[key], 0x244) not in (KIT_ID << 16, 0x80):
            assert after[key] == game.before[key]
        else:
            assert_cre(game.before[key], after[key], missing_kit=name == "EDWIN7_" and u32(game.before[key], 0x244) == 0x80)
        expected[key] = after[key]
    for name in ("MISC89", "MISC89_"):
        key = f"OVERRIDE/{name}.ITM"
        if key not in game.before:
            continue
        value = bytearray(game.before[key])
        struct.pack_into("<I", value, 0x18, (u32(value, 0x18) | 4) & ~16)
        base = u32(value, 0x6A)
        for index in range(1, 10 if name == "MISC89" else 1):
            start = base + index * 48
            value[start:start + 48] = neutralize(value[start:start + 48], 0)
        assert after[key] == bytes(value)
        expected[key] = bytes(value)
    clab = after["OVERRIDE/C0REDWIZ.2DA"]
    assert clab.startswith(game.before["OVERRIDE/C0REDWIZ.2DA"])
    grants = [row.split() for row in clab.decode().splitlines() if "AP_CBMEDSL" in row]
    assert grants == [["CBMEDSLOT", "AP_CBMEDSL", "****", "****", "****", "****"]]
    expected["OVERRIDE/C0REDWIZ.2DA"] = clab
    assert_grant(after["OVERRIDE/CBMEDSL.SPL"])
    expected["OVERRIDE/CBMEDSL.SPL"] = after["OVERRIDE/CBMEDSL.SPL"]
    assert after == expected
    if uninstall:
        result, transcript = run(game, component=COMPONENT, uninstall=True)
        assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in transcript, transcript
        assert game_files(game) == game.before
    return after


@pytest.mark.parametrize("version,shuffled", ((0, False), (1, False), (0, True), (1, True)))
def test_all_templates_indexed_layouts_exact_scope_and_uninstall(tmp_path, version, shuffled):
    assert_success(make_game(tmp_path, version=version, shuffled=shuffled))


def test_second_application_is_byte_identical_and_does_not_double_grants(tmp_path):
    game = make_game(tmp_path)
    after = assert_success(game)
    for name, payload in after.items():
        if name.startswith("OVERRIDE/"):
            (game.override / name.split("/", 1)[1].lower()).write_bytes(payload)
    game.before = game_files(game)
    assert assert_success(game) == after


@pytest.mark.parametrize("kit", (0x41710000, 0x40000000))
def test_explicit_other_edwin_kit_is_preserved(tmp_path, kit):
    game = make_game(tmp_path)
    for name in ("edwin7_", "edwin12"):
        (game.override / f"{name}.cre").write_bytes(make_cre(kit=kit))
    game.before = game_files(game)
    assert_success(game)


def test_partial_game_without_eet_variants(tmp_path):
    game = make_game(tmp_path)
    (game.override / "edwin7_.cre").unlink()
    (game.override / "misc89_.itm").unlink()
    game.before = game_files(game)
    assert_success(game)


@pytest.mark.parametrize("prerequisite,sr60", ((False, False), (True, True)))
def test_missing_conversion_or_wrong_order_is_skipped_without_mutation(tmp_path, prerequisite, sr60):
    game = make_game(tmp_path, prerequisite=prerequisite, sr60=sr60)
    result, transcript = run(game, component=COMPONENT)
    assert "SKIPPING:" in transcript and "SUCCESSFULLY INSTALLED" not in transcript
    assert game_files(game) == game.before


@pytest.mark.parametrize("defect", ("legacy-grant", "foreign-grant", "bad-cre", "bad-effects",
                                  "bad-inventory", "bad-item", "duplicate-clab", "late-clab"))
def test_bad_inputs_rollback_the_entire_component(tmp_path, defect):
    game = make_game(tmp_path)
    if defect in ("legacy-grant", "foreign-grant"):
        name = "c0redw4" if defect == "legacy-grant" else "cbmedsl"
        (game.override / f"{name}.spl").write_bytes(b"unrelated resource")
    elif defect in ("duplicate-clab", "late-clab"):
        path = game.override / "c0redwiz.2da"
        path.write_text(path.read_text() + ("ROW AP_CBMEDSL AP_CBMEDSL **** **** ****\n"
                                           if defect == "duplicate-clab" else
                                           "ROW **** AP_CBMEDSL **** **** ****\n"))
    else:
        path = game.override / ("misc89_.itm" if defect == "bad-item" else "edwin15.cre")
        data = bytearray(path.read_bytes())
        if defect == "bad-cre":
            data[:8] = b"BAD V1.0"
        else:
            field = {"bad-effects": 0x2C4, "bad-inventory": 0x2BC, "bad-item": 0x6A}[defect]
            struct.pack_into("<I", data, field, len(data) + 1)
        path.write_bytes(data)
    game.before = game_files(game)
    result, transcript = run(game, component=COMPONENT)
    assert result.returncode != 0 and "NOT INSTALLED DUE TO ERRORS" in transcript, transcript
    assert "cbm_edwin" in transcript
    assert game_files(game) == game.before
