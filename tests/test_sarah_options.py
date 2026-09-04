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
TP2 = ROOT / "setup-chriz-bg-modpack.tp2"
ARCHER_TPA = ROOT / "chriz-bg-modpack/lib/cbm_sarah_archer.tpa"
HARNESS = ROOT / "tests/weidu/sarah_archer_harness.tp2"

EFFECT_SIZE = 264
STANDARD_PROFICIENCIES = range(89, 116)
EXPECTED_PROFICIENCIES = {90: 1, 104: 3, 105: 2, 114: 2}
STOCK_PORTRAIT_NAMES = ("SARAHL.BMP", "SARAHM.BMP", "SARAHS.BMP")
ONE_EMPTY_STRING_TLK = (
    struct.pack("<8sHII", b"TLK V1  ", 0, 1, 0x2C)
    + struct.pack("<H8siiII", 0, b"\0" * 8, 0, 0, 0, 0)
)


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def make_effect(opcode_value: int, parameter1: int, parameter2: int, seed: int) -> bytes:
    """Build a deterministic embedded EFF V2 record without game-owned bytes."""
    effect = bytearray(EFFECT_SIZE)
    effect[:8] = b"EFF V2.0"
    struct.pack_into("<I", effect, 0x08, opcode_value)
    struct.pack_into("<I", effect, 0x14, parameter1)
    struct.pack_into("<I", effect, 0x18, parameter2)
    effect[0x20:0x28] = f"CBM{seed:05d}".encode("ascii")[:8]
    effect[0x100:0x108] = bytes(((seed + index) & 0xFF) for index in range(8))
    return bytes(effect)


def make_sarah_cre(seed: int) -> bytes:
    """Generate a structurally valid synthetic Sarah-shaped CRE V1.0 fixture."""
    header = bytearray(0x2D4)
    header[:8] = b"CRE V1.0"
    header[0x08:0x10] = bytes(((seed + index) & 0xFF) for index in range(8))
    header[0x33] = 1  # embedded effects are EFF V2
    header[0x34:0x3C] = b"SARAHS\0\0"
    header[0x3C:0x44] = b"SARAHM\0\0"
    header[0x52] = 11 + seed  # THAC0 sentinel; the conversion must preserve it
    header[0x273] = 12  # RANGER
    struct.pack_into("<I", header, 0x244, 0x40000000)  # TRUECLASS
    header[0x280:0x287] = b"K#SARAH"

    effects_offset = len(header)
    effects = [
        make_effect(326, 19 + seed, 105, seed),
        make_effect(233, 2, 104, seed + 10),
        make_effect(233, 2, 90, seed + 20),
        make_effect(233, 2, 111, seed + 30),
        make_effect(233, 2, 114, seed + 40),
        make_effect(233, 7, 152, seed + 50),
    ]

    item_slots = b"\xff" * 80
    item_slots_offset = effects_offset + (len(effects) * EFFECT_SIZE)
    for offset in (0x2A0, 0x2A8, 0x2B0):
        struct.pack_into("<I", header, offset, effects_offset)
    struct.pack_into("<I", header, 0x2BC, item_slots_offset)
    struct.pack_into("<I", header, 0x2B8, item_slots_offset)
    struct.pack_into("<I", header, 0x2C4, effects_offset)
    struct.pack_into("<I", header, 0x2C8, len(effects))
    return bytes(header) + b"".join(effects) + item_slots


def effect_records(data: bytes) -> list[bytes]:
    offset = u32(data, 0x2C4)
    count = u32(data, 0x2C8)
    end = offset + count * EFFECT_SIZE
    if len(data) < 0x2D4 or end > len(data):
        raise AssertionError("invalid CRE V1.0 effect table")
    return [
        data[start : start + EFFECT_SIZE]
        for start in range(offset, end, EFFECT_SIZE)
    ]


def opcode(record: bytes) -> int:
    return u32(record, 0x08)


def proficiency_map(data: bytes) -> dict[int, int]:
    result: dict[int, int] = {}
    for record in effect_records(data):
        if opcode(record) == 233:
            value = u32(record, 0x14)
            stat = u32(record, 0x18)
            if stat in STANDARD_PROFICIENCIES:
                if stat in result:
                    raise AssertionError(f"duplicate proficiency effect for stat {stat}")
                result[stat] = value
    return result


def unrelated_effects(data: bytes) -> list[bytes]:
    records = []
    for record in effect_records(data):
        is_standard_prof = (
            opcode(record) == 233
            and u32(record, 0x18) in STANDARD_PROFICIENCIES
        )
        if not is_standard_prof:
            records.append(record)
    return records


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


def write_marker_key_and_bif(game_root: Path) -> Path:
    """Create the smallest KEY/BIFF pair needed for BG2EE game detection."""
    payload = b"synthetic BG2EE marker"
    bif_relative = Path("DATA/CBMTEST.BIF")
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
        struct.pack(
            "<IIHH",
            bif_path.stat().st_size,
            names_offset,
            len(encoded_name),
            0,
        )
    )
    key.extend(struct.pack("<8sHI", b"OH6000\0\0", 1010, 0))
    key.extend(encoded_name)
    (game_root / "chitin.key").write_bytes(key)
    return bif_path


