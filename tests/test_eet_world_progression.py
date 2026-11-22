"""Component 680: EET story-consistent campaign boundaries and SoD backtracking.

Real WeiDU compiles synthetic EET scripts and installs component 680 into
disposable synthetic games (plus overrides, We Overwrite mutations, and corrupt
single-file isolation). No external game paths are touched.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_utility_xp_installer import (
    MOD_NAME,
    ROOT,
    SETUP_NAME,
    WEIDU,
    ONE_EMPTY_STRING_TLK,
    _file_tree,
    _is_weidu_artifact,
    _write_key_and_bif,
)


COMPONENT = 680

IDS_FILES = {
    "ACTION.IDS": """1 ActionOverride(O:Actor*,A:Action*)
30 SetGlobal(S:Name*,S:Area*,I:Value*)
36 Continue()
108 EscapeAreaMove(S:Area*,I:X*,I:Y*,I:Face*DIR)
111 DestroySelf()
244 SaveLocation(S:Area*,S:Global*,P:Point*)
253 ContainerEnable(O:Object,I:Bool*BOOLEAN)
316 SoundActivate(O:Object*,I:State*BOOLEAN)
328 RemoveMapNote(P:Position*,I:STRREF*)
332 AddAreaFlag(I:Type*AREAFLAG)
333 RemoveAreaFlag(I:Type*AREAFLAG)
367 SetWorldmap(S:Worldmap*)
373 AddWorldmapAreaFlag(S:Area*,I:Type*WMPFLAG)
374 RemoveWorldmapAreaFlag(S:Area*,I:Type*WMPFLAG)
394 MoveContainerContents(S:Container1*,S:Container2*)
""",
    "TRIGGER.IDS": """0x400F Global(S:Name*,S:Area*,I:Value*)
