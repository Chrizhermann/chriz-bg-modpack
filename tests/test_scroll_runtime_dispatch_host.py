"""Actual six-entry install/remove on inert private fixtures only."""
import ctypes as C
import importlib.util,struct,sys,threading
import pytest
from test_scroll_runtime_native import SOURCE
from test_scroll_runtime_binding import windows
from test_scroll_runtime_decode_host import lookup
from test_scroll_runtime_dispatch_carriers import dispatch_api,Harness,Functions,APPLY,CTOR,ADD,RUN,DESTROY
sys.path.insert(0,str(SOURCE))
spec=importlib.util.spec_from_file_location('dispatch_host_recipe',SOURCE/'dispatch_detours.py');recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)
@pytest.fixture(scope='module')
def host(dispatch_api):
    api=dispatch_api[0]
    signatures={
        'TestInstallDispatchHooks':([C.POINTER(Functions),C.c_void_p],C.c_int),
        'TestDispatchHookAllocation':([],C.c_size_t),'TestDispatchHookFailure':([C.c_int],None),
        'RemoveDispatchHooks':([],C.c_int),'DispatchHookError':([],C.c_char_p),
    }
    for name,(args,result) in signatures.items():
        fn=getattr(api,'CBMS_'+name);fn.argtypes=args;fn.restype=result
    return api
class Sites:
    def __init__(self,windows,h):
        self.windows=windows;self.base=windows.VirtualAlloc(None,0x1000,0x3000,4);assert self.base
        self.entries=[self.base+0x100+i*0x100 for i in range(6)]
        self.prefixes=[bytes.fromhex(value[0]) for value in recipe.SITES.values()]
        for address,prefix in zip(self.entries,self.prefixes):C.memmove(address,prefix,len(prefix))
        old=C.c_uint32();assert windows.VirtualProtect(self.base,0x1000,0x20,C.byref(old))
        self.functions=Functions.from_buffer_copy(bytes(h.functions))
        for (name,kind),address in zip([('apply146',APPLY),('apply148',APPLY),('ctor',CTOR),('add',ADD),('run',RUN),('destroy',DESTROY)],self.entries):setattr(self.functions,name,kind(address))
    def edit(self,address,data):
        old=C.c_uint32();assert self.windows.VirtualProtect(address,len(data),0x40,C.byref(old));C.memmove(address,data,len(data))
        ignored=C.c_uint32();assert self.windows.VirtualProtect(address,len(data),old.value,C.byref(ignored))
    def original(self):
        assert [C.string_at(at,len(prefix)) for at,prefix in zip(self.entries,self.prefixes)]==self.prefixes
        old=C.c_uint32();assert self.windows.VirtualProtect(self.base,1,0x20,C.byref(old));assert old.value==0x20
    def close(self):assert self.windows.VirtualFree(self.base,0,0x8000)
def close_without_carriers(h):
    # No fixture instruction was invoked, so no observed carrier was produced.
    assert h.api.CBMS_Destroy(h.runtime)==1

@pytest.mark.parametrize('failure',[0,1,2,3,4,5,6,100])
def test_dispatch_atomic_six_entry_register_write_restore(dispatch_api,host,windows,failure):
    h=Harness(dispatch_api);assert host.CBMS_DetachDispatchCarriers()==1;sites=Sites(windows,h)
    try:
        if failure:host.CBMS_TestDispatchHookFailure(failure)
        result=host.CBMS_TestInstallDispatchHooks(C.byref(sites.functions),h.runtime)
        if failure:
            assert result==0 and b'injected' in host.CBMS_DispatchHookError()
            assert host.CBMS_TestDispatchHookAllocation()==0
        else:
            assert result==1,host.CBMS_DispatchHookError()
            base=host.CBMS_TestDispatchHookAllocation();assert base
            for i,(name,at,prefix) in enumerate(zip(recipe.SITES,sites.entries,sites.prefixes)):
                patch=C.string_at(at,len(prefix));relay=at+5+struct.unpack('<i',patch[1:5])[0]
                assert relay==base+i*0x100
                wrapper=struct.unpack('<Q',C.string_at(relay+6,8))[0]
                plan=recipe.plan(name,at,relay,wrapper,prefix)
                assert patch==plan['patch'] and C.string_at(relay+0x20,len(plan['trampoline']))==plan['trampoline']
                assert C.string_at(relay+0x80,len(plan['unwind']))==plan['unwind']
                assert lookup(relay+0x20)==(base+0x600+i*12,base)
            assert host.CBMS_RemoveDispatchHooks()==1
            assert all(lookup(base+i*0x100+0x20)[0] is None for i in range(6))
        sites.original()
    finally:
        if host.CBMS_TestDispatchHookAllocation():assert host.CBMS_RemoveDispatchHooks()==1
        sites.close();close_without_carriers(h)

def test_dispatch_later_owner_and_wrong_thread_cannot_partially_remove(dispatch_api,host,windows):
    h=Harness(dispatch_api);assert host.CBMS_DetachDispatchCarriers()==1;sites=Sites(windows,h)
    try:
        assert host.CBMS_TestInstallDispatchHooks(C.byref(sites.functions),h.runtime)==1
        after=[C.string_at(at,len(prefix)) for at,prefix in zip(sites.entries,sites.prefixes)]
        results=[];thread=threading.Thread(target=lambda:results.append(host.CBMS_RemoveDispatchHooks()));thread.start();thread.join()
        assert results==[0] and b'owner thread' in host.CBMS_DispatchHookError()
        sites.edit(sites.entries[-1],b'\xCC');assert host.CBMS_RemoveDispatchHooks()==0
        assert b'another owner' in host.CBMS_DispatchHookError()
        assert [C.string_at(at,len(prefix)) for at,prefix in zip(sites.entries[:-1],sites.prefixes[:-1])]==after[:-1]
        sites.edit(sites.entries[-1],after[-1]);assert host.CBMS_RemoveDispatchHooks()==1;sites.original()
    finally:
        if host.CBMS_TestDispatchHookAllocation():assert host.CBMS_RemoveDispatchHooks()==1
        sites.close();close_without_carriers(h)

@pytest.mark.parametrize('bad',['prefix','configuration'])
def test_dispatch_precondition_failure_has_no_leftover_hook_or_registration(dispatch_api,host,windows,bad):
    h=Harness(dispatch_api);assert host.CBMS_DetachDispatchCarriers()==1;sites=Sites(windows,h)
    try:
        if bad=='prefix':sites.edit(sites.entries[2],b'\x90')
        before=C.string_at(sites.base,0x1000)
        assert host.CBMS_TestInstallDispatchHooks(C.byref(sites.functions),None if bad=='configuration' else h.runtime)==0
        assert host.CBMS_DispatchHookError() and not host.CBMS_TestDispatchHookAllocation()
        assert C.string_at(sites.base,0x1000)==before
    finally:
        if host.CBMS_TestDispatchHookAllocation():assert host.CBMS_RemoveDispatchHooks()==1
        sites.close();close_without_carriers(h)
