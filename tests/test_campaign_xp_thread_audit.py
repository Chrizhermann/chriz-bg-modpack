"""Static check: the committed main-thread audit listing claims only what its call graph proves.

research/xp-banking-native/main_thread_audit.py follows only resolved edges of
Baldur.exe's call graph and counts, but does not follow, the indirect calls and
jumps it cannot resolve. Its RESULT line may therefore read PASS only when no
check failed and no route stays unresolved. This test parses the committed
listing (no game binaries needed) and fails unless its verdict is consistent:

* a [FAIL] check line requires RESULT: FAIL, and the head counts the checks;
* a nonzero "stay unresolved" count in section B, or unresolved debug-window
  call sites in section F, forbid PASS, and every such route must appear in the
  RESULT block as "unresolved: <route>: <count> <unit>" with the same count;
* the RESULT block equals what the script's own verdict() returns for them.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "research" / "xp-banking-native"
SCRIPT = AUDIT / "main_thread_audit.py"
LISTING = AUDIT / "main-thread-audit-2.7.3.txt"

CHECK = re.compile(r"^  \[(ok|FAIL)\] +(.*)$")
SECTION = re.compile(r"^([A-F])\. ")
B_UNRESOLVED = re.compile(r"\b(\d+) indirect calls/jumps in them stay unresolved\b")
B_LABEL = re.compile(r"^B (.+?): reaches none of the \d+ targets")
F_DEBUG = re.compile(r"\bits (\d+|\?) indirect call sites are unresolved\b")
HEAD = re.compile(r"^RESULT: (PASS|FAIL|INCONCLUSIVE) \((\d+) checks, (\d+) failed\b(.*)\)$")
DEBUG_LABEL, DEBUG_UNIT, B_UNIT = "EEex debug-window thread", "indirect call sites", "indirect calls/jumps"


def sections(lines):
    """{letter: [lines]} for the lettered sections; the RESULT block is not part of any section."""
    res, cur = {}, None
    for line in lines:
        m = SECTION.match(line)
        if m:
            cur = res.setdefault(m.group(1), [])
        elif line.startswith("RESULT: "):
            cur = None
        if cur is not None:
            cur.append(line)
    return res


def result_block(lines):
    starts = [i for i, line in enumerate(lines) if line.startswith("RESULT: ")]
    assert len(starts) == 1, "the listing has exactly one RESULT line (found %d)" % len(starts)
    i = starts[0]
    block = [lines[i]]
    for line in lines[i + 1:]:
        if not line.startswith("  "):
            break
        block.append(line)
    return block


def open_routes(lines):
    """[(route, count, unit)] for every route the listing reports as unresolved, in listing order."""
    sec, routes = sections(lines), []
    b = sec.get("B", [])
    for i, line in enumerate(b):
        m = B_UNRESOLVED.search(line)
        if not m:
            continue
        label = next((B_LABEL.match(c.group(2)).group(1) for c in map(CHECK.match, b[i + 1:])
                      if c and B_LABEL.match(c.group(2))), None)
        assert label is not None, "no B check names the route of: " + line.strip()
        routes.append((label, int(m.group(1)), B_UNIT))
    f = " ".join(" ".join(sec.get("F", [])).split())
    m = F_DEBUG.search(f)
    if m:
        routes.append((DEBUG_LABEL, -1 if m.group(1) == "?" else int(m.group(1)), DEBUG_UNIT))
    return routes


def problems(text):
    """Every inconsistency between the listing's checks, its open routes and its RESULT block."""
    lines = text.split("\n")
    checks = [m.groups() for m in map(CHECK.match, lines) if m]
    failed = [what for status, what in checks if status == "FAIL"]
    routes = open_routes(lines)
    block = result_block(lines)
    head = HEAD.match(block[0])
    if not head:
        return ["RESULT line has an unknown form: " + block[0]]
    verdict, nchecks, nfailed = head.group(1), int(head.group(2)), int(head.group(3))
    found = []
    if nchecks != len(checks):
        found.append("RESULT counts %d checks, the listing has %d" % (nchecks, len(checks)))
    if nfailed != len(failed):
        found.append("RESULT counts %d failed checks, the listing has %d" % (nfailed, len(failed)))
    if failed and verdict != "FAIL":
        found.append("a check failed but RESULT is %s" % verdict)
    if not failed and verdict == "FAIL":
        found.append("no check failed but RESULT is FAIL")
    if any(n < 0 for r, n, u in routes) and verdict != "FAIL":
        found.append("the debug-window thread was not analysed but RESULT is %s" % verdict)
    opened = [(r, n, u) for r, n, u in routes if n > 0]
    if opened and verdict == "PASS":
        found.append("RESULT is PASS although open routes stay unresolved (%d)" % len(opened))
    if not opened and not failed and verdict != "PASS":
        found.append("nothing failed and no route is open but RESULT is %s" % verdict)
    listed = [line for line in block[1:] if line.startswith("  unresolved: ")]
    for r, n, u in opened:
        want = "  unresolved: %s: %d %s" % (r, n, u)
        if want not in listed:
            found.append("RESULT block lacks %r" % want.strip())
    extra = set(listed) - {"  unresolved: %s: %d %s" % x for x in opened}
    found += ["RESULT block lists a route the listing does not report: %r" % x.strip() for x in sorted(extra)]
    for what in failed:
        if "  failed: " + what not in block:
            found.append("RESULT block does not repeat the failed check %r" % what)
    return found


