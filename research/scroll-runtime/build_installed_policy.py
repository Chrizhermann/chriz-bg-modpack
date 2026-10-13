"""Build a read-only effective installed scroll inventory outside the game.

Uses the existing mechanical classifier and policy format without adding policy
exceptions. No game resource is written or extracted to disk. Exit 2 means the
written report contains unresolved abilities or incomplete item enumeration;
the artifacts are for review, not a claim that every installed scroll is ready.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from pathlib import Path
import runpy
import struct
import sys
import tempfile

from installed_resources import Inventory, ResourceError
from policy_table import build, name_bytes
import extract_key_resource as bundled_key_reader

DEFAULT_READER = Path(__file__).resolve().with_name("extract_key_resource.py")
TABLE_NAME = "CBMSPOL1.bin"
REPORT_NAME = "CBMSPOL1.json"
INSTALLER_STAGE = Path("weidu_external/chriz-bg-modpack/scroll-policy-work")


def unique_child(parent, name, *, required=False):
    matches = [p for p in parent.iterdir() if p.name.casefold() == name.casefold()]
    if len(matches) > 1:
        raise ResourceError(f"case-insensitive path is ambiguous: {parent / name}")
    if matches:
        return matches[0]
    if required:
        raise ResourceError(f"missing installed path: {parent / name}")
    return None


class Installed:
    """Effective resource reader; override always wins, including bad overrides.

    KEY/BIF validation and bounded payload reads reuse the existing extraction
    helper. Index the KEY once rather than rescan its complete resource table
    for every installed item. No call to its disk-writing extract_resource API.
    """
    def __init__(self, game_root, key_reader=DEFAULT_READER):
        self.root = Path(game_root).resolve(strict=True)
        if not self.root.is_dir():
            raise ResourceError("game root must be a directory")
        self.helper = (vars(bundled_key_reader) if Path(key_reader).resolve()==DEFAULT_READER
                       else runpy.run_path(str(key_reader)))
        h = self.helper
        self.key_path = unique_child(self.root, "chitin.key", required=True)
        self.key_data = self.key_path.read_bytes()
        self.key_sha256 = hashlib.sha256(self.key_data).hexdigest()
        self.bifs, self.entries, self.ambiguous, self.overrides = [], {}, set(), {}
        self.sources = {}
        try:
            raw = h["_checked_slice"](self.key_data, 0, h["KEY_HEADER"].size, "KEY header")
            signature, version, bif_count, resource_count, bif_offset, resource_offset = h["KEY_HEADER"].unpack(raw)
            if signature != b"KEY " or version != b"V1  ":
                raise ResourceError("unsupported KEY signature/version")
            h["_checked_slice"](self.key_data, bif_offset, bif_count*h["KEY_BIF_ENTRY"].size, "KEY BIF table")
            h["_checked_slice"](self.key_data, resource_offset, resource_count*h["KEY_RESOURCE_ENTRY"].size, "KEY resource table")
            for i in range(bif_count):
                _, offset, length, _ = h["KEY_BIF_ENTRY"].unpack_from(self.key_data, bif_offset+i*h["KEY_BIF_ENTRY"].size)
                name = h["_decode_ascii"](h["_checked_slice"](self.key_data, offset, length, f"KEY BIF name {i}"), f"KEY BIF name {i}")
                if not name:
                    raise ResourceError(f"empty KEY BIF name {i}")
                self.bifs.append(name)
            kinds = {h["RESOURCE_TYPES"][ext]:ext for ext in ("ITM", "SPL", "EFF")}
            for i in range(resource_count):
                raw_name, kind, locator = h["KEY_RESOURCE_ENTRY"].unpack_from(self.key_data, resource_offset+i*h["KEY_RESOURCE_ENTRY"].size)
                if kind not in kinds:
                    continue
                name = h["_decode_ascii"](raw_name, f"KEY resref {i}").upper()
                name_bytes(name)
                key = name, kinds[kind]
                if key in self.entries and self.entries[key] != locator:
                    self.ambiguous.add(key)
                self.entries.setdefault(key, locator)
        except h["ExtractionError"] as error:
            raise ResourceError(str(error)) from error
        override = unique_child(self.root, "override")
        if override:
            for path in sorted(override.iterdir(), key=lambda p: (p.name.upper(), p.name)):
                if not path.is_file() or path.suffix.upper() not in (".ITM", ".SPL", ".EFF"):
                    continue
                # Invalid long/non-ASCII filenames are not engine resrefs.
                try:
                    name_bytes(path.stem)
                except ValueError:
                    continue
                self.overrides.setdefault((path.stem.upper(), path.suffix[1:].upper()), []).append(path)

    def items(self):
        return sorted({name for name, ext in (*self.entries, *self.overrides) if ext == "ITM"})

    def load(self, name, extension):
        key = name.upper(), extension.upper()
        h = self.helper
        try:
            overrides = self.overrides.get(key)
            if overrides:
                if len(overrides) != 1:
                    raise ResourceError(f"{'.'.join(key)}: multiple case-insensitive override files")
                raw = overrides[0].read_bytes()
                self.sources['.'.join(key)] = {"kind":"override", "path":str(overrides[0])}
                return raw
            if key in self.ambiguous:
                raise ResourceError(f"{'.'.join(key)}: conflicting KEY locators")
            if key not in self.entries:
                raise FileNotFoundError(f"{'.'.join(key)}: missing from override and KEY")
            locator = self.entries[key]
            bif_index = locator >> 20
            if bif_index >= len(self.bifs):
                raise ResourceError(f"{'.'.join(key)}: KEY BIF index {bif_index} is out of bounds")
            path = h["_resolve_bif_path"](self.root, self.bifs[bif_index])
            # The helper guards traversal. Resolve each already-contained path
            # segment case-insensitively for portable fixture/read-only hosts.
            current = self.root
            for segment in path.relative_to(self.root).parts:
                current = unique_child(current, segment, required=True)
            path = current.resolve(strict=True)
            if not path.is_relative_to(self.root):
                raise ResourceError("BIF path escapes game root")
            raw = h["_read_biff_resource"](path, locator & h["RESOURCE_INDEX_MASK"], h["RESOURCE_TYPES"][key[1]])[0]
            self.sources['.'.join(key)] = {"kind":"bif", "path":str(path), "locator":locator}
            return raw
        except h["ExtractionError"] as error:
            raise ResourceError(f"{'.'.join(key)}: {error}") from error
        except OSError as error:
            raise ResourceError(f"{'.'.join(key)}: {error}") from error


def inventory(installed):
    analyzer = Inventory(installed.load)
    reports, errors, scrolls = [], [], []
    items = installed.items()
    for name in items:
        try:
            raw = installed.load(name, "ITM")
            if len(raw) < 0x1E or raw[:8] != b"ITM V1  ":
                raise ResourceError(f"{name}.ITM: unsupported or truncated item header")
            if struct.unpack_from("<H", raw, 0x1C)[0] != 11:
                continue
            scrolls.append(name)
            # Use the already-read root bytes in the shared classifier. It
            # still validates its full indexed blocks and every use ability.
            analyzer.load = lambda n, e, current=name, data=raw: data if (n,e)==(current,"ITM") else installed.load(n,e)
            reports.extend(analyzer.item(name))
        except (ResourceError, ValueError, OSError) as error:
            errors.append({"resource":name+".ITM", "diagnostic":str(error)})
    binary, manifest = build(reports)
    counts = Counter(r.classification for r in reports)
    unresolved = sum(counts[c] for c in ("unresolved", "mixed_learning_cast"))
    manifest.update({
        "game_root":str(installed.root), "key_path":str(installed.key_path),
        "key_sha256":installed.key_sha256,
        "inventory":{"items":len(items), "category11_items":len(scrolls),
                     "classification_counts":dict(sorted(counts.items())),
                     "root_errors":len(errors), "unresolved_abilities":unresolved,
                     "complete":not errors, "requires_review":bool(errors or unresolved)},
        "inventory_errors":errors,
        "sources":{name:installed.sources[name] for name in sorted({resource for r in reports for resource in r.resources})},
        "limitations":["Mechanical classification reuses installed_resources; author-fixed intent still requires its explicit provider exception.",
                       "Resources may change during or after inventory; the runtime must verify effective dependency hashes before use.",
                       "Malformed roots cannot yield reliable ability indexes and are recorded as inventory_errors, not fabricated policy rows."],
    })
    return binary, manifest


def output_directory(game_root, output_dir, *, installer_staging=False):
    root = Path(game_root).resolve(strict=True)
    supplied = Path(output_dir).absolute()
    destination = supplied.resolve()
    if installer_staging:
        # Only these two generated files in this exact mod-owned working folder
        # may be replaced. In particular no override, resource or save output is
        # accepted, and a junction may not redirect the working folder.
        if destination != root / INSTALLER_STAGE:
            raise ValueError("installer staging must use the exact mod-owned scroll-policy-work directory")
    elif supplied.is_relative_to(root) or destination.is_relative_to(root):
        raise ValueError("output directory must be separate from and outside the game")
    for name in (TABLE_NAME, REPORT_NAME):
        path = destination/name
        if path.is_symlink() or (path.exists() and (not installer_staging or not path.is_file())):
            raise ValueError(f"refusing to overwrite output: {path}")
    return destination


def write_inventory(game_root, output_dir, *, key_reader=DEFAULT_READER, installer_staging=False):
    destination = output_directory(game_root, output_dir,installer_staging=installer_staging)
    installed = Installed(game_root, key_reader)
    binary, manifest = inventory(installed)
    if installer_staging and manifest["inventory"]["root_errors"]:
        raise ResourceError("incomplete resource inventory: " + "; ".join(
            item["diagnostic"] for item in manifest["inventory_errors"]))
    import json
    report = (json.dumps(manifest,indent=2,sort_keys=True)+"\n").encode("utf-8")
    destination.mkdir(parents=True,exist_ok=True)
    # Recheck physical containment after mkdir (including existing junctions).
    destination = output_directory(game_root, destination,installer_staging=installer_staging)
    if installer_staging:
        pending=[]
        try:
            for name,data in ((TABLE_NAME,binary),(REPORT_NAME,report)):
                with tempfile.NamedTemporaryFile(dir=destination,prefix="CBMS-",suffix=".tmp",delete=False) as stream:
                    path=Path(stream.name);pending.append((path,destination/name))
                    stream.write(data)
            for temporary, final in pending:
                temporary.replace(final)
        finally:
            for temporary,_ in pending:
                temporary.unlink(missing_ok=True)
        return manifest
    created = []
    try:
        for name, data in ((TABLE_NAME,binary),(REPORT_NAME,report)):
            path = destination/name
            with path.open("xb") as stream:
                created.append(path)
                stream.write(data)
    except BaseException:
        # Only files this invocation exclusively created; never input files or
        # a pre-existing output. No directory tree removal.
        for path in reversed(created):
            path.unlink()
        raise
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--key-reader",type=Path,default=DEFAULT_READER,
                        help="existing read-only KEY/BIFF helper module")
    parser.add_argument("--installer-staging",action="store_true",
                        help="allow only the two generated files in the fixed mod-owned WeiDU working directory")
    args = parser.parse_args(argv)
    try:
        result = write_inventory(args.game_root,args.output_dir,key_reader=args.key_reader,
                                 installer_staging=args.installer_staging)
    except (OSError,ValueError,ResourceError) as error:
        print(f"error: {error}",file=sys.stderr)
        return 1
    summary = result["inventory"]
    print(f"{summary['items']} effective ITMs; {summary['category11_items']} category11 scrolls; "
          f"{result['entries']} abilities; {result['dependencies']} hashed dependencies")
    print(f"classifications: {summary['classification_counts']}")
    print(f"root errors: {summary['root_errors']}; unresolved abilities: {summary['unresolved_abilities']}")
    print(f"output: {Path(args.output_dir).resolve()}")
    return 2 if summary["requires_review"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
