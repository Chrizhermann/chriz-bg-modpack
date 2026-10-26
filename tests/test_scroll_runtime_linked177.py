"""Concrete opcode177 parent/decoder hook, preserving original native bytes."""
import ctypes as C
import json,struct,subprocess
import pytest
from test_scroll_runtime_native import SOURCE,compiler_environment,configure_native_api
from test_scroll_runtime_actor_archive import allocated,runtime_fixture
from test_scroll_runtime_binding import mapped,windows
from test_scroll_runtime_decode_host import lookup
APPLY=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p);DECODE=C.CFUNCTYPE(C.c_void_p,C.c_void_p)
class Functions(C.Structure):_fields_=[('apply',APPLY),('decode',DECODE),('call',C.c_size_t)]
CARRIER_SIGNATURES=[('ConfigureLinked177',[C.c_void_p,C.POINTER(Functions)],C.c_int),('Linked177Idle',[],C.c_int),('DetachLinked177',[],C.c_int),('Linked177Error',[],C.c_char_p),('Linked177Apply',[C.c_void_p,C.c_void_p],C.c_int),('TestLinked177Decode',[C.c_size_t,C.c_void_p],C.c_void_p),('CarrierIsOwned',[C.c_void_p,C.c_uint32,C.c_size_t],C.c_int),('DestructObserved',[C.c_void_p,C.c_uint32,C.c_size_t],C.c_int)]
HOST_SIGNATURES=[('BindLinked177',[C.c_size_t,C.POINTER(Functions),C.c_void_p,C.c_uint32],C.c_int),('TestInstallLinked177Hooks',[C.POINTER(Functions),C.c_void_p],C.c_int),('RemoveLinked177Hooks',[],C.c_int),('Linked177HookError',[],C.c_char_p),('TestLinked177Allocation',[],C.c_size_t),('TestLinked177Failure',[C.c_int],None)]
def configure_linked(library,host=True):
    """Native-API and opcode177 carrier (and host) signatures of a harness build."""
    native=configure_native_api(library)
    for name,args,out in CARRIER_SIGNATURES+(HOST_SIGNATURES if host else []):
        f=getattr(library,'CBMS_'+name);f.argtypes=args;f.restype=out
    return native
@pytest.fixture(scope='module')
def api(tmp_path_factory):
    directory=tmp_path_factory.mktemp('scroll-linked177');compiler,env,msvc=compiler_environment();assert msvc;library=directory/'linked.dll'
    run=subprocess.run([compiler,'/nologo','/std:c++20','/EHsc','/W4','/WX','/permissive-','/DCBMS_OFFLINE_HARNESS','/LD',*[str(SOURCE/n) for n in ('native_api.cpp','linked177_api.cpp','linked177_host.cpp')],f'/Fe{library}'],cwd=directory,env=env,text=True,capture_output=True)
    assert run.returncode==0,run.stdout+run.stderr
    return configure_linked(C.CDLL(str(library)))
class Harness:
    def __init__(self,native):
        self.api,self.runtime,self.resolve,self.report,self.calls,self.errors=runtime_fixture(native)
        self.effects=[];self.events=[];self.on_apply=lambda parent,target:None;self.on_decode=lambda raw:None;self.null=False
        @APPLY
        def apply(parent,target):self.events.append(('apply',parent,target));self.on_apply(parent,target);return -35
        @DECODE
        def decode(raw):
            self.events.append(('decode',raw));self.on_decode(raw)
            if self.null:return None
            child=allocated(bytes([0xA7])*0x160);self.effects.append(child);return C.addressof(child)
        self.kept=(apply,decode);self.functions=Functions(apply,decode,100)
        assert self.api.CBMS_ConfigureLinked177(self.runtime,C.byref(self.functions))==1
        assert self.api.CBMS_ActorObserved(self.runtime,0x1000,1001)==1
    def effect(self,owned=True,selected=False):
        raw=bytearray(0x160);struct.pack_into('<I',raw,0x10,177);parent=allocated(bytes(raw));self.effects.append(parent);at=C.addressof(parent)
        if owned:
            assert self.api.CBMS_Construct(self.runtime,1,at)==1
            use=C.c_uint64();assert self.api.CBMS_ItemBegin(self.runtime,0x1000,b'SCROLL',0,0,C.byref(use))==1
            assert self.api.CBMS_ItemChild(self.runtime,use,at,0)==1;assert self.api.CBMS_ItemEnd(self.runtime,use)==1
            if selected:
                frame=C.c_uint64();level=C.c_uint32();assert self.api.CBMS_BeginCast(self.runtime,1,at,0,0xD000,b'SPELL',0,0,0,0,0,C.byref(frame))==1
                assert self.api.CBMS_Select(self.runtime,frame,0,0xD000,C.byref(level))==1
                child=allocated(bytes(raw));self.effects.append(child);assert self.api.CBMS_Construct(self.runtime,1,C.addressof(child))==1
                assert self.api.CBMS_SpellChild(self.runtime,frame,0xD000,C.addressof(child),C.byref(level))==1;assert self.api.CBMS_EndCast(self.runtime,frame)==1;parent=child
        return parent
    def close(self):
        assert self.api.CBMS_DetachLinked177()==1
        for effect in self.effects:assert self.api.CBMS_DestructObserved(self.runtime,1,C.addressof(effect))==1
        assert self.api.CBMS_Destroy(self.runtime)==1
