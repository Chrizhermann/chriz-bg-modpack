from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools import build_release


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReleaseBuilderTests(unittest.TestCase):
    def make_source(self, root: Path) -> tuple[Path, Path, list[str]]:
        files = {
            "README.md": b"public readme\n",
            "CHANGELOG.md": b"alpha notes\n",
            "LICENSE": b"MIT\n",
            "THIRD_PARTY_NOTICES.md": b"notices\n",
            "VERSION": b"v0.2.0-alpha.1\n",
            "setup-chriz-bg-modpack.tp2": b"VERSION ~v0.2.0-alpha.1~\n",
            "chriz-bg-modpack/languages/english/setup.tra": b"@190 = ~Sarah~\n",
            "chriz-bg-modpack/lib/example.tpa": b"DEFINE_PATCH_FUNCTION example BEGIN END\n",
        }
        for relative, data in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        weidu_exe = b"synthetic weidu executable"
        weidu_copying = b"GNU GENERAL PUBLIC LICENSE Version 2\n"
        archive = root / "weidu.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("WeiDU-Windows/weidu.exe", weidu_exe)
            output.writestr("WeiDU-Windows/COPYING", weidu_copying)

        manifest = {
            "version": "v0.2.0-alpha.1",
            "archive_basename": "chriz-bg-modpack-v0.2.0-alpha.1",
            "weidu": {
                "version": "251.00",
                "url": "https://example.invalid/official-weidu.zip",
                "archive_sha256": sha256(archive.read_bytes()),
                "exe_path": "WeiDU-Windows/weidu.exe",
                "exe_sha256": sha256(weidu_exe),
                "license_path": "WeiDU-Windows/COPYING",
                "source_url": "https://github.com/WeiDUorg/weidu/tree/v251.00",
            },
            "files": sorted(files),
        }
        manifest_path = root / "release-manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        expected_entries = sorted(
            [
                *files,
                "setup-chriz-bg-modpack.exe",
                "WEIDU-COPYING.txt",
            ]
        )
        return manifest_path, archive, expected_entries

    def test_build_is_deterministic_and_exactly_allowlisted(self):
        with tempfile.TemporaryDirectory(prefix="cbm-release-builder-") as raw_temp:
            root = Path(raw_temp)
            manifest, weidu, expected_entries = self.make_source(root)
            first_dir = root / "dist-one"
            second_dir = root / "dist-two"

            first = build_release.build_release(root, manifest, first_dir, weidu)
            second = build_release.build_release(root, manifest, second_dir, weidu)

            self.assertEqual(first.archive.read_bytes(), second.archive.read_bytes())
            self.assertEqual(sha256(first.archive.read_bytes()), first.sha256)
            self.assertEqual(
                f"{first.sha256}  {first.archive.name}\n",
                first.checksum_file.read_text(encoding="ascii"),
            )

            with zipfile.ZipFile(first.archive) as packaged:
                self.assertEqual(expected_entries, packaged.namelist())
                self.assertEqual(
                    b"synthetic weidu executable",
                    packaged.read("setup-chriz-bg-modpack.exe"),
                )
                self.assertEqual(
                    b"GNU GENERAL PUBLIC LICENSE Version 2\n",
                    packaged.read("WEIDU-COPYING.txt"),
                )
                for info in packaged.infolist():
                    self.assertEqual((1980, 1, 1, 0, 0, 0), info.date_time)
                    self.assertFalse(info.is_dir())
                    self.assertNotEqual(0o120000, (info.external_attr >> 16) & 0o170000)

            content_lines = first.contents_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(expected_entries, [line.split("  ", 2)[2] for line in content_lines])

    def test_unlisted_runtime_file_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="cbm-release-unlisted-") as raw_temp:
            root = Path(raw_temp)
            manifest, weidu, _ = self.make_source(root)
            unexpected = root / "chriz-bg-modpack/portraits/SARAHL.BMP"
            unexpected.parent.mkdir(parents=True)
            unexpected.write_bytes(b"unlicensed portrait")

            with self.assertRaisesRegex(ValueError, r"unlisted runtime file.*SARAHL\.BMP"):
                build_release.build_release(root, manifest, root / "dist", weidu)

    def test_archive_hash_mismatch_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory(prefix="cbm-release-hash-") as raw_temp:
            root = Path(raw_temp)
            manifest_path, weidu, _ = self.make_source(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["weidu"]["archive_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"WeiDU archive SHA-256 mismatch"):
                build_release.build_release(root, manifest_path, root / "dist", weidu)
            self.assertFalse((root / "dist").exists())

    def test_executable_hash_mismatch_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory(prefix="cbm-release-exe-hash-") as raw_temp:
            root = Path(raw_temp)
            manifest_path, weidu, _ = self.make_source(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["weidu"]["exe_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"WeiDU executable SHA-256 mismatch"):
                build_release.build_release(root, manifest_path, root / "dist", weidu)
            self.assertFalse((root / "dist").exists())

    def test_version_identity_mismatch_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory(prefix="cbm-release-version-") as raw_temp:
            root = Path(raw_temp)
            manifest_path, weidu, _ = self.make_source(root)
            (root / "VERSION").write_text("v0.2.0-alpha.2\n", encoding="ascii")

            with self.assertRaisesRegex(ValueError, r"VERSION does not match manifest"):
                build_release.build_release(root, manifest_path, root / "dist", weidu)
            self.assertFalse((root / "dist").exists())

    def test_unsafe_manifest_path_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="cbm-release-path-") as raw_temp:
            root = Path(raw_temp)
            manifest_path, weidu, _ = self.make_source(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"].append("../private.txt")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"unsafe manifest path"):
                build_release.build_release(root, manifest_path, root / "dist", weidu)


if __name__ == "__main__":
    unittest.main()
