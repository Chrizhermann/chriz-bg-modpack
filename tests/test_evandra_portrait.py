from __future__ import annotations

import hashlib
import tempfile
import unittest

from tests.test_sarah_options import (
    ROOT, SyntheticSarahGame, file_tree, find_weidu, make_sarah_cre,
)


ARTWORK = ROOT / "chriz-bg-modpack/portraits/evandra/rh#eval.bmp"
ARTWORK_SHA256 = "b4bde98aec195d47db521d3cc4d72b636ae5a0f391cc7469ea5d48688b112aad"


class EvandraPortraitTests(unittest.TestCase):
    def test_approved_artwork_is_shipped_unchanged(self):
        self.assertTrue(ARTWORK.is_file(), "Approved Evandra portrait is missing")
        self.assertEqual(ARTWORK_SHA256, hashlib.sha256(ARTWORK.read_bytes()).hexdigest())

    def test_public_component_replaces_only_portraits_and_uninstalls(self):
        weidu = find_weidu()
        if not weidu:
            self.skipTest("Set WEIDU_BIN to run the real installer")
        with tempfile.TemporaryDirectory(prefix="cbm-evandra-portrait-") as raw:
            with tempfile.TemporaryDirectory(dir=raw) as fixture:
                # Reuse a real synthetic-game harness; all other NPC resources
                # deliberately remain present to detect overly broad writes.
                class TempRoot:
                    name = fixture
                game = SyntheticSarahGame(TempRoot(), complete=True)
                for index, name in enumerate(("rh#eva", "rh#ev25", "rh#evamp")):
                    (game.override / f"{name}.cre").write_bytes(make_sarah_cre(index + 1))
                (game.override / "rh#evmes.cre").write_bytes(make_sarah_cre(4))
                (game.override / "rh#eval.bmp").write_bytes(b"old Evandra portrait")
                baseline = file_tree(game.override)
                result = game.run(weidu, "--force-install-list", 225)
                transcript = game.transcript(result)
                self.assertEqual(0, result.returncode, transcript)
                self.assertIn("SUCCESSFULLY INSTALLED", transcript)
                after = file_tree(game.override)
                expected = dict(baseline)
                expected["RH#EVAL.BMP"] = ARTWORK.read_bytes()
                for name in ("RH#EVA.CRE", "RH#EV25.CRE", "RH#EVAMP.CRE"):
                    data = bytearray(baseline[name])
                    data[0x34:0x44] = b"rh#evaL\0" * 2
                    expected[name] = bytes(data)
                self.assertEqual(expected, after)
                result = game.run(weidu, "--force-uninstall-list", 225)
                self.assertEqual(0, result.returncode, game.transcript(result))
                self.assertEqual(baseline, file_tree(game.override))
                game.assert_stable_inputs(self)

    def test_missing_evandra_does_not_publish_artwork(self):
        weidu = find_weidu()
        if not weidu:
            self.skipTest("Set WEIDU_BIN to run the real installer")
        with tempfile.TemporaryDirectory(prefix="cbm-no-evandra-") as raw:
            class TempRoot:
                name = raw
            game = SyntheticSarahGame(TempRoot(), complete=True)
            baseline = file_tree(game.override)
            result = game.run(weidu, "--force-install-list", 225)
            self.assertIn("SKIPPING", game.transcript(result))
            self.assertEqual(baseline, file_tree(game.override))

    def test_malformed_second_template_rolls_back_first_template(self):
        weidu = find_weidu()
        if not weidu:
            self.skipTest("Set WEIDU_BIN to run the real installer")
        with tempfile.TemporaryDirectory(prefix="cbm-evandra-rollback-") as raw:
            class TempRoot:
                name = raw
            game = SyntheticSarahGame(TempRoot(), complete=True)
            (game.override / "rh#eva.cre").write_bytes(make_sarah_cre(1))
            (game.override / "rh#ev25.cre").write_bytes(b"CRE V1.0")
            baseline = file_tree(game.override)
            result = game.run(weidu, "--force-install-list", 225)
            self.assertIn("NOT INSTALLED DUE TO ERRORS", game.transcript(result))
            self.assertEqual(baseline, file_tree(game.override))

    def test_vampire_variant_is_optional(self):
        weidu = find_weidu()
        if not weidu:
            self.skipTest("Set WEIDU_BIN to run the real installer")
        with tempfile.TemporaryDirectory(prefix="cbm-evandra-no-vampire-") as raw:
            class TempRoot:
                name = raw
            game = SyntheticSarahGame(TempRoot(), complete=True)
            for name in ("rh#eva", "rh#ev25"):
                (game.override / f"{name}.cre").write_bytes(make_sarah_cre(1))
            baseline = file_tree(game.override)
            result = game.run(weidu, "--force-install-list", 225)
            self.assertIn("SUCCESSFULLY INSTALLED", game.transcript(result))
            self.assertFalse((game.override / "rh#evamp.cre").exists())
            result = game.run(weidu, "--force-uninstall-list", 225)
            self.assertEqual(0, result.returncode, game.transcript(result))
            self.assertEqual(baseline, file_tree(game.override))


if __name__ == "__main__":
    unittest.main()
