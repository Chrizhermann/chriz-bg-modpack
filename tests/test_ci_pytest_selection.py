"""Both CI workflows run one shared pytest selection, tests/ci-pytest.txt, through tools.ci_pytest.

Fails if a tests/test_campaign_xp_*.py file is missing from the selection, if the
selection lists a file that does not exist, lists one twice or is not sorted, or
if a workflow runs pytest any other way (for example `python -m pytest` with its
own file list), which is how the selection drifted before. Also fails if what a
workflow's run executes (the selected tests and the repository files they import,
load or name) reads something only a developer's machine has: an absolute local
path or one above the checkout, an environment variable that workflow does not
set for the run (OPTIONAL lists those whose tests manage without them), or EEex
scripts other than through tests/pinned_eeex.py, whose pins both workflows must
fetch, sha256-checked at its commit, before the selection runs. A harness that read
EEex_Sprite.lua from a misnamed variable, else from a C:/tmp research checkout,
passed locally and failed the alpha.14 release check that way.
"""
from __future__ import annotations

import ast
import functools
import os
import re
from pathlib import Path

import pytest

from tests import pinned_eeex
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
    """(commit, {script: sha256}, line of the first pin, line of the tools.ci_pytest run) for one workflow."""
    lines = text.splitlines()
    commits = {m.group(1) for line in lines for m in [EEEX_COMMIT.search(line)] if m}
    pins = {m.group(1): m.group(2) for line in lines for m in [EEEX_PIN.search(line)] if m}
    first_pin = min((n for n, line in enumerate(lines) if EEEX_PIN.search(line)), default=None)
    run = min((n for n, line in enumerate(lines) if RUNNER.search(line)), default=None)
    assert any(EEEX_URL.search(line) for line in lines), "no pinned EEex download"
    return commits, pins, first_pin, run


STEP = re.compile(r"^(\s*)- name:")
ENV_BLOCK = re.compile(r"^(\s*)env:\s*$")
ENV_KEY = re.compile(r"^\s*([A-Za-z_]\w*):")
SET_IN_STEP = re.compile(r"(?:\$env:|\bexport\s+)([A-Za-z_]\w*)\s*=")


def run_env(text):
    """The environment variables a workflow gives its tools.ci_pytest run: a workflow or job env, that step's env,
    what earlier steps export to GITHUB_ENV, and what the step itself sets before the run."""
    lines = text.splitlines()
    run = next(n for n, line in enumerate(lines) if RUNNER.search(line) and not line.lstrip().startswith("#"))
    starts = [n for n, line in enumerate(lines) if STEP.match(line)]
    step = max(n for n in starts if n <= run)
    end = min([n for n in starts if n > step] + [len(lines)])
    indent = len(STEP.match(lines[step]).group(1))
    names = set(re.findall(r"(?:^|\s)([A-Za-z_]\w*)=\S*\s", lines[run][:RUNNER.search(lines[run]).start()]))
    for n, line in enumerate(lines):
        block = ENV_BLOCK.match(line)
        if block and (step < n < end or (n < step and len(block.group(1)) < indent)):
            for item in lines[n + 1:]:
                if item.strip() and len(item) - len(item.lstrip()) <= len(block.group(1)):
                    break
                names.update(ENV_KEY.findall(item))
        if n < step and "GITHUB_ENV" in line:
            names.update(re.findall(r"\b([A-Za-z_]\w*)=", line))
        if step <= n <= run:
            names.update(SET_IN_STEP.findall(line))
    return names


# What a workflow's run executes may read the checkout and what that workflow sets for the run, nothing else.
SELF = "tests/test_ci_pytest_selection.py"  # Its strings are the examples and fetch patterns it checks against.
EEEX_HELPER = "tests/pinned_eeex.py"
LOCAL_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|~[\\/]|/(?:tmp|home|Users|mnt|root)/|/[A-Za-z]/)")
UPWARD = re.compile(r"(?:^|[\\/])\.\.[\\/]|[\\/]\.\.$")  # '..' alone is a path part or Lua's concatenation.
EEEX_LAYOUT = re.compile(r"copy[\\/]+EEex_scripts")
LOCAL_CALLS = ("Path.home", "gettempdir")  # A literal '~/...' is a LOCAL_PATH; expanding a configured path is fine.
ENV_READS = ("os.environ.get", "os.getenv", "os.environ.setdefault", "environ.get", "getenv")
LOADERS = ("spec_from_file_location", "run_path", "SourceFileLoader", "subprocess.run", "subprocess.call",
           "subprocess.check_call", "subprocess.check_output", "subprocess.Popen")
