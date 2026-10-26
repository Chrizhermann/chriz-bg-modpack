"""Source/package parity, real WeiDU synthetic installs, inert startup routing."""
from importlib import import_module
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

import pytest

from tools import sync_campaign_xp as package
from tests.test_utility_xp_installer import (
    ROOT, SETUP_NAME, WEIDU, SyntheticGame, _file_tree, _is_weidu_artifact,
)

SOURCE = ROOT / package.PACKAGE
PUBLICATIONS = {"m_cbmbnk.lua", "cbmbkcfg.lua", "cbmdold.menu"}
NATIVE_HOST = ("baldur.exe", "eeex.dll", "luabindings.dll", "luaprovider.dll", "infinityloaderdll.dll")


@pytest.mark.skipif(os.name != "nt" or WEIDU is None,
                   reason="Combined installer needs Windows to run the shipped scroll policy EXE and WeiDU")
def test_scroll_and_banking_publications_coexist_and_uninstall(tmp_path):
    from tests.test_scroll_runtime_installer import fixture

    game = fixture(tmp_path, kind="eet")
    native_headers(game)
    before = game_files(game)
    result, log = run_component(game, 430)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    scroll_only = game_files(game)
    for component in (650, 651):
        result, log = run_component(game, component)
        assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    combined = game_files(game)
    for name, data in scroll_only.items():
        assert combined[name] == data, name
    for name in PUBLICATIONS:
        assert "OVERRIDE/" + name.upper() in combined
    for component in (651, 650):
        result, log = run_component(game, component, uninstall=True)
        assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == scroll_only
    result, log = run_component(game, 430, uninstall=True)
    assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == before


def native_headers(game):
    header = bytearray(0x200)
    struct.pack_into("<H", header, 0, 0x5A4D)
    struct.pack_into("<I", header, 0x3C, 0x80)
    struct.pack_into("<IH", header, 0x80, 0x4550, 0x8664)
    struct.pack_into("<H", header, 0x98, 0x20B)
    for name in NATIVE_HOST:
        (game.root / name).write_bytes(header)
    (game.root / "infinityloader.db").write_text("; unrelated loader data\n", encoding="ascii")


def run_component(game, component, *, uninstall=False):
    result = subprocess.run([str(WEIDU), SETUP_NAME, "--game", str(game.root),
        "--force-uninstall-list" if uninstall else "--force-install-list", str(component),
        "--language", "0", "--use-lang", "en_us", "--no-exit-pause", "--noautoupdate", "--quick-log"],
        cwd=game.root, capture_output=True, text=True, timeout=60)
    return result, result.stdout + result.stderr


def game_files(game):
    return {name: data for name, data in _file_tree(game.root).items() if not _is_weidu_artifact(name)}


# 652 fixtures, shared with the release ZIP acceptance tests.
CHAPTER_GATE = 'GlobalGT("Chapter","GLOBAL",4)'
BAINVI_IDS = {
    "trigger": "0x4010 GlobalGT(S:Name*,S:Area*,I:Value*)\n",
    "action": "120 StartCutScene(S:CutScene*)\n121 StartCutSceneMode()\n122 ClearAllActions()\n",
}
BAINVI_VANILLA = (
    'IF\n'
    '  XPGT(Player1,10000)\n'
    '  Global("BA_START_SCENE","MYAREA",0)\n'
    'THEN\n'
    '  RESPONSE #100\n'
    '    SetGlobal("BA_START_SCENE","MYAREA",1)\n'
    '    ClearAllActions()\n'
    '    StartCutSceneMode()\n'
    '    StartCutScene("CUTBA01")\n'
    'END\n'
)
# Another mod's Baeloth scene: no BA_START_SCENE or CUTBA01 for 652 to recognise.
BAINVI_REPLACED_SCENE = (
    'IF\n'
    '  Global("OtherModBaelothScene","GLOBAL",0)\n'
    'THEN\n'
    '  RESPONSE #100\n'
    '    SetGlobal("OtherModBaelothScene","GLOBAL",1)\n'
    '    StartCutScene("OMBA01")\n'
    'END\n'
)
BAINVI_NOT_COMPILED = b"not a compiled script\n"
NO_GATE_WARNING = "without Baeloth's Chapter 5+ gate"
NO_GATE_REASONS = {
    "replaced_scene": "has no block that starts his Larswood entrance",
    "not_compiled": "not a valid compiled script",
}
UNRECOGNISED_BAINVI = {"replaced_scene": BAINVI_REPLACED_SCENE, "not_compiled": BAINVI_NOT_COMPILED}


def chapter_game(tmp_path, bainvi=None):
    """EET fixture for 650/652: native host stubs, EEex marker, BAINVI.BCS.

    ``bainvi`` is BAF source compiled to override/bainvi.bcs, raw bytes written
    there unchanged, or None for a game without the script.
    """
    from tests.test_recruitment_xp import make_game, compile_script
    game = make_game(tmp_path, game_type="eet")
    native_headers(game)
    (game.override / "m___eeex.lua").write_text("-- fixture\n")
    for name, rows in BAINVI_IDS.items():
        with (game.override / f"{name}.ids").open("a", encoding="ascii") as stream:
            stream.write(rows)
    if isinstance(bainvi, bytes):
        (game.override / "bainvi.bcs").write_bytes(bainvi)
    elif bainvi is not None:
        compile_script(game, "BAINVI", bainvi)
        (game.root / "bainvi.baf").unlink()
    return game


def test_package_matches_canonical_sources_and_six_reviewed_binaries():
    manifest = package.check()
    assert manifest["status"] == "experimental-unreleased"
    native = {Path(name).name for name in manifest["files"] if name.startswith("native/")}
    assert native == package.NATIVE
    assert "cbmbank_identity_only.dll" not in native
    for path in SOURCE.rglob("*.lua"):
        assert "cbm-bank-trial" not in path.read_text(), path
    assert all(len(Path(name).stem) <= 8 for name in PUBLICATIONS | {"cbmbkchp.lua", "cbmbksoa.lua"})
    tp2 = (ROOT / SETUP_NAME).read_text()
    for number in (650, 651, 652):
        block = tp2.split(f"BEGIN @{number} DESIGNATED {number}", 1)[1].split("BEGIN @", 1)[0]
        assert "INSTALL_BY_DEFAULT" not in block
    assert "REQUIRE_COMPONENT ~setup-chriz-bg-modpack.tp2~ ~650~" in tp2