def load_script():
    spec = importlib.util.spec_from_file_location("main_thread_audit", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- the committed listing

def test_committed_listing_verdict_is_consistent_with_its_checks_and_open_routes():
    assert problems(LISTING.read_text(encoding="ascii")) == []


def test_committed_listing_is_ascii_with_lf_line_ends():
    raw = LISTING.read_bytes()
    raw.decode("ascii")
    assert b"\r" not in raw and raw.endswith(b"\n")


def test_committed_result_block_is_what_the_script_verdict_returns():
    lines = LISTING.read_text(encoding="ascii").split("\n")
    checks = [m.groups() for m in map(CHECK.match, lines) if m]
    failed = [what for status, what in checks if status == "FAIL"]
    assert load_script().verdict(len(checks), failed, open_routes(lines)) == result_block(lines)


# ---------------------------------------------------------------- the consistency check itself

def _committed():
    return LISTING.read_text(encoding="ascii")


def _replace_result(text, block):
    lines = text.split("\n")
    old = result_block(lines)
    i = lines.index(old[0])
    return "\n".join(lines[:i] + block + lines[i + len(old):])


def test_pass_with_open_routes_is_reported():
    lines = _committed().split("\n")
    n = sum(1 for line in lines if CHECK.match(line))
    found = problems(_replace_result(_committed(), ["RESULT: PASS (%d checks, 0 failed)" % n]))
    assert any("RESULT is PASS although" in p for p in found)
    assert any("unresolved: talk_base::Thread::PreRun: 103 indirect calls/jumps" in p for p in found)
    assert any("unresolved: libjingle/glue: 2306 indirect calls/jumps" in p for p in found)
    assert any("unresolved: EEex debug-window thread: 80 indirect call sites" in p for p in found)


def test_a_route_listed_with_another_count_is_reported():
    text = _committed().replace("  unresolved: libjingle/glue: 2306 ", "  unresolved: libjingle/glue: 2305 ")
    found = problems(text)
    assert any("lacks 'unresolved: libjingle/glue: 2306" in p for p in found)
    assert any("does not report: 'unresolved: libjingle/glue: 2305" in p for p in found)


def test_a_failed_check_requires_fail():
    text = _committed().replace("  [ok]   B SDL_RunAudio: reaches none", "  [FAIL] B SDL_RunAudio: reaches none", 1)
    found = problems(text)
    assert any("a check failed but RESULT is INCONCLUSIVE" in p for p in found)
    assert any("counts 0 failed checks, the listing has 1" in p for p in found)


def test_unresolved_debug_window_sites_alone_forbid_pass():
    text = re.sub(r"\d+ indirect calls/jumps in them stay unresolved", "0 indirect calls/jumps in them stay unresolved",
                  _committed())
    n = sum(1 for line in text.split("\n") if CHECK.match(line))
    found = problems(_replace_result(text, ["RESULT: PASS (%d checks, 0 failed; no resolved path from another thread "
                                            "to a target; no route stays unresolved)" % n]))
    assert found == ["RESULT is PASS although open routes stay unresolved (1)",
                     "RESULT block lacks 'unresolved: EEex debug-window thread: 80 indirect call sites'"]


# ---------------------------------------------------------------- the script's verdict()

@pytest.fixture(scope="module")
def verdict():
    return load_script().verdict


def test_verdict_passes_only_without_failures_and_open_routes(verdict):
    assert verdict(3, [], []) == [
        "RESULT: PASS (3 checks, 0 failed; no resolved path from another thread to a target; no route stays unresolved)"]
    assert verdict(3, [], [("WINMM audio callbacks", 0, B_UNIT)])[0].startswith("RESULT: PASS (3 checks, 0 failed;")


def test_verdict_is_inconclusive_while_a_route_stays_unresolved(verdict):
    assert verdict(97, [], [("a", 0, B_UNIT), ("talk_base::Thread::PreRun", 103, B_UNIT), (DEBUG_LABEL, 80, DEBUG_UNIT)]) == [
        "RESULT: INCONCLUSIVE (97 checks, 0 failed; no resolved path from another thread to a target; "
        "2 routes stay unresolved)",
        "  unresolved: talk_base::Thread::PreRun: 103 indirect calls/jumps",
        "  unresolved: EEex debug-window thread: 80 indirect call sites"]
    assert verdict(5, [], [("x", 1, B_UNIT)])[0].endswith("; 1 route stays unresolved)")


def test_verdict_fails_on_a_failed_check_and_still_lists_open_routes(verdict):
    assert verdict(4, ["B x: reaches none"], [("x", 2, B_UNIT)]) == [
        "RESULT: FAIL (4 checks, 1 failed)",
        "  failed: B x: reaches none",
        "  unresolved: x: 2 indirect calls/jumps"]
