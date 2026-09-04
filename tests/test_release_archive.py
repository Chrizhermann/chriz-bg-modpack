from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from tests.test_sarah_options import (
    EXPECTED_PROFICIENCIES,
    SyntheticSarahGame,
    file_tree,
    proficiency_map,
    u32,
)


class ReleaseArchiveAcceptanceTests(unittest.TestCase):
    def test_extracted_release_installs_and_uninstalls_in_synthetic_game(self):
        configured = os.environ.get("CBM_RELEASE_ARCHIVE")
        if not configured:
            self.skipTest("set CBM_RELEASE_ARCHIVE to exercise a built release ZIP")
        release_archive = Path(configured).resolve()
        self.assertTrue(release_archive.is_file(), release_archive)

        with tempfile.TemporaryDirectory(prefix="cbm-release-acceptance-") as raw:
            temporary = tempfile.TemporaryDirectory(dir=raw)
            try:
                game = SyntheticSarahGame(temporary, complete=True)

                # The synthetic fixture initially copies development sources. Remove
                # them so installation can use only files extracted from the ZIP.
                (game.root / "setup-chriz-bg-modpack.tp2").unlink()
                shutil.rmtree(game.root / "chriz-bg-modpack")
                with zipfile.ZipFile(release_archive) as archive:
                    names = archive.namelist()
                    self.assertIn("setup-chriz-bg-modpack.exe", names)
                    self.assertIn("setup-chriz-bg-modpack.tp2", names)
                    self.assertIn("WEIDU-COPYING.txt", names)
                    lowered = "\n".join(names).lower()
                    for excluded in (
                        "sarah-custom",
                        "cbm_sarah_portrait",
                        "cbm_no_cat_and_mouse",
                        "cbm_cm_",
                        ".gitkeep",
                        "extras/",
                    ):
                        self.assertNotIn(excluded, lowered)
                    archive.extractall(game.root)

                weidu = os.environ.get("WEIDU_BIN")
                if os.environ.get("CBM_USE_BUNDLED_WEIDU") == "1":
                    weidu = str(game.root / "setup-chriz-bg-modpack.exe")
                if not weidu:
                    if os.name != "nt":
                        self.skipTest("set WEIDU_BIN on non-Windows hosts")
                    weidu = str(game.root / "setup-chriz-bg-modpack.exe")

                install = game.run(weidu, "--force-install-list", 190)
                transcript = game.transcript(install)
                self.assertEqual(0, install.returncode, transcript)
                self.assertIn("SUCCESSFULLY INSTALLED", transcript)
                for filename in ("K#SARAH.CRE", "K#SARAH1.CRE"):
                    transformed = (game.override / filename).read_bytes()
                    self.assertEqual(0x40070000, u32(transformed, 0x244))
                    self.assertEqual(EXPECTED_PROFICIENCIES, proficiency_map(transformed))

                uninstall = game.run(weidu, "--force-uninstall-list", 190)
                transcript = game.transcript(uninstall)
                self.assertEqual(0, uninstall.returncode, transcript)
                self.assertIn("SUCCESSFULLY REMOVED", transcript)
                self.assertEqual(game.initial_override, file_tree(game.override))
                game.assert_stable_inputs(self)
            finally:
                temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
