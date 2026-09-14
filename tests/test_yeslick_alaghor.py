"""BG1 Yeslick preset: real WeiDU, authored resources, no installed-game writes.

The priest CLAB/qd_multiclass fixtures model the provider's resource contract.
Their preservation is tested; these tests do not execute native recruitment.
"""

from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tests.test_utility_xp_installer import SyntheticGame, WEIDU, _file_tree


COMPONENT = 188
TARGETS = ("YESLIC", "YESLIC5")
EXCLUDED = ("YESLID", "JAYES", "BDYESTIM", "LK#YESL", "LK#YES25")


def creature(*, kit=0x4000, fighter=17, priest=5, dv="Yeslick", cls=8):
    cre = bytearray(0x2D4)
    cre[:8] = b"CRE V1.0"
    struct.pack_into("<III", cre, 0x14, 2000, 99001, 317)
    cre[0x52:0x59] = bytes((13, 1, 9, 8, 7, 6, 5))
    cre[0x234:0x237] = bytes((fighter, priest, 0))
    cre[0x238:0x23F] = bytes((16, 0, 10, 12, 17, 17, 10))
    struct.pack_into("<I", cre, 0x244, kit << 16)
    cre[0x248:0x250] = b"YESLICK\0"
    cre[0x270:0x276] = bytes((128, 1, 4, cls, 0, 1))
    cre[0x280:0x2A0] = dv.encode().ljust(32, b"\0")
    cre[0x2CC:0x2D4] = b"YESLICK\0"
    # Distinct personal/priest spells, spent memorization, equipment and effect.
    known = struct.pack("<8sHH", b"SPIN112", 0, 2) + struct.pack("<8sHH", b"SPPR101", 0, 0)
    memory = struct.pack("<HHHHII", 0, 1, 1, 2, 0, 1)
    memorized = struct.pack("<8sI", b"SPIN112", 0)
    slots = b"\xff\xff" * 40
    items = struct.pack("<8sHHHHI", b"CBMGEAR", 0, 3, 2, 1, 1)
    effect = bytearray(0x30)
    struct.pack_into("<H", effect, 0, 233)
    struct.pack_into("<II", effect, 4, 2, 97)
    effect[12] = 9
    chunks = (known, memory, memorized, slots, items, bytes(effect))
    cursor = len(cre)
    for offset, count, chunk in zip((0x2A0, 0x2A8, 0x2B0, 0x2B8, 0x2BC, 0x2C4),
                                    (2, 1, 1, None, 1, 1), chunks):
        struct.pack_into("<I", cre, offset, cursor)
        if count is not None:
            struct.pack_into("<I", cre, offset + 4, count)
        cursor += len(chunk)
    return bytes(cre) + b"".join(chunks)


def clab(rows, levels=40):
    return "2DA V1.0\n****\n  " + " ".join(map(str, range(1, levels + 1))) + "\n" + "".join(
        name + " " + " ".join(cells.get(level, "****") for level in range(1, levels + 1)) + "\n"
        for name, cells in rows.items()
    )


def dispatch(kit, grants):
    """Authored qd_multiclass shape: one SPL ability, kit-filtered external EFFs."""
    data = bytearray(0x72 + 0x28 + len(grants) * 0x30)
    data[:8] = b"SPL V1  "
    struct.pack_into("<IHI", data, 0x64, 0x72, 1, 0x9A)
    struct.pack_into("<HH", data, 0x72 + 0x1E, len(grants), 0)
    for index, (_, resref) in enumerate(grants):
        pos = 0x9A + index * 0x30
        struct.pack_into("<HBBII", data, pos, 177, 1, 0, kit, 9)
        data[pos + 0x0C] = 9
        data[pos + 0x12] = 100
        data[pos + 0x14:pos + 0x1C] = (resref + "#").encode().ljust(8, b"\0")
    return bytes(data)


