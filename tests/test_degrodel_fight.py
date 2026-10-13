"""Component 660: Degrodel's Helm of Balduran hand-in choice.

Real WeiDU compiles synthetic DEGROD dialogs (written here from scratch, using
public IESDP action/trigger signatures) and installs the public component into
disposable synthetic games. No game resources are read or copied.
Run: python -m pytest -q tests/test_degrodel_fight.py
"""

from __future__ import annotations

import re
import struct
import subprocess

import pytest

from tests.test_utility_xp_installer import (
    SETUP_NAME, WEIDU, SyntheticGame, _file_tree, _is_weidu_artifact,
)

pytestmark = pytest.mark.skipif(WEIDU is None, reason="set WEIDU to a WeiDU 249+ executable")

COMPONENT = 660
DLG_KEY = "OVERRIDE/DEGROD.DLG"
TLK_KEY = "LANG/EN_US/DIALOG.TLK"
FIGHT_GLOBAL = 'SetGlobal("CBMDegrodelFight","GLOBAL",1)'
ADDED_TEXT = {
    "hand": "Here is the helm, as we agreed.",
    "refuse": "No. The Helm of Balduran stays with us.",
    "say": "You would cheat me? Fools! Then I shall take the helm from your corpses!",
}

IDS = {
    "action": """0 NoAction()
1 ActionOverride(O:Actor*,A:Action*)
7 CreateCreature(S:NewObject*,P:Location*,I:Face*DIR)
10 Enemy()
30 SetGlobal(S:Name*,S:Area*,I:Value*)
108 EscapeArea()
108 EscapeAreaMove(S:Area*,I:X*,I:Y*,I:Face*DIR)
116 TakePartyItem(S:Item*)
140 GiveItemCreate(S:ResRef*,O:Object*,I:Usage1*,I:Usage2*,I:Usage3*)
164 AddexperienceParty(I:XP*)
171 GiveGoldForce(I:Amount*)
204 TakePartyItemNum(S:ResRef*,I:Num*)
227 CreateCreatureObject(S:ResRef*,O:Object*,I:Usage1*,I:Usage2*,I:Usage3*)
263 EraseJournalEntry(I:STRREF*)
""",
    "trigger": """0x400F Global(S:Name*,S:Area*,I:Value*)
0x4023 True()
0x4037 StateCheck(O:Object*,I:State*State)
0x4039 NumTimesTalkedTo(I:Num*)
0x4042 PartyHasItem(S:Item*)
0x4043 IsValidForPartyDialogue(O:Object*)
0x40CB InMyArea(O:Object*)
""",
    "object": "1 Myself\n19 LastTalkedToBy\n21 Player1\n",
    "state": "0x80101FEF CD_STATE_NOTVALID\n",
    "dir": "0 S\n1 SSW\n",
}

SERVANTS = """CreateCreature("HELMHO",[371.427],S)
CreateCreature("DOOMGU",[418.460],S)
CreateCreature("DOOMGU",[326.489],S)
CreateCreature("{stalker}",[351.605],S)
"""
JOURNAL = "EraseJournalEntry(26931)\nEraseJournalEntry(26932)\nEraseJournalEntry(26933)\n"


def interjection(target: str, var: str, npc: str, state: int) -> str:
    return f'''  IF ~Global("{var}","GLOBAL",0)
IsValidForPartyDialogue("{npc}")
InMyArea("{npc}")
!StateCheck("{npc}",CD_STATE_NOTVALID)~ THEN DO ~SetGlobal("{var}","GLOBAL",1)~ EXTERN ~{target}~ {state}
'''


