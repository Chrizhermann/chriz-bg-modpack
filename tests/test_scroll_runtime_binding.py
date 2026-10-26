"""Offline mapped-image certification; no engine entry point/function is called.

Uses read-only SEC_IMAGE views, not LoadLibrary/process creation. Temporary
copy-on-write mutations belong to this test process and cannot change the file.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct

import subprocess

import pefile
import pytest

from test_scroll_runtime_native import compiler_environment, native_scroll_build

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/scroll-runtime"
PROFILES = json.loads((SOURCE / "binder-profiles.json").read_text())
SYMBOLS = Path("C:/tmp/scroll-hook-research-20261009/EEex/EEex/loader")
pytestmark = pytest.mark.skipif(os.name != "nt", reason="audited mapped-image binder is Windows x64 only")


@pytest.fixture(params=PROFILES, ids=lambda value: value["version"])
def pinned_image(request):
    """A pinned, unbundled local executable as (pefile image, version, names by address)."""
    profile = request.param
    executable = Path(os.path.expandvars(profile["source"]))
    if not executable.is_file():
        pytest.skip("offline native proof requires the unbundled pinned executable")
    raw = executable.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == profile["sha256"], "unreviewed offline executable"
    symbols = SYMBOLS / f"v{profile['version']}/bg2ee/function_names.db"
    names = {int(at, 16): name for line in symbols.read_text().splitlines()
             for at, _, name in [line.partition("\t")] if at.startswith("0x")}
    return pefile.PE(data=raw), profile["version"], names


@pytest.fixture(scope="session")
def os_unwinder(tmp_path_factory):
    """Windows' own RtlVirtualUnwind over inert copied code, records and stacks."""
    build = tmp_path_factory.mktemp("scroll-unwind-probe")
    compiler, environment, msvc = compiler_environment()
    assert msvc
    target = build / "scroll_unwind_probe.dll"
    command = [compiler, "/nologo", "/std:c++20", "/EHsc", "/W4", "/WX", "/LD",
               str(SOURCE / "unwind_probe.cpp"), f"/Fe{target}"]
    result = subprocess.run(command, cwd=build, env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    library = ctypes.CDLL(str(target))
    callback = library.ScrollTestUnwind
    callback.argtypes = [ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p,
                         ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64)]
    callback.restype = ctypes.c_uint32
    return callback


class FunctionTable(ctypes.Structure):
    _fields_ = [("addresses", ctypes.c_size_t * 8)]


@pytest.fixture(scope="session")
def binding_api(native_scroll_build):
    api = ctypes.CDLL(str(native_scroll_build[1]))
    api.CBMS_BindModule.argtypes = [ctypes.c_size_t, ctypes.POINTER(FunctionTable), ctypes.c_void_p, ctypes.c_uint32]
    api.CBMS_BindModule.restype = ctypes.c_int
    api.CBMS_BindCurrent.argtypes = [ctypes.POINTER(FunctionTable), ctypes.c_void_p, ctypes.c_uint32]
    api.CBMS_BindCurrent.restype = ctypes.c_int
    return api


@pytest.fixture(scope="session")
def windows():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    ptr, u32, size = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_size_t
    definitions = {
        "CreateFileW": ([ctypes.c_wchar_p, u32, u32, ptr, u32, u32, ptr], ptr),
        "CreateFileMappingW": ([ptr, ptr, u32, u32, u32, ctypes.c_wchar_p], ptr),
        "MapViewOfFileEx": ([ptr, u32, u32, u32, size, ptr], ptr),
        "UnmapViewOfFile": ([ptr], ctypes.c_int), "CloseHandle": ([ptr], ctypes.c_int),
        "VirtualProtect": ([ptr, size, u32, ctypes.POINTER(u32)], ctypes.c_int),
        "VirtualAlloc": ([ptr, size, u32, u32], ptr), "VirtualFree": ([ptr, size, u32], ctypes.c_int),
    }
    for name, (args, result) in definitions.items():
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
    return api


