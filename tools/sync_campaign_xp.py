"""Copy the reviewed banking candidate into the mod; never run a game or build.

Research Lua/menu sources remain canonical; text mirrors use repository LF EOLs.
Native DLLs must match the supplied offline bundle manifest and the build record
bank_build.ps1 writes beside it. --capture, before anything compiles, claims a
new or empty build folder, freezes the research sources into it and hashes every
input of each DLL there (its build script, the sources and local headers it
compiles); the build compiles that copy, mapping its path so that no DLL depends
on the folder, and each DLL embeds the digest of its inputs and the build's
identifier (cbm_build_inputs.cpp). --record, after every
check passed, describes each DLL that build compiled from exactly those inputs
(and the MSVC toolchain); it needs the secret only that build holds, refuses a
DLL that does not embed both, and consumes the capture: a record needs one whole
build. The package keeps that record. --check needs no bundle and detects
source/package drift, including a native input that changed after its DLL was
built and a DLL that embeds other inputs than its record names.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path("chriz-bg-modpack/campaign-xp")
NATIVE_SOURCES = PurePosixPath("research/xp-banking-native")
DRIVER = "bank_build.ps1"
CAPTURE, RECORD = "native-inputs.json", "native-build.json"  # In the build folder.
# What a build reads, frozen into its folder (TREE) before anything compiles.
FROZEN = (NATIVE_SOURCES, PurePosixPath("research/xp-banking"))
TREE = "src"
SECRET = "CBM_BUILD_SECRET"  # bank_build.ps1's secret for one run: only that run records.
# What cbm_build_inputs.cpp embeds: the inputs' digest and the build's identifier.
MARKER = re.compile(rb"cbm-build-inputs:([0-9a-f]{64}):([0-9a-f]{32})\0")
# The script that links each packaged DLL; the driver runs every one of them.
BUILDERS = {
    "cbmbank_identity.dll": "reset_check.ps1", "dual_hp_observer.dll": "dual_hp_check.ps1",
    "dual_native_proficiency.dll": "dual_native_check.ps1", "dual_prof_commit.dll": "dual_prof_commit.ps1",
    "dual_skill_rows.dll": "dual_skill_rows_check.ps1", "dual_old_hla.dll": "dual_old_hla.ps1",
}
NATIVE = set(BUILDERS)
BANNERS = {
    "cl": re.compile(r"Microsoft \(R\) C/C\+\+ Optimizing Compiler Version (\d+)\.(\d+)\.(\d+)(?:\.\d+)? for x64"),
    "link": re.compile(r"Microsoft \(R\) Incremental Linker Version (\d+)\.(\d+)\.(\d+)\.\d+"),
    "ml64": re.compile(r"Microsoft \(R\) Macro Assembler \(x64\) Version (\d+)\.(\d+)\.(\d+)\.\d+"),
}
ENVIRONMENT = ("VCToolsVersion", "WindowsSDKVersion", "UCRTVersion")  # Recorded when set; not checked.
# Rich header product ids (VS 2015 and later) of the objects each source kind yields.
OBJECTS = {".cpp": (0x105, "cl"), ".c": (0x104, "cl"), ".asm": (0x103, "ml64")}
LINKER = 0x102
ASSIGNMENT = re.compile(r"\$(\w+)\s*=\s*Join-Path\s+\$(\w+)\s+'([^'\s]+)'")
# MSVC names anonymous namespaces after the path of the file it compiles, and each
# build compiles its own frozen copy: only a compile that maps the script folder to
# one fixed name (/pathmap, which needs /experimental:deterministic) lays a DLL out
# the same in every build folder, so that a sync can keep it and a rebuild check it.
MAPPED = NATIVE_SOURCES.as_posix().replace("/", "\\")
PATHMAP = re.compile(r'(?<!\S)/pathmap:("[^"]*"|\S*?)=(\S*)')
ARGUMENT = re.compile(r'(/F[eo])?"([^"]*)"')
INCLUDE = re.compile(r"^[ \t]*#[ \t]*include\b[ \t]*(.*)$", re.M)
MASM_INCLUDE = re.compile(r"^[ \t]*include[ \t]+(\S+)", re.M | re.I)


def require(condition: object, message: str) -> None:
    if not condition:  # Not an assert: the check must hold under python -O too.
        raise AssertionError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError(f"Unsafe manifest path: {name}")
    return path


def toolchain_from(text: str) -> dict:
    """The version banners (and vcvars versions) bank_build.ps1 captured."""
    found = {}
    for tool, pattern in BANNERS.items():
        match = pattern.search(text)
        if not match:
            raise ValueError(f"Toolchain capture lacks the {tool} version banner")
        found[tool] = match.group(0)
    for name in ENVIRONMENT:
        match = re.search(rf"^{name}=(\S*?)\\?\s*$", text, re.M)
        if match and match.group(1):
            found[name] = match.group(1)
    return found


def version(toolchain: dict, tool: str) -> tuple[int, ...]:
    match = BANNERS[tool].fullmatch(str(toolchain.get(tool, "")))
    if not match:
        raise ValueError(f"Build record names no recognizable {tool} version")
    return tuple(int(n) for n in match.groups())


def links(root: Path, script: str) -> dict[str, list[str]]:
    """Each DLL a build script links with cl /LD, with the sources it compiles."""
    text = (root / NATIVE_SOURCES / script).read_text(encoding="utf-8")
    # The scripts' common prologue: $sourceDir is the script's folder, $build the build folder.
    require("$sourceDir" not in text or re.search(r"\$sourceDir\s*=\s*\$PSScriptRoot\b", text),
            f"{script}: $sourceDir is not the script folder")
    require(re.search(r"\$build\s*=\s*\[(?:System\.)?IO\.Path\]::GetFullPath\(\$BuildDir\)", text),
            f"{script}: $build is not the build folder")
    variables = {name: (base, file) for name, base, file in ASSIGNMENT.findall(text)}

    def place(token: str) -> tuple[str, str]:
        match = re.fullmatch(r"\$(\w+)(?:/([^$]*))?", token)
        if match is None:
            raise ValueError(f"{script}: unrecognized build path {token}")
        name, rest = match.groups()
        base, file = (name, rest) if rest is not None else variables.get(name, (None, None))
        if base in ("PSScriptRoot", "sourceDir") and file:
            return "source", relative(file).as_posix()
        if base == "build" and file is not None:
            return "build", file
        raise ValueError(f"{script}: unrecognized build path {token}")

    assembled, linked = {}, {}
    for line in text.splitlines():
        if line.split()[:1] == ["ml64"]:
            arguments = ARGUMENT.findall(line)
            objects = [place(token) for flag, token in arguments if flag == "/Fo"]
            sources = [place(token) for flag, token in arguments if not flag]
            require(len(objects) == 1 and objects[0][0] == "build" and len(sources) == 1 and sources[0][0] == "source",
                    f"{script}: unrecognized ml64 line {line.strip()}")
            assembled[objects[0][1]] = sources[0][1]
    for line in text.splitlines():
        words = line.split()
        if words[:1] != ["cl"] or "/LD" not in words:
            continue
        compiled = line.split(" /link ", 1)[0]
        maps, compiled = PATHMAP.findall(compiled), PATHMAP.sub("", compiled)
        output, sources = None, []
        for flag, token in ARGUMENT.findall(compiled):
            if flag == "/Fo":
                continue
            kind, file = place(token)
            if flag == "/Fe":
                require(kind == "build" and output is None, f"{script}: unrecognized cl output {token}")
                output = file
            elif kind == "source":
                sources.append(file)
            else:
                require(file in assembled, f"{script}: {file} comes from no ml64 line")
                sources.append(assembled[file])
        require(output and output not in linked, f"{script}: a cl /LD line without its own output")
        require(len(maps) == 1 and maps[0] in (('"$sourceDir"', MAPPED), ('"$PSScriptRoot"', MAPPED))
                and "/experimental:deterministic" in compiled.split(),
                f"{script}: {output} would not compile the same in every build folder: its cl /LD line needs "
                f'/experimental:deterministic and /pathmap:"$sourceDir"={MAPPED}')
        linked[output] = sources
    return linked


def included(root: Path, path: str) -> list[str]:
    """Local files a source or header includes; toolchain headers are the toolchain's."""
    text = (root / path).read_bytes().decode("latin-1")
    if path.endswith(".asm"):
        names = MASM_INCLUDE.findall(text)
    else:
        names = []
        for rest in INCLUDE.findall(text):
            if rest.startswith("<"):
                continue
            match = re.match(r'"([^"]+)"', rest)
            if not match:
                raise ValueError(f"{path}: unrecognized #include {rest.strip()}")
            names.append(match.group(1))
    found = []
    for name in names:
        candidate = PurePosixPath(path).parent / name
        if ".." in candidate.parts or "\\" in name or not (root / candidate).is_file():
            raise ValueError(f"{path}: cannot resolve include {name} beside it")
        found.append(candidate.as_posix())
    return found