OPTIONAL = {  # Read by what the runs execute, set by neither workflow, and why that is fine.
    "CBM_BUILD_SECRET": "tools/sync_campaign_xp.py needs it only to capture or record a native build; the package "
                        "tests hand the tool their own",
    "CBM_KEY_RESOURCE_HELPER": "test_scroll_runtime_resources.py skips its installed-game checks without it",
    "CBM_RESOURCE_SAMPLES": "test_scroll_runtime_resources.py skips its installed-game checks without it",
}
LOCAL_DATA = {  # Absolute or upward paths that are test data, not something read.
    ("tests/test_campaign_xp_package.py", name): "a manifest path the package check must refuse"
    for name in ("../outside", "C:/outside", "x/../../outside")
}
# test_campaign_xp_probe_results.py parses the native build's probes (bank_build.ps1's checks run them) and runs
# only the functions listed here; it never imports or runs a probe whole.
PARSED_ONLY = {
    "research/xp-banking-native/dual_hp_probe.py": (),
    "research/xp-banking-native/dual_old_skill_limits.py": (),
    "research/xp-banking-native/dual_proficiency_probe.py": ("keep_or_write",),
    "research/xp-banking-native/dual_skill_rows_probe.py": (),
}


class Module:
    """One reached file: its syntax tree, the parts of it that run, and its module-level names."""

    def __init__(self, rel, text):
        self.rel, self.tree, self.values = rel, ast.parse(text), {}
        self.runs = [self.tree]
        for node in self.tree.body:
            if isinstance(node, ast.Assign):
                self.values.update((t.id, node.value) for t in node.targets if isinstance(t, ast.Name))

    def nodes(self):
        """Every syntax node of the parts that run."""
        return [node for top in self.runs for node in ast.walk(top)]

    def text(self, node, seen=frozenset()):
        """node's string when it is a literal or a module-level name bound to one, else None."""
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, str) else None
        if isinstance(node, ast.Name) and node.id in self.values and node.id not in seen:
            return self.text(self.values[node.id], seen | {node.id})
        return None

    def strings(self, node, seen=frozenset()):
        """The string literals node is built from, through module-level names."""
        found = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                found.add(sub.value)
            elif isinstance(sub, ast.Name) and sub.id in self.values and sub.id not in seen:
                found |= self.strings(self.values[sub.id], seen | {sub.id})
        return found


def repo_files(root):
    """The repository's .py files outside hidden and cache folders, as paths from root."""
    found = set()
    for top, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        found.update((Path(top) / n).relative_to(root).as_posix() for n in names if n.endswith(".py"))
    return found


def named(text, files):
    """The repository .py files a string names by their path from the root or a tail of it."""
    text = text.replace("\\", "/").lstrip("./")
    if not text.endswith(".py") or "\n" in text:
        return set()
    return {f for f in files if f == text or f.endswith("/" + text)}


def module_files(name, files):
    """The repository file that defines module `name`, if any."""
    stem = name.strip(".").replace(".", "/")
    return {f for f in (stem + ".py", stem + "/__init__.py") if stem and f in files}


def reach(roots, root=ROOT, parsed_only=PARSED_ONLY):
    """{file: Module} for what runs from roots: the roots, the repository modules a reached file imports, and every
    repository .py file it names (which covers what loaders run); of a parsed_only file only the listed functions
    run. Also [(file, parsed_only file)] wherever a reached file imports one or hands one to a loader."""
    files, reached, loaded, queue = repo_files(root), {}, [], list(roots)
    while queue:
        rel = queue.pop()
        if rel in reached:
            continue
        module = reached[rel] = Module(rel, (root / rel).read_text(encoding="utf-8"))
        if rel in parsed_only:
            module.runs = [n for n in module.tree.body if isinstance(n, ast.FunctionDef) and n.name in parsed_only[rel]]
            continue
        imported, loads, names = set(), set(), set()
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Import):
                imported.update(f for alias in node.names for f in module_files(alias.name, files))
            elif isinstance(node, ast.ImportFrom):
                base = ".".join(rel.split("/")[:-node.level] + [node.module or ""]) if node.level else node.module
                imported.update(f for name in [base] + [base + "." + a.name for a in node.names]
                                for f in module_files(name, files))
            elif isinstance(node, ast.Call) and ast.unparse(node.func).endswith("import_module") and node.args:
                imported.update(module_files(module.text(node.args[0]) or "", files))
            elif isinstance(node, ast.Call) and ast.unparse(node.func).endswith(LOADERS):
                loads.update(f for s in module.strings(node) for f in named(s, files))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                names.update(named(node.value, files))
        loaded += [(rel, f) for f in sorted(imported | loads) if f in parsed_only]
        queue += sorted(imported | loads | names)
    return reached, loaded


