"""Component 460: party AI Defensive Stance obeys "Use special abilities".

Real WeiDU compiles synthetic party AI scripts (written here from scratch with
BG2:EE trigger and action signatures) and installs the public component into
disposable synthetic games. No game resources are read or copied.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from tests.test_collection_defaults import (
    ONE_EMPTY_STRING_TLK,
    ROOT,
    TP2,
    file_tree,
    find_weidu,
    resource_path,
    write_marker_key_and_bif,
)


COMPONENT = 460
GATE = 'Global("BDAI_DISABLE_SPECIAL","LOCALS",0)'

# Only the IDS entries the fixtures use; values match BG2:EE.
IDS = {
    "TRIGGER.IDS": """0x400F Global(S:Name*,S:Area*,I:Value*)
0x4018 Range(O:Object*,I:Range*)
0x402A NumCreatureGT(O:Object*,I:Number*)
0x402B ActionListEmpty()
0x4031 HaveSpellRES(S:Spell*)
0x4041 GlobalTimerNotExpired(S:Name*,S:Area*)
0x4043 InParty(O:Object*)
0x4045 CheckStatGT(O:Object*,I:Value*,I:StatNum*Stats)
0x4089 OR(I:OrCount*)
0x40E2 CheckSpellState(O:Object*,I:State*splstate)""",
    "ACTION.IDS": """0 NoAction()
30 SetGlobal(S:Name*,S:Area*,I:Value*)
31 Spell(O:Target*,I:Spell*Spell)
31 SpellRES(S:RES*,O:Target*)
36 Continue()
86 SetInterrupt(I:State*Boolean)
113 ForceSpellRES(S:RES*,O:Target)
115 SetGlobalTimer(S:Name*,S:Area*,I:Time*GTimes)
160 ApplySpellRES(S:RES*,O:Target)
181 ReallyForceSpellRES(S:RES*,O:Target)""",
    "OBJECT.IDS": "0 Nothing\n1 Myself\n12 NearestEnemyOf\n18 LastSeenBy",
    "SPLSTATE.IDS": "81 DEFENSIVE_STANCE",
    "STATS.IDS": "34 LEVEL",
    "BOOLEAN.IDS": "0 FALSE\n1 TRUE",
    "GTIMES.IDS": "6 ONE_ROUND",
    "SPELL.IDS": "4144 KENSAI_KIA",
    "EA.IDS": "0 ANYONE\n200 EVILCUTOFF",
}

UNRELATED = """IF
  Global("BDAI_RESET","GLOBAL",1)
THEN
  RESPONSE #100
    SetGlobal("BDAI_RESET","GLOBAL",0)
    Continue()
END
"""
# The vanilla BG2:EE block already reads the option.
GATED_STANCE = """IF
  Global("BDAI_DISABLE_SPECIAL","LOCALS",0)
  HaveSpellRES("SPDWD02")
  !CheckSpellState(Myself,DEFENSIVE_STANCE)
  Range(NearestEnemyOf(Myself),6)
  OR(2)
    CheckStatGT(LastSeenBy(Myself),12,LEVEL)
    NumCreatureGT([EVILCUTOFF],3)
  !GlobalTimerNotExpired("BD_Cast","LOCALS")
THEN
  RESPONSE #100
    SetInterrupt(FALSE)
    SetGlobalTimer("BD_Cast","LOCALS",ONE_ROUND)
    SpellRES("SPDWD02",Myself)
    SetInterrupt(TRUE)
END
"""
# Another ability without the option is out of scope and must stay as it is.
OTHER_ABILITY = """IF
  ActionListEmpty()
  InParty(Myself)
THEN
  RESPONSE #100
    Spell(Myself,KENSAI_KIA)
END
"""
# EET's BG1-only block from BDDEFAI-eb.baf.
EET_BG1_STANCE = """IF
{gate}  Global("ENDOFBG1","GLOBAL",0)
  HaveSpellRES("SPDWD02")
  !CheckSpellState(Myself,DEFENSIVE_STANCE)
  Range(NearestEnemyOf(Myself),6)
  OR(2)
    CheckStatGT(LastSeenBy(Myself),6,LEVEL)
    NumCreatureGT([EVILCUTOFF],3)
  !GlobalTimerNotExpired("BD_Cast","LOCALS")
THEN
  RESPONSE #100
    SetInterrupt(FALSE)
    SetGlobalTimer("BD_Cast","LOCALS",ONE_ROUND)
    SpellRES("SPDWD02",Myself)
    SetInterrupt(TRUE)
END
"""
# An OR group first, lower-case resref, another cast action and two responses.
OR_FIRST_STANCE = """IF
{gate}  OR(2)
    CheckStatGT(LastSeenBy(Myself),6,LEVEL)
    NumCreatureGT([EVILCUTOFF],3)
  HaveSpellRES("spdwd02")
THEN
  RESPONSE #50
    ForceSpellRES("spdwd02",Myself)
  RESPONSE #50
    Continue()
END
"""
# Only the conditions name the stance; the block casts something else.
CONDITION_ONLY = """IF
  HaveSpellRES("SPDWD02")
  InParty(Myself)
