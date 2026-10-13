"""Real WeiDU recruitment installers and a bounded model of their emitted BAF.

The model executes decompiled installed scripts; it is not an engine playtest.
Fixtures are authored data, with no licensed game resources or saved actors.
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
COMPONENTS = {
    237: ("E3FADE13", "CBMFXP", "E3FADE25"),
    238: ("RH#EVA", "CBMEXP", "RH#EV25"),
}
TIERS = (125_000, 250_000, 500_000, 750_000, 1_000_000, 1_250_000)
IDS = {
    "action": "IDS V1.0\n30 SetGlobal(S:Name*,S:Area*,I:Value*)\n"
              "36 Continue()\n86 SetInterrupt(I:State*Boolean)\n"
              "370 ChangeStat(O:Object*,I:Stat*Stats,I:Value*,I:Modifier*Statmod)\n"
              "160 ApplySpellRES(S:RES*,O:Target*)\n",
    "trigger": "IDS V1.0\n0x400F Global(S:Name*,S:Area*,I:Value*)\n"
               "0x4043 InParty(O:Object*)\n0x4033 XP(O:Object*,I:XP*)\n"
               "0x4034 XPGT(O:Object*,I:XP*)\n0x4035 XPLT(O:Object*,I:XP*)\n"
               "0x4036 CheckStat(O:Object*,I:Value*,I:Stat*Stats)\n"
               "0x4037 CheckStatGT(O:Object*,I:Value*,I:Stat*Stats)\n"
               "0x4038 CheckStatLT(O:Object*,I:Value*,I:Stat*Stats)\n"
               "0x4089 OR(I:OrCount*)\n0x4023 True()\n",
    "object": "IDS V1.0\n1 Myself\n21 Player1\n",
    "boolean": "IDS V1.0\n0 FALSE\n1 TRUE\n",
    "stats": "IDS V1.0\n44 XP\n34 LEVEL\n",
    "statmod": "IDS V1.0\n1 ADD\n2 SET\n",
}
STORY_BLOCKS = (
    'IF\n Global("QuestAlpha","LOCALS",0)\nTHEN\n RESPONSE #100\n'
    ' SetGlobal("QuestAlpha","LOCALS",1)\n Continue()\nEND\n',
    'IF\n Global("QuestBeta","LOCALS",0)\nTHEN\n RESPONSE #100\n'
    ' SetGlobal("QuestBeta","LOCALS",1)\nEND\n',
)


def tree(game):
    return {name: data for name, data in _file_tree(game.root).items()
            if not _is_weidu_artifact(name)}


def invoke(game, *args, cwd=None):
    result = subprocess.run(
        [str(WEIDU), "--no-auto-tp2", "--noautoupdate", "--no-exit-pause",
         "--game", str(game.root), "--use-lang", "en_us", *args],
        cwd=cwd or game.root, capture_output=True, text=True, timeout=60,
    )
    return result, result.stdout + result.stderr


def install(game, component, *, uninstall=False, setup=SETUP_NAME):
    return invoke(game, setup, "--language", "0",
                  "--force-uninstall-list" if uninstall else "--force-install-list", str(component))


def compile_script(game, name, source):
    path = game.root / f"{name.lower()}.baf"
    path.write_text(source, encoding="ascii")
    result, transcript = invoke(game, "--out", str(game.override), path.name)
    assert result.returncode == 0, transcript


def decompile_script(game, name):
    # Inspection output is kept outside the fake game so scope comparisons stay exact.
    inspection = game.root.parent / f"inspect-{name.lower()}"
    inspection.mkdir(exist_ok=True)
    result, transcript = invoke(game, str(game.override / f"{name.lower()}.bcs"), cwd=inspection)
    assert result.returncode == 0, transcript
    return next(inspection.glob("*.baf")).read_text(encoding="utf-8")


def creature(script, *, converted=False):
    result = bytearray(make_cre(class_id=29 if converted else 0, kit=0x56780000,
                               dv="MODDED_NAME", xp=987_654, seed=37))
    struct.pack_into("<HH", result, 0x24, 0, 87)
    result[0x234:0x237] = bytes((0, 9, 2)) if converted else bytes((13, 0, 0))
    result[0x248:0x250] = script.encode("ascii").ljust(8, b"\0")
    result[0x250:0x258] = b"UNRELATE"
    return bytes(result)


def make_game(tmp_path, *, game_type="bg2ee", sr=False, converted=False,
              renamed=False, reversed_blocks=False, provider=None):
    game = SyntheticGame(tmp_path / "game", game=game_type, eeex=False)
    for name, source in IDS.items():
        (game.override / f"{name}.ids").write_text(source, encoding="ascii")
    for name in ("ea", "general", "race", "class", "specific", "gender", "align"):
        (game.override / f"{name}.ids").write_text("IDS V1.0\n", encoding="ascii")
    if sr:
        (game.override / "dvimhere.mrk").write_bytes(b"synthetic SR presence")
    source = "".join(reversed(STORY_BLOCKS) if reversed_blocks else STORY_BLOCKS)
    if provider:
        source = STORY_BLOCKS[1] + provider + STORY_BLOCKS[0]
    script = "RENAMED" if renamed else "SHARED"
    compile_script(game, script, source)
    compile_script(game, "TOBONLY", STORY_BLOCKS[1])
    for target, _, tob in COMPONENTS.values():
        (game.override / f"{target.lower()}.cre").write_bytes(creature(script, converted=converted))
        (game.override / f"{tob.lower()}.cre").write_bytes(creature("TOBONLY"))
    (game.override / "outsider.cre").write_bytes(creature(script))
    game.source_script = script
    game.before = tree(game)
    return game


@dataclass
class ActorState:
    hero_xp: int
    npc_xp: int
    in_party: bool = True
    globals: dict[tuple[str, str], int] = field(default_factory=dict)
    interruptible: bool = True
    events: list[tuple] = field(default_factory=list)


def call(line):
    # WeiDU decompiles one function call per line. Reject anything our explicitly
    # bounded model does not understand instead of silently approximating it.
    match = re.fullmatch(r"(!?)(\w+)\((.*)\)", line.strip())
    assert match, f"unsupported BAF statement: {line}"
    arguments = [token.strip().strip('"') for token in re.findall(r'"[^"]*"|[^,]+', match[3])]
    return bool(match[1]), match[2].lower(), arguments


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


def check(condition, state):
    negate, name, args = call(condition)
    if name == "global":
        answer = state.globals.get((args[0].lower(), args[1].lower()), 0) == int(args[2])
    elif name == "inparty":
        assert args == ["Myself"]
        answer = state.in_party
    elif name in {"xp", "xpgt", "xplt"}:
        assert args[0] in {"Myself", "Player1"}
        value = state.npc_xp if args[0] == "Myself" else state.hero_xp
        threshold = int(args[1])
        answer = value == threshold if name == "xp" else value > threshold if name == "xpgt" else value < threshold
    elif name == "true":
        assert not args
        answer = True
    else:
        raise AssertionError(f"unsupported modeled trigger: {condition}")
    return not answer if negate else answer


def execute_pass(blocks, state):
    # Trigger evaluation in a continued scan can precede queued action effects.
    # Evaluate the scan from one snapshot, then apply its collected actions.
    # In particular, a queued SetGlobal must not exclude later ladder branches.
    trigger_state = copy.deepcopy(state)
    queued = []
    for conditions, actions in blocks:
        if not all(check(condition, trigger_state) for condition in conditions):
            continue
        continuing = False
        for action in actions:
            negate, name, args = call(action)
            assert not negate
            if name == "continue":
                assert not args
                continuing = True
            else:
                assert name in {"setglobal", "setinterrupt", "changestat"}, action
                queued.append((name, args))
        if not continuing:
            break
    for name, args in queued:
        if name == "setglobal":
            state.globals[(args[0].lower(), args[1].lower())] = int(args[2])
            state.events.append(("global", *args))
        elif name == "setinterrupt":
            assert args[0] in {"FALSE", "TRUE", "0", "1"}
            state.interruptible = args[0] in {"TRUE", "1"}
        elif name == "changestat":
            assert args[0] == "Myself" and args[1] == "XP" and args[3] == "SET"
            assert not state.interruptible, "XP change must be in the noninterruptible action sequence"
            assert state.globals.get(("cbm_soarecruitxp", "locals")) == 1
            state.npc_xp = int(args[2])
            state.events.append(("xp", state.npc_xp))
    assert state.interruptible


def assert_installed(game, component):
    target, clone, _ = COMPONENTS[component]
    result, transcript = install(game, component)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    after = tree(game)
    expected = dict(game.before)
    key = f"OVERRIDE/{target}.CRE"
    original_cre = expected[key]
    changed = bytearray(original_cre)
    changed[0x248:0x250] = clone.encode("ascii").ljust(8, b"\0")
    expected[key] = bytes(changed)
    assert f"OVERRIDE/{clone}.BCS" in after, transcript
    expected[f"OVERRIDE/{clone}.BCS"] = after[f"OVERRIDE/{clone}.BCS"]
    assert expected == after
    # The retained original script protects every shared user and any actor
    # already created with that original script, including ToB templates.
    original_script = game.before[f"OVERRIDE/{game.source_script}.BCS"]
    assert after[f"OVERRIDE/{clone}.BCS"].endswith(original_script.removeprefix(b"SC\n"))
    original_blocks = script_blocks(decompile_script(game, game.source_script))
    installed_blocks = script_blocks(decompile_script(game, clone))
    assert installed_blocks[-len(original_blocks):] == original_blocks
    return installed_blocks, after


def assert_uninstalled(game, component):
    result, transcript = install(game, component, uninstall=True)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY REMOVED" in transcript
    assert game.before == tree(game)


@pytest.mark.parametrize("component", COMPONENTS)
@pytest.mark.parametrize("game_type,sr,converted,renamed,reversed_blocks", (
    ("bg2ee", False, False, False, False),
    ("eet", True, True, True, True),
))
def test_private_clone_preserves_shared_scripts_other_actors_and_all_cre_bytes(
    tmp_path, component, game_type, sr, converted, renamed, reversed_blocks,
):
    game = make_game(tmp_path, game_type=game_type, sr=sr, converted=converted,
                     renamed=renamed, reversed_blocks=reversed_blocks)
    assert_installed(game, component)
    assert_uninstalled(game, component)


@pytest.mark.parametrize("component", COMPONENTS)
def test_generated_script_executes_thresholds_once_and_resumes_story_next_pass(tmp_path, component):
    game = make_game(tmp_path)
    blocks, _ = assert_installed(game, component)
    for hero_xp in sorted({0, 9_000_000, *(tier + delta for tier in TIERS for delta in (-1, 0, 1))}):
        target = max((tier for tier in TIERS if hero_xp >= tier), default=0)
        for npc_xp in (0, max(0, target - 1), target, target + 1, 2_000_000):
            actor = ActorState(hero_xp, npc_xp, in_party=False)
            execute_pass(blocks, actor)
            assert actor.npc_xp == npc_xp
            assert actor.globals.get(("cbm_soarecruitxp", "locals"), 0) == 0
            actor.in_party = True
            actor.globals[("questalpha", "locals")] = 0
            actor.globals[("questbeta", "locals")] = 0
            execute_pass(blocks, actor)
            assert actor.npc_xp == max(npc_xp, target), (hero_xp, npc_xp, target)
            assert actor.globals[("cbm_soarecruitxp", "locals")] == 1
            assert actor.globals[("questalpha", "locals")] == 0
            assert actor.globals[("questbeta", "locals")] == 0
            assert [event for event in actor.events if event[0] == "xp"] == (
                [("xp", target)] if npc_xp < target else []
            )
            execute_pass(blocks, actor)
            assert actor.npc_xp == max(npc_xp, target)
            assert actor.globals[("questalpha", "locals")] == 1
            assert actor.globals[("questbeta", "locals")] == 1
            # Local variables persist over save/reload and dismissal/rejoin.
            reloaded = copy.deepcopy(actor)
            reloaded.hero_xp = 20_000_000
            reloaded.in_party = False
            execute_pass(blocks, reloaded)
            reloaded.in_party = True
            execute_pass(blocks, reloaded)
            assert reloaded.npc_xp == actor.npc_xp
            assert reloaded.events == actor.events
    assert_uninstalled(game, component)


@pytest.mark.parametrize("component", COMPONENTS)
def test_deferred_scan_cannot_queue_lower_awards_or_story_after_owned_response(tmp_path, component):
    game = make_game(tmp_path)
    blocks, _ = assert_installed(game, component)
    for hero_xp, npc_xp, expected_xp in (
        (2_000_000, 0, 1_250_000),
        (2_000_000, 3_000_000, 3_000_000),
        (100_000, 0, 0),
    ):
        actor = ActorState(hero_xp, npc_xp)
        execute_pass(blocks, actor)
        assert actor.npc_xp == expected_xp
        # Both award and no-award completion consume this scan. With the old
        # Continue chain the highest award queues all six setters, the fallback,
        # and story effects against the unchanged pre-pass marker/XP state.
        assert actor.globals == {("cbm_soarecruitxp", "locals"): 1}
        assert actor.events == [
            ("global", "CBM_SoARecruitXP", "LOCALS", "1"),
            *([("xp", expected_xp)] if npc_xp < expected_xp else []),
        ]
        execute_pass(blocks, actor)
        assert actor.npc_xp == expected_xp
        assert actor.globals[("questalpha", "locals")] == 1
        assert actor.globals[("questbeta", "locals")] == 1
    assert_uninstalled(game, component)


@pytest.mark.parametrize("component", COMPONENTS)
def test_normalized_input_is_a_byte_stable_second_application(tmp_path, component):
    game = make_game(tmp_path)
    _, normalized = assert_installed(game, component)
    assert_uninstalled(game, component)
    target, clone, _ = COMPONENTS[component]
    for name, extension in ((target, "CRE"), (clone, "BCS")):
        (game.override / f"{name.lower()}.{extension.lower()}").write_bytes(normalized[f"OVERRIDE/{name}.{extension}"])
    game.before = tree(game)
    result, transcript = install(game, component)
    assert result.returncode in (0, 3), transcript
    assert "NOT INSTALLED DUE TO ERRORS" not in transcript
    assert tree(game) == normalized
    assert_uninstalled(game, component)


@pytest.mark.parametrize("component", COMPONENTS)
def test_missing_target_is_reported_without_unused_script_dependencies(tmp_path, component):
    game = make_game(tmp_path)
    target, _, _ = COMPONENTS[component]
    (game.override / f"{target.lower()}.cre").unlink()
    for path in (*game.override.glob("*.ids"), *game.override.glob("*.bcs")):
        path.unlink()
    game.before = tree(game)
    result, transcript = install(game, component)
    assert result.returncode in (0, 3), transcript
    assert "NOT INSTALLED DUE TO ERRORS" not in transcript
    assert "no resources changed" in transcript.lower() or "recruitment xp was not changed" in transcript.lower()
    assert target in transcript.upper()
    assert tree(game) == game.before


@pytest.mark.parametrize("component", COMPONENTS)
@pytest.mark.parametrize("defect", ("signature", "short-header", "missing-script", "empty-script", "foreign-clone"))
def test_invalid_inputs_and_foreign_private_clone_fail_without_changes(tmp_path, component, defect):
    game = make_game(tmp_path)
    target, clone, _ = COMPONENTS[component]
    target_path = game.override / f"{target.lower()}.cre"
    creature_data = bytearray(target_path.read_bytes())
    if defect == "signature":
        creature_data[:8] = b"BAD V1.0"
    elif defect == "short-header":
        creature_data = creature_data[:0x2D3]
    elif defect == "empty-script":
        creature_data[0x248:0x250] = bytes(8)
    elif defect == "missing-script":
        (game.override / f"{game.source_script.lower()}.bcs").unlink()
    else:
        (game.override / f"{clone.lower()}.bcs").write_bytes(b"foreign private-name owner")
    target_path.write_bytes(creature_data)
    game.before = tree(game)
    result, transcript = install(game, component)
    assert result.returncode != 0, transcript
    assert "NOT INSTALLED DUE TO ERRORS" in transcript
    assert "Fade" in transcript if component == 237 else "Evandra" in transcript
    assert tree(game) == game.before


@pytest.mark.parametrize("component", COMPONENTS)
@pytest.mark.parametrize("reordered", (False, True))
@pytest.mark.parametrize("marker", ("ProviderHasJoined", "Provider.Once"))
def test_existing_one_shot_protagonist_xp_provider_is_preserved(tmp_path, component, reordered, marker):
    conditions = [f'Global("{marker}","LOCALS",0)', 'InParty(Myself)', 'XPGT(Player1,599999)']
    if reordered:
        conditions.reverse()
    provider = "IF\n" + "\n".join(conditions) + "\nTHEN\n RESPONSE #100\n" + (
        f' SetInterrupt(FALSE)\n SetGlobal("{marker}","LOCALS",1)\n'
        ' ChangeStat(Myself,XP,600000,SET)\n SetInterrupt(TRUE)\n Continue()\nEND\n'
    )
    game = make_game(tmp_path, provider=provider, renamed=True)
    result, transcript = install(game, component)
    assert result.returncode in (0, 3), transcript
    assert "NOT INSTALLED DUE TO ERRORS" not in transcript
    assert "provider" in transcript.lower()
    assert game.before == tree(game)
    assert_uninstalled(game, component)


@pytest.mark.parametrize("component", COMPONENTS)
@pytest.mark.parametrize("reordered", (False, True))
def test_scs_level_zero_actor_setup_retains_ownership_of_recruitment_xp(tmp_path, component, reordered):
    provider_blocks = (
        'IF\n Global("DWSCS_Setup","LOCALS",0)\n CheckStat(Myself,0,LEVEL)\n'
        'THEN\n RESPONSE #100\n SetGlobal("DWSCS_Setup","LOCALS",1)\n'
        ' ApplySpellRES("dw#aulel",Myself)\n Continue()\nEND\n',
        'IF\n Global("DWSCS_Reset","LOCALS",0)\n CheckStat(Myself,0,LEVEL)\n'
        'THEN\n RESPONSE #100\n ChangeStat(Myself,XP,0,SET)\n'
        ' SetGlobal("DWSCS_Reset","LOCALS",1)\n Continue()\nEND\n',
    )
    provider = "".join(reversed(provider_blocks) if reordered else provider_blocks)
    game = make_game(tmp_path, provider=provider, converted=True, renamed=True)
    result, transcript = install(game, component)
    assert result.returncode in (0, 3), transcript
    assert "NOT INSTALLED DUE TO ERRORS" not in transcript
    assert "SCS" in transcript
    assert game.before == tree(game)
    assert_uninstalled(game, component)


@pytest.mark.parametrize("component", COMPONENTS)
@pytest.mark.parametrize("variant", (
    "separate-blocks", "mismatched-marker", "not-in-party", "actions-only-marker",
    "optional-party-or", "marker-regex-metachar",
))
def test_unrelated_story_actions_do_not_count_as_a_first_join_xp_provider(tmp_path, component, variant):
    conditions = ['InParty(Myself)', 'XPGT(Player1,599999)']
    actions = ['ChangeStat(Myself,XP,600000,SET)', 'SetGlobal("ProviderOnce","LOCALS",1)']
    if variant == "separate-blocks":
        provider = (
            'IF\n Global("ProviderOnce","LOCALS",0)\n InParty(Myself)\n XPGT(Player1,599999)\n'
            'THEN\n RESPONSE #100\n SetGlobal("Unrelated","LOCALS",1)\nEND\n'
            'IF\n Global("Unrelated","LOCALS",0)\nTHEN\n RESPONSE #100\n'
            ' ChangeStat(Myself,XP,600000,SET)\n SetGlobal("ProviderOnce","LOCALS",1)\nEND\n'
        )
    else:
        if variant == "actions-only-marker":
            actions.insert(0, 'SetGlobal("ProviderOnce","LOCALS",0)')
        else:
            conditions.insert(0, 'Global("ProviderOnce","LOCALS",0)')
        if variant == "mismatched-marker":
            actions[-1] = 'SetGlobal("AnotherOnce","LOCALS",1)'
        if variant == "not-in-party":
            conditions[1] = '!InParty(Myself)'
        if variant == "optional-party-or":
            conditions = [conditions[0], 'OR(2)', conditions[1],
                          'Global("AlternateQuest","LOCALS",0)', conditions[2]]
        if variant == "marker-regex-metachar":
            conditions[0] = 'Global("Provider.Once","LOCALS",0)'
            actions[-1] = 'SetGlobal("ProviderXOnce","LOCALS",1)'
        provider = ("IF\n" + "\n".join(conditions) + "\nTHEN\n RESPONSE #100\n"
                    + "\n".join(actions) + "\nEND\n")
    game = make_game(tmp_path, provider=provider)
    assert_installed(game, component)
    assert_uninstalled(game, component)


@pytest.mark.parametrize("component", COMPONENTS)
@pytest.mark.parametrize("piece", ("setup-only", "reset-only"))
def test_an_isolated_scs_like_action_does_not_claim_full_xp_setup(tmp_path, component, piece):
    action = 'ApplySpellRES("dw#aulel",Myself)' if piece == "setup-only" else 'ChangeStat(Myself,XP,0,SET)'
    provider = ('IF\n Global("OtherSetup","LOCALS",0)\n CheckStat(Myself,0,LEVEL)\n'
                'THEN\n RESPONSE #100\n' + action + '\n SetGlobal("OtherSetup","LOCALS",1)\nEND\n')
    game = make_game(tmp_path, provider=provider)
    assert_installed(game, component)
    assert_uninstalled(game, component)