def env_reads(module):
    """(name, node) for each environment variable what runs of module reads; name is None when no literal names it."""
    found = []
    for node in module.nodes():
        if isinstance(node, ast.Call) and ast.unparse(node.func) in ENV_READS and node.args:
            found.append((module.text(node.args[0]), node))
        elif (isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load)
              and ast.unparse(node.value) in ("os.environ", "environ")):
            found.append((module.text(node.slice), node))
        elif (isinstance(node, ast.Compare)
              and any(ast.unparse(c) in ("os.environ", "environ") for c in node.comparators)):
            found.append((module.text(node.left), node))
    return found


def eeex_requests(module):
    """(name, node) for each script what runs of module asks tests/pinned_eeex.py for; name is None when no literal
    names it."""
    return [(module.text(node.args[0]) if node.args else None, node) for node in module.nodes()
            if isinstance(node, ast.Call) and ast.unparse(node.func).split(".")[-1] == "pinned_eeex_script"]


def above_checkout(module):
    """Lines where what runs of module goes above the checkout from __file__: a sibling checkout is local too."""
    depth, levels = len(module.rel.split("/")), {}

    def up(node, more):
        below = level(node)
        return None if below is None else below + more

    def level(node):  # How many folders above __file__ node is, when it is __file__ or one of its folders.
        if isinstance(node, ast.Name):
            return 0 if node.id == "__file__" else levels.get(node.id)
        if isinstance(node, ast.Call) and node.args and ast.unparse(node.func) in ("Path", "pathlib.Path"):
            return level(node.args[0])
        if isinstance(node, ast.Call) and node.args and ast.unparse(node.func) == "os.path.dirname":
            return up(node.args[0], 1)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("resolve", "absolute")):
            return level(node.func.value)
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            return up(node.value, 1)
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "parents"
                and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int)):
            return up(node.value.value, node.slice.value + 1)
        return None

    for node in module.tree.body:
        if isinstance(node, ast.Assign) and level(node.value) is not None:
            levels.update((t.id, level(node.value)) for t in node.targets if isinstance(t, ast.Name))
    return sorted({node.lineno for node in module.nodes()
                   if isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)) and (level(node) or 0) > depth})


def problems(module, provided):
    """'file:line: what' for each thing what runs of module reads that a run given the variables `provided` lacks."""
    rel, found = module.rel, []
    for node in module.nodes():
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and rel != SELF:
            text = node.value
            local = LOCAL_PATH.match(text) or (UPWARD.search(text) and not re.search(r"\s", text))
            if local and (rel, text) not in LOCAL_DATA:
                found.append((node.lineno, "local path %r" % text))
            if EEEX_LAYOUT.search(text) and rel != EEEX_HELPER:
                found.append((node.lineno, "EEex script path %r outside %s" % (text, EEEX_HELPER)))
        elif isinstance(node, ast.Call) and ast.unparse(node.func).endswith(LOCAL_CALLS):
            found.append((node.lineno, "local path from %s()" % ast.unparse(node.func)))
    for name, node in env_reads(module):
        if name is None:
            found.append((node.lineno, "environment variable no literal names: %s" % ast.unparse(node)))
            continue
        if "EEEX" in name.upper() and rel != EEEX_HELPER:
            found.append((node.lineno, "%s: read EEex scripts through %s" % (name, EEEX_HELPER)))
        if name not in provided and name not in OPTIONAL:
            found.append((node.lineno, "%s, which the workflow does not set for the run" % name))
    for name, node in eeex_requests(module):
        if name not in pinned_eeex.PINS:
            found.append((node.lineno, "%s asks for no pinned script" % ast.unparse(node)))
    found += [(line, "a path above the checkout") for line in above_checkout(module)]
    return ["%s:%d: %s" % (rel, line, what) for line, what in sorted(found)]


