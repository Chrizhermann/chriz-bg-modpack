"""Component 135: Dorn's BG1 ambush must not leave the camera locked on Senjak.

Real WeiDU compiles synthetic CUTDN1B/SENJACK scripts (written here from
scratch in the shape of the BG:EE and EET resources, using public IESDP action
and trigger signatures) and installs the public component into disposable
synthetic games. No game resources are read or copied, except by the optional
test at the end, which uses a read-only copy of a folder named by
CBM_DORN_SCRIPTS (CUTDN1B.BCS, SENJACK.BCS and the game's IDS files).
Run: python -m unittest tests.test_dorn_ambush_camera_fix -v
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

from tests.test_utility_xp_installer import (
    ONE_EMPTY_STRING_TLK, ROOT, SETUP_NAME, MOD_NAME, WEIDU, _file_tree, _is_weidu_artifact,
)

COMPONENT = 135
CUT_KEY = "OVERRIDE/CUTDN1B.BCS"
SENJACK_KEY = "OVERRIDE/SENJACK.BCS"
LOCK_HEAD = re.compile(rb"AC\r?\n135OB\r?\n")
RELEASE_BLOCK = (
    'IF !Allegiance(Myself,NEUTRAL) Global("CBM_DornAmbushUnlock","LOCALS",0) '
    'THEN RESPONSE #100 SetGlobal("CBM_DornAmbushUnlock","LOCALS",1) '
    "UnlockScroll() Continue() END"
)
TYPES = {"ARE": 1010, "BCS": 1007, "IDS": 1008}

# Minimal real engine signatures (ACTION/TRIGGER.IDS), not mocked compilation.
IDS = {
    "action": """0 NoAction()
1 ActionOverride(O:Actor*,A:Action*)
23 MoveToPoint(P:Point*)
30 SetGlobal(S:Name*,S:Area*,I:Value*)
36 Continue()
63 Wait(I:Time*)
83 SmallWait(I:Time*)
106 Shout(I:ID*SHOUTIDS)
127 CutSceneId(O:Object*)
131 Kill(O:Object*)
134 AttackReevaluate(O:Target*,I:ReevaluationPeriod*)
135 LockScroll()
136 UnlockScroll()
137 StartDialog(S:DialogFile*,O:Target*)
140 GiveItemCreate(S:ResRef*,O:Object*,I:Usage1*,I:Usage2*,I:Usage3*)
153 ChangeEnemyAlly(O:Object*,I:Value*EA)
229 FaceObject(O:Object*)
269 DisplayStringHead(O:Object*,I:StrRef*)
""",
    "trigger": """0x002F Heard(O:Object*,I:ID*SHOUTIDS)
