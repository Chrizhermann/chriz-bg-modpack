"""Compiled concrete EEex event adapter with an explicit offline-only attach.

No game PE is loaded, no engine function is called, and no file is marshalled.
"""
import ctypes as C
import subprocess

import pytest

from test_scroll_runtime_native import SOURCE, compiler_environment, configure_native_api
from test_scroll_runtime_actor_archive import native_list, allocated, runtime_fixture


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
        "ImportFinished": ([C.c_void_p], C.c_int),
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