THEN
  RESPONSE #100
    ApplySpellRES("SPWI101",Myself)
END
"""
# A different form of the option check is the author's own condition.
OTHER_OPTION_FORM = """IF
  !Global("BDAI_DISABLE_SPECIAL","LOCALS",1)
  HaveSpellRES("SPDWD02")
THEN
  RESPONSE #100
    ReallyForceSpellRES("SPDWD02",Myself)
END
"""
COMPANION_STANCE = """IF
{gate}  HaveSpellRES("SPDWD02")
  Range(NearestEnemyOf(Myself),6)
THEN
  RESPONSE #100
    ApplySpellRES("SPDWD02",Myself)
END
"""


def _gate(template: str, gated: bool) -> str:
    return template.format(gate=f"  {GATE}\n" if gated else "")


def default_script(gated: bool) -> str:
    return "\n".join((
        UNRELATED,
        GATED_STANCE,
        OTHER_ABILITY,
        _gate(EET_BG1_STANCE, gated),
        _gate(OR_FIRST_STANCE, gated),
        CONDITION_ONLY,
        OTHER_OPTION_FORM,
    ))


def companion_script(gated: bool) -> str:
    return "\n".join((UNRELATED, _gate(COMPANION_STANCE, gated)))


PLAIN_SCRIPT = "\n".join((UNRELATED, OTHER_ABILITY))

# Row 1 names the default script; later rows name companion scripts, which may
# be missing from the game or repeat the default.
PARTYAI = (
    "2DA V1.0\n"
    "BDDEFAI\n"
    "          AI_SCRIPT\n"
    "COMPANION BDCOMPC\n"
    "PLAIN     bdplainc\n"
    "MISSING   BDMISSC\n"
    "DEFAULT2  BDDEFAI\n"
)


def transcript(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


class SyntheticPartyAIGame:
    def __init__(self, root: Path, weidu: str) -> None:
        self.root = root
        self.weidu = weidu
        root.mkdir()
        self.override = root / "override"
        self.override.mkdir()
        self.work = root.parent / "work"
        self.work.mkdir()
        shutil.copy2(TP2, root / TP2.name)
        shutil.copytree(ROOT / "chriz-bg-modpack", root / "chriz-bg-modpack")
        write_marker_key_and_bif(root)
        for name, body in IDS.items():
            resource_path(self.override, name).write_text(
                f"IDS V1.0\n{body}\n", encoding="ascii", newline="\n"
            )
        lang_tlk = root / "lang/en_us/dialog.tlk"
        lang_tlk.parent.mkdir(parents=True)
        lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        (root / "dialog.tlk").write_bytes(ONE_EMPTY_STRING_TLK)

    def compile(self, name: str, baf: str) -> bytes:
        source = self.work / f"{name.lower()}.baf"
        source.write_text(baf, encoding="ascii", newline="\n")
        result = self._weidu("--out", str(self.work), str(source))
        compiled = [
            path for path in self.work.iterdir() if path.name.lower() == f"{name.lower()}.bcs"
        ]
        if len(compiled) != 1:
            raise AssertionError(transcript(result))
        data = compiled[0].read_bytes()
        compiled[0].unlink()
        source.unlink()
        return data

    def add_script(self, name: str, baf: str) -> None:
        resource_path(self.override, f"{name}.BCS").write_bytes(self.compile(name, baf))

    def write_partyai(self, text: str, newline: str = "\n") -> None:
        resource_path(self.override, "PARTYAI.2DA").write_bytes(
            text.replace("\n", newline).encode("ascii")
        )

    def run(self, operation: str) -> subprocess.CompletedProcess[str]:
        return self._weidu(
            TP2.name, "--no-auto-tp2", operation, str(COMPONENT),
            "--language", "0", "--no-exit-pause", "--noautoupdate", "--quick-log",
        )

    def _weidu(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.weidu, *arguments, "--game", str(self.root), "--use-lang", "en_us"],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )

    def active_log(self) -> str:
        path = next(
            (candidate for candidate in self.root.iterdir() if candidate.name.lower() == "weidu.log"),
            None,
        )
        if path is None:
            return ""
        return "\n".join(
            line
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if not line.lstrip().startswith("//")
        )

    def installed(self) -> bool:
        return re.search(rf"(?m)#0\s+#{COMPONENT}\b", self.active_log()) is not None


def stage_game(root: Path, weidu: str, newline: str = "\n") -> SyntheticPartyAIGame:
    """Default and companion scripts with ungated stance blocks, plus scripts
    the component must leave alone."""
    game = SyntheticPartyAIGame(root / "game", weidu)
    game.add_script("BDDEFAI", default_script(gated=False))
    game.add_script("BDCOMPC", companion_script(gated=False))
    game.add_script("BDPLAINC", PLAIN_SCRIPT)
    # A creature script outside PARTYAI has no "Use special abilities" option.
    game.add_script("ENEMYDD", companion_script(gated=False))
    game.write_partyai(PARTYAI, newline)
    return game


def expected_tree(
    game: SyntheticPartyAIGame, before: dict[str, bytes], *, prefix: str = ""
) -> dict[str, bytes]:
    """Only the ungated stance blocks of the party AI scripts change."""
    expected = dict(before)
    expected[f"{prefix}BDDEFAI.BCS"] = game.compile("expected_default", default_script(gated=True))
    expected[f"{prefix}BDCOMPC.BCS"] = game.compile("expected_companion", companion_script(gated=True))
    return expected


class DefensiveStanceAITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.weidu = find_weidu()

    def _root(self) -> Path:
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        temporary = tempfile.TemporaryDirectory(prefix="cbm-defensive-stance-ai-")
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name)

    def _game(self) -> SyntheticPartyAIGame:
        return SyntheticPartyAIGame(self._root() / "game", self.weidu)

    def _install(self, game: SyntheticPartyAIGame) -> str:
        result = game.run("--force-install-list")
        text = transcript(result)
        self.assertEqual(0, result.returncode, text)
        self.assertIn("SUCCESSFULLY INSTALLED", text)
        self.assertNotIn("NOT INSTALLED DUE TO ERRORS", text)
        self.assertTrue(game.installed(), text)
        return text

    def _assert_not_installed(self, game: SyntheticPartyAIGame, message: str) -> None:
        before = file_tree(game.override)
        text = transcript(game.run("--force-install-list"))
        self.assertNotIn("SUCCESSFULLY INSTALLED", text)
        self.assertIn(message, text)
        self.assertFalse(game.installed(), text)
        self.assertEqual(before, file_tree(game.override))

    def test_gates_only_ungated_stance_blocks_of_party_ai_scripts(self) -> None:
        for newline in ("\n", "\r\n"):
            with self.subTest(partyai_newline=repr(newline)):
                game = stage_game(self._root(), self.weidu, newline)
                before = file_tree(game.override)
                text = self._install(game)
                after = file_tree(game.override)
                self.assertEqual(expected_tree(game, before), after)
                self.assertIn(
                    'BDDEFAI.BCS now checks "Use special abilities" in 2 Defensive Stance block(s)', text
                )
                self.assertIn(
                    'BDCOMPC.BCS now checks "Use special abilities" in 1 Defensive Stance block(s)', text
                )

    def test_default_script_name_comes_from_partyai(self) -> None:
        game = self._game()
        game.add_script("XYZDEFAI", default_script(gated=False))
        # Not named by this PARTYAI, so BDDEFAI is no party AI script here.
        game.add_script("BDDEFAI", default_script(gated=False))
        game.write_partyai("2DA V1.0\nXYZDEFAI\n          AI_SCRIPT\n")
        before = file_tree(game.override)
        self._install(game)
        after = file_tree(game.override)
        expected = dict(before)
        expected["XYZDEFAI.BCS"] = game.compile("expected", default_script(gated=True))
        self.assertEqual(expected, after)

    def test_uninstall_restores_and_reinstall_matches(self) -> None:
        game = stage_game(self._root(), self.weidu)
        before = file_tree(game.override)
        self._install(game)
        first = file_tree(game.override)

        result = game.run("--force-uninstall-list")
        text = transcript(result)
        self.assertEqual(0, result.returncode, text)
        self.assertIn("SUCCESSFULLY REMOVED", text)
        self.assertFalse(game.installed(), text)
        self.assertEqual(before, file_tree(game.override))

        self._install(game)
        self.assertEqual(first, file_tree(game.override))

    def test_already_gated_scripts_stay_byte_identical(self) -> None:
        game = self._game()
        game.add_script("BDDEFAI", default_script(gated=True))
        game.add_script("BDCOMPC", companion_script(gated=True))
        game.add_script("BDPLAINC", PLAIN_SCRIPT)
        game.write_partyai(PARTYAI)
        before = file_tree(game.override)
        text = self._install(game)
        self.assertEqual(before, file_tree(game.override))
        self.assertIn('every party AI use of Defensive Stance already checks "Use special abilities"', text)

    def test_party_ai_without_the_stance_installs_unchanged(self) -> None:
        game = self._game()
        game.add_script("BDDEFAI", PLAIN_SCRIPT)
        game.add_script("BDCOMPC", PLAIN_SCRIPT)
        game.add_script("BDPLAINC", PLAIN_SCRIPT)
        game.write_partyai(PARTYAI)
        before = file_tree(game.override)
        text = self._install(game)
        self.assertEqual(before, file_tree(game.override))
        self.assertIn("no party AI script uses Defensive Stance; nothing to gate", text)

    def test_game_without_partyai_is_not_installed(self) -> None:
        game = self._game()
        game.add_script("BDDEFAI", default_script(gated=False))
        self._assert_not_installed(game, "cbm_defensive_stance_ai: PARTYAI.2DA is missing.")

    def test_unreadable_partyai_fails_without_mutation(self) -> None:
        game = self._game()
        game.add_script("BDDEFAI", default_script(gated=False))
        game.write_partyai("BDDEFAI\nAI_SCRIPT\nCOMPANION BDCOMPC\n")
        self._assert_not_installed(game, "PARTYAI.2DA is not a readable 2DA table")


if __name__ == "__main__":
    unittest.main()
