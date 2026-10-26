"""Compiled concrete EEex event adapter with an explicit offline-only attach.

No game PE is loaded, no engine function is called, and no file is marshalled.
"""
import ctypes as C
import importlib
import subprocess

import pytest

from test_scroll_runtime_native import SOURCE, compiler_environment, configure_native_api
from test_scroll_runtime_actor_archive import (native_list, allocated, runtime_fixture, linked_list, native_effect,
                                               read_scroll, selected, decode_envelope, encode_envelope, ROW)


@pytest.fixture(scope="module")
def bridge(tmp_path_factory):
    directory = tmp_path_factory.mktemp("scroll-save-bridge")
    compiler, env, msvc = compiler_environment()
    assert msvc
    dll = directory / "scroll_save_bridge.dll"
    command = [compiler, "/nologo", "/std:c++20", "/EHsc", "/W4", "/WX", "/permissive-",
               "/DCBMS_OFFLINE_HARNESS", "/LD", str(SOURCE / "native_api.cpp"),
               str(SOURCE / "eeex_save_bridge.cpp"), str(SOURCE / "decode_carrier_api.cpp"), str(SOURCE / "marshal_carrier_api.cpp"), str(SOURCE / "lifecycle_carrier_api.cpp"), f"/Fe{dll}"]
    result = subprocess.run(command, cwd=directory, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    api = C.CDLL(str(dll))
    signatures = {
        "AttachForTest": ([C.c_void_p], C.c_int),
        "ConfigureCurrent": ([], C.c_int), "BridgeHealthy": ([], C.c_int),
        "BridgeError": ([], C.c_char_p),
        "BeforeEffectMarshal": ([C.c_void_p, C.c_void_p, C.POINTER(C.c_void_p), C.c_uint32], None),
        "AfterEffectMarshal": ([C.c_void_p, C.c_uint32], None),
        "BeginEffectUnmarshal": ([C.c_void_p, C.c_uint32], None),
        "EffectDecoded": ([C.c_void_p, C.c_void_p, C.c_void_p], None),
        "AfterActorUUID": ([C.c_void_p, C.c_uint64], None),
        "ExportText": ([C.c_void_p], C.c_char_p),
        "StageText": ([C.c_void_p, C.c_char_p, C.c_uint32], C.c_int),
        "ImportFinished": ([C.c_void_p], C.c_int), "ImportDropped": ([C.c_void_p], C.c_char_p),
        "RejectEnvelope": ([C.c_char_p], None),
        "EffectDestroyed": ([C.c_void_p], None), "ActorDestroyed": ([C.c_void_p], None),
        "CancelledActorIO": ([C.c_void_p], C.c_int), "DetachQuiescent": ([], C.c_int),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(api, "CBMS_EEex" + name)
        function.argtypes, function.restype = arguments, result
    return configure_native_api(api)


def test_concrete_native_save_decode_uuid_event_chain(bridge):
    api, runtime, resolve, report, calls, errors = runtime_fixture(bridge)
    assert api.CBMS_EEexAttachForTest(runtime) == 1
    reader, target, later_reader = 0x1000, 0x3000, 0x5000
    uuid = 0xFEDCBA9876543210
    assert api.CBMS_ActorObserved(runtime, reader, uuid) == 1
    linked, nodes, effects = native_list([9, 2, 0])
    use = C.c_uint64()
    assert api.CBMS_ItemBegin(runtime, reader, b"SCROLL", 2, 0, C.byref(use)) == 1
    for i, effect in enumerate(effects):
        assert api.CBMS_Construct(runtime, 1, C.addressof(effect)) == 1
        assert api.CBMS_ItemChild(runtime, use, C.addressof(effect), i) == 1
    assert api.CBMS_ItemEnd(runtime, use) == 1
    output = C.c_void_p()
    api.CBMS_EEexBeforeEffectMarshal(reader, C.addressof(linked), C.byref(output), 2)
    text = api.CBMS_EEexExportText(reader)
    assert text.startswith(b"CBMSFX01:")
    saved = allocated(bytes(effects[0])[8:] + bytes(effects[2])[8:] + b"X-BIV1.0" + bytes(256))
    output.value = C.addressof(saved)
    api.CBMS_EEexAfterEffectMarshal(reader, len(saved))
    assert api.CBMS_EEexBridgeHealthy() == 1
    for effect in effects:
        assert api.CBMS_Destruct(runtime, 1, C.addressof(effect)) == 1
    assert api.CBMS_Destruct(runtime, 0, reader) == 1
    api.CBMS_EEexBeginEffectUnmarshal(target, 1)
    decoded = [allocated(bytes(0x110)), allocated(bytes(0x110))]
    api.CBMS_EEexEffectDecoded(target, C.addressof(decoded[0]), C.addressof(saved))
    assert api.CBMS_EEexStageText(target, text, len(text)) == 1  # EEex metadata in middle is legal
    api.CBMS_EEexEffectDecoded(target, C.addressof(decoded[1]), C.addressof(saved) + 264)
    assert api.CBMS_EEexImportFinished(target) == 0
    api.CBMS_EEexAfterActorUUID(target, 777)
    assert api.CBMS_EEexImportFinished(target) == 1
    # UUID stage completes while original reader still has no loaded address.
    # Attaching that reader later must not substitute the effect recipient.
    api.CBMS_EEexAfterActorUUID(later_reader, uuid)
    frame, level = C.c_uint64(), C.c_uint32(90)
    for effect in decoded:
        assert api.CBMS_BeginCast(runtime, 1, C.addressof(effect), 0, 0xD000, b"SPELL", 0, 3, 4, 1, 2, C.byref(frame)) == 1
        assert api.CBMS_Select(runtime, frame, 0, 0xD000, C.byref(level)) == 1 and level.value == 12
        assert api.CBMS_EndCast(runtime, frame) == 1
        assert api.CBMS_Destruct(runtime, 1, C.addressof(effect)) == 1
    assert all(call[0] == later_reader for call in calls)
    assert errors == [] and api.CBMS_EEexDetachQuiescent() == 1
    assert api.CBMS_Destroy(runtime) == 1


def test_rejected_import_cannot_finish_or_detach_until_host_cancelled(bridge):
    api, runtime, resolve, report, calls, errors = runtime_fixture(bridge)
    assert api.CBMS_EEexAttachForTest(runtime) == 1
    api.CBMS_EEexBeginEffectUnmarshal(0x1000, 1)
    unknown = b"CBMSFX99:future"
    assert api.CBMS_EEexStageText(0x1000, unknown, len(unknown)) == 0
    api.CBMS_EEexAfterActorUUID(0x1000, 17)
    assert api.CBMS_EEexImportFinished(0x1000) == 0
    assert api.CBMS_EEexBridgeHealthy() == 0
    assert api.CBMS_EEexDetachQuiescent() == 0
    assert api.CBMS_EEexCancelledActorIO(0x1000) == 1
    assert api.CBMS_EEexBridgeHealthy() == 0  # cancellation does not silently clear the fault
    assert api.CBMS_EEexDetachQuiescent() == 1
    assert api.CBMS_Destroy(runtime) == 1


def test_no_argument_configuration_cannot_bypass_verified_startup(bridge):
    api, runtime, resolve, report, calls, errors = runtime_fixture(bridge)
    assert api.CBMS_EEexAttachForTest(runtime) == 1
    assert api.CBMS_EEexDetachQuiescent() == 1
    assert api.CBMS_Destroy(runtime) == 1
    assert api.CBMS_EEexConfigureCurrent() == 0
    assert b"early startup transaction" in api.CBMS_EEexBridgeError()
    assert api.CBMS_EEexBridgeHealthy() == 0


def test_independent_compiled_carrier_chains_exact_args_and_nested_scopes(bridge):
    api, runtime, resolve, report, calls, errors = runtime_fixture(bridge)
    assert api.CBMS_EEexAttachForTest(runtime) == 1
    unmarshal_t = C.CFUNCTYPE(None,C.c_void_p,C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint8)
    decode_t = C.CFUNCTYPE(C.c_void_p,C.c_void_p)
    api.CBMS_ConfigureDecodeCarrier.argtypes = [unmarshal_t,decode_t]
    api.CBMS_ConfigureDecodeCarrier.restype = C.c_int
    api.CBMS_DetachDecodeCarrier.argtypes = []
    api.CBMS_DetachDecodeCarrier.restype = C.c_int
    api.CBMS_UnmarshalCarrier.argtypes = [C.c_void_p,C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint8]
    api.CBMS_UnmarshalCarrier.restype = None
    api.CBMS_DecodeCarrier.argtypes = [C.c_void_p]
    api.CBMS_DecodeCarrier.restype = C.c_void_p
    records = allocated(b"EFF V2.0"+bytes(256)+b"X-BIV1.0"+bytes(256)+b"EFF V2.0"+bytes(256))
    inner = allocated(b"EFF V2.0"+bytes(256))
    outside = allocated(bytes(264))
    produced, observed, nested = [], [], [False]
    @decode_t
    def native_decode(raw):
        assert api.CBMS_DetachDecodeCarrier() == 0  # includes independent calls
        effect = allocated(bytes(0x110)); produced.append(effect)
        observed.append(("decode",raw))
        return C.addressof(effect)
    @unmarshal_t
    def previous(list_pointer,data,size,actor,version):
        observed.append(("previous",list_pointer,data,size,actor,version))
        assert api.CBMS_DetachDecodeCarrier() == 0
        if not nested[0]:
            nested[0] = True
            api.CBMS_UnmarshalCarrier(0xB000,C.addressof(inner),len(inner),0x2000,1)
            api.CBMS_EEexAfterActorUUID(0x2000,22)
            # A nested V0 call masks the enclosing V1 record scope.
            api.CBMS_UnmarshalCarrier(0xC000,C.addressof(records),264,None,0)
        for offset in range(0,size,264):
            if C.string_at(data+offset,8) != b"X-BIV1.0":
                assert api.CBMS_DecodeCarrier(data+offset)
        assert api.CBMS_DecodeCarrier(C.addressof(outside)) # unrelated decode in same stack
    assert api.CBMS_ConfigureDecodeCarrier(previous,native_decode) == 1
    assert api.CBMS_DecodeCarrier(C.addressof(outside))
    api.CBMS_UnmarshalCarrier(0xA000,C.addressof(records),len(records),0x1000,1)
    api.CBMS_EEexAfterActorUUID(0x1000,11)
    assert api.CBMS_EEexImportFinished(0x1000) == 1 and api.CBMS_EEexImportFinished(0x2000) == 1
    assert api.CBMS_EEexBridgeHealthy() == 1 and errors == []
    assert ("previous",0xA000,C.addressof(records),len(records),0x1000,1) in observed
    assert ("previous",0xC000,C.addressof(records),264,None,0) in observed
    assert api.CBMS_DetachDecodeCarrier() == 1
    assert api.CBMS_EEexDetachQuiescent() == 1
    assert api.CBMS_Destroy(runtime) == 1


def configure_marshal(api):
    original=C.CFUNCTYPE(C.c_uint32,C.c_void_p,C.POINTER(C.c_void_p),C.c_uint8,C.c_int,C.c_int)
    api.CBMS_ConfigureMarshalCarrier.argtypes=[original];api.CBMS_ConfigureMarshalCarrier.restype=C.c_int
    api.CBMS_DetachMarshalCarrier.argtypes=[];api.CBMS_DetachMarshalCarrier.restype=C.c_int
    api.CBMS_MarshalCarrier.argtypes=[C.c_void_p,C.POINTER(C.c_void_p),C.c_uint8,C.c_int,C.c_int];api.CBMS_MarshalCarrier.restype=C.c_uint32
    return original


def test_native_marshal_scope_claims_actual_eeex_actor_and_preserves_nested_calls(bridge):
    api,runtime,resolve,report,calls,errors=runtime_fixture(bridge)
    assert api.CBMS_EEexAttachForTest(runtime)==1
    original_type=configure_marshal(api)
    actors=[allocated(bytes(0x4A80)),allocated(bytes(0x4A80))]
    keep,lists,output_bytes,texts,observed=[],[],[],[],[]
    for actor in actors:
        linked,nodes,effects=native_list([9,2,0]);keep.append((linked,nodes,effects))
        pointer=C.addressof(actor)+0x4A00;C.memmove(pointer,C.addressof(linked),len(linked));lists.append(pointer)
        output_bytes.append(allocated(bytes(effects[0])[8:]+bytes(effects[2])[8:]))
    reader=C.addressof(actors[0]);assert api.CBMS_ActorObserved(runtime,reader,91)==1
    use=C.c_uint64();assert api.CBMS_ItemBegin(runtime,reader,b"SCROLL",0,0,C.byref(use))==1
    for effects in [entry[2] for entry in keep]:
        for i,effect in enumerate(effects):
            assert api.CBMS_Construct(runtime,1,C.addressof(effect))==1
            assert api.CBMS_ItemChild(runtime,use,C.addressof(effect),i)==1
    assert api.CBMS_ItemEnd(runtime,use)==1
    @original_type
    def previous(list_pointer,output,version,permanent,skip):
        observed.append((list_pointer,version,permanent,skip))
        assert api.CBMS_DetachMarshalCarrier()==0
        index=lists.index(list_pointer)
        if index==0:
            nested=C.c_void_p();assert api.CBMS_MarshalCarrier(lists[1],C.byref(nested),1,0,-3)==len(output_bytes[1])
        # EEex calls this exporter inside original Marshal, with actual actor.
        text=api.CBMS_EEexExportText(C.addressof(actors[index]));assert text.startswith(b"CBMSFX01:");texts.append(text)
        assert api.CBMS_EEexExportText(C.addressof(actors[index]))==text # repeated read doesn't prepare twice
        output[0]=C.addressof(output_bytes[index]);return len(output_bytes[index])
    assert api.CBMS_ConfigureMarshalCarrier(previous)==1
    output=C.c_void_p();assert api.CBMS_MarshalCarrier(lists[0],C.byref(output),1,0,7)==len(output_bytes[0])
    assert output.value==C.addressof(output_bytes[0])
    assert observed==[(lists[0],1,0,7),(lists[1],1,0,-3)] and len(texts)==2
    assert api.CBMS_EEexBridgeHealthy()==1 and errors==[]
    assert api.CBMS_DetachMarshalCarrier()==1
    for _,_,effects in keep:
        for effect in effects: assert api.CBMS_Destruct(runtime,1,C.addressof(effect))==1
    assert api.CBMS_EEexDetachQuiescent()==1 and api.CBMS_Destroy(runtime)==1


def test_native_nonactor_marshal_is_unchanged_and_bad_actor_pair_refuses(bridge):
    api,runtime,resolve,report,calls,errors=runtime_fixture(bridge)
    assert api.CBMS_EEexAttachForTest(runtime)==1
    original_type=configure_marshal(api)
    claim=[False];arguments=[]
    @original_type
    def previous(list_pointer,output,version,permanent,skip):
        arguments.append((list_pointer,version,permanent,skip))
        if claim[0]: assert api.CBMS_EEexExportText(0x1000) is None
        output[0]=0xABCDEF;return 17
    assert api.CBMS_ConfigureMarshalCarrier(previous)==1
    output=C.c_void_p();assert api.CBMS_MarshalCarrier(0x2000,C.byref(output),0,9,4)==17
    assert output.value==0xABCDEF and api.CBMS_EEexBridgeHealthy()==1
    claim[0]=True
    assert api.CBMS_MarshalCarrier(0x2000,C.byref(output),1,9,4)==17
    assert api.CBMS_EEexBridgeHealthy()==0
    assert b"does not match" in api.CBMS_EEexBridgeError()
    assert arguments==[(0x2000,0,9,4),(0x2000,1,9,4)]
    assert api.CBMS_DetachMarshalCarrier()==1
    assert api.CBMS_EEexDetachQuiescent()==1 and api.CBMS_Destroy(runtime)==1


def test_compiled_eeex_lifecycle_preserves_owner_copy_and_cleans_after_fault(bridge):
    api,runtime,resolve,report,calls,errors=runtime_fixture(bridge)
    assert api.CBMS_EEexAttachForTest(runtime)==1
    copy_type,destroy_type=C.CFUNCTYPE(None,C.c_void_p,C.c_void_p),C.CFUNCTYPE(None,C.c_void_p)
    api.CBMS_ConfigureLifecycleCarriers.argtypes=[copy_type,destroy_type,destroy_type];api.CBMS_ConfigureLifecycleCarriers.restype=C.c_int
    api.CBMS_DetachLifecycleCarriers.argtypes=[];api.CBMS_DetachLifecycleCarriers.restype=C.c_int
    api.CBMS_EffectCopyCarrier.argtypes=[C.c_void_p,C.c_void_p];api.CBMS_EffectCopyCarrier.restype=None
    for name in ('EffectDestroyCarrier','ActorDestroyCarrier'):
        getattr(api,'CBMS_'+name).argtypes=[C.c_void_p];getattr(api,'CBMS_'+name).restype=None
    api.CBMS_EEexRejectEnvelope.argtypes=[C.c_char_p];api.CBMS_EEexRejectEnvelope.restype=None
    original_calls=[]
    @copy_type
    def previous_copy(source,destination):
        original_calls.append(('copy',source,destination));assert api.CBMS_DetachLifecycleCarriers()==0
    @destroy_type
    def previous_effect(effect):
        original_calls.append(('effect',effect));assert api.CBMS_DetachLifecycleCarriers()==0
    @destroy_type
    def previous_actor(actor):
        original_calls.append(('actor',actor));assert api.CBMS_DetachLifecycleCarriers()==0
    assert api.CBMS_ConfigureLifecycleCarriers(previous_copy,previous_effect,previous_actor)==1
    assert api.CBMS_ActorObserved(runtime,0x1000,55)==1
    assert api.CBMS_Construct(runtime,1,0x2000)==1
    use=C.c_uint64();assert api.CBMS_ItemBegin(runtime,0x1000,b'SCROLL',0,0,C.byref(use))==1
    assert api.CBMS_ItemChild(runtime,use,0x2000,3)==1 and api.CBMS_ItemEnd(runtime,use)==1
    def level(effect):
        frame,result=C.c_uint64(),C.c_uint32(90)
        assert api.CBMS_BeginCast(runtime,1,effect,0,0xD000,b'SPELL',0,1,2,3,4,C.byref(frame))==1
        status=api.CBMS_Select(runtime,frame,0,0xD000,C.byref(result))
        assert api.CBMS_EndCast(runtime,frame)==1
        return status,result.value
    api.CBMS_EffectCopyCarrier(0x2000,0x3000);assert level(0x3000)==(1,12)
    api.CBMS_EffectCopyCarrier(0x4000,0x3000);assert level(0x3000)==(0,90) # absent source clears destination
    api.CBMS_EffectCopyCarrier(0x2000,0x3000)
    api.CBMS_EEexRejectEnvelope(b'unknown newer metadata retained')
    assert api.CBMS_EEexBridgeHealthy()==0
    api.CBMS_EffectDestroyCarrier(0x3000)
    assert api.CBMS_Construct(runtime,1,0x3000)==1 # dead lifetime did not survive address reuse
    assert level(0x3000)==(0,90)
    for effect in (0x2000,0x3000,0x4000):api.CBMS_EffectDestroyCarrier(effect)
    api.CBMS_ActorDestroyCarrier(0x1000)
    assert api.CBMS_Construct(runtime,0,0x1000)==1
    assert original_calls==[('copy',0x2000,0x3000),('copy',0x4000,0x3000),('copy',0x2000,0x3000),
        ('effect',0x3000),('effect',0x2000),('effect',0x3000),('effect',0x4000),('actor',0x1000)]
    assert errors==[] and api.CBMS_DetachLifecycleCarriers()==1
    assert api.CBMS_EEexDetachQuiescent()==1 and api.CBMS_Destroy(runtime)==1


# EEex's marshal plumbing for one process, around the shipped actor adapter.
HOST = '''
    handlers, listeners = {}, {}
    function EEex_GetUDAux(sprite) return sprite.aux end
    function EEex_Sprite_AddMarshalHandlers(name, export, import)
        handlers[name] = {exporter = export, importer = import}
    end
    function EEex_Sprite_AddLoadedListener(f) listeners[#listeners + 1] = f end
    function EEex_Sprite_LuaHook_OnAfterEffectListUnmarshalled(sprite)
        for _, f in ipairs(listeners) do f(sprite) end
    end
    name_strings = {}
    function Infinity_FetchString(strref) return name_strings[strref] or "" end
    -- As loaded listeners see a sprite: display name not set yet, creature name string set.
    function make_sprite(address, low, high, name, script)
        name_strings[address] = name
        return {address = address, aux = {},
            m_sName = {m_pchData = {get = function() return "" end}},
            m_baseStats = {m_name = address},
            m_scriptName = {get = function() return script end},
            m_pLocalVariables = {find = function(_, key)
                assert(key == "EEEX_UUID")
                return {m_intValue = low, m_dWValue = high}
            end}}
    end
'''
DROPPED = ("[CBM scroll] Dropped outdated scroll data for {} only: {}. Its effects keep their levels; "
           "spells they cast later use the normal level.")


class Actor:
    def __init__(self, address, uuid, name, script):
        self.address, self.uuid, self.name, self.script = address, uuid, name, script


class Game:
    """One game process: a fresh runtime attached to the compiled bridge and the
    shipped actor adapter in real Lua. Stand-ins replace EEex's marshal calls and
    the tolua bindings (eeex_lua_bindings.cpp needs the loader SDK); they call
    the same bridge entries those bindings call."""

    def __init__(self, bridge):
        # The resolver and reporter callbacks must outlive the runtime.
        self.api, self.runtime, *self.callbacks, self.calls, self.errors = runtime_fixture(bridge)
        assert self.api.CBMS_EEexAttachForTest(self.runtime) == 1
        api, self.printed, self.objects = self.api, [], []
        self.lua = importlib.import_module("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(HOST)

        def export(sprite):
            text = api.CBMS_EEexExportText(int(sprite.address))
            return text.decode() if text is not None else (None, api.CBMS_EEexBridgeError().decode())

        def stage(sprite, payload):
            data = payload.encode()
            return bool(api.CBMS_EEexStageText(int(sprite.address), data, len(data))), api.CBMS_EEexBridgeError().decode()

        def finished(sprite):
            dropped = api.CBMS_EEexImportDropped(int(sprite.address))
            return bool(api.CBMS_EEexImportFinished(int(sprite.address))), None if dropped is None else dropped.decode()

        def actor_uuid(sprite, low, high):
            api.CBMS_EEexAfterActorUUID(int(sprite.address), (int(high) << 32) | (int(low) & 0xFFFFFFFF))
            return bool(api.CBMS_EEexBridgeHealthy())

        names = self.lua.globals()
        names.CBMS_NativeExport, names.CBMS_NativeStage, names.CBMS_NativeImportFinished = export, stage, finished
        names.CBMS_NativeHealthy = lambda: bool(api.CBMS_EEexBridgeHealthy())
        names.CBMS_NativeActorUUID = actor_uuid
        names.CBMS_NativeRejectEnvelope = lambda reason: api.CBMS_EEexRejectEnvelope(reason.encode())
        names.print = self.printed.append
        self.lua.execute((SOURCE / "CBMS_ScrollMarshal.lua").read_text())
        self.handler = names.handlers.CBM_SCROLL_CONTEXT

    def load(self, actor, records, envelope, copies=1):
        """EEex's actor load: native decode of every record, the marshal importer
        for its X-BIV block, then the after-unmarshal hook (UUID, loaded listeners)."""
        api, names = self.api, self.lua.globals()
        sprite = names.make_sprite(actor.address, actor.uuid & 0xFFFFFFFF, actor.uuid >> 32, actor.name, actor.script)
        api.CBMS_EEexBeginEffectUnmarshal(actor.address, 1)
        saved = allocated(b"".join(records) + b"X-BIV1.0" + bytes(256))
        effects = [allocated(b"EFF V2.0" + wire) for wire in records]
        for i, effect in enumerate(effects):
            api.CBMS_EEexEffectDecoded(actor.address, C.addressof(effect), C.addressof(saved) + i * ROW)
        for _ in range(copies if envelope is not None else 0):
            self.handler.importer(sprite, self.lua.table_from(envelope))
        names.EEex_Sprite_LuaHook_OnAfterEffectListUnmarshalled(sprite)
        loaded = {"actor": actor, "sprite": sprite, "effects": effects}
        self.objects.append(loaded)
        return loaded

    def save(self, loaded):
        """EEex's actor save: native prepare, the marshal exporter, validate.
        Returns the records and the envelope EEex writes to the X-BIV block."""
        api, address = self.api, loaded["actor"].address
        linked, nodes = linked_list(loaded["effects"])
        output = C.c_void_p()
        api.CBMS_EEexBeforeEffectMarshal(address, C.addressof(linked), C.byref(output), 0)
        envelope = self.handler.exporter(loaded["sprite"])
        records = [bytes(effect)[8:] for effect in loaded["effects"]]
        written = allocated(b"".join(records) + b"X-BIV1.0" + bytes(256))
        output.value = C.addressof(written)
        api.CBMS_EEexAfterEffectMarshal(address, len(written))
        return records, None if envelope is None else dict(envelope.items())

    def read_scroll(self, loaded, count=1):
        effects = [native_effect(0, 500 + len(loaded["effects"]) + i) for i in range(count)]
        read_scroll(self.api, self.runtime, loaded["actor"].address, effects)
        loaded["effects"].extend(effects)
        return effects

    def levels(self, loaded):
        return [selected(self.api, self.runtime, effect) for effect in loaded["effects"]]

    def healthy(self):
        return self.api.CBMS_EEexBridgeHealthy() == 1 and self.api.CBMS_EEexBridgeError() == b"" and self.errors == []

    def close(self):
        """Ends every object's lifetime, as the engine does, then detaches."""
        for loaded in self.objects:
            for effect in loaded["effects"]:
                self.api.CBMS_EEexEffectDestroyed(C.addressof(effect))
            self.api.CBMS_EEexActorDestroyed(loaded["actor"].address)
        assert self.api.CBMS_EEexDetachQuiescent() == 1 and self.api.CBMS_Destroy(self.runtime) == 1


def outdated_save(bridge, imoen, xan):
    """A healthy save, reloaded by a process whose overrides went off: both
    envelopes are kept unparsed, only Imoen's records change, and it saves."""
    game = Game(bridge)
    first, second = game.load(imoen, [], None), game.load(xan, [], None)
    game.read_scroll(first, 2)
    game.read_scroll(second)
    healthy = {imoen: game.save(first), xan: game.save(second)}
    assert all(envelope for _, envelope in healthy.values()) and game.healthy()
    game.close()
    game = Game(bridge)
    game.api.CBMS_DisableOverrides(game.runtime)  # a carrier fault, for example
    first, second = game.load(imoen, *healthy[imoen]), game.load(xan, *healthy[xan])
    first["effects"].append(native_effect(0, 600))  # a potion, say
    stale = {imoen: game.save(first), xan: game.save(second)}
    game.close()
    assert stale[imoen][1] == healthy[imoen][1] and stale[xan] == healthy[xan]
    assert len(stale[imoen][0]) == len(healthy[imoen][0]) + 1
    return stale


def test_outdated_envelope_drops_for_one_actor_through_the_shipped_adapter(bridge):
    imoen, xan = Actor(0x1000, 0x100000011, "Imoen", "IMOEN2"), Actor(0x2000, 0x100000022, "Xan", "XAN")
    stale = outdated_save(bridge, imoen, xan)
    # A fresh healthy process: Imoen's envelope is dropped and logged, Xan keeps
    # his saved scroll levels, and nothing is turned off.
    game = Game(bridge)
    first, second = game.load(imoen, *stale[imoen]), game.load(xan, *stale[xan])
    assert game.healthy() and game.api.CBMS_OverridesDisabled(game.runtime) == 0
    assert game.printed == [DROPPED.format("Imoen (IMOEN2, UUID 100000011)", "saved effect record count mismatch (saved 2, loaded 3)")]
    assert game.levels(first) == [(0, 90)] * 3 and game.levels(second) == [(1, 12)]
    assert {call[0] for call in game.calls} == {xan.address}
    # Its next save writes nothing stale: no envelope at all for Imoen...
    assert game.save(first)[1] is None
    # ...then a new scroll uses her level and is saved on its own.
    fresh = game.read_scroll(first)
    assert selected(game.api, game.runtime, fresh[0]) == (1, 12) and game.calls[-1][0] == imoen.address
    resaved = {imoen: game.save(first), xan: game.save(second)}
    rows = decode_envelope(resaved[imoen][1]["payload"].encode())
    assert [wire for wire, _ in rows] == resaved[imoen][0]
    assert [context is not None for _, context in rows] == [False] * 3 + [True]
    xan_rows = decode_envelope(resaved[xan][1]["payload"].encode())
    assert [wire for wire, _ in xan_rows] == stale[xan][0] and all(context for _, context in xan_rows)
    assert game.healthy() and len(game.printed) == 1
    game.close()
    # Fresh processes: the save written after the drop drops nothing, and the
    # outdated save still drops the same way each time it is loaded.
    for _ in range(2):
        game = Game(bridge)
        first, second = game.load(imoen, *resaved[imoen]), game.load(xan, *resaved[xan])
        assert game.printed == [] and game.healthy()
        assert game.levels(first) == [(0, 90)] * 3 + [(1, 12)] and game.levels(second) == [(1, 12)]
        game.close()
        game = Game(bridge)
        first, second = game.load(imoen, *stale[imoen]), game.load(xan, *stale[xan])
        assert game.printed == [DROPPED.format("Imoen (IMOEN2, UUID 100000011)", "saved effect record count mismatch (saved 2, loaded 3)")]
        assert game.healthy() and game.levels(second) == [(1, 12)]
        game.close()


BRIDGE_DAMAGE = {
    "hex": "invalid effect envelope hex",
    "version": "unknown/malformed effect envelope; retain original actor data",
    "origins": "conflicting saved scroll origin definitions",
    "scalar": "saved effect scalar mismatch",
    "ancestry": "invalid saved effect ancestry",
    "duplicate": "duplicate scroll actor envelope; cancel this load",
    "schema": "unknown scroll actor envelope schema; retained unchanged",
    "fields": "unknown scroll actor envelope fields; retained unchanged",
}


@pytest.mark.parametrize("damage", sorted(BRIDGE_DAMAGE))
def test_damaged_envelope_still_turns_430_off_through_the_shipped_adapter(bridge, damage):
    imoen = Actor(0x1000, 0x100000011, "Imoen", "IMOEN2")
    game = Game(bridge)
    first = game.load(imoen, [], None)
    game.read_scroll(first, 2)
    records, envelope = game.save(first)
    game.close()
    payload = envelope["payload"].encode()
    rows = decode_envelope(payload)
    if damage == "scalar":
        rows[0][1][6:8] = [1, 13]
    if damage == "ancestry":
        rows[0][1][1] = 0
    if damage == "origins":
        rows[1][1][3] += 1
    payload = {"hex": payload[:-2] + b"ZZ", "version": b"CBMSFX02:" + payload[9:]}.get(damage, encode_envelope(rows))
    damaged = dict(envelope, payload=payload.decode())
    if damage == "schema":
        damaged["schema"] = 2
    if damage == "fields":
        damaged["future"] = 1
    # The records changed too: damage is never taken for an outdated envelope.
    game = Game(bridge)
    first = game.load(imoen, records + [bytes(native_effect(0, 600))[8:]], damaged,
                      copies=2 if damage == "duplicate" else 1)
    assert game.api.CBMS_EEexBridgeHealthy() == 0
    assert game.api.CBMS_EEexBridgeError() == BRIDGE_DAMAGE[damage].encode()
    assert game.printed == [] and game.api.CBMS_EEexImportDropped(imoen.address) is None
    # Kept unchanged for a later version that can read it, never dropped.
    assert game.save(first)[1] == damaged
    game.close()
