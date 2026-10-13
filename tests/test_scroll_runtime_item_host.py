"""Real five-entry patch/unwind transactions on private instruction fixtures.
No game image, no invocation of these fixture instructions or game functions.
"""
import ctypes as C
import importlib.util
import struct
import threading
import pytest
from test_scroll_runtime_native import SOURCE
from test_scroll_runtime_binding import windows
from test_scroll_runtime_decode_host import lookup
from test_scroll_runtime_item_carriers import item_api,Functions,Harness,DIGEST,USE,POINT,FIRE,ROOT

@pytest.fixture(scope='module')
def host(item_api):
    api=item_api[0]
    signatures={
        'TestInstallItemHooks':([C.POINTER(Functions),C.c_void_p,C.c_void_p,C.c_uint32,DIGEST,C.c_void_p],C.c_int),
        'TestItemHookAllocation':([],C.c_size_t),'TestItemHookFailure':([C.c_int],None),
        'RemoveItemHooks':([],C.c_int),'ItemHookError':([],C.c_char_p),
    }
    for name,(args,result) in signatures.items():
        fn=getattr(api,'CBMS_'+name);fn.argtypes=args;fn.restype=result
    return api

class Sites:
    def __init__(self,windows,harness):
        self.windows=windows;self.base=windows.VirtualAlloc(None,0x1000,0x3000,4);assert self.base
        spec=importlib.util.spec_from_file_location('item_detours_host',SOURCE/'item_detours.py');self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.entries=[self.base+0x100+i*0x100 for i in range(5)]
        self.prefixes=[bytes.fromhex(value[0]) for value in self.module.SITES.values()]
        for at,prefix in zip(self.entries,self.prefixes):C.memmove(at,prefix,len(prefix))
        old=C.c_uint32();assert windows.VirtualProtect(self.base,0x1000,0x20,C.byref(old))
        self.functions=Functions.from_buffer_copy(bytes(harness.functions))
        self.functions.use=USE(self.entries[0]);self.functions.point=POINT(self.entries[1]);self.functions.fire=FIRE(self.entries[2]);self.functions.fire_point=FIRE(self.entries[3]);self.functions.effect=ROOT(self.entries[4])
    def edit(self,address,data):
        old=C.c_uint32();assert self.windows.VirtualProtect(address,len(data),0x40,C.byref(old))
        C.memmove(address,data,len(data));ignored=C.c_uint32();assert self.windows.VirtualProtect(address,len(data),old.value,C.byref(ignored))
    def original(self):
        for at,prefix in zip(self.entries,self.prefixes):assert C.string_at(at,len(prefix))==prefix
        old=C.c_uint32();assert self.windows.VirtualProtect(self.base,1,0x20,C.byref(old));assert old.value==0x20
    def close(self):assert self.windows.VirtualFree(self.base,0,0x8000)

@pytest.mark.parametrize('failure',range(7))
def test_five_item_entries_one_transaction_and_exact_unwind_bytes(item_api,host,windows,failure):
    h=Harness(item_api);assert h.configured==1
    assert host.CBMS_DetachItemCarriers()==1;h.configured=False
    sites=Sites(windows,h)
    try:
        if failure:host.CBMS_TestItemHookFailure(failure)
        result=host.CBMS_TestInstallItemHooks(C.byref(sites.functions),h.runtime,h.table,len(h.table),h.keep[-1],None)
        if failure:
            assert result==0 and b'injected' in host.CBMS_ItemHookError()
            assert host.CBMS_TestItemHookAllocation()==0
        else:
            assert result==1,host.CBMS_ItemHookError()
            base=host.CBMS_TestItemHookAllocation();assert base
            for i,(name,at,prefix) in enumerate(zip(sites.module.SITES,sites.entries,sites.prefixes)):
                patch=C.string_at(at,len(prefix));assert patch[0]==0xE9
                relay=at+5+struct.unpack('<i',patch[1:5])[0];assert relay==base+i*0x100
                wrapper=struct.unpack('<Q',C.string_at(relay+6,8))[0]
                plan=sites.module.plan(name,at,relay,wrapper,prefix)
                assert patch==plan['patch']
                assert C.string_at(relay+0x20,len(plan['trampoline']))==plan['trampoline']
                assert C.string_at(relay+0x80,len(plan['unwind']))==plan['unwind']
                assert lookup(relay+0x20)==(base+0x600+12*i,base)
            assert host.CBMS_RemoveItemHooks()==1,host.CBMS_ItemHookError()
            assert all(lookup(base+i*0x100+0x20)[0] is None for i in range(5))
        sites.original()
    finally:
        if host.CBMS_TestItemHookAllocation():assert host.CBMS_RemoveItemHooks()==1
        sites.close();h.close()

def test_later_owner_last_entry_blocks_all_restoration_and_foreign_thread(item_api,host,windows):
    h=Harness(item_api);assert host.CBMS_DetachItemCarriers()==1;h.configured=False;sites=Sites(windows,h)
    try:
        assert host.CBMS_TestInstallItemHooks(C.byref(sites.functions),h.runtime,h.table,len(h.table),h.keep[-1],None)==1
        after=[C.string_at(at,len(prefix)) for at,prefix in zip(sites.entries,sites.prefixes)]
        results=[];thread=threading.Thread(target=lambda:results.append(host.CBMS_RemoveItemHooks()));thread.start();thread.join()
        assert results==[0] and b'owner thread' in host.CBMS_ItemHookError()
        sites.edit(sites.entries[-1],b'\xCC')
        assert host.CBMS_RemoveItemHooks()==0 and b'another owner' in host.CBMS_ItemHookError()
        assert [C.string_at(at,len(prefix)) for at,prefix in zip(sites.entries[:-1],sites.prefixes[:-1])]==after[:-1]
        sites.edit(sites.entries[-1],after[-1]);assert host.CBMS_RemoveItemHooks()==1;sites.original()
    finally:
        if host.CBMS_TestItemHookAllocation():assert host.CBMS_RemoveItemHooks()==1
        sites.close();h.close()

@pytest.mark.parametrize('bad',['prefix','digest','overlap'])
def test_item_hook_rejects_bad_preconditions_without_persistent_registration(item_api,host,windows,bad):
    h=Harness(item_api);assert host.CBMS_DetachItemCarriers()==1;h.configured=False;sites=Sites(windows,h)
    try:
        digest=h.keep[-1]
        if bad=='prefix':sites.edit(sites.entries[3],b'\x90')
        if bad=='overlap':sites.functions.fire_point=FIRE(sites.entries[2])
        if bad=='digest':digest=DIGEST(lambda name,extension,out,user:0)
        before=C.string_at(sites.base,0x1000)
        assert host.CBMS_TestInstallItemHooks(C.byref(sites.functions),h.runtime,h.table,len(h.table),digest,None)==0
        assert host.CBMS_ItemHookError() and host.CBMS_TestItemHookAllocation()==0
        assert C.string_at(sites.base,0x1000)==before
    finally:
        if host.CBMS_TestItemHookAllocation():assert host.CBMS_RemoveItemHooks()==1
        sites.close();h.close()