0x4018 Range(O:Object*,I:Range*)
0x4023 True()
0x4034 GlobalGT(S:Name*,S:Area*,I:Value*)
0x4035 GlobalLT(S:Name*,S:Area*,I:Value*)
0x4037 StateCheck(O:Object*,I:State*State)
0x4043 InParty(O:Object*)
0x407D IsOverMe(O:Object*)
0x407E AreaCheck(S:ResRef*)
0x4089 OR(I:OrCount*)
0x40A5 Name(S:Name*,O:Object*)
0x40D3 InPartyAllowDead(O:Object*)
0x40E0 NextTriggerObject(O:Object*)
0x40E5 Switch(S:Global*,S:Area*)
""",
    "OBJECT.IDS": "1 Myself\n",
    "BOOLEAN.IDS": "5\n0 FALSE\n1 TRUE\n",
    "WMPFLAG.IDS": "4\n1 VISIBLE\n2 ENABLED\n4 EXPLORABLE\n8 EXPLORED\n",
    "AREAFLAG.IDS": "33\n64 NOTRAVEL\n",
    "STATE.IDS": "IDS V1.0\n0x00000FC0 STATE_REALLY_DEAD\n",
    "DIR.IDS": "IDS\n0 S\n2 SW\n4 W\n6 NW\n8 N\n10 NE\n12 E\n14 SE\n",
}


def make_are(area_type: int = 0) -> bytes:
    buf = bytearray(0x11C)
    buf[0:8] = b"ARE V1.0"
    struct.pack_into("<H", buf, 0x48, area_type)
    return bytes(buf)


def build_wmp(
    areas: list[tuple[str, int, int, int]],
    links: list[tuple[str, int, str, str, int, int]],
    *,
    links_before_areas: bool = False,
) -> bytes:
    """Build a valid WMAP V1.0 binary buffer with explicit N/W/S/E link slots."""
    name_to_idx = {name.upper(): i for i, (name, _, _, _) in enumerate(areas)}
    per_area_dir: list[list[list[bytes]]] = [[[] for _ in range(4)] for _ in areas]
    for src, d, dst, entry, time_h, def_e in links:
        rec = bytearray(0xD8)
        struct.pack_into("<I", rec, 0x00, name_to_idx[dst.upper()])
        eb = entry.encode("ascii")[:32]
        rec[0x04 : 0x04 + len(eb)] = eb
        struct.pack_into("<II", rec, 0x24, time_h, def_e)
        per_area_dir[name_to_idx[src.upper()]][d].append(bytes(rec))

    link_records: list[bytes] = []
    area_records = bytearray()
    for i, (name, flags, x, y) in enumerate(areas):
        arec = bytearray(0xF0)
        nb = name.upper().encode("ascii")[:8]
        arec[0x00 : len(nb)] = nb
        struct.pack_into("<IIII", arec, 0x30, flags, 0, x, y)
        struct.pack_into("<ii", arec, 0x40, -1, -1)
        for j in range(4):
            li = len(link_records)
            nl = len(per_area_dir[i][j])
            struct.pack_into("<II", arec, 0x50 + j * 8, li, nl)
            link_records.extend(per_area_dir[i][j])
        area_records.extend(arec)

    links_blob = b"".join(link_records)
    base = 0x10 + 0xB8
    if links_before_areas:
        lo = base
        ao = base + len(links_blob)
        body = links_blob + bytes(area_records)
    else:
        ao = base
        lo = base + len(area_records)
        body = bytes(area_records) + links_blob

    file_hdr = struct.pack("<8sII", b"WMAPV1.0", 1, 0x10)
    map_hdr = bytearray(0xB8)
    struct.pack_into("<IIII", map_hdr, 0x20, len(areas), ao, lo, len(link_records))
    return file_hdr + bytes(map_hdr) + body


def parse_wmp(data: bytes) -> tuple[list[tuple[str, int, int, int]], dict[tuple[str, int], list[tuple[str, str, int, int]]]]:
    assert data[:8] == b"WMAPV1.0"
    mcnt, moff = struct.unpack_from("<II", data, 0x08)
    assert mcnt >= 1
    na, ao, lo, lc = struct.unpack_from("<IIII", data, moff + 0x20)
    areas = []
    for i in range(na):
        off = ao + i * 0xF0
        name = data[off : off + 8].split(b"\x00", 1)[0].decode("ascii").upper()
        flags, _, x, y = struct.unpack_from("<IIII", data, off + 0x30)
        areas.append((name, flags, x, y))
    edges: dict[tuple[str, int], list[tuple[str, str, int, int]]] = {}
    for i, (src, _, _, _) in enumerate(areas):
        off = ao + i * 0xF0
        for j in range(4):
            li, nl = struct.unpack_from("<II", data, off + 0x50 + j * 8)
            assert li + nl <= lc
            lst = []
            for k in range(nl):
                loff = lo + (li + k) * 0xD8
                tidx = struct.unpack_from("<I", data, loff)[0]
                ent = data[loff + 4 : loff + 0x24].split(b"\x00", 1)[0].decode("ascii")
                t, de = struct.unpack_from("<II", data, loff + 0x24)
                lst.append((areas[tidx][0], ent, t, de))
            edges[(src, j)] = lst
    return areas, edges


SCRIPTS = {
    "BG2600": """IF
  Global("K#NewGame","BG2600",0)
THEN
  RESPONSE #100
    SetGlobal("K#NewGame","BG2600",1)
    RemoveWorldmapAreaFlag("AR0020",ENABLED)
    Continue()
END
""",
    "BDCUT08": """IF
  True()
THEN
  RESPONSE #100
    SetWorldmap("WORLDMAP")
    RemoveWorldmapAreaFlag("BG0100",12)
    RemoveWorldmapAreaFlag("BG0900",12)
END
""",
    "BDDEBUG": """IF
  Global("bd_debug_change_wmp","global",1)
THEN
  RESPONSE #100
    SetGlobal("bd_debug_change_wmp","global",0)
    SetWorldmap("WORLDMAP")
    RemoveWorldmapAreaFlag("BG0100",12)
END
""",
    "AR0602": """IF
  !Global("ENDOFBG1","GLOBAL",0)
  Global("K#NewGame","AR0602",0)
THEN
  RESPONSE #100
    SetGlobal("K#NewGame","AR0602",2)
    RemoveWorldmapAreaFlag("BD0010",15)
    AddWorldmapAreaFlag("AR0020",ENABLED)
END
IF
  Global("ENDOFBG1","GLOBAL",0)
  Global("K#NewGame","AR0602",0)
