"""Compile and exercise the uninstalled native scroll extension, never Baldur.exe."""
from pathlib import Path
import ctypes
import mmap
import os
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research" / "scroll-runtime"
CASES = (
    "policy", "modes", "queued_readers", "actions", "reflection_177", "root177", "nested",
    "reuse", "unwind", "guards", "depth_reset", "route_guards", "thread", "native_provider", "reporter", "effect_archive",
)


def compiler_environment():
    if os.name != "nt":
        compiler = shutil.which("g++") or shutil.which("clang++")
        assert compiler, "native C++20 compiler required; this test must not silently skip"
        return compiler, os.environ.copy(), False
    vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
    result = subprocess.run(
        [str(vswhere), "-latest", "-products", "*", "-requires",
         "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
        text=True, capture_output=True, check=True,
    )
    location = Path(result.stdout.strip())
    setup = location / "VC/Auxiliary/Build/vcvars64.bat"
    assert setup.is_file(), "MSVC x64 toolchain required"
    # A fixed vcvars path only; no user text, shell interpolation, filesystem
    # deletion, or game paths enter this command. Build/run below use argv.
    result = subprocess.run(
        f'cmd /d /s /c ""{setup}" >nul && set"',
        text=True, capture_output=True, check=True,
    )
    environment = os.environ.copy()
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            environment[key] = value
    compiler = shutil.which("cl.exe", path=environment.get("Path", environment.get("PATH", "")))
    assert compiler, "vcvars did not expose cl.exe"
    return compiler, environment, True


@pytest.fixture(scope="session")
def native_scroll_build(tmp_path_factory):
    build = tmp_path_factory.mktemp("scroll-native-build")
    compiler, environment, msvc = compiler_environment()
    binary = build / ("scroll_context_tests.exe" if msvc else "scroll_context_tests")
    if msvc:
        args = [compiler, "/nologo", "/std:c++20", "/EHsc", "/W4", "/WX", "/permissive-",
                str(SOURCE / "runtime_tests.cpp"), str(SOURCE / "native_api.cpp"), f"/Fe{binary}"]
    else:
        args = [compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-pedantic", "-pthread",
                str(SOURCE / "runtime_tests.cpp"), str(SOURCE / "native_api.cpp"), "-o", str(binary)]
    result = subprocess.run(args, cwd=build, env=environment, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    library = build / ("scroll_context.dll" if msvc else "libscroll_context.so")
    if msvc:
        args = [compiler, "/nologo", "/std:c++20", "/EHsc", "/W4", "/WX", "/permissive-", "/LD",
                str(SOURCE / "native_api.cpp"), f"/Fe{library}", f"/Fo{build / 'native_api.obj'}"]
    else:
        args = [compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-pedantic", "-pthread", "-shared", "-fPIC",
                str(SOURCE / "native_api.cpp"), "-o", str(library)]
    result = subprocess.run(args, cwd=build, env=environment, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return binary, library


@pytest.mark.parametrize("case", CASES)
def test_native_scroll_context(native_scroll_build, case):
    result = subprocess.run([str(native_scroll_build[0]), case], text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == f"PASS {case}"


class NativeStats(ctypes.Structure):
    _fields_ = [("count", ctypes.c_uint32), ("level", ctypes.c_uint32 * 3),
                ("active", ctypes.c_uint32 * 3), ("arcane_state", ctypes.c_uint32),
                ("arcane_level", ctypes.c_uint32), ("divine_state", ctypes.c_uint32),
                ("divine_level", ctypes.c_uint32)]


def test_resolved_native_helper_retains_ancestry_without_borrowing_level(native_api):
    api, resolver_type, reporter_type = native_api
    observed, errors = [], []
    @resolver_type
    def resolve(reader, generation, spell, kind, output, _):
        observed.append((reader, spell, kind))
        if kind != 3:
            output.contents.count = 1
            output.contents.level[0] = 16
            output.contents.active[0] = 1
            output.contents.arcane_state = output.contents.divine_state = 0
        return 1
    @reporter_type
    def report(message, _):
        errors.append(message.decode())
    runtime = api.CBMS_Create(resolve, report, None)
    assert api.CBMS_Construct(runtime, 0, 0x1000) == 1
    for pointer in (0x2000, 0x2100, 0x2200, 0x2300):
        assert api.CBMS_Construct(runtime, 1, pointer) == 1
    use = ctypes.c_uint64()
    assert api.CBMS_ItemBegin(runtime, 0x1000, b"SCROLL", 0, 0, ctypes.byref(use)) == 1
    assert api.CBMS_ItemChild(runtime, use, 0x2000, 0) == 1
    assert api.CBMS_ItemEnd(runtime, use) == 1
    frames = []
    for carrier, spell, kind, child in [(0x2000, 0xD000, 0, 0x2100),
                                       (0x2100, 0xD100, 3, 0x2200),
                                       (0x2200, 0xD200, 1, 0x2300)]:
        frame, level = ctypes.c_uint64(), ctypes.c_uint32(99)
        assert api.CBMS_BeginCast(runtime, 1, carrier, 0, spell, b"HELPER", kind, 9, 10, 1, 2, ctypes.byref(frame)) == 1
        frames.append(frame.value)
        assert api.CBMS_Select(runtime, frame, 0, spell, ctypes.byref(level)) == (0 if kind == 3 else 1)
        assert level.value == (99 if kind == 3 else 8)
        # Repeat selection must not re-query or inherit the parent's level.
        count = len(observed)
        assert api.CBMS_Select(runtime, frame, 0, spell, ctypes.byref(level)) == (0 if kind == 3 else 1)
        assert len(observed) == count
        assert api.CBMS_SpellChild(runtime, frame, spell, child, ctypes.byref(level)) == (0 if kind == 3 else 1)
        assert level.value == (99 if kind == 3 else 8)
        independent = ctypes.c_uint64()
        assert api.CBMS_BeginCast(runtime, 1, 0, 0, spell, b"HELPER", 0, 9, 10, 1, 2, ctypes.byref(independent)) == 1
        independent_level = ctypes.c_uint32(77)
        assert api.CBMS_Select(runtime, independent, 0, spell, ctypes.byref(independent_level)) == 0
        assert independent_level.value == 77
        assert api.CBMS_EndCast(runtime, independent) == 1
    assert [entry[2] for entry in observed] == [0, 3, 1]
    assert all(entry[0] == 0x1000 for entry in observed)
    for frame in reversed(frames):
        assert api.CBMS_EndCast(runtime, frame) == 1
    for pointer in (0x2000, 0x2100, 0x2200, 0x2300):
        assert api.CBMS_Destruct(runtime, 1, pointer) == 1
    assert api.CBMS_Destroy(runtime) == 1
    assert errors == []


@pytest.fixture(scope="session")
def native_api(native_scroll_build):
    library = ctypes.CDLL(str(native_scroll_build[1]))
    return configure_native_api(library)


def configure_native_api(library):
    ptr, u32, u64, address = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint64, ctypes.c_size_t
    resolver = ctypes.CFUNCTYPE(ctypes.c_int, address, u64, address, u32, ctypes.POINTER(NativeStats), ptr)
    reporter = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ptr)
    signatures = {
        "Create": ([resolver, reporter, ptr], ptr), "Destroy": ([ptr], ctypes.c_int),
        "LastError": ([ptr], ctypes.c_char_p),
        "Construct": ([ptr, u32, address], ctypes.c_int),
        "Destruct": ([ptr, u32, address], ctypes.c_int),
        "ActorUUID": ([ptr, address, u64], ctypes.c_int),
        "ActorObserved": ([ptr, address, u64], ctypes.c_int),
        "PrepareEffectExport": ([ptr, address, address, u32, u32, u32], ctypes.c_int),
        "EffectExportText": ([ptr, address], ctypes.c_char_p),
        "ValidateEffectExport": ([ptr, address, ptr, u32], ctypes.c_int),
        "BeginEffectImport": ([ptr, address], ctypes.c_int),
        "ObserveEffectDecoded": ([ptr, address, address, ptr], ctypes.c_int),
        "StageEffectImportText": ([ptr, address, ctypes.c_char_p, u32], ctypes.c_int),
        "FinishEffectImport": ([ptr, address], ctypes.c_int),
        "AbortEffectExport": ([ptr, address], ctypes.c_int),
        "AbortEffectImport": ([ptr, address], ctypes.c_int),
        "ItemBegin": ([ptr, address, ctypes.c_char_p, u32, u32, ctypes.POINTER(u64)], ctypes.c_int),
        "ItemChild": ([ptr, u64, address, u32], ctypes.c_int), "ItemEnd": ([ptr, u64], ctypes.c_int),
        "Copy": ([ptr, u32, address, address], ctypes.c_int),
        "Dispatch": ([ptr, address, u32, u32, u32, u32, address], ctypes.c_int),
        "BeginCast": ([ptr, u32, address, u32, address, ctypes.c_char_p, u32,
                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(u64)], ctypes.c_int),
        "Select": ([ptr, u64, u32, address, ctypes.POINTER(u32)], ctypes.c_int),
        "SpellChild": ([ptr, u64, address, address, ctypes.POINTER(u32)], ctypes.c_int),
        "Linked177": ([ptr, address, address, ctypes.POINTER(u32)], ctypes.c_int),
        "EndCast": ([ptr, u64], ctypes.c_int), "Quiescent": ([ptr], ctypes.c_int),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(library, "CBMS_" + name)
        function.argtypes, function.restype = arguments, result
    return library, resolver, reporter


@pytest.mark.parametrize("opcode,mode,special,selector,kind", [
    (146, 0, 0, 3, 3), (146, 1, 0, 1, 2), (146, 2, 0, 0, 1),
    (148, 0, 0, 4, 3), (148, 1, 0, 2, 1), (148, 2, 0, 2, 1),
    (146, 0, 1, 5, 3), (148, 0, 1, 6, 3),
])
def test_exported_native_callback_lifecycle(native_api, opcode, mode, special, selector, kind):
    api, resolver_type, reporter_type = native_api
    observed, errors = [], []

    @resolver_type
    def resolve(reader, generation, spell, spell_type, output, _):
        observed.append((reader, generation, spell, spell_type))
        output.contents.count = 2
        output.contents.level[:] = (31, 12, 0)
        output.contents.active[:] = (0, 1, 0)  # dormant level31 excluded
        output.contents.arcane_state = 0
        output.contents.divine_state = 0
        return 1

    @reporter_type
    def report(message, _):
        errors.append(message.decode("utf-8"))

    runtime = api.CBMS_Create(resolve, report, None)
    assert runtime
    try:
        for object_kind, pointer in [(0, 0x1000), (1, 0x2000), (1, 0x5000), (1, 0x5100)]:
            assert api.CBMS_Construct(runtime, object_kind, pointer) == 1
        use = ctypes.c_uint64()
        assert api.CBMS_ItemBegin(runtime, 0x1000, b"SCROLL", 4, 0, ctypes.byref(use)) == 1
        assert api.CBMS_ItemChild(runtime, use, 0x2000, 17) == 1
        assert api.CBMS_ItemEnd(runtime, use) == 1
        carrier = 0x2000
        if kind != 1:
            carrier = 0x3000
            assert api.CBMS_Construct(runtime, kind, carrier) == 1
            assert api.CBMS_Dispatch(runtime, 0x2000, opcode, mode, special, kind, carrier) == 1
            assert api.CBMS_Destruct(runtime, 1, 0x2000) == 1
        frame = ctypes.c_uint64()
        # Engine source/target now identify reflection; original reader is 0x1000.
        assert api.CBMS_BeginCast(runtime, kind, carrier, selector, 0xD000, b"SR_ALIAS", 0,
                                  901, 902, 73, 81, ctypes.byref(frame)) == 1
        level = ctypes.c_uint32(99)
        assert api.CBMS_Select(runtime, frame, selector, 0xD000, ctypes.byref(level)) == 1
        assert level.value == 6
        assert observed[0][0] == 0x1000
        assert observed[0][2] == 0xD000
        assert api.CBMS_SpellChild(runtime, frame, 0xD000, 0x5000, ctypes.byref(level)) == 1
        assert api.CBMS_Linked177(runtime, 0x5000, 0x5100, ctypes.byref(level)) == 1
        assert level.value == 6
        assert api.CBMS_EndCast(runtime, frame) == 1
        assert api.CBMS_Quiescent(runtime) == 0
        for object_kind, pointer in [(kind, carrier), (1, 0x5000), (1, 0x5100)]:
            assert api.CBMS_Destruct(runtime, object_kind, pointer) == 1
        assert api.CBMS_Quiescent(runtime) == 1
        assert errors == []
    finally:
        assert api.CBMS_Destroy(runtime) == 1


def test_exported_errors_do_not_replace_levels_or_drop_pending_casts(native_api):
    api, resolver_type, reporter_type = native_api
    errors = []

    @resolver_type
    def unresolved(_reader, _generation, _spell, _type, output, _):
        output.contents.count = 1
        output.contents.level[0] = 18
        output.contents.active[0] = 1
        output.contents.arcane_state = 2
        return 1

    @reporter_type
    def report(message, _):
        errors.append(message.decode("utf-8"))

    runtime = api.CBMS_Create(unresolved, report, None)
    assert runtime
    assert api.CBMS_Construct(runtime, 0, 0x1000) == 1
    assert api.CBMS_Construct(runtime, 1, 0x2000) == 1
    assert api.CBMS_Construct(runtime, 1, 0x2100) == 1
    use, frame, mask = ctypes.c_uint64(), ctypes.c_uint64(), ctypes.c_uint64()
    assert api.CBMS_ItemBegin(runtime, 0x1000, b"SCROLL", 0, 0, ctypes.byref(use)) == 1
    assert api.CBMS_ItemChild(runtime, use, 0x2000, 0) == 1
    assert api.CBMS_ItemEnd(runtime, use) == 1
    assert api.CBMS_BeginCast(runtime, 1, 0x2000, 0, 0xD000, b"MIXED", 0,
                              1, 2, 3, 4, ctypes.byref(frame)) == 1
    level = ctypes.c_uint32(99)
    assert api.CBMS_Select(runtime, frame, 0, 0xD000, ctypes.byref(level)) == -1
    assert level.value == 99
    assert "capability" in errors[-1]
    assert api.CBMS_SpellChild(runtime, frame, 0xD000, 0x2100, ctypes.byref(level)) == -1
    assert level.value == 99
    assert api.CBMS_Destroy(runtime) == -1
    # Unrelated nested cast masks the owned outer frame even at same pointer.
    assert api.CBMS_BeginCast(runtime, 1, 0, 0, 0xD000, b"MIXED", 0,
                              5, 6, 7, 8, ctypes.byref(mask)) == 1
    assert api.CBMS_Select(runtime, mask, 0, 0xD000, ctypes.byref(level)) == 0
    assert level.value == 99
    assert api.CBMS_EndCast(runtime, frame) == -1
    assert api.CBMS_EndCast(runtime, mask) == 1
    assert api.CBMS_EndCast(runtime, frame) == 1
    assert api.CBMS_Destruct(runtime, 1, 0x2000) == 1
    assert api.CBMS_Destroy(runtime) == 1


def test_eight_byte_native_resref_never_reads_ninth_byte(native_api):
    api, resolver_type, reporter_type = native_api

    @resolver_type
    def unused(*_):
        return 0

    @reporter_type
    def report(*_):
        pass

    kernel = None
    allocation = None
    storage = ctypes.create_string_buffer(b"FULLNAME", 8)
    address = ctypes.addressof(storage)
    if os.name == "nt":
        # Put byte8 on a no-access page: the earlier size<9 reader would fault.
        # This is private test-process memory, never engine or game memory.
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]
        kernel.VirtualAlloc.restype = ctypes.c_void_p
        kernel.VirtualProtect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
        kernel.VirtualProtect.restype = ctypes.c_int
        kernel.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]
        kernel.VirtualFree.restype = ctypes.c_int
        allocation = kernel.VirtualAlloc(None, mmap.PAGESIZE * 2, 0x3000, 0x04)
        assert allocation
        previous = ctypes.c_uint32()
        assert kernel.VirtualProtect(allocation + mmap.PAGESIZE, mmap.PAGESIZE, 0x01, ctypes.byref(previous))
        address = allocation + mmap.PAGESIZE - 8
        ctypes.memmove(address, b"FULLNAME", 8)
    runtime = api.CBMS_Create(unused, report, None)
    assert runtime
    try:
        assert api.CBMS_Construct(runtime, 0, 0x1000) == 1
        use, frame = ctypes.c_uint64(), ctypes.c_uint64()
        text = ctypes.cast(address, ctypes.c_char_p)
        assert api.CBMS_ItemBegin(runtime, 0x1000, text, 0, 1, ctypes.byref(use)) == 1
        assert api.CBMS_ItemEnd(runtime, use) == 1
        assert api.CBMS_BeginCast(runtime, 1, 0, 0, 0xD000, text, 0,
                                  1, 2, 3, 4, ctypes.byref(frame)) == 1
        assert api.CBMS_EndCast(runtime, frame) == 1
    finally:
        assert api.CBMS_Destroy(runtime) == 1
        if kernel and allocation:
            assert kernel.VirtualFree(allocation, 0, 0x8000)


def test_provider_cannot_destroy_or_recursively_resolve_its_current_frame(native_api):
    api, resolver_type, reporter_type = native_api
    outcomes, errors = [], []
    runtime, frame = None, ctypes.c_uint64()

    @resolver_type
    def resolve(_reader, _generation, _spell, _type, output, _):
        level = ctypes.c_uint32(99)
        outcomes.append(api.CBMS_EndCast(runtime, frame))
        outcomes.append(api.CBMS_Select(runtime, frame, 0, 0xD000, ctypes.byref(level)))
        output.contents.count = 1
        output.contents.level[0] = 18
        output.contents.active[0] = 1
        output.contents.arcane_state = 1
        output.contents.arcane_level = 18
        return 1

    @reporter_type
    def report(message, _):
        errors.append(message.decode("utf-8"))

    runtime = api.CBMS_Create(resolve, report, None)
    assert api.CBMS_Construct(runtime, 0, 0x1000) == 1
    assert api.CBMS_Construct(runtime, 1, 0x2000) == 1
    use = ctypes.c_uint64()
    assert api.CBMS_ItemBegin(runtime, 0x1000, b"SCROLL", 0, 0, ctypes.byref(use)) == 1
    assert api.CBMS_ItemChild(runtime, use, 0x2000, 0) == 1
    assert api.CBMS_ItemEnd(runtime, use) == 1
    assert api.CBMS_BeginCast(runtime, 1, 0x2000, 0, 0xD000, b"SPELL", 0,
                              1, 2, 3, 4, ctypes.byref(frame)) == 1
    level = ctypes.c_uint32(99)
    assert api.CBMS_Select(runtime, frame, 0, 0xD000, ctypes.byref(level)) == 1
    assert level.value == 18 and outcomes == [-1, -1]
    assert len(errors) == 2
    assert api.CBMS_EndCast(runtime, frame) == 1
    assert api.CBMS_Destruct(runtime, 1, 0x2000) == 1
    assert api.CBMS_Destroy(runtime) == 1


def test_exported_native_provider_reads_original_actor_and_calls_audited_abi(native_api):
    api, _, reporter_type = native_api
    pointer, byte = ctypes.c_void_p, ctypes.c_uint8
    lookup_t = ctypes.CFUNCTYPE(byte, ctypes.c_int32, ctypes.POINTER(pointer))
    classes_t = ctypes.CFUNCTYPE(None, pointer, ctypes.POINTER(byte), ctypes.POINTER(byte))
    level_t = ctypes.CFUNCTYPE(byte, pointer, byte, byte)
    maximum_t = ctypes.CFUNCTYPE(byte, pointer, byte)
    capability_t = ctypes.CFUNCTYPE(ctypes.c_int, pointer, pointer)
    type_t = ctypes.CFUNCTYPE(ctypes.c_short, pointer)
    casting_t = ctypes.CFUNCTYPE(ctypes.c_short, pointer, pointer, ctypes.c_int)

    class Functions(ctypes.Structure):
        _fields_ = [("lookup", lookup_t), ("classes", classes_t), ("level", level_t),
                    ("maximum", maximum_t), ("mage", capability_t), ("priest", capability_t),
                    ("type", type_t), ("casting", casting_t)]

    actor = ctypes.create_string_buffer(0x5000)
    address = ctypes.addressof(actor)
    byte.from_buffer(actor, 0x3B).value = 19
    byte.from_buffer(actor, 0x4B73).value = 7
    ctypes.c_int32.from_buffer(actor, 0x4B74).value = 77
    ctypes.c_uint32.from_buffer(actor, 0x4EA4).value = 1
    calls, errors, context = [], [], {"type": 1}

    @lookup_t
    def lookup(instance, output):
        calls.append(("lookup", instance))
        output[0] = address
        return 0

    @classes_t
    def classes(ai, new, old):
        calls.append(("classes", ai))
        new[0], old[0] = 4, 1

    @level_t
    def level(stats, composite, active):
        calls.append(("level", stats, composite, active))
        return 12

    @maximum_t
    def maximum(stats, composite):
        calls.append(("unexpected_maximum", stats, composite))
        return 24

    @capability_t
    def mage(screen, reader):
        calls.append(("mage", screen, reader))
        return 0

    @capability_t
    def priest(screen, reader):
        calls.append(("priest", screen, reader))
        return 1

    @type_t
    def caster_type(spell):
        calls.append(("type", spell))
        return context["type"]

    @casting_t
    def caster_level(reader, spell, wild):
        calls.append(("casting", reader, spell, wild))
        return 7

    @reporter_type
    def report(message, _):
        errors.append(message.decode("utf-8"))

    functions = Functions(lookup, classes, level, maximum, mage, priest, caster_type, caster_level)
    api.CBMS_CreateNative.argtypes = [ctypes.POINTER(Functions), reporter_type, pointer]
    api.CBMS_CreateNative.restype = pointer
    runtime = api.CBMS_CreateNative(ctypes.byref(functions), report, None)
    assert runtime
    assert api.CBMS_Construct(runtime, 0, address) == 1
    assert api.CBMS_Construct(runtime, 1, 0x2000) == 1
    use, frame = ctypes.c_uint64(), ctypes.c_uint64()
    assert api.CBMS_ItemBegin(runtime, address, b"SCROLL", 0, 0, ctypes.byref(use)) == 1
    assert api.CBMS_ItemChild(runtime, use, 0x2000, 0) == 1
    assert api.CBMS_ItemEnd(runtime, use) == 1
    for native_type, expected in [(1, 6), (2, 7)]:
        context["type"] = native_type
        assert api.CBMS_BeginCast(runtime, 1, 0x2000, 0, 0xD000, b"SPELL", native_type - 1,
                                  901, 902, 73, 81, ctypes.byref(frame)) == 1
        chosen = ctypes.c_uint32(99)
        assert api.CBMS_Select(runtime, frame, 0, 0xD000, ctypes.byref(chosen)) == 1
        assert chosen.value == expected
        assert api.CBMS_EndCast(runtime, frame) == 1
    assert ("lookup", 77) in calls
    assert ("classes", address + 0x4B68) in calls
    assert ("level", address + 0x1120, 7, 4) in calls
    assert ("mage", None, address) in calls and ("priest", None, address) in calls
    assert calls.count(("casting", address, 0xD000, 1)) == 1
    assert not any(call[0] == "unexpected_maximum" for call in calls)
    assert errors == []
    assert api.CBMS_Destruct(runtime, 1, 0x2000) == 1
    assert api.CBMS_Destroy(runtime) == 1
