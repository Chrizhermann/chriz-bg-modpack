"""Every hooked native entry, entered on a thread other than its engine thread.

Such a call must reach its native original unchanged (arguments and result),
touch no carrier state, latch the process-wide foreign state that disables
every override, and keep carrier removal waiting while it runs. Each test loads
its own copy of the compiled carriers: that latch is permanent by design.
Native callees are the substitutes of the per-group carrier tests.
"""
import ctypes as C
import shutil
import subprocess
import threading

import pytest

from test_scroll_runtime_native import SOURCE, compiler_environment, configure_native_api
from test_scroll_runtime_actor_archive import allocated, runtime_fixture
import test_scroll_runtime_cast_carriers as cast
import test_scroll_runtime_conditional as conditional
import test_scroll_runtime_dispatch_carriers as dispatch
import test_scroll_runtime_item_carriers as item
import test_scroll_runtime_linked177 as linked


UNITS = ("native_api.cpp", "eeex_save_bridge.cpp", "decode_carrier_api.cpp", "marshal_carrier_api.cpp",
         "lifecycle_carrier_api.cpp", "item_carrier_api.cpp", "dispatch_carrier_api.cpp", "cast_carrier_api.cpp",
         "linked177_api.cpp", "conditional_api.cpp")
# The conditional entrances its own tests use; here the real cast carriers
# hold the additional cast owner, so TestOwner calls that callback directly.
CALLBACKS = r'''
#include "conditional_api.h"
extern "C" CBMS_EXPORT int TestConfigure(CBMS_Runtime*r,const CBMS_ConditionalFunctions*f){return CBMS_ConfigureConditional(r,f);}
extern "C" CBMS_EXPORT int TestDetach(){return CBMS_DetachConditional();}
extern "C" CBMS_EXPORT int TestIdle(){return CBMS_ConditionalIdle();}
extern "C" CBMS_EXPORT const char* TestError(){return CBMS_ConditionalError();}
extern "C" CBMS_EXPORT void TestBefore(uint32_t i,uintptr_t*s){CBMS_ConditionalBefore(i,s);}
extern "C" CBMS_EXPORT int TestOwner(uint32_t s,uintptr_t pc,void*r,uintptr_t*out){return CBMS_ConditionalOwnerAt(s,pc,r,out);}
extern "C" CBMS_EXPORT void TestUpdate(void*s,void*t,int elapsed){CBMS_RepeatingCarrier(s,t,elapsed);}
'''
UNMARSHAL = C.CFUNCTYPE(None, C.c_void_p, C.c_void_p, C.c_uint32, C.c_void_p, C.c_uint8)
DECODE = C.CFUNCTYPE(C.c_void_p, C.c_void_p)
MARSHAL = C.CFUNCTYPE(C.c_uint32, C.c_void_p, C.POINTER(C.c_void_p), C.c_uint8, C.c_int, C.c_int)
COPY = C.CFUNCTYPE(None, C.c_void_p, C.c_void_p)
DESTROY = C.CFUNCTYPE(None, C.c_void_p)
ptr, u32 = C.c_void_p, C.c_uint32
PERSISTENCE = {
    "ConfigureDecodeCarrier": ([UNMARSHAL, DECODE], C.c_int), "DetachDecodeCarrier": ([], C.c_int),
    "DecodeCarrierIdle": ([], C.c_int), "UnmarshalCarrier": ([ptr, ptr, u32, ptr, C.c_uint8], None),
    "DecodeCarrier": ([ptr], ptr),
    "ConfigureMarshalCarrier": ([MARSHAL], C.c_int), "DetachMarshalCarrier": ([], C.c_int),
    "MarshalCarrierIdle": ([], C.c_int), "ClaimMarshalActor": ([ptr], C.c_int),
    "MarshalCarrier": ([ptr, C.POINTER(ptr), C.c_uint8, C.c_int, C.c_int], u32),
    "ConfigureLifecycleCarriers": ([COPY, DESTROY, DESTROY], C.c_int), "DetachLifecycleCarriers": ([], C.c_int),
    "LifecycleCarriersIdle": ([], C.c_int), "EffectCopyCarrier": ([ptr, ptr], None),
    "EffectDestroyCarrier": ([ptr], None), "ActorDestroyCarrier": ([ptr], None),
    "EEexAttachForTest": ([ptr], C.c_int), "EEexConfigureCurrent": ([], C.c_int),
    "EEexBridgeHealthy": ([], C.c_int), "EEexBridgeError": ([], C.c_char_p),
    "EEexBeforeEffectMarshal": ([ptr, ptr, C.POINTER(ptr), u32], None),
    "EEexAfterEffectMarshal": ([ptr, u32], None), "EEexBeginEffectUnmarshal": ([ptr, u32], None),
    "EEexEffectDecoded": ([ptr, ptr, ptr], None), "EEexAfterActorUUID": ([ptr, C.c_uint64], None),
    "EEexLiveEffectCopied": ([ptr, ptr], None), "EEexEffectDestroyed": ([ptr], None),
    "EEexActorDestroyed": ([ptr], None), "EEexCancelledActorIO": ([ptr], C.c_int),
    "EEexDetachQuiescent": ([], C.c_int), "EEexExportText": ([ptr], C.c_char_p),
    "EEexStageText": ([ptr, C.c_char_p, u32], C.c_int), "EEexImportFinished": ([ptr], C.c_int),
    "EEexImportDropped": ([ptr], C.c_char_p),
    "EEexRejectEnvelope": ([C.c_char_p], None), "ActorIsObserved": ([ptr, C.c_size_t], C.c_int),
}


