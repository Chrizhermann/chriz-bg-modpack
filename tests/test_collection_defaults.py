from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TP2 = ROOT / "setup-chriz-bg-modpack.tp2"
LIBRARY = ROOT / "chriz-bg-modpack/lib/cbm_collection_defaults.tpa"
SKIE_LIBRARY = ROOT / "chriz-bg-modpack/lib/cbm_skie_skill_fix.tpa"
HARNESS = ROOT / "tests/weidu/collection_defaults_harness.tp2"

TRUECLASS_ID = 0x4100
INVOKER_ID = 0x0811
KIT_IDS = {
    "TRUECLASS": TRUECLASS_ID,
    "MAGESCHOOL_INVOKER": INVOKER_ID,
    "DWARVEN_DEFENDER": 0x4122,
    "SWASHBUCKLER": 0x412C,
    "BEASTFRIEND": 0x4132,
    "FERALAN": 0x4147,
}
CLASS_IDS = {
    "MAGE": 21,
    "FIGHTER": 22,
    "THIEF": 24,
    "DRUID": 31,
    "RANGER": 32,
}
VANILLA_HASTE_ID = 2305
# Deliberately relocated from vanilla SPWI305. This proves that the production
# path follows the effective WIZARD_HASTE entry in the installed SPELL.IDS.
EFFECTIVE_HASTE_ID = 2399
EFFECTIVE_HASTE_RESREF = "SPWI399"
SKIE_PROFILES = {
    "SKIE": (5_098, 20, 25, 45),
    "SKIE6": (20_056, 30, 35, 65),
    "BDSKIE": (64_000, 35, 35, 70),
    "BDSKIED": (64_000, 35, 35, 70),
}


@dataclass(frozen=True)
class ComponentSpec:
    public_component: int
    harness_component: int
    class_symbol: str
    source_kit_symbol: str
    target_kit_symbol: str
    resources: tuple[tuple[str, str], ...]


KIT_COMPONENTS = {
    "kagain": ComponentSpec(
        194,
        1,
        "FIGHTER",
        "TRUECLASS",
        "DWARVEN_DEFENDER",
        (("KAGAIN", "KAGAIN"), ("KAGAIN2", "KAGAIN"),
         ("KAGAIN4", "KAGAIN"), ("KAGAIN6", "KAGAIN")),
    ),
    "skie": ComponentSpec(
        195,
        2,
        "THIEF",
        "TRUECLASS",
        "SWASHBUCKLER",
        (("SKIE", "SKIE"), ("SKIE6", "SKIE"),
         ("BDSKIE", "BDSKIE"), ("BDSKIED", "BDSKIED")),
    ),
    "faldorn": ComponentSpec(
        196,
        3,
        "DRUID",
        "TRUECLASS",
        "BEASTFRIEND",
        (("FALDOR", "FALDORN"), ("FALDOR5", "FALDORN")),
    ),
    "kivan": ComponentSpec(
        198,
        5,
        "RANGER",
        "TRUECLASS",
        "FERALAN",
        (("KIVAN", "KIVAN"), ("KIVAN4", "KIVAN"),
         ("KIVAN6", "KIVAN")),
    ),
}
DYNAHEIR_RESOURCES = (
    ("DYNAHE", "Dynaheir"),
    ("DYNAHE2", "Dynaheir"),
    ("DYNAHE4", "Dynaheir"),
    ("DYNAHE6", "Dynaheir"),
    ("DYNAHE7", "DYNAHEIR"),
)

ONE_EMPTY_STRING_TLK = (
    struct.pack("<8sHII", b"TLK V1  ", 0, 1, 0x2C)
    + struct.pack("<H8siiII", 0, b"\0" * 8, 0, 0, 0, 0)
)


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def put_resref(buffer: bytearray, offset: int, value: str, size: int = 8) -> None:
    encoded = value.encode("ascii")
    if len(encoded) > size:
        raise ValueError(value)
    buffer[offset : offset + size] = encoded.ljust(size, b"\0")


def known_record(resref: str, level: int, spell_type: int) -> bytes:
    return struct.pack(
        "<8sHH", resref.encode("ascii").ljust(8, b"\0"), level, spell_type
    )


def memorization_info(level: int, index: int, count: int) -> bytes:
    return struct.pack("<HHHHII", level, count + 1, count + 2, 1, index, count)