THEN
  RESPONSE #100
    SetGlobal("K#NewGame","AR0602",1)
    RemoveWorldmapAreaFlag("BG4800",ENABLED)
END
""",
    "AR4000": """IF
  Global("K#NewGame","AR4000",0)
  Global("ENDOFBG1","GLOBAL",0)
THEN
  RESPONSE #100
    SetGlobal("K#NewGame","AR4000",1)
    AddWorldmapAreaFlag("AR4000",EXPLORED)
    RemoveWorldmapAreaFlag("AR0020",ENABLED)
END
""",
    "BD1000": """IF
  Global("K#CleanAreaNote","BD1000",0)
  OR(3)
    GlobalGT("Chapter","GLOBAL",8)
    StateCheck("Baeloth",STATE_REALLY_DEAD)
    InPartyAllowDead("Baeloth")
THEN
  RESPONSE #100
    RemoveMapNote([2000.540],267515)
    SetGlobal("K#CleanAreaNote","BD1000",1)
    Continue()
END
IF
  Global("K#CleanArea","BD1000",0)
  GlobalGT("Chapter","GLOBAL",8)
THEN
  RESPONSE #100
    ActionOverride("BDMIZHEN",DestroySelf())
    ActionOverride("BDBANNO",DestroySelf())
    ActionOverride("BDTCRWD1",DestroySelf())
    SetGlobal("K#CleanArea","BD1000",1)
    Continue()
END
""",
    "BD7100": """IF
  Global("K#CleanArea","BD7100",0)
  GlobalGT("Chapter","GLOBAL",9)
THEN
  RESPONSE #100
    ActionOverride("BDBELEGA",DestroySelf())
    SetGlobal("K#CleanArea","BD7100",1)
    Continue()
END
""",
    "BD2000": """IF
  Global("K#CleanArea","BD2000",0)
  GlobalGT("Chapter","GLOBAL",9)
THEN
  RESPONSE #100
    ActionOverride("BDBENCE",DestroySelf())
    SetGlobal("K#CleanArea","BD2000",1)
    Continue()
END
""",
    "BD2100": """IF
  True()
THEN
  RESPONSE #100
    Continue()
END
""",
    "BD3000": """IF
  Global("bd_plot","global",402)
THEN
  RESPONSE #100
    SetGlobal("bd_plot","global",405)
    RemoveWorldmapAreaFlag("BD5000",6)
    RemoveWorldmapAreaFlag("BD7400",6)
    RemoveWorldmapAreaFlag("BD2000",6)
    RemoveAreaFlag(NOTRAVEL)
END
""",
    "BD4000": """IF
  Global("K#CleanAreaBG2","BD4000",0)
  GlobalGT("Chapter","GLOBAL",13)
THEN
  RESPONSE #100
    RemoveAreaFlag(NOTRAVEL)
    SetGlobal("K#CleanAreaBG2","BD4000",1)
    Continue()
END
IF
  Global("bd_battle","global",1)
THEN
  RESPONSE #100
    AddWorldmapAreaFlag("BD5000",6)
    AddWorldmapAreaFlag("BD7400",6)
    AddWorldmapAreaFlag("BD2000",6)
    AddAreaFlag(NOTRAVEL)
END
""",
    "BDPARTY": """IF
  Global("bd_npc_camp","locals",1)
  Name("minsc",Myself)
  Switch("bd_npc_camp_chapter","global")
  OR(2)
    !Range("ff_camp",999)
    !TriggerOverride("ff_camp",IsOverMe("minsc"))
THEN
  RESPONSE #2
    EscapeAreaMove("bd1000",100,200,E)
  RESPONSE #3
    EscapeAreaMove("bd7100",300,400,NW)
  RESPONSE #4
    EscapeAreaMove("bd3000",500,600,S)
END
IF
  GlobalLT("bd_npc_camp","locals",2)
  Global("bd_joined","locals",0)
  Name("minsc",Myself)
  TriggerOverride("ff_camp",IsOverMe("minsc"))
  Switch("bd_npc_camp_chapter","global")