@functools.lru_cache(maxsize=None)
def workflow_reach(name):
    """reach() of what the workflow's tools.ci_pytest run executes: the selection and the test files it adds."""
    extra = [a for run in pytest_problems(WORKFLOWS[name].read_text(encoding="utf-8"))[1] for a in run
             if a.endswith(".py")]
    return reach(ci_pytest.selection() + extra)


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_what_the_run_executes_reads_only_the_checkout_and_what_the_workflow_sets(name):
    reached, _ = workflow_reach(name)
    provided = run_env(WORKFLOWS[name].read_text(encoding="utf-8"))
    assert [p for module in reached.values() for p in problems(module, provided)] == []


def test_eeex_scripts_come_only_from_the_pinned_fetch():
    """Each script the runs ask tests/pinned_eeex.py for is pinned and each pin is asked for; both workflows fetch
    exactly those pins, with their sha256, at the pinned commit and set CBM_EEEX_SOURCE before the selection runs."""
    asked = {n for name in WORKFLOWS for m in workflow_reach(name)[0].values() for n, _ in eeex_requests(m)}
    assert asked == set(pinned_eeex.PINS)
    for name, path in WORKFLOWS.items():
        text = path.read_text(encoding="utf-8")
        commits, pins, first_pin, run = eeex_fetch(text)
        assert commits == {pinned_eeex.COMMIT} and pins == pinned_eeex.PINS, name
        assert None not in (first_pin, run) and first_pin < run, name
        assert pinned_eeex.VARIABLE in run_env(text), name


def test_parsed_only_files_are_named_but_never_imported_or_loaded():
    for name in WORKFLOWS:
        reached, loaded = workflow_reach(name)
        assert loaded == [], name
        assert [f for f in PARSED_ONLY if f not in reached] == [], name
        assert {f: sorted(n.name for n in reached[f].runs) for f in PARSED_ONLY} == {
            f: sorted(functions) for f, functions in PARSED_ONLY.items()}, name


def test_every_exemption_is_still_needed():
    modules = [m for name in WORKFLOWS for m in workflow_reach(name)[0].values()]
    read = {n for m in modules for n, _ in env_reads(m)}
    provided = set().union(*(run_env(path.read_text(encoding="utf-8")) for path in WORKFLOWS.values()))
    assert sorted(n for n in OPTIONAL if n not in read or n in provided) == []
    strings = {(m.rel, n.value) for m in modules for n in m.nodes() if isinstance(n, ast.Constant)}
    assert sorted(k for k in LOCAL_DATA if k not in strings) == []


def fake_repo(root, files):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


# The harness that failed the alpha.14 release check, loaded the way its two tests loaded it.
BUGGY_HARNESS = '''\
import os
from pathlib import Path

EEEX = Path(os.environ.get("CBMI_EEEX_SOURCE", "C:/tmp/scroll-hook-research-20261009/EEex/EEex/copy/EEex_scripts/EEex_Sprite.lua"))


def wire():
    return EEEX.read_text(encoding="utf-8")
'''
LOADS_THE_HARNESS = '''\
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

CHECK = Path(__file__).resolve().parents[1] / "research/native/serializer_check.py"
_spec = spec_from_file_location("fixture", CHECK)
_fixture = module_from_spec(_spec)
_spec.loader.exec_module(_fixture)
'''


def test_the_alpha14_harness_failure_is_reported(tmp_path):
    root = fake_repo(tmp_path, {"tests/test_loads_harness.py": LOADS_THE_HARNESS,
                                "research/native/serializer_check.py": BUGGY_HARNESS})
    reached, loaded = reach(["tests/test_loads_harness.py"], root, {})
    assert sorted(reached) == ["research/native/serializer_check.py", "tests/test_loads_harness.py"] and loaded == []
    path = "C:/tmp/scroll-hook-research-20261009/EEex/EEex/copy/EEex_scripts/EEex_Sprite.lua"
    assert problems(reached["research/native/serializer_check.py"], {"WEIDU", "WEIDU_BIN", "CBM_EEEX_SOURCE"}) == [
        "research/native/serializer_check.py:4: CBMI_EEEX_SOURCE, which the workflow does not set for the run",
        "research/native/serializer_check.py:4: CBMI_EEEX_SOURCE: read EEex scripts through tests/pinned_eeex.py",
        "research/native/serializer_check.py:4: EEex script path %r outside tests/pinned_eeex.py" % path,
        "research/native/serializer_check.py:4: local path %r" % path,
    ]
    assert problems(reached["tests/test_loads_harness.py"], set()) == []


