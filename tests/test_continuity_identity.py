"""Run real WeiDU against identity fixtures in temporary games only.

Set WEIDU to a WeiDU executable and CBM_EET_SOURCE to an EET source directory
containing lib/macros.tph. The upstream parser is copied read-only into each
fixture; it is deliberately not vendored or mocked.
"""

import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

from test_safana_inventory import IDS, find_resource, snapshot


REPO = Path(__file__).resolve().parents[1]
LIBRARY = REPO / "chriz-bg-modpack/lib/cbm_continuity_identity.tpa"
WEIDU = os.environ.get("WEIDU") or shutil.which("weidu")
EET_SOURCE = os.environ.get("CBM_EET_SOURCE")


def put_text(data, offset, value, width):
    data[offset:offset + width] = value.encode("ascii").ljust(width, b"\0")


def effect(version=0, opcode=319, param2=11, resource="Xan"):
    data = bytearray(0x108 if version else 0x30)
    if version:
        struct.pack_into("<I", data, 8, opcode)
        struct.pack_into("<I", data, 0x18, param2)
        put_text(data, 0x28, resource, 8)
    else:
        struct.pack_into("<H", data, 0, opcode)
        struct.pack_into("<I", data, 8, param2)
        put_text(data, 0x14, resource, 8)
    return data


def creature(dv="Xan", version=0):
    data = bytearray(0x2d4)
    data[:8] = b"CRE V1.0"
    data[0x33] = version
    # Distinct sound slots detect an accidental second EET sound migration.
    for index in range(100):
        struct.pack_into("<I", data, 0xa4 + index * 4, 9000 + index)
    data[0x230:0x248] = bytes(range(24))
    put_text(data, 0x248, "Xan", 8)  # script resref: must not be renamed
    put_text(data, 0x280, dv, 32)
    put_text(data, 0x2cc, "Xan", 8)  # dialogue resref: must not be renamed
    struct.pack_into("<II", data, 0x2c4, len(data), 2)
    data += effect(version, resource=dv)
    data += effect(version, opcode=146, resource="Xan")
    return data


def area():
    data = bytearray(0x11c + 3 * 0x110)
    data[:8] = b"AREAV1.0"
    struct.pack_into("<IH", data, 0x54, 0x11c, 3)
    for index, flags in enumerate((9, 1, 8)):
        actor = 0x11c + index * 0x110
        put_text(data, actor, "Xan", 32)
        struct.pack_into("<I", data, actor + 0x28, flags)
        put_text(data, actor + 0x80, "Xan", 8)
    embedded = creature("Yeslick", 1)
    struct.pack_into("<II", data, 0x11c + 2 * 0x110 + 0x88, len(data), len(embedded))
    data += embedded
    struct.pack_into("<II", data, 0x88, len(data), 1)
    variable = bytearray(0x54)
    put_text(variable, 0, "SPRITE_IS_DEADXAN", 32)
    struct.pack_into("<I", variable, 0x28, 3)
    return data + variable


def item_or_spell(kind):
    size = 0x38 if kind == "itm" else 0x28
    data = bytearray(0x72 + size)
    data[:8] = b"ITM V1  " if kind == "itm" else b"SPL V1  "
    struct.pack_into("<IHIHH", data, 0x64, 0x72, 1, len(data), 0, 1)
    struct.pack_into("<HH", data, 0x72 + 0x1e, 2, 1)
    data += effect(resource="Xan")
    data += effect(opcode=146, resource="Xan")
    data += effect(param2=10, resource="Xan")
    return data


SCRIPT = '''IF
  See("Xan")
  BeenInParty("Yeslick")
  Global("SPRITE_IS_DEADXAN","GLOBAL",0)
  Global("XanQuest","GLOBAL",1)
THEN
  RESPONSE #100
    ActionOverride("Xan",GiveItemCreate("Xan","Yeslick",1,0,0))
    CreateCreature("Xan",[20.30],4)
    ActionOverride("Yeslick",ChangeAIScript("Xan",OVERRIDE))
    ActionOverride("Xan",SetDialog("Xan"))
    DisplayString("Xan",9000)
    SetGlobal("SPRITE_IS_DEADYESLICK","GLOBAL",2)
    SetGlobal("Xan","GLOBAL",3)
    Continue()
END
'''

DIALOGUE = '''BEGIN ~cbmdlga~
IF ~See("Xan") Global("XanQuest","GLOBAL",1)~ THEN BEGIN entry
  SAY #0
  IF ~BeenInParty("Yeslick")~ THEN DO ~ActionOverride("Xan",SetDialog("Xan"))~
    EXTERN ~cbmdlgb~ 0
END
BEGIN ~cbmdlgb~
IF ~~ THEN BEGIN entry
  SAY #0
  IF ~~ THEN DO ~SetGlobal("SPRITE_IS_DEADXAN","GLOBAL",1)~ EXIT
END
BEGIN ~cbmdlgc~
IF ~Global("XanQuest","GLOBAL",1)~ THEN BEGIN entry
  SAY #0
  IF ~~ THEN DO ~SetGlobal("YeslickQuest","GLOBAL",2)~ EXIT
END
'''


