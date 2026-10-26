"""What the native build's probes write: LF, no trailing spaces, current.

bank_build.ps1's checks run four probes that regenerate eight result files and
two native inputs. Written with write_text (CRLF on Windows) and with padded
listing lines, every build rewrote all of them, and the results kept hashes of
sources long since changed. The probes now write through keep_or_write (LF, and
only a changed text), and the build returns what they regenerate to the
checkout (tools/sync_campaign_xp.py record), so the committed results are the
build's own. Needs no game files: it reads only the repository.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research/xp-banking-native"
GENERATORS = ("dual_hp_probe.py", "dual_old_skill_limits.py", "dual_proficiency_probe.py", "dual_skill_rows_probe.py")
RESULTS = ("dual-hp-check-results.json", "dual_manual_profiles.lua", "dual-old-skill-limits-2.6.6.0.txt",
           "dual-old-skill-limits-2.7.3.0.txt", "dual-old-skill-limits.json", "dual-proficiency-signatures.json",
           "dual-proficiency-check-results.json", "dual-skill-row-results.json")
GENERATED_INPUTS = ("dual_native_proficiency_builds.inc", "dual_skill_rows_builds.inc")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def writes(path):
    """File writes in a probe outside keep_or_write: (line, call)."""
    found = []

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef) and child.name == "keep_or_write":
                continue
            if isinstance(child, ast.Call):
                called = child.func.attr if isinstance(child.func, ast.Attribute) else getattr(child.func, "id", "")
                if called in ("write_text", "write_bytes", "open"):
                    found.append((child.lineno, called))
            visit(child)

    visit(ast.parse(path.read_text(encoding="utf-8")))
    return found


@pytest.mark.parametrize("name", GENERATORS)
def test_the_build_probes_write_only_through_keep_or_write(name):
    assert writes(RESEARCH / name) == []


def test_keep_or_write_writes_lf_and_only_a_changed_text(tmp_path):
    # The helper's own source, without the probe's game-file imports.
    tree = ast.parse((RESEARCH / "dual_proficiency_probe.py").read_text(encoding="utf-8"))
    helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "keep_or_write")
    scope = {}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "keep_or_write", "exec"), scope)
    keep_or_write = scope["keep_or_write"]
    path = tmp_path / "result.json"
    keep_or_write(path, '{\n  "a": 1\n}\n')
    assert path.read_bytes() == b'{\n  "a": 1\n}\n'
    path.write_bytes(b'{\r\n  "a": 1\r\n}\r\n')  # The same text with other line ends: left alone.
    keep_or_write(path, '{\n  "a": 1\n}\n')
    assert path.read_bytes() == b'{\r\n  "a": 1\r\n}\r\n'
    keep_or_write(path, '{\n  "a": 2\n}\n')
    assert path.read_bytes() == b'{\n  "a": 2\n}\n'


@pytest.mark.parametrize("name", RESULTS + GENERATED_INPUTS)
def test_probe_output_is_lf_without_trailing_spaces(name):
    data = (RESEARCH / name).read_bytes()
    assert b"\r" not in data and data.endswith(b"\n")
    assert [n for n, line in enumerate(data.split(b"\n"), 1) if line != line.rstrip()] == []


def test_probe_results_name_the_sources_they_checked():
    hp = json.loads((RESEARCH / "dual-hp-check-results.json").read_text(encoding="utf-8"))
    assert hp["source_sha256"] == {path.name: sha256(path) for prefix in ("dual_hp_*", "dual_choice_*")
                                   for path in RESEARCH.glob(prefix) if path.is_file()}
    proficiency = json.loads((RESEARCH / "dual-proficiency-check-results.json").read_text(encoding="utf-8"))
    assert proficiency["source_sha256"] == {name: sha256(RESEARCH / name) for name in (
        "dual_native_proficiency.h", "dual_native_proficiency.cpp", "dual_native_proficiency_builds.inc",
        "dual_proficiency_probe.py")}
