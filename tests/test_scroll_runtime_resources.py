"""Effective-resource inventory checks. No installer/game/save writes."""
import os
import hashlib
import importlib.util
from pathlib import Path
import runpy
import struct
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scroll_installed_resources", ROOT / "research/scroll-runtime/installed_resources.py")
resources = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = resources
spec.loader.exec_module(resources)


def effect(opcode, target=b"", mode=0, level=0):
    out = bytearray(48)
    struct.pack_into("<H", out, 0, opcode)
    struct.pack_into("<II", out, 4, level, mode)
    out[20:28] = target.ljust(8, b"\0")
    return bytes(out)


def resource(ext, kind, abilities, *, globals=(), effects_first=False):
    stride = 56 if ext == "ITM" else 40
    all_effects = list(globals) + [e for _, _, entries in abilities for e in entries]
    ao = 160 if not effects_first else 160 + len(all_effects) * 48 + 19
    fo = 160 if effects_first else ao + len(abilities) * stride + 19
    out = bytearray(max(ao + stride * len(abilities), fo + 48 * len(all_effects)) + 7)
    out[:8] = ext.encode() + b" V1  "
    struct.pack_into("<H", out, 28, kind)
    struct.pack_into("<IHIHH", out, 100, ao, len(abilities), fo, 0, len(globals))
    first = len(globals)
    for i, (atype, level, effects) in enumerate(abilities):
        at = ao + i * stride
        struct.pack_into("<H", out, at, atype)
        struct.pack_into("<H", out, at + 16, level)
        struct.pack_into("<HH", out, at + 30, len(effects), first)
        first += len(effects)
    for i, e in enumerate(all_effects):
        out[fo + i * 48:fo + (i + 1) * 48] = e
    return bytes(out)


def eff(opcode, target, *, mode=0, level=0):
    out = bytearray(0x110)
    out[:8] = b"EFF V2.0"
    struct.pack_into("<I", out, 16, opcode)
    struct.pack_into("<II", out, 28, level, mode)
    out[48:56] = target.ljust(8, b"\0")
    return bytes(out)


def inventory(data, **kwargs):
    return resources.Inventory(lambda n, e: data[n + "." + e], **kwargs)


@pytest.mark.parametrize("installed_type", [1, 2, 0, 3, 4])
@pytest.mark.parametrize("effects_first", [False, True])
def test_installed_identity_not_name_or_level(installed_type, effects_first):
    data = {"CDIA001.ITM": resource("ITM", 11, [(3, 0, [effect(141), effect(146, b"SPWI102", level=15)]),
                                                   (3, 0, [effect(147, b"SPWI102")])], effects_first=effects_first),
            "SPWI102.SPL": resource("SPL", installed_type, [(1, 1, [effect(12)]), (1, 17, [effect(12)])], effects_first=effects_first)}
    before = data.copy()
    result = inventory(data).item("cdia001")
    assert result[0].classification == ("typed_cast_candidate" if installed_type in (1, 2) else "native_only")
    assert result[0].spells["SPWI102"]["installed_type"] == installed_type
    assert result[0].spells["SPWI102"]["ability_levels"] == [1, 17]
    assert result[1].classification == "learning"
    assert data == before


def test_linked177_mixed_wrappers_multiple_dispatches_and_shared_child():
    data = {"SCROLL.ITM": resource("ITM", 11, [(3, 0, [effect(177, b"LINK"), effect(146, b"DIVINE")])]),
            "LINK.EFF": eff(148, b"WRAP", mode=2, level=10),
            "WRAP.SPL": resource("SPL", 4, [(1, 1, [effect(146, b"ARCANE"), effect(148, b"DIVINE")])]),
            "ARCANE.SPL": resource("SPL", 1, [(1, 1, [])]),
            "DIVINE.SPL": resource("SPL", 2, [(1, 1, [])])}
    report = inventory(data).item("SCROLL")[0]
    assert report.classification == "typed_cast_candidate"
    assert report.spells["WRAP"]["policy"] == "native_untyped"
    assert report.spells["ARCANE"]["policy"] == "arcane"
    assert report.spells["DIVINE"]["policy"] == "divine"
    assert len(report.edges) == 5
    assert not report.diagnostics


