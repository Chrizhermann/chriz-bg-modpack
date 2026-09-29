"""Accept the new alpha.8 components using only runtime files from a release ZIP."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from lupa.lua51 import LuaRuntime

from tests import test_evandra_sorcerer as evandra
from tests import test_release_archive as release_archive
from tests import test_unidentified_items_installer as unidentified
from tests import test_utility_xp_installer as utility
from tests.test_evandra_portrait import ARTWORK_SHA256
from tests.test_story_utility_xp_installer import STORY_PUBLICATIONS


class NewComponentReleaseAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        configured = os.environ.get("CBM_RELEASE_ARCHIVE")
        if not configured:
            self.skipTest("set CBM_RELEASE_ARCHIVE to exercise a built release ZIP")
        self.archive = Path(configured).resolve()
        self.assertTrue(self.archive.is_file(), self.archive)

    @staticmethod
    def game_files(root: Path) -> dict[str, bytes]:
        return {
            name: payload for name, payload in utility._file_tree(root).items()
            if not utility._is_weidu_artifact(name)
        }

    def extract_release(self, game) -> dict[str, bytes]:
        # The shared extractor removes development TP2/runtime files first.
        # Fixtures retain only authored game data alongside the extracted ZIP.
        runtime = (game.root / utility.MOD_NAME).resolve()
        self.assertEqual(game.root.resolve(), runtime.parent)
        release_archive.ReleaseArchiveAcceptanceTests.extract_release(self, game.root)
        return self.game_files(game.root)

    def run_component(self, game, component: int, *, uninstall: bool = False) -> None:
        executable = release_archive.ReleaseArchiveAcceptanceTests.installer(self, game.root)
        result = subprocess.run(
            [
                executable, utility.SETUP_NAME,
                "--game", str(game.root),
                "--force-uninstall-list" if uninstall else "--force-install-list",
                str(component), "--language", "0", "--use-lang", "en_us",
                "--no-exit-pause", "--noautoupdate", "--no-auto-tp2", "--quick-log",
            ],
            cwd=game.root, capture_output=True, text=True, timeout=90, check=False,
        )
        transcript = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn(
            "SUCCESSFULLY REMOVED" if uninstall else "SUCCESSFULLY INSTALLED",
            transcript,
        )
        pattern = rf"(?m)#0\s+#{component}\b"
        if uninstall:
            self.assertNotRegex(game.active_log(), pattern)
        else:
            self.assertRegex(game.active_log(), pattern)

    def assert_restored(self, game, component: int, before: dict[str, bytes]) -> None:
        self.run_component(game, component, uninstall=True)
        self.assertEqual(before, self.game_files(game.root))

    def test_224_extracted_conversion_with_sr_and_without_sr(self) -> None:
        for sr in (False, True):
            with self.subTest(spell_revisions=sr), tempfile.TemporaryDirectory(
                prefix="cbm-release-evandra-build-"
            ) as raw:
                game, resolved = evandra.make_game(Path(raw), sr=sr, game_type="eet")
                before = self.extract_release(game)
                self.run_component(game, 224)
                after = self.game_files(game.root)
                expected = dict(before)
                for name in ("OVERRIDE/RH#EVA.CRE", "OVERRIDE/RH#EV25.CRE"):
                    evandra.assert_conversion(before[name], after[name], resolved)
                    expected[name] = after[name]
                self.assertEqual(expected, after)
                self.assert_restored(game, 224, before)

    def test_225_extracted_portrait_has_approved_hash_and_changes_only_portraits(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbm-release-evandra-portrait-") as raw:
            game = utility.SyntheticGame(Path(raw) / "game", game="eet", eeex=False)
            for index, name in enumerate(("rh#eva", "rh#ev25", "rh#evamp", "rh#evmes")):
                (game.override / f"{name}.cre").write_bytes(evandra.make_cre(variant=index))
            (game.override / "rh#eval.bmp").write_bytes(b"previous portrait\r\n\x00\xff")
            before = self.extract_release(game)
            artwork = (game.root / utility.MOD_NAME / "portraits/evandra/rh#eval.bmp").read_bytes()
            self.assertEqual(ARTWORK_SHA256, hashlib.sha256(artwork).hexdigest())
            self.run_component(game, 225)
            expected = dict(before)
            expected["OVERRIDE/RH#EVAL.BMP"] = artwork
            for name in ("RH#EVA", "RH#EV25", "RH#EVAMP"):
                key = f"OVERRIDE/{name}.CRE"
                creature = bytearray(before[key])
                creature[0x34:0x44] = b"rh#evaL\0" * 2
                expected[key] = bytes(creature)
            self.assertEqual(expected, self.game_files(game.root))
            self.assert_restored(game, 225, before)

    def test_611_extracted_runtime_preserves_xp_tables_and_previous_resources(self) -> None:
        for location in ("bif", "override"):
            with self.subTest(table_location=location), tempfile.TemporaryDirectory(
                prefix="cbm-release-story-xp-"
            ) as raw:
                game = utility.SyntheticGame(
                    Path(raw) / "game", game="eet", table_location=location,
                    missing_tables=("XPLEVEL.2DA",),
                )
                for name in STORY_PUBLICATIONS:
                    (game.override / name.lower()).write_bytes(
                        f"-- previous {name}\r\n".encode("ascii") + b"\x00\xff"
                    )
                before = self.extract_release(game)
                self.run_component(game, 611)
                expected = dict(before)
                for name in STORY_PUBLICATIONS:
                    expected[f"OVERRIDE/{name.upper()}"] = (
                        game.root / utility.MOD_NAME / "story-utility-xp" / name.lower()
                    ).read_bytes()
                # Full-tree equality protects the BIFF/KEY, an override XPBONUS,
                # every unrelated resource, and absence of an XPLEVEL dependency.
                self.assertEqual(expected, self.game_files(game.root))
                self.assert_restored(game, 611, before)

    def test_630_extracted_installer_updates_only_toy_loader_and_owned_resources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbm-release-unidentified-") as raw:
            temporary = Path(raw)
            # The fixture copies an installer but does not execute it while
            # constructing its toy game. Bootstrap from the ZIP if needed.
            fixture_weidu = unidentified.WEIDU_SOURCE
            if fixture_weidu is None:
                fixture_weidu = temporary / "fixture-weidu.exe"
                with zipfile.ZipFile(self.archive) as archive:
                    fixture_weidu.write_bytes(archive.read("setup-chriz-bg-modpack.exe"))
            with patch.object(unidentified, "WEIDU_SOURCE", fixture_weidu):
                game = unidentified.SyntheticGame(
                    temporary / "game", game="eet", preexisting_publications=True
                )
            before = self.extract_release(game)
            self.assertTrue(before["BALDUR.EXE"].startswith(b"synthetic Baldur.exe"))
            self.run_component(game, 630)
            after = self.game_files(game.root)
            allowed = {f"OVERRIDE/{name.upper()}" for name in unidentified.PUBLICATIONS}
            allowed.add("INFINITYLOADER.DB")
            self.assertEqual(set(before) | allowed, set(after))
            for name, payload in before.items():
                if name not in allowed:
                    self.assertEqual(payload, after[name], name)
            self.assertIn(unidentified.LOADER_DB, after["INFINITYLOADER.DB"])
            loader = after["INFINITYLOADER.DB"].decode("ascii")
            self.assertEqual(1, loader.count("[Foreign::Hook]"))
            source = game.root / utility.MOD_NAME / "unidentified-items"
            for row in unidentified._catalog_rows(source / "hooks.2da"):
                label = f"[CBMID::{row['ROW']}]"
                self.assertEqual(1, loader.count(label))
                section = loader.split(label, 1)[1].split("[", 1)[0]
                self.assertIn(f"Pattern={row['PATTERN']}", section)
                self.assertIn(f"Operations=ADD {row['CALL_OFFSET']}", section)
            for name in ("M_CBMID.lua", "CBMID.lua"):
                self.assertEqual(
                    (source / name.lower()).read_bytes(), after[f"OVERRIDE/{name.upper()}"]
                )
            self.assertNotEqual(before["OVERRIDE/CBMID.MRK"], after["OVERRIDE/CBMID.MRK"])
            lua = LuaRuntime()
            lua.execute(after["OVERRIDE/CBMIDCFG.LUA"].decode("ascii"))
            lua.execute(after["OVERRIDE/CBMID.LUA"].decode("utf-8"))
            self.assertGreater(lua.globals().CBMID.validate(lua.globals().CBMID_Config), 0)
            self.assert_restored(game, 630, before)

    def test_640_extracted_adapter_updates_util_before_legacy_ui_captures_t(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbm-release-legacy-ui-") as raw:
            game = utility.SyntheticGame(Path(raw) / "game", game="bg2ee", eeex=False)
            original_util = (
                b"-- synthetic current UI text provider\r\n"
                b"function getUiString(key) return 'translated:' .. key end\r\n"
            )
            legacy_loader = (
                b"local translate = t\r\n"
                b"legacy_ui_message = translate('UI_LABEL')\r\n"
            )
            (game.override / "util.lua").write_bytes(original_util)
            (game.override / "m_duiload.lua").write_bytes(legacy_loader)
            before = self.extract_release(game)
            self.run_component(game, 640)
            after = self.game_files(game.root)
            self.assertTrue(after["OVERRIDE/UTIL.LUA"].startswith(original_util))
            expected = dict(before)
            expected["OVERRIDE/UTIL.LUA"] = after["OVERRIDE/UTIL.LUA"]
            self.assertEqual(expected, after)
            lua = LuaRuntime()
            lua.execute(after["OVERRIDE/UTIL.LUA"].decode("utf-8"))
            lua.execute("assert(type(t) == 'function'); assert(t == getUiString)")
            lua.execute(after["OVERRIDE/M_DUILOAD.LUA"].decode("utf-8"))
            self.assertEqual("translated:UI_LABEL", lua.globals().legacy_ui_message)
            self.assert_restored(game, 640, before)


if __name__ == "__main__":
    unittest.main()
