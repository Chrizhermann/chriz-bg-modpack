"""Component 239: EET's own join-XP catch-up where a joinable NPC's script lacks it.

Real WeiDU installs on synthetic EET games, plus a bounded model of the emitted
BAF (not an engine playtest). Fixtures are authored data shaped like EET's
tables and transition scripts; no licensed game resources or saved actors.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import re
import struct
import subprocess

import pytest

from tests.test_collection_defaults import make_cre
from tests.test_utility_xp_installer import (
    SETUP_NAME, WEIDU, SyntheticGame, _file_tree, _is_weidu_artifact,
)


pytestmark = pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
COMPONENT = 239
TIERS = (125_000, 250_000, 500_000, 750_000, 1_000_000, 1_250_000)
# EET's TRIGGER.IDS lists trigger 0x4043 five times; WeiDU decompiles it with the
# last name, so installed scripts read IsValidForPartyDialogue(Myself).
IDS = {
    "trigger": "IDS V1.0\n0x400F Global(S:Name*,S:Area*,I:Value*)\n"
               "0x4043 InParty(O:Object*)\n0x4034 XPGT(O:Object*,I:XP*)\n"
               "0x4035 XPLT(O:Object*,I:XP*)\n0x4036 CheckStat(O:Object*,I:Value*,I:Stat*Stats)\n"
               "0x4089 OR(I:OrCount*)\n0x4023 True()\n0x40D3 InPartyAllowDead(O:Object*)\n"
               "0x4043 IfValidForPartyDialog(O:Object*)\n0x4043 IfValidForPartyDialogue(O:Object*)\n"
               "0x4043 IsValidForPartyDialog(O:Object*)\n0x4043 IsValidForPartyDialogue(O:Object*)\n",
    "action": "IDS V1.0\n1 ActionOverride(O:Actor*,A:Action*)\n"
              "7 CreateCreature(S:NewObject*,P:Location*,I:Face*)\n"
              "30 SetGlobal(S:Name*,S:Area*,I:Value*)\n36 Continue()\n"
              "82 ChangeAIScript(S:ScriptFile*,I:Level*Scrlev)\n86 SetInterrupt(I:State*Boolean)\n"
              "160 ApplySpellRES(S:RES*,O:Target*)\n"
              "370 ChangeStat(O:Object*,I:Stat*Stats,I:Value*,I:Modifier*Statmod)\n",
    "object": "IDS V1.0\n1 Myself\n21 Player1\n",
    "boolean": "IDS V1.0\n0 FALSE\n1 TRUE\n",
    "stats": "IDS V1.0\n44 XP\n34 LEVEL\n",
    "statmod": "IDS V1.0\n1 ADD\n2 SET\n",
    "scrlev": "IDS V1.0\n0 OVERRIDE\n1 AREA\n2 SPECIFICS\n4 CLASS\n5 RACE\n6 GENERAL\n7 DEFAULT\n",
}
# Shaped like EET's: PDIALOG is not the first column, the SoA table has a short
# row (Safana in Amn adds three of seven columns), the ToB table names only
# three columns, and both use a "multig" default value.
CAMPAIGN = (
    "2DA            V1.0\n*\n"
    "               WORLDSCRIPT    DESCRIPTION    NPCLEVEL       PDIALOG        SAVE_DIR\n"
    "SOA            BALDUR         -1             *              PDIALOG        save\n"
    "TOB            BALDUR25       -1             *              25DIALOG       save\n"
    "BG1            BALDUR         -1             *              BGDIALOG       save\n"
    "BP1            BALDUR         -1             *              *\n"
)
SOA_TABLE = (
    "2DA V1.0\nmultig\n"
    "         POST_DIALOG_FILE JOIN_DIALOG_FILE DREAM_SCRIPT_FILE 25POST_DIALOG_FILE"
    " 25JOIN_DIALOG_FILE 25DREAM_SCRIPT_FILE 25OVERRIDE_SCRIPT_FILE\n"
    "AERIE    AERIEP AERIEJ AERIED *** *** *** ***\n"
    "WILSON   WILSONP WILSONJ WILSOND *** *** *** ***\n"
    "YOSHIMO  YOSHP YOSHJ YOSHD *** *** *** ***\n"
    "K#Sarah  K#SarahP K#SarahJ K#SarahD *** *** *** ***\n"
    "KIVAN    KIVANP KIVANJ KIVAND\n"
    "SAFANA   SAFANP SAFANJ SAFAND\n"
)
TOB_TABLE = (
    "2DA V1.0\nmultig\n"
    "         POST_DIALOG_FILE JOIN_DIALOG_FILE DREAM_SCRIPT_FILE\n"
    "AERIE    AERIE25P AERIE25J AERIE25D\n"
    "WILSON   WILSONP WILSONJ WILSOND\n"
    "YOSHIMO  YOSHP YOSHJ YOSHD\n"
    "K#SARAH  K#Sar25P K#SARAHJ K#Sar25D\n"
    "SAFANA   SAFANP SAFANJ SAFAND\n"
)
STORY = (
    'IF\n Global("QuestAlpha","LOCALS",0)\nTHEN\n RESPONSE #100\n'
    ' SetGlobal("QuestAlpha","LOCALS",1)\n Continue()\nEND\n'
    'IF\n Global("QuestBeta","LOCALS",0)\nTHEN\n RESPONSE #100\n'
    ' SetGlobal("QuestBeta","LOCALS",1)\nEND\n'
)


def party_block(dv):
    # EET_NPC_TRANSITION's party-et block, which marks the SoA override script.
    return (f'IF\n Global("{dv}PartyBG2","GLOBAL",0)\n InPartyAllowDead(Myself)\nTHEN\n'
            f' RESPONSE #100\n SetGlobal("{dv}PartyBG2","GLOBAL",1)\n Continue()\nEND\n')


def ladder(variable="BD_JOINXP"):
    # Beamdog's SoA ladder as installed for vanilla NPCs, catch-all included.
    blocks = []
    for tier in reversed(TIERS):
        blocks.append(f'IF\n Global("{variable}","LOCALS",0)\n InParty(Myself)\n XPGT(Player1,{tier - 1})\n'
                      f' XPLT(Myself,{tier})\nTHEN\n RESPONSE #100\n SetInterrupt(FALSE)\n'
                      f' SetGlobal("{variable}","LOCALS",1)\n ChangeStat(Myself,XP,{tier},SET)\n'
                      ' SetInterrupt(TRUE)\nEND\n')
    blocks.append(f'IF\n Global("{variable}","LOCALS",0)\n InParty(Myself)\n XPLT(Player1,89001)\nTHEN\n'
                  f' RESPONSE #100\n SetInterrupt(FALSE)\n SetGlobal("{variable}","LOCALS",1)\n'
                  ' SetInterrupt(TRUE)\nEND\n')
    blocks.append(f'IF\n Global("{variable}","LOCALS",0)\n InParty(Myself)\nTHEN\n RESPONSE #100\n'
                  f' SetInterrupt(FALSE)\n SetGlobal("{variable}","LOCALS",1)\n SetInterrupt(TRUE)\nEND\n')
    return "".join(blocks)


def raise_block(xp=2_500_000, variable="BD_JOINXP"):
    # EET's ToB raise (EET_functions.tph), which EET appends to ToB scripts.
    return (f'IF\n Global("{variable}","LOCALS",0)\n InParty(Myself)\n XPLT(Myself,{xp})\nTHEN\n'
            f' RESPONSE #100\n SetInterrupt(FALSE)\n SetGlobal("{variable}","LOCALS",1)\n'
            f' ChangeStat(Myself,XP,{xp},SET)\n SetInterrupt(TRUE)\nEND\n')


SCRIPTS = {
    # SoA: Sarah (SarahToB) has EET's party block and no catch-up.
    "K#SARAH": party_block("K#SARAH") + STORY,
    # SoA: vanilla NPCs have Beamdog's ladder; their ToB scripts EET's raise.
    "AERIE": party_block("Aerie") + STORY + ladder(),
    "AERI25": STORY + raise_block(),
    "K#SARA25": STORY + raise_block(),
    # Wilson keeps one script for SoA and ToB; its catch-all completes BD_JOINXP
    # before EET's raise can run.
    "WILSON": party_block("WILSON") + STORY + ladder() + raise_block(),
    # Yoshimo's ToB-start creature keeps his SoA script.
    "YOSHIMO": party_block("Yoshimo") + STORY + ladder(),
    # Safana in Amn moves her BG1 actor without EET's NPC transition.
    "SAFANA2": STORY,
    "CHGOOD": STORY,
    "AR4000": (
        'IF\n InPartyAllowDead("K#SARAH")\nTHEN\n RESPONSE #100\n'
        ' ActionOverride("K#SARAH",ChangeAIScript("K#SARA25",OVERRIDE))\nEND\n'
        'IF\n InPartyAllowDead("Aerie")\nTHEN\n RESPONSE #100\n'
        ' ActionOverride("Aerie",ChangeAIScript("AERI25",OVERRIDE))\nEND\n'
        'IF\n InPartyAllowDead("Wilson")\nTHEN\n RESPONSE #100\n'
        ' ActionOverride("WILSON",ChangeAIScript("WILSON",OVERRIDE))\nEND\n'
        'IF\n Global("Unrelated","GLOBAL",0)\nTHEN\n RESPONSE #100\n'
        ' ActionOverride("Commoner",ChangeAIScript("CHGOOD",OVERRIDE))\nEND\n'
    ),
    "AR4500": (
        'IF\n Global("K#SARAHSummoned","GLOBAL",1)\nTHEN\n RESPONSE #100\n'
        ' ActionOverride("K#SARAH",ChangeAIScript("K#SARA25",OVERRIDE))\n'
        ' ActionOverride("K#SARAH",SetGlobal("BD_JOINXP","LOCALS",0))\nEND\n'
        'IF\n Global("YoshimoSummoned","GLOBAL",1)\nTHEN\n RESPONSE #100\n'
        ' CreateCreature("YOSHI12",[100.100],0)\nEND\n'
        'IF\n Global("Challenge","GLOBAL",1)\nTHEN\n RESPONSE #100\n'
        ' CreateCreature("CHGOOD01",[200.200],0)\nEND\n'
    ),
}
CREATURES = {"YOSHI12": ("Yoshimo", "YOSHIMO"), "CHGOOD01": ("CHGOOD01", "CHGOOD")}
PATCHED = {"K#SARAH": "soa", "WILSON": "tob", "YOSHIMO": "tob"}


def tree(game):
    return {name: data for name, data in _file_tree(game.root).items()
            if not _is_weidu_artifact(name)}


def invoke(game, *args, cwd=None):
    result = subprocess.run(
        [str(WEIDU), "--no-auto-tp2", "--noautoupdate", "--no-exit-pause",
         "--game", str(game.root), "--use-lang", "en_us", *args],
        cwd=cwd or game.root, capture_output=True, text=True, timeout=120,
    )
    return result, result.stdout + result.stderr


def install(game, component=COMPONENT, *, uninstall=False):
    return invoke(game, SETUP_NAME, "--language", "0",
                  "--force-uninstall-list" if uninstall else "--force-install-list", str(component))


def compile_script(game, name, source):
    path = game.root / f"{name.lower()}.baf"
    path.write_text(source, encoding="ascii")
    result, transcript = invoke(game, "--out", str(game.override), path.name)
    assert result.returncode == 0, transcript
    path.unlink()


def decompile_script(game, name):
    inspection = game.root.parent / f"inspect-{name.lower().replace('#', '_')}"
    inspection.mkdir(exist_ok=True)
    for old in inspection.glob("*.baf"):
        old.unlink()
    result, transcript = invoke(game, str(game.override / f"{name.lower()}.bcs"), cwd=inspection)
    assert result.returncode == 0, transcript
    return next(inspection.glob("*.baf")).read_text(encoding="utf-8")


def creature(dv, script):
    data = bytearray(make_cre(class_id=0, kit=0, dv=dv, xp=440_000, seed=11))
    data[0x248:0x250] = script.encode("ascii").ljust(8, b"\0")
    return bytes(data)


def make_game(tmp_path, *, sr=False, scripts=None, tables=None, game_type="eet"):
    game = SyntheticGame(tmp_path / "game", game=game_type, eeex=False)
    for name, source in IDS.items():
        (game.override / f"{name}.ids").write_text(source, encoding="ascii")
    for name in ("ea", "general", "race", "class", "specific", "gender", "align"):
        (game.override / f"{name}.ids").write_text("IDS V1.0\n", encoding="ascii")
    if sr:
        (game.override / "dvimhere.mrk").write_bytes(b"synthetic SR presence")
    for name, text in {"campaign": CAMPAIGN, "pdialog": SOA_TABLE, "25dialog": TOB_TABLE,
                       **(tables or {})}.items():
        if text is not None:
            (game.override / f"{name}.2da").write_text(text, encoding="ascii")
    for name, source in {**SCRIPTS, **(scripts or {})}.items():
        if source is not None:
            compile_script(game, name, source)
    for name, (dv, script) in CREATURES.items():
        (game.override / f"{name.lower()}.cre").write_bytes(creature(dv, script))
    game.before = tree(game)
    return game


def script_blocks(source):
    cleaned = re.sub(r"//[^\n]*", "", source)
    blocks = []
    cursor = 0
    for match in re.finditer(r"\bIF\b(.*?)\bTHEN\b\s*RESPONSE\s+#100\b(.*?)\bEND\b", cleaned, re.S):
        assert not cleaned[cursor:match.start()].strip()
        blocks.append(tuple([line.strip() for line in section.splitlines() if line.strip()]
                            for section in match.groups()))
        cursor = match.end()
    assert not cleaned[cursor:].strip()
    assert blocks
    return blocks


def source_blocks(game, name):
    return script_blocks(decompile_script(game, name))


@dataclass
class Actor:
    hero_xp: int
    npc_xp: int
    in_party: bool = True
    globals: dict[tuple[str, str], int] = field(default_factory=dict)
    interruptible: bool = True
    events: list[tuple] = field(default_factory=list)


PARTY = {"inparty", "ifvalidforpartydialog", "ifvalidforpartydialogue",
         "isvalidforpartydialog", "isvalidforpartydialogue", "inpartyallowdead"}


def call(line):
    # One function call per decompiled line; anything else fails the model.
    match = re.fullmatch(r"(!?)(\w+)\((.*)\)", line.strip())
    assert match, f"unsupported BAF statement: {line}"
    arguments = [token.strip().strip('"') for token in re.findall(r'"[^"]*"|[^,]+', match[3])]
    return bool(match[1]), match[2].lower(), arguments


def check(condition, actor):
    negate, name, args = call(condition)
    if name == "global":
        answer = actor.globals.get((args[0].lower(), args[1].lower()), 0) == int(args[2])
    elif name in PARTY:
        assert args == ["Myself"]
        answer = actor.in_party
    elif name in {"xpgt", "xplt"}:
        value = actor.npc_xp if args[0] == "Myself" else actor.hero_xp
        assert args[0] in {"Myself", "Player1"}
        answer = value > int(args[1]) if name == "xpgt" else value < int(args[1])
    else:
        raise AssertionError(f"unsupported modeled trigger: {condition}")
    return not answer if negate else answer


def run_pass(blocks, actor):
    # A scan evaluates triggers against one snapshot, then applies the queued
    # responses of every block up to the first one without Continue().
    snapshot = copy.deepcopy(actor)
    queued = []
    for conditions, actions in blocks:
        if not all(check(condition, snapshot) for condition in conditions):
            continue
        continuing = False
        for action in actions:
            negate, name, args = call(action)
            assert not negate
            if name == "continue":
                continuing = True
            else:
                assert name in {"setglobal", "setinterrupt", "changestat"}, action
                queued.append((name, args))
        if not continuing:
            break
    for name, args in queued:
        if name == "setglobal":
            actor.globals[(args[0].lower(), args[1].lower())] = int(args[2])
        elif name == "setinterrupt":
            actor.interruptible = args[0] in {"TRUE", "1"}
        else:
            assert args[0] == "Myself" and args[1] == "XP" and args[3] == "SET"
            assert not actor.interruptible, "XP change must be in the noninterruptible response"
            actor.npc_xp = int(args[2])
            actor.events.append(("xp", actor.npc_xp))
    assert actor.interruptible


def soa(extra=None):
    # EET sets ENDOFBG1 to 2 at the SoD-to-SoA transition; it stays 2 in ToB.
    return {("endofbg1", "global"): 2, **(extra or {})}


def assert_installed(game):
    result, transcript = install(game)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    after = tree(game)
    changed = {name for name in set(after) | set(game.before) if after.get(name) != game.before.get(name)}
    assert changed == {f"OVERRIDE/{name}.BCS" for name in PATCHED}, (changed, transcript)
    for name in PATCHED:
        # EXTEND_TOP: the original compiled blocks follow unchanged.
        assert after[f"OVERRIDE/{name}.BCS"].endswith(game.before[f"OVERRIDE/{name}.BCS"].removeprefix(b"SC\n"))
    return transcript, after


def assert_uninstalled(game):
    result, transcript = install(game, uninstall=True)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY REMOVED" in transcript
    assert game.before == tree(game)


@pytest.mark.parametrize("sr", (False, True))
def test_adds_eet_blocks_only_where_missing_and_uninstalls_byte_exact(tmp_path, sr):
    game = make_game(tmp_path, sr=sr)
    originals = {name: source_blocks(game, name) for name in PATCHED}
    transcript, _ = assert_installed(game)
    for name, phase in PATCHED.items():
        blocks = source_blocks(game, name)
        added = 8 if phase == "soa" else 1
        assert blocks[added:] == originals[name], name
        assert ("SoA join-XP ladder" if phase == "soa" else "ToB join-XP raise") in transcript
    # Every joinable script that already has its block is reported, not changed.
    assert "5 SoA and ToB scripts of joinable NPCs already have their join-XP catch-up" in transcript
    soa_missing = re.search(r"SoA party-table entries without an EET SoA script, unchanged:(.*)", transcript)
    tob_missing = re.search(r"ToB party-table entries without an EET ToB script, unchanged:(.*)", transcript)
    assert set(soa_missing[1].split()) == {"KIVAN", "SAFANA"}, transcript
    assert set(tob_missing[1].split()) == {"SAFANA"}, transcript
    assert_uninstalled(game)


def test_sarah_joins_at_the_protagonist_band_once_and_only_in_soa(tmp_path):
    game = make_game(tmp_path)
    assert_installed(game)
    blocks = source_blocks(game, "K#SARAH")
    for hero_xp in sorted({0, 89_000, 89_001, 9_000_000, *(t + d for t in TIERS for d in (-1, 0, 1))}):
        band = max((tier for tier in TIERS if hero_xp >= tier), default=0)
        for npc_xp in (89_000, max(0, band - 1), band, band + 1, 2_000_000):
            # Waiting outside the party changes nothing.
            actor = Actor(hero_xp, npc_xp, in_party=False, globals=soa())
            run_pass(blocks, actor)
            assert actor.npc_xp == npc_xp and ("bd_joinxp", "locals") not in actor.globals
            actor.in_party = True
            run_pass(blocks, actor)
            assert actor.npc_xp == max(npc_xp, band), (hero_xp, npc_xp)
            assert actor.globals[("bd_joinxp", "locals")] == 1
            # The catch-up consumed this scan; EET's party block and the story run next.
            assert ("k#sarahpartybg2", "global") not in actor.globals
            run_pass(blocks, actor)
            assert actor.globals[("k#sarahpartybg2", "global")] == 1
            assert actor.globals[("questalpha", "locals")] == 1
            # One shot: later protagonist XP, a rejoin or a reload do not repeat it.
            later = copy.deepcopy(actor)
            later.hero_xp = 20_000_000
            later.in_party = False
            run_pass(blocks, later)
            later.in_party = True
            run_pass(blocks, later)
            assert later.npc_xp == actor.npc_xp and later.events == actor.events
    for state in ({("endofbg1", "global"): 1}, soa({("intob", "global"): 1})):
        # Not in BG1/SoD, and not in ToB, where EET's raise applies.
        actor = Actor(2_000_000, 89_000, globals=dict(state))
        run_pass(blocks, actor)
        assert actor.npc_xp == 89_000 and ("bd_joinxp", "locals") not in actor.globals
    assert_uninstalled(game)


@pytest.mark.parametrize("name", ("WILSON", "YOSHIMO"))
def test_tob_raise_runs_first_in_tob_and_never_in_soa(tmp_path, name):
    game = make_game(tmp_path)
    originals = source_blocks(game, name)
    assert_installed(game)
    blocks = source_blocks(game, name)
    tob = soa({("intob", "global"): 1})
    for npc_xp, expected in ((440_000, 2_500_000), (2_499_999, 2_500_000), (3_000_000, 3_000_000)):
        # The AR4500 summon resets BD_JOINXP; a ToB-start creature starts at 0.
        actor = Actor(4_000_000, npc_xp, globals=dict(tob))
        run_pass(blocks, actor)
        if npc_xp < 2_500_000:
            assert actor.npc_xp == expected and actor.globals[("bd_joinxp", "locals")] == 1
        else:
            run_pass(blocks, actor)
            assert actor.npc_xp == expected and actor.globals[("bd_joinxp", "locals")] == 1
        run_pass(blocks, actor)
        assert actor.npc_xp == expected
    # In SoA the added raise cannot run: the script behaves as before.
    for hero_xp, npc_xp in ((2_000_000, 300_000), (400_000, 300_000), (2_000_000, 3_000_000)):
        before, after = Actor(hero_xp, npc_xp, globals=soa()), Actor(hero_xp, npc_xp, globals=soa())
        for _ in range(3):
            run_pass(originals, before)
            run_pass(blocks, after)
        assert (after.npc_xp, after.globals) == (before.npc_xp, before.globals)
    assert_uninstalled(game)


def test_normalized_input_is_a_byte_stable_second_application(tmp_path):
    # EET's own guard tests the compiled text for "BD_JOINXP", which never
    # matches a compiled script; 239 recognises its blocks by what they do.
    game = make_game(tmp_path)
    _, normalized = assert_installed(game)
    assert_uninstalled(game)
    for name in PATCHED:
        (game.override / f"{name.lower()}.bcs").write_bytes(normalized[f"OVERRIDE/{name}.BCS"])
    game.before = tree(game)
    result, transcript = install(game)
    assert result.returncode == 0, transcript
    assert "join-XP ladder" not in transcript and "join-XP raise" not in transcript
    assert "8 SoA and ToB scripts of joinable NPCs already have their join-XP catch-up" in transcript
    assert tree(game) == game.before
    assert_uninstalled(game)


@pytest.mark.parametrize("variant", ("own-variable-ladder", "ladder-without-catch-all", "scs"))
def test_existing_soa_catch_up_of_any_owner_is_preserved(tmp_path, variant):
    if variant == "own-variable-ladder":
        script = party_block("K#SARAH") + STORY + ladder("SarahJoinedOnce")
    elif variant == "ladder-without-catch-all":
        # Pai'Na and Sirene ship the ladder without its final disarm.
        script = party_block("K#SARAH") + STORY + "END\n".join(ladder().split("END\n")[:7]) + "END\n"
    else:
        script = party_block("K#SARAH") + STORY + (
            'IF\n Global("DWSCS_Setup","LOCALS",0)\n CheckStat(Myself,0,LEVEL)\n'
            'THEN\n RESPONSE #100\n SetGlobal("DWSCS_Setup","LOCALS",1)\n'
            ' ApplySpellRES("dw#aulel",Myself)\n Continue()\nEND\n'
            'IF\n Global("DWSCS_Reset","LOCALS",0)\n CheckStat(Myself,0,LEVEL)\n'
            'THEN\n RESPONSE #100\n ChangeStat(Myself,XP,0,SET)\n'
            ' SetGlobal("DWSCS_Reset","LOCALS",1)\n Continue()\nEND\n')
    game = make_game(tmp_path, scripts={"K#SARAH": script})
    result, transcript = install(game)
    assert result.returncode == 0, transcript
    assert "K#SARAH.BCS gets" not in transcript
    if variant == "scs":
        assert "SCS NPC customization owns joining XP in K#SARAH.BCS" in transcript
    after = tree(game)
    assert after["OVERRIDE/K#SARAH.BCS"] == game.before["OVERRIDE/K#SARAH.BCS"]
    assert_uninstalled(game)


@pytest.mark.parametrize("variant,patched", (
    ("raise-before-catch-all", False),
    ("own-variable-raise", False),
    ("disarm-outside-party-first", True),
    ("raise-after-soa-only-disarm", False),
    # A ToB-only script's own protagonist ladder is that mod's ToB catch-up.
    ("player-based-raise", False),
))
def test_tob_raise_counts_only_if_it_can_run_first(tmp_path, variant, patched):
    catch_all = ('IF\n Global("BD_JOINXP","LOCALS",0)\n InParty(Myself)\nTHEN\n RESPONSE #100\n'
                 ' SetGlobal("BD_JOINXP","LOCALS",1)\nEND\n')
    script = {
        "raise-before-catch-all": STORY + raise_block() + catch_all,
        "own-variable-raise": STORY + raise_block(3_000_000, "SarahToBOnce"),
        "disarm-outside-party-first": STORY + (
            'IF\n Global("BD_JOINXP","LOCALS",0)\n !InParty(Myself)\nTHEN\n RESPONSE #100\n'
            ' SetGlobal("BD_JOINXP","LOCALS",1)\nEND\n') + raise_block(),
        "raise-after-soa-only-disarm": STORY + (
            'IF\n Global("BD_JOINXP","LOCALS",0)\n Global("INTOB","GLOBAL",0)\n InParty(Myself)\n'
            'THEN\n RESPONSE #100\n SetGlobal("BD_JOINXP","LOCALS",1)\nEND\n') + raise_block(),
        "player-based-raise": STORY + (
            'IF\n Global("BD_JOINXP","LOCALS",0)\n InParty(Myself)\n XPGT(Player1,2000000)\n'
            ' XPLT(Myself,2500000)\nTHEN\n RESPONSE #100\n SetInterrupt(FALSE)\n'
            ' SetGlobal("BD_JOINXP","LOCALS",1)\n ChangeStat(Myself,XP,2500000,SET)\n'
            ' SetInterrupt(TRUE)\nEND\n'),
    }[variant]
    game = make_game(tmp_path, scripts={"K#SARA25": script})
    result, transcript = install(game)
    assert result.returncode == 0, transcript
    after = tree(game)
    assert (after["OVERRIDE/K#SARA25.BCS"] != game.before["OVERRIDE/K#SARA25.BCS"]) == patched, transcript
    assert ("K#SARA25.BCS gets EET's ToB join-XP raise" in transcript) == patched
    assert_uninstalled(game)


def test_missing_tob_script_is_reported_and_the_rest_installs(tmp_path):
    game = make_game(tmp_path, scripts={"K#SARA25": None})
    result, transcript = install(game)
    assert result.returncode in (0, 3), transcript
    assert "NOT INSTALLED DUE TO ERRORS" not in transcript
    assert "ToB script K#SARA25.BCS does not exist" in transcript
    after = tree(game)
    assert {name for name in after if after[name] != game.before.get(name)} == {
        f"OVERRIDE/{name}.BCS" for name in PATCHED}
    assert_uninstalled(game)


@pytest.mark.parametrize("defect", (
    "no-campaign", "no-pdialog-column", "no-tob-row", "missing-tob-table",
    "blank-default-line", "no-transition-script",
))
def test_unreadable_eet_rules_fail_without_changes(tmp_path, defect):
    tables, scripts = {}, {}
    if defect == "no-campaign":
        tables["campaign"] = None
    elif defect == "no-pdialog-column":
        tables["campaign"] = CAMPAIGN.replace("PDIALOG        SAVE_DIR", "PARTYDLG       SAVE_DIR")
    elif defect == "no-tob-row":
        tables["campaign"] = "\n".join(line for line in CAMPAIGN.split("\n") if not line.startswith("TOB"))
    elif defect == "missing-tob-table":
        tables["25dialog"] = None
    elif defect == "blank-default-line":
        tables["pdialog"] = SOA_TABLE.replace("multig\n", "\n")
    else:
        scripts["AR4500"] = None
    game = make_game(tmp_path, tables=tables, scripts=scripts)
    result, transcript = install(game)
    assert result.returncode != 0, transcript
    assert "NOT INSTALLED DUE TO ERRORS" in transcript
    assert tree(game) == game.before


def test_requires_eet(tmp_path):
    game = make_game(tmp_path, game_type="bg2ee")
    result, transcript = install(game)
    assert "NOT INSTALLED DUE TO ERRORS" not in transcript
    assert "supports EET only" in transcript
    assert tree(game) == game.before


@pytest.mark.parametrize("order", ((237, 239), (239, 237)))
def test_fade_with_component_237_gets_one_catch_up_owner_per_script(tmp_path, order):
    fade = party_block("E3Fade") + STORY
    game = make_game(tmp_path, scripts={"E3FADE": fade},
                     tables={"pdialog": SOA_TABLE + "E3Fade   E3FadeP E3FadeJ E3FadeD *** *** *** ***\n"})
    (game.override / "e3fade13.cre").write_bytes(creature("E3Fade", "E3FADE"))
    game.before = tree(game)
    transcripts = []
    for component in order:
        result, transcript = install(game, component)
        assert result.returncode == 0, transcript
        transcripts.append(transcript)
    after = tree(game)
    fade_blocks = source_blocks(game, "E3FADE")
    if order == (237, 239):
        # 237's private clone keeps its own ladder; 239 recognises it through
        # the decompiled 0x4043 alias and adds Beamdog's ladder only to the
        # original script, which existing actors and other users keep.
        assert "OVERRIDE/CBMFXP.BCS" in after
        assert "CBMFXP.BCS gets" not in transcripts[1]
        assert "E3FADE.BCS gets EET's SoA join-XP ladder" in transcripts[1]
        assert len(fade_blocks) == 8 + len(script_blocks(fade))
    else:
        # 237 now sees 239's ladder as the existing provider.
        assert "provider is preserved" in transcripts[1]
        assert "OVERRIDE/CBMFXP.BCS" not in after
    for component in reversed(order):
        result, transcript = install(game, component, uninstall=True)
        assert result.returncode == 0, transcript
    assert tree(game) == game.before
