from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tests import test_utility_xp_installer as utility_installer
from tests import test_companion_classes_installer as companion_installer
from tests.test_sarah_options import (
    EXPECTED_PROFICIENCIES,
    SyntheticSarahGame,
    file_tree,
    proficiency_map,
    u32,
)


class ReleaseArchiveAcceptanceTests(unittest.TestCase):
    def extract_release(self, game_root: Path) -> dict[str, bytes]:
        configured = os.environ.get("CBM_RELEASE_ARCHIVE")
        if not configured:
            self.skipTest("set CBM_RELEASE_ARCHIVE to exercise a built release ZIP")
        release_archive = Path(configured).resolve()
        self.assertTrue(release_archive.is_file(), release_archive)

        # Each fixture initially copies development sources. Remove those so
        # installation can use only the source shipped in the release ZIP.
        (game_root / "setup-chriz-bg-modpack.tp2").unlink()
        shutil.rmtree(game_root / "chriz-bg-modpack")
        with zipfile.ZipFile(release_archive) as archive:
            names = archive.namelist()
            self.assertIn("setup-chriz-bg-modpack.exe", names)
            self.assertIn("setup-chriz-bg-modpack.tp2", names)
            self.assertIn("WEIDU-COPYING.txt", names)
            self.assertIn("docs/utility-xp.md", names)
            self.assertIn("docs/companion-classes.md", names)
            self.assertIn("chriz-bg-modpack/lib/cbm_companion_classes.tpa", names)
            lowered = "\n".join(names).lower()
            for excluded in (
                "sarah-custom",
                "cbm_sarah_portrait",
                "cbm_no_cat_and_mouse",
                "cbm_cm_",
                "cbm_imoen_spellhold_xp",
                ".gitkeep",
                "extras/",
            ):
                self.assertNotIn(excluded, lowered)
            payloads = {
                name: archive.read("chriz-bg-modpack/utility-xp/" + name.lower())
                for name in utility_installer.PUBLICATIONS
            }
            archive.extractall(game_root)
        return payloads

    def installer(self, game_root: Path) -> str:
        if os.environ.get("CBM_USE_BUNDLED_WEIDU") == "1":
            return str(game_root / "setup-chriz-bg-modpack.exe")
        configured = os.environ.get("WEIDU_BIN") or os.environ.get("WEIDU")
        if configured:
            return configured
        if os.name != "nt":
            self.skipTest("set WEIDU_BIN on non-Windows hosts")
        return str(game_root / "setup-chriz-bg-modpack.exe")

    def test_extracted_release_installs_and_uninstalls_in_synthetic_game(self):
        with tempfile.TemporaryDirectory(prefix="cbm-release-acceptance-") as raw:
            temporary = tempfile.TemporaryDirectory(dir=raw)
            try:
                game = SyntheticSarahGame(temporary, complete=True)
                self.extract_release(game.root)
                weidu = self.installer(game.root)

                install = game.run(weidu, "--force-install-list", 190)
                transcript = game.transcript(install)
                self.assertEqual(0, install.returncode, transcript)
                self.assertIn("SUCCESSFULLY INSTALLED", transcript)
                for filename in ("K#SARAH.CRE", "K#SARAH1.CRE"):
                    transformed = (game.override / filename.lower()).read_bytes()
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

    def test_extracted_release_installs_and_restores_all_utility_xp_resources(self):
        with tempfile.TemporaryDirectory(prefix="cbm-utility-release-") as raw:
            game = utility_installer.SyntheticGame(
                Path(raw) / "game", game="eet", existing_publications=True
            )
            payloads = self.extract_release(game.root)
            weidu = self.installer(game.root)
            executable = Path(shutil.which(weidu) or weidu).resolve()
            self.assertTrue(executable.is_file(), executable)

            def game_files() -> dict[str, bytes]:
                return {
                    name: data
                    for name, data in utility_installer._file_tree(game.root).items()
                    if not utility_installer._is_weidu_artifact(name)
                }

            before = game_files()
            with patch.object(utility_installer, "WEIDU", executable):
                install = game.run()
                transcript = install.stdout + install.stderr
                self.assertEqual(0, install.returncode, transcript)
                self.assertIn("SUCCESSFULLY INSTALLED", transcript)
                self.assertRegex(game.active_log(), r"(?m)#0\s+#610\b")
                expected = dict(before)
                for name, payload in payloads.items():
                    expected["OVERRIDE/" + name.upper()] = payload
                self.assertEqual(expected, game_files())

                uninstall = game.run(uninstall=True)
                transcript = uninstall.stdout + uninstall.stderr
                self.assertEqual(0, uninstall.returncode, transcript)
                self.assertIn("SUCCESSFULLY REMOVED", transcript)
                self.assertNotRegex(game.active_log(), r"(?m)#0\s+#610\b")
                self.assertEqual(before, game_files())
                self.assertEqual(
                    game.override_before, utility_installer._file_tree(game.override)
                )

    def test_extracted_release_installs_and_restores_all_companion_choices(self):
        if not os.environ.get("CBM_RELEASE_ARCHIVE"):
            self.skipTest("set CBM_RELEASE_ARCHIVE to exercise a built release ZIP")
        if companion_installer.WEIDU is None:
            self.skipTest("set WEIDU_BIN to compile authored script fixtures")
        for component, kit, class_id in companion_installer.CHOICES:
            with self.subTest(component=component):
                with tempfile.TemporaryDirectory(prefix="cbm-companion-release-") as raw:
                    temporary = Path(raw)
                    game = companion_installer._make_game(temporary, game_type="eet")
                    self.extract_release(game.root)
                    weidu = self.installer(game.root)
                    executable = Path(shutil.which(weidu) or weidu).resolve()
                    self.assertTrue(executable.is_file(), executable)
                    # Include the extracted payload in rollback/scope checks.
                    game.before = utility_installer._file_tree(game.root)
                    with patch.object(companion_installer, "WEIDU", executable):
                        install, transcript = companion_installer._run(game, component)
                        self.assertEqual(0, install.returncode, transcript)
                        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
                        companion_installer._assert_installed_choice(
                            game, temporary, component, kit, class_id
                        )
                        uninstall, transcript = companion_installer._run(
                            game, component, uninstall=True
                        )
                        self.assertEqual(0, uninstall.returncode, transcript)
                        self.assertIn("SUCCESSFULLY REMOVED", transcript)
                        self.assertNotIn(f"#{component} ", game.active_log())
                        companion_installer._assert_restored(game)


if __name__ == "__main__":
    unittest.main()
