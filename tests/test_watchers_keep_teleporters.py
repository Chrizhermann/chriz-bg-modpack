"""Offline tests for component 697 (cbm_watchers_keep_teleporters)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.test_utility_xp_installer import (
    ROOT,
    SETUP_NAME,
    WEIDU,
    SyntheticGame,
    _file_tree,
    _is_weidu_artifact,
    _write_key_and_bif,
)

COMPONENT = 697
BAF_DIR = ROOT / "chriz-bg-modpack/watchers-keep-teleporters/baf"
EXPECTED_SCRIPTS = (
    [f"CUT202{chr(c)}" for c in range(ord("A"), ord("Z") + 1)]
    + [f"CUT202Z{chr(c)}" for c in range(ord("A"), ord("H") + 1)]
    + ["CUT211A", "CUT246A", "ITPORTAL"]
)

# Minimal IDS tables required for WeiDU to compile and decompile all 37 scripts cleanly
# in a synthetic game without any licensed game files.
IDS_FILES = {
    "ACTION.IDS": """90
1 ActionOverride(O:Actor*,A:Action*)
83 SmallWait(I:Time*)
110 LeaveAreaLUA(S:Area*,S:Parchment*,P:Point*,I:Face*DIR)
115 SetGlobalTimer(S:Name*,S:Area*,I:Time*GTimes)
120 StartCutScene(S:CutScene*)
120 StartCutSceneEx(S:CutScene*,I:evaluateConditions*BOOLEAN)
121 StartCutSceneMode()
122 EndCutSceneMode()
127 CutSceneId(O:Object*)
133 ClearActions(O:Object*)
151 DisplayString(O:Object*,I:StrRef*)
183 MultiPlayerSync()
189 LeaveAreaLUAPanic(S:Area*,S:Parchment*,P:Point*,I:Face*DIR)
272 CreateVisualEffect(S:Object*,P:Location*)
273 CreateVisualEffectObject(S:Effect*,O:Target*)
350 LeaveAreaLUAEntry(S:Area*,S:Entry*,P:Point*,I:Face*DIR)
351 LeaveAreaLUAPanicEntry(S:Area*,S:Entry*,P:Point*,I:Face*DIR)
""",
    "TRIGGER.IDS": """IDS V1.0
0x00D6 WalkedToTrigger(O:Object*)
0x400F Global(S:Name*,S:Area*,I:Value*)
0x4023 True()
0x4041 GlobalTimerNotExpired(S:Name*,S:Area*)
0x4042 PartyHasItem(S:Item*)
0x4051 Dead(S:Name*)
0x4089 OR(I:OrCount*)
""",
    "OBJECT.IDS": """IDS V1.0