@pytest.fixture(scope="module")
def carriers(tmp_path_factory):
    directory = tmp_path_factory.mktemp("scroll-foreign-thread")
    wrapper = directory / "callbacks.cpp"
    wrapper.write_text(CALLBACKS)
    compiler, environment, msvc = compiler_environment()
    assert msvc
    library = directory / "carriers.dll"
    result = subprocess.run(
        [compiler, "/nologo", "/std:c++20", "/EHsc", "/W4", "/WX", "/permissive-", "/LD",
         "/DCBMS_OFFLINE_HARNESS", f"/I{SOURCE}", str(wrapper), *(str(SOURCE / unit) for unit in UNITS),
         f"/Fe{library}"],
        cwd=directory, env=environment, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return library


@pytest.fixture
def fresh(carriers, tmp_path):
    """A private copy of the carriers, so its foreign latch starts clear."""
    copy = tmp_path / "carriers.dll"
    shutil.copyfile(carriers, copy)
    library = C.CDLL(str(copy))
    native = cast.configure_cast(dispatch.configure_dispatch(library))
    item.configure_items(library)
    linked.configure_linked(library, host=False)
    conditional.configure_conditional(library, host=False)
    for name, (arguments, result) in PERSISTENCE.items():
        function = getattr(library, "CBMS_" + name)
        function.argtypes, function.restype = arguments, result
    assert library.CBMS_ForeignEntrySeen() == 0
    return native


def on_thread(call):
    """Runs call() on a new thread; returns its result or raises its error."""
    box = {}

    def run():
        try:
            box["value"] = call()
        except BaseException as error:  # re-raised on the test thread
            box["error"] = error
    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


class Held:
    """A native original that stays inside its call until released, so the
    owner thread can look at a foreign call in flight."""

    def __init__(self):
        self.entered, self.released = threading.Event(), threading.Event()

    def __call__(self, *_):
        self.entered.set()
        self.released.wait(30)

    def run(self, call, during):
        box = {}
        thread = threading.Thread(target=lambda: box.setdefault("value", call()))
        thread.start()
        try:
            assert self.entered.wait(30)
            during()
        finally:
            self.released.set()
            thread.join()
        return box.get("value")


def latched(api, runtime):
    return api.CBMS_ForeignEntrySeen() == 1 and api.CBMS_OverridesDisabled(runtime) == 1


def test_dispatch_and_cast_entries_forward_unchanged(fresh):
    h = cast.CastHarness(fresh)
    try:
        api, target, spell = h.api, h.sprite_address, C.addressof(h.spell)
        early = h.effect(146, 2)  # owned before the foreign call
        # On the engine thread this owned mode0 with a foreign message class
        # would latch a carrier fault; the foreign call only forwards.
        root = h.effect(146, 0, 1)
        h.on_apply = lambda effect, where: h.insert(146, 1, vtable=0xDEADBEEF)
        assert on_thread(lambda: api.CBMS_Apply146Carrier(C.addressof(root), 0x9876)) == -71
        message = C.addressof(h.inserts[0])
        assert h.events[:2] == [("apply", C.addressof(root), 0x9876), ("add", 0x3000, message, 0)]
        assert C.c_size_t.from_buffer(h.inserts[0], 0x90).value == h.strings.empty and not h.witnesses
        assert latched(api, h.runtime) and api.CBMS_DispatchCarrierError() == b""
        h.on_apply = lambda effect, where: None
        other = h.effect(148, 1)
        assert on_thread(lambda: api.CBMS_Apply148Carrier(C.addressof(other), 0x5432)) == -71
        assert h.events[-1] == ("apply", C.addressof(other), 0x5432)
        on_thread(lambda: h.action(caller=100))  # the audited constructor call, forwarded
        fire = C.addressof(on_thread(h.message))
        on_thread(lambda: api.CBMS_FireMessageRunCarrier(fire))
        assert h.events[-2:] == [("add", 0x3000, fire, -7), ("run", fire)]
        assert on_thread(lambda: api.CBMS_FireMessageDestroyCarrier(fire, 0x80000001)) == fire
        assert h.events[-1] == ("destroy", fire, 0x80000001)
        assert on_thread(lambda: h.owner(1, 103, 0x8888)) == (0, 99, 0xBAD)
        # Cast entries and the child and selection call bridges.
        on_thread(lambda: api.CBMS_TestEffectFireCarrier(104, C.addressof(root), spell + 8, target, 17, 10, 0x555))
        assert h.entries[-1] == (0, (C.addressof(root), spell + 8, target, 17, 10, 0x555))
        for path in (1, 2):
            assert on_thread(lambda: api.CBMS_TestFireCarrier(path, 102 + path, target, spell + 8, 0x345,
                                                              17, -1, 0x567, 19, 23)) == -219
            assert h.entries[-1] == (path, (target, spell + 8, 0x345, 17, -1, 0x567, 19, 23))
        for path, name, arguments in ((3, "Force", (target, 0x345)), (4, "ForcePoint", (target,)),
                                      (5, "Spell", (target, 0x345)), (6, "SpellPoint", (target,))):
            assert on_thread(lambda: getattr(api, f"CBMS_{name}Carrier")(*arguments)) == -219
            assert h.entries[-1] == (path, arguments)
        child = on_thread(h.produce)
        assert child == C.addressof(h.created[-1]) and bytes(h.created[-1]) == bytes([0xA5]) * 0x160
        assert h.entries[-1] == ("child", (spell, 4, 9, 0x7654))
        saved, before = on_thread(lambda: h.scalar(path=5, pc=777))  # a wrong site on the engine thread
        assert bytes(saved) == before and h.scalars[-1] == 7 and api.CBMS_CastCarrierError() == b""
        # Removal waits for a foreign call in flight.
        held = Held()
        h.on_cast = held

        def casting():
            assert api.CBMS_CastCarriersIdle() == 0 and api.CBMS_DetachCastCarriers() == 0
        assert held.run(lambda: api.CBMS_SpellCarrier(target, 0x345), casting) == -219
        held = Held()
        h.on_run = held

        def running():
            assert api.CBMS_DispatchCarriersIdle() == 0 and api.CBMS_DetachDispatchCarriers() == 0
        held.run(lambda: api.CBMS_FireMessageRunCarrier(fire), running)
        assert api.CBMS_CastCarriersIdle() == 1 and api.CBMS_DispatchCarriersIdle() == 1
        # Afterwards the effect owned before casts at its native level on the
        # engine thread, and its reader is never queried.
        count = len(h.scalars)
        h.on_cast, h.on_run = lambda: (h.scalar(), h.produce()), lambda message: None
        h.on_apply = lambda effect, where: api.CBMS_TestEffectFireCarrier(104, effect, spell + 8, where, 17, 10, 0x555)
        assert api.CBMS_Apply146Carrier(C.addressof(early), target) == -71
        assert h.scalars[count:] == [7] and C.c_uint32.from_buffer(h.created[-1], 0xC8).value == 0xA5A5A5A5
        assert not h.calls and api.CBMS_DispatchCarrierError() == b"" and api.CBMS_CastCarrierError() == b""
    finally:
        h.close()


def test_item_entries_forward_unchanged(fresh):
    h = item.Harness(fresh)
    try:
        api, reader = h.api, 0x3000  # unobserved: the engine thread would register it
        assert h.configured == 1
        h.on_use = lambda actor, target: h.root()
        assert api.CBMS_UseItemCarrier(0x1000, 0x2000) == 0xFEDC
        owned = C.addressof(h.effects[-1])  # owned before the foreign call
        assert api.CBMS_CarrierIsOwned(h.runtime, 1, owned) == 1
        start = len(h.arguments)

        def use(actor, target):
            h.root(0, actor, 0)
            h.root(0, actor, 1, ability=3)  # absent from the policy: an engine-thread fault
        h.on_use = use
        assert on_thread(lambda: api.CBMS_UseItemCarrier(reader, 0x12345678)) == 0xFEDC
        assert h.arguments[start:] == [("use", reader, 0x12345678), ("root", h.item_address, 2, 0, reader),
                                       ("root", h.item_address, 3, 1, reader)]
        assert latched(api, h.runtime) and api.CBMS_ItemCarrierError() == b""
        assert api.CBMS_ActorIsObserved(h.runtime, reader) == 0
        assert on_thread(lambda: api.CBMS_UsePointCarrier(reader)) == 0xEDCB
        assert ("point", reader) in h.arguments
        h.on_use = lambda actor, target: None
        assert on_thread(lambda: h.fire(reader, 0, 200)) == 0xDCBA
        assert on_thread(lambda: h.fire(reader, 1, 201)) == 0xDCBA
        assert h.arguments[-2:] == [("fire", reader, h.item_address, 2, 0xAABBCCDD)] * 2
        effect = on_thread(lambda: h.root(0, reader, 5))
        assert effect == C.addressof(h.effects[-1]) and h.arguments[-1] == ("root", h.item_address, 2, 5, reader)
        assert all(C.c_uint32.from_buffer(value, 0xC8).value == 10 for value in h.effects)
        assert api.CBMS_ActorIsObserved(h.runtime, reader) == 0 and api.CBMS_ItemCarrierError() == b""
        held = Held()
        h.on_use = held

        def using():
            assert api.CBMS_ItemCarriersIdle() == 0 and api.CBMS_DetachItemCarriers() == 0
        assert held.run(lambda: api.CBMS_UseItemCarrier(reader, 7), using) == 0xFEDC
        assert api.CBMS_ItemCarriersIdle() == 1
        # Afterwards the root owned before casts at its native level, and a new
        # scroll read on the engine thread starts no ownership.
        frame, level = C.c_uint64(), C.c_uint32(10)
        assert api.CBMS_BeginCast(h.runtime, 1, owned, 0, 0xD000, b"SPELL", 0, 2, 3, 4, 5, C.byref(frame)) == 1
        assert api.CBMS_Select(h.runtime, frame, 0, 0xD000, C.byref(level)) == 0 and level.value == 10
        assert api.CBMS_EndCast(h.runtime, frame) == 1 and not h.calls
        h.on_use = lambda actor, target: h.root()
        assert api.CBMS_UseItemCarrier(0x1000, 0x2000) == 0xFEDC
        assert api.CBMS_CarrierIsOwned(h.runtime, 1, C.addressof(h.effects[-1])) == 0
    finally:
        h.close()


def test_linked177_entries_forward_unchanged(fresh):
    h = linked.Harness(fresh)
    try:
        api = h.api
        selected = h.effect(owned=True, selected=True)  # an owned parent with an applied level
        parent = h.effect(owned=True)
        C.c_uint32.from_buffer(parent, 0x10).value = 999  # opcode disagreement: an engine-thread fault
        before, results = bytes(parent), []
        h.on_apply = lambda effect, where: results.append(api.CBMS_TestLinked177Decode(105, 0x1234))
        assert on_thread(lambda: api.CBMS_Linked177Apply(C.addressof(parent), 0x9876)) == -35
        assert h.events == [("apply", C.addressof(parent), 0x9876), ("decode", 0x1234)]
        assert results == [C.addressof(h.effects[-1])] and C.string_at(results[0], 0x160) == bytes([0xA7]) * 0x160
        assert bytes(parent) == before and latched(api, h.runtime) and api.CBMS_Linked177Error() == b""
        assert on_thread(lambda: api.CBMS_TestLinked177Decode(105, 0x5678)) == C.addressof(h.effects[-1])
        held = Held()
        h.on_apply = held

        def applying():
            assert api.CBMS_Linked177Idle() == 0 and api.CBMS_DetachLinked177() == 0
        assert held.run(lambda: api.CBMS_Linked177Apply(C.addressof(parent), 1), applying) == -35
        assert api.CBMS_Linked177Idle() == 1
        # Afterwards the owned parent's decoded child keeps its native level.
        results.clear()
        h.on_apply = lambda effect, where: results.append(api.CBMS_TestLinked177Decode(105, 0x9ABC))
        assert api.CBMS_Linked177Apply(C.addressof(selected), 0x9876) == -35
        assert C.string_at(results[0], 0x160) == bytes([0xA7]) * 0x160
        assert api.CBMS_CarrierIsOwned(h.runtime, 1, results[0]) == 0 and api.CBMS_Linked177Error() == b""
    finally:
        h.close()


def test_conditional_entries_forward_unchanged(fresh):
    h = conditional.Harness(fresh)
    try:
        api, exact = h.api, h.functions.decode_call + 5
        parent = h.applied_parent()  # owned, with an applied level
        repeating = h.buffer()
        C.c_size_t.from_address(repeating + 0x38).value = parent
        contingency, receiver = h.buffer(0x300), h.buffer()
        h.own(contingency + 0x78)
        calls, child = [], h.buffer()

        def decode(raw):
            calls.append(("decode", raw))
            return child

        def update(self_, target, elapsed):
            calls.append(("update", self_, target, elapsed))
            calls.append(("decoded", api.CBMS_TestRepeatingDecode(exact, 0x888)))
        h.decode_body, h.update_body = decode, update
        on_thread(lambda: api.TestUpdate(repeating, 0xABCDE, 17))
        assert calls == [("update", repeating, 0xABCDE, 17), ("decode", 0x888), ("decoded", child)]
        assert C.string_at(child, 0x200) == b"\xA5" * 0x200 and latched(api, h.runtime)
        snapshot = h.snapshot(0, contingency, receiver)
        snapshot[16] += 1  # a wrong CALL identity: an engine-thread fault
        before = bytes(snapshot)
        on_thread(lambda: api.TestBefore(0, snapshot))
        assert bytes(snapshot) == before and on_thread(lambda: h.owner(1, snapshot[16], receiver)) == (0, 0xCAFE)
        assert not api.TestError() and not h.errors
        held = Held()
        h.update_body = held

        def updating():
            assert api.TestIdle() == 0 and api.TestDetach() == 0
        held.run(lambda: api.TestUpdate(repeating, 0, 1), updating)
        assert api.TestIdle() == 1
        # Afterwards the owned repeating effect's child keeps its native level.
        later = h.buffer()
        h.decode_body = lambda raw: later
        h.update_body = lambda self_, target, elapsed: api.CBMS_TestRepeatingDecode(exact, 0x999)
        api.TestUpdate(repeating, 0, 2)
        assert C.string_at(later, 0x200) == b"\xA5" * 0x200 and api.CBMS_CarrierIsOwned(h.runtime, 1, later) == 0
        assert not api.TestError() and not h.errors
    finally:
        h.close()


def test_persistence_and_bridge_entries_forward_unchanged(fresh):
    api, runtime, resolve, report, calls, errors = runtime_fixture(fresh)
    assert api.CBMS_EEexAttachForTest(runtime) == 1
    observed, hold = [], [None]

    def holding():
        if hold[0]:
            hold[0]()

    @DECODE
    def native_decode(raw):
        observed.append(("decode", raw))
        return 0x7777

    @UNMARSHAL
    def previous(list_pointer, data, size, actor, version):
        observed.append(("previous", list_pointer, data, size, actor, version))
        observed.append(("decoded", api.CBMS_DecodeCarrier(data)))
        holding()

    @MARSHAL
    def marshal(list_pointer, output, version, permanent, skip):
        observed.append(("marshal", list_pointer, version, permanent, skip))
        observed.append(("claim", api.CBMS_ClaimMarshalActor(0x1000), api.CBMS_EEexExportText(0x1000)))
        holding()
        output[0] = 0xABCDEF
        return 17

    @COPY
    def copy(source, destination):
        observed.append(("copy", source, destination))
        holding()

    @DESTROY
    def effect_destroy(effect):
        observed.append(("effect", effect))

    @DESTROY
    def actor_destroy(actor):
        observed.append(("actor", actor))
    assert api.CBMS_ConfigureDecodeCarrier(previous, native_decode) == 1
    assert api.CBMS_ConfigureMarshalCarrier(marshal) == 1
    assert api.CBMS_ConfigureLifecycleCarriers(copy, effect_destroy, actor_destroy) == 1
    records = allocated(b"EFF V2.0" + bytes(256))
    # An actor V1 load: the engine thread would begin an actor import.
    on_thread(lambda: api.CBMS_UnmarshalCarrier(0xA000, C.addressof(records), len(records), 0x1000, 1))
    assert observed == [("previous", 0xA000, C.addressof(records), len(records), 0x1000, 1),
                        ("decode", C.addressof(records)), ("decoded", 0x7777)]
    assert latched(api, runtime) and api.CBMS_ActorIsObserved(runtime, 0x1000) == 0
    assert api.CBMS_Quiescent(runtime) == 1
    output = C.c_void_p()
    assert on_thread(lambda: api.CBMS_MarshalCarrier(0x2000, C.byref(output), 1, 0, 7)) == 17
    assert output.value == 0xABCDEF and observed[-2:] == [("marshal", 0x2000, 1, 0, 7), ("claim", -1, None)]
    assert api.CBMS_ActorObserved(runtime, 0x4000, 0) == 1 and api.CBMS_Construct(runtime, 1, 0x5000) == 1
    on_thread(lambda: api.CBMS_EffectCopyCarrier(0x5000, 0x6000))
    on_thread(lambda: api.CBMS_EffectDestroyCarrier(0x5000))
    on_thread(lambda: api.CBMS_ActorDestroyCarrier(0x4000))
    assert observed[-3:] == [("copy", 0x5000, 0x6000), ("effect", 0x5000), ("actor", 0x4000)]
    # The engine thread would have registered the copy and ended both lifetimes.
    assert api.CBMS_ActorIsObserved(runtime, 0x4000) == 1
    assert api.CBMS_Construct(runtime, 1, 0x6000) == 1 and api.CBMS_Destruct(runtime, 1, 0x5000) == 1
    # Bridge entries reachable from Lua refuse there and change nothing.
    assert on_thread(lambda: (api.CBMS_EEexBridgeHealthy(), api.CBMS_EEexExportText(0x4000),
                              api.CBMS_EEexStageText(0x4000, b"x", 1), api.CBMS_EEexImportFinished(0x4000),
                              api.CBMS_EEexImportDropped(0x4000),
                              api.CBMS_EEexCancelledActorIO(0x4000), api.CBMS_EEexDetachQuiescent(),
                              api.CBMS_EEexConfigureCurrent())) == (0, None, 0, 0, None, 0, 0, 0)

    def events():
        api.CBMS_EEexAfterActorUUID(0x4000, 99)
        api.CBMS_EEexRejectEnvelope(b"foreign")
        api.CBMS_EEexBeforeEffectMarshal(0x4000, 0x2000, C.byref(output), 0)
        api.CBMS_EEexAfterEffectMarshal(0x4000, 0)
        api.CBMS_EEexBeginEffectUnmarshal(0x4000, 1)
        api.CBMS_EEexEffectDecoded(0x4000, 0x6000, C.addressof(records))
        api.CBMS_EEexLiveEffectCopied(0x6000, 0x7000)
        api.CBMS_EEexEffectDestroyed(0x6000)
        api.CBMS_EEexActorDestroyed(0x4000)
    on_thread(events)
    assert api.CBMS_EEexBridgeError() == b"" and api.CBMS_ActorIsObserved(runtime, 0x4000) == 1
    assert on_thread(lambda: api.CBMS_Construct(runtime, 1, 0x8000)) == -1
    assert on_thread(lambda: api.CBMS_LastError(runtime)) == b"native scroll callback on another thread"
    # Removal waits for a foreign call in flight, in each persistence group.
    for start, idle, detach in (
            (lambda: api.CBMS_UnmarshalCarrier(0xA000, C.addressof(records), len(records), None, 0),
             api.CBMS_DecodeCarrierIdle, api.CBMS_DetachDecodeCarrier),
            (lambda: api.CBMS_MarshalCarrier(0x2000, C.byref(output), 0, 0, 0),
             api.CBMS_MarshalCarrierIdle, api.CBMS_DetachMarshalCarrier),
            (lambda: api.CBMS_EffectCopyCarrier(0x6000, 0x7000),
             api.CBMS_LifecycleCarriersIdle, api.CBMS_DetachLifecycleCarriers)):
        hold[0] = Held()

        def waiting():
            assert idle() == 0 and detach() == 0
        hold[0].run(start, waiting)
        hold[0] = None
        assert idle() == 1
    # Owner-thread state was never touched: everything still detaches cleanly.
    assert api.CBMS_EEexBridgeHealthy() == 0 and api.CBMS_EEexBridgeError() == b"" and not errors
    assert api.CBMS_DetachDecodeCarrier() == 1 and api.CBMS_DetachMarshalCarrier() == 1
    assert api.CBMS_DetachLifecycleCarriers() == 1
    assert api.CBMS_Destruct(runtime, 1, 0x6000) == 1 and api.CBMS_Destruct(runtime, 0, 0x4000) == 1
    assert api.CBMS_EEexDetachQuiescent() == 1 and api.CBMS_Destroy(runtime) == 1
