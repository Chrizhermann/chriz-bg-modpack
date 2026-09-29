"""Exercise story-stage utility XP with real WeiDU and disposable fake games."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.test_utility_xp_installer import (
    MOD_NAME,
    PUBLICATIONS as PROGRESSIVE_PUBLICATIONS,
    SETUP_NAME,
    WEIDU,
    SyntheticGame,
    _file_tree,
    _is_weidu_artifact,
)


STORY_COMPONENT = 611
PROGRESSIVE_COMPONENT = 610
STORY_PUBLICATIONS = (
    "M_CBMSXP.lua",
    "CBMSXP.lua",
    "CBMSXRT.lua",
    "CBMSXP.menu",
)
COMPONENT_FILES = {
    PROGRESSIVE_COMPONENT: ("utility-xp", PROGRESSIVE_PUBLICATIONS),
    STORY_COMPONENT: ("story-utility-xp", STORY_PUBLICATIONS),
}


@unittest.skipUnless(WEIDU, "WeiDU unavailable; set WEIDU or WEIDU_BIN")
class StoryUtilityXPInstallerTests(unittest.TestCase):
    def make_game(
        self, *, existing_story_publications: bool = False, **kwargs: object
    ) -> SyntheticGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbm-story-xp-installer-")
        self.addCleanup(temporary.cleanup)
        kwargs.setdefault("game", "eet")
        game = SyntheticGame(Path(temporary.name) / "game", **kwargs)
        if existing_story_publications:
            for name in STORY_PUBLICATIONS:
                (game.override / name.lower()).write_bytes(
                    f"-- pre-existing {name}; preserve 125% and CRLF\r\n".encode("ascii")
                    + b"\x00\xff"
                )
        game.before = _file_tree(game.root)
        game.override_before = _file_tree(game.override)
        return game

    def run_component(
        self, game: SyntheticGame, component: int, *, uninstall: bool = False
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(WEIDU),
                SETUP_NAME,
                "--no-auto-tp2",
                "--game", str(game.root),
                "--force-uninstall-list" if uninstall else "--force-install-list",
                str(component),
                "--language", "0",
                "--use-lang", "en_us",
                "--no-exit-pause",
                "--noautoupdate",
                "--quick-log",
            ],
            cwd=game.root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def assert_game_files(
        self, game: SyntheticGame, installed: tuple[int, ...] = ()
    ) -> None:
        expected = dict(game.before)
        for component in installed:
            directory, publications = COMPONENT_FILES[component]
            for name in publications:
                expected[f"OVERRIDE/{name.upper()}"] = (
                    game.root / MOD_NAME / directory / name.lower()
                ).read_bytes()
        actual = {
            name: payload
            for name, payload in _file_tree(game.root).items()
            if not _is_weidu_artifact(name)
        }
        self.assertEqual(set(expected), set(actual), "installer wrote outside its allowlist")
        for name, payload in expected.items():
            self.assertEqual(payload, actual[name], f"unexpected bytes in {name}")
        # This also checks BIFF/KEY/TLK bytes and whether XPBONUS was materialized.
        # Nothing outside the explicitly selected runtime publications may change.
        for component in COMPONENT_FILES:
            pattern = rf"(?m)#0\s+#{component}\b"
            if component in installed:
                self.assertRegex(game.active_log(), pattern)
            else:
                self.assertNotRegex(game.active_log(), pattern)

    def assert_installed(self, game: SyntheticGame, component: int = STORY_COMPONENT) -> None:
        result = self.run_component(game, component)
        transcript = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assert_game_files(game, (component,))

    def assert_uninstalled(self, game: SyntheticGame, component: int = STORY_COMPONENT) -> None:
        result = self.run_component(game, component, uninstall=True)
        transcript = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY REMOVED", transcript)
        self.assert_game_files(game)
        self.assertEqual(game.override_before, _file_tree(game.override))

    def assert_skipped(
        self,
        game: SyntheticGame,
        reason: str,
        *,
        component: int = STORY_COMPONENT,
        installed: tuple[int, ...] = (),
    ) -> None:
        result = self.run_component(game, component)
        transcript = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SKIPPING:", transcript)
        self.assertRegex(transcript, reason)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotIn("NOT INSTALLED DUE TO ERRORS", transcript)
        self.assert_game_files(game, installed)

    def test_eet_installs_and_uninstalls_with_biff_or_override_xpbonus_unchanged(self) -> None:
        for location in ("bif", "override"):
            with self.subTest(table_location=location):
                game = self.make_game(table_location=location)
                self.assert_installed(game)
                self.assert_uninstalled(game)

    def test_uninstall_restores_each_preexisting_story_resource_byte_exactly(self) -> None:
        game = self.make_game(existing_story_publications=True)
        self.assert_installed(game)
        self.assert_uninstalled(game)

    def test_story_xp_does_not_require_xplevel(self) -> None:
        game = self.make_game(missing_tables=("XPLEVEL.2DA",))
        self.assert_installed(game)
        self.assert_uninstalled(game)

    def test_non_eet_games_are_skipped_without_changes(self) -> None:
        for game_type in ("bg2ee", "bgee"):
            with self.subTest(game=game_type):
                self.assert_skipped(self.make_game(game=game_type), r"(?i)EET")

    def test_missing_runtime_dependencies_are_skipped_without_changes(self) -> None:
        cases = (
            ({"eeex": False}, r"(?i)EEex"),
            ({"missing_tables": ("XPBONUS.2DA",)}, r"(?i)XPBONUS"),
        )
        for options, reason in cases:
            with self.subTest(options=options):
                self.assert_skipped(self.make_game(**options), reason)

    def test_conflicts_preserve_the_installed_choice_and_uninstall_allows_switching(self) -> None:
        for first, second in (
            (PROGRESSIVE_COMPONENT, STORY_COMPONENT),
            (STORY_COMPONENT, PROGRESSIVE_COMPONENT),
        ):
            with self.subTest(first=first, second=second):
                game = self.make_game(
                    existing_story_publications=True, existing_publications=True
                )
                self.assert_installed(game, first)
                first_log = game.active_log()
                self.assert_skipped(
                    game,
                    rf"(?i)\b{first}\b",
                    component=second,
                    installed=(first,),
                )
                self.assertEqual(first_log, game.active_log())
                self.assert_uninstalled(game, first)
                self.assert_installed(game, second)
                self.assert_uninstalled(game, second)


if __name__ == "__main__":
    unittest.main()