class SyntheticSarahGame:
    def __init__(self, temporary: tempfile.TemporaryDirectory[str], *, complete: bool):
        self.root = Path(temporary.name) / "game"
        self.root.mkdir()
        self.override = self.root / "override"
        self.override.mkdir()

        shutil.copy2(TP2, self.root / TP2.name)
        shutil.copytree(ROOT / "chriz-bg-modpack", self.root / "chriz-bg-modpack")
        (self.override / "K#SARAH.CRE").write_bytes(make_sarah_cre(1))
        if complete:
            (self.override / "K#SARAH1.CRE").write_bytes(make_sarah_cre(2))
        for filename in STOCK_PORTRAIT_NAMES:
            (self.override / filename).write_bytes(f"stock sentinel {filename}".encode())

        self.bif = write_marker_key_and_bif(self.root)
        self.lang_tlk = self.root / "lang/en_US/dialog.tlk"
        self.lang_tlk.parent.mkdir(parents=True)
        self.lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.root_tlk = self.root / "dialog.tlk"
        self.root_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.initial_override = file_tree(self.override)
        self.stable_hashes = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                self.root / "chitin.key",
                self.bif,
                self.lang_tlk,
                self.root_tlk,
            )
        }

    def run(self, weidu: str, operation: str, component: int):
        return subprocess.run(
            [
                weidu,
                TP2.name,
                "--no-auto-tp2",
                "--game",
                str(self.root),
                operation,
                str(component),
                "--language",
                "0",
                "--use-lang",
                "en_US",
                "--no-exit-pause",
                "--quick-log",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )

    def transcript(self, result: subprocess.CompletedProcess[str]) -> str:
        return result.stdout + result.stderr

    def active_log(self) -> str:
        log = self.root / "WeiDU.log"
        if not log.exists():
            return ""
        return "\n".join(
            line
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines()
            if not line.lstrip().startswith("//")
        )

    def assert_stable_inputs(self, testcase: unittest.TestCase) -> None:
        for path, expected_hash in self.stable_hashes.items():
            testcase.assertEqual(
                expected_hash,
                hashlib.sha256(path.read_bytes()).hexdigest(),
                f"installer changed synthetic input {path}",
            )


class SarahArcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.weidu = find_weidu()

    def test_archer_reads_the_full_cre_effect_count_dword(self):
        source = ARCHER_TPA.read_text(encoding="utf-8")
        self.assertIn("READ_LONG 0x2c8", source)
        self.assertNotIn("READ_SHORT 0x2c8", source)

    def transform(self, source: bytes, *, expect_success: bool = True):
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        with tempfile.TemporaryDirectory(prefix="cbm-sarah-") as raw_temp:
            run_dir = Path(raw_temp)
            harness_path = run_dir / HARNESS.name
            source_path = run_dir / "source.cre"
            output_path = run_dir / "output.cre"
            shutil.copyfile(HARNESS, harness_path)
            source_path.write_bytes(source)
            command = [
                self.weidu,
                harness_path.name,
                "--no-auto-tp2",
                "--nogame",
                "--force-install-list",
                "1",
                "--args",
                ARCHER_TPA.as_posix(),
                "--args",
                source_path.as_posix(),
                "--args",
                output_path.as_posix(),
                "--no-exit-pause",
                "--quick-log",
            ]
            result = subprocess.run(
                command,
                cwd=run_dir,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            transcript = result.stdout + result.stderr
            if expect_success:
                self.assertEqual(0, result.returncode, transcript)
                self.assertTrue(output_path.is_file(), transcript)
                return output_path.read_bytes(), transcript
            self.assertNotEqual(0, result.returncode, transcript)
            self.assertFalse(output_path.exists(), transcript)
            return None, transcript

    def test_both_sarah_variants_receive_exact_archer_build(self):
        for seed in (1, 2):
            with self.subTest(seed=seed):
                source = make_sarah_cre(seed)
                transformed, _ = self.transform(source)

                self.assertEqual(b"CRE V1.0", transformed[:8])
                self.assertEqual(12, transformed[0x273])
                self.assertEqual(0x40070000, u32(transformed, 0x244))
                self.assertEqual(EXPECTED_PROFICIENCIES, proficiency_map(transformed))
                self.assertEqual(8, sum(proficiency_map(transformed).values()))
                self.assertEqual(unrelated_effects(source), unrelated_effects(transformed))

                source_effect_offset = u32(source, 0x2C4)
                transformed_effect_offset = u32(transformed, 0x2C4)
                self.assertEqual(source_effect_offset, transformed_effect_offset)
                self.assertEqual(u32(source, 0x2C8), u32(transformed, 0x2C8))
                self.assertEqual(len(source), len(transformed))

                source_prefix = bytearray(source[:source_effect_offset])
                transformed_prefix = bytearray(transformed[:transformed_effect_offset])
                source_prefix[0x246:0x248] = b"\0\0"
                transformed_prefix[0x246:0x248] = b"\0\0"
                self.assertEqual(source_prefix, transformed_prefix)

                source_end = source_effect_offset + u32(source, 0x2C8) * EFFECT_SIZE
                transformed_end = (
                    transformed_effect_offset
                    + u32(transformed, 0x2C8) * EFFECT_SIZE
                )
                self.assertEqual(source[source_end:], transformed[transformed_end:])

    def test_archer_patch_is_byte_idempotent(self):
        source = make_sarah_cre(1)
        first, _ = self.transform(source)
        second, _ = self.transform(first)
        self.assertEqual(first, second)

    def test_archer_patch_rejects_non_ranger(self):
        source = bytearray(make_sarah_cre(1))
        source[0x273] = 2
        _, transcript = self.transform(bytes(source), expect_success=False)
        self.assertIn("expected Ranger class", transcript)

    def test_archer_patch_rejects_unexpected_ranger_kit(self):
        source = bytearray(make_sarah_cre(1))
        struct.pack_into("<H", source, 0x246, 0x4001)
        _, transcript = self.transform(bytes(source), expect_success=False)
        self.assertIn("unexpected Ranger kit", transcript)


class SarahPublicInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.weidu = find_weidu()

    def make_game(self, *, complete: bool = True) -> SyntheticSarahGame:
        if self.weidu is None:
            self.skipTest("WeiDU 249+ not available; set WEIDU_BIN")
        temporary = tempfile.TemporaryDirectory(prefix="cbm-sarah-game-")
        self.addCleanup(temporary.cleanup)
        return SyntheticSarahGame(temporary, complete=complete)

    def assert_installed(self, game: SyntheticSarahGame, result, component: int):
        transcript = game.transcript(result)
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertRegex(game.active_log(), rf"(?m)#0\s+#{component}\b")
        game.assert_stable_inputs(self)

    def test_archer_component_installs_and_uninstalls_exactly(self):
        game = self.make_game()

        archer_install = game.run(self.weidu, "--force-install-list", 190)
        self.assert_installed(game, archer_install, 190)
        for filename in ("K#SARAH.CRE", "K#SARAH1.CRE"):
            transformed = (game.override / filename).read_bytes()
            self.assertEqual(0x40070000, u32(transformed, 0x244))
            self.assertEqual(EXPECTED_PROFICIENCIES, proficiency_map(transformed))
        for filename, sentinel in game.initial_override.items():
            if filename.endswith(".BMP"):
                self.assertEqual(sentinel, (game.override / filename).read_bytes())

        archer_uninstall = game.run(self.weidu, "--force-uninstall-list", 190)
        self.assertEqual(0, archer_uninstall.returncode, game.transcript(archer_uninstall))
        self.assertNotRegex(game.active_log(), r"(?m)#0\s+#190\b")
        self.assertEqual(game.initial_override, file_tree(game.override))
        game.assert_stable_inputs(self)

    def test_missing_second_cre_skips_without_writes(self):
        game = self.make_game(complete=False)
        result = game.run(self.weidu, "--force-install-list", 190)
        transcript = game.transcript(result)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertIn("K#SARAH1.CRE", transcript)
        self.assertIn("missing", transcript)
        self.assertNotRegex(game.active_log(), r"(?m)#0\s+#190\b")
        self.assertEqual(game.initial_override, file_tree(game.override))
        game.assert_stable_inputs(self)


class SarahInstallerMetadataTests(unittest.TestCase):
    def test_archer_is_recommended_and_private_portrait_slot_is_reserved(self):
        tp2 = TP2.read_text(encoding="utf-8")
        self.assertIn("BEGIN @190 DESIGNATED 190", tp2)
        self.assertIn("LABEL ~cbm_sarah_archer~", tp2)
        self.assertIn("INCLUDE ~chriz-bg-modpack/lib/cbm_sarah_archer.tpa~", tp2)
        self.assertNotIn("BEGIN @191", tp2)
        self.assertNotIn("LABEL ~cbm_sarah_portrait~", tp2)
        self.assertNotIn("cbm_sarah_portrait.tpa", tp2)

        archer_block = tp2.split("BEGIN @190", 1)[1].split("BEGIN @192", 1)[0]
        self.assertNotIn("cbm_sarah_portrait", archer_block.lower())
        self.assertNotIn("SARAHL.BMP", archer_block)

        tra = (
            ROOT / "chriz-bg-modpack/languages/english/setup.tra"
        ).read_text(encoding="utf-8")
        self.assertRegex(tra, r"@190\s*=.*recommended")
        self.assertNotRegex(tra, r"(?m)^@191\s*=")

    def test_archer_component_guards_both_sarah_resources(self):
        tp2 = TP2.read_text(encoding="utf-8")
        block = tp2.split("BEGIN @190", 1)[1].split("BEGIN @192", 1)[0]
        self.assertIn("FILE_EXISTS_IN_GAME ~K#SARAH.CRE~", block)
        self.assertIn("FILE_EXISTS_IN_GAME ~K#SARAH1.CRE~", block)


if __name__ == "__main__":
    unittest.main()