def build_inputs(root: Path, dll: str) -> dict:
    """How the current tree builds a packaged DLL: script, compiled sources, and the
    LF-normalized hash of every input (sources, local include closure, both scripts)."""
    script = BUILDERS[dll]
    driver = (root / NATIVE_SOURCES / DRIVER).read_text(encoding="utf-8")
    require(re.search(rf"^Invoke-Check '{re.escape(script)}'$", driver, re.M), f"{DRIVER} does not run {script}")
    linked = links(root, script)
    require(dll in linked, f"{script} links no {dll}")
    compiles = [(NATIVE_SOURCES / name).as_posix() for name in linked[dll]]
    for path in compiles:
        require(PurePosixPath(path).suffix in OBJECTS, f"{script}: unsupported source kind {path}")
    seen, pending = set(), list(compiles)
    while pending:
        path = pending.pop()
        if path not in seen:
            seen.add(path)
            pending.extend(included(root, path))
    seen |= {(NATIVE_SOURCES / script).as_posix(), (NATIVE_SOURCES / DRIVER).as_posix()}
    return {"script": (NATIVE_SOURCES / script).as_posix(), "compiles": compiles,
            "inputs": {path: digest(source_bytes(root / path)) for path in sorted(seen)}}


def drift(recorded: dict, current: dict) -> list[str]:
    old, new = recorded.get("inputs") or {}, current["inputs"]
    problems = []
    if recorded.get("script") != current["script"]:
        problems.append(f"script {recorded.get('script')} is now {current['script']}")
    if recorded.get("compiles") != current["compiles"]:
        problems.append("compiled sources are now " + ", ".join(current["compiles"]))
    problems += [f"changed {path}" for path in sorted(old.keys() & new.keys()) if old[path] != new[path]]
    problems += [f"added {path}" for path in sorted(new.keys() - old.keys())]
    problems += [f"removed {path}" for path in sorted(old.keys() - new.keys())]
    return problems


