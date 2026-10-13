"""Copy the reviewed banking candidate into the mod; never run a game or build.

Research Lua/menu sources remain canonical; text mirrors use repository LF EOLs.
Native DLLs must match the supplied
offline bundle manifest. --check needs no bundle and detects source/package drift.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path("chriz-bg-modpack/campaign-xp")
NATIVE = {
    "cbmbank_identity.dll", "dual_hp_observer.dll", "dual_native_proficiency.dll",
    "dual_prof_commit.dll", "dual_skill_rows.dll", "dual_old_hla.dll",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError(f"Unsafe manifest path: {name}")
    return path


def sync(bundle: Path, root: Path = ROOT) -> dict:
    manifest = json.loads((bundle / "research-build.json").read_text(encoding="utf-8-sig"))
    assert manifest.get("researchOnly") is True, "Expected the offline candidate manifest"
    selected = manifest["files"]
    assert {n for n in selected if n.endswith(".dll")} == NATIVE, "Unexpected native DLL set"
    planned = {}
    for name, expected in selected.items():
        path = relative(name)
        if name in NATIVE:
            data = (bundle / path).read_bytes()
            assert digest(data) == expected, f"Native bundle checksum mismatch: {name}"
            planned[f"native/{name}"] = (data, {"kind": "native", "sha256": expected})
        elif name.startswith(("xp-banking/", "xp-banking-native/")) and path.suffix == ".lua":
            source = Path("research") / path
            planned[f"runtime/{name}"] = (source_bytes(root / source), {"source": source.as_posix()})
        elif name == "resources/CBMDOLD.menu":
            source = Path("research/xp-banking-native/dual_retired_menu.menu")
            planned["cbmdold.menu"] = (source_bytes(root / source), {"source": source.as_posix()})
        elif name != "resources/M_CBMBNK.lua":
            raise ValueError(f"Unreviewed bundle entry: {name}")
    source = Path("research/xp-banking-native/bank_recruitment_patch.tpa")
    planned["bank_recruitment_patch.tpa"] = (source_bytes(root / source), {"source": source.as_posix()})
    assert "runtime/xp-banking-native/bank_notice.lua" in planned, "Bundle selection lacks notice integration"
    assert "runtime/xp-banking-native/bank_record.lua" in planned, "Bundle selection lacks record display integration"
    package = root / PACKAGE
    records = {}
    for name, (data, record) in sorted(planned.items()):
        destination = package / relative(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        records[name] = {**record, "sha256": digest(data)}
    result = {"schema": 1, "status": "experimental-unreleased", "nativePlaytestRequired": True,
              "files": records}
    (package / "package-manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    check(root)
    return result


def check(root: Path = ROOT) -> dict:
    package = root / PACKAGE
    manifest = json.loads((package / "package-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == 1 and manifest["nativePlaytestRequired"] is True
    actual_native = set()
    for name, record in manifest["files"].items():
        data = (package / relative(name)).read_bytes()
        assert digest(data) == record["sha256"], f"Package checksum mismatch: {name}"
        if "source" in record:
            assert data == source_bytes(root / relative(record["source"])), f"Canonical source changed: {name}"
        else:
            assert record.get("kind") == "native", f"Unknown package record: {name}"
            actual_native.add(PurePosixPath(name).name)
    assert actual_native == NATIVE, "Missing or unexpected native DLL"
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        manifest = check()
    else:
        if args.bundle is None:
            parser.error("--bundle is required when syncing")
        manifest = sync(args.bundle)
    print(f"Verified {len(manifest['files'])} campaign XP package files; nothing installed or launched.")


if __name__ == "__main__":
    main()
