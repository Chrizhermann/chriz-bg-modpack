"""Both CI workflows run one shared pytest selection, tests/ci-pytest.txt, through tools.ci_pytest.

Fails if a tests/test_campaign_xp_*.py file is missing from the selection, if the
selection lists a file that does not exist, lists one twice or is not sorted, or
if a workflow runs pytest any other way (for example `python -m pytest` with its
own file list), which is how the selection drifted before. Also fails if a workflow
does not fetch the pinned EEex scripts that the notice and record tests read, or
does not point CBM_EEEX_SOURCE at them before the selection runs.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools import ci_pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {"ci": ROOT / ".github" / "workflows" / "ci.yml", "release": ROOT / ".github" / "workflows" / "release.yml"}
PYTEST = re.compile(r"\b(pytest|py\.test)\b")
RUNNER = re.compile(r"\bpython3? -m tools\.ci_pytest\b([^;&|]*)")


def pytest_problems(text):
    """Workflow lines (YAML comments aside) that mention pytest other than through tools.ci_pytest, and the
    argument lists of the tools.ci_pytest invocations."""
    bad, runs = [], []
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        m = RUNNER.search(line)
        if m:
            runs.append(m.group(1).split())
            line = line[:m.start()] + line[m.end():]
        if PYTEST.search(line):
            bad.append("line %d: %s" % (n, line.strip()))
    return bad, runs


def test_every_campaign_xp_test_is_selected():
    listed = set(ci_pytest.selection())
    found = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_campaign_xp_*.py"))
    assert found, "no tests/test_campaign_xp_*.py found"
    assert [f for f in found if f not in listed] == []


def test_selection_lists_existing_files_once_in_sorted_order():
    files = ci_pytest.selection()
    assert files
    assert [f for f in files if not (ROOT / f).is_file() or "\\" in f] == []
    assert sorted({f for f in files if files.count(f) > 1}) == []
    assert files == sorted(files)
    assert "tests/test_ci_pytest_selection.py" in files


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_workflow_runs_pytest_only_through_the_shared_selection(name):
    bad, runs = pytest_problems(WORKFLOWS[name].read_text(encoding="utf-8"))
    assert bad == []
    assert len(runs) == 1, "%s.yml runs tools.ci_pytest %d times" % (name, len(runs))


def test_only_the_windows_policy_test_is_added_outside_the_selection():
    files = set(ci_pytest.selection())
    extra = {name: [a for run in pytest_problems(path.read_text(encoding="utf-8"))[1] for a in run if a.endswith(".py")]
             for name, path in WORKFLOWS.items()}
    assert extra == {"ci": [], "release": ["tests/test_scroll_runtime_installer.py"]}
    assert "tests/test_scroll_runtime_installer.py" not in files


EEEX_URL = re.compile(r"raw\.githubusercontent\.com/Bubb13/EEex/(?:\$\{EEEX_COMMIT\}|\$commit)/EEex/copy/EEex_scripts/")
EEEX_COMMIT = re.compile(r"""(?:EEEX_COMMIT=|\$commit = )["']([0-9a-f]{40})["']""")
EEEX_PIN = re.compile(r"""(EEex_\w+\.lua)'?\s*=?\s*'?([0-9a-f]{64})\b""")


def eeex_fetch(text):
    """(commit, {script: sha256}, line of the first pin, line that provides CBM_EEEX_SOURCE, line of the
    tools.ci_pytest run) for one workflow."""
    lines = text.splitlines()
    commits = {m.group(1) for line in lines for m in [EEEX_COMMIT.search(line)] if m}
    pins = {m.group(1): m.group(2) for line in lines for m in [EEEX_PIN.search(line)] if m}
    first_pin = min((n for n, line in enumerate(lines) if EEEX_PIN.search(line)), default=None)
    source = min((n for n, line in enumerate(lines) if re.search(r"\bCBM_EEEX_SOURCE(?:=|: )", line)), default=None)
    run = min((n for n, line in enumerate(lines) if RUNNER.search(line)), default=None)
    assert any(EEEX_URL.search(line) for line in lines), "no pinned EEex download"
    return commits, pins, first_pin, source, run


def test_both_workflows_fetch_the_pinned_eeex_scripts_the_tests_read():
    """test_campaign_xp_notices.py and test_campaign_xp_record_ui.py read real EEex scripts; CI fetches them at one
    pinned commit with sha256 checks and points CBM_EEEX_SOURCE at them before the shared selection runs."""
    read = {m for f in ["tests/test_campaign_xp_notices.py", "tests/test_campaign_xp_record_ui.py"]
            for m in re.findall(r"EEex_\w+\.lua", (ROOT / f).read_text(encoding="utf-8"))}
    assert read == {"EEex_Action.lua", "EEex_Keybinds.lua", "EEex_Menu.lua"}
    seen = {}
    for name, path in WORKFLOWS.items():
        commits, pins, first_pin, source, run = eeex_fetch(path.read_text(encoding="utf-8"))
        assert commits == {"a6d21abe44e20509f5d0259ccc6c7e7f9d12b285"}, name
        assert set(pins) == read, name
        assert None not in (first_pin, source, run) and first_pin < run and source < run, name
        seen[name] = pins
    assert seen["ci"] == seen["release"]


@pytest.mark.parametrize("line", [
    "        run: python3 -m pytest tests/test_utility_xp.py -q",
    "        run: python -m pytest tests/test_a.py tests/test_b.py",
    "        run: pytest -q tests",
    "        run: python -m tools.ci_pytest -q && python -m pytest tests/test_extra.py",
])
def test_a_separate_pytest_invocation_is_reported(line):
    bad, runs = pytest_problems("steps:\n" + line + "\n")
    assert len(bad) == 1 and bad[0].startswith("line 2: ")


def test_selection_skips_comments_and_blank_lines(tmp_path):
    sel = tmp_path / "ci-pytest.txt"
    sel.write_text("# comment\n\n  tests/test_b.py  \n# tests/test_c.py\ntests/test_a.py\n", encoding="utf-8")
    assert ci_pytest.selection(sel) == ["tests/test_b.py", "tests/test_a.py"]


def test_missing_selected_file_fails_clearly(tmp_path, monkeypatch, capsys):
    sel = tmp_path / "ci-pytest.txt"
    sel.write_text("tests/test_ci_pytest_selection.py\ntests/test_does_not_exist.py\n", encoding="utf-8")
    monkeypatch.setattr(ci_pytest, "SELECTION", sel)
    assert ci_pytest.main(["-q"]) == 2
    err = capsys.readouterr().err
    assert "missing" in err and "tests/test_does_not_exist.py" in err
    assert "tests/test_ci_pytest_selection.py" not in err