@pytest.mark.parametrize("mode", [0, 1, 2])
@pytest.mark.parametrize("opcode", [146, 148])
def test_all_native_modes_preserved_in_inventory(mode, opcode):
    report = inventory({"S.ITM": resource("ITM", 11, [(3, 0, [effect(opcode, b"A", mode, 23)])]),
                        "A.SPL": resource("SPL", 1, [(1, 1, [])])}).item("S")[0]
    assert report.edges[0]["parameter1"] == 23
    assert report.edges[0]["parameter2"] == mode
    assert report.classification == "typed_cast_candidate"


@pytest.mark.parametrize("op", [232, 272, 326])
def test_common_conditional_dispatch_resolves_actual_child(op):
    data={"S.ITM": resource("ITM", 11, [(3, 0, [effect(op, b"A")])]),
          "A.SPL": resource("SPL", 1, [(1, 1, [])])}
    if op==272:data['A.EFF']=eff(146,b'A')
    report=inventory(data).item('S')[0]
    assert report.classification=='typed_cast_candidate'
    assert report.edges[0]['opcode']==op
    assert report.spells['A']['installed_type']==1


def test_contingency_eff_secondary_slots_are_effective_dependencies():
    external=bytearray(eff(232,b'A'));external[0x70:0x78]=b'B\0\0\0\0\0\0\0'
    data={'S.ITM':resource('ITM',11,[(3,0,[effect(177,b'E')])]),'E.EFF':bytes(external),
          'A.SPL':resource('SPL',1,[(1,1,[])]),'B.SPL':resource('SPL',2,[(1,1,[])])}
    report=inventory(data).item('S')[0]
    assert report.classification=='typed_cast_candidate'
    assert set(report.spells)=={'A','B'}
    assert not report.diagnostics


def test_repeating_edges_are_recorded_without_reexpansion_and_budgets_still_apply():
    data = {"S.ITM": resource("ITM", 11, [(3, 0, [effect(146, b"A")])]),
            "A.SPL": resource("SPL", 1, [(1, 1, [effect(146, b"B")])]),
            "B.SPL": resource("SPL", 2, [(1, 1, [effect(146, b"A")])])}
    report = inventory(data).item("S")[0]
    assert report.classification == 'typed_cast_candidate'
    assert "native repeating edge" in report.diagnostics[0]
    assert len(report.edges) == 3 and set(report.spells) == {'A','B'}
    assert "depth" in inventory(data, max_depth=1).item("S")[0].diagnostics[0]
    assert "resources" in inventory(data, max_nodes=1).item("S")[0].diagnostics[0]


@pytest.mark.parametrize('opcode', [146, 326])
def test_native_repeating_helper_retains_untyped_semantics_and_checks_other_branches(opcode):
    data = {'S.ITM':resource('ITM',11,[(3,0,[effect(146,b'A')])]),
            'A.SPL':resource('SPL',1,[(1,1,[effect(146,b'HELPER')])]),
            'HELPER.SPL':resource('SPL',0,[(1,1,[effect(opcode,b'HELPER',1 if opcode==146 else 0),effect(146,b'B')])]),
            'B.SPL':resource('SPL',2,[(1,1,[])])}
    report=inventory(data).item('S')[0]
    assert report.classification=='typed_cast_candidate'
    assert report.spells['HELPER']['policy']=='native_untyped'
    assert set(report.resources)=={'S.ITM','A.SPL','HELPER.SPL','B.SPL'}
    del data['B.SPL']
    report=inventory(data).item('S')[0]
    assert report.classification=='unresolved'
    assert 'B.SPL' in report.diagnostics[-1]


def test_direct_native_effects_and_binary_unrelated_resref_are_preserved():
    binary = bytearray(effect(101))
    binary[20:28] = b"\xff\x00\x80\xff\x00\x80\xff\x00"
    data = {"S.ITM": resource("ITM", 11, [(3, 0, [bytes(binary), effect(12)])])}
    assert inventory(data).item("S")[0].classification == "native_only"
    assert not inventory(data).item("S")[0].diagnostics


def test_missing_mode_malformed_and_learning_mix_have_explicit_outcomes():
    data = {"S.ITM": resource("ITM", 11, [(3, 0, [effect(146, b"MISSING")])])}
    assert "MISSING.SPL" in inventory(data).item("S")[0].diagnostics[0]
    data["S.ITM"] = resource("ITM", 11, [(3, 0, [effect(146, b"A", 99)])])
    assert "mode 99" in inventory(data).item("S")[0].diagnostics[0]
    data["S.ITM"] = resource("ITM", 11, [(3, 0, [effect(147, b"A"), effect(146, b"A")])])
    data["A.SPL"] = resource("SPL", 1, [(1, 1, [])])
    assert inventory(data).item("S")[0].classification == "mixed_learning_cast"
    data["A.SPL"] = data["A.SPL"][:113]
    assert "outside resource" in inventory(data).item("S")[0].diagnostics[0]


