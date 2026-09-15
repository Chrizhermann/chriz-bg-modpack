"""Exercise production continuity patches with WeiDU in disposable fake games.

Set WEIDU to WeiDU 249+. CBM_CONTINUITY_GAME optionally adds read-only copies
of installed templates and scripts. These are installer tests, not engine tests.
"""

import os
from pathlib import Path
import re
import shutil
import struct
import unittest

import test_safana_inventory as safana_helpers
from test_safana_inventory import REPO, WEIDU, OTHER_BLOCK, find_resource, snapshot


CASES = {
    "xan": {
        "dv": "O#XAN", "cre": "O#Xan09", "area": "AR1000",
        "spawn": "O#XanSpawned", "point": "[2745.321]", "facing": "4",
        "extra": 'SetGlobal("O#XanExperienceSet","GLOBAL",3)',
        "old": '''IF
Global("O#XanSpawned","GLOBAL",0)
THEN
RESPONSE #100
CreateCreature("O#Xan09",[2745.321],4)
SetGlobal("O#XanSpawned","GLOBAL",1)
Continue()
END
''',
    },
    "yeslick": {
        "dv": "LK#YESLK", "cre": "lk#yesl", "area": "AR2010",
        "spawn": "LK#YeslickExists", "point": "[586.318]", "facing": "5",
        "extra": "",
        "old": '''IF
    Global("LK#YeslickExists","GLOBAL",0)
THEN
  RESPONSE #100
    SetGlobal("LK#YeslickExists","GLOBAL",1)
    CreateCreature("lk#yesl",[586.318],5)
END
''',
    },
}


def norm(text):
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"\s+", "", text).lower().replace("setdialogue(", "setdialog(")
    return text.replace(",w)", ",4)").replace("face(w)", "face(4)")


