from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
TP2 = ROOT / "setup-chriz-bg-modpack.tp2"
TRA = ROOT / "chriz-bg-modpack/languages/english/setup.tra"
MANIFEST = ROOT / "release-manifest.json"
VERSION = ROOT / "VERSION"
README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"

PUBLIC_COMPONENTS = {
    110,
    130,
    140,
    160,
    170,
    188,
    189,
    190,
    192,
    193,
    194,
    195,
    196,
    197,
    198,
    199,
    220,
    221,
    222,
    223,
    400,
    410,
    430,
    440,
    450,
    610,
    620,
}


class PublicSurfaceTests(unittest.TestCase):
    def test_installer_exposes_only_implemented_alpha_components(self):
        source = TP2.read_text(encoding="utf-8")
        version = VERSION.read_text(encoding="utf-8").strip()
        declarations = [
            int(match.group(1))
            for match in re.finditer(
                r"(?m)^BEGIN\s+@(\d+)\s+DESIGNATED\s+\1\b", source
            )
        ]
        declared = set(declarations)
        self.assertEqual(len(declarations), len(declared), "Component IDs must be unique")
        self.assertEqual(PUBLIC_COMPONENTS, declared)
        self.assertNotRegex(source, r"(?im)^\s*FAIL\s+~Component\b")
        self.assertNotIn("cbm_sarah_portrait", source)
        self.assertNotIn("cbm_no_cat_and_mouse", source)
        self.assertRegex(source, rf"(?m)^VERSION\s+~{re.escape(version)}~$")

    def test_companion_ids_preserve_released_and_reserved_ownership(self):
        source = TP2.read_text(encoding="utf-8")
        labels = {
            int(component): label
            for component, label in re.findall(
                r"(?m)^BEGIN\s+@(\d+)\s+DESIGNATED\s+\1\b[^\n]*LABEL\s+~([^~]+)~", source
            )
        }
        expected = {
            188: "cbm_yeslick_alaghor",
            189: "cbm_safana_inventory",
            190: "cbm_sarah_archer",
            192: "cbm_viconia_cleric_thief",
            193: "cbm_sharteel_wizard_slayer",
            194: "cbm_kagain_dwarven_defender",
            195: "cbm_skie_swashbuckler",
            196: "cbm_faldorn_avenger",
            197: "cbm_dynaheir_haste",
            198: "cbm_kivan_archer",
            199: "cbm_companion_continuity",
            620: "cbm_imoen_spellhold_xp",
        }
        for component, label in expected.items():
            with self.subTest(component=component):
                self.assertEqual(label, labels.get(component))
        self.assertNotIn(191, labels, "191 remains reserved for the private Sarah portrait")

    def test_translation_catalog_matches_the_public_component_set(self):
        source = TRA.read_text(encoding="utf-8")
        component_strings = {
            int(match.group(1))
            for match in re.finditer(r"(?m)^@(\d+)\s*=", source)
            if int(match.group(1)) < 1000
        }
        self.assertEqual(PUBLIC_COMPONENTS, component_strings)
        self.assertNotRegex(source, r"(?im)portrait|not yet|TBD")

    def test_release_manifest_is_complete_and_excludes_private_material(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        version = VERSION.read_text(encoding="utf-8").strip()
        self.assertEqual(version, manifest["version"])
        self.assertEqual(f"chriz-bg-modpack-{version}", manifest["archive_basename"])
        self.assertIn(f"**Release:** `{version}`", README.read_text(encoding="utf-8"))
        self.assertIn(f"## {version}", CHANGELOG.read_text(encoding="utf-8"))
        files = set(manifest["files"])
        runtime = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "chriz-bg-modpack").rglob("*")
            if path.is_file()
        }
        self.assertEqual(runtime, {path for path in files if path.startswith("chriz-bg-modpack/")})
        for required in (
            "README.md",
            "CHANGELOG.md",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "setup-chriz-bg-modpack.tp2",
            "docs/utility-xp.md",
            "docs/companion-classes.md",
            "docs/companion-continuity.md",
            "docs/imoen-spellhold-xp.md",
            "docs/npc-builds.md",
            "docs/yeslick-alaghor.md",
        ):
            self.assertIn(required, files)
        forbidden_fragments = (
            "extras/",
            "portraits/",
            "snapshot",
            "save",
            "handover",
            "tests/",
        )
        for path in files:
            with self.subTest(path=path):
                self.assertFalse(any(fragment in path.lower() for fragment in forbidden_fragments))
        self.assertEqual(
            {
                "docs/utility-xp.md",
                "docs/companion-classes.md",
                "docs/companion-continuity.md",
                "docs/imoen-spellhold-xp.md",
                "docs/npc-builds.md",
                "docs/yeslick-alaghor.md",
            },
            {path for path in files if path.startswith("docs/")},
            "Only the public component user guides belong in release docs",
        )


if __name__ == "__main__":
    unittest.main()