THEN
  RESPONSE #2
    SetGlobal("bd_npc_camp","locals",2)
    SaveLocation("LOCALS","bd_default_loc",[100.200])
  RESPONSE #3
    SetGlobal("bd_npc_camp","locals",2)
    SaveLocation("LOCALS","bd_default_loc",[300.400])
END
""",
    "BDFIST": """IF
  GlobalGT("Chapter","GLOBAL",13)
THEN
  RESPONSE #100
    DestroySelf()
END
""",
}


def compile_bafs(weidu: Path, root: Path, bafs: dict[str, str]) -> None:
    staging = root / "_baf_stage"
    staging.mkdir(exist_ok=True)
    args = [str(weidu), "--no-auto-tp2", "--noautoupdate", "--no-exit-pause", "--log", str(staging / "weidu.log"), "--game", str(root), "--use-lang", "en_us"]
    for name, text in bafs.items():
        p = staging / f"{name.lower()}.baf"
        p.write_text(text, encoding="utf-8")
        args.append(str(p))
    args.extend(["--out", str(root / "override")])
    res = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=60, check=False)
    out = res.stdout + res.stderr
    assert res.returncode == 0 and "ERROR" not in out, out
    shutil.rmtree(staging)


def decompile_bcs(weidu: Path, root: Path, name: str) -> str:
    with tempfile.TemporaryDirectory(prefix="cbm-ewp-dec-") as td:
        bcs = root / "override" / f"{name.lower()}.bcs"
        res = subprocess.run(
            [str(weidu), "--no-auto-tp2", "--noautoupdate", "--no-exit-pause", "--log", str(Path(td) / "weidu.log"), "--game", str(root), "--use-lang", "en_us", str(bcs), "--out", td],
            cwd=root, capture_output=True, text=True, timeout=60, check=False,
        )
        out = res.stdout + res.stderr
        assert res.returncode == 0 and "ERROR" not in out, out
        return (Path(td) / f"{name.lower()}.baf").read_text(encoding="utf-8")


DEFAULT_AREAS = [
    ("BG0100", 3, 117, 1446),
    ("BG0900", 3, 755, 1492),
    ("BG4800", 3, 949, 2070),
    ("AR10PB", 2, 1600, 1100),   # NTotSC BG1 mod area via table
    ("MODBG1", 2, 1650, 2600),   # Unlisted mod area marked BG1AREA in .ARE
    ("MODNBR", 2, 1700, 2600),   # Unlisted mod area classified by neighbor BG4800 -> BG1
    ("BD1000", 0, 882, 1252),
    ("BD2000", 0, 1059, 1083),
    ("BD3000", 3, 556, 941),
    ("BD4000", 3, 541, 765),
    ("BD5000", 0, 759, 848),
    ("BD7000", 0, 809, 1223),    # Hidden by SoD Remix 210
    ("BD7100", 0, 1059, 1196),
    ("BD7200", 2, 1172, 1116),
    ("BD7300", 0, 589, 852),
    ("BD7400", 0, 831, 931),
    ("WIBH13", 0, 620, 990),     # Blackhearts SoD area linked to BD3000
    ("AR0020", 3, 359, 2502),
    ("AR0700", 3, 172, 2623),
    ("C0AUR1", 2, 410, 2550),    # Aura SoA area
    ("AR3000", 3, 772, 2923),    # Watcher's Keep (SHARED_SOA_TOB)
    ("AR4000", 3, 870, 3007),
    ("AR5203", 0, 1100, 3200),
    ("AR6400", 0, 1306, 3173),
]

DEFAULT_LINKS = [
    ("BG4800", 0, "AR0020", "ExitNE", 8, 1),
    ("BG4800", 0, "MODNBR", "", 2, 1),
    ("AR0020", 0, "BG4800", "CDEastExit", 8, 1),
    ("AR0020", 0, "AR3000", "EXITSW", 5, 4),
    ("BG0900", 0, "BD1000", "ExitSW", 4, 1),
    ("BD1000", 0, "BG0900", "Exit1400", 4, 1),
    ("BD3000", 0, "WIBH13", "ExitW", 2, 1),
    ("BD7400", 0, "BD5000", "EXITNE", 2, 2),
    ("AR3000", 3, "AR0020", "EXITNE", 5, 1),
    ("AR3000", 2, "AR5203", "ExitNE", 2, 1),
    ("AR5203", 2, "AR3000", "ExitW", 2, 5),
]


def stage_eet_game(
    root: Path,
    weidu: Path,
    *,
    game: str = "eet",
    areas=None,
    links=None,
    links_before_areas: bool = False,
    omit_scripts: tuple[str, ...] = (),
    policy_override: str | None = None,
    stale_scripts: bool = False,
    corrupt_target: str | None = None,
) -> Path:
    game_dir = root / "game"
    game_dir.mkdir()
    ov = game_dir / "override"
    ov.mkdir()
    shutil.copy2(ROOT / SETUP_NAME, game_dir / SETUP_NAME)
    shutil.copytree(ROOT / MOD_NAME, game_dir / MOD_NAME)

    marker = {"bg2ee": "OH6000", "eet": "OH6000", "bgee": "OH1000"}[game]
    resources: list[tuple[str, str, bytes]] = [(marker, "ARE", b"synthetic marker")]
    if game == "eet":
        (ov / "eet.flag").write_bytes(b"EET\r\n")
    _write_key_and_bif(game_dir, resources)

    (game_dir / "lang" / "en_us").mkdir(parents=True)
    (game_dir / "lang" / "en_us" / "dialog.tlk").write_bytes(ONE_EMPTY_STRING_TLK)
    (game_dir / "dialog.tlk").write_bytes(ONE_EMPTY_STRING_TLK)

    for ids_name, text in IDS_FILES.items():
        body = text if text.startswith("IDS") else "IDS V1.0\n" + text
        (ov / ids_name.lower()).write_bytes(body.encode("ascii"))
    (ov / "modbg1.are").write_bytes(make_are(0x100))

    wmp_bytes = build_wmp(
        DEFAULT_AREAS if areas is None else areas,
        DEFAULT_LINKS if links is None else links,
        links_before_areas=links_before_areas,
    )
    if corrupt_target == "wmp":
        wmp_bytes = b"BADWMP"
    (ov / "worldmap.wmp").write_bytes(wmp_bytes)

    to_compile = {k: v for k, v in SCRIPTS.items() if k not in omit_scripts}
    if stale_scripts and "BD2100" in to_compile:
        to_compile["BD2100"] = (
            'IF\n  Global("CBM_CleanJegg","BD2100",0)\nTHEN\n  RESPONSE #100\n    Continue()\nEND\n'
            + to_compile["BD2100"]
        )
    if stale_scripts and "BDPARTY" in to_compile:
        to_compile["BDPARTY"] = to_compile["BDPARTY"].replace(
            'OR(2)\n    !Range("ff_camp",999)',
            'OR(3)\n    Global("CBM_OldCamp","MYAREA",1)\n    !Range("ff_camp",999)',
        )
    compile_bafs(weidu, game_dir, to_compile)
    if corrupt_target == "bd2000":
        (ov / "bd2000.bcs").write_bytes(b"CORRUPT")

    if policy_override is not None:
        (ov / "eet_world_progression.2da").write_text(policy_override, encoding="utf-8")

    return game_dir


def run_680(weidu: Path, game_dir: Path, *, uninstall: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(weidu),
            "--no-auto-tp2",
            SETUP_NAME,
            "--game",
            str(game_dir),
            "--force-uninstall-list" if uninstall else "--force-install-list",
            str(COMPONENT),
            "--language",
            "0",
            "--use-lang",
            "en_us",
            "--no-exit-pause",
            "--noautoupdate",
            "--quick-log",
        ],
        cwd=game_dir,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def game_files(game_dir: Path) -> dict[str, bytes]:
    return {k: v for k, v in _file_tree(game_dir).items() if not _is_weidu_artifact(k)}


@unittest.skipUnless(WEIDU, "WeiDU unavailable; set WEIDU or put weidu on PATH")
class EETWorldProgressionTests(unittest.TestCase):
    def test_clean_eet_install_boundaries_sod_fixes_and_byte_exact_uninstall(self) -> None:
        assert WEIDU is not None
        with tempfile.TemporaryDirectory(prefix="cbm-ewp-clean-") as raw:
            game = stage_eet_game(Path(raw), WEIDU)
            before = game_files(game)

            res = run_680(WEIDU, game)
            transcript = res.stdout + res.stderr
            self.assertEqual(0, res.returncode, transcript)
            self.assertIn("SUCCESSFULLY INSTALLED", transcript)

            _, edges = parse_wmp((game / "override" / "worldmap.wmp").read_bytes())
            self.assertNotIn("BG4800", [e[0] for e in edges[("AR0020", 0)]])
            self.assertNotIn("AR0020", [e[0] for e in edges[("BG4800", 0)]])
            self.assertNotIn("BD1000", [e[0] for e in edges[("BG0900", 0)]])
            self.assertNotIn("BG0900", [e[0] for e in edges[("BD1000", 0)]])
            self.assertIn("AR3000", [e[0] for e in edges[("AR0020", 0)]])
            self.assertIn("AR0020", [e[0] for e in edges[("AR3000", 3)]])
            self.assertIn("AR5203", [e[0] for e in edges[("AR3000", 2)]])
            self.assertIn(("BD1000", "EXITSW", 4, 4), edges[("BD7100", 0)])
            self.assertIn(("BD2000", "ExitNW", 10, 15), edges[("BD3000", 0)])
            self.assertIn(("BD3000", "ExitN", 5, 1), edges[("BD7400", 1)])
            self.assertIn(("BD3000", "ExitN", 5, 1), edges[("BD7400", 2)])

            bg2600 = decompile_bcs(WEIDU, game, "BG2600")
            self.assertIn('Global("CBM_EWP_BG1","BG2600",0)', bg2600)
            for out_area in ("BD1000", "WIBH13", "AR0020", "C0AUR1", "AR3000", "AR4000"):
                self.assertIn(f'RemoveWorldmapAreaFlag("{out_area}",15)', bg2600)
            self.assertNotIn('RemoveWorldmapAreaFlag("BG0900",15)', bg2600)
            self.assertNotIn('RemoveWorldmapAreaFlag("MODBG1",15)', bg2600)

            bdcut08 = decompile_bcs(WEIDU, game, "BDCUT08")
            self.assertNotIn(',12)', bdcut08)
            self.assertIn('SetGlobal("CBM_EWP_SOD","GLOBAL",1)', bdcut08)
            for out_area in ("BG0100", "BG0900", "BG4800", "AR10PB", "MODBG1", "MODNBR", "AR0020", "C0AUR1", "AR3000", "AR4000", "BD7000"):
                self.assertIn(f'RemoveWorldmapAreaFlag("{out_area}",15)', bdcut08)
            self.assertIn('AddWorldmapAreaFlag("BD7200",ENABLED)', bdcut08)
            self.assertIn('AddWorldmapAreaFlag("BD3000",3)', bdcut08)
            self.assertIn('AddWorldmapAreaFlag("BD4000",3)', bdcut08)

            ar0602 = decompile_bcs(WEIDU, game, "AR0602")
            for area in ("BG0900", "BG4800", "AR10PB", "BD1000", "BD4000", "WIBH13", "AR4000", "AR5203"):
                self.assertIn(f'RemoveWorldmapAreaFlag("{area}",15)', ar0602)
            self.assertIn('AddWorldmapAreaFlag("AR0020",3)', ar0602)
            self.assertIn('AddWorldmapAreaFlag("AR0700",3)', ar0602)
            self.assertIn('AddWorldmapAreaFlag("AR3000",3)', ar0602)

            ar4000 = decompile_bcs(WEIDU, game, "AR4000")
            for area in ("BG0900", "BG4800", "BD1000", "WIBH13", "AR0020", "AR0700", "C0AUR1"):
                self.assertIn(f'RemoveWorldmapAreaFlag("{area}",15)', ar4000)
            self.assertIn('AddWorldmapAreaFlag("AR4000",3)', ar4000)
            self.assertIn('AddWorldmapAreaFlag("AR3000",3)', ar4000)

            bd4000 = decompile_bcs(WEIDU, game, "BD4000")
            self.assertNotIn("RemoveAreaFlag(NOTRAVEL)", bd4000)
            self.assertNotIn('AddWorldmapAreaFlag("BD5000"', bd4000)
            self.assertNotIn('AddWorldmapAreaFlag("BD7400"', bd4000)
            self.assertNotIn('AddWorldmapAreaFlag("BD2000"', bd4000)
            self.assertIn("AddAreaFlag(NOTRAVEL)", bd4000)

            bd3000 = decompile_bcs(WEIDU, game, "BD3000")
            self.assertNotIn("RemoveWorldmapAreaFlag", bd3000)
            self.assertIn("RemoveAreaFlag(NOTRAVEL)", bd3000)

            bdparty = decompile_bcs(WEIDU, game, "BDPARTY")
            self.assertEqual(1, bdparty.count('Global("CBM_OldCamp","MYAREA",1)'))
            self.assertEqual(1, bdparty.count('Global("CBM_OldCamp","MYAREA",0)'))
            self.assertIn("OR(3)", bdparty)

            bd1000 = decompile_bcs(WEIDU, game, "BD1000")
            self.assertIn('MoveContainerContents("BD1000*PlayerChest00","BD7100*PlayerChest00")', bd1000)
            self.assertIn('ContainerEnable("PlayerChest00",FALSE)', bd1000)
            self.assertIn('GlobalGT("BD_Baeloth_Intro","GLOBAL",5)', bd1000)
            self.assertIn('ActionOverride("BDMIZHEN",DestroySelf())', bd1000)
            k_clean_area = bd1000.split('Global("K#CleanArea","BD1000",0)', 1)[1]
            self.assertNotIn('"BDBANNO"', k_clean_area)
            self.assertNotIn('"BDTCRWD1"', k_clean_area)

            bd7100 = decompile_bcs(WEIDU, game, "BD7100")
            self.assertIn('MoveContainerContents("BD7100*PlayerChest00","BD3000*PlayerChest00")', bd7100)
            self.assertIn('ActionOverride("BDOTILDA",DestroySelf())', bd7100)

            self.assertIn('ActionOverride("BDJEGG",DestroySelf())', decompile_bcs(WEIDU, game, "BD2100"))
            bd2000 = decompile_bcs(WEIDU, game, "BD2000")
            self.assertIn('ActionOverride("BDDUGRAF",DestroySelf())', bd2000)
            self.assertIn('SoundActivate("AM_Distant_Battle",FALSE)', bd2000)
            bdfist = decompile_bcs(WEIDU, game, "BDFIST")
            self.assertIn('AreaCheck("BD1000")', bdfist)
            self.assertIn('AreaCheck("BD7100")', bdfist)

            un = run_680(WEIDU, game, uninstall=True)
            self.assertEqual(0, un.returncode, un.stdout + un.stderr)
            self.assertEqual(before, game_files(game))

    def test_policy_table_overrides_toggle_boundaries_and_keepers(self) -> None:
        assert WEIDU is not None
        override = (
            "2DA V1.0\n*\n"
            "KIND TARGET ARG EXTRA\n"
            "R1 RULE BLOCK_SOD_TO_BG1 0 *\n"
            "R2 RULE WATCHERS_KEEP_IN_SOA 0 *\n"
            "R3 RULE SOD_KEEP_PRE_ASSAULT_OPEN 0 *\n"
            "R4 RULE BLOCK_TOB_TO_SOA 0 *\n"
        )
        with tempfile.TemporaryDirectory(prefix="cbm-ewp-ov-") as raw:
            game = stage_eet_game(Path(raw), WEIDU, policy_override=override)
            res = run_680(WEIDU, game)
            self.assertEqual(0, res.returncode, res.stdout + res.stderr)

            _, edges = parse_wmp((game / "override" / "worldmap.wmp").read_bytes())
            self.assertIn("BG0900", [e[0] for e in edges[("BD1000", 0)]])
            self.assertIn("BD1000", [e[0] for e in edges[("BG0900", 0)]])

            bdcut08 = decompile_bcs(WEIDU, game, "BDCUT08")
            self.assertIn('RemoveWorldmapAreaFlag("BG0100",15)', bdcut08)
            self.assertNotIn('RemoveWorldmapAreaFlag("BG4800",15)', bdcut08)
            bd1000 = decompile_bcs(WEIDU, game, "BD1000")
            self.assertIn('Global("CBM_EWP_SOD_NEW","BD1000",0)', bd1000)
            self.assertIn('RemoveWorldmapAreaFlag("BG4800",15)', bd1000)

            ar0602 = decompile_bcs(WEIDU, game, "AR0602")
            self.assertIn('RemoveWorldmapAreaFlag("AR3000",15)', ar0602)
            ar4000 = decompile_bcs(WEIDU, game, "AR4000")
            self.assertIn('AddWorldmapAreaFlag("AR3000",3)', ar4000)
            self.assertNotIn('RemoveWorldmapAreaFlag("AR0700",15)', ar4000)

            bd3000 = decompile_bcs(WEIDU, game, "BD3000")
            self.assertIn('RemoveWorldmapAreaFlag("BD5000",6)', bd3000)

    def test_we_overwrite_mutations_and_corrupt_files_isolated(self) -> None:
        assert WEIDU is not None
        mutated_links = DEFAULT_LINKS + [
            ("AR0020", 2, "BG4800", "EXTRA", 8, 1),
            ("BD7100", 0, "BD1000", "EXITSW", 4, 4),
        ]
        with tempfile.TemporaryDirectory(prefix="cbm-ewp-mut-") as raw:
            game = stage_eet_game(
                Path(raw),
                WEIDU,
                areas=list(reversed(DEFAULT_AREAS)),
                links=mutated_links,
                links_before_areas=True,
                omit_scripts=("BDDEBUG", "BDFIST"),
                stale_scripts=True,
                corrupt_target="bd2000",
            )
            before = game_files(game)
            res = run_680(WEIDU, game)
            transcript = res.stdout + res.stderr
            self.assertEqual(0, res.returncode, transcript)
            self.assertIn("SUCCESSFULLY INSTALLED", transcript)
            self.assertIn("too damaged to write", transcript)
            self.assertEqual(before["OVERRIDE/BD2000.BCS"], (game / "override" / "bd2000.bcs").read_bytes())

            _, edges = parse_wmp((game / "override" / "worldmap.wmp").read_bytes())
            self.assertNotIn("BG4800", [e[0] for e in edges[("AR0020", 2)]])
            self.assertEqual(1, [e[0] for e in edges[("BD7100", 0)]].count("BD1000"))

            bdparty = decompile_bcs(WEIDU, game, "BDPARTY")
            self.assertEqual(1, bdparty.count('Global("CBM_OldCamp","MYAREA",1)'))
            bd2100 = decompile_bcs(WEIDU, game, "BD2100")
            self.assertEqual(1, bd2100.count('Global("CBM_CleanJegg","BD2100",0)'))

            un = run_680(WEIDU, game, uninstall=True)
            self.assertEqual(0, un.returncode, un.stdout + un.stderr)
            self.assertEqual(before, game_files(game))

        with tempfile.TemporaryDirectory(prefix="cbm-ewp-badwmp-") as raw:
            game = stage_eet_game(Path(raw), WEIDU, corrupt_target="wmp")
            before = game_files(game)
            res = run_680(WEIDU, game)
            self.assertEqual(0, res.returncode, res.stdout + res.stderr)
            self.assertIn("WORLDMAP.WMP is too damaged", res.stdout + res.stderr)
            self.assertEqual(before["OVERRIDE/WORLDMAP.WMP"], (game / "override" / "worldmap.wmp").read_bytes())
            un = run_680(WEIDU, game, uninstall=True)
            self.assertEqual(before, game_files(game))

    def test_non_eet_games_are_skipped_without_changes(self) -> None:
        assert WEIDU is not None
        for game_kind in ("bg2ee", "bgee"):
            with self.subTest(game=game_kind), tempfile.TemporaryDirectory(prefix="cbm-ewp-skip-") as raw:
                game = stage_eet_game(Path(raw), WEIDU, game=game_kind)
                before = game_files(game)
                res = run_680(WEIDU, game)
                self.assertIn("SKIPPING:", res.stdout + res.stderr)
                self.assertEqual(before, game_files(game))


if __name__ == "__main__":
    unittest.main()
