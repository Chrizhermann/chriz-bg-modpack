from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests/weidu/spell_tail_public_harness.tp2"
LIB_DIR = ROOT / "chriz-bg-modpack/lib"
LIBRARIES = {
    400: LIB_DIR / "cbm_branwen_hammer_fix.tpa",
    410: LIB_DIR / "cbm_yeslick_keldorn_dispel_fix.tpa",
    430: LIB_DIR / "cbm_uai_caster_level.tpa",
    440: LIB_DIR / "cbm_ascension_slayer_eefp_fix.tpa",
    450: LIB_DIR / "cbm_scs_shapechange_eefp_fix.tpa",
}

ONE_EMPTY_STRING_TLK = (
    struct.pack("<8sHII", b"TLK V1  ", 0, 1, 0x2C)
    + struct.pack("<H8siiII", 0, b"\0" * 8, 0, 0, 0, 0)
)


def find_weidu() -> str | None:
    configured = os.environ.get("WEIDU_BIN")
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("weidu") or shutil.which("weidu.exe")


def file_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix().upper(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def resource_path(root: Path, name: str) -> Path:
    """Return the lowercase on-disk path WeiDU uses on case-sensitive hosts."""
    return root / name.lower()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def effect(
    opcode: int,
    *,
    p1: int = 0,
    p2: int = 0,
    timing: int = 1,
    duration: int = 37,
    resource: str = "",
    probability1: int = 100,
    probability2: int = 0,
    marker: int = 0x5A,
) -> bytes:
    data = bytearray([marker] * 0x30)
    struct.pack_into("<H", data, 0x00, opcode)
    data[0x02] = 2
    data[0x03] = 3
    struct.pack_into("<I", data, 0x04, p1)
    struct.pack_into("<I", data, 0x08, p2)
    data[0x0C] = timing
    data[0x0D] = 1
    struct.pack_into("<I", data, 0x0E, duration)
    data[0x12] = probability1
    data[0x13] = probability2
    encoded = resource.encode("ascii")[:8]
    data[0x14:0x1C] = encoded.ljust(8, b"\0")
    return bytes(data)


def ability(
    first_effect: int,
    effect_count: int,
    *,
    minimum_level: int = 1,
    projectile: int = 157,
    ability_type: int = 3,
    marker: int = 0x35,
    size: int = 0x28,
) -> bytes:
    data = bytearray([marker] * size)
    data[0x00] = ability_type
    data[0x0C] = 4
    struct.pack_into("<H", data, 0x10, minimum_level)
    struct.pack_into("<H", data, 0x1E, effect_count)
    struct.pack_into("<H", data, 0x20, first_effect)
    if size == 0x28:
        struct.pack_into("<H", data, 0x26, projectile)
    return bytes(data)


def make_spl(
    ability_effects: list[list[bytes]],
    *,
    minimum_levels: list[int] | None = None,
    projectiles: list[int] | None = None,
    casting_effects: list[bytes] | None = None,
    footer: bytes = b"",
) -> bytes:
    minimum_levels = minimum_levels or list(range(1, len(ability_effects) + 1))
    projectiles = projectiles or [157] * len(ability_effects)
    casting_effects = casting_effects or []
    header = bytearray(0x72)
    header[:8] = b"SPL V1  "
    header[0x08:0x10] = b"CBMTEST\0"
    ability_offset = 0x72
    effect_offset = ability_offset + (len(ability_effects) * 0x28)
    struct.pack_into("<I", header, 0x64, ability_offset)
    struct.pack_into("<H", header, 0x68, len(ability_effects))
    struct.pack_into("<I", header, 0x6A, effect_offset)
    total_ability_effects = sum(len(items) for items in ability_effects)
    struct.pack_into("<H", header, 0x6E, total_ability_effects)
    struct.pack_into("<H", header, 0x70, len(casting_effects))

    headers = bytearray()
    flat_effects = bytearray()
    first = 0
    for index, items in enumerate(ability_effects):
        headers.extend(
            ability(
                first,
                len(items),
                minimum_level=minimum_levels[index],
                projectile=projectiles[index],
                marker=0x31 + index,
            )
        )
        flat_effects.extend(b"".join(items))
        first += len(items)
    flat_effects.extend(b"".join(casting_effects))
    return bytes(header + headers + flat_effects + footer)


def make_itm(
    category: int,
    ability_effects: list[list[bytes]],
    *,
    ability_types: list[int] | None = None,
    equipped_effects: list[bytes] | None = None,
    footer: bytes = b"",
) -> bytes:
    ability_types = ability_types or [3] * len(ability_effects)
    equipped_effects = equipped_effects or []
    header = bytearray(0x72)
    header[:8] = b"ITM V1  "
    header[0x08:0x10] = b"CBMITEM\0"
    struct.pack_into("<H", header, 0x1C, category)
    ability_offset = 0x72
    effect_offset = ability_offset + (len(ability_effects) * 0x38)
    struct.pack_into("<I", header, 0x64, ability_offset)
    struct.pack_into("<H", header, 0x68, len(ability_effects))
    struct.pack_into("<I", header, 0x6A, effect_offset)
    first_equipped = sum(len(items) for items in ability_effects)
    struct.pack_into("<H", header, 0x6E, first_equipped)
    struct.pack_into("<H", header, 0x70, len(equipped_effects))

    headers = bytearray()
    flat_effects = bytearray()
    first = 0
    for index, items in enumerate(ability_effects):
        headers.extend(
            ability(
                first,
                len(items),
                ability_type=ability_types[index],
                marker=0x61 + index,
                size=0x38,
            )
        )
        flat_effects.extend(b"".join(items))
        first += len(items)
    flat_effects.extend(b"".join(equipped_effects))
    return bytes(header + headers + flat_effects + footer)


def rearrange_spl(
    data: bytes, *, casting_first: bool, effects_first: bool, reverse: bool = True
) -> bytes:
    """Put identical indexed lists in padded, noncanonical physical locations."""
    old_ability_offset = struct.unpack_from("<I", data, 0x64)[0]
    old_effect_offset = struct.unpack_from("<I", data, 0x6A)[0]
    rows = spl_abilities(data)
    casts = casting_effects(data)
    headers = bytearray(data[old_ability_offset:old_effect_offset])
    flat = bytearray(b"UNREFERENCED-EFFECT-PADDING".ljust(0x30, b"!"))
    order = list(reversed(range(len(rows)))) if reverse else list(range(len(rows)))
    order.insert(0 if casting_first else len(order), -1)
    cast_first = 0
    for index in order:
        first = len(flat) // 0x30
        if index == -1:
            cast_first = first
            flat.extend(b"".join(casts))
        else:
            struct.pack_into("<H", headers, index * 0x28 + 0x20, first)
            flat.extend(b"".join(rows[index]["effects"]))
        flat.extend(b"OPAQUE-SLICE-GAP".ljust(0x30, b"?"))
    # The last gap is a physical trailer, not part of any indexed list.
    header = bytearray(data[:0x72])
    prefix = b"PREFIX-PADDING\x00%marker%\xff"
    middle = b"BETWEEN-TABLES\x00\xaa\x55"
    old_end = old_effect_offset + 0x30 * (
        sum(len(row["effects"]) for row in rows) + len(casts)
    )
    footer = data[old_end:]
    if effects_first:
        effect_offset = 0x72 + len(prefix)
        ability_offset = effect_offset + len(flat) + len(middle)
        body = prefix + flat + middle + headers
    else:
        ability_offset = 0x72 + len(prefix)
        effect_offset = ability_offset + len(headers) + len(middle)
        body = prefix + headers + middle + flat
    struct.pack_into("<I", header, 0x64, ability_offset)
    struct.pack_into("<I", header, 0x6A, effect_offset)
    struct.pack_into("<H", header, 0x6E, cast_first)
    return bytes(header + body + footer)


def spl_abilities(data: bytes) -> list[dict[str, object]]:
    ability_offset = struct.unpack_from("<I", data, 0x64)[0]
    ability_count = struct.unpack_from("<H", data, 0x68)[0]
    effect_offset = struct.unpack_from("<I", data, 0x6A)[0]
    rows: list[dict[str, object]] = []
    for index in range(ability_count):
        header_offset = ability_offset + (index * 0x28)
        count = struct.unpack_from("<H", data, header_offset + 0x1E)[0]
        first = struct.unpack_from("<H", data, header_offset + 0x20)[0]
        rows.append(
            {
                "offset": header_offset,
                "minimum_level": struct.unpack_from("<H", data, header_offset + 0x10)[0],
                "projectile": struct.unpack_from("<H", data, header_offset + 0x26)[0],
                "effects": [
                    data[
                        effect_offset + ((first + effect_index) * 0x30) :
                        effect_offset + ((first + effect_index + 1) * 0x30)
                    ]
                    for effect_index in range(count)
                ],
            }
        )
    return rows


def casting_effects(data: bytes) -> list[bytes]:
    effect_offset = struct.unpack_from("<I", data, 0x6A)[0]
    first = struct.unpack_from("<H", data, 0x6E)[0]
    count = struct.unpack_from("<H", data, 0x70)[0]
    return [
        data[
            effect_offset + ((first + index) * 0x30) :
            effect_offset + ((first + index + 1) * 0x30)
        ]
        for index in range(count)
    ]


def itm_effects(data: bytes, *, equipped: bool) -> list[bytes]:
    effect_offset = struct.unpack_from("<I", data, 0x6A)[0]
    if equipped:
        first = struct.unpack_from("<H", data, 0x6E)[0]
        count = struct.unpack_from("<H", data, 0x70)[0]
    else:
        ability_offset = struct.unpack_from("<I", data, 0x64)[0]
        first = struct.unpack_from("<H", data, ability_offset + 0x20)[0]
        count = struct.unpack_from("<H", data, ability_offset + 0x1E)[0]
    return [
        data[
            effect_offset + ((first + index) * 0x30) :
            effect_offset + ((first + index + 1) * 0x30)
        ]
        for index in range(count)
    ]


def opcode(row: bytes) -> int:
    return struct.unpack_from("<H", row, 0x00)[0]


def p1(row: bytes) -> int:
    return struct.unpack_from("<I", row, 0x04)[0]


def p2(row: bytes) -> int:
    return struct.unpack_from("<I", row, 0x08)[0]


def resref(row: bytes) -> str:
    return row[0x14:0x1C].split(b"\0", 1)[0].decode("ascii").lower()


def write_marker_key_and_bif(game_root: Path) -> Path:
    payload = b"synthetic BG2EE marker"
    bif_relative = Path("DATA/CBMSPELL.BIF")
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
            "<4s4sIIII",
            b"KEY ",
            b"V1  ",
            1,
            1,
            bif_table_offset,
            resource_table_offset,
        )
    )
    key.extend(
        struct.pack("<IIHH", bif_path.stat().st_size, names_offset, len(encoded_name), 0)
    )
    key.extend(struct.pack("<8sHI", b"OH6000\0\0", 1010, 0))
    key.extend(encoded_name)
    (game_root / "chitin.key").write_bytes(key)
    return bif_path