def inputs_digest(entry: dict) -> str:
    """What a DLL embeds of the inputs it was compiled from: one digest of its build
    script, its compiled sources and every input's hash."""
    text = json.dumps({key: entry[key] for key in ("script", "compiles", "inputs")}, sort_keys=True,
                      separators=(",", ":"))
    return digest(text.encode("utf-8"))


def build_id(secret: str) -> str:
    """The identifier the DLLs of one bank_build.ps1 run embed, from the secret
    only that run holds; the identifier does not reveal the secret."""
    require(re.fullmatch(r"(?:[0-9a-f]{2}){32,}", secret or ""),
            f"{SECRET} must hold this build's secret (64 or more hex digits): only bank_build.ps1 captures and records")
    return digest(b"cbm-build-id\0" + bytes.fromhex(secret))[:32]


def embedded(dll: str, data: bytes) -> tuple[str, str]:
    """The input digest and the build identifier a DLL embeds."""
    found = MARKER.findall(data)
    require(found, f"{dll} embeds no build inputs: bank_build.ps1 did not compile it")
    require(len(found) == 1, f"{dll} embeds {len(found)} build input markers")
    return found[0][0].decode("ascii"), found[0][1].decode("ascii")


def pe_build(data: bytes) -> tuple[tuple[int, int], dict[tuple[int, int], int]]:
    """A PE32+ x64 image's linker version and Rich header ((product, build) -> objects)."""
    pe = struct.unpack_from("<I", data, 0x3C)[0] if data[:2] == b"MZ" and len(data) >= 0x40 else 0
    if not pe or data[pe:pe + 4] != b"PE\0\0" or struct.unpack_from("<H", data, pe + 4)[0] != 0x8664 \
            or struct.unpack_from("<H", data, pe + 24)[0] != 0x20B:
        raise ValueError("Not a PE32+ x64 image")
    objects: dict[tuple[int, int], int] = {}
    end = data.find(b"Rich", 0x40, pe)
    if end >= 0:
        key = struct.unpack_from("<I", data, end + 4)[0]
        start = data.find(struct.pack("<I", 0x536E6144 ^ key), 0x40, end)
        words = [struct.unpack_from("<I", data, at)[0] ^ key for at in range(start, end, 4)] if start >= 0 else []
        if words[:4] != [0x536E6144, 0, 0, 0] or len(words) % 2:
            raise ValueError("Malformed Rich header")
        for word, count in zip(words[4::2], words[5::2]):
            objects[(word >> 16, word & 0xFFFF)] = objects.get((word >> 16, word & 0xFFFF), 0) + count
    return (data[pe + 26], data[pe + 27]), objects


