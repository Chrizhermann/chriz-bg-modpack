"""Real WeiDU tests; only temporary synthetic games are ever modified.

Set WEIDU to a WeiDU 249+ executable. Optionally set CBM_SAFANA_GAME to an
installed EET game to add a read-only copy of its effective AR0311 and IDS.
Run: python -m unittest discover -s tests -p test_safana_inventory.py -v
"""

import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
LIBRARY = REPO / "chriz-bg-modpack/lib/cbm_safana_inventory.tpa"
WEIDU = os.environ.get("WEIDU") or shutil.which("weidu")

# Independent fixture transcribed from Safana v0.5 Extend/ar0311.baf.
ARRIVAL = '''IF
Global("bd_safana_spawn","ar0311",0)
BeenInParty("safana")
!StateCheck("Safana",STATE_REALLY_DEAD)
THEN
RESPONSE #100
SetGlobal("bd_safana_spawn","ar0311",1)
SetGlobal("O#CoranSpawn","GLOBAL",1)
MoveGlobal("ar0311","SAFANA",[250.350])
ApplySpellRES("bdresurr","SAFANA")
SmallWait(1)
ActionOverride("SAFANA",Face(W))
ApplySpellRES("bdrejuve","SAFANA")
ChangeEnemyAlly("SAFANA",NEUTRAL)
ChangeSpecifics("SAFANA",ALLIES)
ActionOverride("SAFANA",ChangeAIScript("SAFANA2",OVERRIDE))
ActionOverride("SAFANA",ChangeAIScript("",CLASS))
ActionOverride("SAFANA",ChangeAIScript("",RACE))
ActionOverride("SAFANA",ChangeAIScript("BDTHIE01",GENERAL))
ActionOverride("SAFANA",ChangeAIScript("",DEFAULT))
ActionOverride("SAFANA",SetDialog("SAFANA2"))
ActionOverride("SAFANA",FaceObject(Player1))
Continue()
END
'''

OTHER_BLOCK = '''IF
  Global("CBMOtherQuest","GLOBAL",0)
THEN
  RESPONSE #100
    SetGlobal("CBMOtherQuest","GLOBAL",1)
    ActionOverride(Player1,Face(W))
END
'''

# Minimal real engine signatures, not mocked compilation or transformations.
IDS = {
    "action": '''0 NoAction()
30 SetGlobal(S:Name*,S:Area*,I:Value*)
36 Continue()
60 ChangeAIScript(S:ScriptFile*,I:Level*Scrlev)
83 SmallWait(I:Time*)
84 Face(I:Direction*DIR)
138 SetDialog(S:DialogFile*)
153 ChangeEnemyAlly(O:Object*,I:Value*EA)
157 ChangeSpecifics(O:Object*,I:Value*Specific)
160 ApplySpellRES(S:RES*,O:Target*)
197 MoveGlobal(S:Area*,O:Object*,P:Point*)
223 DestroyAllEquipment()
229 FaceObject(O:Object*)
''',
    "trigger": '''0x400F Global(S:Name*,S:Area*,I:Value*)
0x4023 True()
0x4037 StateCheck(O:Object*,I:State*State)
0x40DF BeenInParty(S:Name*)
''',
    "object": "1 Myself\n21 Player1\n",
    "state": "0x00000FC0 STATE_REALLY_DEAD\n",
    "dir": "4 W\n",
    "scrlev": "0 OVERRIDE\n4 CLASS\n5 RACE\n6 GENERAL\n7 DEFAULT\n",
    "ea": "128 NEUTRAL\n",
    "specific": "2 ALLIES\n",
    "gender": "",
    "general": "",
    "race": "",
    "class": "",
    "align": "",
    "spell": "",
}


def snapshot(directory):
    return {
        path.relative_to(directory).as_posix().lower(): path.read_bytes()
        for path in directory.rglob("*") if path.is_file()
    }


def find_resource(directory, name):
    matches = [p for p in directory.iterdir() if p.name.lower() == name.lower()]
    if len(matches) != 1:
        raise AssertionError(f"Expected exactly one {name}: {matches}")
    return matches[0]