def test_sync_rejects_changed_binary_before_writing_package(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    selected = {}
    for name in package.NATIVE:
        (bundle / name).write_bytes(b"native fixture")
        selected[name] = package.digest(b"native fixture")
    changed = next(iter(package.NATIVE))
    (bundle / changed).write_bytes(b"changed")
    (bundle / "research-build.json").write_text(json.dumps({"researchOnly": True, "files": selected}))
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(AssertionError, match="checksum mismatch"):
        package.sync(bundle, root)
    assert not (root / package.PACKAGE).exists()


CHECKED_SOURCES = {".lua", ".menu", ".tpa", ".cpp", ".h", ".inc", ".asm", ".ps1"}
SECRET, OTHER = "5e" * 32, "07" * 32  # What two bank_build.ps1 runs hold.


def checkout_copy(tmp_path):
    """The package and every source the check compares it with, outside the checkout."""
    root = tmp_path / "repo"
    shutil.copytree(SOURCE, root / package.PACKAGE)
    for folder in ("research/xp-banking", "research/xp-banking-native"):
        (root / folder).mkdir(parents=True)
        for path in (ROOT / folder).iterdir():
            if path.is_file() and path.suffix in CHECKED_SOURCES:
                shutil.copyfile(path, root / folder / path.name)
    return root


def section(data, name):
    """(file offset, size) of a PE section's raw data."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count, size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    for at in range(pe + 24 + size, pe + 24 + size + 40 * count, 40):
        if data[at:at + 8].rstrip(b"\0") == name:
            return struct.unpack_from("<I", data, at + 20)[0], struct.unpack_from("<I", data, at + 16)[0]
    raise AssertionError(name)


def linked_at(data, seconds):
    """The same objects linked again at that time: its COFF link time stamp."""
    image = bytearray(data)
    struct.pack_into("<I", image, struct.unpack_from("<I", data, 0x3C)[0] + 8, seconds)
    return bytes(image)


def embed(data, inputs, build):
    """The image as a build compiles it: its marker names those inputs and that build."""
    found = list(package.MARKER.finditer(data))
    assert len(found) == 1
    image = bytearray(data)
    image[found[0].start(1):found[0].end(1)] = inputs.encode("ascii")
    image[found[0].start(2):found[0].end(2)] = build.encode("ascii")
    return bytes(image)


def packaged(root, name):
    return (root / package.PACKAGE / "native" / name).read_bytes()


def staged(build, root, fresh=None, secret=SECRET):
    """bank_build.ps1 up to its --record: root's sources frozen into build, and its
    DLLs (packaged ones unless given) compiled there by this build."""
    captured = package.capture(build, secret, root)
    for name in package.NATIVE:
        data = (fresh or {}).get(name) or packaged(root, name)
        (build / name).write_bytes(embed(data, captured["files"][name]["digest"], captured["build"]))
    return build


def toolchain(root):
    return json.loads((root / package.PACKAGE / "package-manifest.json").read_text(encoding="utf-8"))["toolchain"]


def describe(bundle, root):
    """research-build.json as bank_build.ps1 writes it for that bundle."""
    manifest = json.loads((root / package.PACKAGE / "package-manifest.json").read_text(encoding="utf-8"))
    selected = {"resources/CBMDOLD.menu": "menu", "resources/M_CBMBNK.lua": "startup"}
    selected.update({name.removeprefix("runtime/"): "source" for name in manifest["files"] if name.startswith("runtime/")})
    selected.update({name: package.digest((bundle / name).read_bytes()) for name in package.NATIVE})
    (bundle / "research-build.json").write_text(json.dumps({"researchOnly": True, "files": selected}))


def candidate(tmp_path, root, fresh=None):
    """A bank_build.ps1 bundle whose DLLs (packaged ones unless given) were built
    from root's sources with the package's recorded toolchain."""
    bundle = staged(tmp_path / "bundle", root, fresh)
    describe(bundle, root)
    package.record(bundle, toolchain(root), SECRET, root)
    return bundle


def test_package_records_how_each_native_dll_was_built():
    manifest = package.check()
    assert set(package.BANNERS) <= set(manifest["toolchain"])
    for dll, script in package.BUILDERS.items():
        entry = manifest["files"][f"native/{dll}"]
        build = entry["build"]
        assert build["script"] == f"research/xp-banking-native/{script}"
        assert {"research/xp-banking-native/bank_build.ps1", build["script"], *build["compiles"]} <= set(build["inputs"])
        assert build["normalizedSha256"] == package.normalized((SOURCE / "native" / dll).read_bytes())
        # Every packaged DLL names the inputs it was compiled from, and its build.
        assert "research/xp-banking-native/cbm_build_inputs.cpp" in build["compiles"]
        assert package.embedded(dll, (SOURCE / "native" / dll).read_bytes()) == (build["digest"], build["id"])
        assert build["digest"] == package.inputs_digest(build)
    identity = manifest["files"]["native/cbmbank_identity.dll"]["build"]
    assert [Path(path).name for path in identity["compiles"]] == [
        "identity_native.cpp", "reset_native.cpp", "party_native.cpp", "award_native.cpp", "writer_native.cpp",
        "cbm_build_inputs.cpp"]
    # The include closure, not only the compiled files; a test-only include is no input.
    assert {"research/xp-banking-native/writer_native.h", "research/xp-banking-native/identity_native.h"} <= set(identity["inputs"])
    assert "research/xp-banking-native/writer_native_windows.inc" not in identity["inputs"]
    observer = manifest["files"]["native/dual_hp_observer.dll"]["build"]
    assert {"research/xp-banking-native/dual_hp_thunks.asm", "research/xp-banking-native/dual_choice_thunks.asm"} <= set(observer["compiles"])
    proficiency = manifest["files"]["native/dual_native_proficiency.dll"]["build"]
    assert "research/xp-banking-native/dual_native_proficiency_builds.inc" in proficiency["inputs"]


def edit(root, name, old, new):
    path = root / "research/xp-banking-native" / name
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (name, old)
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def flip(root, name):
    path = root / package.PACKAGE / "native" / name
    data = bytearray(path.read_bytes())
    at, _ = section(data, b".text")
    data[at + 0x40] ^= 1
    path.write_bytes(data)
    return bytes(data)


def rehash(root, name, data):
    path = root / package.PACKAGE / "package-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["files"][f"native/{name}"]["sha256"] = package.digest(data)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")


def remark(root, name, inputs=None, build=None):
    """The packaged image with other inputs or another build in its marker, rehashed."""
    data = packaged(root, name)
    old_inputs, old_build = package.embedded(name, data)
    data = embed(data, inputs or old_inputs, build or old_build)
    (root / package.PACKAGE / "native" / name).write_bytes(data)
    rehash(root, name, data)


def unmarked(data):
    """The image as a builder script run on its own compiles it: no inputs, no build."""
    found = package.MARKER.search(data)
    blank = b"cbm-build-inputs::".ljust(found.end() - found.start(), b"\0")
    return data[:found.start()] + blank + data[found.end():]


def unmark(root, name):
    data = unmarked(packaged(root, name))
    (root / package.PACKAGE / "native" / name).write_bytes(data)
    rehash(root, name, data)


def retool(root, tool, part):
    """Record another version of a tool: its major (0), minor (1) or build (2) moved on."""
    path = root / package.PACKAGE / "package-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    numbers = list(package.version(manifest["toolchain"], tool))
    old = ".".join(map(str, numbers))
    numbers[part] += 1
    manifest["toolchain"][tool] = manifest["toolchain"][tool].replace(old, ".".join(map(str, numbers)), 1)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")


STALE_RECORDS = {
    "source": (lambda root: edit(root, "writer_native.cpp", "namespace{\n", "namespace{ // changed\n"),
               r"cbmbank_identity\.dll is stale \(changed research/xp-banking-native/writer_native\.cpp\)"),
    "header": (lambda root: edit(root, "identity_native.h", "#pragma once", "#pragma once // changed"),
               r"cbmbank_identity\.dll is stale \(changed research/xp-banking-native/identity_native\.h\)"),
    "added include": (lambda root: ((root / "research/xp-banking-native/extra.h").write_text("#pragma once\n"),
                                    edit(root, "party_native.cpp", '#include "party_native.h"', '#include "party_native.h"\n#include "extra.h"')),
                      r"added research/xp-banking-native/extra\.h"),
    "unresolved include": (lambda root: edit(root, "party_native.cpp", '#include "party_native.h"', '#include "party_native.h"\n#include "missing.h"'),
                           r"cannot resolve include missing\.h"),
    "compiler flags": (lambda root: edit(root, "dual_prof_commit.ps1", '/O2 /LD "$source"', '/O1 /LD "$source"'),
                       r"dual_prof_commit\.dll is stale \(changed research/xp-banking-native/dual_prof_commit\.ps1\)"),
    "compiled sources": (lambda root: edit(root, "dual_skill_rows_check.ps1", ' "$PSScriptRoot/dual_skill_rows_lua.cpp"', ""),
                         r"dual_skill_rows\.dll is stale \(compiled sources are now research/xp-banking-native/dual_skill_rows\.cpp"),
    "build marker": (lambda root: edit(root, "cbm_build_inputs.cpp", "#define CBM_TEXT_", "// changed\n#define CBM_TEXT_"),
                     r"cbmbank_identity\.dll is stale \(changed research/xp-banking-native/cbm_build_inputs\.cpp\)"),
    "build driver": (lambda root: edit(root, "bank_build.ps1", "$ErrorActionPreference='Stop'", "$ErrorActionPreference='Stop' # changed"),
                     r"is stale \(changed research/xp-banking-native/bank_build\.ps1\)"),
    "packaged DLL": (lambda root: flip(root, "dual_old_hla.dll"), r"Package checksum mismatch: native/dual_old_hla\.dll"),
    "another image": (lambda root: rehash(root, "dual_old_hla.dll", flip(root, "dual_old_hla.dll")),
                      r"dual_old_hla\.dll is not the image its build record describes"),
    "embedded inputs": (lambda root: remark(root, "dual_old_hla.dll", inputs="0" * 64),
                        r"dual_old_hla\.dll does not embed the inputs and build its record names"),
    "embedded build": (lambda root: remark(root, "dual_old_hla.dll", build="0" * 32),
                       r"dual_old_hla\.dll does not embed the inputs and build its record names"),
    "no marker": (lambda root: unmark(root, "dual_prof_commit.dll"), r"dual_prof_commit\.dll embeds no build inputs"),
    "compiler build": (lambda root: retool(root, "cl", 2),
                       r"cbmbank_identity\.dll lacks 6 \.cpp object\(s\) built by the recorded"),
    "assembler build": (lambda root: retool(root, "ml64", 2),
                        r"dual_hp_observer\.dll lacks 2 \.asm object\(s\) built by the recorded"),
    "linker version": (lambda root: retool(root, "link", 0), r"cbmbank_identity\.dll was not linked by the recorded"),
    "linker build": (lambda root: retool(root, "link", 2), r"cbmbank_identity\.dll was not linked by the recorded"),
}


def test_a_dll_the_driver_does_not_build_has_no_build_inputs(tmp_path):
    root = checkout_copy(tmp_path)
    edit(root, "bank_build.ps1", "Invoke-Check 'dual_old_hla.ps1'\n", "")
    with pytest.raises(AssertionError, match=r"bank_build\.ps1 does not run dual_old_hla\.ps1"):
        package.build_inputs(root, "dual_old_hla.dll")


# MSVC names anonymous namespaces after the path of the file it compiles, and each
# build compiles its own frozen copy: a DLL that another build folder lays out
# differently can be neither kept by a sync nor checked by a fresh build.
def test_each_packaged_dll_compiles_the_same_in_every_build_folder():
    for dll, script in package.BUILDERS.items():
        text = (ROOT / "research/xp-banking-native" / script).read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if line.split()[:1] == ["cl"] and "/LD" in line.split()]
        assert len(lines) == 1 and "/experimental:deterministic" in lines[0].split(), (script, lines)
        assert re.search(r'(?<!\S)/pathmap:"\$(?:sourceDir|PSScriptRoot)"=research\\xp-banking-native(?!\S)', lines[0]), script


FOLDER_DEPENDENT = {
    "not deterministic": ("dual_old_hla.ps1", " /experimental:deterministic /pathmap", " /pathmap"),
    "folder not mapped": ("reset_check.ps1", ' /pathmap:"$sourceDir"=research\\xp-banking-native', ""),
    "mapped to the build": ("dual_skill_rows_check.ps1", "=research\\xp-banking-native", "=$build"),
    "mapped twice": ("dual_prof_commit.ps1", ' /pathmap:"$PSScriptRoot"=research\\xp-banking-native',
                     ' /pathmap:"$PSScriptRoot"=research\\xp-banking-native /pathmap:"$PSScriptRoot"=research\\xp-banking-native'),
}


@pytest.mark.parametrize("change", sorted(FOLDER_DEPENDENT))
def test_a_dll_whose_compile_depends_on_the_build_folder_has_no_build_inputs(tmp_path, change):
    root = checkout_copy(tmp_path)
    script, old, new = FOLDER_DEPENDENT[change]
    edit(root, script, old, new)
    dll = next(name for name, builder in package.BUILDERS.items() if builder == script)
    with pytest.raises(AssertionError, match=rf"{re.escape(script)}: {re.escape(dll)} would not compile the same in every build folder"):
        package.build_inputs(root, dll)
    with pytest.raises(AssertionError, match="would not compile the same in every build folder"):
        package.check(root)


def test_a_checkout_copy_passes_the_check(tmp_path):
    assert package.check(checkout_copy(tmp_path))["schema"] == 3


@pytest.mark.parametrize("change", sorted(STALE_RECORDS))
def test_check_fails_when_the_build_record_no_longer_describes_the_dll(tmp_path, change):
    root = checkout_copy(tmp_path)
    apply, message = STALE_RECORDS[change]
    apply(root)
    with pytest.raises((AssertionError, ValueError), match=message):
        package.check(root)


def test_check_survives_python_optimization(tmp_path):
    root = checkout_copy(tmp_path)
    STALE_RECORDS["source"][0](root)
    result = subprocess.run([sys.executable, "-O", "-c",
                             "import sys;from pathlib import Path;from tools import sync_campaign_xp as p;p.check(Path(sys.argv[1]))",
                             str(root)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0 and "is stale" in result.stderr, result.stderr


def test_normalization_masks_the_build_and_link_times_not_the_inputs():
    for name in package.NATIVE:
        data = (SOURCE / "native" / name).read_bytes()
        inputs, build = package.embedded(name, data)
        assert package.normalized(embed(data, inputs, "f" * 32)) == package.normalized(data), name
        assert package.normalized(linked_at(data, 12345)) == package.normalized(data), name
        assert package.normalized(embed(data, "f" * 64, build)) != package.normalized(data), name


def test_sync_keeps_a_packaged_dll_that_a_new_build_reproduces(tmp_path):
    root = checkout_copy(tmp_path)
    before = {name: packaged(root, name) for name in package.NATIVE}
    package.sync(candidate(tmp_path, root), root)
    manifest = package.check(root)
    for name, data in before.items():
        assert packaged(root, name) == data, name
        build = manifest["files"][f"native/{name}"]["build"]
        assert build["normalizedSha256"] == package.normalized(data)
        assert build["id"] == package.embedded(name, data)[1] != package.build_id(SECRET)  # The kept image's build.
    written = (root / package.PACKAGE / "package-manifest.json").read_bytes()
    assert b"\r\n" not in written and written.endswith(b"}\n")
    assert b"\r\n" not in (root / package.PACKAGE / "runtime/xp-banking-native/bank_notice.lua").read_bytes()


def test_sync_takes_a_rebuilt_dll_that_differs_from_the_packaged_one(tmp_path):
    root = checkout_copy(tmp_path)
    original = packaged(root, "dual_prof_commit.dll")
    rebuilt = bytearray(original)
    at, _ = section(rebuilt, b".text")
    rebuilt[at + 0x40] ^= 1
    bundle = candidate(tmp_path, root, {"dual_prof_commit.dll": bytes(rebuilt)})
    package.sync(bundle, root)
    taken = (bundle / "dual_prof_commit.dll").read_bytes()
    assert packaged(root, "dual_prof_commit.dll") == taken
    assert package.normalized(taken) == package.normalized(bytes(rebuilt)) != package.normalized(original)
    entry = package.check(root)["files"]["native/dual_prof_commit.dll"]
    assert entry["sha256"] == package.digest(taken) and entry["build"]["id"] == package.build_id(SECRET)


def test_sync_refuses_a_candidate_built_from_other_sources(tmp_path):
    root = checkout_copy(tmp_path)
    bundle = candidate(tmp_path, root)
    STALE_RECORDS["header"][0](root)
    before = (root / package.PACKAGE / "package-manifest.json").read_bytes()
    with pytest.raises(AssertionError, match=r"cbmbank_identity\.dll was built from other sources "
                                             r"\(changed research/xp-banking-native/identity_native\.h\)"):
        package.sync(bundle, root)
    assert (root / package.PACKAGE / "package-manifest.json").read_bytes() == before


@pytest.mark.parametrize("field", ["inputs", "build"])
def test_sync_refuses_a_bundle_dll_that_embeds_other_inputs_or_another_build(tmp_path, field):
    root = checkout_copy(tmp_path)
    bundle = candidate(tmp_path, root)
    name = "dual_skill_rows.dll"
    data = (bundle / name).read_bytes()
    inputs, build = package.embedded(name, data)
    data = embed(data, "0" * 64, build) if field == "inputs" else embed(data, inputs, package.build_id(OTHER))
    (bundle / name).write_bytes(data)
    built = json.loads((bundle / package.RECORD).read_text(encoding="utf-8"))
    built["files"][name]["sha256"] = package.digest(data)  # A record and manifest that describe it.
    (bundle / package.RECORD).write_text(json.dumps(built), encoding="utf-8")
    describe(bundle, root)
    before = (root / package.PACKAGE / "package-manifest.json").read_bytes()
    with pytest.raises(AssertionError, match=r"Native bundle dual_skill_rows\.dll does not embed the inputs "
                                             r"and build its record names"):
        package.sync(bundle, root)
    assert (root / package.PACKAGE / "package-manifest.json").read_bytes() == before


def test_record_describes_what_its_build_compiled_from_the_frozen_inputs(tmp_path):
    root = checkout_copy(tmp_path)
    build = staged(tmp_path / "build", root)
    captured = json.loads((build / package.CAPTURE).read_text(encoding="utf-8"))
    # The frozen copy is the research sources as they were when the build began.
    assert captured["frozen"] == {path.relative_to(root).as_posix(): package.digest(path.read_bytes())
                                  for top in package.FROZEN for path in (root / top).rglob("*") if path.is_file()}
    assert {name: package.digest((build / package.TREE / name).read_bytes()) for name in captured["frozen"]} == captured["frozen"]
    result, copied = package.record(build, toolchain(root), SECRET, root)
    assert result["schema"] == 3 and result["build"] == captured["build"] == package.build_id(SECRET) and copied == []
    for dll in package.NATIVE:
        entry = result["files"][dll]
        data = (build / dll).read_bytes()
        assert entry == {"sha256": package.digest(data), **captured["files"][dll]}
        assert {key: entry[key] for key in ("script", "compiles", "inputs")} == package.build_inputs(root, dll)
        assert package.embedded(dll, data) == (entry["digest"], result["build"])
        assert captured["embed"][Path(entry["script"]).name] == entry["digest"]
    assert json.loads((build / package.RECORD).read_text(encoding="utf-8")) == result
    # One capture serves one record: a second one has nothing to bind DLLs to.
    with pytest.raises(AssertionError, match="No build captured its inputs"):
        package.record(build, toolchain(root), SECRET, root)


def test_a_build_needs_a_new_or_empty_folder_of_its_own(tmp_path):
    root = checkout_copy(tmp_path)
    used = tmp_path / "used"
    used.mkdir()
    (used / "dual_old_hla.dll").write_bytes(packaged(root, "dual_old_hla.dll"))  # An earlier build's output.
    with pytest.raises(AssertionError, match="is not empty: each build needs a new or empty folder of its own"):
        package.capture(used, SECRET, root)
    assert [path.name for path in used.iterdir()] == ["dual_old_hla.dll"]
    package.capture(tmp_path / "empty", SECRET, root)
    with pytest.raises(AssertionError, match="is not empty"):  # Nor can a second build share a folder.
        package.capture(tmp_path / "empty", OTHER, root)
    with pytest.raises(AssertionError, match=f"{package.SECRET} must hold this build's secret"):
        package.capture(tmp_path / "unclaimed", "", root)
    assert not (tmp_path / "unclaimed").exists()


def test_of_two_builds_racing_for_one_folder_only_the_first_claims_it(tmp_path):
    root = checkout_copy(tmp_path)
    first = tmp_path / "build"

    class Racing(type(first)):  # The other build claims the folder after this one found it empty.
        def mkdir(self, *arguments, **options):
            super().mkdir(*arguments, **options)
            if not (self / package.CAPTURE).exists():
                package.capture(type(first)(self), OTHER, root)

    with pytest.raises(AssertionError, match="is taken by another build"):
        package.capture(Racing(first), SECRET, root)
    claimed = json.loads((first / package.CAPTURE).read_text(encoding="utf-8"))
    assert claimed["build"] == package.build_id(OTHER)  # The first claim stands, untouched.


def test_a_standalone_record_blesses_no_existing_dll(tmp_path):
    root = checkout_copy(tmp_path)
    build = staged(tmp_path / "build", root)
    (build / package.CAPTURE).unlink()  # DLLs compiled, but no build that captured is left.
    with pytest.raises(AssertionError, match="No build captured its inputs"):
        package.record(build, toolchain(root), SECRET, root)
    assert not (build / package.RECORD).exists()


def test_only_the_build_that_captured_records(tmp_path):
    root = checkout_copy(tmp_path)
    build = staged(tmp_path / "build", root)
    with pytest.raises(AssertionError, match="This capture belongs to another build"):
        package.record(build, toolchain(root), OTHER, root)
    assert not (build / package.RECORD).exists()
    with pytest.raises(AssertionError, match="No build captured its inputs"):  # That attempt consumed it.
        package.record(build, toolchain(root), SECRET, root)
    with pytest.raises(AssertionError, match=f"{package.SECRET} must hold this build's secret"):
        package.record(staged(tmp_path / "again", root), toolchain(root), "", root)


@pytest.mark.parametrize("other_sources", [False, True])
def test_record_refuses_a_dll_another_worktree_built(tmp_path, other_sources):
    # Codex's case: a DLL linked after this capture, by a build elsewhere.
    root = checkout_copy(tmp_path)
    elsewhere = checkout_copy(tmp_path / "elsewhere")
    if other_sources:
        STALE_RECORDS["source"][0](elsewhere)
    other = staged(tmp_path / "other", elsewhere, secret=OTHER)
    build = staged(tmp_path / "build", root)
    shutil.copyfile(other / "cbmbank_identity.dll", build / "cbmbank_identity.dll")
    with pytest.raises(AssertionError, match=r"cbmbank_identity\.dll was not compiled by this build"):
        package.record(build, toolchain(root), SECRET, root)
    assert not (build / package.RECORD).exists()


def test_record_refuses_a_dll_this_build_compiled_from_other_inputs(tmp_path):
    root = checkout_copy(tmp_path)
    build = staged(tmp_path / "build", root)
    image = (build / "dual_hp_observer.dll").read_bytes()
    (build / "dual_hp_observer.dll").write_bytes(embed(image, "0" * 64, package.build_id(SECRET)))
    with pytest.raises(AssertionError, match=r"dual_hp_observer\.dll was compiled from other inputs than this build froze"):
        package.record(build, toolchain(root), SECRET, root)


def test_record_refuses_a_dll_a_builder_script_compiled_on_its_own(tmp_path):
    root = checkout_copy(tmp_path)
    build = staged(tmp_path / "build", root)
    (build / "dual_skill_rows.dll").write_bytes(unmarked((build / "dual_skill_rows.dll").read_bytes()))
    with pytest.raises(AssertionError, match=r"dual_skill_rows\.dll embeds no build inputs"):
        package.record(build, toolchain(root), SECRET, root)


def test_record_refuses_a_dll_that_names_two_builds(tmp_path):
    # A second marker (here in an appended overlay, which the loader ignores) would
    # leave it open which build and inputs the DLL belongs to.
    root = checkout_copy(tmp_path)
    build = staged(tmp_path / "build", root)
    data = (build / "dual_skill_rows.dll").read_bytes()
    found = package.MARKER.search(data)
    (build / "dual_skill_rows.dll").write_bytes(data + embed(data, "0" * 64, "0" * 32)[found.start():found.end()])
    with pytest.raises(AssertionError, match=r"dual_skill_rows\.dll embeds 2 build input markers"):
        package.record(build, toolchain(root), SECRET, root)
    assert not (build / package.RECORD).exists()


def test_an_abandoned_capture_records_nothing(tmp_path):
    # Codex's case: a build captured, then stopped (a check failed) a day ago; DLLs
    # in its folder, its own or dropped in later, stay unrecorded.
    root = checkout_copy(tmp_path)
    build = staged(tmp_path / "build", root)
    day_ago = time.time_ns() - 86400 * 10**9
    for path in build.iterdir():
        os.utime(path, ns=(day_ago, day_ago))
    with pytest.raises(AssertionError, match="This capture belongs to another build"):
        package.record(build, toolchain(root), OTHER, root)  # Another run, with its own secret.
    with pytest.raises(AssertionError, match="No build captured its inputs"):
        package.record(build, toolchain(root), SECRET, root)  # Consumed by that attempt.
    with pytest.raises(AssertionError, match="is not empty"):
        package.capture(build, OTHER, root)  # And no new build adopts the folder.
    assert not (build / package.RECORD).exists()


def test_record_refuses_an_earlier_builds_image_from_the_same_second(tmp_path):
    # Codex's case: images an earlier build linked in the second this build
    # captured, copied in afterwards with a fresh modification time.
    root = checkout_copy(tmp_path)
    earlier = staged(tmp_path / "earlier", root, secret=OTHER)
    build = staged(tmp_path / "build", root)
    second = int(time.time())
    for name in package.NATIVE:
        (build / name).write_bytes(linked_at((earlier / name).read_bytes(), second))
    with pytest.raises(AssertionError, match=r"\.dll was not compiled by this build"):
        package.record(build, toolchain(root), SECRET, root)
    assert not (build / package.RECORD).exists()


@pytest.mark.parametrize("shift", [-86400, -1, 0, 86400])
def test_no_clock_change_refuses_a_builds_own_dlls(tmp_path, shift):
    # Codex's case: the clock moved between capture and link. No time decides anything.
    root = checkout_copy(tmp_path)
    build = staged(tmp_path / "build", root)
    at = int(time.time()) + shift
    for name in package.NATIVE:
        (build / name).write_bytes(linked_at((build / name).read_bytes(), at))
        os.utime(build / name, (at, at))
    result, _ = package.record(build, toolchain(root), SECRET, root)
    assert set(result["files"]) == package.NATIVE


def test_a_checkout_edit_during_the_build_reaches_sync_not_the_record(tmp_path):
    # The build compiles its frozen copy, so an edit saved meanwhile is in none of
    # its DLLs: the record stands, and sync refuses them for the edited sources.
    root = checkout_copy(tmp_path)
    bundle = staged(tmp_path / "bundle", root)
    STALE_RECORDS["source"][0](root)
    describe(bundle, root)
    result, copied = package.record(bundle, toolchain(root), SECRET, root)
    assert copied == [] and result["files"]["cbmbank_identity.dll"]["inputs"] == \
        package.build_inputs(bundle / package.TREE, "cbmbank_identity.dll")["inputs"]
    with pytest.raises(AssertionError, match=r"cbmbank_identity\.dll was built from other sources "
                                             r"\(changed research/xp-banking-native/writer_native\.cpp\)"):
        package.sync(bundle, root)


def test_record_refuses_an_input_the_build_rewrote_and_returns_it(tmp_path):
    # A probe regenerated a native input in the frozen copy after the capture (as
    # dual_proficiency_probe.py --generate may its .inc): the DLL holds either text.
    root = checkout_copy(tmp_path)
    build = staged(tmp_path / "build", root)
    name = "research/xp-banking-native/dual_native_proficiency_builds.inc"
    frozen = build / package.TREE / name
    frozen.write_bytes(frozen.read_bytes() + b"// regenerated\n")
    with pytest.raises(AssertionError, match=r"The inputs of dual_native_proficiency\.dll are not as this build froze them \(changed "
                                             + re.escape(name) + r"\); build again \(back in the checkout: " + re.escape(name)):
        package.record(build, toolchain(root), SECRET, root)
    assert (root / name).read_bytes() == frozen.read_bytes()  # The next build compiles it from the start.


def test_what_the_probes_regenerated_returns_with_the_record(tmp_path):
    root = checkout_copy(tmp_path)
    native = root / "research/xp-banking-native"
    for name in ("dual-skill-row-results.json", "dual-hp-check-results.json"):
        (native / name).write_bytes(b'{"old": true}\n')
    build = staged(tmp_path / "build", root)
    tree = build / package.TREE / "research/xp-banking-native"
    for name in ("dual-skill-row-results.json", "dual-hp-check-results.json", "dual_manual_profiles.lua"):
        (tree / name).write_bytes(b"regenerated " + name.encode() + b"\n")
    (native / "dual-hp-check-results.json").write_bytes(b'{"edited meanwhile": true}\n')  # Stays.
    result, copied = package.record(build, toolchain(root), SECRET, root)
    assert copied == ["research/xp-banking-native/dual-skill-row-results.json",
                      "research/xp-banking-native/dual_manual_profiles.lua"]
    assert (native / "dual-skill-row-results.json").read_bytes() == b"regenerated dual-skill-row-results.json\n"
    assert (native / "dual_manual_profiles.lua").read_bytes() == b"regenerated dual_manual_profiles.lua\n"
    assert (native / "dual-hp-check-results.json").read_bytes() == b'{"edited meanwhile": true}\n'


def test_a_refused_record_returns_no_results(tmp_path):
    root = checkout_copy(tmp_path)
    native = root / "research/xp-banking-native"
    (native / "dual-skill-row-results.json").write_bytes(b'{"old": true}\n')
    build = staged(tmp_path / "build", root)
    (build / package.TREE / "research/xp-banking-native/dual-skill-row-results.json").write_bytes(b"regenerated\n")
    (build / "dual_old_hla.dll").write_bytes(packaged(root, "dual_old_hla.dll"))  # Not this build's.
    with pytest.raises(AssertionError, match=r"dual_old_hla\.dll was not compiled by this build"):
        package.record(build, toolchain(root), SECRET, root)
    assert (native / "dual-skill-row-results.json").read_bytes() == b'{"old": true}\n'


def test_record_refuses_a_capture_changed_after_the_build_froze_it(tmp_path):
    root = checkout_copy(tmp_path)
    for rehashed in (False, True):
        build = staged(tmp_path / f"build-{rehashed}", root)
        capture = json.loads((build / package.CAPTURE).read_text(encoding="utf-8"))
        entry = capture["files"]["dual_old_hla.dll"]
        entry["inputs"][entry["compiles"][0]] = "0" * 64  # As if the capture had read other content.
        if rehashed:
            entry["digest"] = package.inputs_digest(entry)
        (build / package.CAPTURE).write_text(json.dumps(capture), encoding="utf-8")
        message = r"The inputs of dual_old_hla\.dll are not as this build froze them \(changed " if rehashed else "Unexpected build capture"
        with pytest.raises(AssertionError, match=message):
            package.record(build, toolchain(root), SECRET, root)


def test_a_failed_record_needs_a_new_build(tmp_path):
    root = checkout_copy(tmp_path)
    build = staged(tmp_path / "build", root)
    own = (build / "dual_prof_commit.dll").read_bytes()
    (build / "dual_prof_commit.dll").write_bytes(packaged(root, "dual_prof_commit.dll"))  # An earlier build's.
    with pytest.raises(AssertionError, match=r"dual_prof_commit\.dll was not compiled by this build"):
        package.record(build, toolchain(root), SECRET, root)
    (build / "dual_prof_commit.dll").write_bytes(own)  # Its own image back: no capture is left to bind it to.
    with pytest.raises(AssertionError, match="No build captured its inputs"):
        package.record(build, toolchain(root), SECRET, root)


def test_the_driver_compiles_only_its_frozen_copy():
    driver = (ROOT / "research/xp-banking-native/bank_build.ps1").read_text(encoding="utf-8")
    assert driver.startswith("param([Parameter(Mandatory=$true)][string]$BuildDir)\n")  # No shared default folder.
    assert f"$sources=Join-Path $build '{package.TREE}/{package.NATIVE_SOURCES}'" in driver
    assert "try {& (Join-Path $sources $script) -BuildDir $build}" in driver
    # After the capture nothing is read beside the driver but the sync tool itself.
    assert re.findall(r"\$PSScriptRoot\b.*", driver) == ["$PSScriptRoot -Parent) -Parent) 'tools/sync_campaign_xp.py'"]
    # Nor does the environment add compiler or linker options to the frozen scripts' own.
    assert "$injected='CL','_CL_','LINK','_LINK_'" in driver
    check = driver[driver.index("function Invoke-Check"):driver.index("Invoke-Check 'identity_check.ps1'")]
    assert "[Environment]::SetEnvironmentVariable($name,$null)" in check
    assert check.index("SetEnvironmentVariable($name,$null)") < check.index("try {& (Join-Path $sources $script)")
    assert "[Environment]::SetEnvironmentVariable($name,$saved[$name])" in check.split("finally", 1)[1]


def test_the_command_line_captures_and_records_once_with_the_builds_secret(tmp_path):
    command = [sys.executable, "-I", str(ROOT / "tools/sync_campaign_xp.py")]
    environment = {key: value for key, value in os.environ.items() if key != package.SECRET}
    holding = {**environment, package.SECRET: SECRET}
    result = subprocess.run(command + ["--capture", str(tmp_path / "none")], capture_output=True, text=True, env=environment)
    assert result.returncode != 0 and "must hold this build's secret" in result.stderr and not (tmp_path / "none").exists()
    build = tmp_path / "build"
    result = subprocess.run(command + ["--capture", str(build)], capture_output=True, text=True, env=holding)
    assert result.returncode == 0 and "Captured the inputs of 6 native DLLs" in result.stdout, result.stderr
    captured = json.loads((build / package.CAPTURE).read_text(encoding="utf-8"))
    for name in package.NATIVE:
        (build / name).write_bytes(embed((SOURCE / "native" / name).read_bytes(), captured["files"][name]["digest"],
                                         captured["build"]))
    banners = "\r\n".join(toolchain(ROOT)[tool] for tool in package.BANNERS)
    (build / "toolchain.txt").write_text(banners + "\r\n", encoding="utf-8")
    result = subprocess.run(command + ["--record", str(build)], capture_output=True, text=True, env=holding)
    assert result.returncode == 0 and "Recorded how 6 native DLLs were built" in result.stdout, result.stderr
    result = subprocess.run(command + ["--record", str(build)], capture_output=True, text=True, env=holding)
    assert result.returncode != 0 and "No build captured its inputs" in result.stderr


def test_toolchain_capture_reads_the_version_banners():
    text = ("'vswhere.exe' is not recognized as an internal or external command,\r\n"
            "Microsoft (R) C/C++ Optimizing Compiler Version 19.44.35228 for x64\r\n"
            "Microsoft (R) Incremental Linker Version 14.44.35228.0\r\n"
            "Microsoft (R) Macro Assembler (x64) Version 14.44.35228.0\r\n"
            "VCToolsVersion=14.44.35207\r\nWindowsSDKVersion=10.0.26100.0\\\r\nUCRTVersion=\r\n")
    toolchain = package.toolchain_from(text)
    assert toolchain == {"cl": "Microsoft (R) C/C++ Optimizing Compiler Version 19.44.35228 for x64",
                         "link": "Microsoft (R) Incremental Linker Version 14.44.35228.0",
                         "ml64": "Microsoft (R) Macro Assembler (x64) Version 14.44.35228.0",
                         "VCToolsVersion": "14.44.35207", "WindowsSDKVersion": "10.0.26100.0"}
    assert package.version(toolchain, "cl") == (19, 44, 35228)
    with pytest.raises(ValueError, match="lacks the ml64 version banner"):
        package.toolchain_from(text.replace("Macro Assembler", "Assembler"))


def test_text_mirrors_use_stable_repository_line_endings(tmp_path):
    source = tmp_path / "source.lua"
    source.write_bytes(b"line one\r\nline two\n")
    assert package.source_bytes(source) == b"line one\nline two\n"
    manifest = package.check()
    for name, record in manifest["files"].items():
        if "source" in record:
            assert b"\r\n" not in (SOURCE / name).read_bytes(), name


@pytest.mark.parametrize("name", ["../outside", "C:/outside", "x/../../outside", "x\\outside"])
def test_manifest_paths_remain_inside_package(name):
    with pytest.raises(ValueError, match="Unsafe"):
        package.relative(name)


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
@pytest.mark.parametrize(
    "config,policy",
    [("cbmbkcfg.lua", "bg1_sod"), ("cbmbksoa.lua", "bg1_sod_soa"), ("cbmbkchp.lua", "chapter_caps")],
)
def test_startup_uses_normal_package_and_selected_policy_once(flavor, config, policy):
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.globals().config = (SOURCE / config).read_text()
    lua.globals().expected = policy
    lua.execute('''
        EEex_Active=true; calls=0
        gameReady=false;initListeners={}
        function EEex_GameState_AddInitializedListener(f) initListeners[#initListeners+1]=f end
        function initialize() gameReady=true;for _,f in ipairs(initListeners) do f() end;initListeners={} end
        function Infinity_DoFile(name) assert(name=='CBMBKCFG');assert(loadstring(config))() end
        function dofile(path)
            assert(path=='chriz-bg-modpack/campaign-xp/runtime/xp-banking-native/bank_bootstrap.lua')
            return {Install=function(o)
                assert(gameReady,'bank must start only once the game object exists')
                calls=calls+1;assert(o.policy==expected and o.researchOnly)
                assert(o.dllPath=='chriz-bg-modpack/campaign-xp/native/cbmbank_identity.dll')
                assert(o.progressionDLLDirectory=='chriz-bg-modpack/campaign-xp/native')
                assert(o.researchDir=='chriz-bg-modpack/campaign-xp/runtime')
                return true
            end}
        end
        function print()end
    ''')
    loader = (SOURCE / "m_cbmbnk.lua").read_text()
    lua.execute(loader)
    lua.execute(loader)
    # Loading the file only registers the start; the game object does not exist yet.
    assert lua.globals().calls == 0
    lua.execute("initialize()")
    assert lua.globals().calls == 1
    lua.execute(loader)
    assert lua.globals().calls == 1


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
def test_scroll_casting_starts_the_bank_first_and_it_runs_once(flavor):
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        EEex_Active=true; calls=0
        gameReady=false;initListeners={}
        function EEex_GameState_AddInitializedListener(f) initListeners[#initListeners+1]=f end
        function Infinity_DoFile(name) CBMBank_Config={schema=1,policy='bg1_sod'} end
        function dofile() return {Install=function()
            assert(gameReady,'bank must start only once the game object exists')
            calls=calls+1;CBMBank_Identity={ActorDestroyChain=function() end};return true end} end
        function print() end
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    # Scroll casting's earlier listener runs first and starts the bank; the bank's own
    # listener then finds it started.
    lua.execute('''
        gameReady=true
        CBMBank_Start();assert(calls==1 and CBMBank_Identity)
        for _,f in ipairs(initListeners) do f() end
        assert(calls==1)
    ''')
    # A running bank owns the rerouted names; the loader defines no fallback.
    lua.execute("assert(CBMBank_ActiveXP==nil and CBMBank_ImoenXPSet==nil and CBMBank_Catchup==nil)")


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
def test_without_eeex_startup_reports_at_load_and_keeps_pre_650_behavior(flavor):
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        printed={}
        function print(s) printed[#printed+1]=s end
        function dofile() error('nothing may load without EEex') end
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    lua.execute('''
        assert(#printed==1 and printed[1]:find('EEex is unavailable',1,true))
        assert(type(CBMBank_ActiveXP)=='function' and type(CBMBank_ImoenXPSet)=='function')
        assert(type(CBMBank_Catchup)=='function')
    ''')


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
def test_failed_startup_falls_back_only_for_names_nothing_owns(flavor):
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        EEex_Active=true
        gameReady=false;initListeners={}
        function EEex_GameState_AddInitializedListener(f) initListeners[#initListeners+1]=f end
        function initialize() gameReady=true;for _,f in ipairs(initListeners) do f() end;initListeners={} end
        function Infinity_DoFile(name) CBMBank_Config={schema=1,policy='bg1_sod'} end
        function dofile() return {Install=function() error('injected startup failure') end} end
        function print() end
        owned=function() end;CBMBank_ImoenXPSet=owned
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    lua.execute("assert(CBMBank_ActiveXP==nil and CBMBank_Catchup==nil);initialize()")
    lua.execute('''
        assert(CBMBank_ImoenXPSet==owned)
        assert(type(CBMBank_ActiveXP)=='function' and type(CBMBank_Catchup)=='function')
    ''')


WARNING_HARNESS = '''
    EEex_Active=true
    gameReady=false;initListeners={};actionListeners={};destroyedListeners={};shown={};printed={}
    function EEex_GameState_AddInitializedListener(f) initListeners[#initListeners+1]=f end
    function EEex_Action_AddSpriteStartedActionListener(f) actionListeners[#actionListeners+1]=f end
    function EEex_GameState_AddDestroyedListener(f) destroyedListeners[#destroyedListeners+1]=f end
    function initialize() gameReady=true;for _,f in ipairs(initListeners) do f() end;initListeners={} end
    function act(n) for i=1,n do for _,f in ipairs(actionListeners) do assert(f({},{})==nil) end end end
    function destroy() for _,f in ipairs(destroyedListeners) do f() end end
    function Infinity_DisplayString(s) shown[#shown+1]=s end
    function Infinity_DoFile(name) CBMBank_Config={schema=1,policy='bg1_sod'} end
    function print(s) printed[#printed+1]=s end
'''


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
def test_failed_startup_shows_nothing_unasked_and_the_status_command_explains(flavor):
    # The live failure of 2026-10-13 left only the loader log line. The game
    # shows no technical notice unasked (Christopher, 2026-10-25): the loader
    # log has the failure, and CBMBank_Status(), run in the console, explains it.
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute(WARNING_HARNESS + '''
        function dofile() return {Install=function() error(
            '...ign-xp/runtime/xp-banking-native/dual_combined_hooks.lua:36: '..
            'EEex stats relay does not preserve native first call',0) end} end
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    lua.execute('''
        assert(#actionListeners==0 and CBMBank_Status==nil);initialize()
        assert(#printed==1 and printed[1]:find('Startup failed; stop and review the log before playing: '..
            '...ign-xp/runtime/xp-banking-native/dual_combined_hooks.lua:36: EEex stats relay',1,true))
        -- Nothing listens for actions or loaded games: nothing is shown unasked.
        assert(#actionListeners==0 and #destroyedListeners==0)
        act(3);destroy();act(2);assert(#shown==0)
        local text=CBMBank_Status()
        assert(#shown==1 and shown[1]==text)
        assert(text:find('did not start, so XP is not capped or banked',1,true))
        assert(text:find('Reason: dual_combined_hooks.lua:36: EEex stats relay does not '..
            'preserve native first call',1,true))
        assert(not text:find('runtime/',1,true))
    ''')


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
def test_started_bank_adds_no_failure_warning(flavor):
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute(WARNING_HARNESS + '''
        function dofile() return {Install=function() assert(gameReady);return true end} end
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    lua.execute('''
        initialize();act(2)
        assert(#actionListeners==0 and #destroyedListeners==0 and #shown==0)
        assert(CBMBank_Status==nil and printed[1]:find('initialized',1,true))
    ''')


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
def test_failed_startup_leaves_an_owned_status_command_and_works_without_eeex(flavor):
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute(WARNING_HARNESS + '''
        function dofile() return {Install=function() error('injected startup failure',0) end} end
        owned=function() return 'owned' end;CBMBank_Status=owned
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    lua.execute('''
        initialize();assert(CBMBank_Status==owned)
        act(1);assert(#shown==0 and #printed==1 and printed[1]:find('injected startup failure',1,true))
    ''')
    # Without EEex nothing can be listened to; the status command still explains.
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        shown={}
        function print() end
        function Infinity_DisplayString(s) shown[#shown+1]=s end
        function dofile() error('nothing may load without EEex') end
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    lua.execute('''
        assert(#shown==0)
        local text=CBMBank_Status()
        assert(text:find('did not start',1,true) and text:find('EEex is unavailable; launch using InfinityLoader',1,true))
        assert(#shown==1 and shown[1]==text)
    ''')


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU or WEIDU_BIN")
@pytest.mark.parametrize("prior", [False, True])
def test_base_soa_dependency_and_exact_uninstall(tmp_path, prior):
    game = SyntheticGame(tmp_path / "game", game="eet")
    native_headers(game)
    if prior:
        for name in PUBLICATIONS:
            (game.override / name).write_bytes(b"foreign prior bytes\x00\xff\r\n")
    before = game_files(game)
    result, log = run_component(game, 651)
    assert result.returncode == 0 and "SKIPPING:" in log, log
    assert game_files(game) == before
    result, log = run_component(game, 650)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    base = game_files(game)
    expected = dict(before)
    for name in PUBLICATIONS:
        expected["OVERRIDE/" + name.upper()] = (SOURCE / name).read_bytes()
    assert base == expected
    result, log = run_component(game, 651)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    expected["OVERRIDE/CBMBKCFG.LUA"] = (SOURCE / "cbmbksoa.lua").read_bytes()
    assert game_files(game) == expected
    result, log = run_component(game, 651, uninstall=True)
    assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == base
    result, log = run_component(game, 650, uninstall=True)
    assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU or WEIDU_BIN")
@pytest.mark.parametrize("problem", ["non-eet", "no-eeex", "missing-native", "x86", "truncated", "bad-offset"])
def test_real_prerequisites_and_pe_failures_publish_nothing(tmp_path, problem):
    game = SyntheticGame(tmp_path / "game", game="bg2ee" if problem == "non-eet" else "eet",
                         eeex=problem != "no-eeex")
    native_headers(game)
    host = game.root / "eeex.dll"
    if problem == "missing-native":
        host.unlink()
    elif problem == "truncated":
        host.write_bytes(b"MZ")
    elif problem in ("x86", "bad-offset"):
        data = bytearray(host.read_bytes())
        struct.pack_into("<H" if problem == "x86" else "<I", data,
                         0x84 if problem == "x86" else 0x3C, 0x14C if problem == "x86" else 0xFFFFFFF0)
        host.write_bytes(data)
    before = game_files(game)
    result, log = run_component(game, 650)
    assert "SUCCESSFULLY INSTALLED" not in log, log
    if problem in ("non-eet", "no-eeex", "missing-native"):
        assert result.returncode == 0 and "SKIPPING:" in log, log
    else:
        assert result.returncode != 0 and "ERROR" in log, log
    assert game_files(game) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU or WEIDU_BIN")
@pytest.mark.parametrize("sr", [False, True])
def test_component_routes_owned_recruitment_without_changing_authored_xp(tmp_path, sr):
    from tests.test_recruitment_xp import make_game, install, decompile_script, compile_script
    game = make_game(tmp_path, game_type="eet", sr=sr, converted=sr, reversed_blocks=sr)
    native_headers(game)
    (game.override / "m___eeex.lua").write_text("-- fixture\n")
    with (game.override / "action.ids").open("a") as stream:
        stream.write('472 EEex_LuaAction(S:Code*)\n')
    for component in (237, 238):
        result, log = install(game, component)
        assert result.returncode == 0, log
    for script in ("CBMFXP", "CBMEXP"):
        source = decompile_script(game, script)
        compile_script(game, script, source + 'IF\n Global("ForeignXP","LOCALS",0)\nTHEN\n RESPONSE #100\n ChangeStat(Myself,XP,555000,SET)\nEND\n')
    (game.override / "m_cbmixp.lua").write_bytes((ROOT / "chriz-bg-modpack/imoen-xp/m_cbmixp.lua").read_bytes())
    before = game_files(game)
    result, log = run_component(game, 650)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    for script in ("CBMFXP", "CBMEXP"):
        source = decompile_script(game, script)
        assert source.count("CBMBank_Catchup(") == 6
        assert 'ChangeStat(Myself,XP,555000,SET)' in source
    imoen = (game.override / "m_cbmixp.lua").read_text()
    assert "CBMBank_ActiveXP(member)" in imoen and "CBMBank_ImoenXPSet(sprite, target)" in imoen
    assert "math.min(3000000, math.floor(total / count))" in imoen
    result, log = run_component(game, 650, uninstall=True)
    assert result.returncode == 0, log
    assert game_files(game) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU or WEIDU_BIN")
def test_chapter_caps_dependency_mutual_exclusion_and_exact_uninstall(tmp_path):
    game = SyntheticGame(tmp_path / "game", game="eet")
    native_headers(game)
    before = game_files(game)
    # 652 requires 650
    result, log = run_component(game, 652)
    assert result.returncode == 0 and "SKIPPING:" in log, log
    assert game_files(game) == before
    # Install 650 then 652
    result, log = run_component(game, 650)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    base = game_files(game)
    result, log = run_component(game, 652)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    expected = dict(base)
    expected["OVERRIDE/CBMBKCFG.LUA"] = (SOURCE / "cbmbkchp.lua").read_bytes()
    assert game_files(game) == expected
    # 651 is mutually exclusive while 652 is installed
    result, log = run_component(game, 651)
    assert result.returncode == 0 and "SKIPPING:" in log, log
    assert game_files(game) == expected
    # Uninstall 652 restores 650's CBMBKCFG.lua; 651 can then install and blocks 652
    result, log = run_component(game, 652, uninstall=True)
    assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == base
    result, log = run_component(game, 651)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    result, log = run_component(game, 652)
    assert result.returncode == 0 and "SKIPPING:" in log, log
    for component in (651, 650):
        result, log = run_component(game, component, uninstall=True)
        assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU or WEIDU_BIN")
@pytest.mark.parametrize("layout", ["vanilla", "modded_triggers_and_extra_block", "already_gated"])
def test_chapter_caps_gates_bainvi_bcs_and_preserves_unrelated_blocks(tmp_path, layout):
    from tests.test_recruitment_xp import decompile_script
    bainvi_baf = {
        "vanilla": BAINVI_VANILLA,
        "modded_triggers_and_extra_block": (
            'IF\n'
            '  Global("OtherModPrep","LOCALS",0)\n'
            'THEN\n'
            '  RESPONSE #100\n'
            '    SetGlobal("OtherModPrep","LOCALS",1)\n'
            '    Continue()\n'
            'END\n'
            'IF\n'
            '  Global("BA_START_SCENE","MYAREA",0)\n'
            '  XPGT(Player1,25000)\n'
            'THEN\n'
            '  RESPONSE #100\n'
            '    SetGlobal("BA_START_SCENE","MYAREA",1)\n'
            '    StartCutScene("CUTBA01")\n'
            'END\n'
        ),
        "already_gated": (
            'IF\n'
            '  GlobalGT("Chapter","GLOBAL",4)\n'
            '  Global("BA_START_SCENE","MYAREA",0)\n'
            'THEN\n'
            '  RESPONSE #100\n'
            '    SetGlobal("BA_START_SCENE","MYAREA",1)\n'
            '    StartCutScene("CUTBA01")\n'
            'END\n'
        ),
    }[layout]
    game = chapter_game(tmp_path, bainvi_baf)
    before = game_files(game)
    for component in (650, 652):
        result, log = run_component(game, component)
        assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    patched = decompile_script(game, "BAINVI")
    assert patched.count(CHAPTER_GATE) == 1
    assert 'StartCutScene("CUTBA01")' in patched
    if layout == "modded_triggers_and_extra_block":
        assert 'Global("OtherModPrep","LOCALS",0)' in patched
        assert 'XPGT(Player1,25000)' in patched
    for component in (652, 650):
        result, log = run_component(game, component, uninstall=True)
        assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU or WEIDU_BIN")
@pytest.mark.parametrize("layout", sorted(UNRECOGNISED_BAINVI))
def test_chapter_caps_install_and_warn_when_bainvi_has_no_known_entrance(tmp_path, layout):
    # The caps do not depend on the Baeloth gate: an unrecognised BAINVI.BCS stays
    # byte-identical, the installer warns, and the chapter caps still install.
    game = chapter_game(tmp_path, UNRECOGNISED_BAINVI[layout])
    original = (game.override / "bainvi.bcs").read_bytes()
    before = game_files(game)
    result, log = run_component(game, 650)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    base = game_files(game)
    result, log = run_component(game, 652)
    # WeiDU exits with 3 after a component installed with warnings.
    assert result.returncode == 3 and "INSTALLED WITH WARNINGS" in log, log
    assert NO_GATE_WARNING in log, log
    assert NO_GATE_REASONS[layout] in log, log
    assert (game.override / "bainvi.bcs").read_bytes() == original
    expected = dict(base)
    expected["OVERRIDE/CBMBKCFG.LUA"] = (SOURCE / "cbmbkchp.lua").read_bytes()
    assert game_files(game) == expected
    for component in (652, 650):
        result, log = run_component(game, component, uninstall=True)
        assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == before