def make_dialog(*, stalker="STALKE", interjections=False, handin=None, extra_states="",
                handin_extra=""):
    """A DEGROD-shaped dialog: offer, fight threat, quest, no-helm and hand-in."""
    if handin is None:
        handin = ("GiveGoldForce(5000)\nTakePartyItem(\"HELM07\")\n"
                  + SERVANTS.format(stalker=stalker) + JOURNAL + "EscapeArea()\n")
    offer_extra = interjection("VICONIJ", "X#VicDegro", "viconia", 675) if interjections else ""
    quest_extra = "".join(
        interjection(t, "X#DEGROD2", n, s)
        for t, n, s in (("DYNAHJ", "dynaheir", 174), ("CORANJ", "coran", 580),
                        ("QUAYLJ", "quayle", 44))
    ) if interjections else ""
    return f"""BEGIN ~DEGROD~
IF ~NumTimesTalkedTo(0)~ THEN BEGIN 0
  SAY #10327
  IF ~~ THEN REPLY #10382 GOTO 1
  IF ~~ THEN REPLY #10383 GOTO 1
  IF ~~ THEN REPLY #10384 GOTO 2
{offer_extra}END
IF ~~ THEN BEGIN 1
  SAY #10385
  IF ~~ THEN DO ~{SERVANTS.format(stalker=stalker)}Enemy()~ EXIT
END
IF ~~ THEN BEGIN 2
  SAY #10386
  IF ~~ THEN DO ~SetGlobal("Baldurian","GLOBAL",1)
GiveItemCreate("scrlpet",LastTalkedToBy,6,0,0)~ UNSOLVED_JOURNAL #26931 EXIT
{quest_extra}END
{extra_states}IF ~!PartyHasItem("HELM07")~ THEN BEGIN 3
  SAY #10416
  IF ~~ THEN EXIT
END
IF ~PartyHasItem("HELM07")~ THEN BEGIN 4
  SAY #10417
  IF ~~ THEN DO ~{handin}~ SOLVED_JOURNAL #26934 EXIT
{handin_extra}END
"""


# --------------------------------------------------------------------------
# Binary readers (DLG V1.0 and TLK V1 per IESDP)
# --------------------------------------------------------------------------

def _text(data: bytes, table: int, index: int) -> str | None:
    if index < 0 or index == 0xFFFFFFFF:
        return None
    offset, length = struct.unpack_from("<II", data, table + index * 8)
    return data[offset:offset + length].decode("latin-1")


def parse_dlg(data: bytes, *, semantic: bool = True) -> list[dict]:
    """Decode states; by default compare actions as top-level action lists and
    triggers without whitespace, because WeiDU re-separates every action string
    (one action per line) whenever it rewrites a DLG."""
    assert data[:8] == b"DLG V1.0"
    (n_states, off_states, n_trans, off_trans, off_strig, _n_strig, off_ttrig, _n_ttrig,
     off_act, _n_act) = struct.unpack_from("<10I", data, 8)
    states = []
    for s in range(n_states):
        strref, first, count, trig = struct.unpack_from("<IIIi", data, off_states + s * 16)
        transitions = []
        for t in range(first, first + count):
            flags, text, journal, ttrig, action, next_dlg, next_state = struct.unpack_from(
                "<IIIII8sI", data, off_trans + t * 32)
            transitions.append({
                "flags": flags,
                "text": text if flags & 1 else None,
                "journal": journal if flags & 0x10 else None,
                "trigger": _squash(_text(data, off_ttrig, ttrig), semantic) if flags & 2 else None,
                "action": _actions(_text(data, off_act, action), semantic) if flags & 4 else None,
                "next": None if flags & 8 else (next_dlg.rstrip(b"\0").decode(), next_state),
            })
        states.append({
            "say": strref,
            "trigger": _squash(_text(data, off_strig, trig), semantic) if trig >= 0 else None,
            "transitions": transitions,
        })
    return states


def _squash(text, semantic):
    return re.sub(r"\s+", "", text) if semantic and text is not None else text


def _actions(text, semantic):
    # Script identifiers and resrefs are case-insensitive, and WeiDU's D
    # compiler canonicalizes identifier case (myself -> Myself).
    return tuple(a.lower() for a in actions(text)) if semantic and text is not None else text


def tlk_strings(data: bytes) -> list[str]:
    _sig, _lang, count, base = struct.unpack_from("<8sHII", data, 0)
    strings = []
    for index in range(count):
        _flags, _sound, _vol, _pitch, offset, length = struct.unpack_from(
            "<H8sIIII", data, 0x12 + index * 0x1A)
        strings.append(data[base + offset:base + offset + length].decode("latin-1"))
    return strings


def actions(text: str) -> list[str]:
    """Top-level actions with whitespace removed (WeiDU stores text verbatim)."""
    found, depth, start, quoted = [], 0, None, False
    for index, char in enumerate(text):
        if quoted:
            quoted = char != '"'
        elif char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                found.append(re.sub(r"\s+", "", text[start:index + 1]))
                start = None
        elif depth == 0 and start is None and not char.isspace():
            start = index
    return found


# --------------------------------------------------------------------------
# Synthetic game helpers
# --------------------------------------------------------------------------

def weidu(game, *args):
    result = subprocess.run(
        [str(WEIDU), "--game", str(game.root), "--use-lang", "en_us", "--no-exit-pause",
         "--noautoupdate", "--no-auto-tp2", *args],
        cwd=game.root, capture_output=True, text=True, errors="replace", timeout=90,
    )
    return result, result.stdout + result.stderr