0x400B Allegiance(O:Object*,I:Allegience*EA)
0x400F Global(S:Name*,S:Area*,I:Value*)
0x401C See(O:Object*)
0x4023 True()
0x4051 Dead(S:Name*)
0x407E AreaCheck(S:ResRef*)
0x4089 OR(I:OrCount*)
""",
    "object": "1 Myself\n12 NearestEnemyOf\n21 Player1\n",
    "ea": "2 PC\n4 ALLY\n128 NEUTRAL\n255 ENEMY\n",
    "shoutids": "",
    "gender": "",
    "general": "",
    "race": "",
    "class": "",
    "specific": "",
    "align": "",
}


def cutscene_block(trigger: str, point: str, dialog: str, lock: str = "LockScroll()\n",
                   extra: str = "") -> str:
    """One CUTDN1B-shaped block: Senjak is the cutscene actor, Dorn kills the
    smugglers, the camera locks on Senjak and Dorn starts the dialogue."""
    return f"""IF
{trigger}
THEN
  RESPONSE #100
    CutSceneId("SENJACK")
    GiveItemCreate("minhp1","DORN",0,0,0)
    Kill("SJMUGG")
    SmallWait(35)
    DisplayStringHead(Myself,28602)
    ActionOverride("SJMUGG2",FaceObject("SJMUGG"))
    Kill("SJMUGG2")
    Wait(2)
    ActionOverride("DORN",MoveToPoint({point}))
    ActionOverride("DORN",FaceObject("SENJACK"))
    ActionOverride("DOROTEA",FaceObject("DORN"))
    FaceObject("DORN")
{extra}    {lock}    ActionOverride("DORN",StartDialog("{dialog}",Player1))
END
"""


def cutscene(prefix: str = "BG", dialog: str = "DORN_", **kwargs) -> str:
    """Both area variants, as in BG:EE (AR####, DORN) and EET (BG####, DORN_)."""
    outside = f'  !AreaCheck("{prefix}5800")\n  !AreaCheck("{prefix}5801")'
    inside = f'  OR(2)\n    AreaCheck("{prefix}5800")\n    AreaCheck("{prefix}5801")'
    return (cutscene_block(outside, "[297.239]", dialog, **kwargs)
            + cutscene_block(inside, "[724.190]", dialog, **kwargs))


SENJACK = """IF
  Global("senjack_combat","GLOBAL",1)
  Allegiance(Myself,NEUTRAL)
THEN
  RESPONSE #100
    UnlockScroll()
    ChangeEnemyAlly(Myself,ENEMY)
    ActionOverride("DORN",ChangeEnemyAlly("DORN",ALLY))
    Shout(111)
END
IF
  Global("senjack_combat","GLOBAL",1)
  !Dead("DORN")
THEN
  RESPONSE #100
    AttackReevaluate("DORN",30)
END
IF
  See(NearestEnemyOf(Myself))
THEN
  RESPONSE #100
    AttackReevaluate(NearestEnemyOf(Myself),30)
END
"""

# Another mod's own additions, which the component must keep.
FOREIGN_BLOCK = """IF
  Global("OtherModAmbush","GLOBAL",0)
THEN
  RESPONSE #100
    SetGlobal("OtherModAmbush","GLOBAL",1)
    Shout(222)
END
"""


def write_key_and_bif(root: Path, resources: list[tuple[str, str, bytes]]) -> None:
    """KEY V1 and one uncompressed BIFF V1 (IESDP layouts)."""
    bif_path = root / "data" / "cbmdorn.bif"
    bif_path.parent.mkdir(exist_ok=True)
    table_offset = 0x14
    payload_offset = table_offset + len(resources) * 0x10
    table, payloads = bytearray(), bytearray()
    for index, (resref, extension, payload) in enumerate(resources):
        table.extend(struct.pack("<IIIHH", index, payload_offset + len(payloads),
                                 len(payload), TYPES[extension], 0))
        payloads.extend(payload)
    bif_path.write_bytes(struct.pack("<4s4sIII", b"BIFF", b"V1  ", len(resources), 0,
                                     table_offset) + table + payloads)
    bif_name = b"data\\cbmdorn.bif\0"
    names_offset = 0x18 + 0x0C + len(resources) * 0x0E
    key = bytearray(struct.pack("<4s4sIIII", b"KEY ", b"V1  ", 1, len(resources), 0x18, 0x24))
    key.extend(struct.pack("<IIHH", bif_path.stat().st_size, names_offset, len(bif_name), 0))
    for index, (resref, extension, _payload) in enumerate(resources):
        key.extend(struct.pack("<8sHI", resref.encode("ascii"), TYPES[extension], index))
    key.extend(bif_name)
    (root / "chitin.key").write_bytes(key)


def weidu(root: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], str]:
    result = subprocess.run(
        [str(WEIDU), "--game", str(root), "--use-lang", "en_us", "--no-exit-pause",
         "--noautoupdate", "--no-auto-tp2", *args],
        cwd=root, capture_output=True, text=True, errors="replace", timeout=90,
    )
    return result, result.stdout + result.stderr


class DornGame:
    """A disposable synthetic game with the public installer copied in."""

    def __init__(self, root: Path, *, game: str = "eet", location: str = "override",
                 cut: str | bytes | None = None, senjack: str | bytes | None = SENJACK,
                 extra: dict[str, str | bytes] | None = None) -> None:
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
        # GAME_IS uses marker resources; eet.flag additionally selects EET.
        marker = {"eet": "OH6000", "bg2ee": "OH6000", "bgee": "OH1000"}[game]
        biff = [(marker, "ARE", b"synthetic engine marker")]
        write_key_and_bif(root, biff)
        scripts = {"CUTDN1B": cutscene() if cut is None else cut, "SENJACK": senjack}
        scripts.update(extra or {})
        for name, body in scripts.items():
            if body is None:
                continue
            data = body if isinstance(body, bytes) else self.compile(name, body)
            if location == "bif":
                biff.append((name, "BCS", data))
            else:
                (self.override / f"{name.lower()}.bcs").write_bytes(data)
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

    def decompile(self, data: bytes) -> str:
        work = self.root / "fixture-decompile"
        work.mkdir(exist_ok=True)
        (work / "probe.bcs").write_bytes(data)
        result, transcript = weidu(self.root, str(work / "probe.bcs"), "--out", str(work))
        assert result.returncode == 0, transcript
        text = next(p for p in work.iterdir() if p.name.lower() == "probe.baf").read_text()
        shutil.rmtree(work)
        return text


