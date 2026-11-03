"""Component 670: Marek carries the Boomerang Dagger +2 (DAGG11) in BG1.

Real WeiDU installs the public component into disposable synthetic games. The
creature, area and script fixtures are written here from scratch in the shape
of the BG:EE and EET resources (IESDP CRE V1.0 and ARE V1.0 layouts; the BG1
NPC Project Kivan reward block transcribed from its p#fw3100.baf), and the
scripts are compiled by WeiDU from public IESDP signatures. No game resources
are read or copied, except by the optional test at the end, which uses a
read-only copy of a folder named by CBM_MAREK_RESOURCES.
Run: python -m unittest tests.test_marek_boomerang_dagger -v
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from tests.test_utility_xp_installer import (
    ONE_EMPTY_STRING_TLK, ROOT, SETUP_NAME, MOD_NAME, WEIDU, _file_tree, _is_weidu_artifact,
)

COMPONENT = 670
STREET_KEY = "OVERRIDE/MAREK.CRE"
MAREK1_KEY = "OVERRIDE/MAREK1.CRE"
MAREK_KEY = MAREK1_KEY
MAREK_KEYS = (STREET_KEY, MAREK1_KEY)
TYPES = {"ITM": 1005, "BCS": 1007, "IDS": 1008, "CRE": 1009, "ARE": 1010}
HEADER = 0x2D4
INVENTORY = range(21, 37)
EMPTY = 0xFFFF

# Minimal real engine signatures (ACTION/TRIGGER.IDS), not mocked compilation.
IDS = {
    "action": """0 NoAction()
1 ActionOverride(O:Actor*,A:Action*)
7 CreateCreature(S:NewObject*,P:Location*,I:Face*)
30 SetGlobal(S:Name*,S:Area*,I:Value*)
82 CreateItem(S:ResRef*,I:Usage1*,I:Usage2*,I:Usage3*)
140 GiveItemCreate(S:ResRef*,O:Object*,I:Usage1*,I:Usage2*,I:Usage3*)
269 DisplayStringHead(O:Object*,I:StrRef*)
""",
    "trigger": """0x400F Global(S:Name*,S:Area*,I:Value*)
0x4023 True()
0x4043 InParty(O:Object*)
0x4061 HasItem(S:ResRef*,O:Object*)
""",
    "object": "1 Myself\n21 Player1\n",
    "ea": "",
    "general": "",
    "race": "",
    "class": "",
    "specific": "",
    "gender": "",
    "align": "",
}

# BG1 NPC Project 10's Shipwreck's Coast blocks (p#fw3100.baf, EE variables
# filled in as its installer does), without the cutscene block it also adds.
SEASNAKE = """IF
  Global("X#KivanSea","GLOBAL",0)
  InParty("kivan")
  Global("X#SeasnakeExist","{area}",0)
THEN
  RESPONSE #100
    SetGlobal("X#SeasnakeExist","{area}",1)
    CreateCreature("X#SEASN",[3417.974],3)
END
"""
TREASURE = """IF
  Global("X#KivanSea","GLOBAL",7)
  Global("X#SeaElfTreasure","{area}",0)
THEN
  RESPONSE #100
    SetGlobal("X#SeaElfTreasure","{area}",1)
    ActionOverride("Container1",CreateItem("AMUL11",0,0,0))
    ActionOverride("Container1",CreateItem("DAGG11",0,0,0))
END
"""
# The area's own block and another mod's addition, which mention no dagger.
SHIPWRECK = """IF
  Global("CBMShipwreckIntro","{area}",0)
THEN
  RESPONSE #100
    SetGlobal("CBMShipwreckIntro","{area}",1)
END
"""
# Mentions DAGG11 only in a trigger: this gives nothing.
CHECKS_DAGGER = """IF
  HasItem("DAGG11",Player1)
  Global("CBMDaggerSeen","GLOBAL",0)
THEN
  RESPONSE #100
    SetGlobal("CBMDaggerSeen","GLOBAL",1)
    DisplayStringHead(Player1,1)
END
"""
# A BG2 area script that creates DAGG11 elsewhere: no BG1 source.
ELSEWHERE = """IF
  True()
THEN
  RESPONSE #100
    GiveItemCreate("DAGG11","OHRALOR2",0,0,0)