def provider(override, kit=0x4069, kit_clab="CBMYCLAB", *, passive=True):
    (override / "kit.ids").write_text(f"IDS V1.0\n0x4000 TRUECLASS\n{kit:#x} LK_ALAGHOR\n")
    (override / "class.ids").write_text("IDS V1.0\n3 CLERIC\n8 FIGHTER_CLERIC\n")
    # Row number, KITIDS and CLAB name deliberately do not match vanilla guesses.
    (override / "kitlist.2da").write_text(
        "2DA V1.0\n*\n ROWNAME LOWER MIXED HELP ABILITIES PROFICIENCY UNUSABLE CLASS KITIDS\n"
        f"91 LK_ALAGHOR 11 12 13 {kit_clab} 25 0x00100000 3 {kit:#x}\n"
    )
    grants = {8: [("GA", "CBMYA")], 14: [("GA", "CBMYB")], 16: [("GA", "CBMYC")]}
    if passive:
        grants[1] = [("AP", "CBMYPS")]
    (override / f"{kit_clab.lower()}.2da").write_text(clab({
        f"ABILITY{i}": {level: f"{kind}_{resref}"}
        for i, (level, entries) in enumerate(grants.items(), 1)
        for kind, resref in entries
    }))
    (override / "qd_multi.qd").write_bytes(b"provider marker")
    (override / "clabpr01.2da").write_text(clab({
        "QD_MULTI": {level: f"AP_QD_MCP{level:02}" for level in range(1, 41)}
    }))
    for level in range(1, 41):
        (override / f"qd_mcp{level:02}.spl").write_bytes(dispatch(kit, grants.get(level, [])))
    for entries in grants.values():
        for kind, resref in entries:
            (override / f"{resref.lower()}.spl").write_bytes(dispatch(kit, []))
            eff = bytearray(0x110)
            eff[:8] = b"EFF V2.0"
            struct.pack_into("<I", eff, 0x10, 171 if kind == "GA" else 146)
            eff[0x30:0x38] = resref.encode().ljust(8, b"\0")
            (override / f"{resref.lower()}#.eff").write_bytes(eff)
    return grants


