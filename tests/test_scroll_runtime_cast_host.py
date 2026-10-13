"""Concrete eight-entry/seven-selector transaction on our inert private pages."""
import ctypes as C
import struct,sys,threading
import pytest
from test_scroll_runtime_native import SOURCE
from test_scroll_runtime_binding import windows
from test_scroll_runtime_decode_host import lookup
from test_scroll_runtime_cast_carriers import cast_api,dispatch_api,CastHarness,Functions,EFFECT,FIRE,TARGET,POINT,CHILD
sys.path.insert(0,str(SOURCE))
import cast_entry_detours as entries
import cast_selection_detours as selectors
@pytest.fixture(scope='module')
def host(cast_api):
    dll=cast_api[0]
    for name,args,result in [('TestInstallCastHooks',[C.POINTER(Functions),C.c_void_p],C.c_int),('RemoveCastHooks',[],C.c_int),('CastHookError',[],C.c_char_p),('TestCastHookAllocation',[C.c_uint32],C.c_size_t),('TestCastHookFailure',[C.c_uint32,C.c_int],None)]:
        fn=getattr(dll,'CBMS_'+name);fn.argtypes=args;fn.restype=result
    return dll
class Sites:
    def __init__(self,api,h):
        self.api=api;self.base=api.VirtualAlloc(None,0x3000,0x3000,4);assert self.base
        self.entries=[self.base+0x100+i*0x100 for i in range(8)];self.sites=[self.base+0x1100+i*0x100 for i in range(7)];self.getter=self.base+0x2100
        self.functions=Functions.from_buffer_copy(bytes(h.cast));self.functions.getter=self.getter
        self.prefixes=[bytes.fromhex(value[0]) for value in entries.SITES.values()]
        for address,prefix in zip(self.entries,self.prefixes):C.memmove(address,prefix,len(prefix))
        for (name,kind),address in zip([('effect',EFFECT),('fire',FIRE),('point',FIRE),('force',TARGET),('force_point',POINT),('spell',TARGET),('spell_point',POINT),('child',CHILD)],self.entries):setattr(self.functions,name,kind(address))
        self.calls=[b'\xe8'+struct.pack('<i',self.getter-at-5) for at in self.sites]
        for i,(at,call) in enumerate(zip(self.sites,self.calls)):C.memmove(at,call,5);self.functions.selection[i]=at
        old=C.c_uint32();assert api.VirtualProtect(self.base,0x3000,0x20,C.byref(old))
    def edit(self,at,value):
        old=C.c_uint32();assert self.api.VirtualProtect(at,len(value),0x40,C.byref(old));C.memmove(at,value,len(value));temp=C.c_uint32();assert self.api.VirtualProtect(at,len(value),old.value,C.byref(temp))
    def original(self):
        assert [C.string_at(at,len(p)) for at,p in zip(self.entries,self.prefixes)]==self.prefixes
        assert [C.string_at(at,5) for at in self.sites]==self.calls
    def close(self):assert self.api.VirtualFree(self.base,0,0x8000)
@pytest.mark.parametrize('group,point',[(0,0),*[(0,i) for i in range(1,9)],(0,100),*[(1,i) for i in range(1,8)],(1,100)])
def test_real_fifteen_site_register_transaction_and_failure_rollback(cast_api,host,windows,group,point):
    h=CastHarness(cast_api);assert host.CBMS_DetachCastCarriers()==1;s=Sites(windows,h)
    try:
        if point:host.CBMS_TestCastHookFailure(group,point)
        result=host.CBMS_TestInstallCastHooks(C.byref(s.functions),h.runtime)
        if point:assert result==0 and b'injected' in host.CBMS_CastHookError() and not host.CBMS_TestCastHookAllocation(0) and not host.CBMS_TestCastHookAllocation(1)
        else:
            assert result==1,host.CBMS_CastHookError();entrybase=host.CBMS_TestCastHookAllocation(0);base=host.CBMS_TestCastHookAllocation(1)
            for i,at in enumerate(s.sites):
                plan=selectors.emit(i,at,base+i*0x200,C.cast(host.CBMS_SelectCapturedNative,C.c_void_p).value,s.getter,s.calls[i])
                assert C.string_at(at,5)==plan['patch'] and C.string_at(base+i*0x200,len(plan['code']))==plan['code']
                for begin,end,_ in plan['segments']:assert lookup(base+i*0x200+begin)[1]==base and lookup(base+i*0x200+end-1)[1]==base
            assert all(lookup(entrybase+i*0x100+0x20)[1]==entrybase for i in range(8))
            assert host.CBMS_RemoveCastHooks()==1
            assert lookup(base)[0] is None and lookup(entrybase+0x20)[0] is None
        s.original()
    finally:
        if host.CBMS_TestCastHookAllocation(0):assert host.CBMS_RemoveCastHooks()==1
        s.close();assert host.CBMS_DetachDispatchCarriers()==1;assert host.CBMS_Destroy(h.runtime)==1
@pytest.mark.parametrize('kind',['entry','selector','thread'])
def test_later_owner_refusal_preflights_all_fifteen_sites(cast_api,host,windows,kind):
    h=CastHarness(cast_api);assert host.CBMS_DetachCastCarriers()==1;s=Sites(windows,h)
    try:
        assert host.CBMS_TestInstallCastHooks(C.byref(s.functions),h.runtime)==1
        before=C.string_at(s.base,0x3000);at=s.entries[-1] if kind=='entry' else s.sites[-1]
        if kind!='thread':s.edit(at,b'\xCC')
        observed=C.string_at(s.base,0x3000)
        if kind=='thread':
            result=[];t=threading.Thread(target=lambda:result.append(host.CBMS_RemoveCastHooks()));t.start();t.join();assert result==[0]
        else:assert host.CBMS_RemoveCastHooks()==0
        assert C.string_at(s.base,0x3000)==observed
        if kind!='thread':s.edit(at,before[at-s.base:at-s.base+1])
        assert host.CBMS_RemoveCastHooks()==1;s.original()
    finally:
        if host.CBMS_TestCastHookAllocation(0):assert host.CBMS_RemoveCastHooks()==1
        s.close();assert host.CBMS_DetachDispatchCarriers()==1;assert host.CBMS_Destroy(h.runtime)==1