def memorized_record(resref: str, memorized: int) -> bytes:
    return struct.pack(
        "<8sI", resref.encode("ascii").ljust(8, b"\0"), memorized
    )


def make_cre(
    *,
    class_id: int,
    kit: int,
    dv: str,
    seed: int = 1,
    haste_entries: tuple[tuple[int, int], ...] = (),
    haste_resref: str = EFFECTIVE_HASTE_RESREF,
    xp: int = 0,
    open_locks: int = 0,
    move_silently: int = 0,
) -> bytes:
    """Build a synthetic but structurally complete CRE V1.0 fixture."""
    header = bytearray(0x2D4)
    header[0:8] = b"CRE V1.0"
    header[0x33] = 1
    header[0x52] = (37 + seed) & 0xFF  # THAC0 sentinel
    header[0x53] = 7
    header[0x54:0x59] = bytes((seed + n * 3) & 0xFF for n in range(5))
    struct.pack_into("<I", header, 0x18, xp)
    header[0x67] = open_locks
    header[0x68] = move_silently
    header[0x234] = 5
    struct.pack_into("<I", header, 0x244, kit)
    header[0x273] = class_id
    put_resref(header, 0x280, dv, 32)

    known = [
        known_record("SPWI112", 0, 1),
        known_record("SPWI212", 1, 1),
        known_record("SPWI304", 2, 1),
        known_record("SPIN102", 0, 2),
    ]
    known.extend(known_record(haste_resref, level, spell_type)
                 for level, spell_type in haste_entries)
    known_blob = b"".join(known)

    meminfo_blob = b"".join(
        (memorization_info(0, 0, 2), memorization_info(1, 2, 1),
         memorization_info(2, 3, 1))
    )
    memorized_blob = b"".join(
        (
            memorized_record("SPWI112", 1),
            memorized_record("SPWI112", 0),
            memorized_record("SPWI212", 1),
            memorized_record("SPWI304", 0),
        )
    )
    # Keep every structured record valid so WeiDU has no reason to normalize
    # unrelated fields while rebuilding the CRE around a known-spell insert.
    effect = bytearray(0x108)
    struct.pack_into("<I", effect, 0x08, 142)
    struct.pack_into("<I", effect, 0x14, 1000 + seed)
    put_resref(effect, 0x30, "CBMEFF")
    effect_blob = bytes(effect)
    item = bytearray(20)
    put_resref(item, 0, "CBMITEM")
    struct.pack_into("<HHHHI", item, 8, 0, 1, 2, 3, 1)
    item_blob = bytes(item)
    slots = [0xFFFF] * 38 + [0, 0]
    slots[21] = 0
    slots_blob = struct.pack("<40H", *slots)

    known_off = len(header)
    meminfo_off = known_off + len(known_blob)
    memorized_off = meminfo_off + len(meminfo_blob)
    effects_off = memorized_off + len(memorized_blob)
    items_off = effects_off + len(effect_blob)
    slots_off = items_off + len(item_blob)

    struct.pack_into("<II", header, 0x2A0, known_off, len(known))
    struct.pack_into("<II", header, 0x2A8, meminfo_off, 3)
    struct.pack_into("<II", header, 0x2B0, memorized_off, 4)
    struct.pack_into("<I", header, 0x2B8, slots_off)
    struct.pack_into("<II", header, 0x2BC, items_off, 1)
    struct.pack_into("<II", header, 0x2C4, effects_off, 1)

    return bytes(header) + known_blob + meminfo_blob + memorized_blob + effect_blob + item_blob + slots_blob


def known_records(data: bytes) -> list[bytes]:
    offset, count = u32(data, 0x2A0), u32(data, 0x2A4)
    return [data[offset + n * 12 : offset + (n + 1) * 12] for n in range(count)]


def section(data: bytes, offset_field: int, count_field: int, stride: int) -> bytes:
    offset, count = u32(data, offset_field), u32(data, count_field)
    return data[offset : offset + count * stride]


def file_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix().upper(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def find_weidu() -> str | None:
    configured = os.environ.get("WEIDU_BIN")
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("weidu") or shutil.which("weidu.exe")


def component_block(source: str, component: int) -> str:
    marker = f"BEGIN @{component} DESIGNATED {component}"
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"public component {component} is missing")
    following = source[start + len(marker) :]
    next_component = following.find("\nBEGIN @")
    if next_component < 0:
        return source[start:]
    return source[start : start + len(marker) + next_component]


