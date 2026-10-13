"""Installer tests for the optional companion stat components 230-234."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

from tests.test_collection_defaults import (
    ROOT,
    TP2,
    SyntheticGame,
    component_block,
    file_tree,
    find_weidu,
    make_cre,
    resource_path,
)


LIBRARY = ROOT / "chriz-bg-modpack/lib/cbm_companion_stats.tpa"
GUIDE = ROOT / "docs/companion-stats.md"

# Publicly selectable stat allocations. All other bytes belong to the existing
# creature, including class/kit conversions and any previous mod's adjustments.
STAT_COMPONENTS = {
    230: (
        ("RASAAD", "RASAAD2", "RASAAD4", "RASAAD6", "RASAAD7", "RASAAD8",
         "RASAAD9", "RASAAD10", "RASAAD11", "RASAAD12", "RASAAD13"),
        {0x23C: 17, 0x23D: 16},
    ),
    231: (
        ("DORN", "DORN2", "DORN4", "DORN6", "DORN7", "DORN8", "DORN9",
         "DORN10", "DORN12", "DORN14"),
        {0x23D: 16},
    ),
    232: (
        ("ELDOTH", "ELDOTH5", "ELDOTD"),
        {0x238: 17, 0x239: 0, 0x23A: 14, 0x23B: 9, 0x23D: 16},
    ),
    233: (
        ("GARRIC", "GARRIC2", "GARRIC4", "GARRIC6", "BDGARRIC", "GARRICK"),
        {0x23C: 17, 0x23A: 15},
    ),
    234: (
        ("QUAYLE", "QUAYLE_", "QUAYLE4", "QUAYLE6", "QUAYLEM"),
        {0x23D: 15},
    ),
}
PRESETS = {
    230: ("RASAAD", "cbm_rasaad_stats"),
    231: ("DORN", "cbm_dorn_stats"),
    232: ("ELDOTH", "cbm_eldoth_stats"),
    233: ("GARRICK", "cbm_garrick_stats"),
    234: ("QUAYLE", "cbm_quayle_stats"),
}
# Separate actors that resemble companions (the Black Pits II arena opponents)
# plus an unrelated creature. No stat component may change them.
UNRELATED = ("CBMOTHER", "OHB1RASD", "OHB2DORN")
CRE_TYPE = 1009
ARE_TYPE = 1010


def source_cre(index: int) -> bytes:
    """Valid CRE layout with deliberately noncanonical companion gameplay data."""
    creature = bytearray(
        make_cre(
            class_id=(index * 17) % 256,
            kit=0x5ABC0000 + index,
            dv=f"MODDED_ALIAS_{index}",
            seed=index + 1,
            xp=(0, 161_000, 8_000_000, 16_777_215)[index % 4],
        )
    )
    hp, max_hp = ((0, 53), (1, 120), (36, 36), (255, 320))[index % 4]
    struct.pack_into("<HH", creature, 0x24, hp, max_hp)
    creature[0x234:0x237] = bytes(
        ((0, 1, 9), (5, 9, 4), (30, 25, 28))[index % 3]
    )
    incoming_stats = (0, 1, 9, 18, 25)
    for offset in range(0x238, 0x23F):
        creature[offset] = incoming_stats[(index + offset) % len(incoming_stats)]
    creature[0x239] = 99  # Preserve exceptional STR except when assigning STR 17.
    return bytes(creature)


def apply_allocation(creature: bytes, component: int) -> bytes:
    patched = bytearray(creature)
    for offset, value in STAT_COMPONENTS[component][1].items():
        patched[offset] = value
    return bytes(patched)


def components_of(components: int | Iterable[int]) -> tuple[int, ...]:
    return (components,) if isinstance(components, int) else tuple(components)


def expected_tree(
    before: dict[str, bytes], components: int | Iterable[int], *, prefix: str = ""
) -> dict[str, bytes]:
    """Apply only the selected allocations to the selected, present families."""
    expected = dict(before)
    for component in components_of(components):
        for resref in STAT_COMPONENTS[component][0]:
            name = f"{prefix}{resref}.CRE"
            if name in expected:
                expected[name] = apply_allocation(expected[name], component)
    return expected


def stage_game(root: Path) -> SyntheticGame:
    """A disposable game holding every listed variant plus unrelated actors."""
    game = SyntheticGame(root / "game")
    shutil.copy2(TP2, game.root / TP2.name)
    shutil.copytree(ROOT / "chriz-bg-modpack", game.root / "chriz-bg-modpack")
    # Stat assignment has no dependency on class, kit, or spell symbols.
    for path in game.override.iterdir():
        path.unlink()
    index = 0
    for resources, _ in STAT_COMPONENTS.values():
        for resref in resources:
            resource_path(game.override, f"{resref}.CRE").write_bytes(source_cre(index))
            index += 1
    for resref in UNRELATED:
        resource_path(game.override, f"{resref}.CRE").write_bytes(source_cre(index))
        index += 1
    return game


def run_component(
    weidu: str,
    game: SyntheticGame,
    components: int | Iterable[int],
    *,
    uninstall: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            weidu,
            TP2.name,
            "--no-auto-tp2",
            "--game", str(game.root),
            "--force-uninstall-list" if uninstall else "--force-install-list",
            *(str(component) for component in components_of(components)),
            "--language", "0",
            "--use-lang", "en_us",
            "--no-exit-pause",
            "--noautoupdate",
            "--quick-log",
        ],
        cwd=game.root,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def write_key_and_bif(game: SyntheticGame, resources: list[tuple[str, int, bytes]]) -> Path:
    """Replace the synthetic KEY with one that also indexes BIFF creatures.

    Lowercase BIFF paths keep the payload readable by WeiDU on case-sensitive
    hosts, where it looks up game files in lowercase.
    """
    bif = game.root / "data" / "cbmstats.bif"
    bif.parent.mkdir(exist_ok=True)
    entries = [("OH6000", ARE_TYPE, b"synthetic BG2EE marker"), *resources]
    table_offset = 0x14
    payload_offset = table_offset + len(entries) * 0x10
    table = bytearray()
    payloads = bytearray()
    for index, (_, resource_type, payload) in enumerate(entries):
        table.extend(struct.pack(
            "<IIIHH", index, payload_offset + len(payloads), len(payload), resource_type, 0
        ))
        payloads.extend(payload)
    bif.write_bytes(
        struct.pack("<4s4sIII", b"BIFF", b"V1  ", len(entries), 0, table_offset)
        + table + payloads
    )
    encoded_name = b"data\\cbmstats.bif\0"
    bif_table_offset = 0x18
    resource_table_offset = bif_table_offset + 0x0C
    names_offset = resource_table_offset + len(entries) * 0x0E
    key = bytearray(struct.pack(
        "<4s4sIIII", b"KEY ", b"V1  ", 1, len(entries),
        bif_table_offset, resource_table_offset,
    ))
    key.extend(struct.pack(
        "<IIHH", bif.stat().st_size, names_offset, len(encoded_name), 0
    ))
    for index, (resref, resource_type, _) in enumerate(entries):
        key.extend(struct.pack(
            "<8sHI", resref.encode("ascii").ljust(8, b"\0"), resource_type, index
        ))
    key.extend(encoded_name)
    (game.root / "chitin.key").write_bytes(key)
    return bif


class CompanionStatSourceTests(unittest.TestCase):
    def test_components_declare_only_the_shared_preset_without_prerequisites(self):
        source = TP2.read_text(encoding="utf-8")
        for component, (npc, label) in PRESETS.items():
            with self.subTest(component=component):
                block = component_block(source, component)
                self.assertIn(f"GROUP @1100 LABEL ~{label}~", block)
                self.assertIn("INCLUDE ~chriz-bg-modpack/lib/cbm_companion_stats.tpa~", block)
                self.assertIn(f"LAF cbm_companion_stats STR_VAR npc = ~{npc}~ END", block)
                # Class, kit, game, spell or other mod choices never gate a stat choice.
                self.assertNotRegex(block, r"(?i)\b(REQUIRE_\w+|FORBID_\w+|SUBCOMPONENT)\b")

    def test_library_and_guide_cover_the_same_named_variants(self):
        library = LIBRARY.read_text(encoding="utf-8")
        declared: dict[str, tuple[str, ...]] = {}
        for npc, names in re.findall(
            r"STRING_EQUAL ~(\w+)~\) BEGIN\s+ACTION_DEFINE_ARRAY cbmst_resources BEGIN\s+([A-Z0-9_\s]+?)\s+END\b",
            library,
        ):
            declared[npc] = tuple(names.split())
        guide = GUIDE.read_text(encoding="utf-8")
        for component, (npc, _) in PRESETS.items():
            with self.subTest(component=component):
                self.assertEqual(STAT_COMPONENTS[component][0], declared.get(npc))
                for resref in STAT_COMPONENTS[component][0]:
                    self.assertIn(f"`{resref}`", guide)


class CompanionStatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.weidu = find_weidu()
        if cls.weidu is None:
            raise unittest.SkipTest("WeiDU 249+ not available; set WEIDU_BIN")

    @contextmanager
    def staged_game(self):
        with tempfile.TemporaryDirectory(prefix="cbm-companion-stats-") as raw:
            yield stage_game(Path(raw))

    def run_component(
        self, game: SyntheticGame, components: int | Iterable[int], *, uninstall: bool = False
    ) -> subprocess.CompletedProcess[str]:
        return run_component(self.weidu, game, components, uninstall=uninstall)

    def assert_success(self, result: subprocess.CompletedProcess[str]) -> str:
        transcript = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotIn("NOT INSTALLED DUE TO ERRORS", transcript)
        self.assertNotIn("ERROR locating resource", transcript)
        return transcript

    def assert_uninstall_restores(
        self,
        game: SyntheticGame,
        components: int | Iterable[int],
        before: dict[str, bytes],
    ) -> None:
        uninstall = self.run_component(game, components, uninstall=True)
        transcript = uninstall.stdout + uninstall.stderr
        self.assertEqual(0, uninstall.returncode, transcript)
        self.assertIn("SUCCESSFULLY REMOVED", transcript)
        self.assertEqual(before, file_tree(game.override))

    def test_each_component_owns_only_its_stats_and_is_stable_on_normalized_input(self):
        for component, (resources, _) in STAT_COMPONENTS.items():
            with self.subTest(component=component), self.staged_game() as game:
                before = file_tree(game.override)
                expected = expected_tree(before, component)
                transcript = self.assert_success(self.run_component(game, component))
                self.assertIn(
                    f"processed {len(resources)} present creature variant(s)", transcript
                )
                self.assertNotIn("WARNING: cbm_companion_stats", transcript)
                # Full-file and full-tree equality protects HP, daily casts,
                # effects, all unselected stats, and every other companion.
                self.assertEqual(expected, file_tree(game.override))
                self.assert_uninstall_restores(game, component, before)

                # Apply again to already-normalized creatures in an uninstalled
                # game, so this exercises the patch rather than WeiDU's skip path.
                for filename, content in expected.items():
                    resource_path(game.override, filename).write_bytes(content)
                self.assert_success(self.run_component(game, component))
                self.assertEqual(expected, file_tree(game.override))
                self.assert_uninstall_restores(game, component, expected)

    def test_all_components_selected_together_keep_their_own_allocations(self):
        # One WeiDU run must not leak a previous component's scores or variant
        # list into the next; uninstalling all of them restores every byte.
        with self.staged_game() as game:
            before = file_tree(game.override)
            selected = tuple(STAT_COMPONENTS)
            transcript = self.assert_success(self.run_component(game, selected))
            self.assertEqual(len(selected), transcript.count("SUCCESSFULLY INSTALLED"))
            self.assertEqual(expected_tree(before, selected), file_tree(game.override))
            for resref in UNRELATED:
                name = f"{resref}.CRE"
                self.assertEqual(before[name], file_tree(game.override)[name])
            self.assert_uninstall_restores(game, selected, before)

    def test_biff_variants_are_patched_where_effective_and_restored_exactly(self):
        for component, (resources, allocation) in STAT_COMPONENTS.items():
            with self.subTest(component=component), self.staged_game() as game:
                biff_only, shadowed, already_set = resources[:3]
                stock = {
                    biff_only: source_cre(900 + component),
                    shadowed: source_cre(950 + component),
                    already_set: apply_allocation(source_cre(990 + component), component),
                }
                # BIFF-only variants exist solely in the KEY; the shadowed one
                # keeps its (different) staged override copy as effective data.
                for resref in (biff_only, already_set):
                    resource_path(game.override, f"{resref}.CRE").unlink()
                bif = write_key_and_bif(
                    game, [(resref, CRE_TYPE, payload) for resref, payload in stock.items()]
                )
                key = (game.root / "chitin.key").read_bytes()
                biff = bif.read_bytes()
                before = file_tree(game.override)

                self.assert_success(self.run_component(game, component))
                expected = expected_tree(before, component)
                # Changed BIFF data is materialized; already-correct data is not.
                expected[f"{biff_only}.CRE"] = apply_allocation(stock[biff_only], component)
                self.assertEqual(expected, file_tree(game.override))
                self.assertNotIn(f"{already_set}.CRE", file_tree(game.override))
                self.assertEqual(
                    apply_allocation(before[f"{shadowed}.CRE"], component),
                    file_tree(game.override)[f"{shadowed}.CRE"],
                )
                self.assertEqual(key, (game.root / "chitin.key").read_bytes())
                self.assertEqual(biff, bif.read_bytes())
                self.assert_uninstall_restores(game, component, before)
                self.assertEqual(key, (game.root / "chitin.key").read_bytes())
                self.assertEqual(biff, bif.read_bytes())

    def test_each_component_patches_a_late_variant_when_earlier_variants_are_absent(self):
        for component, (resources, _) in STAT_COMPONENTS.items():
            with self.subTest(component=component), self.staged_game() as game:
                for resref in resources[:-1]:
                    resource_path(game.override, f"{resref}.CRE").unlink()
                before = file_tree(game.override)
                transcript = self.assert_success(self.run_component(game, component))
                self.assertEqual(expected_tree(before, component), file_tree(game.override))
                self.assertIn("processed 1 present creature variant(s)", transcript)
                for resref in resources[:-1]:
                    self.assertRegex(
                        transcript,
                        rf"(?im)^.*WARNING.*{re.escape(resref)}\.CRE.*missing.*$",
                    )
                self.assertRegex(transcript, r"(?i)renamed variants may remain unpatched")
                self.assert_uninstall_restores(game, component, before)

    def test_absent_family_is_a_reported_noop_without_symbol_dependencies(self):
        for component, (resources, _) in STAT_COMPONENTS.items():
            with self.subTest(component=component), self.staged_game() as game:
                for resref in resources:
                    resource_path(game.override, f"{resref}.CRE").unlink()
                before = file_tree(game.override)
                transcript = self.assert_success(self.run_component(game, component))
                self.assertIn("no resources changed", transcript.lower())
                self.assertEqual(before, file_tree(game.override))
                for resref in resources:
                    self.assertRegex(
                        transcript,
                        rf"(?im)^.*WARNING.*{re.escape(resref)}\.CRE.*missing.*$",
                    )
                self.assert_uninstall_restores(game, component, before)

    def test_malformed_targets_fail_clearly_and_roll_back_prior_valid_variants(self):
        valid = source_cre(5)
        malformed = (
            (b"BAD V1.0" + valid[8:], r"signature|cre v1\.0"),
            (b"CRE V9.0" + valid[8:], r"signature|cre v1\.0"),
            (valid[:0x100], r"truncated|header"),
            (valid[:0x2D3], r"truncated|header"),
        )
        for component, (resources, _) in STAT_COMPONENTS.items():
            for payload, error in malformed:
                with self.subTest(component=component, error=error, size=len(payload)), self.staged_game() as game:
                    damaged = resources[-1]
                    resource_path(game.override, f"{damaged}.CRE").write_bytes(payload)
                    before = file_tree(game.override)
                    result = self.run_component(game, component)
                    transcript = result.stdout + result.stderr
                    self.assertNotEqual(0, result.returncode, transcript)
                    self.assertIn("NOT INSTALLED DUE TO ERRORS", transcript)
                    self.assertIn(f"{damaged}.CRE", transcript.upper())
                    self.assertRegex(transcript.lower(), error)
                    self.assertEqual(before, file_tree(game.override))


if __name__ == "__main__":
    unittest.main()