END
"""


def kivan_quest(area: str) -> str:
    return SHIPWRECK.format(area=area) + SEASNAKE.format(area=area) + TREASURE.format(area=area)


def plain_shipwreck(area: str) -> str:
    return SHIPWRECK.format(area=area)


def item(resref: str, flags: int = 0, charges: tuple[int, int, int] = (0, 0, 0)) -> bytes:
    return struct.pack("<8sHHHHI", resref.encode("ascii"), 0, *charges, flags)


def effect_v1(opcode: int, parameter: int) -> bytes:
    value = bytearray(48)
    struct.pack_into("<HBBII", value, 0, opcode, 1, 0, parameter, 0)
    value[0x14:0x1C] = b"SENTINEL"
    return bytes(value)


def effect_v2(opcode: int, parameter: int) -> bytes:
    value = bytearray(264)
    struct.pack_into("<IIIIII", value, 8, opcode, 1, 0, parameter, 0, 9)
    value[0xA8:0xB0] = b"SENTINEL"
    return bytes(value)


# Both Marek files as shipped in BG:EE: Mage/Thief, Heart of the Golem +2 in
# hand, two bows (the unstealable one in the backpack), arrows, two potions.
# MAREK1, the Blushing Mermaid copy, also has the antidote in the amulet slot.
STREET_ITEMS = [
    (item("BOW08", 2), 21),
    (item("AROW01", 0, (20, 0, 0)), 13),
    (item("DAGG03"), 9),          # weapon 1, selected
    (item("COMPB08"), 10),        # weapon 2
    (item("POTN45"), 18),
    (item("POTN36"), 19),
]
VANILLA_ITEMS = STREET_ITEMS + [(item("POTN47", 0, (10, 0, 0)), 6)]
# SCS (6000/6030/6100) adds random-potion placeholders and potions; Kitpack
# passes and Tweaks only rewrite fields this component does not own.
SCS_ADDS = [
    (item("DW#RND03"), 22),
    (item("DW#RND37"), 24),       # a gap: backpack slot 23 stays free
    (item("POTN34"), 20),
    (item("CLCK06", 1), 17),
]
SCS_ITEMS = VANILLA_ITEMS + SCS_ADDS
SCS_STREET_ITEMS = [(item("DW#HASPT"), 23)] + STREET_ITEMS + SCS_ADDS[:1]

def make_cre(items: list[tuple[bytes, int]], *, scripts: tuple[str, ...] = ("", "", "", "", ""),
             effect_version: int = 0, effects: int = 2, shuffled: bool = False,
             known: int = 3, filler: bool = True) -> bytes:
    """A CRE V1.0 with the item list and slot table placed by offsets, plus
    unrelated spells and effects that must keep their bytes."""
    header = bytearray(((index * 13 + 7) % 251 for index in range(HEADER)) if filler else HEADER)
    header[:8] = b"CRE V1.0"
    header[0x33] = effect_version
    struct.pack_into("<HH", header, 0x24, 49, 49)
    for index, name in enumerate(scripts):
        header[0x248 + index * 8:0x250 + index * 8] = name.encode("ascii").ljust(8, b"\0")
    header[0x280:0x2A0] = b"Marek".ljust(32, b"\0")
    known_spells = b"".join(struct.pack("<8sHH", f"SPWI1{index:02d}".encode(), 0, 1)
                            for index in range(known))
    # Wizard levels 1-9; one memorized level-1 spell. Each level's first index
    # into the memorized list follows the counts before it, as in game files.
    groups = b"".join(struct.pack("<HHHHII", level, 2, 2, 1, 0 if level == 0 else 1,
                                  1 if level == 0 else 0)
                      for level in range(9))
    memorized = struct.pack("<8sI", b"SPWI112", 1)
    effect = effect_v2 if effect_version else effect_v1
    effect_list = b"".join(effect(233 + index, index) for index in range(effects))
    slots = [EMPTY] * 38 + [0, 0]
    for index, (_record, slot) in enumerate(items):
        slots[slot] = index
    blocks = {
        0x2A0: (known_spells, known),
        0x2A8: (groups, 9),
        0x2B0: (memorized, 1),
        0x2B8: (struct.pack("<40H", *slots), None),
        0x2BC: (b"".join(record for record, _slot in items), len(items)),
        0x2C4: (effect_list, effects),
    }
    order = (0x2C4, 0x2B8, 0x2A0, 0x2BC, 0x2B0, 0x2A8) if shuffled else tuple(blocks)
    body = bytearray()
    for pointer in order:
        payload, count = blocks[pointer]
        struct.pack_into("<I", header, pointer, HEADER + len(body))
        if count is not None:
            struct.pack_into("<I", header, pointer + 4, count)
        body.extend(payload)
    return bytes(header + body)


def make_area(script: str) -> bytes:
    header = bytearray(0x11C)
    header[:8] = b"AREAV1.0"
    header[0x94:0x9C] = script.encode("ascii").ljust(8, b"\0")
    return bytes(header)


DAGGER_ITEM = (b"ITM V1  " + bytes(0x72 - 8))


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def items_and_slots(cre: bytes) -> tuple[list[bytes], list[int]]:
    offset, count = u32(cre, 0x2BC), u32(cre, 0x2C0)
    records = [cre[offset + index * 20:offset + index * 20 + 20] for index in range(count)]
    slots = list(struct.unpack_from("<40H", cre, u32(cre, 0x2B8)))
    return records, slots


def blocks_of(cre: bytes) -> dict[str, bytes]:
    """Every indexed block by meaning, independent of its position."""
    version = cre[0x33]
    return {
        "known": cre[u32(cre, 0x2A0):u32(cre, 0x2A0) + u32(cre, 0x2A4) * 12],
        "groups": cre[u32(cre, 0x2A8):u32(cre, 0x2A8) + u32(cre, 0x2AC) * 16],
        "memorized": cre[u32(cre, 0x2B0):u32(cre, 0x2B0) + u32(cre, 0x2B4) * 12],
        "effects": cre[u32(cre, 0x2C4):u32(cre, 0x2C4) + u32(cre, 0x2C8) * (264 if version else 48)],
    }


def with_dagger(cre: bytes) -> tuple[list[bytes], list[int]]:
    """Independent expectation: the original records, then one unidentified,
    droppable DAGG11 in the first free backpack slot; no other slot changes."""
    records, slots = items_and_slots(cre)
    free = next(slot for slot in INVENTORY if slots[slot] == EMPTY)
    slots = list(slots)
    slots[free] = len(records)
    return records + [item("DAGG11")], slots


def weidu(root: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], str]:
    result = subprocess.run(
        [str(WEIDU), "--game", str(root), "--use-lang", "en_us", "--no-exit-pause",
         "--noautoupdate", "--no-auto-tp2", *args],
        cwd=root, capture_output=True, text=True, errors="replace", timeout=90,
    )
    return result, result.stdout + result.stderr


def write_key_and_bif(root: Path, resources: list[tuple[str, str, bytes]]) -> None:
    """KEY V1 and one uncompressed BIFF V1 (IESDP layouts)."""
    bif_path = root / "data" / "cbmmarek.bif"
    bif_path.parent.mkdir(exist_ok=True)
    table_offset = 0x14
    payload_offset = table_offset + len(resources) * 0x10
    table, payloads = bytearray(), bytearray()
    for index, (_resref, extension, payload) in enumerate(resources):
        table.extend(struct.pack("<IIIHH", index, payload_offset + len(payloads),
                                 len(payload), TYPES[extension], 0))
        payloads.extend(payload)
    bif_path.write_bytes(struct.pack("<4s4sIII", b"BIFF", b"V1  ", len(resources), 0,
                                     table_offset) + table + payloads)
    bif_name = b"data\\cbmmarek.bif\0"
    names_offset = 0x18 + 0x0C + len(resources) * 0x0E
    key = bytearray(struct.pack("<4s4sIIII", b"KEY ", b"V1  ", 1, len(resources), 0x18, 0x24))
    key.extend(struct.pack("<IIHH", bif_path.stat().st_size, names_offset, len(bif_name), 0))
    for index, (resref, extension, _payload) in enumerate(resources):
        key.extend(struct.pack("<8sHI", resref.encode("ascii"), TYPES[extension], index))
    key.extend(bif_name)
    (root / "chitin.key").write_bytes(key)


def biff_resource(root: Path, resref: str, extension: str) -> bytes:
    key = (root / "chitin.key").read_bytes()
    _sig, _ver, _nbif, nres, _offbif, offres = struct.unpack_from("<4s4sIIII", key, 0)
    bif = (root / "data" / "cbmmarek.bif").read_bytes()
    for index in range(nres):
        name, rtype, locator = struct.unpack_from("<8sHI", key, offres + index * 14)
        if name.rstrip(b"\0").decode().upper() == resref and rtype == TYPES[extension]:
            _loc, offset, size, _t, _u = struct.unpack_from("<IIIHH", bif, 0x14 + locator * 16)
            return bif[offset:offset + size]
    raise AssertionError(f"{resref}.{extension} is not in the synthetic BIFF")


class MarekGame:
    """A disposable synthetic game with the public installer copied in.

    resources maps RESREF.EXT to bytes, or to BAF text for BCS (compiled here).
    """

    def __init__(self, root: Path, *, game: str = "eet", location: str = "override",
                 resources: dict[str, str | bytes] | None = None, log: str = "") -> None:
        self.root = root
        root.mkdir()
        self.override = root / "override"
        self.override.mkdir()
        shutil.copy2(ROOT / SETUP_NAME, root / SETUP_NAME)
        shutil.copytree(ROOT / MOD_NAME, root / MOD_NAME)
        (root / "lang" / "en_us").mkdir(parents=True)
        (root / "lang" / "en_us" / "dialog.tlk").write_bytes(ONE_EMPTY_STRING_TLK)
        (root / "dialog.tlk").write_bytes(ONE_EMPTY_STRING_TLK)
        (self.override / "foreign.2da").write_bytes(b"foreign resource\x00\xff\r\n")
        if game == "eet":
            (self.override / "eet.flag").write_bytes(b"synthetic EET marker\r\n")
        for name, body in IDS.items():
            (self.override / f"{name}.ids").write_text("IDS V1.0\n" + body)
        if log:
            (root / "weidu.log").write_text(log)
        # GAME_IS uses marker resources; eet.flag additionally selects EET.
        marker = {"eet": "OH6000", "bg2ee": "OH6000", "bgee": "OH1000"}[game]
        biff = [(marker, "ARE", b"synthetic engine marker")]
        write_key_and_bif(root, biff)
        if resources is None:
            resources = default_resources(game)
        for name, body in resources.items():
            resref, extension = name.upper().split(".")
            data = self.compile(resref, body) if isinstance(body, str) else body
            if location == "bif":
                biff.append((resref, extension, data))
            else:
                (self.override / name.lower()).write_bytes(data)
        write_key_and_bif(root, biff)
        self.before = self.files()

    def compile(self, name: str, body: str) -> bytes:
        work = self.root / "fixture-build"
        work.mkdir(exist_ok=True)
        source = work / f"{name.lower()}.baf"
        source.write_text(body)
        result, transcript = weidu(self.root, str(source), "--out", str(work))
        assert result.returncode == 0, transcript
        data = next(p for p in work.iterdir() if p.name.lower() == f"{name.lower()}.bcs").read_bytes()
        shutil.rmtree(work)
        return data

    def files(self) -> dict[str, bytes]:
        return {name: data for name, data in _file_tree(self.root).items()
                if not _is_weidu_artifact(name)}

    def run(self, *, uninstall: bool = False) -> tuple[subprocess.CompletedProcess[str], str]:
        return weidu(self.root, SETUP_NAME, "--language", "0", "--quick-log",
                     "--force-uninstall-list" if uninstall else "--force-install-list",
                     str(COMPONENT))

    def active_log(self) -> str:
        path = next((p for p in self.root.iterdir() if p.name.lower() == "weidu.log"), None)
        if path is None:
            return ""
        return "\n".join(line for line in path.read_text(errors="replace").splitlines()
                         if not line.lstrip().startswith("//"))


def default_resources(game: str, *, marek: bytes | None = None, street: bytes | None = None,
                      quest: bool = False) -> dict[str, str | bytes]:
    area = "BG3100" if game == "eet" else "AR3100"
    return {
        "MAREK.CRE": make_cre(STREET_ITEMS) if street is None else street,
        "MAREK1.CRE": make_cre(VANILLA_ITEMS) if marek is None else marek,
        "DAGG11.ITM": DAGGER_ITEM,
        f"{area}.ARE": make_area(area),
        f"{area}.BCS": kivan_quest(area) if quest else plain_shipwreck(area),
    }


def changed(before: dict[str, bytes], after: dict[str, bytes]) -> set[str]:
    return {name for name in set(before) | set(after) if before.get(name) != after.get(name)}


@unittest.skipUnless(WEIDU, "Set WEIDU to a WeiDU 249+ executable")
class MarekBoomerangDaggerTests(unittest.TestCase):
    def make_game(self, **kwargs) -> MarekGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbm-marek-dagger-")
        self.addCleanup(temporary.cleanup)
        return MarekGame(Path(temporary.name) / "game", **kwargs)

    def install(self, game: MarekGame) -> str:
        result, transcript = game.run()
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotIn("ERROR", transcript)
        # A fresh synthetic game has no WeiDU.log yet; any other warning counts.
        warnings = [line for line in transcript.splitlines()
                    if "WARNING" in line and "parsing log [WeiDU.log]" not in line]
        self.assertEqual([], warnings, transcript)
        self.assertRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        return transcript

    def uninstall(self, game: MarekGame) -> None:
        result, transcript = game.run(uninstall=True)
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY REMOVED", transcript)
        self.assertNotRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")

    def assert_aborted(self, game: MarekGame, message: str) -> None:
        result, transcript = game.run()
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("INSTALLATION ABORTED", transcript)
        self.assertIn(message, transcript)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        self.assertEqual(game.before, game.files())

    def assert_skipped(self, game: MarekGame, message: str) -> None:
        result, transcript = game.run()
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SKIPPING:", transcript)
        self.assertIn(message, transcript)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        self.assertEqual(game.before, game.files())

    def assert_no_op(self, game: MarekGame, message: str) -> str:
        transcript = self.install(game)
        self.assertIn(message, transcript)
        self.assertNotIn("now carries", transcript)
        self.assertEqual(game.before, game.files())
        self.assertFalse(any((game.root / "weidu_external").rglob("MAREK*.CRE")))
        self.uninstall(game)
        self.assertEqual(game.before, game.files())
        return transcript

    def assert_dagger_added(self, original: bytes, patched: bytes) -> None:
        """Exactly one DAGG11 more, unidentified and droppable, in the first
        free backpack slot; everything else by meaning, and the header byte for
        byte apart from the block pointers."""
        records, slots = with_dagger(original)
        self.assertEqual((records, slots), items_and_slots(patched))
        daggers = [record for record in records if record[:8].rstrip(b"\0").upper() == b"DAGG11"]
        self.assertEqual(1, len(daggers))
        self.assertEqual(0, u32(daggers[0], 16) & 8, "never undroppable")
        self.assertEqual(blocks_of(original), blocks_of(patched))
        pointers = {byte for pointer in (0x2A0, 0x2A8, 0x2B0, 0x2B8, 0x2BC, 0x2C0, 0x2C4)
                    for byte in range(pointer, pointer + 4)}
        changed_bytes = {offset for offset in range(HEADER) if original[offset] != patched[offset]}
        self.assertLessEqual(changed_bytes, pointers)
        self.assertEqual(len(original) + 20, len(patched))
        # Every block still lies inside the file, without overlaps.
        spans = [(u32(patched, 0x2B8), u32(patched, 0x2B8) + 80),
                 (u32(patched, 0x2BC), u32(patched, 0x2BC) + u32(patched, 0x2C0) * 20)]
        spans += [(u32(patched, pointer), u32(patched, pointer) + len(block))
                  for pointer, block in zip((0x2A0, 0x2A8, 0x2B0, 0x2C4), blocks_of(patched).values())]
        spans.sort()
        for (_start, end), (next_start, _next_end) in zip(spans, spans[1:]):
            self.assertLessEqual(end, next_start)
        self.assertLessEqual(spans[-1][1], len(patched))

    def assert_both_added(self, game: MarekGame, before: dict[str, bytes] | None = None) -> dict[str, bytes]:
        before = game.before if before is None else before
        installed = game.files()
        self.assertEqual(set(MAREK_KEYS), changed(before, installed))
        for key in MAREK_KEYS:
            with self.subTest(file=key):
                self.assert_dagger_added(before[key], installed[key])
        return installed

    def test_eet_override_both_mareks_install_reinstall_and_restore_bytes(self) -> None:
        game = self.make_game()
        transcript = self.install(game)
        self.assertIn("MAREK.CRE now carries the Boomerang Dagger +2", transcript)
        self.assertIn("MAREK1.CRE now carries the Boomerang Dagger +2", transcript)
        self.assertIn("only one of them can die", transcript)
        installed = self.assert_both_added(game)
        for key in MAREK_KEYS:
            records, slots = items_and_slots(installed[key])
            self.assertEqual(22, slots.index(len(records) - 1), "first free backpack slot")
            self.assertEqual(b"DAGG03", records[slots[9]][:6], "Heart of the Golem +2 stays in his hand")
            self.assertEqual(slots[38:], [0, 0], "weapon selection unchanged")

        self.uninstall(game)
        self.assertEqual(game.before, game.files())
        self.install(game)
        self.assertEqual(installed, game.files())
        # A forced reinstall in one run gives the same bytes again.
        result, transcript = weidu(game.root, SETUP_NAME, "--language", "0", "--quick-log",
                                   "--force-uninstall-list", str(COMPONENT),
                                   "--force-install-list", str(COMPONENT))
        self.assertEqual(0, result.returncode, transcript)
        self.assertEqual(installed, game.files())
        self.uninstall(game)
        self.assertEqual(game.before, game.files())

    def test_bgee_biff_resources_use_ar_areas(self) -> None:
        # BG:EE keeps Marek and Shipwreck's Coast in BIFF archives; installing
        # writes both Marek files to override and uninstalling removes them.
        game = self.make_game(game="bgee", location="bif")
        originals = {key: biff_resource(game.root, key[9:-4], "CRE") for key in MAREK_KEYS}
        self.assertFalse(set(MAREK_KEYS) & set(game.before))
        self.install(game)
        self.assert_both_added(game, {**game.before, **originals})
        self.uninstall(game)
        self.assertEqual(game.before, game.files())

    def test_scs_changed_mareks_keep_every_other_change(self) -> None:
        # SCS-shaped: more items with a gap in the backpack, AI scripts, V2
        # effects and the item list after the other blocks.
        marek = make_cre(SCS_ITEMS, scripts=("DW#MG274", "", "", "DW#MAREK", "DW#MG273"),
                         effect_version=1, effects=5, shuffled=True, known=9)
        street = make_cre(SCS_STREET_ITEMS, scripts=("DW#MG274", "", "", "DW#MAREK", ""),
                          effect_version=1, effects=3, shuffled=True)
        game = self.make_game(resources=default_resources("eet", marek=marek, street=street))
        self.install(game)
        installed = self.assert_both_added(game)
        for key, original, first_free in ((MAREK1_KEY, marek, 23), (STREET_KEY, street, 24)):
            records, slots = items_and_slots(installed[key])
            self.assertEqual(first_free, slots.index(len(records) - 1), "the first gap is used")
            self.assertEqual(original[0x248:0x270], installed[key][0x248:0x270], "scripts unchanged")
        self.uninstall(game)
        self.assertEqual(game.before, game.files())

    def test_other_block_orders_and_effect_versions(self) -> None:
        for shuffled in (False, True):
            for version in (0, 1):
                with self.subTest(shuffled=shuffled, effect_version=version):
                    marek = make_cre(VANILLA_ITEMS, effect_version=version, shuffled=shuffled,
                                     filler=False)
                    street = make_cre(STREET_ITEMS, effect_version=version, shuffled=not shuffled)
                    game = self.make_game(resources=default_resources("eet", marek=marek, street=street))
                    self.install(game)
                    self.assert_both_added(game)

    def test_kivan_quest_already_gives_the_dagger(self) -> None:
        # BG1 NPC Project installed on the BG:EE side before EET: its block is
        # in BG3100.BCS, and this game's WeiDU.log does not mention it.
        game = self.make_game(resources=default_resources("eet", quest=True))
        self.assertEqual("", game.active_log())
        transcript = self.assert_no_op(
            game, "Shipwreck's Coast (BG3100.BCS) already gives the Boomerang Dagger +2")
        self.assertIn("Nothing was changed.", transcript)

    def test_kivan_quest_skips_scs_changed_mareks_too(self) -> None:
        marek = make_cre(SCS_ITEMS, scripts=("DW#MG274", "", "", "DW#MAREK", "DW#MG273"),
                         effect_version=1, shuffled=True)
        street = make_cre(SCS_STREET_ITEMS, effect_version=1)
        game = self.make_game(resources=default_resources("eet", marek=marek, street=street,
                                                          quest=True))
        self.assert_no_op(game, "already gives the Boomerang Dagger +2")

    def test_kivan_quest_on_bgee_and_with_windows_line_endings(self) -> None:
        game = self.make_game(game="bgee", location="bif", resources=default_resources("bgee", quest=True))
        self.assert_no_op(game, "Shipwreck's Coast (AR3100.BCS) already gives the Boomerang Dagger +2")

        game = self.make_game(resources=default_resources("eet", quest=True))
        crlf = game.before["OVERRIDE/BG3100.BCS"].replace(b"\n", b"\r\n")
        (game.override / "bg3100.bcs").write_bytes(crlf)
        game.before = game.files()
        self.assert_no_op(game, "already gives the Boomerang Dagger +2")

    def test_the_script_the_area_names_is_checked(self) -> None:
        # The area file decides which script runs there.
        resources = default_resources("eet")
        resources["BG3100.ARE"] = make_area("CBMSHIP")
        resources["CBMSHIP.BCS"] = kivan_quest("BG3100")
        game = self.make_game(resources=resources)
        self.assert_no_op(game, "Shipwreck's Coast (CBMSHIP.BCS) already gives")

    def test_dagger_mentions_that_give_nothing_in_bg1(self) -> None:
        # A trigger that checks for the dagger, another area's script that
        # creates it, and a WeiDU.log line for BG1 NPC Project without its
        # Shipwreck's Coast block: none of them is a BG1 source.
        resources = default_resources("eet")
        resources["BG3100.BCS"] = plain_shipwreck("BG3100") + CHECKS_DAGGER
        resources["AR3100.BCS"] = ELSEWHERE
        resources["OHRALOR.BCS"] = ELSEWHERE
        game = self.make_game(resources=resources,
                              log="~BG1NPC/BG1NPC.TP2~ #0 #10 // The BG1 NPC Project: v32\n")
        self.install(game)
        self.assert_both_added(game)

    def test_without_shipwrecks_coast_the_dagger_is_added(self) -> None:
        for missing in (("BG3100.ARE", "BG3100.BCS"), ("BG3100.BCS",)):
            with self.subTest(missing=missing):
                resources = default_resources("eet")
                for name in missing:
                    resources.pop(name)
                game = self.make_game(resources=resources)
                self.install(game)
                self.assert_both_added(game)
        # An area without a script runs nothing there either.
        resources = default_resources("eet", quest=True)
        resources["BG3100.ARE"] = make_area("")
        game = self.make_game(resources=resources)
        self.install(game)
        self.assert_both_added(game)

    def test_a_marek_with_the_dagger_already_is_left_unchanged(self) -> None:
        # Only the file without a dagger changes; it never gets a second one.
        marek = make_cre(VANILLA_ITEMS + [(item("dagg11"), 30)])
        game = self.make_game(resources=default_resources("eet", marek=marek))
        transcript = self.install(game)
        self.assertIn("MAREK1.CRE already carries the Boomerang Dagger +2 and was left unchanged",
                      transcript)
        installed = game.files()
        self.assertEqual({STREET_KEY}, changed(game.before, installed))
        self.assert_dagger_added(game.before[STREET_KEY], installed[STREET_KEY])
        self.uninstall(game)
        self.assertEqual(game.before, game.files())

    def test_patched_mareks_are_stable_when_applied_again(self) -> None:
        game = self.make_game()
        self.install(game)
        installed = game.files()
        again = self.make_game(resources=default_resources(
            "eet", marek=installed[MAREK1_KEY], street=installed[STREET_KEY]))
        transcript = self.assert_no_op(again, "MAREK.CRE already carries")
        self.assertIn("MAREK1.CRE already carries", transcript)

    def test_one_missing_marek_is_skipped_with_a_note(self) -> None:
        for missing, present in (("MAREK1", STREET_KEY), ("MAREK", MAREK1_KEY)):
            with self.subTest(missing=missing):
                resources = default_resources("eet")
                resources.pop(f"{missing}.CRE")
                game = self.make_game(resources=resources)
                transcript = self.install(game)
                self.assertIn(f"{missing}.CRE is not in this game and was skipped", transcript)
                installed = game.files()
                self.assertEqual({present}, changed(game.before, installed))
                self.assert_dagger_added(game.before[present], installed[present])
                self.uninstall(game)
                self.assertEqual(game.before, game.files())

    def test_missing_mareks_or_dagger_skip_without_changes(self) -> None:
        resources = default_resources("eet")
        resources.pop("MAREK.CRE")
        resources.pop("MAREK1.CRE")
        self.assert_skipped(self.make_game(game="bg2ee", resources=resources),
                            "MAREK.CRE and MAREK1.CRE are not in this game")
        resources = default_resources("eet")
        resources.pop("DAGG11.ITM")
        self.assert_skipped(self.make_game(resources=resources),
                            "The Boomerang Dagger +2 (DAGG11.ITM) is not in this game")

    def test_full_backpack_aborts_before_either_file_is_written(self) -> None:
        full = [(item("DAGG03", 1), 9)] + [(item(f"POTN{slot:02d}"), slot) for slot in INVENTORY]
        game = self.make_game(resources=default_resources("eet", marek=make_cre(full)))
        self.assert_aborted(game, "MAREK1.CRE has no free backpack slot")
        # A full backpack that already holds the dagger needs no slot.
        with_one = [(item("DAGG11"), 9)] + full[1:]
        game = self.make_game(resources=default_resources("eet", marek=make_cre(with_one)))
        self.install(game)
        self.assertEqual({STREET_KEY}, changed(game.before, game.files()))

    def test_invalid_files_abort_before_either_file_is_written(self) -> None:
        valid = make_cre(VANILLA_ITEMS)
        dangling = bytearray(valid)
        struct.pack_into("<H", dangling, u32(valid, 0x2B8) + 2 * 3, len(VANILLA_ITEMS))
        too_many = bytearray(valid)
        struct.pack_into("<I", too_many, 0x2C0, 1000)
        cases = {
            "not a creature": ("MAREK1.CRE", b"CRE V9.0" + valid[8:], "MAREK1.CRE is not a valid file"),
            "truncated": ("MAREK1.CRE", valid[:0x200], "the file is shorter than a creature header"),
            "items outside": ("MAREK1.CRE", bytes(too_many), "its item list lies outside the file"),
            "effects outside": ("MAREK1.CRE", valid[:-30], "its effect list lies outside the file"),
            "dangling slot": ("MAREK1.CRE", bytes(dangling),
                              "item slot 3 refers to item 7, but the creature has 7 items"),
            "street file": ("MAREK.CRE", b"not a creature", "MAREK.CRE is not a valid file"),
            "area": ("BG3100.ARE", b"AREAV9.9" + bytes(0x200), "BG3100.ARE is not a valid file"),
            "script": ("BG3100.BCS", b"SC\nCR\nCO\n", "BG3100.BCS is not a valid file"),
        }
        for name, (resource, data, message) in cases.items():
            with self.subTest(name=name):
                resources = default_resources("eet")
                resources[resource] = data
                self.assert_aborted(self.make_game(resources=resources), message)

    @unittest.skipUnless(os.environ.get("CBM_MAREK_RESOURCES"), "Optional installed-resource copy")
    def test_read_only_copy_of_installed_resources(self) -> None:
        # A folder with copies of MAREK.CRE, MAREK1.CRE, DAGG11.ITM and Shipwreck's
        # Coast's ARE and BCS from an installed game (with or without BG1 NPC Project).
        source = Path(os.environ["CBM_MAREK_RESOURCES"])
        originals = {p.name.upper(): p.read_bytes() for p in source.iterdir() if p.is_file()}
        game = self.make_game(game="eet" if "BG3100.ARE" in originals else "bgee",
                              resources=dict(originals))
        quest = any(b'"DAGG11"' in data.upper() for name, data in originals.items()
                    if name.endswith(".BCS"))
        transcript = self.install(game)
        if quest:
            self.assertIn("already gives the Boomerang Dagger +2", transcript)
            self.assertEqual(game.before, game.files())
        else:
            present = [key for key in MAREK_KEYS if key[9:] in originals]
            self.assertTrue(present)
            self.assertEqual(set(present), changed(game.before, game.files()))
            for key in present:
                self.assert_dagger_added(originals[key[9:]], game.files()[key])
        self.uninstall(game)
        self.assertEqual(game.before, game.files())
        self.assertEqual(originals, {p.name.upper(): p.read_bytes() for p in source.iterdir() if p.is_file()})


if __name__ == "__main__":
    unittest.main()