@unittest.skipUnless(WEIDU, "Set WEIDU to WeiDU 249")
class YeslickAlaghorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cbm-yeslick-")
        self.addCleanup(self.temporary.cleanup)
        self.game = SyntheticGame(Path(self.temporary.name) / "game", game="eet", eeex=False)
        self.override = self.game.override
        self.grants = provider(self.override)
        for name in TARGETS + EXCLUDED:
            (self.override / f"{name.lower()}.cre").write_bytes(creature())
        self.log("~YESLICKNPC/YESLICKNPC.TP2~ #0 #1 // Alaghor\n")

    def log(self, text):
        (self.game.root / "weidu.log").write_text(text)

    def run_component(self, number=COMPONENT, *, uninstall=False, success=True):
        result = subprocess.run(
            [str(WEIDU), "setup-chriz-bg-modpack.tp2", "--noautoupdate", "--no-exit-pause",
             "--use-lang", "en_us", "--language", "0", "--game", str(self.game.root),
             "--force-uninstall-list" if uninstall else "--force-install-list", str(number)],
            cwd=self.game.root, capture_output=True, text=True, timeout=60,
        )
        output = result.stdout + result.stderr
        if success:
            self.assertEqual(0, result.returncode, output)
            self.assertIn("SUCCESSFULLY", output)
        return output

    def test_only_recruitment_kits_change_and_uninstall_restores_every_byte(self):
        before = _file_tree(self.override)
        self.run_component()
        expected = dict(before)
        for name in TARGETS:
            key = name + ".CRE"
            data = bytearray(expected[key])
            struct.pack_into("<I", data, 0x244, 0x40690000)
            expected[key] = bytes(data)
        self.assertEqual(expected, _file_tree(self.override))
        self.run_component(uninstall=True)
        self.assertEqual(before, _file_tree(self.override))

    def test_levels_and_provider_grants_remain_on_the_priest_schedule(self):
        for priest in (1, 5, 7, 8, 13, 14, 15, 16, 24):
            with self.subTest(priest=priest):
                for name in TARGETS:
                    (self.override / f"{name.lower()}.cre").write_bytes(creature(priest=priest))
                before = _file_tree(self.override)
                self.run_component()
                # The installer must not pre-grant AP/GA spells or duplicate
                # the provider's native recruitment/level-up work.
                for name in TARGETS:
                    old = before[name + ".CRE"]
                    new = (self.override / f"{name.lower()}.cre").read_bytes()
                    self.assertEqual(old[:0x244] + old[0x248:], new[:0x244] + new[0x248:])
                for key, value in before.items():
                    if not key.endswith(".CRE"):
                        self.assertEqual(value, _file_tree(self.override)[key])
                self.run_component(uninstall=True)

    def test_dynamic_kit_and_clab_and_already_target_are_supported(self):
        provider(self.override, kit=0x4073, kit_clab="CBMLOCAL")
        (self.override / "yeslic5.cre").write_bytes(creature(kit=0x4073))
        self.run_component()
        for name in TARGETS:
            data = (self.override / f"{name.lower()}.cre").read_bytes()
            self.assertEqual(0x40730000, struct.unpack_from("<I", data, 0x244)[0])

    def test_vanilla_or_missing_provider_and_late_order_do_not_mutate(self):
        for log in ("", "~YESLICKNPC/YESLICKNPC.TP2~ #0 #0 // Vanilla\n",
                    "~YESLICKNPC/YESLICKNPC.TP2~ #0 #1\n~EET_END/EET_END.TP2~ #0 #0\n",
                    "~YESLICKNPC/YESLICKNPC.TP2~ #0 #1\n~SETUP-CHRIZ-BG-MODPACK.TP2~ #0 #199\n"):
            with self.subTest(log=log):
                self.log(log)
                before = _file_tree(self.override)
                output = self.run_component(success=False)
                self.assertNotIn("SUCCESSFULLY INSTALLED", output)
                self.assertEqual(before, _file_tree(self.override))

    def test_bad_second_recruit_rolls_back_the_first(self):
        for altered in (creature(kit=0x4017), creature(cls=2), creature(dv="Impostor"),
                        creature(priest=0), b"CRE V1.0"):
            with self.subTest(header=altered[:8]):
                (self.override / "yeslic5.cre").write_bytes(altered)
                before = _file_tree(self.override)
                output = self.run_component(success=False)
                self.assertNotIn("SUCCESSFULLY INSTALLED", output)
                self.assertEqual(before, _file_tree(self.override))

    def test_missing_local_kit_clab_or_multiclass_dispatch_is_rejected(self):
        for name in ("kit.ids", "kitlist.2da", "cbmyclab.2da", "clabpr01.2da",
                     "qd_multi.qd", "qd_mcp08.spl", "cbmya#.eff", "cbmya.spl"):
            with self.subTest(missing=name):
                path = self.override / name
                data = path.read_bytes()
                path.unlink()
                before = _file_tree(self.override)
                output = self.run_component(success=False)
                self.assertNotIn("SUCCESSFULLY INSTALLED", output)
                self.assertEqual(before, _file_tree(self.override))
                path.write_bytes(data)

    def test_wrong_kit_or_early_only_grant_is_not_accepted_as_level_eight(self):
        path = self.override / "qd_mcp08.spl"
        original = path.read_bytes()
        for wrong in (dispatch(0x4068, self.grants[8]), dispatch(0x4069, [])):
            with self.subTest(wrong_dispatch=wrong[-16:]):
                # A grant at fighter/priest level 5 cannot stand in for the
                # installed kit CLAB's required priest level 8 registration.
                (self.override / "qd_mcp05.spl").write_bytes(original)
                path.write_bytes(wrong)
                before = _file_tree(self.override)
                output = self.run_component(success=False)
                self.assertIn("not registered", output)
                self.assertEqual(before, _file_tree(self.override))

    def test_later_priest_passives_and_ragged_fifty_level_clab_are_supported(self):
        path = self.override / "cbmyclab.2da"
        # Keep older kit rows at 40 columns, as in the effective Combined data.
        path.write_text(path.read_text() + "LATER " + " ".join(["AP_CBMPASS"] * 50) + "\n")
        (self.override / "clabpr01.2da").write_text(clab({
            "PRIEST": {level: "AP_CBMPASS" for level in range(1, 51)},
            "QD_MULTI": {level: f"AP_QD_MCP{level:02}" for level in range(1, 51)},
        }, levels=50))
        (self.override / "cbmpass.spl").write_bytes(dispatch(0x4069, []))
        before = _file_tree(self.override)
        self.run_component()
        for key, value in before.items():
            if not key.endswith(".CRE"):
                self.assertEqual(value, _file_tree(self.override)[key])

    def test_kitlist_disagreement_and_duplicate_named_rows_fail(self):
        path = self.override / "kitlist.2da"
        original = path.read_text()
        for content in (original.replace("0x4069", "0x4068"),
                        original + original.splitlines()[-1].replace("91 ", "92 ", 1) + "\n"):
            with self.subTest(kitlist=content[-30:]):
                path.write_text(content)
                before = _file_tree(self.override)
                output = self.run_component(success=False)
                self.assertNotIn("SUCCESSFULLY INSTALLED", output)
                self.assertEqual(before, _file_tree(self.override))

    def test_bg2_only_installation_does_not_apply_the_bg1_preset(self):
        (self.override / "eet.flag").unlink()
        before = _file_tree(self.override)
        output = self.run_component(success=False)
        self.assertNotIn("SUCCESSFULLY INSTALLED", output)
        self.assertEqual(before, _file_tree(self.override))


if __name__ == "__main__":
    unittest.main()
