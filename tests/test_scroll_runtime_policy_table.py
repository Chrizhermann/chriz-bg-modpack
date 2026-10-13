"""Installed graph export -> compiled bounded lookup, with fresh hash gating."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/scroll-runtime"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


exporter = module("scroll_policy_exporter", SOURCE / "policy_table.py")
fixtures = module("scroll_policy_resources", ROOT / "tests/test_scroll_runtime_resources.py")
native = module("scroll_policy_native", ROOT / "tests/test_scroll_runtime_native.py")


def reports():
    effect, resource = fixtures.effect, fixtures.resource
    data = {
        "S.ITM": resource("ITM", 11, [(3, 0, [effect(146, b"HELPER")]),
                                        (3, 0, [effect(147, b"ARCANE")]),
                                        (3, 0, [effect(12)]),
                                        (3, 0, [effect(147, b"ARCANE"), effect(146, b"ARCANE")]),
                                        (3, 0, [effect(326, b"ARCANE")]),
                                        # A dispatch whose child resource is absent stays unresolved.
                                        (3, 0, [effect(146, b"GONE")])]),
        "HELPER.SPL": resource("SPL", 4, [(1, 1, [effect(146, b"ARCANE")])]),
        "ARCANE.SPL": resource("SPL", 1, [(1, 1, [])]),
        "ABCDEFGH.ITM": resource("ITM", 11, [(3, 0, [effect(146, b"DIVINE")])]),
        "DIVINE.SPL": resource("SPL", 2, [(1, 1, [])]),
        "SCRL03.ITM": resource("ITM", 11, [(3, 0, [effect(27), effect(146, b"ARCANE")])]),
    }
    analyzer = fixtures.inventory(data)
    return data, analyzer.item("S") + analyzer.item("ABCDEFGH") + analyzer.item("SCRL03")


@pytest.fixture(scope="session")
def probe(tmp_path_factory):
    build = tmp_path_factory.mktemp("scroll-policy-build")
    compiler, env, msvc = native.compiler_environment()
    binary = build / ("policy.exe" if msvc else "policy")
    source = str(SOURCE / "policy_table_probe.cpp")
    args = ([compiler, "/nologo", "/std:c++20", "/EHsc", "/W4", "/WX", "/permissive-", source, f"/Fe{binary}"]
            if msvc else [compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-pedantic", source, "-o", str(binary)])
    result = subprocess.run(args, cwd=build, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return binary


def run(probe, tmp_path, blob, *arguments):
    path = tmp_path / "policy.bin"
    path.write_bytes(blob)
    return subprocess.run([str(probe), str(path), *arguments], capture_output=True, text=True)


def test_deterministic_export_and_dependency_digests():
    data, source = reports()
    blob, manifest = exporter.build(source)
    reversed_blob, reversed_manifest = exporter.build(reversed(source))
    assert blob == reversed_blob and manifest == reversed_manifest
    assert manifest["entries"] == 8 and manifest["dependencies"] == len(data)
    assert manifest["table_sha256"] == hashlib.sha256(blob).hexdigest()
    offset = 16 + manifest["entries"] * 16
    for i in range(manifest["dependencies"]):
        name, ext, digest = struct.unpack_from("<8s4s32s", blob, offset + i * 44)
        key = name.rstrip(b"\0").decode() + "." + ext.rstrip(b"\0").decode()
        assert digest == hashlib.sha256(data[key]).digest()
    source[0].diagnostics.append("later caller mutation")
    assert "later caller mutation" not in str(manifest)


@pytest.mark.parametrize("item,ability,result", [
    ("S", 0, "0 0"), ("s", 1, "1 1"), ("S", 2, "1 2"),
    # Opcode 326 is an implemented conditional dispatch (see
    # test_common_conditional_dispatch_resolves_actual_child), not unresolved.
    ("S", 3, "2 4"), ("S", 4, "0 0"), ("S", 5, "2 5"), ("S", 6, "absent"),
    ("abcdefgh", 0, "0 0"), ("SCRL03", 0, "1 3"), ("MISSING", 0, "absent"),
])
def test_compiled_lookup_by_exact_item_ability(probe, tmp_path, item, ability, result):
    blob, _ = exporter.build(reports()[1])
    actual = run(probe, tmp_path, blob, "lookup", item, str(ability))
    assert actual.returncode == 0, actual.stderr
    assert actual.stdout.strip() == result


@pytest.mark.parametrize("mode,expected", [
    ("before", "not been verified"), ("invalidate", "not been verified"),
    ("invalid_name", "invalid policy resource reference"),
])
def test_unverified_or_invalid_runtime_input_refused(probe, tmp_path, mode, expected):
    actual = run(probe, tmp_path, exporter.build(reports()[1])[0], mode)
    assert actual.returncode == 1 and expected in actual.stderr


@pytest.mark.parametrize("mode,expected", [("fixed8", "0"), ("changed", "invalidated"), ("missing", "invalidated")])
def test_fixed_resrefs_and_dependency_refresh_invalidate(probe, tmp_path, mode, expected):
    actual = run(probe, tmp_path, exporter.build(reports()[1])[0], mode)
    assert actual.returncode == 0 and actual.stdout.strip() == expected, actual.stderr


@pytest.mark.parametrize("mutation", ["count", "truncate", "trailing", "duplicate", "order", "policy", "reason", "reserved", "ability", "name", "extension", "root", "dep_duplicate"])
def test_compiled_wire_bounds_and_ambiguity_checks(probe, tmp_path, mutation):
    blob, manifest = exporter.build(reports()[1])
    raw = bytearray(blob)
    dep = 16 + manifest["entries"] * 16
    if mutation == "count": struct.pack_into("<I", raw, 8, exporter.MAX_ENTRIES + 1)
    elif mutation == "truncate": raw.pop()
    elif mutation == "trailing": raw.append(0)
    elif mutation == "duplicate": raw[32:48] = raw[16:32]
    elif mutation == "order": raw[16:32], raw[32:48] = raw[32:48], raw[16:32]
    elif mutation == "policy": raw[28] = 1
    elif mutation == "reason": raw[29] = 255
    elif mutation == "reserved": raw[30] = 1
    elif mutation == "ability": struct.pack_into("<I", raw, 24, 65535)
    elif mutation == "name": raw[16] = ord("a")
    elif mutation == "extension": raw[dep + 8] = ord("X")
    elif mutation == "root": raw[dep + 8:dep + 12] = b"EFF\0"
    elif mutation == "dep_duplicate": raw[dep + 44:dep + 88] = raw[dep:dep + 44]
    actual = run(probe, tmp_path, bytes(raw), "parse")
    assert actual.returncode == 1, mutation


@pytest.mark.parametrize("mutation", ["duplicate", "ability", "name", "classification", "root", "digest", "conflict"])
def test_export_rejects_ambiguous_or_invalid_inventory(mutation):
    source = [r.as_dict() for r in reports()[1]]
    if mutation == "duplicate": source.append(source[0])
    elif mutation == "ability": source[0]["ability"] = True
    elif mutation == "name": source[0]["item"] = "TOOLONG99"
    elif mutation == "classification": source[0]["classification"] = "maybe"
    elif mutation == "root": del source[0]["resources"]["S.ITM"]
    elif mutation == "digest": source[0]["resources"]["S.ITM"] = "x" * 64
    elif mutation == "conflict": source[0]["resources"]["S.ITM"] = "0" * 64
    with pytest.raises(ValueError): exporter.build(source)


@pytest.mark.parametrize("name,target", [("SCRL08", 25), ("SCRL15", 134)])
def test_opcode101_exception_requires_actual_protected_condition(name, target):
    for mode, classification in [(target, "native_exception"), (12, "unresolved")]:
        data = {name + ".ITM": fixtures.resource("ITM", 11, [(3, 0, [fixtures.effect(101, mode=mode)])])}
        result = fixtures.inventory(data).item(name)[0]
        assert result.classification == classification


def test_changed_linked_graph_changes_export():
    data, source = reports()
    before, _ = exporter.build(source)
    data["ARCANE.SPL"] = fixtures.resource("SPL", 2, [(1, 1, [])])
    inventory = fixtures.inventory(data)
    after, _ = exporter.build(inventory.item("S") + inventory.item("ABCDEFGH") + inventory.item("SCRL03"))
    assert before != after


def test_resref_normalization_preserves_ascii_punctuation():
    assert exporter.name_bytes("a.b_#-1") == b"A.B_#-1\0"
    with pytest.raises(ValueError): exporter.name_bytes("\u00df")
