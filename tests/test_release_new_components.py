"""Accept current components using only runtime files from a release ZIP."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from lupa.lua51 import LuaRuntime

from tests import test_evandra_sorcerer as evandra
from tests import test_baeloth_spellbook as baeloth
from tests import test_campaign_xp_package as campaign
from tests import test_companion_stats as stats
from tests import test_defensive_stance_ai as stance
from tests import test_degrodel_fight as degrodel
from tests import test_dorn_ambush_camera_fix as dorn
from tests import test_edwin_redwizard as edwin
from tests import test_eet_join_xp as join_xp
from tests import test_recruitment_xp as recruitment
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

    def run_installer(self, game, component: int, *, uninstall: bool = False) -> tuple[int, str]:
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
        return result.returncode, result.stdout + result.stderr

    def run_component(self, game, component: int, *, uninstall: bool = False) -> None:
        returncode, transcript = self.run_installer(game, component, uninstall=uninstall)
        self.assertEqual(0, returncode, transcript)
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

    def test_230_234_extracted_companion_stats_install_alone_and_together(self) -> None:
        for selection in (*((component,) for component in stats.STAT_COMPONENTS),
                          tuple(stats.STAT_COMPONENTS)):
            with self.subTest(components=selection), tempfile.TemporaryDirectory(
                prefix="cbm-release-stats-"
            ) as raw:
                game = stats.stage_game(Path(raw))
                before = self.extract_release(game)
                installer = release_archive.ReleaseArchiveAcceptanceTests.installer(self, game.root)
                result = stats.run_component(installer, game, selection)
                transcript = result.stdout + result.stderr
                self.assertEqual(0, result.returncode, transcript)
                self.assertEqual(len(selection), transcript.count("SUCCESSFULLY INSTALLED"))
                # The stat fixture has no log helper; utility's reads only game.root.
                log = utility.SyntheticGame.active_log(game)
                for component in selection:
                    self.assertRegex(log, rf"(?m)#0\s+#{component}\b")
                # Every game file outside the selected families keeps its bytes.
                self.assertEqual(
                    stats.expected_tree(before, selection, prefix="OVERRIDE/"),
                    self.game_files(game.root),
                )
                uninstall = stats.run_component(installer, game, selection, uninstall=True)
                transcript = uninstall.stdout + uninstall.stderr
                self.assertEqual(0, uninstall.returncode, transcript)
                self.assertIn("SUCCESSFULLY REMOVED", transcript)
                self.assertNotRegex(
                    utility.SyntheticGame.active_log(game), r"(?m)#0\s+#23[0-4]\b"
                )
                self.assertEqual(before, self.game_files(game.root))

    def test_235_extracted_baeloth_with_sr_and_without_sr(self) -> None:
        for sr in (False, True):
            with self.subTest(spell_revisions=sr), tempfile.TemporaryDirectory(
                prefix="cbm-release-baeloth-"
            ) as raw:
                game, spells = baeloth.make_game(Path(raw), sr=sr)
                game.before = self.extract_release(game)
                bundled = release_archive.ReleaseArchiveAcceptanceTests.installer(self, game.root)
                with patch.object(baeloth, "WEIDU", bundled):
                    baeloth.assert_success(game, spells, sr=sr)

    def test_236_extracted_edwin_slots_and_amulet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbm-release-edwin-") as raw:
            game = edwin.make_game(Path(raw), shuffled=True)
            game.before = self.extract_release(game)
            bundled = release_archive.ReleaseArchiveAcceptanceTests.installer(self, game.root)
            # Edwin shares the same invocation helper but reads all runtime
            # source from the extracted archive, never the development checkout.
            with patch.object(baeloth, "WEIDU", bundled):
                edwin.assert_success(game)

    def test_237_238_extracted_recruitment_xp_reads_the_shared_block_library(self) -> None:
        # 237/238 include the join-XP block reader they share with 239.
        for component in recruitment.COMPONENTS:
            with self.subTest(component=component), tempfile.TemporaryDirectory(
                prefix="cbm-release-recruitment-"
            ) as raw:
                game = recruitment.make_game(Path(raw), game_type="eet", sr=True, party_aliases=True)
                game.before = self.extract_release(game)
                bundled = release_archive.ReleaseArchiveAcceptanceTests.installer(self, game.root)
                with patch.object(recruitment, "WEIDU", bundled):
                    recruitment.assert_installed(game, component)
                    recruitment.assert_uninstalled(game, component)

    def test_239_extracted_eet_join_xp_with_sr_and_without_sr(self) -> None:
        for sr in (False, True):
            with self.subTest(spell_revisions=sr), tempfile.TemporaryDirectory(
                prefix="cbm-release-join-xp-"
            ) as raw:
                game = join_xp.make_game(Path(raw), sr=sr)
                game.before = self.extract_release(game)
                bundled = release_archive.ReleaseArchiveAcceptanceTests.installer(self, game.root)
                with patch.object(join_xp, "WEIDU", bundled):
                    join_xp.assert_installed(game)
                    join_xp.assert_uninstalled(game)

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


    def test_135_extracted_dorn_fix_unlocks_camera_and_restores_scripts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbm-release-dorn-") as raw:
            game = dorn.DornGame(Path(raw) / "game")
            before = self.extract_release(game)
            cut, senjack = before[dorn.CUT_KEY], before[dorn.SENJACK_KEY]
            self.run_component(game, 135)
            after = self.game_files(game.root)
            self.assertEqual({dorn.CUT_KEY, dorn.SENJACK_KEY},
                             {name for name in after if after[name] != before.get(name)})
            self.assertIsNone(dorn.LOCK_HEAD.search(after[dorn.CUT_KEY]))
            self.assertEqual(dorn.without_locks(cut), after[dorn.CUT_KEY])
            self.assertTrue(after[dorn.SENJACK_KEY].endswith(senjack.split(b"\n", 1)[1]))
            self.assertIn(b"CBM_DornAmbushUnlock", after[dorn.SENJACK_KEY])
            self.assert_restored(game, 135, before)

    def test_660_extracted_degrodel_choice_installs_and_restores_dialog(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbm-release-degrodel-") as raw:
            game = degrodel.make_game(
                Path(raw), degrodel.make_dialog(stalker="STALKE_", interjections=True))
            game.before = self.extract_release(game)
            bundled = release_archive.ReleaseArchiveAcceptanceTests.installer(self, game.root)
            with patch.object(degrodel, "WEIDU", bundled):
                degrodel.install(game)
                degrodel.assert_choice(game, handin_state=4)
                result, transcript = degrodel.run(game, uninstall=True)
            self.assertEqual(0, result.returncode, transcript)
            restored = self.game_files(game.root)
            # WeiDU keeps appended dialog.tlk strings; everything else is restored.
            restored.pop(degrodel.TLK_KEY)
            expected = dict(game.before)
            expected.pop(degrodel.TLK_KEY)
            self.assertEqual(expected, restored)

    def test_460_extracted_party_ai_gate_installs_and_restores(self) -> None:
        weidu = stance.find_weidu()
        if weidu is None:
            self.skipTest("set WEIDU_BIN to compile authored script fixtures")
        with tempfile.TemporaryDirectory(prefix="cbm-release-stance-") as raw:
            game = stance.stage_game(Path(raw), weidu)
            before = self.extract_release(game)
            self.run_component(game, 460)
            after = self.game_files(game.root)
            self.assertEqual(stance.expected_tree(game, before, prefix="OVERRIDE/"), after)
            self.assert_restored(game, 460, before)

    # 650/651/652: campaign XP banking and its two mutually exclusive cap modes.
    # Expected bytes come from the extracted ZIP, never the development checkout.
    def shipped_campaign_file(self, game, name: str) -> bytes:
        return (game.root / campaign.package.PACKAGE / name).read_bytes()

    def expected_bank(self, game, before: dict[str, bytes], config: str) -> dict[str, bytes]:
        expected = dict(before)
        for name in campaign.PUBLICATIONS:
            expected["OVERRIDE/" + name.upper()] = self.shipped_campaign_file(game, name)
        expected["OVERRIDE/CBMBKCFG.LUA"] = self.shipped_campaign_file(game, config)
        return expected

    def assert_campaign_runtime_shipped(self, game) -> None:
        # The bank loads these modules and DLLs from the mod folder at game start,
        # so every packaged file must be in the ZIP with its reviewed bytes.
        package_root = game.root / campaign.package.PACKAGE
        manifest = json.loads((package_root / "package-manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["files"])
        for name, entry in manifest["files"].items():
            path = package_root / name
            self.assertTrue(path.is_file(), f"release ZIP lacks {path}")
            self.assertEqual(entry["sha256"], hashlib.sha256(path.read_bytes()).hexdigest(), name)
        for name in campaign.PUBLICATIONS | {"cbmbksoa.lua", "cbmbkchp.lua"}:
            self.assertTrue((package_root / name).is_file(), f"release ZIP lacks {name}")

    def assert_skipped(self, game, component: int) -> None:
        files = self.game_files(game.root)
        returncode, transcript = self.run_installer(game, component)
        self.assertEqual(0, returncode, transcript)
        self.assertIn("SKIPPING:", transcript)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotRegex(game.active_log(), rf"(?m)#0\s+#{component}\b")
        self.assertEqual(files, self.game_files(game.root))

    def test_650_extracted_bank_publishes_its_runtime_and_restores_the_fixture(self) -> None:
        for prior in (False, True):
            with self.subTest(prior_publications=prior), tempfile.TemporaryDirectory(
                prefix="cbm-release-bank-"
            ) as raw:
                game = utility.SyntheticGame(Path(raw) / "game", game="eet")
                campaign.native_headers(game)
                if prior:
                    for name in campaign.PUBLICATIONS:
                        (game.override / name).write_bytes(b"foreign prior bytes\x00\xff\r\n")
                before = self.extract_release(game)
                self.assert_campaign_runtime_shipped(game)
                self.run_component(game, 650)
                self.assertEqual(
                    self.expected_bank(game, before, "cbmbkcfg.lua"), self.game_files(game.root)
                )
                self.assert_restored(game, 650, before)

    def test_651_extracted_soa_cap_installs_on_650_and_excludes_652(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbm-release-bank-soa-") as raw:
            game = utility.SyntheticGame(Path(raw) / "game", game="eet")
            campaign.native_headers(game)
            before = self.extract_release(game)
            self.assert_skipped(game, 651)  # requires 650
            self.run_component(game, 650)
            base = self.game_files(game.root)
            self.run_component(game, 651)
            soa = self.expected_bank(game, before, "cbmbksoa.lua")
            self.assertEqual(soa, self.game_files(game.root))
            self.assert_skipped(game, 652)  # mutually exclusive with 651
            self.assert_restored(game, 651, base)
            self.assert_restored(game, 650, before)

    def test_652_extracted_chapter_caps_gate_vanilla_bainvi_once_and_restore(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbm-release-chapter-caps-") as raw:
            game = campaign.chapter_game(Path(raw), campaign.BAINVI_VANILLA)
            before = self.extract_release(game)
            self.assert_skipped(game, 652)  # requires 650
            self.run_component(game, 650)
            base = self.game_files(game.root)
            self.run_component(game, 652)
            after = self.game_files(game.root)
            self.assertEqual(
                self.shipped_campaign_file(game, "cbmbkchp.lua"), after["OVERRIDE/CBMBKCFG.LUA"]
            )
            self.assertEqual({"OVERRIDE/BAINVI.BCS", "OVERRIDE/CBMBKCFG.LUA"},
                             {name for name in after if after[name] != base.get(name)})
            self.assertEqual(set(base), set(after))
            bundled = release_archive.ReleaseArchiveAcceptanceTests.installer(self, game.root)
            with patch.object(recruitment, "WEIDU", bundled):
                patched = recruitment.decompile_script(game, "BAINVI")
            self.assertEqual(1, patched.count(campaign.CHAPTER_GATE))
            self.assertIn('StartCutScene("CUTBA01")', patched)
            self.assertIn('Global("BA_START_SCENE","MYAREA",0)', patched)
            self.assert_skipped(game, 651)  # mutually exclusive with 652
            self.assert_restored(game, 652, base)
            self.assert_restored(game, 650, before)

    def test_652_extracted_unrecognised_bainvi_warns_unchanged_and_keeps_caps(self) -> None:
        for layout, bainvi in sorted(campaign.UNRECOGNISED_BAINVI.items()):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory(
                prefix="cbm-release-chapter-warn-"
            ) as raw:
                game = campaign.chapter_game(Path(raw), bainvi)
                before = self.extract_release(game)
                self.run_component(game, 650)
                base = self.game_files(game.root)
                returncode, transcript = self.run_installer(game, 652)
                # WeiDU exits with 3 after a component installed with warnings.
                self.assertEqual(3, returncode, transcript)
                self.assertIn("INSTALLED WITH WARNINGS", transcript)
                self.assertIn(campaign.NO_GATE_WARNING, transcript)
                self.assertIn(campaign.NO_GATE_REASONS[layout], transcript)
                self.assertRegex(game.active_log(), r"(?m)#0\s+#652\b")
                expected = dict(base)
                expected["OVERRIDE/CBMBKCFG.LUA"] = self.shipped_campaign_file(game, "cbmbkchp.lua")
                # Exact equality also proves BAINVI.BCS kept its bytes.
                self.assertEqual(expected, self.game_files(game.root))
                self.assertEqual(before["OVERRIDE/BAINVI.BCS"],
                                 (game.override / "bainvi.bcs").read_bytes())
                self.assert_restored(game, 652, base)
                self.assert_restored(game, 650, before)

if __name__ == "__main__":
    unittest.main()