def run(game, *, uninstall=False):
    return weidu(game, SETUP_NAME, "--language", "0", "--quick-log",
                 "--force-uninstall-list" if uninstall else "--force-install-list",
                 str(COMPONENT))


def files(game):
    return {name: data for name, data in _file_tree(game.root).items()
            if not _is_weidu_artifact(name)}


def rewrite_actions(game, old_marker: str, raw: str) -> None:
    """Give one compiled action string raw text, as another DLG editor might."""
    path = next(p for p in game.override.iterdir() if p.name.upper() == "DEGROD.DLG")
    data = bytearray(path.read_bytes())
    off_act, n_act = struct.unpack_from("<II", data, 0x28)
    hits = [i for i in range(n_act) if old_marker in (_text(bytes(data), off_act, i) or "")]
    assert len(hits) == 1, hits
    struct.pack_into("<II", data, off_act + hits[0] * 8, len(data), len(raw))
    data.extend(raw.encode("latin-1"))
    path.write_bytes(bytes(data))
    game.before = files(game)


def make_game(tmp_path, dialog: str | None, *, game="eet"):
    synthetic = SyntheticGame(tmp_path / "game", game=game, eeex=False)
    for name, body in IDS.items():
        (synthetic.override / f"{name}.ids").write_text("IDS V1.0\n" + body)
    if dialog is not None:
        source = synthetic.root / "fixture.d"
        source.write_text(dialog)
        result, transcript = weidu(synthetic, "fixture.d", "--out", "override")
        assert result.returncode == 0, transcript
        source.unlink()
    synthetic.before = files(synthetic)
    return synthetic


def install(game):
    result, transcript = run(game)
    assert result.returncode == 0, transcript
    assert "SUCCESSFULLY INSTALLED" in transcript, transcript
    assert re.search(rf"(?m)#0\s+#{COMPONENT}\b", game.active_log())
    return transcript


def assert_skipped(game, message: str):
    result, transcript = run(game)
    assert result.returncode == 0, transcript
    assert "INSTALLATION ABORTED" in transcript, transcript
    assert message in transcript, transcript
    assert "SUCCESSFULLY INSTALLED" not in transcript
    assert not re.search(rf"(?m)#0\s+#{COMPONENT}\b", game.active_log())
    # No partial patch: every game file, including the TLK, is untouched.
    assert files(game) == game.before


def assert_choice(game, *, handin_state: int, handin_index: int = 0, reply_was=None,
                  expect_trigger=None):
    """The hand-in keeps its actions; refusing fights with the same servants."""
    before = parse_dlg(game.before[DLG_KEY])
    after_files = files(game)
    after = parse_dlg(after_files[DLG_KEY])
    strings = tlk_strings(after_files[TLK_KEY])

    # Only DEGROD.DLG and the TLK change.
    changed = {k for k in set(game.before) | set(after_files)
               if game.before.get(k) != after_files.get(k)}
    assert changed == {DLG_KEY, TLK_KEY}

    # Unrelated states, interjections included, are unchanged; one state appended.
    assert len(after) == len(before) + 1
    for index, state in enumerate(before):
        if index != handin_state:
            assert after[index] == state, index

    original = before[handin_state]
    patched = after[handin_state]
    assert patched["say"] == original["say"]
    assert patched["trigger"] == original["trigger"]
    assert len(patched["transitions"]) == len(original["transitions"]) + 1
    for index, transition in enumerate(original["transitions"]):
        current = patched["transitions"][index]
        if index != handin_index:
            assert current == transition
            continue
        # Hand over: exactly the installed outcome, now a player reply.
        expected = dict(transition, flags=transition["flags"] | 1)
        expected["text"] = current["text"]
        assert current == expected
        if reply_was is None:
            assert strings[current["text"]] == ADDED_TEXT["hand"]
        else:
            assert current["text"] == reply_was

    refuse = patched["transitions"][-1]
    assert strings[refuse["text"]] == ADDED_TEXT["refuse"]
    assert refuse["action"] is None and refuse["journal"] is None
    # The refusal is offered exactly when the hand-in is.
    assert refuse["trigger"] == _squash(expect_trigger, True)
    assert refuse["trigger"] == original["transitions"][handin_index]["trigger"]
    assert refuse["next"] == ("DEGROD", len(before))

    fight_state = after[-1]
    assert fight_state["trigger"] is None
    assert strings[fight_state["say"]] == ADDED_TEXT["say"]
    [fight] = fight_state["transitions"]
    assert fight["next"] is None and fight["text"] is None
    assert fight["flags"] & 0x100, "the fight path adds a solved journal entry"
    assert strings[fight["journal"]].startswith("The Helm of Balduran\n")
    assert "refused" in strings[fight["journal"]]

    handin = original["transitions"][handin_index]["action"]
    expected = [a for a in handin if a.startswith("createcreature")]
    expected += [a for a in handin if a.startswith("erasejournalentry")]
    expected += [FIGHT_GLOBAL.lower(), "enemy()"]
    assert list(fight["action"]) == expected
    lowered = "".join(fight["action"])
    for forbidden in ("escapearea", "takepartyitem", "givegold"):
        assert forbidden not in lowered
    return after


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_vanilla_shape_installs_reinstalls_and_uninstalls(tmp_path):
    game = make_game(tmp_path, make_dialog(stalker="STALKE"))
    install(game)
    assert_choice(game, handin_state=4)
    first = files(game)
    tlk_count = len(tlk_strings(first[TLK_KEY]))
    assert tlk_count == 1 + 4

    # Reinstalling replaces the previous install and adds no duplicate strings.
    install(game)
    assert files(game) == first

    result, transcript = run(game, uninstall=True)
    assert result.returncode == 0, transcript
    restored = files(game)
    assert restored[DLG_KEY] == game.before[DLG_KEY]
    # WeiDU keeps appended strings after uninstall; nothing else differs.
    assert {k: v for k, v in restored.items() if k != TLK_KEY} == {
        k: v for k, v in game.before.items() if k != TLK_KEY}
    install(game)
    assert files(game) == first