0 Nothing
1 Myself
17 LastTrigger
21 Player1
22 Player2
23 Player3
24 Player4
25 Player5
26 Player6
""",
    "BOOLEAN.IDS": "5\n0 FALSE\n1 TRUE\n",
    "DIR.IDS": "IDS\n0 S\n2 SW\n4 W\n6 NW\n8 N\n10 NE\n12 E\n14 SE\n",
    "GTIMES.IDS": "IDS\n120 TWO_MINUTES\n",
}


def _game_files(root: Path) -> dict[str, bytes]:
    return {
        name: payload
        for name, payload in _file_tree(root).items()
        if not _is_weidu_artifact(name)
    }


def _stage_ids(game: SyntheticGame) -> None:
    for name, text in IDS_FILES.items():
        (game.override / name.lower()).write_text(text, encoding="ascii")


def _run_component(game: SyntheticGame, *, uninstall: bool = False, expect_ok: bool = True) -> str:
    assert WEIDU is not None
    result = subprocess.run(
        [
            str(WEIDU),
            SETUP_NAME,
            "--game", str(game.root),
            "--force-uninstall-list" if uninstall else "--force-install-list",
            str(COMPONENT),
            "--language", "0",
            "--use-lang", "en_us",
            "--no-exit-pause",
            "--noautoupdate",
            "--no-auto-tp2",
            "--quick-log",
        ],
        cwd=game.root,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=90,
        check=False,
    )
    transcript = result.stdout + result.stderr
    if expect_ok:
        assert result.returncode == 0, transcript
        assert "ERROR:" not in transcript and "INSTALLED WITH WARNINGS" not in transcript, transcript
    return transcript


def _decompile_bcs(game: SyntheticGame, resref: str, out_dir: Path) -> str:
    assert WEIDU is not None
    bcs_path = game.override / f"{resref.lower()}.bcs"
    assert bcs_path.is_file(), f"missing compiled {bcs_path}"
    result = subprocess.run(
        [str(WEIDU), "--noautoupdate", "--game", str(game.root), "--out", str(out_dir), str(bcs_path)],
        cwd=game.root,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=30,
        check=True,
    )
    assert "ERROR:" not in result.stdout + result.stderr, result.stdout + result.stderr
    expected_name = f"{resref.upper()}.BAF"
    for candidate in out_dir.iterdir():
        if candidate.name.upper() == expected_name:
            return candidate.read_text(encoding="latin1")
    raise FileNotFoundError(out_dir / expected_name)


def test_all_authored_baf_sources_present_and_stall_free():
    actual = sorted(p.stem.upper() for p in BAF_DIR.glob("*.baf"))
    assert actual == sorted(EXPECTED_SCRIPTS)
    for name in EXPECTED_SCRIPTS:
        text = (BAF_DIR / f"{name.lower()}.baf").read_text(encoding="utf-8")
        assert "FadeToColor" not in text, name
        assert "FadeFromColor" not in text, name
        assert not re.search(r"(?m)^\s*Wait\(", text), name
        if name == "ITPORTAL":
            assert text.count('StartCutSceneEx("cut202q",FALSE)') == 2
            assert 'CreateVisualEffect("ICRMPAR2",[1450.1156])' in text
        elif name == "CUT202Z":
            assert 'StartCutSceneEx("cut207a",FALSE)' in text
            assert 'CreateVisualEffectObject("ICRMPARI",Player1)' in text
            assert len(re.findall(r"LeaveAreaLUA", text)) == 7
        else:
            assert 'CreateVisualEffectObject("ICRMPARI",Player1)' in text
            assert "EndCutSceneMode()" in text
            assert len(re.findall(r"LeaveAreaLUA", text)) == 7


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
def test_weidu_parse_check():
    result = subprocess.run(
        [str(WEIDU), "--noautoupdate", "--nogame", "--parse-check", "TPA",
         "chriz-bg-modpack/lib/cbm_watchers_keep_teleporters.tpa"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=30,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ERROR" not in output and "WARNING" not in output, output


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
@pytest.mark.parametrize("game_type", ("bg2ee", "eet"))
def test_install_we_overwrite_decompile_and_uninstall(tmp_path, game_type):
    game = SyntheticGame(tmp_path / "game", game=game_type, eeex=False)
    _stage_ids(game)
    # Seed mutated/third-party pre-existing compiled overrides to verify We Overwrite.
    for mutated in ("cut202a.bcs", "cut202z.bcs", "cut246a.bcs", "itportal.bcs"):
        (game.override / mutated).write_bytes(b"SC\r\nCR\r\nCR\r\nSC\r\n")
    before = _game_files(game.root)

    for run_idx in range(2):
        transcript = _run_component(game)
        assert "SUCCESSFULLY INSTALLED" in transcript
        assert re.search(rf"(?m)#0\s+#{COMPONENT}\b", game.active_log())
        if run_idx == 0:
            after_first = _game_files(game.root)
        else:
            assert _game_files(game.root) == after_first

    dec_dir = tmp_path / "decompiled"
    dec_dir.mkdir()
    for name in EXPECTED_SCRIPTS:
        decompiled = _decompile_bcs(game, name, dec_dir)
        assert "FadeToColor" not in decompiled, name
        assert "FadeFromColor" not in decompiled, name
        assert not re.search(r"(?m)^\s*Wait\(", decompiled), name
        if name == "ITPORTAL":
            assert 'CreateVisualEffect("ICRMPAR2",[1450.1156])' in decompiled
            assert 'PartyHasItem("PLOT01B")' in decompiled
        elif name == "CUT202Z":
            assert 'StartCutSceneEx("cut207a",FALSE)' in decompiled
            assert 'CreateVisualEffectObject("ICRMPARI",Player1)' in decompiled
        else:
            assert 'CreateVisualEffectObject("ICRMPARI",Player1)' in decompiled
            assert "EndCutSceneMode()" in decompiled

    transcript = _run_component(game, uninstall=True)
    assert "SUCCESSFULLY REMOVED" in transcript
    assert not re.search(rf"(?m)#0\s+#{COMPONENT}\b", game.active_log())
    assert _game_files(game.root) == before


def _make_iwdee_game(root: Path, *, eeex: bool) -> SyntheticGame:
    game = SyntheticGame(root, game="bg2ee", eeex=eeex)
    data_dir = root / "data"
    for f in data_dir.iterdir():
        f.unlink()
    data_dir.rmdir()
    (root / "chitin.key").unlink()
    _write_key_and_bif(root, [("HOWPARTY", "2DA", b"2DA V1.0\r\n*\r\n")])
    return game


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
@pytest.mark.parametrize("game_type", ("bgee", "iwdee"))
def test_non_bg2_engines_are_skipped_by_predicate(tmp_path, game_type):
    if game_type == "iwdee":
        game = _make_iwdee_game(tmp_path / "game", eeex=False)
    else:
        game = SyntheticGame(tmp_path / "game", game=game_type, eeex=False)
    _stage_ids(game)
    before = _game_files(game.root)
    transcript = _run_component(game, expect_ok=False)
    assert "Instant Watcher's Keep teleporters require BG2:EE or EET." in transcript
    assert not re.search(rf"(?m)#0\s+#{COMPONENT}\b", game.active_log())
    assert _game_files(game.root) == before