@unittest.skipUnless(WEIDU, "Set WEIDU to a WeiDU 249+ executable")
class CompanionContinuityInstallerTests(unittest.TestCase):
    setUp = safana_helpers.SafanaInventoryInstallerTests.setUp
    run_weidu = safana_helpers.SafanaInventoryInstallerTests.run_weidu

    def prepare(self):
        library_dir = self.game / "chriz-bg-modpack/lib"
        library_dir.mkdir(parents=True)
        # Read the actual production include tree, including identity preflight.
        for path in (REPO / "chriz-bg-modpack/lib").glob("*.tpa"):
            shutil.copy2(path, library_dir / path.name)
        identity = library_dir / "cbm_continuity_identity.tpa"
        if not identity.exists():
            self.fail("Production cbm_continuity_identity.tpa must exist")
        with (self.override / "action.ids").open("a") as stream:
            stream.write('''7 CreateCreature(S:NewObject*,P:Location*,I:Face*DIR)
15 GiveItem(S:Object*,O:Target*)
166 SetNumTimesTalkedTo(I:Num*)
82 CreateItem(S:ResRef*,I:Usage1*,I:Usage2*,I:Usage3*)
320 SetPlayerSound(O:Object*,I:StrRef*,I:Slot*SNDSLOT)
''')
        with (self.override / "trigger.ids").open("a") as stream:
            stream.write("0x4030 False()\n")
        (self.override / "sndslot.ids").write_text("IDS V1.0\n")
        # Header-only CRE fields and valid empty resource fixtures suffice to
        # exercise resource resolution; all actor data is checked byte-exact.
        self.scripts = ["cbmcls", "cbmrace", "cbmgen", "cbmdef", "cbmovr"]
        for resref in self.scripts:
            (self.override / f"{resref}.bcs").write_bytes(b"SC\nSC\n")
        (self.override / "cbmdlg.dlg").write_bytes(
            b"DLG V1.0" + struct.pack("<8I", 0, 40, 0, 40, 40, 0, 40, 0)
        )

    def prepare_public(self, eet_source=True):
        self.prepare()
        shutil.copytree(REPO / "chriz-bg-modpack", self.game / "chriz-bg-modpack", dirs_exist_ok=True)
        shutil.copy2(REPO / "setup-chriz-bg-modpack.tp2", self.game)
        if eet_source:
            eet = Path(os.environ["CBM_EET_SOURCE"])
            # Linux WeiDU resolves game paths in lowercase.
            (self.game / "eet/lib").mkdir(parents=True)
            shutil.copy2(eet / "lib/macros.tph", self.game / "eet/lib/macros.tph")
        with (self.game / "weidu.log").open("a") as stream:
            stream.write("~XAN/XAN.TP2~ #0 #0 // Xan v19\n~YESLICKNPC/YESLICKNPC.TP2~ #0 #0 // Yeslick v5\n")

    def public_install(self, number, expected_success=True):
        return self.run_weidu(
            "setup-chriz-bg-modpack.tp2", "--force-install-list", str(number),
            "--language", "0", "--use-lang", "en_US", "--quick-log",
            expected_success=expected_success,
        )

    def make_fatesp(self):
        legacy = '  IF ~Global("YeslickSummoned","GLOBAL",0)~ THEN REPLY #0 EXIT\n'
        (self.game / "fatesp.d").write_text(
            'BEGIN ~FATESP~\nIF ~True()~ THEN BEGIN first\n SAY #0\n' + legacy * 3
            + '  IF ~Global("LK#YESLKSummoned","GLOBAL",0)~ THEN REPLY #0 EXIT\nEND\n'
        )
        self.run_weidu("fatesp.d", "--out", "override")

    def make_template(self, case, blades=None):
        if blades is None:
            blades = ["O#XANMB", "RING01"] if case["dv"] == "O#XAN" else ["HAMM01"]
        data = bytearray(0x2D4 + len(blades) * 20)
        data[:8] = b"CRE V1.0"
        data[0x280:0x280 + len(case["dv"])] = case["dv"].encode("ascii")
        data[0x2CC:0x2D2] = b"cbmdlg"
        for offset, name in zip([0x250, 0x258, 0x260, 0x268, 0x248], self.scripts):
            data[offset:offset + len(name)] = name.encode("ascii")
        for slot in range(100):
            struct.pack_into("<I", data, 0xA4 + slot * 4, slot)
        # Deliberately non-default progression metadata: never rewritten.
        data[0x234:0x238] = bytes([19, 11, 7, 1])
        data[0x238:0x23E] = bytes([18, 43, 18, 17, 18, 16])
        struct.pack_into("<I", data, 0x244, 0x40000000)
        struct.pack_into("<II", data, 0x2BC, 0x2D4, len(blades))
        for index, item in enumerate(blades):
            pos = 0x2D4 + index * 20
            data[pos:pos + len(item)] = item.encode("ascii")
            (self.override / f"{item.lower()}.itm").write_bytes(b"ITM V1  " + bytes(106))
        (self.override / f'{case["cre"].lower()}.cre').write_bytes(data)
        return bytes(data)

    def compile_area(self, case, body=None):
        path = self.game / f'{case["area"].lower()}.baf'
        path.write_text(OTHER_BLOCK + (body if body is not None else case["old"]) + OTHER_BLOCK)
        self.run_weidu(path.name, "--out", "override")

    def harness(self, cases):
        body = ('BACKUP ~ci-backup~\nAUTHOR ~test~\nBEGIN ~Continuity arrival fixture~\n'
                'INCLUDE ~chriz-bg-modpack/lib/cbm_companion_continuity.tpa~\n')
        for name in cases:
            case = CASES[name]
            (self.game / f"{name}-old.baf").write_text(case["old"])
            body += 'LAF cbm_continuity_arrival STR_VAR\n'
            for key in ("dv", "cre", "area", "spawn", "point", "facing", "extra"):
                body += f'cbm_{key} = ~{case[key]}~\n'
            body += f'cbm_old = ~{name}-old.baf~\nEND\n'
        (self.game / "ci-harness.tp2").write_text(body)

    def install(self, expected_success=True):
        return self.run_weidu(
            "ci-harness.tp2", "--force-install-list", "0", "--language", "0",
            "--use-lang", "en_US", "--quick-log", expected_success=expected_success,
        )

    def decompile(self, case):
        self.run_weidu(f'override/{case["area"].lower()}.bcs', "--out", ".")
        return find_resource(self.game, f'{case["area"]}.baf').read_text()

    def assert_arrival(self, case, text, blade="O#XANMB", expected_sounds=None,
                       dialog="cbmdlg", scripts=None, expected_others=2):
        blocks = re.findall(r"(?ms)^IF\s.*?^END\s*", text)
        target = [b for b in blocks if case["spawn"].lower() in b.lower()]
        self.assertEqual(len(target), 2, text)
        returned = next(b for b in target if "MoveGlobal(" in b)
        fresh = next(b for b in target if "CreateCreature(" in b)
        returned, fresh = norm(returned), norm(fresh)
        dv = case["dv"].lower()
        self.assertIn(f'beeninparty("{dv}")!statecheck("{dv}",state_really_dead)', returned)
        self.assertIn(f'!beeninparty("{dv}")', fresh)
        self.assertNotIn("createcreature(", returned)
        self.assertNotIn("moveglobal(", fresh)
        self.assertNotIn("destroyallequipment(", fresh)
        self.assertEqual(norm(case["old"]).replace("then", f'!beeninparty("{dv}")then'), fresh)
        move = f'moveglobal("{case["area"].lower()}","{dv}",{case["point"]})'
        self.assertEqual(returned.count(move), 1)
        self.assertEqual(returned.count("destroyallequipment()"), 1)
        self.assertIn(f'actionoverride("{dv}",setnumtimestalkedto(0))', returned)
        self.assertIn(f'actionoverride("{dv}",setglobal("kickedout","locals",0))', returned)
        self.assertIn(f'actionoverride("{dv}",setdialog("{dialog.lower()}"))', returned)
        for name, slot in zip(scripts if scripts is not None else self.scripts, [4, 5, 6, 7, 0]):
            self.assertIn(f'actionoverride("{dv}",changeaiscript("{name.lower()}",{slot}))', returned)
        # IDS may decompile numeric slots into names; normalize those separately
        # in caller where needed. No stat/XP/level/spell reconstruction actions.
        for forbidden in ("setstat(", "addxpobject(", "setxp(", "levelup(", "addspell(",
                          "addspecialability(", "addkit(", "changeclass(", "resurrect("):
            self.assertNotIn(forbidden, returned)
        if blade:
            self.assertIn(f'actionoverride("{dv}",createitem("{blade.lower()}",1,0,0))', returned)
            self.assertEqual(returned.count("createitem("), 1)
            self.assertLess(returned.index("destroyallequipment()"), returned.index("createitem("))
        else:
            self.assertNotIn("createitem(", returned)
        if case["extra"]:
            self.assertIn(norm(case["extra"]), returned)
        if expected_sounds is None:
            expected_sounds = range(100)
        sounds = re.findall(r'setplayersound\("' + re.escape(dv) + r'",(-?\d+),(\d+)\)', returned)
        self.assertEqual(sounds, [(str(sound), str(slot)) for slot, sound in enumerate(expected_sounds)])
        other = [b for b in blocks if "CBMOtherQuest".lower() in b.lower()]
        self.assertEqual([norm(b) for b in other], [norm(OTHER_BLOCK)] * expected_others)

    def normalize_ids(self, text):
        for name, value in {"OVERRIDE": 0, "CLASS": 4, "RACE": 5, "GENERAL": 6, "DEFAULT": 7}.items():
            text = re.sub(r"," + name + r"\)", f",{value})", text, flags=re.I)
        return text

    def test_both_arrival_paths_preserve_templates_and_uninstall_exactly(self):
        self.prepare()
        for case in CASES.values():
            self.make_template(case)
            self.compile_area(case)
        self.harness(CASES)
        before = snapshot(self.override)
        self.install()
        for name, case in CASES.items():
            self.assert_arrival(case, self.normalize_ids(self.decompile(case)),
                                blade="O#XANMB" if name == "xan" else None)
        after = snapshot(self.override)
        self.assertEqual(before.keys(), after.keys())
        self.assertEqual({p for p in before if before[p] != after[p]}, {"ar1000.bcs", "ar2010.bcs"})
        self.run_weidu("ci-harness.tp2", "--force-uninstall-list", "0", "--quick-log")
        self.assertEqual(snapshot(self.override), before)
        self.install()
        self.assertEqual(snapshot(self.override), after)

    def test_selected_alternative_moonblade_is_the_only_recreated_item(self):
        self.prepare()
        case = CASES["xan"]
        self.make_template(case, ["O#XANMS", "RING01", "HAMM01"])
        self.compile_area(case)
        self.harness(["xan"])
        self.install()
        self.assert_arrival(case, self.normalize_ids(self.decompile(case)), blade="O#XANMS")

    def test_second_companion_hook_failure_rolls_back_first_companion(self):
        self.prepare()
        for case in CASES.values():
            self.make_template(case)
            body = case["old"] if case is CASES["xan"] else case["old"].replace("[586.318]", "[587.318]")
            self.compile_area(case, body)
        self.harness(CASES)
        before = snapshot(self.override)
        output = self.install(expected_success=False)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertIn("spawn code differs", output)
        self.assertEqual(snapshot(self.override), before)

    def test_missing_duplicate_and_malformed_moonblade_fail_atomically(self):
        self.prepare()
        case = CASES["xan"]
        self.compile_area(case)
        self.harness(["xan"])
        for mode in ("none", "duplicate", "missing_resource", "truncated_inventory"):
            with self.subTest(mode=mode):
                items = [] if mode == "none" else (["O#XANMB", "O#XANMS"] if mode == "duplicate" else ["O#XANMB"])
                data = bytearray(self.make_template(case, items))
                if mode == "missing_resource":
                    find_resource(self.override, "O#XANMB.itm").unlink()
                if mode == "truncated_inventory":
                    struct.pack_into("<I", data, 0x2C0, 40)
                    find_resource(self.override, "O#XAN09.cre").write_bytes(data)
                before = snapshot(self.override)
                output = self.install(expected_success=False)
                self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
                self.assertIn("cbm_companion_continuity:", output)
                self.assertEqual(snapshot(self.override), before)

    def test_duplicate_and_missing_spawn_hooks_fail_atomically(self):
        self.prepare()
        case = CASES["yeslick"]
        self.make_template(case)
        self.harness(["yeslick"])
        for body in ("", case["old"] * 2):
            with self.subTest(body=body):
                self.compile_area(case, body)
                before = snapshot(self.override)
                output = self.install(expected_success=False)
                self.assertIn("ambiguous", output)
                self.assertEqual(snapshot(self.override), before)

    @unittest.skipUnless(os.environ.get("CBM_EET_SOURCE"), "Set CBM_EET_SOURCE to an EET source directory")
    def test_bg1_alaghor_preset_survives_public_199_without_regrant_or_reset(self):
        from tests.test_yeslick_alaghor import provider, creature, TARGETS

        self.prepare_public()
        log = self.game / "weidu.log"
        log.write_text(log.read_text().replace(
            "~YESLICKNPC/YESLICKNPC.TP2~ #0 #0", "~YESLICKNPC/YESLICKNPC.TP2~ #0 #1"
        ))
        provider(self.override)
        for case in CASES.values():
            self.make_template(case)
            self.compile_area(case)
        self.make_fatesp()
        for name in TARGETS:
            (self.override / f"{name.lower()}.cre").write_bytes(creature())
        before = snapshot(self.override)
        self.public_install(188)
        preset = {name: (self.override / f"{name.lower()}.cre").read_bytes() for name in TARGETS}
        self.public_install(199)
        for name, original in preset.items():
            expected = bytearray(original)
            expected[0x280:0x2a0] = b"LK#YESLK".ljust(32, b"\0")
            actual = (self.override / f"{name.lower()}.cre").read_bytes()
            self.assertEqual(bytes(expected), actual)
            self.assertEqual(0x40690000, struct.unpack_from("<I", actual, 0x244)[0])
        arrival = self.normalize_ids(self.decompile(CASES["yeslick"]))
        self.assert_arrival(CASES["yeslick"], arrival, blade=None)
        self.assertNotIn("addkit(", norm(arrival))
        self.assertNotIn("addspecialability(", norm(arrival))
        self.run_weidu("setup-chriz-bg-modpack.tp2", "--force-uninstall-list", "199", "--quick-log")
        self.run_weidu("setup-chriz-bg-modpack.tp2", "--force-uninstall-list", "188", "--quick-log")
        self.assertEqual(snapshot(self.override), before)

    @unittest.skipUnless(os.environ.get("CBM_EET_SOURCE"), "Set CBM_EET_SOURCE to an EET source directory")
    def test_public_199_complete_install_and_fatesp_replies(self):
        self.prepare_public()
        for case in CASES.values():
            self.make_template(case)
            self.compile_area(case)
        self.make_fatesp()
        before = snapshot(self.override)
        self.public_install(199)
        for name, case in CASES.items():
            self.assert_arrival(case, self.normalize_ids(self.decompile(case)),
                                blade="O#XANMB" if name == "xan" else None)
        self.run_weidu("override/fatesp.dlg", "--out", ".")
        fatesp = norm(find_resource(self.game, "fatesp.d").read_text())
        self.assertEqual(fatesp.count("false()"), 3)
        self.assertNotIn('global("yeslicksummoned","global",0)', fatesp)
        self.assertIn('global("lk#yeslksummoned","global",0)', fatesp)
        after = snapshot(self.override)
        self.assertEqual(before.keys(), after.keys())
        self.assertEqual({p for p in before if before[p] != after[p]}, {"ar1000.bcs", "ar2010.bcs", "fatesp.dlg"})
        self.run_weidu("setup-chriz-bg-modpack.tp2", "--force-uninstall-list", "199", "--quick-log")
        self.assertEqual(snapshot(self.override), before)

    @unittest.skipUnless(os.environ.get("CBM_EET_SOURCE"), "Set CBM_EET_SOURCE to an EET source directory")
    def test_public_199_rejects_late_order_and_legacy_stat_transfer(self):
        self.prepare_public()
        (self.game / "weidu.log").write_text("~EET_END/EET_END.TP2~ #0 #0 // EET end\n")
        before = snapshot(self.override)
        output = self.public_install(199)
        self.assertIn("SKIPPING:", output)
        self.assertNotIn("SUCCESSFULLY INSTALLED", output)
        self.assertEqual(snapshot(self.override), before)
        (self.game / "weidu.log").write_text("~XAN/XAN.TP2~ #0 #0 // Xan v19\n")
        (self.override / "M_K#FP.lua").write_text("-- conflicting legacy stat transfer\n")
        before = snapshot(self.override)
        output = self.public_install(199, expected_success=False)
        self.assertIn("remove legacy", output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        self.assertEqual(snapshot(self.override), before)

    def test_public_199_wrong_game_or_missing_eet_source_skips_without_changes(self):
        self.prepare_public(eet_source=False)
        before = snapshot(self.override)
        output = self.public_install(199)
        self.assertIn("SKIPPING:", output)
        self.assertNotIn("SUCCESSFULLY INSTALLED", output)
        self.assertEqual(snapshot(self.override), before)
        (self.override / "eet.flag").unlink()
        before = snapshot(self.override)
        output = self.public_install(199)
        self.assertIn("SKIPPING:", output)
        self.assertEqual(snapshot(self.override), before)

    def test_public_189_installs_and_uninstalls_real_inventory_library(self):
        self.prepare_public(eet_source=False)
        (self.game / "ar0311.baf").write_text(safana_helpers.ARRIVAL)
        self.run_weidu("ar0311.baf", "--out", "override")
        before = snapshot(self.override)
        self.public_install(189)
        self.run_weidu("override/ar0311.bcs", "--out", ".")
        self.assertEqual(norm(find_resource(self.game, "ar0311.baf").read_text()).count(
            'actionoverride("safana",destroyallequipment())'), 1)
        self.run_weidu("setup-chriz-bg-modpack.tp2", "--force-uninstall-list", "189", "--quick-log")
        self.assertEqual(snapshot(self.override), before)

    @unittest.skipUnless(os.environ.get("CBM_CONTINUITY_GAME"), "Optional read-only installed companion resources")
    def test_effective_installed_templates_and_area_scripts_read_only(self):
        self.prepare()
        source = Path(os.environ["CBM_CONTINUITY_GAME"]) / "override"
        source_bytes = {}
        for path in source.iterdir():
            # ADD_SPELL.IDS is WeiDU's temporary install bookkeeping, not an
            # engine IDS dependency; rollback intentionally removes that file.
            if path.suffix.lower() == ".ids" and path.name.lower() != "add_spell.ids":
                shutil.copy2(path, self.override / path.name.lower())
        # Use numeric slots/directions in decompilation for portable comparison.
        (self.override / "sndslot.ids").write_text("IDS V1.0\n")
        (self.override / "dir.ids").write_text("IDS V1.0\n4 W\n")
        (self.override / "timeoday.ids").write_text("IDS V1.0\n")
        expected = {}
        for name, case in CASES.items():
            template_path = find_resource(source, case["cre"] + ".cre")
            template = template_path.read_bytes()
            scripts = [template[pos:pos+8].split(b"\0")[0].decode("ascii")
                       for pos in [0x250, 0x258, 0x260, 0x268, 0x248]]
            scripts = ["" if script.upper() == "NONE" else script for script in scripts]
            dialog = template[0x2CC:0x2D4].split(b"\0")[0].decode("ascii")
            sounds = struct.unpack_from("<100i", template, 0xA4)
            resources = [case["cre"] + ".cre", case["area"] + ".bcs", dialog + ".dlg"]
            resources += [script + ".bcs" for script in scripts if script]
            blade = None
            if name == "xan":
                start, count = struct.unpack_from("<II", template, 0x2BC)
                items = [template[start+i*20:start+i*20+8].split(b"\0")[0].decode("ascii") for i in range(count)]
                blades = [item for item in items if item.upper() in ("O#XANMB", "O#XANMS")]
                self.assertEqual(len(blades), 1)
                blade = blades[0]
                resources += [blade + ".itm"]
            for resource in resources:
                path = find_resource(source, resource)
                source_bytes[path] = path.read_bytes()
                shutil.copy2(path, self.override / path.name.lower())
            expected[name] = dict(dialog=dialog, scripts=scripts, blade=blade,
                                  expected_sounds=sounds, expected_others=0)
        self.harness(CASES)
        legacy_present = any(b"K#FP_" in find_resource(self.override, case["area"] + ".bcs").read_bytes()
                             for case in CASES.values())
        if legacy_present:
            # The inspected live installation contains old stat-transfer
            # hooks. They must be rejected unchanged. Then use the independently
            # audited mod-source spawn fixtures with the effective donor CREs.
            rejected_before = snapshot(self.override)
            output = self.install(expected_success=False)
            self.assertIn("ambiguous", output)
            self.assertEqual(snapshot(self.override), rejected_before)
            for name, case in CASES.items():
                self.compile_area(case)
                expected[name]["expected_others"] = 2
        before = snapshot(self.override)
        self.install()
        for name, case in CASES.items():
            self.assert_arrival(case, self.normalize_ids(self.decompile(case)), **expected[name])
        self.run_weidu("ci-harness.tp2", "--force-uninstall-list", "0", "--quick-log")
        self.assertEqual(snapshot(self.override), before)
        for path, data in source_bytes.items():
            self.assertEqual(path.read_bytes(), data, str(path))


if __name__ == "__main__":
    unittest.main()