@unittest.skipUnless(WEIDU and EET_SOURCE, "Set WEIDU and CBM_EET_SOURCE")
class ContinuityIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cbm-identity-")
        self.addCleanup(self.temp.cleanup)
        self.game = Path(self.temp.name)
        self.override = self.game / "override"
        self.override.mkdir()
        (self.game / "chitin.key").write_bytes(struct.pack("<8sIIII", b"KEY V1  ", 0, 0, 24, 24))
        tlk = struct.pack("<8sHII", b"TLK V1  ", 0, 1, 44) + bytes(26)
        (self.game / "dialog.tlk").write_bytes(tlk)
        (self.game / "lang/en_us").mkdir(parents=True)
        (self.game / "lang/en_us/dialog.tlk").write_bytes(tlk)
        (self.override / "oh6000.are").write_bytes(b"AREA V1.0")
        (self.override / "eet.flag").write_text("fixture\n")
        # Linux WeiDU resolves game paths in lowercase.
        (self.game / "eet/lib").mkdir(parents=True)
        shutil.copy2(Path(EET_SOURCE) / "lib/macros.tph", self.game / "eet/lib/macros.tph")
        extra = {
            "action": '\n7 CreateCreature(S:NewObject*,P:Location*,I:Face*Dir)\n'
                      '139 DisplayString(O:Object*,I:StrRef*)\n'
                      '140 GiveItemCreate(S:ResRef*,O:Object*,I:Usage1*,I:Usage2*,I:Usage3*)\n',
            "trigger": '\n0x401C See(O:Object*)\n',
        }
        for name, body in IDS.items():
            (self.override / f"{name}.ids").write_text("IDS V1.0\n" + body + extra.get(name, ""))
        self.protected = {p: (self.game / p).read_bytes() for p in
                          ("chitin.key", "dialog.tlk", "lang/en_us/dialog.tlk", "eet/lib/macros.tph")}
        self.harness()

    def harness(self, xan=1, yeslick=1, twice=False):
        call = f'LAF cbm_continuity_normalize_identity INT_VAR cbmci_xan={xan} cbmci_yeslick={yeslick} END\n'
        (self.game / "identity-harness.tp2").write_text(
            'BACKUP ~backup~\nAUTHOR ~test~\nBEGIN ~Identity fixture~\n'
            f'INCLUDE ~{LIBRARY.as_posix()}~\n' + call * (2 if twice else 1)
        )

    def run_weidu(self, *args, success=True):
        result = subprocess.run([str(WEIDU), "--game", str(self.game), "--no-auto-tp2",
                                 "--no-exit-pause", *args], cwd=self.game,
                                capture_output=True, text=True, errors="replace", timeout=90)
        output = result.stdout + result.stderr
        if success:
            self.assertEqual(result.returncode, 0, output)
            self.assertNotIn("ERROR", output, output)
        for name, before in self.protected.items():
            self.assertEqual((self.game / name).read_bytes(), before, name)
        return output

    def install(self, success=True):
        return self.run_weidu("identity-harness.tp2", "--force-install-list", "0",
                              "--language", "0", "--use-lang", "en_US", "--quick-log", success=success)

    def compile(self):
        (self.game / "cbmtest.baf").write_text(SCRIPT)
        self.run_weidu("cbmtest.baf", "--out", "override")
        (self.game / "test.d").write_text(DIALOGUE)
        self.run_weidu("test.d", "--out", "override")

    def read(self, name):
        return find_resource(self.override, name).read_bytes()

    def decompile(self, name):
        self.run_weidu(str(find_resource(self.override, name)), "--out", ".")
        suffix = ".baf" if name.endswith(".bcs") else ".d"
        return find_resource(self.game, Path(name).stem + suffix).read_text().lower()

    def test_scripts_dialogues_change_only_typed_identities_and_counters(self):
        self.compile()
        # Candidate substrings in unrelated globals must not cause rewrites.
        (self.game / "unrelated.baf").write_text('IF Global("XanQuest","GLOBAL",1) THEN RESPONSE #100 SetGlobal("YeslickQuest","GLOBAL",2) END')
        self.run_weidu("unrelated.baf", "--out", "override")
        unrelated = self.read("unrelated.bcs")
        unrelated_dialogue = self.read("cbmdlgc.dlg")
        self.install()
        baf = re.sub(r"\s+", "", self.decompile("cbmtest.bcs"))
        self.assertIn('see("o#xan")', baf)
        self.assertIn('beeninparty("lk#yeslk")', baf)
        self.assertIn('actionoverride("o#xan",giveitemcreate("xan","lk#yeslk",1,0,0))', baf)
        self.assertIn('createcreature("xan",[20.30],w)', baf)
        self.assertIn('changeaiscript("xan",override)', baf)
        self.assertIn('setdialog("xan")', baf)
        self.assertIn('displaystring("o#xan",9000)', baf)
        self.assertIn('global("sprite_is_deado#xan","global",0)', baf)
        self.assertIn('setglobal("sprite_is_deadlk#yeslk","global",2)', baf)
        self.assertIn('setglobal("xan","global",3)', baf)
        self.assertEqual(self.read("unrelated.bcs"), unrelated)
        self.assertEqual(self.read("cbmdlgc.dlg"), unrelated_dialogue)
        dialogue = self.decompile("cbmdlga.dlg")
        self.assertIn('"o#xan"', dialogue)
        self.assertIn('"lk#yeslk"', dialogue)
        self.assertIn('setdialog("xan")', dialogue)
        self.assertIn('extern ~cbmdlgb~', dialogue)

    def test_binary_fields_preserve_other_bytes_and_both_effect_layouts(self):
        fixtures = {"xan_.cre": creature(), "yeslic.cre": creature("Yeslick", 1),
                    "cbmarea.are": area(), "sw1h13.itm": item_or_spell("itm"),
                    "cbmspell.spl": item_or_spell("spl"),
                    "cbmeffect.eff": b"EFF V2.0" + effect(1, resource="Yeslick")}
        for name, data in fixtures.items():
            (self.override / name).write_bytes(data)
        expected = {name: bytearray(data) for name, data in fixtures.items()}
        put_text(expected["xan_.cre"], 0x280, "O#XAN", 32)
        put_text(expected["xan_.cre"], 0x2d4 + 0x14, "O#XAN", 8)
        put_text(expected["yeslic.cre"], 0x280, "LK#YESLK", 32)
        put_text(expected["yeslic.cre"], 0x2d4 + 0x28, "LK#YESLK", 8)
        for index in (0, 2):
            put_text(expected["cbmarea.are"], 0x11c + index * 0x110, "O#XAN", 32)
        embedded = 0x11c + 3 * 0x110
        put_text(expected["cbmarea.are"], embedded + 0x280, "LK#YESLK", 32)
        put_text(expected["cbmarea.are"], embedded + 0x2d4 + 0x28, "LK#YESLK", 8)
        put_text(expected["cbmarea.are"], len(expected["cbmarea.are"]) - 0x54, "SPRITE_IS_DEADO#XAN", 32)
        put_text(expected["sw1h13.itm"], 0x72 + 0x38 + 0x14, "O#XAN", 8)
        put_text(expected["cbmspell.spl"], 0x72 + 0x28 + 0x14, "O#XAN", 8)
        put_text(expected["cbmeffect.eff"], 8 + 0x28, "LK#YESLK", 8)
        self.install()
        for name, data in expected.items():
            self.assertEqual(self.read(name), data, name)

    def test_split_effect_variable_counter_is_mapped_without_other_fields(self):
        data = bytearray(b"EFF V2.0") + effect(1, opcode=187, param2=0, resource="SPRITE_I")
        put_text(data, 8 + 0x68, "S_DEADXA", 8)
        put_text(data, 8 + 0x70, "N", 8)
        (self.override / "deadmark.eff").write_bytes(data)
        expected = bytearray(data)
        put_text(expected, 8 + 0x68, "S_DEADO#", 8)
        put_text(expected, 8 + 0x70, "XAN", 8)
        self.install()
        self.assertEqual(self.read("deadmark.eff"), expected)

    def tables(self):
        for name in ("bgdialog", "bddialog", "bgbanter", "bdbanter", "partyai", "npclvlds"):
            (self.override / f"{name}.2da").write_text("2DA V1.0\n*\n VALUE\nXan Xan\nYeslick Yeslic5\nOther Xan\n")
        for name in ("interact", "sodinter"):
            (self.override / f"{name}.2da").write_text("2DA V1.0\n0\n Xan Yeslick\nXan 0 c\nYeslick s 0\n")
        (self.override / "item_use.2da").write_text("2DA V1.0\n*\n USER STRREF FLAG USERNAME\nSW1H13 Xan 10220 2 268\nXan Other 10 2 3\n")
        (self.override / "pdialog.2da").write_text("2DA V1.0\n*\n POST\nXan XanP\nO#XAN O#XANP\nLK#YESLK LK#YESLP\n")

    def test_table_keys_item_user_and_matrix_axes_with_uninstall_and_repeat(self):
        self.tables()
        self.compile()
        before = snapshot(self.override)
        self.harness(twice=True)
        self.install()
        after = snapshot(self.override)
        self.assertEqual(after["pdialog.2da"], before["pdialog.2da"])
        for name in ("bgdialog", "bddialog", "bgbanter", "bdbanter", "partyai", "npclvlds"):
            rows = self.read(name + ".2da").decode().splitlines()[3:]
            self.assertEqual([line.split() for line in rows],
                             [["O#XAN", "Xan"], ["LK#YESLK", "Yeslic5"], ["Other", "Xan"]])
        for name in ("interact", "sodinter"):
            rows = self.read(name + ".2da").decode().splitlines()[2:]
            self.assertEqual([line.split() for line in rows],
                             [["O#XAN", "LK#YESLK"], ["O#XAN", "0", "c"], ["LK#YESLK", "s", "0"]])
        self.assertEqual(self.read("item_use.2da").decode().splitlines()[3].split(),
                         ["SW1H13", "O#XAN", "10220", "2", "268"])
        self.run_weidu("identity-harness.tp2", "--force-uninstall-list", "0", "--quick-log")
        self.assertEqual(snapshot(self.override), before)
        self.harness(twice=False)
        self.install()
        self.assertEqual(snapshot(self.override), after)

    def test_collision_fails_before_any_change(self):
        self.tables()
        self.compile()
        for collision in ("row", "column"):
            with self.subTest(collision=collision):
                self.tables()
                name = "bddialog.2da" if collision == "row" else "sodinter.2da"
                path = self.override / name
                if collision == "row":
                    path.write_text(path.read_text() + "O#XAN MODROW\n")
                else:
                    path.write_text("2DA V1.0\n0\n Xan O#XAN\nXan 0 c\nYeslick s 0\n")
                before = snapshot(self.override)
                output = self.install(success=False)
                self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
                self.assertIn("conflicting", output)
                self.assertEqual(snapshot(self.override), before)

    def test_disabled_mapping_and_empty_selection_leave_resources_untouched(self):
        (self.override / "yeslic.cre").write_bytes(creature("Yeslick", 1))
        original = snapshot(self.override)
        self.harness(xan=1, yeslick=0)
        self.install()
        self.assertEqual(snapshot(self.override), original)
        self.run_weidu("identity-harness.tp2", "--force-uninstall-list", "0", "--quick-log")
        self.harness(xan=0, yeslick=0)
        self.install()
        self.assertEqual(snapshot(self.override), original)

    def test_matrix_header_positions_for_one_and_many_columns(self):
        for headings in (("Xan",), ("Xan", "Yeslick", "Other", "Fourth")):
            with self.subTest(headings=headings):
                rows = [" ".join(headings)] + [name + " " + " ".join("0" for _ in headings)
                                               for name in headings]
                (self.override / "interact.2da").write_text("2DA V1.0\n0\n" + "\n".join(rows) + "\n")
                self.install()
                actual = [line.split() for line in self.read("interact.2da").decode().splitlines()[2:]]
                names = [{"Xan": "O#XAN", "Yeslick": "LK#YESLK"}.get(name, name) for name in headings]
                self.assertEqual(actual, [names] + [[name] + ["0"] * len(names) for name in names])
                self.run_weidu("identity-harness.tp2", "--force-uninstall-list", "0", "--quick-log")

    def test_invalid_candidate_effects_roll_back_already_patched_tables(self):
        self.tables()
        bad = creature()
        struct.pack_into("<I", bad, 0x2c8, 999999)
        (self.override / "xan_.cre").write_bytes(bad)
        before = snapshot(self.override)
        output = self.install(success=False)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertIn("invalid CRE effects", output)
        self.assertEqual(snapshot(self.override), before)

    def test_shared_eet_command_metadata_is_restored(self):
        harness = self.game / "identity-harness.tp2"
        # Define caller-owned metadata before entering the helper's scope.
        body = harness.read_text().replace('BEGIN ~Identity fixture~',
                                          'BEGIN ~Identity fixture~\nINCLUDE ~EET/lib/macros.tph~')
        harness.write_text(body + '''
ACTION_IF NOT VARIABLE_IS_SET $array_DISPLAYSTRING(~2~ ~2~) BEGIN
  FAIL ~EET DisplayString stringref argument was removed~
END
OUTER_SPRINT fixture_type $array_DISPLAYSTRING(~2~ ~2~)
ACTION_IF NOT (~%fixture_type%~ STR_EQ ~tra~) BEGIN
  FAIL ~EET DisplayString argument metadata changed~
END
''')
        self.install()


if __name__ == "__main__":
    unittest.main()