def biff_resource(root: Path, resref: str) -> bytes:
    key = (root / "chitin.key").read_bytes()
    _sig, _ver, _nbif, nres, _offbif, offres = struct.unpack_from("<4s4sIIII", key, 0)
    bif = (root / "data" / "cbmdorn.bif").read_bytes()
    for index in range(nres):
        name, rtype, locator = struct.unpack_from("<8sHI", key, offres + index * 14)
        if name.rstrip(b"\0").decode().upper() == resref and rtype == TYPES["BCS"]:
            _loc, offset, size, _t, _u = struct.unpack_from("<IIIHH", bif, 0x14 + locator * 16)
            return bif[offset:offset + size]
    raise AssertionError(f"{resref}.BCS is not in the synthetic BIFF")


def without_locks(data: bytes) -> bytes:
    """Independent expectation: drop each LockScroll() action record, from its
    AC line to the next AC that closes it, and keep every other byte."""
    out, position = bytearray(), 0
    for match in LOCK_HEAD.finditer(data):
        if match.start() < position:
            continue
        end = re.compile(rb"AC\r?\n").search(data, match.end()).end()
        out += data[position:match.start()]
        position = end
    return bytes(out + data[position:])


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def blocks(baf: str) -> list[str]:
    return [squash(block) + " END" for block in re.split(r"(?m)^END\s*$", baf) if block.strip()]