def test_eeex_scripts_are_asked_for_by_pinned_name(tmp_path):
    root = fake_repo(tmp_path, {"tests/test_asks_eeex.py": (
        "from tests.pinned_eeex import pinned_eeex_script\n\nNAME = 'EEex_Sprite.lua'\n\n\n"
        "def test_scripts(name):\n"
        "    pinned_eeex_script('EEex_Object.lua'), pinned_eeex_script(NAME), pinned_eeex_script(name)\n")})
    module = reach(["tests/test_asks_eeex.py"], root, {})[0]["tests/test_asks_eeex.py"]
    assert [n for n, _ in eeex_requests(module)] == ["EEex_Object.lua", "EEex_Sprite.lua", None]
    assert problems(module, set()) == [
        "tests/test_asks_eeex.py:7: pinned_eeex_script('EEex_Object.lua') asks for no pinned script",
        "tests/test_asks_eeex.py:7: pinned_eeex_script(name) asks for no pinned script",
    ]


def test_environment_variables_and_paths_above_the_checkout_are_reported(tmp_path):
    root = fake_repo(tmp_path, {"tests/test_local_inputs.py": (
        "import os\nfrom pathlib import Path\n\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "OWN = ROOT / 'tools'\n"
        "SIBLING = ROOT.parent / 'chriz-bg-collection'\n"
        "OTHER = Path(__file__).parents[2]\n"
        "UP = ROOT / '../chriz-bg-collection/x'\n"
        "SET = os.environ['WEIDU'], os.getenv('WEIDU_BIN')\n"
        "UNSET = 'CBM_EET_SOURCE' in os.environ\n"
        "SOME = os.environ.get(os.sep)\n"
        "HOME = Path.home() / 'Games'\n"
        "FINE = ('..', 'a..b', '~=', Path(os.environ['WEIDU']).expanduser(), '..' in ROOT.parts)\n")})
    module = reach(["tests/test_local_inputs.py"], root, {})[0]["tests/test_local_inputs.py"]
    assert problems(module, {"WEIDU", "WEIDU_BIN"}) == [
        "tests/test_local_inputs.py:6: a path above the checkout",
        "tests/test_local_inputs.py:7: a path above the checkout",
        "tests/test_local_inputs.py:8: local path '../chriz-bg-collection/x'",
        "tests/test_local_inputs.py:10: CBM_EET_SOURCE, which the workflow does not set for the run",
        "tests/test_local_inputs.py:11: environment variable no literal names: os.environ.get(os.sep)",
        "tests/test_local_inputs.py:12: local path from Path.home()",
    ]


def test_a_loaded_parsed_only_file_is_reported_and_runs_only_its_listed_functions(tmp_path):
    root = fake_repo(tmp_path, {"tests/test_runs_probe.py": "import runpy\n\nrunpy.run_path('research/probe.py')\n",
                                "research/probe.py": "SOURCE = 'C:/tmp/research'\n\n\ndef keep():\n    return 1\n"})
    reached, loaded = reach(["tests/test_runs_probe.py"], root, {"research/probe.py": ("keep",)})
    assert loaded == [("tests/test_runs_probe.py", "research/probe.py")]
    assert problems(reached["research/probe.py"], set()) == []
    assert problems(reach(["research/probe.py"], root, {})[0]["research/probe.py"], set()) == [
        "research/probe.py:1: local path 'C:/tmp/research'"]


def test_run_env_reads_job_step_and_exported_variables():
    text = """\
jobs:
  test:
    env:
      JOB_WIDE: 1
    steps:
      - name: Fetch
        run: echo "EXPORTED=$RUNNER_TEMP/x" >> "$GITHUB_ENV"
      - name: Another step
        env:
          NOT_FOR_THE_RUN: 1
        run: true
      - name: Run
        env:
          STEP_ONLY: 1
        run: |
          export SET_IN_STEP=1
          INLINE=1 python3 -m tools.ci_pytest -q
      - name: Later
        run: echo "LATER=1" >> "$GITHUB_ENV"
"""
    assert run_env(text) == {"JOB_WIDE", "EXPORTED", "STEP_ONLY", "SET_IN_STEP", "INLINE"}
    assert run_env(WORKFLOWS["ci"].read_text(encoding="utf-8")) == {"WEIDU_BIN", "WEIDU", "CBM_EEEX_SOURCE"}
    assert run_env(WORKFLOWS["release"].read_text(encoding="utf-8")) == {
        "WEIDU_BIN", "WEIDU", "CBM_EET_SOURCE", "CBM_EEEX_SOURCE"}


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