def test_non_scroll_and_non_use_abilities_are_excluded():
    assert inventory({"S.ITM": resource("ITM", 7, [(3, 0, [effect(146, b"MISSING")])])}).item("S") == []
    assert inventory({"S.ITM": resource("ITM", 11, [(1, 0, [effect(146, b"MISSING")])])}).item("S") == []


@pytest.mark.parametrize("field,value", [(100, 1), (106, 114), (106, 0xFFFFFFF0)])
def test_reject_index_corruption_not_padding(field, value):
    raw = bytearray(resource("ITM", 11, [(3, 0, [effect(12)])]))
    struct.pack_into("<I", raw, field, value)
    with pytest.raises(resources.ResourceError):
        resources.parse("S", "ITM", bytes(raw))


def test_actual_installed_sr_and_non_sr_resources_read_only():
    # Optional local samples, never bundled: an installation with and one without
    # Spell Revisions (CBM_RESOURCE_SAMPLES, separated by os.pathsep) and the
    # Rebalance repository's KEY reader (CBM_KEY_RESOURCE_HELPER).
    helper = Path(os.environ.get("CBM_KEY_RESOURCE_HELPER") or "missing-helper")
    roots = [Path(p) for p in os.environ.get("CBM_RESOURCE_SAMPLES", "").split(os.pathsep) if p]
    if not helper.is_file() or not roots or any(not (p / "chitin.key").is_file() for p in roots):
        pytest.skip("unbundled local resource samples unavailable")
    reader = runpy.run_path(str(helper))
    for root in roots:
        key = (root / "chitin.key").read_bytes()
        override = {p.name.upper(): p for p in (root / "override").glob("*") if p.is_file()}
        def load(name, ext):
            path = override.get(name + "." + ext)
            if path:
                return path.read_bytes()
            _, locator, bifs = reader["_find_key_resource"](key, name, reader["RESOURCE_TYPES"][ext])
            path = reader["_resolve_bif_path"](root, bifs[locator >> 20][1])
            return reader["_read_biff_resource"](path, locator & 0xFFFFF, reader["RESOURCE_TYPES"][ext])[0]
        analyzer = resources.Inventory(load)
        for name in ("SCRL67", "SCRL75", "SCRL7C", "SCRL03", "SCRL04", "SCRL05", "SCRL06", "SCRL07", "SCRL08", "SCRL09", "SCRL15"):
            before = hashlib.sha256(load(name, "ITM")).hexdigest()
            result = analyzer.item(name)
            assert result
            if name in ("SCRL67", "SCRL75", "SCRL7C"):
                assert any(r.classification == "typed_cast_candidate" for r in result)
                assert any(r.classification == "learning" for r in result)
            else:
                assert all(r.classification == "native_exception" for r in result), [r.as_dict() for r in result]
            assert hashlib.sha256(load(name, "ITM")).hexdigest() == before


def test_fixed_family_mechanics_allow_reordering_links_and_added_typed_helpers():
    data = {"SCRL03.ITM": resource("ITM", 11, [(3, 0, [effect(146, b"A"), effect(141), effect(177, b"ACID")])]),
            "A.SPL": resource("SPL", 1, [(1, 1, [])]), "ACID.EFF": eff(27, b"", level=17)}
    report = inventory(data).item("SCRL03")[0]
    assert report.classification == "native_exception"
    assert report.exception == "protection from acid"
    data["ACID.EFF"] = eff(12, b"", level=17)
    report = inventory(data).item("SCRL03")[0]
    assert report.classification == "unresolved"
    assert "lacks its protection mechanic" in report.diagnostics[0]


def test_unknown_installed_spell_type_is_not_native_preservation():
    report = inventory({"S.ITM": resource("ITM", 11, [(3, 0, [effect(146, b"A")])]),
                        "A.SPL": resource("SPL", 99, [(1, 1, [])])}).item("S")[0]
    assert report.classification == "unresolved"
    assert "unknown installed spell type 99" in report.diagnostics[0]