class MappedImage:
    def __init__(self, windows, profile, desired):
        self.windows, self.profile = windows, profile
        path = Path(os.path.expandvars(profile["source"]))
        if not path.is_file():
            pytest.skip("offline mapped-image evidence requires the unbundled pinned local executable")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == profile["sha256"], "unreviewed offline executable"
        handle = windows.CreateFileW(str(path), 0x80000000, 7, None, 3, 0, None)  # GENERIC_READ, OPEN_EXISTING
        assert handle not in (None, ctypes.c_void_p(-1).value), ctypes.get_last_error()
        mapping = None
        try:
            mapping = windows.CreateFileMappingW(handle, None, 0x1000002, 0, 0, None)  # SEC_IMAGE | PAGE_READONLY
            assert mapping, ctypes.get_last_error()
            self.base = windows.MapViewOfFileEx(mapping, 4, 0, 0, 0, desired)
            assert self.base == desired, ctypes.get_last_error()
        finally:
            if mapping:
                assert windows.CloseHandle(mapping)
            assert windows.CloseHandle(handle)
        assert self.base != profile["preferred_base"]
        self.nt = self.u32(0x3C)
        self.optional = self.nt + 24
        self.sections = self.optional + self.u16(self.nt + 20)

    def close(self):
        assert self.windows.UnmapViewOfFile(self.base)
        assert hashlib.sha256(Path(os.path.expandvars(self.profile["source"])).read_bytes()).hexdigest() == self.profile["sha256"]

    def read(self, rva, count):
        return ctypes.string_at(self.base + rva, count)

    def u16(self, rva):
        return struct.unpack("<H", self.read(rva, 2))[0]

    def u32(self, rva):
        return struct.unpack("<I", self.read(rva, 4))[0]

    def write(self, rva, content):
        old = ctypes.c_uint32()
        assert self.windows.VirtualProtect(self.base + rva, len(content), 0x80, ctypes.byref(old)), ctypes.get_last_error()  # EXECUTE_WRITECOPY
        try:
            ctypes.memmove(self.base + rva, content, len(content))
        finally:
            temporary = ctypes.c_uint32()
            assert self.windows.VirtualProtect(self.base + rva, len(content), old.value, ctypes.byref(temporary))

    def protect(self, rva, protection):
        old = ctypes.c_uint32()
        assert self.windows.VirtualProtect(self.base + rva, 1, protection, ctypes.byref(old))

    def evidence(self):
        return self.read(0, 0x1000) + b"".join(self.read(s["rva"], s["size"]) for s in self.profile["signatures"])


@pytest.fixture(params=PROFILES, ids=lambda profile: profile["version"])
def mapped(windows, request):
    image = MappedImage(windows, request.param, 0x200000000)
    try:
        yield image
    finally:
        image.close()


def bind(api, module):
    table = FunctionTable((ctypes.c_size_t * 8)(*(0xCAFE0000 + i for i in range(8))))
    before = bytes(table)
    diagnostic = ctypes.create_string_buffer(512)
    result = api.CBMS_BindModule(module, ctypes.byref(table), diagnostic, len(diagnostic))
    return result, table, before, diagnostic.value.decode()


def test_binds_two_relocated_pinned_views_without_invocation(binding_api, mapped, windows):
    alternate = MappedImage(windows, mapped.profile, 0x300000000)
    try:
        before = [image.evidence() for image in (mapped, alternate)]
        for index, image in enumerate((mapped, alternate)):
            result, table, _, diagnostic = bind(binding_api, image.base)
            assert result == 1, diagnostic
            assert image.profile["version"] in diagnostic
            assert list(table.addresses) == [image.base + item["rva"] for item in image.profile["signatures"][:8]]
            assert image.evidence() == before[index]
            # No table pointer is invoked: these views have no initialized
            # engine globals/imports and are not a live acceptance fixture.
    finally:
        alternate.close()


@pytest.mark.parametrize("index", range(19), ids=lambda value: PROFILES[0]["signatures"][value]["name"])
def test_rejects_each_changed_native_or_dependency_body(binding_api, mapped, index):
    signature = mapped.profile["signatures"][index]
    # Change the final body byte as well as covering tiny getters: this catches
    # entry-prefix-only checking and includes function-local branch tables.
    at = signature["rva"] + signature["size"] - 1
    mapped.write(at, bytes([mapped.read(at, 1)[0] ^ 1]))
    result, table, before, diagnostic = bind(binding_api, mapped.base)
    assert result == 0 and bytes(table) == before
    assert signature["name"] in diagnostic and "signature differs" in diagnostic


