"""Certified bank-first actor destructor chaining, without invoking engine code.

The named banking DLL below is a locally compiled counter stand-in. Game/EEex
images are read-only mappings with private COW edits; private hook pages are
never invoked. Only our compiled lifecycle carrier and counter export execute.
"""
import ctypes as C
import json
import struct
import subprocess

import pytest

from test_scroll_runtime_native import SOURCE, compiler_environment
from test_scroll_runtime_binding import windows
from test_scroll_runtime_decode_binding import images
from test_scroll_runtime_decode_host import host, PrivateSites, lookup


ORIGINAL = bytes.fromhex("4c8bdc49894b08")
PROFILES = json.loads((SOURCE / "lifecycle-profiles.json").read_text())


class Chain(C.Structure):
    _fields_ = [("schema", C.c_uint32), ("entry", C.c_size_t), ("handler", C.c_size_t),
                ("original", C.c_ubyte * 7), ("replacement", C.c_ubyte * 7)]


QUERY = C.CFUNCTYPE(C.c_int, C.c_size_t, C.POINTER(Chain), C.c_void_p)


@pytest.fixture(scope="module")
def bank(tmp_path_factory):
    directory = tmp_path_factory.mktemp("bank-chain-counter")
    source = directory / "counter.cpp"
    source.write_text(r'''
#include <stdint.h>
static uintptr_t last{};static unsigned count{};
extern "C" __declspec(dllexport) void CBMI_Destruct(void* actor){last=reinterpret_cast<uintptr_t>(actor);++count;}
extern "C" __declspec(dllexport) uintptr_t TestLast(){return last;}
extern "C" __declspec(dllexport) unsigned TestCount(){return count;}
''')
    compiler, environment, msvc = compiler_environment()
    assert msvc
    dll = directory / "cbmbank_identity.dll"
    result = subprocess.run(
        [compiler, "/nologo", "/std:c++20", "/EHsc", "/W4", "/WX", "/LD",
         str(source), f"/Fe{dll}", "/link", "/BASE:0x430000000", "/DYNAMICBASE:NO"],
        cwd=directory, env=environment, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    api = C.CDLL(str(dll))
    api.TestLast.restype, api.TestCount.restype = C.c_size_t, C.c_uint
    handler = C.cast(api.CBMI_Destruct, C.c_void_p).value
    return api, handler


@pytest.fixture(scope="module")
def chain_host(host):
    host.CBMS_BindLifecycleModulesChained.argtypes = [
        C.c_size_t, C.c_size_t, C.c_void_p, QUERY, C.c_void_p,
        C.POINTER(Chain), C.c_void_p, C.c_uint32,
    ]
    host.CBMS_BindLifecycleModulesChained.restype = C.c_int
    host.CBMS_TestInstallEffectPersistenceHooksChained.argtypes = [C.c_size_t] * 7 + [C.POINTER(Chain)]
    host.CBMS_TestInstallEffectPersistenceHooksChained.restype = C.c_int
    host.CBMS_ActorDestroyCarrier.argtypes, host.CBMS_ActorDestroyCarrier.restype = [C.c_void_p], None
    return host


def offer(entry, handler, relay):
    patch = b"\xE9" + struct.pack("<i", relay - entry - 5) + b"\x90\x90"
    return Chain(1, entry, handler, (C.c_ubyte * 7).from_buffer_copy(ORIGINAL),
                 (C.c_ubyte * 7).from_buffer_copy(patch))


def relay_bytes(relay, handler, route):
    if route == "rel32":
        return b"\xE9" + struct.pack("<i", handler - relay - 5) + b"\x90"
    return b"\xFF\x25\0\0\0\0" + struct.pack("<Q", handler)


@pytest.mark.parametrize("route", ["absolute", "rel32"])
def test_actual_mapped_lifecycle_accepts_only_reconstructed_actor_prefix(chain_host, bank, images, windows, route):
    game, dll, decode = images
    counter_before = bank[0].TestCount()
    profile = next(p for p in PROFILES if p["timestamp"] == decode["eeex_timestamp"])
    actor = profile["entries"][2]["body"]
    relay = windows.VirtualAlloc(0x420000000, 0x1000, 0x3000, 4)
    assert relay == 0x420000000
    try:
        code = relay_bytes(relay, bank[1], route)
        C.memmove(relay, code, len(code))
        old = C.c_uint32()
        assert windows.VirtualProtect(relay, 0x1000, 0x20, C.byref(old))
        proposal = offer(dll.base + actor["rva"], bank[1], relay)
        dll.write(actor["rva"], bytes(proposal.replacement))
        read_before = dll.read(actor["rva"], actor["size"])
        observations = []

        @QUERY
        def query(expected, output, user):
            observations.append((expected, user))
            C.memmove(output, C.byref(proposal), C.sizeof(proposal))
            return 1

        output, accepted, reason = (C.c_size_t * 3)(11, 22, 33), Chain(), C.create_string_buffer(512)
        assert chain_host.CBMS_BindLifecycleModulesChained(
            game.base, dll.base, output, query, 0xBEEF, C.byref(accepted), reason, len(reason)
        ) == 1, reason.value
        assert observations == [(proposal.entry, 0xBEEF)]
        assert bytes(accepted) == bytes(proposal)
        assert list(output) == [dll.base + e["body"]["rva"] for e in profile["entries"]]
        assert dll.read(actor["rva"], actor["size"]) == read_before
        assert bank[0].TestCount() == counter_before
    finally:
        assert windows.VirtualFree(relay, 0, 0x8000)


@pytest.mark.parametrize("damage", ["tail", "replacement", "handler", "relay", "refused"])
def test_changed_body_or_unverified_bank_offer_keeps_outputs_untouched(chain_host, bank, images, windows, damage):
    game, dll, decode = images
    profile = next(p for p in PROFILES if p["timestamp"] == decode["eeex_timestamp"])
    actor = profile["entries"][2]["body"]
    relay = windows.VirtualAlloc(0x420000000, 0x1000, 0x3000, 4)
    assert relay == 0x420000000
    try:
        code = relay_bytes(relay, bank[1] + (damage == "relay"), "absolute")
        C.memmove(relay, code, len(code))
        old = C.c_uint32()
        assert windows.VirtualProtect(relay, 0x1000, 0x20, C.byref(old))
        proposal = offer(dll.base + actor["rva"], bank[1], relay)
        dll.write(actor["rva"], bytes(proposal.replacement))
        if damage == "tail":
            at = actor["rva"] + actor["size"] - 1
            dll.write(at, bytes([dll.read(at, 1)[0] ^ 1]))
        elif damage == "replacement":
            proposal.replacement[1] ^= 1
        elif damage == "handler":
            proposal.handler += 1

        @QUERY
        def query(expected, output, user):
            C.memmove(output, C.byref(proposal), C.sizeof(proposal))
            return 0 if damage == "refused" else 1

        output, accepted = (C.c_size_t * 3)(11, 22, 33), Chain()
        C.memset(C.byref(accepted), 0xCA, C.sizeof(accepted))
        before = bytes(output), bytes(accepted), dll.read(actor["rva"], actor["size"])
        reason = C.create_string_buffer(512)
        assert chain_host.CBMS_BindLifecycleModulesChained(
            game.base, dll.base, output, query, None, C.byref(accepted), reason, len(reason)
        ) == 0
        assert reason.value
        assert (bytes(output), bytes(accepted), dll.read(actor["rva"], actor["size"])) == before
    finally:
        assert windows.VirtualFree(relay, 0, 0x8000)


@pytest.mark.parametrize("mode", ["success", "rollback", "later_owner"])
def test_private_host_calls_previous_handler_directly_and_restores_bank_bytes(chain_host, bank, windows, mode):
    sites = PrivateSites(windows, "absolute")
    entries = [sites.base + offset for offset in (0x300, 0x600, 0x800, 0xA00)]
    prefixes = [bytes.fromhex("405356574154415541564881ec88010000"),
                bytes.fromhex("4c8bdc49895310"), ORIGINAL]
    for address, prefix in zip(entries, prefixes):
        sites.edit(address, prefix)
    relay = sites.base + 0xC00
    sites.edit(relay, relay_bytes(relay, bank[1], "absolute"))
    proposal = offer(entries[-1], bank[1], relay)
    sites.edit(entries[-1], bytes(proposal.replacement))
    before = C.string_at(sites.base, 0x2000)
    try:
        if mode == "rollback":
            chain_host.CBMS_TestDecodeFailure(3)
        result = chain_host.CBMS_TestInstallEffectPersistenceHooksChained(
            sites.unmarshal, sites.decoder, sites.previous, *entries, C.byref(proposal)
        )
        if mode == "rollback":
            assert result == 0 and b"injected failure" in chain_host.CBMS_DecodeHookError()
            assert not chain_host.CBMS_TestDecodeAllocation()
        else:
            assert result == 1, chain_host.CBMS_DecodeHookError()
            patch = C.string_at(entries[-1], 7)
            actor_relay = entries[-1] + 5 + struct.unpack_from("<i", patch, 1)[0]
            # A leaf absolute branch reaches the prior authenticated carrier;
            # its installed relative entry jump has not been relocated.
            assert C.string_at(actor_relay + 0x20, 14) == relay_bytes(actor_relay + 0x20, bank[1], "absolute")
            assert lookup(actor_relay + 0x20)[0]
            count = bank[0].TestCount()
            chain_host.CBMS_ActorDestroyCarrier(0x12345678)
            assert bank[0].TestCount() == count + 1 and bank[0].TestLast() == 0x12345678
            if mode == "later_owner":
                sites.edit(entries[-1], b"\xCC")
                foreign = C.string_at(sites.base, 0x2000)
                assert chain_host.CBMS_RemoveDecodeHooks() == 0
                assert C.string_at(sites.base, 0x2000) == foreign
                sites.edit(entries[-1], patch)
            assert chain_host.CBMS_RemoveDecodeHooks() == 1
            assert lookup(actor_relay + 0x20)[0] is None
        assert C.string_at(sites.base, 0x2000) == before
        assert C.string_at(entries[-1], 7) == bytes(proposal.replacement)
    finally:
        if chain_host.CBMS_TestDecodeAllocation():
            assert chain_host.CBMS_RemoveDecodeHooks() == 1
        sites.close()