@unittest.skipUnless(WEIDU, "Set WEIDU to a WeiDU 249+ executable")
class DornAmbushCameraFixTests(unittest.TestCase):
    def make_game(self, **kwargs) -> DornGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbm-dorn-ambush-")
        self.addCleanup(temporary.cleanup)
        return DornGame(Path(temporary.name) / "game", **kwargs)

    def install(self, game: DornGame) -> str:
        result, transcript = game.run()
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotIn("ERROR", transcript)
        self.assertRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        return transcript

    def uninstall(self, game: DornGame) -> None:
        result, transcript = game.run(uninstall=True)
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY REMOVED", transcript)
        self.assertNotRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")

    def assert_aborted(self, game: DornGame, message: str) -> None:
        result, transcript = game.run()
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("INSTALLATION ABORTED", transcript)
        self.assertIn(message, transcript)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotRegex(game.active_log(), rf"(?m)#0\s+#{COMPONENT}\b")
        self.assertEqual(game.before, game.files())

    def assert_cutscene_fixed(self, original: bytes, patched: bytes) -> None:
        self.assertTrue(LOCK_HEAD.search(original), "fixture must contain a camera lock")
        self.assertIsNone(LOCK_HEAD.search(patched))
        self.assertEqual(without_locks(original), patched)

    def assert_release_prepended(self, game: DornGame, original: bytes, patched: bytes) -> None:
        # The release block comes first; Senjak's original blocks follow with
        # their exact compiled bytes.
        self.assertTrue(patched.endswith(original.split(b"\n", 1)[1]))
        before, after = blocks(game.decompile(original)), blocks(game.decompile(patched))
        self.assertEqual([squash(RELEASE_BLOCK)] + before, after)

    def test_eet_override_scripts_install_reinstall_and_restore_bytes(self) -> None:
        game = self.make_game()
        cut, senjack = game.before[CUT_KEY], game.before[SENJACK_KEY]
        transcript = self.install(game)
        self.assertIn("Removed 2 camera lock(s)", transcript)
        installed = game.files()
        changed = {k for k in installed if installed[k] != game.before.get(k)}
        self.assertEqual({CUT_KEY, SENJACK_KEY}, changed)
        self.assert_cutscene_fixed(cut, installed[CUT_KEY])
        self.assert_release_prepended(game, senjack, installed[SENJACK_KEY])
        # The original hostility block (unlock, enemy, Dorn ally, shout) is intact.
        after = game.decompile(installed[SENJACK_KEY])
        self.assertIn(squash('IF Global("senjack_combat","GLOBAL",1) Allegiance(Myself,NEUTRAL) '
                             'THEN RESPONSE #100 UnlockScroll() ChangeEnemyAlly(Myself,ENEMY)'),
                      squash(after))

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

    def test_bgee_biff_scripts_use_ar_areas_and_original_dialog(self) -> None:
        # BG:EE keeps both scripts in BIFF archives, with AR#### area names and
        # the original DORN dialog. Installing materializes them in override.
        game = self.make_game(game="bgee", location="bif", cut=cutscene("AR", "DORN"))
        cut = biff_resource(game.root, "CUTDN1B")
        senjack = biff_resource(game.root, "SENJACK")
        self.assertIn(b'"ar5800"', cut.lower())
        self.assertNotIn(CUT_KEY, game.before)
        self.install(game)
        installed = game.files()
        self.assertEqual({CUT_KEY, SENJACK_KEY},
                         {k for k in installed if installed[k] != game.before.get(k)})
        self.assert_cutscene_fixed(cut, installed[CUT_KEY])
        self.assert_release_prepended(game, senjack, installed[SENJACK_KEY])
        self.uninstall(game)
        self.assertEqual(game.before, game.files())

    def test_other_mods_changes_and_every_lock_executor_are_handled(self) -> None:
        foreign_cut = (
            cutscene(extra="    Wait(1)\n    DisplayStringHead(Myself,1)\n")
            + FOREIGN_BLOCK
            # A second lock in one response and one run through ActionOverride.
            + cutscene_block('  Global("OtherModAmbush","GLOBAL",2)', "[1.1]", "DORN_",
                             lock='LockScroll()\n    ActionOverride("DOROTEA",LockScroll())\n')
            # A response whose only action is the lock.
            + 'IF\n  Global("OtherModAmbush","GLOBAL",3)\nTHEN\n  RESPONSE #100\n    LockScroll()\nEND\n'
        )
        foreign_senjack = FOREIGN_BLOCK + SENJACK
        unrelated = "IF\n  True()\nTHEN\n  RESPONSE #100\n    CutSceneId(\"SENJACK\")\n    LockScroll()\nEND\n"
        game = self.make_game(cut=foreign_cut, senjack=foreign_senjack,
                              extra={"CUTDN1A": unrelated})
        cut, senjack = game.before[CUT_KEY], game.before[SENJACK_KEY]
        self.assertEqual(5, len(LOCK_HEAD.findall(cut)))
        transcript = self.install(game)
        self.assertIn("Removed 5 camera lock(s)", transcript)
        installed = game.files()
        self.assertEqual({CUT_KEY, SENJACK_KEY},
                         {k for k in installed if installed[k] != game.before.get(k)})
        self.assert_cutscene_fixed(cut, installed[CUT_KEY])
        self.assert_release_prepended(game, senjack, installed[SENJACK_KEY])
        # Semantically: only the LockScroll() lines are gone; the empty response remains.
        before = [line for line in game.decompile(cut).splitlines() if "LockScroll()" not in line]
        self.assertEqual([squash(line) for line in before if line.strip()],
                         [squash(line) for line in game.decompile(installed[CUT_KEY]).splitlines()
                          if line.strip()])
        self.uninstall(game)
        self.assertEqual(game.before, game.files())

    def test_already_fixed_scripts_install_as_a_no_op(self) -> None:
        game = self.make_game(cut=cutscene(lock=""))
        transcript = self.install(game)
        self.assertIn("CUTDN1B.BCS already has no camera lock", transcript)
        installed = game.files()
        self.assertEqual({SENJACK_KEY}, {k for k in installed if installed[k] != game.before.get(k)})

        # Both scripts already fixed (for example by an earlier installation that
        # is not in this game's log): nothing is written at all.
        done = self.make_game(cut=installed[CUT_KEY], senjack=installed[SENJACK_KEY])
        transcript = self.install(done)
        self.assertIn("already contains this release block", transcript)
        self.assertEqual(done.before, done.files())
        self.assertFalse(any((done.root / "weidu_external").rglob("CUTDN1B.BCS")))

    def test_patched_output_is_stable_when_applied_again(self) -> None:
        game = self.make_game()
        self.install(game)
        installed = game.files()
        again = self.make_game(cut=installed[CUT_KEY], senjack=installed[SENJACK_KEY])
        self.install(again)
        self.assertEqual(again.before, again.files())

    def test_missing_cutscene_skips_without_changes(self) -> None:
        game = self.make_game(cut=b"", senjack=SENJACK)
        (game.override / "cutdn1b.bcs").unlink()
        game.before = game.files()
        result, transcript = game.run()
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SKIPPING:", transcript)
        self.assertIn("CUTDN1B.BCS is not in this game", transcript)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertEqual(game.before, game.files())

    def test_missing_senjack_script_changes_the_cutscene_only(self) -> None:
        game = self.make_game(senjack=None)
        cut = game.before[CUT_KEY]
        transcript = self.install(game)
        self.assertIn("SENJACK.BCS is not in this game, so only the cutscene was changed", transcript)
        installed = game.files()
        self.assertEqual({CUT_KEY}, {k for k in installed if installed[k] != game.before.get(k)})
        self.assert_cutscene_fixed(cut, installed[CUT_KEY])
        self.uninstall(game)
        self.assertEqual(game.before, game.files())

    def test_invalid_scripts_abort_without_changes(self) -> None:
        cases = {
            "not a script": (b"not a compiled script\n", SENJACK, "CUTDN1B.BCS is not a valid compiled script"),
            "truncated": (None, SENJACK, "CUTDN1B.BCS is not a valid compiled script"),
            "senjack": (None, b"SC\nCR\nCO\n", "SENJACK.BCS is not a valid compiled script"),
        }
        for name, (cut, senjack, message) in cases.items():
            with self.subTest(name=name):
                game = self.make_game(senjack=senjack)
                if name == "truncated":
                    data = game.before[CUT_KEY]
                    (game.override / "cutdn1b.bcs").write_bytes(data[: len(data) // 2])
                elif cut is not None:
                    (game.override / "cutdn1b.bcs").write_bytes(cut)
                game.before = game.files()
                self.assert_aborted(game, message)

    def test_unreadable_lock_record_aborts_without_changes(self) -> None:
        game = self.make_game()
        data = game.before[CUT_KEY]
        match = LOCK_HEAD.search(data)
        # Break the record's first object line: the action can no longer be
        # identified as one complete record, so nothing is removed.
        broken = data[:match.end()] + b"0 0\n" + data[match.end():]
        (game.override / "cutdn1b.bcs").write_bytes(broken)
        game.before = game.files()
        self.assert_aborted(game, "CUTDN1B.BCS has 2 LockScroll() action(s), but only 1 could be read")

    def test_windows_line_endings_are_supported(self) -> None:
        game = self.make_game()
        crlf = game.before[CUT_KEY].replace(b"\n", b"\r\n")
        (game.override / "cutdn1b.bcs").write_bytes(crlf)
        game.before = game.files()
        self.install(game)
        patched = game.files()[CUT_KEY]
        self.assert_cutscene_fixed(crlf, patched)
        self.assertNotIn(b"\n", patched.replace(b"\r\n", b""))

    @unittest.skipUnless(os.environ.get("CBM_DORN_SCRIPTS"), "Optional installed-script copy")
    def test_read_only_copy_of_installed_scripts(self) -> None:
        source = Path(os.environ["CBM_DORN_SCRIPTS"])
        originals = {p.name.upper(): p.read_bytes() for p in source.iterdir() if p.is_file()}
        game = self.make_game(cut=originals["CUTDN1B.BCS"], senjack=originals["SENJACK.BCS"])
        for name, data in originals.items():
            if name.endswith(".IDS"):
                (game.override / name.lower()).write_bytes(data)
        game.before = game.files()
        transcript = self.install(game)
        installed = game.files()
        self.assert_cutscene_fixed(originals["CUTDN1B.BCS"], installed[CUT_KEY])
        self.assert_release_prepended(game, originals["SENJACK.BCS"], installed[SENJACK_KEY])
        self.assertIn("Removed 2 camera lock(s)", transcript)
        self.uninstall(game)
        self.assertEqual(game.before, game.files())
        self.assertEqual(originals, {p.name.upper(): p.read_bytes() for p in source.iterdir() if p.is_file()})


if __name__ == "__main__":
    unittest.main()