def test_unrelated_engine_patches_and_rule_data_do_not_require_pristine_image(binding_api, mapped):
    # An unrelated entry-point instruction is never called by this test. Its
    # bytes and ordinary writable-section data are outside the provider ABI.
    entry = mapped.profile["entry"]
    assert not any(s["rva"] <= entry < s["rva"] + s["size"] for s in mapped.profile["signatures"])
    mapped.write(entry, bytes([mapped.read(entry, 1)[0] ^ 1]))
    for index in range(mapped.u16(mapped.nt + 6)):
        section = mapped.sections + index * 40
        if mapped.u32(section + 36) & 0x80000000:
            at = mapped.u32(section + 12)
            mapped.write(at, bytes([mapped.read(at, 1)[0] ^ 1]))
            break
    else:
        pytest.fail("pinned image has no writable data section")
    result, table, _, diagnostic = bind(binding_api, mapped.base)
    assert result == 1, diagnostic
    assert list(table.addresses) == [mapped.base + item["rva"] for item in mapped.profile["signatures"][:8]]


CORRUPTIONS = (
    "dos", "pe_offset", "pe_signature", "machine", "optional_size", "optional_magic",
    "section_count", "image_extent", "header_extent", "alignment", "overlap", "section_extent",
    "section_execute", "entry", "unknown_build", "header_unreadable", "code_unreadable", "code_nonexecutable",
)


@pytest.mark.parametrize("case", CORRUPTIONS)
def test_rejects_corrupt_or_unreadable_mapped_layout(binding_api, mapped, case):
    u16 = lambda at, value: mapped.write(at, struct.pack("<H", value))
    u32 = lambda at, value: mapped.write(at, struct.pack("<I", value))
    nt, optional, sections = mapped.nt, mapped.optional, mapped.sections
    if case == "dos": u16(0, 0)
    elif case == "pe_offset": u32(0x3C, 0xFFFFFFF0)
    elif case == "pe_signature": u32(nt, 0)
    elif case == "machine": u16(nt + 4, 0x14C)
    elif case == "optional_size": u16(nt + 20, 2)
    elif case == "optional_magic": u16(optional, 0x10B)
    elif case == "section_count": u16(nt + 6, 0xFFFF)
    elif case == "image_extent": u32(optional + 56, 0x70000000)
    elif case == "header_extent": u32(optional + 60, 64)
    elif case == "alignment": u32(optional + 32, 0x1800)
    elif case == "overlap": u32(sections + 40 + 12, mapped.u32(sections + 12))
    elif case == "section_extent": u32(sections + 8, 0xFFFFFFFF)
    elif case == "section_execute": u32(sections + 36, mapped.u32(sections + 36) & ~0x20000000)
    elif case == "entry": u32(optional + 16, 0xFFFFFFF0)
    elif case == "unknown_build": u32(nt + 8, 1)
    elif case == "header_unreadable": mapped.protect(0, 1)
    elif case == "code_unreadable": mapped.protect(mapped.profile["signatures"][0]["rva"], 1)
    elif case == "code_nonexecutable": mapped.protect(mapped.profile["signatures"][0]["rva"], 2)
    result, table, before, diagnostic = bind(binding_api, mapped.base)
    assert result == 0 and bytes(table) == before and diagnostic


def test_refuses_private_buffers_invalid_addresses_and_unreviewed_current_process(binding_api, windows):
    private = windows.VirtualAlloc(None, 0x1000, 0x3000, 4)
    assert private
    try:
        for pointer in (0, 1, 0xFFFFFFFFFFFFF000, private):
            result, table, before, diagnostic = bind(binding_api, pointer)
            assert result == 0 and bytes(table) == before and diagnostic
    finally:
        assert windows.VirtualFree(private, 0, 0x8000)
    table = FunctionTable((ctypes.c_size_t * 8)(*range(8)))
    before = bytes(table)
    diagnostic = ctypes.create_string_buffer(512)
    assert binding_api.CBMS_BindCurrent(ctypes.byref(table), diagnostic, len(diagnostic)) == 0
    assert bytes(table) == before and diagnostic.value
