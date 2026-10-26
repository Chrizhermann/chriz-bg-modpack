"""Conditional scroll carriers: compiled adapter, private hooks and read-only PE views.

Engine functions are never invoked. The native callback tests supply small explicit
update/decoder stand-ins; mapped-image tests certify bytes only.
"""
import ctypes as C
import json
import os
import struct
import subprocess

import pytest

from test_scroll_runtime_native import SOURCE, compiler_environment, configure_native_api
from test_scroll_runtime_binding import mapped, windows
from test_scroll_runtime_decode_host import lookup


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows x64 conditional adapter")
UPDATE = C.CFUNCTYPE(None, C.c_void_p, C.c_void_p, C.c_int)
DECODE = C.CFUNCTYPE(C.c_void_p, C.c_void_p)
PROFILES = json.loads((SOURCE / "conditional-profiles.json").read_text())


class Functions(C.Structure):
    _fields_ = [("update", UPDATE), ("decode", DECODE),
                ("decode_call", C.c_size_t), ("fire326_return", C.c_size_t),
                ("calls", C.c_size_t * 10), ("targets", C.c_size_t * 10)]


@pytest.fixture(scope="module")
def conditional_api(tmp_path_factory):
    build = tmp_path_factory.mktemp("scroll-conditional")
    wrapper = build / "callbacks.cpp"
    # Keep test visibility and the unrelated cast-host registration stand-in out
    # of production. TestOwner exercises the callback actually registered.
    wrapper.write_text(r'''
#include "conditional_api.h"
#include "cast_carrier_api.h"
static CBMS_AdditionalCastOwner additional{};
extern "C" void CBMS_SetAdditionalCastOwner(CBMS_AdditionalCastOwner f){additional=f;}
extern "C" CBMS_EXPORT int TestConfigure(CBMS_Runtime*r,const CBMS_ConditionalFunctions*f){return CBMS_ConfigureConditional(r,f);}
extern "C" CBMS_EXPORT int TestDetach(){return CBMS_DetachConditional();}
extern "C" CBMS_EXPORT int TestIdle(){return CBMS_ConditionalIdle();}
extern "C" CBMS_EXPORT const char* TestError(){return CBMS_ConditionalError();}
extern "C" CBMS_EXPORT void TestBefore(uint32_t i,uintptr_t*s){CBMS_ConditionalBefore(i,s);}
extern "C" CBMS_EXPORT int TestOwner(uint32_t s,uintptr_t pc,void*r,uintptr_t*out){return additional?additional(s,pc,r,out):0;}
extern "C" CBMS_EXPORT void TestUpdate(void*s,void*t,int elapsed){CBMS_RepeatingCarrier(s,t,elapsed);}
''')
    compiler, environment, msvc = compiler_environment()
    assert msvc
    library = build / "conditional.dll"
    result = subprocess.run(
        [compiler, "/nologo", "/std:c++20", "/EHsc", "/W4", "/WX", "/permissive-",
         "/LD", "/DCBMS_OFFLINE_HARNESS", f"/I{SOURCE}", str(wrapper),
         str(SOURCE / "native_api.cpp"), str(SOURCE / "conditional_api.cpp"),
         str(SOURCE / "conditional_host.cpp"), f"/Fe{library}"],
        cwd=build, env=environment, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return configure_conditional(C.CDLL(str(library)))


_ptr, _addr, _u32 = C.c_void_p, C.c_size_t, C.c_uint32
CARRIER_SIGNATURES = {
    "TestConfigure": ([_ptr, C.POINTER(Functions)], C.c_int),
    "TestDetach": ([], C.c_int), "TestIdle": ([], C.c_int),
    "TestError": ([], C.c_char_p),
    "TestBefore": ([_u32, C.POINTER(_addr)], None),
    "TestOwner": ([_u32, _addr, _ptr, C.POINTER(_addr)], C.c_int),
    "TestUpdate": ([_ptr, _ptr, C.c_int], None),
    "CBMS_TestRepeatingDecode": ([_addr, _ptr], _ptr),
    "CBMS_CarrierIsOwned": ([_ptr, _u32, _addr], C.c_int),
    "CBMS_EffectCopied": ([_ptr, _addr, _addr], C.c_int),
    "CBMS_DestructObserved": ([_ptr, _u32, _addr], C.c_int),
}
HOST_SIGNATURES = {
    "CBMS_BindConditional": ([_addr, C.POINTER(Functions), _ptr, _u32], C.c_int),
    "CBMS_TestInstallConditional": ([C.POINTER(Functions), _ptr], C.c_int),
    "CBMS_TestConditionalAllocation": ([C.c_int], _addr),
    "CBMS_RemoveConditionalHooks": ([], C.c_int),
    "CBMS_ConditionalHookError": ([], C.c_char_p),
}


def configure_conditional(library, host=True):
    """Native-API and conditional wrapper (and host) signatures of a harness build
    whose callbacks.cpp exports the Test* entrances above."""
    api, resolver, reporter = configure_native_api(library)
    for name, (arguments, returns) in {**CARRIER_SIGNATURES, **(HOST_SIGNATURES if host else {})}.items():
        fn = getattr(api, name)
        fn.argtypes, fn.restype = arguments, returns
    return api, resolver, reporter


class Harness:
    def __init__(self, api_tuple):
        self.api, resolver_type, reporter_type = api_tuple
        self.errors, self.resolutions, self.buffers = [], [], []
        self.effects = set()

        @resolver_type
        def resolve(reader, generation, spell, kind, out, context):
            self.resolutions.append((reader, generation, spell, kind))
            out.contents.count = 1
            out.contents.level[0] = 12
            out.contents.active[0] = 1
            return 1

        self.resolve = resolve
        self.report = reporter_type(lambda message, _: self.errors.append(message.decode()))
        self.runtime = self.api.CBMS_Create(self.resolve, self.report, None)
        assert self.runtime
        self.update_body = lambda self_, target, elapsed: None
        self.decode_body = lambda raw: None
        self.update = UPDATE(lambda s, t, n: self.update_body(s, t, n))
        self.decode = DECODE(lambda raw: self.decode_body(raw))
        self.functions = Functions(self.update, self.decode, 0x11000, 0x12005,
                                   (C.c_size_t * 10)(*(0x13000 + i * 0x100 for i in range(10))),
                                   (C.c_size_t * 10)(*(0x15000 + i * 0x100 for i in range(10))))
        assert self.api.TestConfigure(self.runtime, C.byref(self.functions)) == 1
        self.reader = 0x7000
        assert self.api.CBMS_Construct(self.runtime, 0, self.reader) == 1

    def buffer(self, size=0x200):
        value = C.create_string_buffer(b"\xA5" * size)
        self.buffers.append(value)
        return C.addressof(value)

    def own(self, address=None):
        address = address or self.buffer()
        self.effects.add(address)
        assert self.api.CBMS_Construct(self.runtime, 1, address) == 1
        use = C.c_uint64()
        assert self.api.CBMS_ItemBegin(self.runtime, self.reader, b"SCROLL", 0, 0, C.byref(use)) == 1
        assert self.api.CBMS_ItemChild(self.runtime, use, address, 0) == 1
        assert self.api.CBMS_ItemEnd(self.runtime, use) == 1
        return address

    def applied_parent(self):
        root, parent = self.own(), self.buffer()
        assert self.api.CBMS_Construct(self.runtime, 1, parent) == 1
        frame, level = C.c_uint64(), C.c_uint32()
        assert self.api.CBMS_BeginCast(self.runtime, 1, root, 0, 0xD000, b"PARENT", 0,
                                      1, 2, 3, 4, C.byref(frame)) == 1
        assert self.api.CBMS_Select(self.runtime, frame, 0, 0xD000, C.byref(level)) == 1
        assert level.value == 6
        assert self.api.CBMS_SpellChild(self.runtime, frame, 0xD000, parent, C.byref(level)) == 1
        assert self.api.CBMS_EndCast(self.runtime, frame) == 1
        return parent

    def owner(self, selector, pc, receiver):
        effect = C.c_size_t(0xCAFE)
        result = self.api.TestOwner(selector, pc, receiver, C.byref(effect))
        return result, effect.value

    def snapshot(self, index, contingency, receiver):
        snapshot = (C.c_size_t * 17)(*(0xA000 + n for n in range(17)))
        snapshot[10], snapshot[14] = contingency, receiver
        snapshot[16] = self.functions.calls[index] + 5
        return snapshot

    def close(self):
        assert self.api.TestIdle() == 1
        assert self.api.TestDetach() == 1
        assert self.owner(0, self.functions.fire326_return, 1) == (0, 0xCAFE)
        # End the explicit synthetic effect lifetimes before destroying the
        # core, which correctly refuses to discard outstanding owned carriers.
        for address in self.effects | {C.addressof(value) for value in self.buffers}:
            assert self.api.CBMS_DestructObserved(self.runtime, 1, address) == 1
        assert self.api.CBMS_Quiescent(self.runtime) == 1
        assert self.api.CBMS_Destroy(self.runtime) == 1


@pytest.fixture
def h(conditional_api):
    value = Harness(conditional_api)
    try:
        yield value
    finally:
        value.close()


def test_326_requires_exact_native_return_and_current_owned_self(h):
    parent, unrelated = h.own(), h.buffer()
    pc = h.functions.fire326_return
    assert h.owner(0, pc, parent) == (1, parent)
    assert h.owner(0, pc + 1, parent) == (0, 0xCAFE)
    assert h.owner(1, pc, parent) == (0, 0xCAFE)
    assert h.owner(0, pc, unrelated) == (0, 0xCAFE)
    # Native copies preserve the context; destruction ends this incarnation.
    copied = h.buffer()
    assert h.api.CBMS_EffectCopied(h.runtime, parent, copied) == 1
    assert h.owner(0, pc, copied) == (1, copied)
    assert h.api.CBMS_DestructObserved(h.runtime, 1, copied) == 1
    assert h.owner(0, pc, copied) == (0, 0xCAFE)
    assert h.api.CBMS_Construct(h.runtime, 1, copied) == 1
    assert h.owner(0, pc, copied) == (0, 0xCAFE)
    assert not h.api.TestError() and not h.errors


@pytest.mark.parametrize("index", range(6))
def test_232_each_cast_edge_uses_embedded_effect_once_and_masks_unowned(h, index):
    contingency, receiver = h.buffer(0x300), h.buffer()
    embedded = h.own(contingency + 0x78)
    snapshot = h.snapshot(index, contingency, receiver)
    before = bytes(snapshot)
    h.api.TestBefore(index, snapshot)
    assert bytes(snapshot) == before and h.api.TestIdle() == 0
    assert h.owner(1, snapshot[16], receiver) == (1, embedded)
    assert h.api.TestIdle() == 1
    # A nested Fire without its own native CALL edge cannot borrow the parent.
    assert h.owner(1, snapshot[16], receiver) == (0, 0xCAFE)
    unrelated = h.buffer(0x300)
    nested = h.snapshot(index, unrelated, receiver)
    h.api.TestBefore(index, nested)
    assert h.owner(1, nested[16], receiver) == (0, 0xCAFE)
    # A later legitimate activation continues to work.
    h.api.TestBefore(index, snapshot)
    assert h.owner(1, snapshot[16], receiver) == (1, embedded)
    assert not h.api.TestError() and not h.errors


@pytest.mark.parametrize("wrong", ["site", "caller", "receiver"])
def test_232_crossed_native_boundary_does_not_attach_context(h, wrong):
    contingency, receiver = h.buffer(0x300), h.buffer()
    h.own(contingency + 0x78)
    snapshot = h.snapshot(0, contingency, receiver)
    if wrong == "site":
        snapshot[16] += 1
    h.api.TestBefore(0, snapshot)
    assert h.owner(1, snapshot[16] + (wrong == "caller"), receiver + (wrong == "receiver")) == (0, 0xCAFE)
    assert h.api.TestError()
    assert h.api.TestIdle() == 1


@pytest.mark.parametrize("index", range(6, 10))
def test_232_cleanup_subtracts_sound_member_offset_and_clears_reused_address(h, index):
    target, other = h.own(), h.own()
    snapshot = h.snapshot(index, other, target + 0x130)
    h.api.TestBefore(index, snapshot)
    assert h.api.CBMS_CarrierIsOwned(h.runtime, 1, target) == 0
    assert h.api.CBMS_CarrierIsOwned(h.runtime, 1, other) == 1
    # Duplicate destruction and an untracked embedded effect remain harmless.
    h.api.TestBefore(index, snapshot)
    snapshot[14] = h.buffer() + 0x130
    h.api.TestBefore(index, snapshot)
    assert h.api.CBMS_Construct(h.runtime, 1, target) == 1
    assert h.api.CBMS_CarrierIsOwned(h.runtime, 1, target) == 0
    assert not h.api.TestError() and not h.errors


def test_272_only_native_update_decoder_inherits_and_nested_unowned_update_masks(h):
    parent = h.applied_parent()
    copied = h.buffer()
    assert h.api.CBMS_EffectCopied(h.runtime, parent, copied) == 1
    owned_self, unowned_self = h.buffer(), h.buffer()
    C.c_size_t.from_address(owned_self + 0x38).value = copied
    C.c_size_t.from_address(unowned_self + 0x38).value = h.buffer()
    children, calls = [], []
    exact = h.functions.decode_call + 5

    def decode(raw):
        child = h.buffer()
        children.append(child)
        return child

    def update(self_, target, elapsed):
        calls.append((self_, target, elapsed, h.api.TestIdle()))
        if self_ == owned_self:
            h.api.CBMS_TestRepeatingDecode(exact + 1, 0x777)
            h.api.TestUpdate(unowned_self, target, elapsed + 1)
            h.api.CBMS_TestRepeatingDecode(exact, 0x888)
        else:
            h.api.CBMS_TestRepeatingDecode(exact, 0x999)

    h.decode_body, h.update_body = decode, update
    h.api.CBMS_TestRepeatingDecode(exact, 0x666)  # no enclosing Update
    for _ in range(2):
        h.api.TestUpdate(owned_self, 0xABCDE, 17)
    assert calls == [(owned_self, 0xABCDE, 17, 0), (unowned_self, 0xABCDE, 18, 0)] * 2
    assert len(children) == 7
    for i, child in enumerate(children):
        expected = bytearray(b"\xA5" * 0x200)
        owned = i in (3, 6)
        if owned:
            struct.pack_into("<I", expected, 0xC8, 6)
        assert C.string_at(child, 0x200) == expected
        assert h.api.CBMS_CarrierIsOwned(h.runtime, 1, child) == int(owned)
    # The eventual child resolves its own spell using the original reader.
    frame, level = C.c_uint64(), C.c_uint32(99)
    assert h.api.CBMS_BeginCast(h.runtime, 1, children[-1], 0, 0xD100, b"CHILD", 1,
                              22, 33, 44, 55, C.byref(frame)) == 1
    assert h.api.CBMS_Select(h.runtime, frame, 0, 0xD100, C.byref(level)) == 1
    assert h.resolutions[-1][0] == h.reader and h.resolutions[-1][2] == 0xD100
    assert level.value == 6
    assert h.api.CBMS_EndCast(h.runtime, frame) == 1
    assert not h.api.TestError() and not h.errors


def test_272_null_decode_and_unselected_parent_never_invent_an_applied_level(h):
    parent, self_ = h.own(), h.buffer()
    C.c_size_t.from_address(self_ + 0x38).value = parent
    outputs = []
    h.update_body = lambda s, t, n: outputs.append(h.api.CBMS_TestRepeatingDecode(h.functions.decode_call + 5, 0))
    h.api.TestUpdate(self_, 0, 1)
    assert outputs == [None]
    child = h.buffer()
    before = C.string_at(child, 0x200)
    h.decode_body = lambda raw: child
    h.api.TestUpdate(self_, 0, 2)
    assert outputs[-1] == child and C.string_at(child, 0x200) == before
    assert h.api.CBMS_CarrierIsOwned(h.runtime, 1, child) == 1
    assert not h.api.TestError() and not h.errors


@pytest.mark.parametrize("damage", [None, "body", "missing_fix"])
def test_pinned_conditional_profile_relocated_binding_is_read_only(conditional_api, mapped, damage):
    api = conditional_api[0]
    profile = next(p for p in PROFILES if p["version"] == mapped.profile["version"])
    if damage != "missing_fix":
        mapped.write(profile["fix"], b"\xE9" + struct.pack("<i", 0x280000 - profile["fix"] - 5) + b"\x90\x90")
    if damage == "body":
        at = profile["spans"][3]["rva"] + profile["spans"][3]["size"] - 1
        mapped.write(at, bytes([mapped.read(at, 1)[0] ^ 1]))
    before = [mapped.read(s["rva"], s["size"]) for s in profile["spans"]]
    out, reason = Functions(), C.create_string_buffer(512)
    C.memset(C.byref(out), 0xCA, C.sizeof(out))
    untouched = bytes(out)
    result = api.CBMS_BindConditional(mapped.base, C.byref(out), reason, len(reason))
    assert before == [mapped.read(s["rva"], s["size"]) for s in profile["spans"]]
    if damage:
        assert result == 0 and bytes(out) == untouched and reason.value
    else:
        assert result == 1, reason.value
        assert C.cast(out.update, C.c_void_p).value == mapped.base + profile["update"]
        assert C.cast(out.decode, C.c_void_p).value == mapped.base + profile["decoder"]
        assert out.decode_call == mapped.base + profile["decode_call"]
        assert out.fire326_return == mapped.base + profile["fire326_return"]
        assert list(out.calls) == [mapped.base + r for r in profile["calls"]]
        assert list(out.targets) == [mapped.base + r for r in profile["targets"]]


class Sites:
    """Private executable bytes are patch targets only, never called."""
    def __init__(self, windows, functions):
        self.windows = windows
        self.base = windows.VirtualAlloc(None, 0x3000, 0x3000, 4)
        assert self.base
        self.functions = Functions.from_buffer_copy(bytes(functions))
        self.functions.update = UPDATE(self.base + 0x100)
        self.functions.decode = DECODE(self.base + 0x200)
        self.functions.decode_call = self.base + 0x300
        self.sites = [self.base + 0x400 + i * 0x100 for i in range(10)]
        self.original = {self.base + 0x100: bytes.fromhex("40 53 41 56 48 83 EC 68")}
        self.original[self.base + 0x300] = b"\xE8" + struct.pack("<i", -0x105)
        for i, at in enumerate(self.sites):
            target = self.base + 0x2000 + i * 0x10
            self.functions.calls[i], self.functions.targets[i] = at, target
            self.original[at] = b"\xE8" + struct.pack("<i", target - at - 5)
        for at, value in self.original.items():
            C.memmove(at, value, len(value))
        self.before = C.string_at(self.base, 0x3000)
        old = C.c_uint32()
        assert windows.VirtualProtect(self.base, 0x3000, 0x20, C.byref(old))

    def edit(self, at, data):
        old, ignored = C.c_uint32(), C.c_uint32()
        assert self.windows.VirtualProtect(at, len(data), 0x40, C.byref(old))
        C.memmove(at, data, len(data))
        assert self.windows.VirtualProtect(at, len(data), old.value, C.byref(ignored))

    def close(self):
        assert self.windows.VirtualFree(self.base, 0, 0x8000)


@pytest.mark.parametrize("damage", [None, "install_last_call", "later_owner"])
def test_twelve_private_hook_sites_restore_or_refuse_without_partial_removal(conditional_api, windows, damage):
    h = Harness(conditional_api)
    api = h.api
    assert api.TestDetach() == 1
    sites = Sites(windows, h.functions)
    try:
        if damage == "install_last_call":
            sites.edit(sites.sites[-1], b"\xCC")
        before = C.string_at(sites.base, 0x3000)
        installed = api.CBMS_TestInstallConditional(C.byref(sites.functions), h.runtime)
        if damage == "install_last_call":
            assert installed == 0 and api.CBMS_ConditionalHookError()
            assert not api.CBMS_TestConditionalAllocation(0) and not api.CBMS_TestConditionalAllocation(1)
            assert C.string_at(sites.base, 0x3000) == before
            sites.edit(sites.sites[-1], sites.original[sites.sites[-1]])
        else:
            assert installed == 1, api.CBMS_ConditionalHookError()
            entry, calls = api.CBMS_TestConditionalAllocation(0), api.CBMS_TestConditionalAllocation(1)
            assert entry and calls and api.TestIdle() == 1
            patched = C.string_at(sites.base, 0x3000)
            for i, at in enumerate(sites.sites):
                data = C.string_at(at, 5)
                assert data[0] == 0xE8
                destination = at + 5 + struct.unpack_from("<i", data, 1)[0]
                assert destination == calls + i * 0x200
                assert lookup(destination)[1] == calls
            if damage == "later_owner":
                sites.edit(sites.sites[-1], b"\xCC")
                foreign = C.string_at(sites.base, 0x3000)
                assert api.CBMS_RemoveConditionalHooks() == 0
                assert C.string_at(sites.base, 0x3000) == foreign
                offset = sites.sites[-1] - sites.base
                sites.edit(sites.sites[-1], patched[offset:offset + 5])
            assert api.CBMS_RemoveConditionalHooks() == 1
            assert lookup(calls)[0] is None and lookup(entry + 0x20)[0] is None
        assert C.string_at(sites.base, 0x3000) == sites.before
    finally:
        if api.CBMS_TestConditionalAllocation(0):
            assert api.CBMS_RemoveConditionalHooks() == 1
        sites.close()
        assert api.CBMS_Destroy(h.runtime) == 1
