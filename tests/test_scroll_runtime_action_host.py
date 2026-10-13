"""Concrete action host on private memory; engine instructions run in Unicorn.

No native game function is invoked, and read-only SEC_IMAGE source mappings
never modify the executable. Native OS unwind registration is exercised.
"""
import ctypes as C
import json
import os
import struct
import subprocess
import sys
import threading

import pytest

from test_scroll_runtime_native import SOURCE, compiler_environment, configure_native_api
from test_scroll_runtime_binding import windows, mapped
from test_scroll_runtime_decode_host import lookup
from test_scroll_runtime_detours import action_image, execute, module as emitter

sys.path.insert(0, str(SOURCE))
import generate_action_profiles as generator
from action_loader import bundle

PROFILES = json.loads((SOURCE / "action-profiles.json").read_text())
pytestmark = pytest.mark.skipif(os.name != "nt", reason="actual Windows x64 hook host")


class Functions(C.Structure):
    _fields_ = [("profile", C.c_uint32), ("sites", C.c_size_t * 3)]


@pytest.fixture(scope="module")
def action_api(tmp_path_factory):
    compiler, environment, msvc = compiler_environment()
    assert msvc
    build = tmp_path_factory.mktemp("scroll-action-host")
    target = build / "action_host.dll"
    args = [compiler, "/nologo", "/std:c++20", "/EHsc", "/W4", "/WX", "/permissive-", "/LD",
            "/DCBMS_OFFLINE_HARNESS",
            *(str(SOURCE / name) for name in ("native_api.cpp", "action_carrier_api.cpp", "action_hook_host.cpp")),
            f"/Fe{target}"]
    result = subprocess.run(args, cwd=build, env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    api, resolve, report = configure_native_api(C.CDLL(str(target)))
    ptr, u32, address = C.c_void_p, C.c_uint32, C.c_size_t
    signatures = {
        "BindActionModule": ([address, C.POINTER(Functions), ptr, u32], C.c_int),
        "InstallActionHooks": ([address, ptr], C.c_int),
        "TestInstallActionHooks": ([C.POINTER(Functions), ptr], C.c_int),
        "TestActionHookAllocation": ([], address), "TestActionHookFailure": ([C.c_int], None),
        "ActionHooksReadyRemove": ([], C.c_int), "RemoveActionHooks": ([], C.c_int),
        "ActionHookError": ([], C.c_char_p), "ActionCarrierError": ([], C.c_char_p),
        "ConfigureActionCarriers": ([ptr], C.c_int), "DetachActionCarriers": ([], C.c_int),
        "ActionCarriersIdle": ([], C.c_int),
        "ActionCopiedCarrier": ([ptr, address, address, u32], C.c_int),
        "ActionDestroyCarrier": ([ptr, address], C.c_int),
        "CarrierIsOwned": ([ptr, u32, address], C.c_int),
    }
    for name, (arguments, result_type) in signatures.items():
        fn = getattr(api, "CBMS_" + name)
        fn.argtypes, fn.restype = arguments, result_type
    return api, resolve, report


class Runtime:
    def __init__(self, action_api):
        self.api, resolver, reporter = action_api
        self.errors = []

        @resolver
        def resolve(reader, generation, spell, kind, out, user):
            out.contents.count = 1
            out.contents.level[0] = 12
            out.contents.active[0] = 1
            return 1

        @reporter
        def report(message, _):
            self.errors.append(message.decode())

        self.callbacks = resolve, report
        self.runtime = self.api.CBMS_Create(resolve, report, None)
        assert self.runtime

    def own(self, action):
        api, runtime = self.api, self.runtime
        assert api.CBMS_Construct(runtime, 0, 0x9000) == 1
        assert api.CBMS_Construct(runtime, 1, 0x9001) == 1
        use = C.c_uint64()
        assert api.CBMS_ItemBegin(runtime, 0x9000, b"SCROLL", 0, 0, C.byref(use)) == 1
        assert api.CBMS_ItemChild(runtime, use, 0x9001, 0) == 1
        assert api.CBMS_ItemEnd(runtime, use) == 1
        assert api.CBMS_Construct(runtime, 3, action) == 1
        assert api.CBMS_Dispatch(runtime, 0x9001, 146, 0, 0, 3, action) == 1
        assert api.CBMS_Destruct(runtime, 1, 0x9001) == 1

    def close(self):
        assert self.api.CBMS_Destroy(self.runtime) == 1


class Sites:
    def __init__(self, windows, profile):
        self.windows, self.profile = windows, PROFILES[profile]
        self.base = windows.VirtualAlloc(None, 0x1000, 0x3000, 4)
        assert self.base
        self.entries = [self.base + 0x100 + i * 0x100 for i in range(3)]
        self.prefixes = [bytes.fromhex(s["original"]) for s in self.profile["sites"]]
        for address, prefix in zip(self.entries, self.prefixes):
            C.memmove(address, prefix, len(prefix))
        old = C.c_uint32()
        assert windows.VirtualProtect(self.base, 0x1000, 0x20, C.byref(old))
        self.functions = Functions(profile, (C.c_size_t * 3)(*self.entries))

    def edit(self, address, data):
        old, ignored = C.c_uint32(), C.c_uint32()
        assert self.windows.VirtualProtect(address, len(data), 0x40, C.byref(old))
        C.memmove(address, data, len(data))
        assert self.windows.VirtualProtect(address, len(data), old.value, C.byref(ignored))

    def originals(self):
        assert [C.string_at(at, len(p)) for at, p in zip(self.entries, self.prefixes)] == self.prefixes
        old = C.c_uint32()
        assert self.windows.VirtualProtect(self.base, 1, 0x20, C.byref(old))
        assert old.value == 0x20

    def close(self):
        assert self.windows.VirtualFree(self.base, 0, 0x8000)


def test_generated_recipes_match_audited_native_emitter():
    profiles = generator.generate()
    assert profiles == PROFILES
    assert generator.header(profiles) == (SOURCE / "action_profiles.hpp").read_text()


@pytest.mark.parametrize("failure", [0, 1, 2, 3, 100])
@pytest.mark.parametrize("profile", [0, 1], ids=[p["version"] for p in PROFILES])
def test_atomic_install_restoration_and_registered_instruction_unwind(action_api, windows, profile, failure):
    api = action_api[0]
    h, sites = Runtime(action_api), Sites(windows, profile)
    try:
        if failure:
            api.CBMS_TestActionHookFailure(failure)
        result = api.CBMS_TestInstallActionHooks(C.byref(sites.functions), h.runtime)
        if failure:
            assert result == 0 and b"injected" in api.CBMS_ActionHookError()
            assert api.CBMS_TestActionHookAllocation() == 0
        else:
            assert result == 1, api.CBMS_ActionHookError()
            base = api.CBMS_TestActionHookAllocation()
            expected = bytearray.fromhex(sites.profile["payload"])
            for i, (at, s) in enumerate(zip(sites.entries, sites.profile["sites"])):
                code = s["code_offset"]
                callback = api.CBMS_ActionDestroyCarrier if i == 2 else api.CBMS_ActionCopiedCarrier
                struct.pack_into("<Q", expected, code+s["runtime"], h.runtime)
                struct.pack_into("<Q", expected, code+s["callback"], C.cast(callback, C.c_void_p).value)
                resume = at + len(sites.prefixes[i])
                struct.pack_into("<I", expected, code+s["resume_lo"], resume & 0xFFFFFFFF)
                struct.pack_into("<I", expected, code+s["resume_hi"], resume >> 32)
                patch = b"\xE9" + struct.pack("<i", base+code-at-5) + b"\x90"*(len(sites.prefixes[i])-5)
                assert C.string_at(at, len(patch)) == patch
            assert C.string_at(base, len(expected)) == expected
            ranges = [struct.unpack_from("<III", expected, sites.profile["table_offset"]+i*12)
                      for i in range(sites.profile["count"])]
            for i, (start, stop, info) in enumerate(ranges):
                for pc in (start, stop-1):
                    assert lookup(base+pc) == (base+sites.profile["table_offset"]+i*12, base)
            assert api.CBMS_ActionHooksReadyRemove() == 1
            assert api.CBMS_RemoveActionHooks() == 1
            assert all(lookup(base+start)[0] is None for start, _, _ in ranges)
        sites.originals()
    finally:
        if api.CBMS_TestActionHookAllocation():
            assert api.CBMS_RemoveActionHooks() == 1
        sites.close()
        h.close()


def test_later_owner_or_wrong_thread_refuses_before_any_restore(action_api, windows):
    api = action_api[0]
    h, sites = Runtime(action_api), Sites(windows, 0)
    try:
        assert api.CBMS_TestInstallActionHooks(C.byref(sites.functions), h.runtime) == 1
        after = [C.string_at(at,len(p)) for at,p in zip(sites.entries,sites.prefixes)]
        results = []
        worker = threading.Thread(target=lambda:results.append(api.CBMS_RemoveActionHooks()))
        worker.start(); worker.join()
        assert results == [0] and b"owner thread" in api.CBMS_ActionHookError()
        sites.edit(sites.entries[-1], b"\xCC")
        assert api.CBMS_ActionHooksReadyRemove() == 0
        assert api.CBMS_RemoveActionHooks() == 0 and b"another owner" in api.CBMS_ActionHookError()
        assert [C.string_at(at,len(p)) for at,p in zip(sites.entries[:-1],sites.prefixes[:-1])] == after[:-1]
        sites.edit(sites.entries[-1],after[-1])
        assert api.CBMS_RemoveActionHooks() == 1
        sites.originals()
    finally:
        if api.CBMS_TestActionHookAllocation():
            assert api.CBMS_RemoveActionHooks() == 1
        sites.close(); h.close()


@pytest.mark.parametrize("bad", ["prefix", "configuration", "profile", "overlap", "already_configured"])
def test_invalid_install_preserves_all_originals_and_configuration(action_api, windows, bad):
    api = action_api[0]
    h, sites = Runtime(action_api), Sites(windows, 0)
    try:
        if bad == "prefix": sites.edit(sites.entries[2], b"\x90")
        if bad == "profile": sites.functions.profile = 2
        if bad == "overlap": sites.functions.sites[1] = sites.functions.sites[0]
        if bad == "already_configured": assert api.CBMS_ConfigureActionCarriers(h.runtime) == 1
        before = C.string_at(sites.base, 0x1000)
        result = api.CBMS_TestInstallActionHooks(C.byref(sites.functions), None if bad == "configuration" else h.runtime)
        assert result == 0 and api.CBMS_ActionHookError()
        assert not api.CBMS_TestActionHookAllocation()
        assert C.string_at(sites.base,0x1000) == before
        if bad == "already_configured": assert api.CBMS_ActionCarriersIdle() == 1
    finally:
        if bad == "already_configured": assert api.CBMS_DetachActionCarriers() == 1
        if api.CBMS_TestActionHookAllocation(): assert api.CBMS_RemoveActionHooks() == 1
        sites.close(); h.close()


@pytest.mark.parametrize("operation", ["copy", "assign", "destroy", "self_assign"])
@pytest.mark.parametrize("owned", [False, True])
def test_compiled_carriers_with_actual_native_action_instructions(action_api, action_image, operation, owned):
    api = action_api[0]
    h = Runtime(action_api)
    assert api.CBMS_ConfigureActionCarriers(h.runtime) == 1
    name = "assign" if operation == "self_assign" else operation
    site = action_image[1][name]
    baseline = execute(action_image, site, self_assignment=operation == "self_assign")
    source, destination = baseline["source"], baseline["destination"]
    if owned: h.own(destination if name == "destroy" else source)
    elif operation == "assign": h.own(destination)  # clears stale destination ownership
    plan = emitter.emit(site, image_base=action_image[0].OPTIONAL_HEADER.ImageBase,
                        stub=0x150000000, runtime=h.runtime, callback=0x150008000, observed=site.body)

    def event(runtime, first, second, construction):
        assert runtime == h.runtime
        if name == "destroy":
            assert first == destination
            return api.CBMS_ActionDestroyCarrier(runtime, first)
        assert (first,second,construction) == (source,destination,int(name == "copy"))
        return api.CBMS_ActionCopiedCarrier(runtime,first,second,construction)

    try:
        hooked = execute(action_image,site,plan,event,self_assignment=operation == "self_assign")
        assert hooked["registers"] == baseline["registers"]
        assert hooked["data"] == baseline["data"]
        assert hooked["calls"] == baseline["calls"]
        assert len(hooked["events"]) == 1
        assert hooked["events"][0][1] == (0 if name == "destroy" else len(baseline["calls"]))
        if name == "destroy":
            # Reusing the exact action address starts a fresh, unowned lifetime.
            assert api.CBMS_Construct(h.runtime,3,destination) == 1
            assert api.CBMS_CarrierIsOwned(h.runtime,3,destination) == 0
        else:
            frame, level = C.c_uint64(), C.c_uint32(99)
            assert api.CBMS_BeginCast(h.runtime,3,destination,3,0xD000,b"CHILD",0,1,2,3,4,C.byref(frame)) == 1
            assert api.CBMS_Select(h.runtime,frame,3,0xD000,C.byref(level)) == int(owned)
            assert level.value == (6 if owned else 99)
            assert api.CBMS_EndCast(h.runtime,frame) == 1
        assert h.errors == [] and api.CBMS_ActionCarrierError() == b""
    finally:
        for at in {source,destination}: assert api.CBMS_ActionDestroyCarrier(h.runtime,at) == 1
        assert api.CBMS_DetachActionCarriers() == 1
        h.close()


@pytest.mark.parametrize("changed", [None, 0, 1, 2])
def test_read_only_binding_rejects_changed_bodies_preserves_output(action_api, mapped, changed):
    api = action_api[0]
    profile = next(p for p in PROFILES if p["version"] == mapped.profile["version"])
    if changed is not None:
        s = profile["sites"][changed]
        at = s["function"] + s["body_size"] - 1
        mapped.write(at, bytes([mapped.read(at,1)[0]^1]))
    out = Functions(123,(C.c_size_t*3)(17,18,19))
    before, text = bytes(out), C.create_string_buffer(512)
    result = api.CBMS_BindActionModule(mapped.base,C.byref(out),text,len(text))
    if changed is None:
        assert result == 1, text.value
        assert out.profile == PROFILES.index(profile)
        assert list(out.sites) == [mapped.base+s["site"] for s in profile["sites"]]
    else:
        assert result == 0 and bytes(out) == before
        assert b"action" in text.value and b"body changed" in text.value
    assert not api.CBMS_TestActionHookAllocation()


def test_carrier_failure_is_latched_and_wrong_thread_cannot_mutate(action_api):
    api = action_api[0]
    h = Runtime(action_api)
    assert api.CBMS_ConfigureActionCarriers(h.runtime) == 1
    try:
        assert api.CBMS_Construct(h.runtime,3,0x3000) == 1
        assert api.CBMS_ActionCopiedCarrier(h.runtime,0x3000,0x3000,1) == -1
        assert api.CBMS_ActionCarrierError() and h.errors
        results = []
        worker = threading.Thread(target=lambda:results.append(api.CBMS_ActionDestroyCarrier(h.runtime,0x3000)))
        worker.start(); worker.join()
        assert results == [-1]
        assert api.CBMS_CarrierIsOwned(h.runtime,3,0x3000) == 0
        assert api.CBMS_ActionDestroyCarrier(h.runtime,0x3000) == 1
    finally:
        assert api.CBMS_DetachActionCarriers() == 1
        h.close()