def verify_toolchain(dll: str, data: bytes, compiles: list[str], toolchain: dict) -> None:
    """The recorded toolchain is the one the image names: the linker version, and at
    least one object of each recorded compiler build per compiled source of its kind."""
    linker, objects = pe_build(data)
    link = version(toolchain, "link")
    require(linker == link[:2] and objects.get((LINKER, link[2])),
            f"{dll} was not linked by the recorded {toolchain.get('link')}")
    for suffix, (product, tool) in OBJECTS.items():
        count = sum(PurePosixPath(path).suffix == suffix for path in compiles)
        if count:
            require(objects.get((product, version(toolchain, tool)[2]), 0) >= count,
                    f"{dll} lacks {count} {suffix} object(s) built by the recorded {toolchain.get(tool)}")


def file_offset(data: bytes, rva: int) -> int:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count, size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    for at in range(pe + 24 + size, pe + 24 + size + 40 * count, 40):
        virtual_size, address, raw_size, raw = struct.unpack_from("<IIII", data, at + 8)
        if address <= rva < address + max(virtual_size, raw_size):
            return raw + rva - address
    raise ValueError("Directory outside every section")


def debug_entries(data: bytes) -> list[tuple[int, int, int, int]]:
    """(file offset, type, size, file pointer) of each debug directory entry."""
    opt = struct.unpack_from("<I", data, 0x3C)[0] + 24
    debug, length = struct.unpack_from("<II", data, opt + 112 + 6 * 8)
    if not debug:
        return []
    start = file_offset(data, debug)
    return [(entry, *struct.unpack_from("<II4xI", data, entry + 12)) for entry in range(start, start + length // 28 * 28, 28)]


def link_identifiers(data: bytes) -> list[tuple[int, int]]:
    """(offset, size) of what relinking the same objects changes: the link
    timestamps, the image checksum and debug identifiers."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    coff, opt = pe + 4, pe + 24
    fields = [(coff + 4, 4), (opt + 64, 4)]
    export = struct.unpack_from("<I", data, opt + 112)[0]
    if export:
        fields.append((file_offset(data, export) + 4, 4))
    for entry, kind, size, pointer in debug_entries(data):
        fields.append((entry + 4, 4))
        if kind == 2 and size >= 24 and data[pointer:pointer + 4] == b"RSDS":
            fields.append((pointer + 4, 20))  # CodeView GUID and age.
        if kind == 16:
            fields.append((pointer, size))  # Reproducible-build hash.
    return fields


def normalized(data: bytes) -> str:
    """The image's hash with those fields and the embedded build identifier zeroed,
    not the inputs' digest beside it: equal for two builds of the same inputs, so
    it binds a packaged DLL to the build its record describes."""
    image = bytearray(data)
    found = MARKER.search(data)
    for start, size in link_identifiers(data) + ([(found.start(2), 32)] if found else []):
        image[start:start + size] = bytes(size)
    return digest(bytes(image))


def freeze(root: Path, tree: Path) -> dict[str, str]:
    """Copies what a build reads (FROZEN) into its folder; the hash of each file."""
    frozen = {}
    for top in FROZEN:
        for path in sorted((root / top).rglob("*")):
            name = path.relative_to(root).as_posix()
            if path.is_file() and "__pycache__" not in PurePosixPath(name).parts:
                data = path.read_bytes()
                (tree / name).parent.mkdir(parents=True, exist_ok=True)
                (tree / name).write_bytes(data)
                frozen[name] = digest(data)
    return frozen


def capture(build: Path, secret: str, root: Path = ROOT) -> dict:
    """Before bank_build.ps1 compiles: claims a new or empty folder for this build,
    freezes the research sources into it (TREE) and hashes what each packaged
    DLL's build reads there. The build compiles that copy; each DLL embeds its
    entry's digest and this build's identifier."""
    identity = build_id(secret)
    require(not build.exists() or (build.is_dir() and not any(build.iterdir())),
            f"{build} is not empty: each build needs a new or empty folder of its own")
    build.mkdir(parents=True, exist_ok=True)
    try:
        claim = (build / CAPTURE).open("x", encoding="utf-8", newline="\n")
    except FileExistsError:
        raise AssertionError(f"{build} is taken by another build") from None
    with claim:
        claim.write("{}\n")
    frozen = freeze(root, build / TREE)
    files = {}
    for dll in sorted(NATIVE):
        entry = build_inputs(build / TREE, dll)
        files[dll] = {**entry, "digest": inputs_digest(entry)}
    result = {"schema": 2, "build": identity, "files": files, "frozen": frozen,
              # For bank_build.ps1: what the DLL each builder script links embeds.
              "embed": {PurePosixPath(entry["script"]).name: entry["digest"] for entry in files.values()}}
    (build / CAPTURE).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    return result


def regenerated(tree: Path, frozen: dict) -> list[str]:
    """The frozen files the build rewrote: what its generators produced."""
    return [name for name, sha in sorted(frozen.items())
            if (tree / relative(name)).is_file() and digest((tree / relative(name)).read_bytes()) != sha]


def copy_back(root: Path, tree: Path, frozen: dict, names: list[str]) -> list[str]:
    """Copies rewritten files of the frozen copy into the checkout where it still
    has them as frozen (an edit made meanwhile stays); the names copied."""
    copied = []
    for name in names:
        target = root / relative(name)
        if target.is_file() and digest(target.read_bytes()) == frozen[name]:
            target.write_bytes((tree / relative(name)).read_bytes())
            copied.append(name)
    return copied


def record(build: Path, toolchain: dict, secret: str, root: Path = ROOT) -> tuple[dict, list[str]]:
    """native-build.json for the DLLs that bank_build.ps1 compiled from the inputs
    it froze, made once and only by that build, after its checks: it needs the
    build's secret, and every DLL must embed this build's identifier and the
    digest of its captured inputs, those inputs being as frozen still. The
    capture is consumed whatever the outcome. What the build's generators rewrote
    in the frozen copy returns to the checkout where it still has the frozen
    version: rewritten inputs at once (the next build compiles them), their other
    output with a record. Returns the record and the files that returned."""
    path = build / CAPTURE
    require(path.is_file(), f"No build captured its inputs in {build}: bank_build.ps1 does, before it compiles")
    text = path.read_text(encoding="utf-8")
    path.unlink()
    captured = json.loads(text)
    require(captured.get("schema") == 2 and set(captured.get("files") or {}) == NATIVE
            and isinstance(captured.get("frozen"), dict), "Unexpected build capture")
    identity = build_id(secret)
    require(captured.get("build") == identity,
            "This capture belongs to another build: only the build that captured its inputs records them")
    tree, frozen = build / TREE, captured["frozen"]
    inputs = {name for entry in captured["files"].values() for name in entry.get("inputs") or {}}
    rewritten = regenerated(tree, frozen)
    copied = copy_back(root, tree, frozen, [name for name in rewritten if name in inputs])
    files = {}
    for dll in sorted(NATIVE):
        entry = captured["files"][dll]
        require(entry.get("digest") == inputs_digest(entry), "Unexpected build capture")
        problems = drift(entry, build_inputs(tree, dll))
        require(not problems, f"The inputs of {dll} are not as this build froze them ({'; '.join(problems)}); "
                "build again" + (f" (back in the checkout: {', '.join(copied)})" if copied else ""))
        data = (build / dll).read_bytes()
        compiled_from, compiled_by = embedded(dll, data)
        require(compiled_by == identity, f"{dll} was not compiled by this build")
        require(compiled_from == entry["digest"], f"{dll} was compiled from other inputs than this build froze")
        verify_toolchain(dll, data, entry["compiles"], toolchain)
        files[dll] = {"sha256": digest(data), **entry}
    result = {"schema": 3, "build": identity, "toolchain": toolchain, "files": files}
    (build / RECORD).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    copied += copy_back(root, tree, frozen, [name for name in rewritten if name not in inputs])
    return result, copied


def sync(bundle: Path, root: Path = ROOT) -> dict:
    manifest = json.loads((bundle / "research-build.json").read_text(encoding="utf-8-sig"))
    require(manifest.get("researchOnly") is True, "Expected the offline candidate manifest")
    selected = manifest["files"]
    require({n for n in selected if n.endswith(".dll")} == NATIVE, "Unexpected native DLL set")
    planned, fresh = {}, {}
    for name, expected in selected.items():
        path = relative(name)
        if name in NATIVE:
            fresh[name] = (bundle / path).read_bytes()
            require(digest(fresh[name]) == expected, f"Native bundle checksum mismatch: {name}")
        elif name.startswith(("xp-banking/", "xp-banking-native/")) and path.suffix == ".lua":
            source = Path("research") / path
            planned[f"runtime/{name}"] = (source_bytes(root / source), {"source": source.as_posix()})
        elif name == "resources/CBMDOLD.menu":
            source = Path("research/xp-banking-native/dual_retired_menu.menu")
            planned["cbmdold.menu"] = (source_bytes(root / source), {"source": source.as_posix()})
        elif name != "resources/M_CBMBNK.lua":
            raise ValueError(f"Unreviewed bundle entry: {name}")
    built = json.loads((bundle / RECORD).read_text(encoding="utf-8"))
    require(built.get("schema") == 3 and set(built.get("files") or {}) == NATIVE, "Unexpected native build record")
    toolchain = built["toolchain"]
    package = root / PACKAGE
    for name, data in sorted(fresh.items()):
        entry = built["files"][name]
        require(entry.get("sha256") == digest(data), f"Native build record does not describe the bundle's {name}")
        current = build_inputs(root, name)
        problems = drift(entry, current)
        require(not problems, f"Native bundle {name} was built from other sources ({'; '.join(problems)})")
        expected = inputs_digest(current)
        require(entry.get("digest") == expected and embedded(name, data) == (expected, built.get("build")),
                f"Native bundle {name} does not embed the inputs and build its record names")
        verify_toolchain(name, data, current["compiles"], toolchain)
        # A packaged DLL that rebuilding the same inputs reproduces stays byte-identical.
        packaged, built_as = package / "native" / name, normalized(data)
        kept = packaged.read_bytes() if packaged.is_file() else None
        image = kept if kept is not None and normalized(kept) == built_as else data
        planned[f"native/{name}"] = (image, {"kind": "native", "build": {
            **current, "digest": expected, "id": embedded(name, image)[1], "normalizedSha256": built_as}})
    source = Path("research/xp-banking-native/bank_recruitment_patch.tpa")
    planned["bank_recruitment_patch.tpa"] = (source_bytes(root / source), {"source": source.as_posix()})
    require("runtime/xp-banking-native/bank_notice.lua" in planned, "Bundle selection lacks notice integration")
    require("runtime/xp-banking-native/bank_record.lua" in planned, "Bundle selection lacks record display integration")
    records = {}
    for name, (data, entry) in sorted(planned.items()):
        destination = package / relative(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        records[name] = {**entry, "sha256": digest(data)}
    result = {"schema": 3, "status": "experimental-unreleased", "nativePlaytestRequired": True,
              "toolchain": toolchain, "files": records}
    (package / "package-manifest.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    check(root)
    return result


def check(root: Path = ROOT) -> dict:
    package = root / PACKAGE
    manifest = json.loads((package / "package-manifest.json").read_text(encoding="utf-8"))
    require(manifest["schema"] == 3 and manifest["nativePlaytestRequired"] is True, "Unexpected package manifest")
    toolchain = manifest.get("toolchain") or {}
    actual_native = set()
    for name, entry in manifest["files"].items():
        data = (package / relative(name)).read_bytes()
        require(digest(data) == entry["sha256"], f"Package checksum mismatch: {name}")
        if "source" in entry:
            require(data == source_bytes(root / relative(entry["source"])), f"Canonical source changed: {name}")
            continue
        dll = PurePosixPath(name).name
        require(entry.get("kind") == "native" and name == f"native/{dll}" and dll in NATIVE,
                f"Unknown package record: {name}")
        actual_native.add(dll)
        build, current = entry.get("build") or {}, build_inputs(root, dll)
        problems = drift(build, current)
        require(not problems, f"Native build record of {dll} is stale ({'; '.join(problems)}): "
                              "rebuild with bank_build.ps1 and sync")
        expected = inputs_digest(current)
        require(build.get("digest") == expected and embedded(dll, data) == (expected, build.get("id")),
                f"{dll} does not embed the inputs and build its record names")
        require(normalized(data) == build.get("normalizedSha256"), f"{dll} is not the image its build record describes")
        verify_toolchain(dll, data, current["compiles"], toolchain)
    require(actual_native == NATIVE, "Missing or unexpected native DLL")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--capture", type=Path, metavar="BUILD",
                        help=f"before bank_build.ps1 compiles into BUILD, a new or empty folder: freeze and "
                             f"capture the inputs it reads (with that build's {SECRET})")
    parser.add_argument("--record", type=Path, metavar="BUILD",
                        help=f"after its checks: describe the DLLs that build compiled (with its {SECRET}; "
                             "reads its capture and toolchain.txt)")
    args = parser.parse_args()
    secret = os.environ.get(SECRET, "")
    if args.capture is not None:
        result = capture(args.capture, secret)
        print(f"Captured the inputs of {len(result['files'])} native DLLs in a frozen copy of "
              f"{len(result['frozen'])} research files; nothing built, installed or launched.")
        return
    if args.record is not None:
        result, copied = record(args.record, toolchain_from((args.record / "toolchain.txt").read_text(encoding="utf-8")),
                                secret)
        for name in copied:
            print(f"The build regenerated {name}: copied into the checkout.")
        print(f"Recorded how {len(result['files'])} native DLLs were built; nothing installed or launched.")
        return
    if args.check:
        manifest = check()
    else:
        if args.bundle is None:
            parser.error("--bundle is required when syncing")
        manifest = sync(args.bundle)
    print(f"Verified {len(manifest['files'])} campaign XP package files; nothing installed or launched.")


if __name__ == "__main__":
    main()
