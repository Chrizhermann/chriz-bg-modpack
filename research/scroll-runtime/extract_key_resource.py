"""Extract one variable resource from an Infinity Engine KEY V1 / BIFF V1 pair.

Copied from chriz-bg-rebalance/research/scripts/extract_key_resource.py for the
self-contained scroll installer. Copyright (c) 2026 Christopher Hermann, MIT;
see the repository LICENSE. The scroll builder calls only its read functions.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath


RESOURCE_TYPES = {
    "BMP": 1,
    "MVE": 2,
    "WAV": 4,
    "WFX": 5,
    "PLT": 6,
    "BAM": 1000,
    "WED": 1001,
    "CHU": 1002,
    "TIS": 1003,
    "MOS": 1004,
    "ITM": 1005,
    "SPL": 1006,
    "BCS": 1007,
    "IDS": 1008,
    "CRE": 1009,
    "ARE": 1010,
    "DLG": 1011,
    "2DA": 1012,
    "GAM": 1013,
    "STO": 1014,
    "WMP": 1015,
    "EFF": 1016,
    "BS": 1017,
    "CHR": 1018,
    "VVC": 1019,
    "VEF": 1020,
    "PRO": 1021,
    "BIO": 1022,
    "WBM": 1023,
    "FNT": 1024,
    "GUI": 1025,
    "SQL": 1026,
    "PVRZ": 1027,
    "GLSL": 1028,
    "MENU": 1029,
    "LUA": 1030,
    "TTF": 1031,
    "PNG": 1032,
    "BAH": 1033,
    "INI": 1034,
    "SRC": 1035,
}

KEY_HEADER = struct.Struct("<4s4sIIII")
KEY_BIF_ENTRY = struct.Struct("<IIHH")
KEY_RESOURCE_ENTRY = struct.Struct("<8sHI")
BIFF_HEADER = struct.Struct("<4s4sIII")
BIFF_VARIABLE_ENTRY = struct.Struct("<IIIHH")
RESOURCE_INDEX_MASK = 0xFFFFF


class ExtractionError(Exception):
    """Raised when an indexed resource cannot be extracted safely."""


@dataclass(frozen=True)
class ExtractionResult:
    key_entry_index: int
    key_locator: int
    bif_index: int
    resource_index: int
    bif_path: Path
    bif_resource_locator: int
    payload_offset: int
    payload_size: int
    sha256: str
    output_path: Path


def _checked_slice(data: bytes, offset: int, size: int, description: str) -> bytes:
    end = offset + size
    if offset < 0 or size < 0 or end > len(data):
        raise ExtractionError(
            f"{description} range 0x{offset:X}..0x{end:X} exceeds file size {len(data)}"
        )
    return data[offset:end]


def _decode_ascii(raw: bytes, description: str) -> str:
    try:
        return raw.rstrip(b"\0 ").decode("ascii")
    except UnicodeDecodeError as error:
        raise ExtractionError(f"{description} is not ASCII") from error


def _resource_type_id(value: str) -> int:
    normalized = value.strip().upper()
    if normalized in RESOURCE_TYPES:
        return RESOURCE_TYPES[normalized]
    try:
        numeric = int(normalized, 0)
    except ValueError as error:
        names = ", ".join(sorted(RESOURCE_TYPES))
        raise ExtractionError(f"unknown resource type {value!r}; expected one of: {names}") from error
    if not 0 <= numeric <= 0xFFFF:
        raise ExtractionError(f"resource type {value!r} is outside the uint16 range")
    return numeric


def _read_file(path: Path, description: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ExtractionError(f"cannot read {description} {path}: {error}") from error


def _resolve_bif_path(game_root: Path, key_name: str) -> Path:
    windows_path = PureWindowsPath(key_name.replace("/", "\\"))
    if windows_path.is_absolute() or windows_path.drive or ".." in windows_path.parts:
        raise ExtractionError(f"unsafe BIF path in KEY: {key_name!r}")
    root = game_root.resolve()
    candidate = root.joinpath(*windows_path.parts).resolve()
    if not candidate.is_relative_to(root):
        raise ExtractionError(f"BIF path escapes game root: {key_name!r}")
    return candidate


def _find_key_resource(
    key_data: bytes,
    requested_resref: str,
    requested_type: int,
) -> tuple[int, int, list[tuple[int, str]]]:
    if len(key_data) < KEY_HEADER.size:
        raise ExtractionError(f"KEY header is truncated: size {len(key_data)}")
    signature, version, bif_count, resource_count, bif_offset, resource_offset = (
        KEY_HEADER.unpack_from(key_data)
    )
    if signature != b"KEY " or version != b"V1  ":
        raise ExtractionError(f"unsupported KEY signature/version: {signature!r} {version!r}")

    _checked_slice(
        key_data,
        bif_offset,
        bif_count * KEY_BIF_ENTRY.size,
        "KEY BIF table",
    )
    _checked_slice(
        key_data,
        resource_offset,
        resource_count * KEY_RESOURCE_ENTRY.size,
        "KEY resource table",
    )

    bifs: list[tuple[int, str]] = []
    for index in range(bif_count):
        entry_offset = bif_offset + index * KEY_BIF_ENTRY.size
        file_size, name_offset, name_length, _location = KEY_BIF_ENTRY.unpack_from(
            key_data, entry_offset
        )
        name_raw = _checked_slice(key_data, name_offset, name_length, f"KEY BIF name {index}")
        name = _decode_ascii(name_raw, f"KEY BIF name {index}")
        if not name:
            raise ExtractionError(f"KEY BIF name {index} is empty")
        bifs.append((file_size, name))

    wanted = requested_resref.casefold()
    for index in range(resource_count):
        entry_offset = resource_offset + index * KEY_RESOURCE_ENTRY.size
        raw_resref, resource_type, locator = KEY_RESOURCE_ENTRY.unpack_from(
            key_data, entry_offset
        )
        resref = _decode_ascii(raw_resref, f"KEY resource resref {index}")
        if resref.casefold() == wanted and resource_type == requested_type:
            return index, locator, bifs

    raise ExtractionError(
        f"resource {requested_resref!r} type {requested_type} was not found in KEY"
    )


def _read_biff_resource(
    bif_path: Path,
    resource_index: int,
    requested_type: int,
) -> tuple[bytes, int, int, int]:
    try:
        file_size = bif_path.stat().st_size
        with bif_path.open("rb") as handle:
            header_data = handle.read(BIFF_HEADER.size)
            if len(header_data) != BIFF_HEADER.size:
                raise ExtractionError(f"BIFF header is truncated: size {len(header_data)}")
            signature, version, variable_count, _fixed_count, table_offset = (
                BIFF_HEADER.unpack(header_data)
            )
            if signature != b"BIFF" or version != b"V1  ":
                raise ExtractionError(
                    f"unsupported BIFF signature/version: {signature!r} {version!r}"
                )
            table_size = variable_count * BIFF_VARIABLE_ENTRY.size
            if table_offset + table_size > file_size:
                raise ExtractionError(
                    f"BIFF variable table size {table_size} at 0x{table_offset:X} "
                    f"exceeds file size {file_size}"
                )
            handle.seek(table_offset)
            table = handle.read(table_size)
            if len(table) != table_size:
                raise ExtractionError(
                    f"BIFF variable table size mismatch: expected {table_size}, got {len(table)}"
                )

            if resource_index >= variable_count:
                raise ExtractionError(
                    f"BIFF variable-resource index 0x{resource_index:X} is out of range "
                    f"for {variable_count} entries"
                )
            entry_offset = resource_index * BIFF_VARIABLE_ENTRY.size
            serialized_locator, payload_offset, payload_size, resource_type, _unknown = (
                BIFF_VARIABLE_ENTRY.unpack_from(table, entry_offset)
            )
            if resource_type != requested_type:
                raise ExtractionError(
                    f"BIFF variable-resource index 0x{resource_index:X} type mismatch: "
                    f"expected {requested_type}, got {resource_type}"
                )
            payload_end = payload_offset + payload_size
            if payload_end > file_size:
                raise ExtractionError(
                    f"BIFF payload size mismatch: range 0x{payload_offset:X}.."
                    f"0x{payload_end:X} exceeds file size {file_size}"
                )
            handle.seek(payload_offset)
            payload = handle.read(payload_size)
            if len(payload) != payload_size:
                raise ExtractionError(
                    f"BIFF payload size mismatch: expected {payload_size}, got {len(payload)}"
                )
            return payload, serialized_locator, payload_offset, payload_size
    except ExtractionError:
        raise
    except OSError as error:
        raise ExtractionError(f"cannot read BIFF {bif_path}: {error}") from error


def extract_resource(
    *,
    key_path: Path | str,
    game_root: Path | str,
    resref: str,
    resource_type: str,
    output_path: Path | str,
    expected_sha256: str | None = None,
) -> ExtractionResult:
    """Resolve and extract exactly one variable resource to ``output_path``."""
    normalized_resref = resref.strip().rstrip(".")
    if not normalized_resref or len(normalized_resref.encode("ascii", "ignore")) > 8:
        raise ExtractionError("resref must contain one to eight ASCII characters")
    try:
        normalized_resref.encode("ascii")
    except UnicodeEncodeError as error:
        raise ExtractionError("resref must contain one to eight ASCII characters") from error

    type_id = _resource_type_id(resource_type)
    key = Path(key_path)
    root = Path(game_root)
    output = Path(output_path)
    key_data = _read_file(key, "KEY")
    key_index, locator, bifs = _find_key_resource(key_data, normalized_resref, type_id)
    bif_index = locator >> 20
    resource_index = locator & RESOURCE_INDEX_MASK
    if bif_index >= len(bifs):
        raise ExtractionError(
            f"KEY locator 0x{locator:08X} selects BIF {bif_index}, "
            f"but the KEY contains {len(bifs)} BIF entries"
        )
    _indexed_size, bif_name = bifs[bif_index]
    bif_path = _resolve_bif_path(root, bif_name)
    payload, bif_locator, payload_offset, payload_size = _read_biff_resource(
        bif_path, resource_index, type_id
    )

    digest = hashlib.sha256(payload).hexdigest()
    normalized_expected: str | None = None
    if expected_sha256 is not None:
        normalized_expected = expected_sha256.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", normalized_expected):
            raise ExtractionError("expected SHA-256 must be exactly 64 hexadecimal characters")
        if digest != normalized_expected:
            raise ExtractionError(
                f"payload SHA-256 mismatch: expected {normalized_expected}, got {digest}"
            )

    if output.exists() and normalized_expected is None:
        raise ExtractionError(
            f"output already exists: {output}; pass --expected-sha256 to authorize overwrite"
        )
    if not output.parent.is_dir():
        raise ExtractionError(f"output parent directory does not exist: {output.parent}")
    try:
        with output.open("wb" if output.exists() else "xb") as handle:
            handle.write(payload)
    except OSError as error:
        raise ExtractionError(f"cannot write output {output}: {error}") from error

    return ExtractionResult(
        key_entry_index=key_index,
        key_locator=locator,
        bif_index=bif_index,
        resource_index=resource_index,
        bif_path=bif_path,
        bif_resource_locator=bif_locator,
        payload_offset=payload_offset,
        payload_size=payload_size,
        sha256=digest,
        output_path=output,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", required=True, type=Path, help="path to chitin.key")
    parser.add_argument("--game-root", required=True, type=Path, help="game root for BIF paths")
    parser.add_argument("--resref", required=True, help="resource reference, without extension")
    parser.add_argument("--type", required=True, dest="resource_type", help="resource type, e.g. SPL")
    parser.add_argument("--output", required=True, type=Path, help="explicit destination path")
    parser.add_argument(
        "--expected-sha256",
        help="expected payload hash; also authorizes overwrite of an existing output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = extract_resource(
            key_path=args.key,
            game_root=args.game_root,
            resref=args.resref,
            resource_type=args.resource_type,
            output_path=args.output,
            expected_sha256=args.expected_sha256,
        )
    except ExtractionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"KEY entry: {result.key_entry_index}")
    print(f"KEY locator: 0x{result.key_locator:08X}")
    print(f"BIF index: {result.bif_index}")
    print(f"BIF path: {result.bif_path}")
    print(f"BIF serialized locator field: 0x{result.bif_resource_locator:X}")
    print(f"Payload offset: 0x{result.payload_offset:X}")
    print(f"Payload size: {result.payload_size}")
    print(f"SHA-256: {result.sha256}")
    print(f"Output: {result.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