@unittest.skipUnless(WEIDU, "Set WEIDU to a WeiDU 249+ executable")
class SafanaInventoryInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cbm-safana-")
        self.addCleanup(self.temp.cleanup)
        self.game = Path(self.temp.name)
        self.override = self.game / "override"
        self.override.mkdir()
        # Empty, valid KEY; override provides all test resources.
        (self.game / "chitin.key").write_bytes(
            struct.pack("<8sIIII", b"KEY V1  ", 0, 0, 24, 24)
        )
        tlk = struct.pack("<8sHII", b"TLK V1  ", 0, 1, 44) + bytes(26)
        (self.game / "dialog.tlk").write_bytes(tlk)
        (self.game / "lang/en_us").mkdir(parents=True)
        (self.game / "lang/en_us/dialog.tlk").write_bytes(tlk)
        (self.override / "oh6000.are").write_bytes(b"AREA V1.0")
        (self.override / "eet.flag").write_text("fixture\n")
        (self.game / "weidu.log").write_text(
            "~SAFANA/SAFANA.TP2~ #0 #0 // Safana in Amn: v0.5\n"
        )
        for name, body in IDS.items():
            (self.override / f"{name}.ids").write_text("IDS V1.0\n" + body)
        # The harness includes the production library without duplicating its
        # guards or patch. Compiler and installer run with cwd inside this game.
        (self.game / "safana-harness.tp2").write_text(
            'BACKUP ~backup~\nAUTHOR ~test~\nBEGIN ~Safana fixture~\n'
            f'INCLUDE ~{LIBRARY.as_posix()}~\n'
        )
        self.protected = {
            p: (self.game / p).read_bytes()
            for p in ("chitin.key", "dialog.tlk", "lang/en_us/dialog.tlk")
        }

    def run_weidu(self, *args, expected_success=True):
        result = subprocess.run(
            [str(WEIDU), "--game", str(self.game), "--no-exit-pause",
             "--no-auto-tp2", *args],
            cwd=self.game, capture_output=True, text=True, errors="replace",
            timeout=60,
        )
        output = result.stdout + result.stderr
        if expected_success:
            self.assertEqual(result.returncode, 0, output)
            self.assertNotIn("ERROR", output, output)
        for path, data in self.protected.items():
            self.assertEqual((self.game / path).read_bytes(), data, path)
        return output

    def compile_fixture(self, body=OTHER_BLOCK + ARRIVAL + OTHER_BLOCK):
        (self.game / "ar0311.baf").write_text(body)
        self.run_weidu("ar0311.baf", "--out", "override")

    def install(self, expected_success=True):
        return self.run_weidu(
            "safana-harness.tp2", "--force-install-list", "0",
            "--language", "0", "--use-lang", "en_US", "--quick-log",
            expected_success=expected_success,
        )

    def decompile(self):
        self.run_weidu("override/ar0311.bcs", "--out", ".")
        return find_resource(self.game, "ar0311.baf").read_text()

    def assert_only_inventory_action_added(self, before, after):
        # Ignore whitespace/case emitted by WeiDU, retain action order and every
        # original condition, actor reference, quest action and other block.
        normalize = lambda text: re.sub(r"\s+", "", text).lower()
        before = normalize(before)
        after = normalize(after)
        added = 'actionoverride("safana",destroyallequipment())'
        self.assertEqual(after.count(added), 1)
        self.assertEqual(after.replace(added, ""), before)
        self.assertIn('smallwait(1)' + added + 'actionoverride("safana",face(w))', after)
        self.assertLess(after.index('moveglobal('), after.index(added))

    def test_install_changes_only_original_arrival_and_uninstall_restores_bytes(self):
        self.compile_fixture()
        before_baf = self.decompile()
        before = snapshot(self.override)
        output = self.install()
        self.assertIn("SUCCESSFULLY INSTALLED", output)
        self.assert_only_inventory_action_added(before_baf, self.decompile())
        after = snapshot(self.override)
        self.assertEqual(before.keys(), after.keys())
        self.assertEqual([k for k in before if before[k] != after[k]], ["ar0311.bcs"])
        self.run_weidu("safana-harness.tp2", "--force-uninstall-list", "0", "--quick-log")
        self.assertEqual(snapshot(self.override), before)
        self.install()
        self.assertEqual(snapshot(self.override), after)

    def test_hook_whitespace_and_case_are_compiled_semantically(self):
        self.compile_fixture(ARRIVAL.lower().replace("\n", "\n\t  "))
        before = self.decompile()
        self.install()
        self.assert_only_inventory_action_added(before, self.decompile())

    def test_drift_missing_duplicate_and_prepatched_hooks_fail_atomically(self):
        cases = {
            "missing": OTHER_BLOCK,
            "duplicate": ARRIVAL + ARRIVAL,
            "coordinates": ARRIVAL.replace("[250.350]", "[251.350]"),
            "trigger": ARRIVAL.replace('"ar0311",0', '"ar0311",2'),
            "weight": ARRIVAL.replace("RESPONSE #100", "RESPONSE #50"),
            "additional_action": ARRIVAL.replace("Continue()", "SmallWait(2)\nContinue()"),
            "already_patched": ARRIVAL.replace("SmallWait(1)",
                'SmallWait(1)\nActionOverride("SAFANA",DestroyAllEquipment())'),
        }
        for name, body in cases.items():
            with self.subTest(name=name):
                self.compile_fixture(body)
                before = snapshot(self.override)
                output = self.install(expected_success=False)
                self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
                self.assertIn("cbm_safana_inventory:", output)
                self.assertEqual(snapshot(self.override), before)

    def test_wrong_game_fails_without_resource_changes(self):
        self.compile_fixture()
        (self.override / "eet.flag").unlink()
        before = snapshot(self.override)
        output = self.install(expected_success=False)
        self.assertIn("requires EET", output)
        self.assertEqual(snapshot(self.override), before)

    def test_missing_mod_fails_without_resource_changes(self):
        self.compile_fixture()
        (self.game / "weidu.log").write_text("")
        before = snapshot(self.override)
        output = self.install(expected_success=False)
        self.assertIn("requires Safana in Amn component 0", output)
        self.assertEqual(snapshot(self.override), before)

    @unittest.skipUnless(os.environ.get("CBM_SAFANA_GAME"), "Optional installed-source copy")
    def test_read_only_copy_of_effective_installed_script(self):
        source = Path(os.environ["CBM_SAFANA_GAME"]) / "override"
        original = find_resource(source, "ar0311.bcs")
        original_bytes = original.read_bytes()
        shutil.copy2(original, self.override / "ar0311.bcs")
        for ids in source.iterdir():
            if ids.suffix.lower() == ".ids":
                shutil.copy2(ids, self.override / ids.name.lower())
        before_baf = self.decompile()
        before = snapshot(self.override)
        self.install()
        self.assert_only_inventory_action_added(before_baf, self.decompile())
        self.run_weidu("safana-harness.tp2", "--force-uninstall-list", "0", "--quick-log")
        self.assertEqual(snapshot(self.override), before)
        self.assertEqual(original.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()
