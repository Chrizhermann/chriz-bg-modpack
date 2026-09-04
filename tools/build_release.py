"""Build a deterministic, allowlisted chriz-bg-modpack release archive."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import urllib.request
import zipfile


_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class ReleaseArtifacts:
    archive: Path
    sha256: str
    checksum_file: Path
    contents_file: Path


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relative_path(raw_path: object, *, label: str) -> PurePosixPath:
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
        raise ValueError(f"unsafe {label}: {raw_path!r}")
    path = PurePosixPath(raw_path)
    if (
        path.is_absolute()
        or raw_path != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
        or (path.parts and ":" in path.parts[0])
    ):
        raise ValueError(f"unsafe {label}: {raw_path!r}")
    return path


def _load_manifest(manifest_path: Path) -> dict[str, object]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read release manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("release manifest must contain a JSON object")
    return manifest


def _manifest_file_paths(manifest: dict[str, object]) -> list[PurePosixPath]:
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("release manifest files must be a non-empty list")
    paths = [_safe_relative_path(raw, label="manifest path") for raw in raw_files]
    names = [path.as_posix() for path in paths]
    if len(names) != len(set(names)):
        raise ValueError("release manifest contains duplicate paths")
    return sorted(paths, key=lambda path: path.as_posix())


def _read_source_payloads(
    source_root: Path, paths: list[PurePosixPath]
) -> dict[str, bytes]:
    payloads: dict[str, bytes] = {}
    for relative in paths:
        source = source_root.joinpath(*relative.parts)
        if source.is_symlink():
            raise ValueError(f"release input may not be a symlink: {relative.as_posix()}")
        if not source.is_file():
            raise ValueError(f"release input is missing or not a file: {relative.as_posix()}")
        payloads[relative.as_posix()] = source.read_bytes()

    runtime_root = source_root / "chriz-bg-modpack"
    if runtime_root.exists():
        actual_runtime: set[str] = set()
        for source in runtime_root.rglob("*"):
            relative = source.relative_to(source_root).as_posix()
            if source.is_symlink():
                raise ValueError(f"runtime file may not be a symlink: {relative}")
            if source.is_file():
                actual_runtime.add(relative)
        listed_runtime = {
            name for name in payloads if name.startswith("chriz-bg-modpack/")
        }
        unlisted = sorted(actual_runtime - listed_runtime)
        if unlisted:
            raise ValueError(f"unlisted runtime file: {unlisted[0]}")
        missing = sorted(listed_runtime - actual_runtime)
        if missing:
            raise ValueError(f"listed runtime file is missing: {missing[0]}")
    return payloads


def _validate_release_identity(
    manifest: dict[str, object], payloads: dict[str, bytes]
) -> None:
    version = manifest.get("version")
    if not isinstance(version, str) or not version.startswith("v"):
        raise ValueError("manifest version is missing or invalid")
    try:
        version_file = payloads["VERSION"].decode("utf-8").strip()
    except (KeyError, UnicodeError) as exc:
        raise ValueError("release manifest must include a UTF-8 VERSION file") from exc
    if version_file != version:
        raise ValueError(
            f"VERSION does not match manifest: {version_file!r} != {version!r}"
        )

    expected_basename = f"chriz-bg-modpack-{version}"
    if manifest.get("archive_basename") != expected_basename:
        raise ValueError(
            "archive_basename does not match VERSION: "
            f"expected {expected_basename!r}"
        )

    try:
        tp2_lines = payloads["setup-chriz-bg-modpack.tp2"].decode("utf-8").splitlines()
    except (KeyError, UnicodeError) as exc:
        raise ValueError("release manifest must include a UTF-8 setup TP2") from exc
    expected_tp2_version = f"VERSION ~{version}~"
    if tp2_lines.count(expected_tp2_version) != 1:
        raise ValueError(
            f"setup TP2 does not declare exactly {expected_tp2_version!r}"
        )


def _read_weidu_archive(archive_path: Path | None, url: str) -> bytes:
    if archive_path is not None:
        try:
            return archive_path.read_bytes()
        except OSError as exc:
            raise ValueError(f"cannot read WeiDU archive: {exc}") from exc
    if not url.startswith("https://"):
        raise ValueError("WeiDU download URL must use HTTPS")
    try:
        with urllib.request.urlopen(url) as response:  # noqa: S310 - pinned hash below
            return response.read()
    except OSError as exc:
        raise ValueError(f"cannot download WeiDU archive: {exc}") from exc


def _archive_payloads(archive_data: bytes, weidu: dict[str, object]) -> dict[str, bytes]:
    expected_hash = weidu.get("archive_sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError("WeiDU archive SHA-256 is missing or invalid")
    actual_hash = _sha256(archive_data)
    if actual_hash.lower() != expected_hash.lower():
        raise ValueError(
            "WeiDU archive SHA-256 mismatch: "
            f"expected {expected_hash.lower()}, got {actual_hash}"
        )

    exe_path = _safe_relative_path(weidu.get("exe_path"), label="WeiDU ZIP path")
    expected_exe_hash = weidu.get("exe_sha256")
    if not isinstance(expected_exe_hash, str) or len(expected_exe_hash) != 64:
        raise ValueError("WeiDU executable SHA-256 is missing or invalid")
    license_path = _safe_relative_path(
        weidu.get("license_path"), label="WeiDU ZIP path"
    )
    wanted = {exe_path.as_posix(), license_path.as_posix()}
    try:
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ValueError("WeiDU ZIP contains duplicate entries")
            for info in infos:
                _safe_relative_path(info.filename.rstrip("/"), label="WeiDU ZIP path")
                file_type = (info.external_attr >> 16) & 0o170000
                if file_type == stat.S_IFLNK:
                    raise ValueError(f"WeiDU ZIP contains a symlink: {info.filename}")
            by_name = {info.filename: info for info in infos}
            missing = sorted(wanted - by_name.keys())
            if missing:
                raise ValueError(f"WeiDU ZIP is missing required entry: {missing[0]}")
            if any(by_name[name].is_dir() for name in wanted):
                raise ValueError("WeiDU ZIP required entries must be files")
            executable = archive.read(exe_path.as_posix())
            actual_exe_hash = _sha256(executable)
            if actual_exe_hash.lower() != expected_exe_hash.lower():
                raise ValueError(
                    "WeiDU executable SHA-256 mismatch: "
                    f"expected {expected_exe_hash.lower()}, got {actual_exe_hash}"
                )
            return {
                "setup-chriz-bg-modpack.exe": executable,
                "WEIDU-COPYING.txt": archive.read(license_path.as_posix()),
            }
    except zipfile.BadZipFile as exc:
        raise ValueError("WeiDU archive is not a valid ZIP file") from exc


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    mode = 0o755 if name.endswith(".exe") else 0o644
    info.external_attr = (stat.S_IFREG | mode) << 16
    return info


def _render_archive(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(payloads):
            archive.writestr(_zip_info(name), payloads[name], compresslevel=9)
    return output.getvalue()


def build_release(
    source_root: Path,
    manifest_path: Path,
    output_dir: Path,
    weidu_archive: Path | None = None,
) -> ReleaseArtifacts:
    """Build and describe a release after all inputs pass validation."""

    source_root = source_root.resolve()
    manifest = _load_manifest(manifest_path)
    paths = _manifest_file_paths(manifest)
    payloads = _read_source_payloads(source_root, paths)
    _validate_release_identity(manifest, payloads)

    weidu = manifest.get("weidu")
    if not isinstance(weidu, dict):
        raise ValueError("release manifest must contain WeiDU metadata")
    url = weidu.get("url")
    if not isinstance(url, str):
        raise ValueError("WeiDU URL is missing")
    archive_data = _read_weidu_archive(weidu_archive, url)
    payloads.update(_archive_payloads(archive_data, weidu))

    archive_basename = manifest.get("archive_basename")
    if (
        not isinstance(archive_basename, str)
        or not archive_basename
        or archive_basename != Path(archive_basename).name
    ):
        raise ValueError("archive_basename is missing or unsafe")

    packaged = _render_archive(payloads)
    packaged_hash = _sha256(packaged)
    content_text = "".join(
        f"{_sha256(payloads[name])}  {len(payloads[name])}  {name}\n"
        for name in sorted(payloads)
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{archive_basename}.zip"
    checksum_path = output_dir / f"{archive_path.name}.sha256"
    contents_path = output_dir / f"{archive_basename}.contents.txt"
    archive_path.write_bytes(packaged)
    checksum_path.write_text(
        f"{packaged_hash}  {archive_path.name}\n", encoding="ascii", newline=""
    )
    contents_path.write_text(content_text, encoding="utf-8", newline="")
    return ReleaseArtifacts(
        archive=archive_path,
        sha256=packaged_hash,
        checksum_file=checksum_path,
        contents_file=contents_path,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--manifest", type=Path, default=Path("release-manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("dist"))
    parser.add_argument("--weidu-archive", type=Path)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    manifest = args.manifest
    if not manifest.is_absolute():
        manifest = source_root / manifest
    output = args.output
    if not output.is_absolute():
        output = source_root / output
    artifacts = build_release(source_root, manifest, output, args.weidu_archive)
    print(artifacts.archive)
    print(artifacts.checksum_file)
    print(artifacts.contents_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