def write_marker_key_and_bif(game_root: Path) -> Path:
    payload = b"synthetic BG2EE marker"
    bif_relative = Path("DATA/CBMDEFAULTS.BIF")
    bif_path = game_root / bif_relative
    bif_path.parent.mkdir(parents=True)
    table_offset = 0x14
    payload_offset = table_offset + 0x10
    bif_path.write_bytes(
        struct.pack("<4s4sIII", b"BIFF", b"V1  ", 1, 0, table_offset)
        + struct.pack("<IIIHH", 0, payload_offset, len(payload), 1010, 0)
        + payload
    )
    encoded_name = (str(bif_relative).replace("/", "\\") + "\0").encode("ascii")
    bif_table_offset = 0x18
    resource_table_offset = bif_table_offset + 0x0C
    names_offset = resource_table_offset + 0x0E
    key = bytearray(
        struct.pack(
            "<4s4sIIII", b"KEY ", b"V1  ", 1, 1,
            bif_table_offset, resource_table_offset,
        )
    )
    key.extend(struct.pack("<IIHH", bif_path.stat().st_size, names_offset,
                           len(encoded_name), 0))
    key.extend(struct.pack("<8sHI", b"OH6000\0\0", 1010, 0))
    key.extend(encoded_name)
    (game_root / "chitin.key").write_bytes(key)
    return bif_path


class SyntheticGame:
    def __init__(self, root: Path, *, haste_id: int = EFFECTIVE_HASTE_ID):
        self.root = root
        self.root.mkdir()
        self.override = root / "override"
        self.override.mkdir()
        kit_text = "IDS\n" + "".join(
            f"0x{value:04X} {symbol}\n" for symbol, value in KIT_IDS.items()
        )
        class_text = "IDS\n" + "".join(
            f"{value} {symbol}\n" for symbol, value in CLASS_IDS.items()
        )
        (self.override / "KIT.IDS").write_text(kit_text, encoding="ascii")
        (self.override / "CLASS.IDS").write_text(class_text, encoding="ascii")
        (self.override / "SPELL.IDS").write_text(
            f"IDS\n{haste_id} WIZARD_HASTE\n", encoding="ascii"
        )
        haste_resref = f"SPWI{haste_id - 2000}"
        # Presence is validated by the production context resolver. The spell
        # payload is irrelevant to a known-spell-list insertion.
        (self.override / f"{haste_resref}.SPL").write_bytes(b"synthetic spell")
        self.bif = write_marker_key_and_bif(root)
        lang_tlk = root / "lang/en_us/dialog.tlk"
        lang_tlk.parent.mkdir(parents=True)
        lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        (root / "dialog.tlk").write_bytes(ONE_EMPTY_STRING_TLK)
        self.initial_override = file_tree(self.override)


class CollectionDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.weidu = find_weidu()

    def run_harness(
        self,
        component: int,
        source: bytes,
        *,
        expected_dv: str,
        haste_id: int = EFFECTIVE_HASTE_ID,
    ) -> tuple[subprocess.CompletedProcess[str], bytes | None]:
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        with tempfile.TemporaryDirectory(prefix="cbm-collection-defaults-") as raw:
            run_dir = Path(raw)
            game = SyntheticGame(run_dir / "game", haste_id=haste_id)
            harness = run_dir / HARNESS.name
            source_path = run_dir / "source.cre"
            output_path = run_dir / "output.cre"
            shutil.copy2(HARNESS, harness)
            source_path.write_bytes(source)
            result = subprocess.run(
                [
                    self.weidu,
                    harness.name,
                    "--no-auto-tp2",
                    "--game",
                    str(game.root),
                    "--force-install-list",
                    str(component),
                    "--args",
                    LIBRARY.as_posix(),
                    "--args",
                    source_path.as_posix(),
                    "--args",
                    output_path.as_posix(),
                    "--args",
                    expected_dv,
                    "--args",
                    SKIE_LIBRARY.as_posix(),
                    "--language",
                    "0",
                    "--use-lang",
                    "en_us",
                    "--no-exit-pause",
                    "--quick-log",
                ],
                cwd=run_dir,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(
                game.initial_override,
                file_tree(game.override),
                "symbol resolution must not materialize or rewrite IDS resources",
            )
            output = output_path.read_bytes() if output_path.is_file() else None
            return result, output

    @staticmethod
    def transcript(result: subprocess.CompletedProcess[str]) -> str:
        return result.stdout + result.stderr

    def transform(
        self,
        component: int,
        source: bytes,
        *,
        expected_dv: str,
        haste_id: int = EFFECTIVE_HASTE_ID,
    ) -> bytes:
        result, output = self.run_harness(
            component, source, expected_dv=expected_dv, haste_id=haste_id
        )
        transcript = self.transcript(result)
        self.assertEqual(0, result.returncode, transcript)
        self.assertIsNotNone(output, transcript)
        return output

    def assert_fails_closed(
        self,
        component: int,
        source: bytes,
        *,
        expected_dv: str,
        pattern: str,
    ) -> None:
        result, output = self.run_harness(component, source, expected_dv=expected_dv)
        transcript = self.transcript(result)
        self.assertNotEqual(0, result.returncode, transcript)
        self.assertIsNone(output, transcript)
        self.assertRegex(transcript.lower(), pattern)

    def test_harness_uses_canonical_installed_symbols(self):
        text = HARNESS.read_text(encoding="utf-8")
        for symbol in (
            "FIGHTER", "THIEF", "DRUID", "MAGE", "RANGER", "TRUECLASS",
            "DWARVEN_DEFENDER", "SWASHBUCKLER", "BEASTFRIEND", "FERALAN",
            "MAGESCHOOL_INVOKER", "WIZARD_HASTE",
        ):
            self.assertIn(f"~{symbol}~", text)
        self.assertNotIn("~AVENGER~", text)
        self.assertNotIn("~ARCHER~", text)
        skie_block = text.split("DESIGNATED 2", 1)[1].split("DESIGNATED 3", 1)[0]
        self.assertIn("INCLUDE ~%argv[4]%~", skie_block)
        self.assertEqual(1, skie_block.count("COPY ~%argv[1]%~ ~%argv[2]%~"))
        self.assertLess(
            skie_block.index("cbm_collection_make_skie_swashbuckler"),
            skie_block.index("cbm_skie_move_stealth_to_locks"),
        )

    def test_every_explicit_kit_variant_changes_only_the_resolved_kit(self):
        for group, spec in KIT_COMPONENTS.items():
            source_kit = KIT_IDS[spec.source_kit_symbol] << 16
            target_kit = KIT_IDS[spec.target_kit_symbol] << 16
            for index, (resref, dv) in enumerate(spec.resources):
                with self.subTest(group=group, resref=resref):
                    source_options: dict[str, int] = {}
                    if group == "skie":
                        xp, locks, move, _ = SKIE_PROFILES[resref]
                        source_options = {
                            "xp": xp,
                            "open_locks": locks,
                            "move_silently": move,
                        }
                    source = make_cre(
                        class_id=CLASS_IDS[spec.class_symbol],
                        kit=source_kit,
                        dv=dv.swapcase() if index % 2 else dv,
                        seed=20 + index,
                        **source_options,
                    )
                    transformed = self.transform(
                        spec.harness_component, source, expected_dv=dv
                    )
                    self.assertEqual(target_kit, u32(transformed, 0x244))
                    self.assertEqual(source[0x52], transformed[0x52], "THAC0 changed")
                    mutable_offsets = set(range(0x244, 0x248))
                    if group == "skie":
                        self.assertEqual(SKIE_PROFILES[resref][3], transformed[0x67])
                        self.assertEqual(0, transformed[0x68])
                        mutable_offsets.update((0x67, 0x68))
                    self.assertEqual(len(source), len(transformed))
                    for offset, (before, after) in enumerate(zip(source, transformed)):
                        if offset not in mutable_offsets:
                            self.assertEqual(
                                before,
                                after,
                                f"{resref} changed unrelated byte 0x{offset:03X}",
                            )

    def test_kit_changes_are_byte_idempotent(self):
        for group, spec in KIT_COMPONENTS.items():
            resref, dv = spec.resources[0]
            source_options: dict[str, int] = {}
            if group == "skie":
                xp, locks, move, _ = SKIE_PROFILES[resref]
                source_options = {
                    "xp": xp,
                    "open_locks": locks,
                    "move_silently": move,
                }
            source = make_cre(
                class_id=CLASS_IDS[spec.class_symbol],
                kit=KIT_IDS[spec.source_kit_symbol] << 16,
                dv=dv,
                seed=44,
                **source_options,
            )
            with self.subTest(group=group):
                first = self.transform(spec.harness_component, source, expected_dv=dv)
                second = self.transform(spec.harness_component, first, expected_dv=dv)
                self.assertEqual(first, second)

    def test_skie_default_is_atomic_when_the_skill_state_is_invalid(self):
        source = make_cre(
            class_id=CLASS_IDS["THIEF"],
            kit=KIT_IDS["TRUECLASS"] << 16,
            dv="SKIE",
            xp=5_098,
            open_locks=21,
            move_silently=25,
        )
        self.assert_fails_closed(2, source, expected_dv="SKIE", pattern=r"skill|state")

    def test_kit_guards_reject_wrong_signature_identity_class_and_kit(self):
        for group, spec in KIT_COMPONENTS.items():
            _, dv = spec.resources[0]
            class_id = CLASS_IDS[spec.class_symbol]
            source_kit = KIT_IDS[spec.source_kit_symbol] << 16
            bad_signature = bytearray(
                make_cre(class_id=class_id, kit=source_kit, dv=dv, seed=51)
            )
            bad_signature[0:8] = b"BAD V1.0"
            cases = (
                (bytes(bad_signature), r"signature|cre v1\.0"),
                (make_cre(class_id=class_id, kit=source_kit, dv="SOMEONEELSE"), r"death.?variable|\bdv\b"),
                (make_cre(class_id=(class_id + 1) & 0xFF, kit=source_kit, dv=dv), r"\bclass\b"),
                (make_cre(class_id=class_id, kit=0x5ABC0000, dv=dv), r"\bkit\b"),
            )
            for source, pattern in cases:
                with self.subTest(group=group, pattern=pattern):
                    self.assert_fails_closed(
                        spec.harness_component,
                        source,
                        expected_dv=dv,
                        pattern=pattern,
                    )

    def test_all_dynaheir_variants_gain_haste_once_without_memorized_changes(self):
        allowed_header_changes = set(range(0x2A4, 0x2A8))
        for field in (0x2A8, 0x2B0, 0x2B8, 0x2BC, 0x2C4):
            allowed_header_changes.update(range(field, field + 4))
        for index, (resref, dv) in enumerate(DYNAHEIR_RESOURCES):
            with self.subTest(resref=resref):
                source = make_cre(
                    class_id=CLASS_IDS["MAGE"],
                    kit=INVOKER_ID << 16,
                    dv=dv.swapcase() if index % 2 else dv,
                    seed=70 + index,
                )
                transformed = self.transform(4, source, expected_dv=dv)
                haste = [
                    record for record in known_records(transformed)
                    if record[:8].rstrip(b"\0").upper() == EFFECTIVE_HASTE_RESREF.encode()
                ]
                self.assertEqual(
                    [known_record(EFFECTIVE_HASTE_RESREF, 2, 1)], haste
                )
                self.assertEqual(len(source) + 12, len(transformed))
                self.assertEqual(source[0x52], transformed[0x52], "THAC0 changed")

                before_header = bytearray(source[:0x2D4])
                after_header = bytearray(transformed[:0x2D4])
                for offset in allowed_header_changes:
                    before_header[offset] = after_header[offset] = 0
                self.assertEqual(before_header, after_header)
                self.assertEqual(
                    known_records(source),
                    [record for record in known_records(transformed)
                     if record[:8].rstrip(b"\0").upper() != EFFECTIVE_HASTE_RESREF.encode()],
                )
                for offset_field, count_field, stride in (
                    (0x2A8, 0x2AC, 16),
                    (0x2B0, 0x2B4, 12),
                    (0x2C4, 0x2C8, 0x108),
                    (0x2BC, 0x2C0, 20),
                ):
                    self.assertEqual(
                        section(source, offset_field, count_field, stride),
                        section(transformed, offset_field, count_field, stride),
                    )
                self.assertEqual(
                    source[u32(source, 0x2B8) : u32(source, 0x2B8) + 80],
                    transformed[u32(transformed, 0x2B8) : u32(transformed, 0x2B8) + 80],
                )

    def test_dynaheir_haste_is_byte_idempotent_when_already_known(self):
        source = make_cre(
            class_id=CLASS_IDS["MAGE"],
            kit=INVOKER_ID << 16,
            dv="Dynaheir",
            seed=83,
            haste_entries=((2, 1),),
        )
        transformed = self.transform(4, source, expected_dv="DYNAHEIR")
        self.assertEqual(source, transformed)

    def test_vanilla_spell_ids_mapping_adds_spwi305_exactly_once(self):
        source = make_cre(
            class_id=CLASS_IDS["MAGE"],
            kit=INVOKER_ID << 16,
            dv="Dynaheir",
            seed=84,
        )
        transformed = self.transform(
            4,
            source,
            expected_dv="DYNAHEIR",
            haste_id=VANILLA_HASTE_ID,
        )
        haste = [
            record
            for record in known_records(transformed)
            if record[:8].rstrip(b"\0").upper() == b"SPWI305"
        ]
        self.assertEqual([known_record("SPWI305", 2, 1)], haste)

    def test_dynaheir_rejects_duplicate_or_malformed_haste_entries(self):
        cases = (
            (((2, 1), (2, 1)), r"duplicate|exactly once"),
            (((3, 1),), r"level|metadata"),
            (((2, 2),), r"type|metadata"),
        )
        for entries, pattern in cases:
            with self.subTest(entries=entries):
                source = make_cre(
                    class_id=CLASS_IDS["MAGE"],
                    kit=INVOKER_ID << 16,
                    dv="Dynaheir",
                    haste_entries=entries,
                )
                self.assert_fails_closed(
                    4, source, expected_dv="DYNAHEIR", pattern=pattern
                )

    def test_dynaheir_guards_identity_class_and_invoker_kit(self):
        base = dict(class_id=CLASS_IDS["MAGE"], kit=INVOKER_ID << 16, dv="Dynaheir")
        bad_signature = bytearray(make_cre(**base))
        bad_signature[0:8] = b"BAD V1.0"
        cases = (
            (bytes(bad_signature), r"signature|cre v1\.0"),
            (make_cre(**{**base, "dv": "NOTDYNAHEIR"}), r"death.?variable|\bdv\b"),
            (make_cre(**{**base, "class_id": CLASS_IDS["FIGHTER"]}), r"\bclass\b"),
            (make_cre(**{**base, "kit": TRUECLASS_ID << 16}), r"\bkit\b"),
        )
        for source, pattern in cases:
            with self.subTest(pattern=pattern):
                self.assert_fails_closed(
                    4, source, expected_dv="DYNAHEIR", pattern=pattern
                )

    def test_truncated_creatures_fail_before_output_publication(self):
        for component in range(1, 6):
            with self.subTest(component=component):
                self.assert_fails_closed(
                    component,
                    b"CRE V1.0" + bytes(40),
                    expected_dv="KAGAIN" if component == 1 else "DYNAHEIR",
                    pattern=r"truncated|header",
                )

    def test_public_component_metadata_wires_every_explicit_resource(self):
        source = TP2.read_text(encoding="utf-8")
        functions = {
            "kagain": "cbm_collection_make_kagain_dwarven_defender",
            "skie": "cbm_collection_make_skie_swashbuckler",
            "faldorn": "cbm_collection_make_faldorn_avenger",
            "kivan": "cbm_collection_make_kivan_archer",
        }
        for group, spec in KIT_COMPONENTS.items():
            with self.subTest(group=group):
                block = component_block(source, spec.public_component)
                self.assertIn(functions[group], block)
                for resref, _ in spec.resources:
                    self.assertIn(f"FILE_EXISTS_IN_GAME ~{resref}.CRE~", block)
                    self.assertRegex(block, rf"(?i)\b{re.escape(resref)}\b")
        skie = component_block(source, 195)
        self.assertEqual(1, skie.count("COPY_EXISTING"))
        self.assertLess(
            skie.index("cbm_collection_make_skie_swashbuckler"),
            skie.index("cbm_skie_move_stealth_to_locks"),
        )
        dynaheir = component_block(source, 197)
        self.assertIn("WIZARD_HASTE", dynaheir)
        self.assertNotIn("SPWI305", dynaheir)
        for resref, _ in DYNAHEIR_RESOURCES:
            self.assertIn(f"FILE_EXISTS_IN_GAME ~{resref}.CRE~", dynaheir)
        self.assertNotIn("BEGIN @199", source)

    def _run_public(
        self, game: SyntheticGame, operation: str, component: int
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                self.weidu,
                TP2.name,
                "--no-auto-tp2",
                "--game",
                str(game.root),
                operation,
                str(component),
                "--language",
                "0",
                "--use-lang",
                "en_us",
                "--no-exit-pause",
                "--quick-log",
            ],
            cwd=game.root,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )

    def _stage_public_component(
        self, game: SyntheticGame, component: int
    ) -> tuple[list[str], dict[str, int]]:
        expected_skills: dict[str, int] = {}
        if component == 197:
            resources = list(DYNAHEIR_RESOURCES)
            for index, (resref, dv) in enumerate(resources):
                (game.override / f"{resref}.CRE").write_bytes(
                    make_cre(
                        class_id=CLASS_IDS["MAGE"],
                        kit=KIT_IDS["MAGESCHOOL_INVOKER"] << 16,
                        dv=dv,
                        seed=130 + index,
                    )
                )
            return [resref for resref, _ in resources], expected_skills

        spec = next(
            candidate
            for candidate in KIT_COMPONENTS.values()
            if candidate.public_component == component
        )
        for index, (resref, dv) in enumerate(spec.resources):
            options: dict[str, int] = {}
            if component == 195:
                xp, locks, move, target_locks = SKIE_PROFILES[resref]
                options = {
                    "xp": xp,
                    "open_locks": locks,
                    "move_silently": move,
                }
                expected_skills[resref] = target_locks
            (game.override / f"{resref}.CRE").write_bytes(
                make_cre(
                    class_id=CLASS_IDS[spec.class_symbol],
                    kit=KIT_IDS[spec.source_kit_symbol] << 16,
                    dv=dv,
                    seed=150 + index,
                    **options,
                )
            )
        return [resref for resref, _ in spec.resources], expected_skills

    def test_public_components_install_and_uninstall_byte_exactly(self):
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        for component in (194, 195, 196, 197, 198):
            with self.subTest(component=component), tempfile.TemporaryDirectory(
                prefix=f"cbm-public-default-{component}-"
            ) as raw:
                game = SyntheticGame(Path(raw) / "game")
                shutil.copy2(TP2, game.root / TP2.name)
                shutil.copytree(
                    ROOT / "chriz-bg-modpack", game.root / "chriz-bg-modpack"
                )
                resources, expected_skills = self._stage_public_component(game, component)
                before = file_tree(game.override)

                install = self._run_public(game, "--force-install-list", component)
                transcript = self.transcript(install)
                self.assertEqual(0, install.returncode, transcript)
                self.assertIn("SUCCESSFULLY INSTALLED", transcript)
                for resref in resources:
                    transformed = (game.override / f"{resref}.CRE").read_bytes()
                    if component == 197:
                        haste = [
                            row
                            for row in known_records(transformed)
                            if row[:8].rstrip(b"\0").upper()
                            == EFFECTIVE_HASTE_RESREF.encode()
                        ]
                        self.assertEqual(
                            [known_record(EFFECTIVE_HASTE_RESREF, 2, 1)], haste
                        )
                    else:
                        spec = next(
                            candidate
                            for candidate in KIT_COMPONENTS.values()
                            if candidate.public_component == component
                        )
                        self.assertEqual(
                            KIT_IDS[spec.target_kit_symbol] << 16,
                            u32(transformed, 0x244),
                        )
                    if component == 195:
                        self.assertEqual(expected_skills[resref], transformed[0x67])
                        self.assertEqual(0, transformed[0x68])

                uninstall = self._run_public(game, "--force-uninstall-list", component)
                self.assertEqual(0, uninstall.returncode, self.transcript(uninstall))
                self.assertEqual(before, file_tree(game.override))

    def test_public_components_preflight_all_declared_resources(self):
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        for component in (194, 195, 196, 197, 198):
            with self.subTest(component=component), tempfile.TemporaryDirectory(
                prefix=f"cbm-public-default-missing-{component}-"
            ) as raw:
                game = SyntheticGame(Path(raw) / "game")
                shutil.copy2(TP2, game.root / TP2.name)
                shutil.copytree(
                    ROOT / "chriz-bg-modpack", game.root / "chriz-bg-modpack"
                )
                resources, _ = self._stage_public_component(game, component)
                missing = resources[-1]
                (game.override / f"{missing}.CRE").unlink()
                before = file_tree(game.override)
                install = self._run_public(game, "--force-install-list", component)
                transcript = self.transcript(install)
                self.assertEqual(0, install.returncode, transcript)
                self.assertIn("SKIPPING", transcript)
                self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
                self.assertIn(f"{missing}.CRE", transcript)
                self.assertEqual(before, file_tree(game.override))


if __name__ == "__main__":
    unittest.main()