class SyntheticSpellGame:
    def __init__(self, root: Path, resources: dict[str, bytes]) -> None:
        self.root = root
        self.root.mkdir(parents=True)
        self.override = self.root / "override"
        self.override.mkdir()
        (self.root / "weidu.log").write_text("", encoding="ascii")
        self.bif = write_marker_key_and_bif(self.root)
        self.lang_tlk = self.root / "lang/en_us/dialog.tlk"
        self.lang_tlk.parent.mkdir(parents=True)
        self.lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.root_tlk = self.root / "dialog.tlk"
        self.root_tlk.write_bytes(ONE_EMPTY_STRING_TLK)

        shutil.copy2(HARNESS, self.root / HARNESS.name)
        destination_lib = self.root / "chriz-bg-modpack/lib"
        destination_lib.mkdir(parents=True)
        for source in LIBRARIES.values():
            if source.is_file():
                shutil.copy2(source, destination_lib / source.name)
        for name, payload in resources.items():
            resource_path(self.override, name).write_bytes(payload)

        self.initial_override = file_tree(self.override)
        self.initial_stable = {
            path: sha256(path)
            for path in (self.root / "chitin.key", self.bif, self.lang_tlk, self.root_tlk)
        }

    def run(
        self,
        weidu: str,
        *operation: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                weidu,
                HARNESS.name,
                "--no-auto-tp2",
                "--game",
                str(self.root),
                *operation,
                "--language",
                "0",
                "--use-lang",
                "en_us",
                "--no-exit-pause",
                "--quick-log",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    @staticmethod
    def transcript(result: subprocess.CompletedProcess[str]) -> str:
        return result.stdout + result.stderr

    def assert_stable_inputs(self, testcase: unittest.TestCase) -> None:
        testcase.assertEqual(
            self.initial_stable,
            {
                path: sha256(path)
                for path in (
                    self.root / "chitin.key",
                    self.bif,
                    self.lang_tlk,
                    self.root_tlk,
                )
            },
        )


def branwen_resources() -> dict[str, bytes]:
    abilities = []
    for level in (1, 7, 13):
        abilities.append(
            [
                effect(111, p1=0, p2=level, resource="SHAMMR", marker=level),
                effect(215, p1=level, resource="SPROTECT", marker=level + 1),
            ]
        )
    return {
        "SPIN113.SPL": make_spl(
            abilities,
            minimum_levels=[1, 7, 13],
            projectiles=[1, 1, 1],
            casting_effects=[effect(111, p1=0, resource="CASTONLY", marker=0xD1)],
            footer=b"BRANWEN-FOOTER",
        )
    }


def dispel_resources() -> dict[str, bytes]:
    yeslick_effects = [
        effect(215, p1=71, resource="SPROTECT", marker=0x71),
        effect(58, p1=0, p2=0, resource="", marker=0x72),
        effect(139, p1=14056, resource="", marker=0x73),
        effect(81, p1=11, p2=12, resource="DEAFNESS", marker=0x76),
        effect(77, p1=13, p2=14, resource="FEEBLEM", marker=0x77),
        effect(240, p1=15, p2=112, resource="ICONA", marker=0x78),
        effect(240, p1=16, p2=48, resource="ICONB", marker=0x79),
        effect(177, p1=7, p2=7, resource="DESTSELF", marker=0x7A),
        effect(221, p1=18, p2=19, resource="SCREEN", marker=0x7B),
        effect(174, p1=20, p2=21, resource="SOUND", marker=0x7C),
        effect(142, p1=22, p2=23, resource="PORTRAIT", marker=0x7D),
        effect(12, p1=24, p2=25, resource="SENTINEL", marker=0x7E),
    ]
    yeslick = make_spl(
        [yeslick_effects],
        projectiles=[157],
        casting_effects=[
            effect(146, p1=19, p2=2, resource="DW#HOOK", marker=0x74),
            effect(321, p1=23, p2=4, resource="DW#MARK", marker=0x75),
        ],
        footer=b"YESLICK-FOOTER",
    )
    keldorn_abilities: list[list[bytes]] = []
    for level, scale in enumerate((1, 3, 4, 6), start=1):
        keldorn_abilities.append(
            [
                effect(
                    58,
                    p1=scale,
                    p2=0x20002 if level % 2 else 2,
                    marker=0x80 + level,
                ),
                effect(221, p1=level * 9, resource="KELMARK", marker=0x90 + level),
            ]
        )
    keldorn = make_spl(
        keldorn_abilities,
        minimum_levels=[1, 2, 3, 4],
        projectiles=[157, 157, 157, 157],
        casting_effects=[effect(146, p1=77, resource="SCSHOOK", marker=0xA1)],
        footer=b"KELDORN-FOOTER",
    )
    return {"SPIN112.SPL": yeslick, "SPCL231.SPL": keldorn}


def uai_resources() -> dict[str, bytes]:
    return {
        "SCRLZERO.ITM": make_itm(
            11,
            [[
                effect(146, p1=0, p2=0, resource="SPELLA", marker=0x11),
                effect(148, p1=9, p2=1, resource="SPELLB", marker=0x12),
                effect(12, p1=99, p2=7, resource="DAMAGE", marker=0x13),
            ]],
            footer=b"SCROLL-ZERO",
        ),
        "SCRLFIX.ITM": make_itm(
            11,
            [[
                effect(146, p1=10, p2=0, resource="FIXED", marker=0x21),
                effect(148, p1=12, p2=2, resource="INSTANT", marker=0x22),
            ]],
        ),
        "SCRLALT.ITM": make_itm(
            11,
            [[effect(146, p1=0, p2=0, resource="NOTCAST", marker=0x31)]],
            ability_types=[1],
        ),
        "WANDZERO.ITM": make_itm(
            34,
            [[effect(146, p1=0, p2=0, resource="WAND", marker=0x41)]],
        ),
    }


def slayer_resources() -> dict[str, bytes]:
    resources: dict[str, bytes] = {}
    for number in (2, 3, 4):
        resources[f"SLAYER{number}.SPL"] = make_spl(
            [[
                effect(146, p1=number, p2=8, resource=f"FINSLAY{number}", marker=0x40 + number),
                effect(146, p1=70 + number, p2=9, resource="OTHER", marker=0x50 + number),
                effect(111, p1=80 + number, p2=10, resource=f"FINSLAY{number}", marker=0x60 + number),
            ]],
            projectiles=[33 + number],
            casting_effects=[effect(146, p1=number, resource="CASTHOOK", marker=0x70 + number)],
            footer=f"SLAYER-{number}-FOOTER".encode("ascii"),
        )
        resources[f"SLAYER{number}A.SPL"] = make_spl(
            [[effect(111, p1=1, resource=f"FINSLAY{number}", marker=0x80 + number)]],
            projectiles=[1],
        )
    return resources


FORM_SPELLS = ("SPWI495", "SPWI496", "SPIN152", "SPIN153", "SPIN154")
POLY_ITEMS = (
    "PLYJELLY",
    "PLYSPID",
    "TROLLALL",
    "CDGOLIRO",
    "CDMINDFL",
    "DW-SSBAI",
    "DW-PSHHI",
    "DW-PSRTI",
)


def shapechange_resources() -> dict[str, bytes]:
    resources: dict[str, bytes] = {}
    for index, name in enumerate(FORM_SPELLS):
        resources[f"{name}.SPL"] = make_spl(
            [[
                effect(146, p1=4, p2=6, resource="SPINHUMR", marker=0x20 + index),
                effect(111, p1=1, p2=9, timing=1, duration=777, resource="POLYWEAP", marker=0x30 + index),
                effect(139, p1=1234 + index, p2=5, resource="MESSAGE", marker=0x40 + index),
            ]],
            projectiles=[17 + index],
            casting_effects=[effect(111, p1=99, timing=1, duration=999, resource="CASTONLY", marker=0x50 + index)],
            footer=f"{name}-FOOTER".encode("ascii"),
        )
    for index, name in enumerate(POLY_ITEMS):
        equipped = [effect(335, p1=index, resource="SPINHUM", marker=0x60 + index)]
        if name == "CDMINDFL":
            equipped.append(effect(335, p1=99, resource="SPIN974", marker=0x69))
        if name == "PLYJELLY":
            equipped.append(effect(335, p1=98, resource="UNRELATED", marker=0x68))
        equipped.append(effect(12, p1=200 + index, resource="KEEP", marker=0x70 + index))
        resources[f"{name}.ITM"] = make_itm(
            16,
            [[effect(335, p1=777, resource="ABILITY", marker=0x80 + index)]],
            ability_types=[1],
            equipped_effects=equipped,
            footer=f"{name}-FOOTER".encode("ascii"),
        )
    resources["DW-SSRA.SPL"] = make_spl(
        [[
            effect(321, p1=4, resource="SPINHUMR", marker=0x91),
            effect(321, p1=5, resource="OTHER", marker=0x92),
        ]],
        projectiles=[1],
        casting_effects=[effect(321, p1=6, resource="SPINHUMR", marker=0x93)],
        footer=b"DW-SSRA-FOOTER",
    )
    return resources


class SpellTailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.weidu = find_weidu()

    def require_weidu(self) -> str:
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        return self.weidu

    def install(self, game: SyntheticSpellGame, component: int) -> None:
        result = game.run(self.require_weidu(), "--force-install-list", str(component))
        transcript = game.transcript(result)
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        game.assert_stable_inputs(self)

    def uninstall(self, game: SyntheticSpellGame, component: int) -> None:
        result = game.run(self.require_weidu(), "--force-uninstall-list", str(component))
        transcript = game.transcript(result)
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY REMOVED", transcript)
        self.assertEqual(game.initial_override, file_tree(game.override))
        game.assert_stable_inputs(self)

    def assert_already_patched_is_stable(
        self,
        component: int,
        patched_resources: dict[str, bytes],
    ) -> None:
        with tempfile.TemporaryDirectory(prefix=f"cbm-spell-{component}-idem-") as raw:
            game = SyntheticSpellGame(Path(raw) / "game", patched_resources)
            before = file_tree(game.override)
            self.install(game, component)
            self.assertEqual(before, file_tree(game.override))
            self.uninstall(game, component)

    def test_all_spell_tail_libraries_are_source_only_and_present(self):
        missing = [str(path) for path in LIBRARIES.values() if not path.is_file()]
        self.assertEqual([], missing)
        for path in LIBRARIES.values():
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?i)COPY\s+~[^~]+\.(spl|itm)~")

    def test_400_repairs_only_ability_create_weapon_charges_and_uninstalls(self):
        with tempfile.TemporaryDirectory(prefix="cbm-spell-400-") as raw:
            source = branwen_resources()
            game = SyntheticSpellGame(Path(raw) / "game", source)
            self.install(game, 400)
            transformed = resource_path(game.override, "SPIN113.SPL").read_bytes()
            source_rows = spl_abilities(source["SPIN113.SPL"])
            rows = spl_abilities(transformed)
            self.assertEqual(len(source_rows), len(rows))
            for source_ability, transformed_ability in zip(source_rows, rows):
                source_effects = source_ability["effects"]
                transformed_effects = transformed_ability["effects"]
                for before, after in zip(source_effects, transformed_effects):
                    if opcode(before) == 111:
                        expected = bytearray(before)
                        struct.pack_into("<I", expected, 0x04, 1)
                        self.assertEqual(bytes(expected), after)
                    else:
                        self.assertEqual(before, after)
            self.assertEqual(casting_effects(source["SPIN113.SPL"]), casting_effects(transformed))
            patched = {"SPIN113.SPL": transformed}
            self.uninstall(game, 400)
        self.assert_already_patched_is_stable(400, patched)

    def test_400_fails_closed_when_create_weapon_shape_is_missing(self):
        malformed = {
            "SPIN113.SPL": make_spl([[effect(215, resource="SPROTECT")]])
        }
        with tempfile.TemporaryDirectory(prefix="cbm-spell-400-bad-") as raw:
            game = SyntheticSpellGame(Path(raw) / "game", malformed)
            result = game.run(self.require_weidu(), "--force-install-list", "400")
            transcript = game.transcript(result)
            self.assertIn("NOT INSTALLED DUE TO ERRORS", transcript)
            self.assertEqual(game.initial_override, file_tree(game.override))

    def test_410_rebuilds_yeslick_and_only_retargets_keldorn_then_uninstalls(self):
        with tempfile.TemporaryDirectory(prefix="cbm-spell-410-") as raw:
            source = dispel_resources()
            game = SyntheticSpellGame(Path(raw) / "game", source)
            self.install(game, 410)

            yeslick = resource_path(game.override, "SPIN112.SPL").read_bytes()
            yeslick_rows = spl_abilities(yeslick)
            self.assertEqual(40, len(yeslick_rows))
            source_effects = spl_abilities(source["SPIN112.SPL"])[0]["effects"]
            for level, row in enumerate(yeslick_rows, start=1):
                self.assertEqual(level, row["minimum_level"])
                self.assertEqual(177, row["projectile"])
                effects = row["effects"]
                self.assertEqual(len(source_effects), len(effects))
                for before, after in zip(source_effects, effects):
                    if opcode(before) == 58:
                        expected = bytearray(before)
                        struct.pack_into("<I", expected, 0x04, (level * 3) // 2)
                        struct.pack_into("<I", expected, 0x08, 2)
                        self.assertEqual(bytes(expected), after)
                    else:
                        self.assertEqual(before, after)
            self.assertEqual(casting_effects(source["SPIN112.SPL"]), casting_effects(yeslick))
            self.assertTrue(yeslick.endswith(b"YESLICK-FOOTER"))

            keldorn = resource_path(game.override, "SPCL231.SPL").read_bytes()
            source_rows = spl_abilities(source["SPCL231.SPL"])
            keldorn_rows = spl_abilities(keldorn)
            self.assertEqual(len(source_rows), len(keldorn_rows))
            mutable = {
                int(row["offset"]) + 0x26 + byte_index
                for row in source_rows
                for byte_index in range(2)
            }
            self.assertEqual(
                bytes(value for index, value in enumerate(source["SPCL231.SPL"]) if index not in mutable),
                bytes(value for index, value in enumerate(keldorn) if index not in mutable),
            )
            for before, after in zip(source_rows, keldorn_rows):
                self.assertEqual(157, before["projectile"])
                self.assertEqual(177, after["projectile"])
                self.assertEqual(before["effects"], after["effects"])
            patched = {"SPIN112.SPL": yeslick, "SPCL231.SPL": keldorn}
            self.uninstall(game, 410)
        self.assert_already_patched_is_stable(410, patched)

    def test_410_fails_closed_on_missing_or_ambiguous_dispel_shape(self):
        cases = (
            {"SPIN112.SPL": dispel_resources()["SPIN112.SPL"]},
            {
                "SPIN112.SPL": make_spl(
                    [[effect(58, p1=0, p2=0), effect(58, p1=2, p2=2)]],
                    projectiles=[157],
                ),
                "SPCL231.SPL": dispel_resources()["SPCL231.SPL"],
            },
            {
                "SPIN112.SPL": dispel_resources()["SPIN112.SPL"],
                "SPCL231.SPL": make_spl([[effect(215, resource="NO_DISP")]]),
            },
        )
        for index, resources in enumerate(cases):
            with self.subTest(case=index), tempfile.TemporaryDirectory(
                prefix="cbm-spell-410-bad-"
            ) as raw:
                game = SyntheticSpellGame(Path(raw) / "game", resources)
                result = game.run(self.require_weidu(), "--force-install-list", "410")
                transcript = game.transcript(result)
                self.assertIn("NOT INSTALLED DUE TO ERRORS", transcript)
                self.assertEqual(game.initial_override, file_tree(game.override))

    def assert_dispel_result(self, source: dict[str, bytes], output: dict[str, bytes]):
        before = source["SPIN112.SPL"]
        after = output["SPIN112.SPL"]
        source_rows = spl_abilities(before)
        rows = spl_abilities(after)
        self.assertEqual(40, len(rows))
        for level, row in enumerate(rows, start=1):
            source_row = max(
                (item for item in source_rows if item["minimum_level"] <= level),
                key=lambda item: item["minimum_level"],
            )
            expected_header = bytearray(before[source_row["offset"]:source_row["offset"] + 0x28])
            struct.pack_into("<H", expected_header, 0x10, level)
            struct.pack_into("<H", expected_header, 0x20,
                             struct.unpack_from("<H", after, row["offset"] + 0x20)[0])
            struct.pack_into("<H", expected_header, 0x26, 177)
            self.assertEqual(bytes(expected_header), after[row["offset"]:row["offset"] + 0x28])
            self.assertEqual(len(source_row["effects"]), len(row["effects"]))
            for old_effect, new_effect in zip(source_row["effects"], row["effects"]):
                expected = bytearray(old_effect)
                if opcode(old_effect) == 58:
                    struct.pack_into("<II", expected, 4, level * 3 // 2, 2)
                self.assertEqual(bytes(expected), new_effect)
        self.assertEqual(casting_effects(before), casting_effects(after))
        old_keldorn = source["SPCL231.SPL"]
        expected_keldorn = bytearray(old_keldorn)
        for row in spl_abilities(old_keldorn):
            struct.pack_into("<H", expected_keldorn, row["offset"] + 0x26, 177)
        self.assertEqual(bytes(expected_keldorn), output["SPCL231.SPL"])

    def test_410_handles_casting_first_from_real_weidu_add_spell_cfeffect(self):
        source = dispel_resources()
        ability_effects = spl_abilities(source["SPIN112.SPL"])[0]["effects"]
        empty_casting = bytearray(make_spl([ability_effects], footer=b"REAL-WEIDU-FOOTER"))
        struct.pack_into("<H", empty_casting, 0x6E, 0)
        source["SPIN112.SPL"] = bytes(empty_casting)
        with tempfile.TemporaryDirectory(prefix="cbm-spell-410-cfeffect-") as raw:
            game = SyntheticSpellGame(Path(raw) / "game", source)
            with (game.root / HARNESS.name).open("a", encoding="ascii") as harness:
                harness.write("""
BEGIN ~Add a real WeiDU casting effect~ DESIGNATED 409
COPY_EXISTING ~SPIN112.SPL~ ~override~
  LPF ADD_SPELL_CFEFFECT INT_VAR opcode = 146 target = 1 timing = 1
    STR_VAR resource = ~DW#HOOK~ END
BUT_ONLY
""")
            self.install(game, 409)
            source = file_tree(game.override)
            self.assertEqual(1, len(casting_effects(source["SPIN112.SPL"])))
            ability_offset = struct.unpack_from("<I", source["SPIN112.SPL"], 0x64)[0]
            self.assertEqual(1, struct.unpack_from("<H", source["SPIN112.SPL"], ability_offset + 0x20)[0])
            self.assertEqual(ability_effects, spl_abilities(source["SPIN112.SPL"])[0]["effects"])
            game.initial_override = source
            self.install(game, 410)
            patched = file_tree(game.override)
            self.assert_dispel_result(source, patched)
            self.assertTrue(patched["SPIN112.SPL"].endswith(b"REAL-WEIDU-FOOTER"))
            self.uninstall(game, 410)
        self.assert_already_patched_is_stable(410, patched)

    def test_410_preserves_displaced_tables_casting_order_gaps_and_variable_tiers(self):
        for casting_first in (False, True):
            for effects_first in (False, True):
                for levels in ([0], [1, 7, 19], list(range(1, 41)), list(range(1, 46))):
                    with self.subTest(casting_first=casting_first, effects_first=effects_first, levels=len(levels)):
                        source = dispel_resources()
                        tier_effects = [
                            [effect(58, p1=987, p2=1, marker=0x40 + index)]
                            + [effect(215, resource="KEEP", marker=0xB0 + extra)
                               for extra in range(index % 3)]
                            for index in range(len(levels))
                        ]
                        source["SPIN112.SPL"] = make_spl(
                            tier_effects, minimum_levels=levels,
                            casting_effects=[effect(146, resource="HOOK")], footer=b"YESLICK-FOOTER",
                        )
                        # Keldorn also accepts more than 40 installed tiers.
                        if len(levels) > 40:
                            source["SPCL231.SPL"] = make_spl(
                                [[effect(58, p1=level * 2, p2=0x20002)] for level in levels],
                                minimum_levels=levels, footer=b"KELDORN-FOOTER",
                            )
                        source = {name: rearrange_spl(payload, casting_first=casting_first,
                                                       effects_first=effects_first)
                                  for name, payload in source.items()}
                        with tempfile.TemporaryDirectory(prefix="cbm-spell-410-layout-") as raw:
                            game = SyntheticSpellGame(Path(raw) / "game", source)
                            self.install(game, 410)
                            patched = file_tree(game.override)
                            self.assert_dispel_result(source, patched)
                            before, after = source["SPIN112.SPL"], patched["SPIN112.SPL"]
                            for sentinel in (b"PREFIX-PADDING\x00%marker%\xff", b"BETWEEN-TABLES\x00\xaa\x55",
                                             b"UNREFERENCED-EFFECT-PADDING".ljust(0x30, b"!"),
                                             b"OPAQUE-SLICE-GAP".ljust(0x30, b"?")):
                                self.assertEqual(before.count(sentinel), after.count(sentinel))
                            self.assertTrue(after.endswith(b"YESLICK-FOOTER"))
                            if len(levels) == 40:
                                self.assertEqual(len(before), len(after))
                            else:
                                # All original indexed effect bytes survive expansion,
                                # including unreferenced padding between the slices.
                                old_start = struct.unpack_from("<I", before, 0x6A)[0]
                                new_start = struct.unpack_from("<I", after, 0x6A)[0]
                                old_ends = [struct.unpack_from("<HH", before, row["offset"] + 0x1E)
                                            for row in spl_abilities(before)]
                                old_ends.append((struct.unpack_from("<H", before, 0x70)[0],
                                                 struct.unpack_from("<H", before, 0x6E)[0]))
                                size = max(count + first for count, first in old_ends) * 0x30
                                self.assertEqual(before[old_start:old_start + size], after[new_start:new_start + size])
                            self.uninstall(game, 410)
                        self.assert_already_patched_is_stable(410, patched)

    def test_410_dealiases_shared_ability_and_casting_slices(self):
        for count in (1, 40):
            with self.subTest(ability_count=count):
                source = dispel_resources()
                shared = bytearray(make_spl([[effect(58, p1=73, p2=1)] for _ in range(count)],
                                           footer=b"SHARED-FOOTER"))
                ability_offset = struct.unpack_from("<I", shared, 0x64)[0]
                for index in range(count):
                    struct.pack_into("<H", shared, ability_offset + index * 0x28 + 0x20, 0)
                struct.pack_into("<HH", shared, 0x6E, 0, 1)
                source["SPIN112.SPL"] = bytes(shared)
                with tempfile.TemporaryDirectory(prefix="cbm-spell-410-shared-") as raw:
                    game = SyntheticSpellGame(Path(raw) / "game", source)
                    self.install(game, 410)
                    patched = file_tree(game.override)
                    self.assert_dispel_result(source, patched)
                    self.assertTrue(patched["SPIN112.SPL"].endswith(b"SHARED-FOOTER"))
                    self.uninstall(game, 410)
                self.assert_already_patched_is_stable(410, patched)

    def test_410_copies_binary_percent_sequences_without_expanding_variables(self):
        source = dispel_resources()
        yeslick = bytearray(make_spl([[effect(58), effect(215, resource="%test%")]]))
        header = struct.unpack_from("<I", yeslick, 0x64)[0]
        yeslick[header + 2:header + 8] = b"%test%"
        source["SPIN112.SPL"] = bytes(yeslick)
        with tempfile.TemporaryDirectory(prefix="cbm-spell-410-binary-") as raw:
            game = SyntheticSpellGame(Path(raw) / "game", source)
            harness = game.root / HARNESS.name
            harness.write_text(harness.read_text(encoding="ascii").replace(
                "INCLUDE ~chriz-bg-modpack/lib/cbm_yeslick_keldorn_dispel_fix.tpa~",
                "OUTER_SPRINT test ~WRONG!~\nINCLUDE ~chriz-bg-modpack/lib/cbm_yeslick_keldorn_dispel_fix.tpa~",
            ), encoding="ascii")
            self.install(game, 410)
            patched = file_tree(game.override)
            self.assert_dispel_result(source, patched)
            self.uninstall(game, 410)
        self.assert_already_patched_is_stable(410, patched)

    def test_410_checks_slice_start_capacity_without_rejecting_valid_slice_ends(self):
        for first in (65455, 65456):
            with self.subTest(first=first):
                source = dispel_resources()
                data = bytearray(make_spl([[effect(58), effect(215)]], footer=b"LIMIT-FOOTER"))
                header = struct.unpack_from("<I", data, 0x64)[0]
                effects = struct.unpack_from("<I", data, 0x6A)[0]
                data[effects:effects] = b"\xEE" * (first * 0x30)
                struct.pack_into("<H", data, header + 0x20, first)
                source["SPIN112.SPL"] = bytes(data)
                with tempfile.TemporaryDirectory(prefix="cbm-spell-410-capacity-") as raw:
                    game = SyntheticSpellGame(Path(raw) / "game", source)
                    if first == 65455:
                        self.install(game, 410)
                        patched = file_tree(game.override)
                        self.assert_dispel_result(source, patched)
                        last = spl_abilities(patched["SPIN112.SPL"])[-1]["offset"]
                        self.assertEqual(65535, struct.unpack_from("<H", patched["SPIN112.SPL"], last + 0x20)[0])
                        self.uninstall(game, 410)
                    else:
                        result = game.run(self.require_weidu(), "--force-install-list", "410")
                        self.assertIn("replacement exceeds the effect-index capacity", game.transcript(result))
                        self.assertEqual(game.initial_override, file_tree(game.override))
                        game.assert_stable_inputs(self)
        self.assert_already_patched_is_stable(410, patched)

    def test_410_rejects_malformed_slices_and_ambiguous_thresholds_with_exact_rollback(self):
        cases = []
        for resource in ("SPIN112.SPL", "SPCL231.SPL"):
            for damage in ("header", "ability_table", "huge_ability_offset", "negative_ability_offset",
                           "huge_effect_offset", "negative_effect_offset", "ability_slice",
                           "casting_slice", "overlap", "empty", "duplicate_dispel"):
                source = dispel_resources()
                data = bytearray(source[resource])
                header = struct.unpack_from("<I", data, 0x64)[0]
                effects = struct.unpack_from("<I", data, 0x6A)[0]
                if damage == "header":
                    data = data[:50]
                elif damage == "ability_table":
                    struct.pack_into("<I", data, 0x64, len(data) - 1)
                elif damage in ("huge_ability_offset", "negative_ability_offset"):
                    struct.pack_into("<I", data, 0x64, 0x7FFFFFF0 if damage.startswith("huge") else 0xFFFFFFF0)
                elif damage in ("huge_effect_offset", "negative_effect_offset"):
                    struct.pack_into("<I", data, 0x6A, 0x7FFFFFF0 if damage.startswith("huge") else 0xFFFFFFF0)
                elif damage == "ability_slice":
                    struct.pack_into("<H", data, header + 0x20, 65535)
                elif damage == "casting_slice":
                    struct.pack_into("<HH", data, 0x6E, 65535, 3)
                elif damage == "overlap":
                    struct.pack_into("<I", data, 0x64, effects)
                elif damage == "empty":
                    struct.pack_into("<H", data, header + 0x1E, 0)
                else:
                    count, first = struct.unpack_from("<HH", data, header + 0x1E)
                    for index in range(count):
                        if struct.unpack_from("<H", data, effects + (first + index) * 0x30)[0] != 58:
                            struct.pack_into("<H", data, effects + (first + index) * 0x30, 58)
                            break
                source[resource] = bytes(data)
                cases.append((f"{resource}:{damage}", source))
        for levels in ([2], [1, 1], [1, 7, 3]):
            source = dispel_resources()
            source["SPIN112.SPL"] = make_spl([[effect(58)] for _ in levels], minimum_levels=levels)
            cases.append((str(levels), source))
        for label, source in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory(prefix="cbm-spell-410-invalid-") as raw:
                game = SyntheticSpellGame(Path(raw) / "game", source)
                result = game.run(self.require_weidu(), "--force-install-list", "410")
                self.assertIn("NOT INSTALLED DUE TO ERRORS", game.transcript(result))
                self.assertEqual(game.initial_override, file_tree(game.override))
                game.assert_stable_inputs(self)

    def test_430_rewrites_only_flooring_scroll_cast_effects_and_uninstalls(self):
        with tempfile.TemporaryDirectory(prefix="cbm-spell-430-") as raw:
            source = uai_resources()
            game = SyntheticSpellGame(Path(raw) / "game", source)
            self.install(game, 430)
            transformed = file_tree(game.override)

            rows = itm_effects(transformed["SCRLZERO.ITM"], equipped=False)
            self.assertEqual((15, 0), (p1(rows[0]), p2(rows[0])))
            self.assertEqual((15, 0), (p1(rows[1]), p2(rows[1])))
            self.assertEqual(itm_effects(source["SCRLZERO.ITM"], equipped=False)[2], rows[2])
            for untouched in ("SCRLFIX.ITM", "SCRLALT.ITM", "WANDZERO.ITM"):
                self.assertEqual(source[untouched], transformed[untouched])
            patched = {name: transformed[name] for name in source}
            self.uninstall(game, 430)
        self.assert_already_patched_is_stable(430, patched)

    def test_440_repoints_only_broken_slayer_subspell_links_and_uninstalls(self):
        with tempfile.TemporaryDirectory(prefix="cbm-spell-440-") as raw:
            source = slayer_resources()
            game = SyntheticSpellGame(Path(raw) / "game", source)
            self.install(game, 440)
            patched: dict[str, bytes] = {}
            for number in (2, 3, 4):
                name = f"SLAYER{number}.SPL"
                transformed = resource_path(game.override, name).read_bytes()
                before_rows = spl_abilities(source[name])[0]["effects"]
                after_rows = spl_abilities(transformed)[0]["effects"]
                for before, after in zip(before_rows, after_rows):
                    if opcode(before) == 146 and resref(before) == f"finslay{number}":
                        expected = bytearray(before)
                        expected[0x14:0x1C] = f"slayer{number}a".encode("ascii")
                        self.assertEqual(bytes(expected), after)
                    else:
                        self.assertEqual(before, after)
                self.assertEqual(casting_effects(source[name]), casting_effects(transformed))
                patched[name] = transformed
                subspell = f"SLAYER{number}A.SPL"
                self.assertEqual(
                    source[subspell], resource_path(game.override, subspell).read_bytes()
                )
                patched[subspell] = source[subspell]
            self.uninstall(game, 440)
        self.assert_already_patched_is_stable(440, patched)

    def test_440_fails_closed_when_a_required_subspell_is_missing(self):
        resources = slayer_resources()
        del resources["SLAYER3A.SPL"]
        with tempfile.TemporaryDirectory(prefix="cbm-spell-440-bad-") as raw:
            game = SyntheticSpellGame(Path(raw) / "game", resources)
            result = game.run(self.require_weidu(), "--force-install-list", "440")
            transcript = game.transcript(result)
            self.assertIn("NOT INSTALLED DUE TO ERRORS", transcript)
            self.assertEqual(game.initial_override, file_tree(game.override))

    def test_440_is_transformation_only_and_rejects_ambiguous_link_shapes(self):
        library = LIBRARIES[440].read_text(encoding="utf-8")
        self.assertNotRegex(library.lower(), r"uddoor|\.bcs\b|hasitem")

        cases: list[dict[str, bytes]] = []
        missing_main = slayer_resources()
        del missing_main["SLAYER3.SPL"]
        cases.append(missing_main)

        no_link = slayer_resources()
        no_link["SLAYER2.SPL"] = make_spl(
            [[effect(146, resource="OTHER"), effect(111, resource="FINSLAY2")]]
        )
        cases.append(no_link)

        duplicate_old = slayer_resources()
        duplicate_old["SLAYER2.SPL"] = make_spl(
            [[
                effect(146, resource="FINSLAY2", marker=1),
                effect(146, resource="FINSLAY2", marker=2),
            ]]
        )
        cases.append(duplicate_old)

        duplicate_fixed = slayer_resources()
        duplicate_fixed["SLAYER2.SPL"] = make_spl(
            [[
                effect(146, resource="SLAYER2A", marker=3),
                effect(146, resource="SLAYER2A", marker=4),
            ]]
        )
        cases.append(duplicate_fixed)

        for index, resources in enumerate(cases):
            with self.subTest(case=index), tempfile.TemporaryDirectory(
                prefix="cbm-spell-440-shape-"
            ) as raw:
                game = SyntheticSpellGame(Path(raw) / "game", resources)
                result = game.run(self.require_weidu(), "--force-install-list", "440")
                transcript = game.transcript(result)
                self.assertIn("NOT INSTALLED DUE TO ERRORS", transcript)
                self.assertEqual(game.initial_override, file_tree(game.override))

    def test_450_repairs_only_targeted_effects_and_uninstalls(self):
        with tempfile.TemporaryDirectory(prefix="cbm-spell-450-") as raw:
            source = shapechange_resources()
            game = SyntheticSpellGame(Path(raw) / "game", source)
            self.install(game, 450)
            patched: dict[str, bytes] = {}

            for name in FORM_SPELLS:
                filename = f"{name}.SPL"
                transformed = resource_path(game.override, filename).read_bytes()
                before_rows = spl_abilities(source[filename])[0]["effects"]
                after_rows = spl_abilities(transformed)[0]["effects"]
                for before, after in zip(before_rows, after_rows):
                    if opcode(before) == 111:
                        expected = bytearray(before)
                        expected[0x0C] = 4
                        struct.pack_into("<I", expected, 0x0E, 0)
                        self.assertEqual(bytes(expected), after)
                    else:
                        self.assertEqual(before, after)
                self.assertEqual(casting_effects(source[filename]), casting_effects(transformed))
                patched[filename] = transformed

            for name in POLY_ITEMS:
                filename = f"{name}.ITM"
                transformed = resource_path(game.override, filename).read_bytes()
                before_equipped = itm_effects(source[filename], equipped=True)
                after_equipped = itm_effects(transformed, equipped=True)
                for before, after in zip(before_equipped, after_equipped):
                    if opcode(before) == 335 and resref(before) in {"spinhum", "spin974"}:
                        expected = bytearray(before)
                        expected[0x12] = 0
                        expected[0x13] = 100
                        self.assertEqual(bytes(expected), after)
                    else:
                        self.assertEqual(before, after)
                self.assertEqual(
                    itm_effects(source[filename], equipped=False),
                    itm_effects(transformed, equipped=False),
                )
                patched[filename] = transformed

            revert = resource_path(game.override, "DW-SSRA.SPL").read_bytes()
            before_rows = spl_abilities(source["DW-SSRA.SPL"])[0]["effects"]
            after_rows = spl_abilities(revert)[0]["effects"]
            for before, after in zip(before_rows, after_rows):
                if opcode(before) == 321 and resref(before) == "spinhumr":
                    expected = bytearray(before)
                    expected[0x12] = 0
                    expected[0x13] = 100
                    self.assertEqual(bytes(expected), after)
                else:
                    self.assertEqual(before, after)
            self.assertEqual(casting_effects(source["DW-SSRA.SPL"]), casting_effects(revert))
            patched["DW-SSRA.SPL"] = revert
            self.uninstall(game, 450)
        self.assert_already_patched_is_stable(450, patched)

    def test_450_fails_closed_before_writes_when_required_shape_is_missing(self):
        cases: list[dict[str, bytes]] = []
        missing_revert = shapechange_resources()
        missing_revert["SPIN153.SPL"] = make_spl(
            [[effect(111, p1=1, resource="POLYWEAP")]]
        )
        cases.append(missing_revert)

        split_pair = shapechange_resources()
        split_pair["SPIN153.SPL"] = make_spl(
            [
                [effect(146, resource="SPINHUMR")],
                [effect(111, p1=1, resource="POLYWEAP")],
            ]
        )
        cases.append(split_pair)

        for index, resources in enumerate(cases):
            with self.subTest(case=index), tempfile.TemporaryDirectory(
                prefix="cbm-spell-450-bad-"
            ) as raw:
                game = SyntheticSpellGame(Path(raw) / "game", resources)
                result = game.run(self.require_weidu(), "--force-install-list", "450")
                transcript = game.transcript(result)
                self.assertIn("NOT INSTALLED DUE TO ERRORS", transcript)
                self.assertEqual(game.initial_override, file_tree(game.override))


if __name__ == "__main__":
    unittest.main()