@pytest.mark.parametrize('case',['root','selected','unowned','wrong_pc','null','nested_unowned','nested_owned'])
def test_specific_decode_result_inherits_parent_without_changing_targets_modes_or_source(api,case):
    h=Harness(api);result=[];depth=0
    try:
        parent=h.effect(owned=case!='unowned',selected=case=='selected');before=bytes(parent);h.null=case=='null'
        nested=h.effect(owned=case=='nested_owned') if case.startswith('nested') else None
        def apply(effect,target):
            nonlocal depth
            if nested is not None and not depth:
                depth=1;h.api.CBMS_Linked177Apply(C.addressof(nested),0x345);depth=0
            result.append(h.api.CBMS_TestLinked177Decode(777 if case=='wrong_pc' else 105,0x1234))
        h.on_apply=apply;assert h.api.CBMS_Linked177Apply(C.addressof(parent),0x9876)==-35
        assert bytes(parent)==before and h.api.CBMS_Linked177Error()==b''
        if case=='null':assert result==[None]
        else:
            for i,at in enumerate(result):
                expected=case not in ('unowned','wrong_pc') and not(case=='nested_unowned' and i==0)
                assert h.api.CBMS_CarrierIsOwned(h.runtime,1,at)==int(expected)
                raw=C.string_at(at,0x160);assert raw[:0xC8]==bytes([0xA7])*0xC8 and raw[0xCC:]==bytes([0xA7])*(0x160-0xCC)
                assert struct.unpack_from('<I',raw,0xC8)[0]==(12 if case=='selected' else 0xA7A7A7A7)
    finally:h.close()
@pytest.mark.parametrize('damage',[None,'parent','decoder','call'])
def test_exact_native_opcode177_and_decoder_bind_read_only(api,mapped,damage):
    p=next(p for p in json.loads((SOURCE/'linked177-profiles.json').read_text()) if p['version']==mapped.profile['version'])
    if damage:
        at=p['call'] if damage=='call' else p[damage]['rva'];mapped.write(at,bytes([mapped.read(at,1)[0]^1]))
    out=Functions();C.memset(C.byref(out),0xCA,C.sizeof(out));old=bytes(out);reason=C.create_string_buffer(256)
    result=api[0].CBMS_BindLinked177(mapped.base,C.byref(out),reason,len(reason))
    if damage:assert result==0 and bytes(out)==old and reason.value
    else:assert result==1 and struct.unpack('<3Q',bytes(out))==tuple(mapped.base+x for x in (p['parent']['rva'],p['decoder']['rva'],p['call']))
@pytest.mark.parametrize('failure',[0,1,2,100])
def test_two_site_parent_and_decoder_call_transaction(api,windows,failure):
    h=Harness(api);assert h.api.CBMS_DetachLinked177()==1;base=windows.VirtualAlloc(None,0x1000,0x3000,4);assert base
    prefix=bytes.fromhex('48895c2418');apply,call,decoder=base+0x100,base+0x300,base+0x500;original=b'\xE8'+struct.pack('<i',decoder-call-5)
    C.memmove(apply,prefix,5);C.memmove(call,original,5);old=C.c_uint32();assert windows.VirtualProtect(base,0x1000,0x20,C.byref(old))
    f=Functions(APPLY(apply),DECODE(decoder),call)
    try:
        if failure:h.api.CBMS_TestLinked177Failure(failure)
        result=h.api.CBMS_TestInstallLinked177Hooks(C.byref(f),h.runtime)
        if failure:assert result==0 and not h.api.CBMS_TestLinked177Allocation() and b'injected' in h.api.CBMS_Linked177HookError()
        else:
            assert result==1,h.api.CBMS_Linked177HookError();relay=h.api.CBMS_TestLinked177Allocation();assert C.string_at(call,1)==b'\xE8'
            assert call+5+struct.unpack('<i',C.string_at(call+1,4))[0]==relay+0x100
            assert C.string_at(relay+0x120,14)==b'\xFF\x25'+bytes(4)+struct.pack('<Q',decoder)
            assert lookup(relay+0x120)[1]==relay;assert h.api.CBMS_RemoveLinked177Hooks()==1
            assert lookup(relay+0x120)[0] is None
        assert C.string_at(apply,5)==prefix and C.string_at(call,5)==original
    finally:
        if h.api.CBMS_TestLinked177Allocation():assert h.api.CBMS_RemoveLinked177Hooks()==1
        assert windows.VirtualFree(base,0,0x8000);assert h.api.CBMS_Destroy(h.runtime)==1