def test_eet_shape_with_bg1npc_interjections(tmp_path):
    game = make_game(tmp_path, make_dialog(stalker="STALKE_", interjections=True))
    transcript = install(game)
    after = assert_choice(game, handin_state=4)
    fight = after[-1]["transitions"][0]["action"]
    assert 'createcreature("stalke_",[351.605],s)' in fight
    assert "4 servant(s)" in transcript and "GiveGoldForce TakePartyItem EscapeArea" in transcript
    # The interjection EXTERNs on states 0 and 2 survive unchanged.
    externs = [t["next"] for s in after for t in s["transitions"]
               if t["next"] and t["next"][0] != "DEGROD"]
    assert externs == [("VICONIJ", 675), ("DYNAHJ", 174), ("CORANJ", 580), ("QUAYLJ", 44)]
    # For WeiDU-compiled input, other states and the hand-in's own action and
    # trigger strings stay byte-identical, not only equivalent.
    raw_before = parse_dlg(game.before[DLG_KEY], semantic=False)
    raw_after = parse_dlg(files(game)[DLG_KEY], semantic=False)
    assert raw_after[:4] == raw_before[:4]
    assert raw_after[4]["transitions"][0]["action"] == raw_before[4]["transitions"][0]["action"]


def test_bgee_shape_installs(tmp_path):
    game = make_game(tmp_path, make_dialog(stalker="STALKE"), game="bgee")
    install(game)
    assert_choice(game, handin_state=4)


def test_recompiled_variant_with_reordered_extra_actions_and_existing_reply(tmp_path):
    # Another editor's one-line, lower-case, reordered hand-in text with other
    # mods' additions and alternative take/escape actions; the hand-in also has
    # a trigger and an existing reply beside another reply, and is not last.
    raw = ('erasejournalentry(26931) createcreatureobject("helmho",myself,0,0,0)'
           ' AddexperienceParty(500)\ttakepartyitemnum( "helm07" , 1 )\r\n'
           'CreateCreature("DOOMGU",[418.460],S) SetGlobal("HelmDone","GLOBAL",1)'
           ' givegoldforce(5000) escapeareamove("AR0100",10,10,S)')
    variant = make_dialog().replace(
        "  IF ~~ THEN DO ~GiveGoldForce(5000)",
        '  IF ~Global("HelmMood","GLOBAL",0)~ THEN REPLY #555 DO ~GiveGoldForce(5000)',
    ).replace(
        "SOLVED_JOURNAL #26934 EXIT\n",
        "SOLVED_JOURNAL #26934 EXIT\n  IF ~~ THEN REPLY #556 EXIT\n",
    ) + "IF ~True()~ THEN BEGIN 5\n  SAY #20000\n  IF ~~ THEN EXIT\nEND\n"
    game = make_game(tmp_path, variant)
    rewrite_actions(game, "GiveGoldForce(5000)", raw)
    transcript = install(game)
    after = assert_choice(game, handin_state=4, reply_was=555,
                          expect_trigger='Global("HelmMood","GLOBAL",0)')
    assert after[4]["transitions"][0]["action"] == _actions(raw, True)
    assert after[-1]["transitions"][0]["action"] == _actions(
        'createcreatureobject("helmho",myself,0,0,0) CreateCreature("DOOMGU",[418.460],S)'
        f' erasejournalentry(26931) {FIGHT_GLOBAL} Enemy()', True)
    assert "AddexperienceParty takepartyitemnum SetGlobal givegoldforce escapeareamove" in transcript


