"""Install component 620 with real WeiDU; no licensed game data is required."""
import os
import subprocess
from pathlib import Path

import pytest

from test_utility_xp_installer import (
    ROOT, SETUP_NAME, WEIDU, SyntheticGame, _file_tree, _is_weidu_artifact,
)

pytestmark = pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")

# Minimal, authored IDS fixtures for the source and installed script blocks.
IDS = {
    "ACTION.IDS": "IDS V1.0\n30 SetGlobal(S:Name*,S:Area*,I:Value*)\n"
                  "86 SetInterrupt(I:State*Boolean)\n"
                  "370 ChangeStat(O:Object*,I:Stat*Stats,I:Value*,I:Modifier*Statmod)\n"
                  "472 EEex_LuaAction(S:Chunk*)\n",
    "TRIGGER.IDS": "IDS V1.0\n0x400F Global(S:Name*,S:Area*,I:Value*)\n"
                   "0x4043 InParty(O:Object*)\n0x407E AreaCheck(S:ResRef*)\n"
                   "0x4089 OR(I:OrCount*)\n",
    "OBJECT.IDS": "IDS V1.0\n1 Myself\n",
    "BOOLEAN.IDS": "IDS V1.0\n0 FALSE\n1 TRUE\n",
    "STATS.IDS": "IDS V1.0\n44 XP\n",
    "STATMOD.IDS": "IDS V1.0\n1 ADD\n2 SET\n",
}
ORIGINAL = """
IF
  Global("BD_JOINXP","LOCALS",0)
  InParty(Myself)
THEN
  RESPONSE #100
    ChangeStat(Myself,XP,1250000,SET)
    SetGlobal("BD_JOINXP","LOCALS",2)
END
IF
  Global("UnrelatedQuest","LOCALS",0)
THEN
  RESPONSE #100
    SetGlobal("UnrelatedQuest","LOCALS",1)
END
"""


def run_weidu(game, *args):
    result = subprocess.run(
        [str(WEIDU), "--noautoupdate", "--no-exit-pause", "--game", str(game.root),
         "--use-lang", "en_US", *args],
        cwd=game.root, capture_output=True, text=True, timeout=60,
    )
    transcript = result.stdout + result.stderr
    assert result.returncode == 0, transcript
    return transcript


def make_game(tmp_path, *, game_type="bg2ee", eeex=True, old_helper=False):
    game = SyntheticGame(tmp_path / "game", game=game_type, eeex=eeex)
    # WeiDU's Linux EE detection requires the physical folder name en_us.
    if os.name != "nt" and (game.root / "lang/en_US").is_dir():
        (game.root / "lang/en_US").rename(game.root / "lang/en_us")
    for name, text in IDS.items():
        (game.override / name).write_text(text, encoding="ascii")
    # These object-selector tables are requested by the BAF compiler.
    for name in ("EA", "GENERAL", "RACE", "CLASS", "SPECIFIC", "GENDER", "ALIGN"):
        (game.override / (name + ".IDS")).write_text("IDS V1.0\n", encoding="ascii")
    (game.root / "imoen2.baf").write_text(ORIGINAL, encoding="ascii")
    run_weidu(game, "--out", str(game.override), "imoen2.baf")
    if old_helper:
        (game.override / "M_CBMIXP.lua").write_bytes(b"-- original helper\r\n\xff")
    game.before = _file_tree(game.root)
    return game


def install(game):
    return run_weidu(game, SETUP_NAME, "--language", "0", "--force-install-list", "620")


def assert_restored(game):
    actual = {name: data for name, data in _file_tree(game.root).items()
              if not _is_weidu_artifact(name)}
    expected = {name: data for name, data in game.before.items()
                if not _is_weidu_artifact(name)}
    assert actual == expected


@pytest.mark.parametrize("game_type,old_helper", [("bg2ee", False), ("eet", True)])
def test_install_preserves_script_and_uninstall_restores_all_bytes(tmp_path, game_type, old_helper):
    game = make_game(tmp_path, game_type=game_type, old_helper=old_helper)
    original_script = game.before["OVERRIDE/IMOEN2.BCS"]
    transcript = install(game)
    assert "SUCCESSFULLY INSTALLED" in transcript
    actual = _file_tree(game.root)
    changed = {name for name in set(actual) | set(game.before)
               if actual.get(name) != game.before.get(name) and not _is_weidu_artifact(name)}
    assert changed == {"OVERRIDE/IMOEN2.BCS", "OVERRIDE/M_CBMIXP.LUA"}
    helper = ROOT / "chriz-bg-modpack/imoen-xp/M_CBMIXP.lua"
    assert actual["OVERRIDE/M_CBMIXP.LUA"] == helper.read_bytes()
    # EXTEND_TOP must preserve every original compiled block, byte for byte.
    assert actual["OVERRIDE/IMOEN2.BCS"].endswith(original_script.removeprefix(b"SC\n"))
    # Decompile into a separate directory so the fixture source remains intact.
    inspection = game.root / "inspection"
    inspection.mkdir()
    result = subprocess.run(
        [str(WEIDU), "--noautoupdate", "--no-exit-pause", "--game", str(game.root),
         "--use-lang", "en_US", str(game.override / "imoen2.bcs")],
        cwd=inspection, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    source = next(inspection.glob("*.baf")).read_text()
    assert source.index('Global("CBM_ImoenSpellholdXP"') < source.index('Global("BD_JOINXP"')
    assert source.count("CBM_ImoenXP_Apply(EEex_LuaAction_Object)") == 1
    assert all(f'AreaCheck("{area}")' in source for area in ("AR1512", "AR1513", "AR1514"))
    assert 'InParty(Myself)' in source
    assert 'SetGlobal("UnrelatedQuest","LOCALS",1)' in source
    # Inspection files are test artifacts, not installer publications.
    for path in inspection.iterdir():
        path.unlink()
    inspection.rmdir()
    transcript = run_weidu(game, SETUP_NAME, "--language", "0", "--force-uninstall-list", "620")
    assert "SUCCESSFULLY REMOVED" in transcript
    assert_restored(game)


@pytest.mark.parametrize("missing", ["eeex", "script", "action"])
def test_missing_prerequisites_make_no_game_changes(tmp_path, missing):
    game = make_game(tmp_path, eeex=missing != "eeex")
    if missing == "script":
        (game.override / "imoen2.bcs").unlink()
    if missing == "action":
        path = game.override / "ACTION.IDS"
        path.write_text(IDS["ACTION.IDS"].replace("472 EEex_LuaAction(S:Chunk*)\n", ""))
    game.before = _file_tree(game.root)
    # Failed predicate skips; a missing action discovered during install rolls back.
    result = subprocess.run(
        [str(WEIDU), SETUP_NAME, "--noautoupdate", "--no-exit-pause", "--game", str(game.root),
         "--use-lang", "en_US", "--language", "0", "--force-install-list", "620"],
        cwd=game.root, capture_output=True, text=True, timeout=60,
    )
    transcript = result.stdout + result.stderr
    assert "SUCCESSFULLY INSTALLED" not in transcript
    expected = "NOT INSTALLED DUE TO ERRORS" if missing == "action" else "SKIPPING:"
    assert expected in transcript
    assert "EEex" in transcript if missing != "script" else "IMOEN2.BCS" in transcript
    assert_restored(game)