def test_handin_found_by_meaning_when_states_are_reordered(tmp_path):
    # Hand-in first, a decoy that takes the helm without leaving, and one that
    # leaves without the helm: neither decoy is the hand-in.
    extra = """IF ~Global("Decoy","GLOBAL",1)~ THEN BEGIN 10
  SAY #30000
  IF ~~ THEN DO ~TakePartyItem("HELM07")~ EXIT
  IF ~~ THEN DO ~EscapeArea()~ EXIT
END
"""
    dialog = make_dialog(stalker="STALKE_")
    handin_block = dialog[dialog.index('IF ~PartyHasItem("HELM07")~'):]
    dialog = dialog.replace(handin_block, "").replace(
        "BEGIN ~DEGROD~\n", "BEGIN ~DEGROD~\n" + handin_block + extra)
    game = make_game(tmp_path, dialog)
    install(game)
    assert_choice(game, handin_state=0)


@pytest.mark.parametrize("case,message", [
    ("missing_take", "no transition in DEGROD.DLG takes the Helm of Balduran"),
    ("missing_escape", "no transition in DEGROD.DLG takes the Helm of Balduran"),
    ("two_handins", "has 2 Helm of Balduran hand-ins (states 3 4)"),
    ("handin_interjection", "hand-in state 4 in DEGROD.DLG also continues without a player reply"),
    ("already_applied", "choice is already present in DEGROD.DLG"),
])
def test_ambiguous_or_unsupported_handins_skip_cleanly(tmp_path, case, message):
    base = ("GiveGoldForce(5000)\nTakePartyItem(\"HELM07\")\n"
            + SERVANTS.format(stalker="STALKE_") + JOURNAL + "EscapeArea()\n")
    dialog = {
        "missing_take": make_dialog(handin=base.replace('TakePartyItem("HELM07")\n', "")),
        "missing_escape": make_dialog(handin=base.replace("EscapeArea()\n", "")),
        "two_handins": make_dialog().replace(
            "  IF ~~ THEN EXIT\nEND\nIF ~PartyHasItem",
            f"  IF ~~ THEN DO ~{base}~ EXIT\nEND\nIF ~PartyHasItem"),
        "handin_interjection": make_dialog(handin=base, handin_extra=interjection(
            "IMOENJ", "X#ImoenHelm", "imoen2", 9)),
        "already_applied": make_dialog(handin=base).replace(
            'GOTO 2\n', f'GOTO 2\n  IF ~~ THEN DO ~{FIGHT_GLOBAL} Enemy()~ EXIT\n', 1),
    }[case]
    game = make_game(tmp_path, dialog)
    assert_skipped(game, message)


def test_invalid_dialog_skips_cleanly(tmp_path):
    game = make_game(tmp_path, make_dialog())
    path = next(p for p in game.override.iterdir() if p.name.upper() == "DEGROD.DLG")
    data = bytearray(path.read_bytes())
    struct.pack_into("<I", data, 0x28, len(data) + 100)  # action table past EOF
    path.write_bytes(bytes(data))
    game.before = files(game)
    assert_skipped(game, "DEGROD.DLG is not a valid dialog (a state, transition, trigger or action table lies outside the file)")


def test_unbalanced_handin_actions_skip_cleanly(tmp_path):
    handin = 'TakePartyItem("HELM07") CreateCreature("HELMHO",[371.427],S EscapeArea()'
    game = make_game(tmp_path, make_dialog(handin=handin))
    assert_skipped(game, "could not be separated into individual actions")


def test_missing_dialog_and_unsupported_game_are_not_attempted(tmp_path):
    for name, dialog, game_type in (("nodlg", None, "eet"), ("bg2ee", make_dialog(), "bg2ee")):
        (tmp_path / name).mkdir()
        game = make_game(tmp_path / name, dialog, game=game_type)
        result, transcript = run(game)
        assert result.returncode == 0, transcript
        assert "SKIPPING" in transcript or "NOT INSTALLED" in transcript, transcript
        assert "SUCCESSFULLY INSTALLED" not in transcript
        assert files(game) == game.before
