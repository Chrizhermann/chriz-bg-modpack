"""Install/remove real hooks only on our private, never-invoked byte fixtures.

The actual product DLL is linked separately; no game/EEex module is loaded here.
"""
import ctypes as C
import struct
import subprocess
import threading

import pytest
from test_scroll_runtime_binding import windows
from test_scroll_runtime_native import SOURCE, compiler_environment

PREFIX = bytes.fromhex("4c8bdc49895b10")
PREVIOUS = C.CFUNCTYPE(None,C.c_void_p,C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint8)
@pytest.fixture(scope="module")
def host(tmp_path_factory):
    folder=tmp_path_factory.mktemp("scroll-decode-host")
    compiler,environment,msvc=compiler_environment();assert msvc
    output=folder/"private_host.dll"
    units=["native_api.cpp","eeex_save_bridge.cpp","decode_carrier_api.cpp","decode_hook_host.cpp","marshal_carrier_api.cpp","lifecycle_carrier_api.cpp"]
    command=[compiler,"/nologo","/std:c++20","/EHsc","/W4","/WX","/permissive-","/DCBMS_OFFLINE_HARNESS","/LD"]
    result=subprocess.run(command+[str(SOURCE/name) for name in units]+["/Fe"+str(output)],cwd=folder,env=environment,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    api=C.CDLL(str(output))
    signatures={
        "CBMS_TestInstallDecodeHooks":([C.c_size_t]*3,C.c_int),
        "CBMS_TestDecodeAllocation":([],C.c_size_t),
        "CBMS_TestDecodeFailure":([C.c_int],None),
        "CBMS_TestInstallPersistenceHooks":([C.c_size_t]*4,C.c_int),
        "CBMS_TestInstallEffectPersistenceHooks":([C.c_size_t]*7,C.c_int),
        "CBMS_RemoveDecodeHooks":([],C.c_int),
        "CBMS_DecodeHookError":([],C.c_char_p),
        "CBMS_UnmarshalCarrier":([C.c_void_p,C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint8],None),
    }
    for name,(arguments,result_type) in signatures.items():
        function=getattr(api,name);function.argtypes=arguments;function.restype=result_type
    return api


class PrivateSites:
    def __init__(self,windows,route,callback=None):
        self.windows=windows
        self.base=windows.VirtualAlloc(None,0x2000,0x3000,4);assert self.base
        self.decoder,self.unmarshal=self.base+0x100,self.base+0x1100
        self.callback=callback
        self.previous=C.cast(callback,C.c_void_p).value if callback else self.base+0x500
        if route=="rel32": self.head=b"\xe9"+struct.pack("<i",self.previous-self.unmarshal-5)+bytes(range(9))
        # "aligned" is EEex's live 16-byte form: FF 25 02 00 00 00, two padding bytes, target.
        elif route=="aligned": self.head=b"\xff\x25\x02"+bytes(5)+struct.pack("<Q",self.previous)
        else: self.head=b"\xff\x25"+bytes(4)+struct.pack("<Q",self.previous)
        C.memmove(self.decoder,PREFIX,len(PREFIX));C.memmove(self.unmarshal,self.head,len(self.head))
        old=C.c_uint32();assert windows.VirtualProtect(self.base,0x2000,0x20,C.byref(old))

    def edit(self,address,data):
        old=C.c_uint32();assert self.windows.VirtualProtect(address,len(data),0x40,C.byref(old))
        C.memmove(address,data,len(data))
        ignored=C.c_uint32();assert self.windows.VirtualProtect(address,len(data),old.value,C.byref(ignored))

    def assert_original(self):
        assert C.string_at(self.decoder,7)==PREFIX
        assert C.string_at(self.unmarshal,len(self.head))==self.head
        # VirtualProtect returns the previous protection without writing bytes.
        for address in (self.decoder,self.unmarshal):
            old=C.c_uint32();assert self.windows.VirtualProtect(address,1,0x20,C.byref(old))
            assert old.value==0x20

    def close(self):
        assert self.windows.VirtualFree(self.base,0,0x8000)


def lookup(address):
    ntdll=C.WinDLL("ntdll")
    function=ntdll.RtlLookupFunctionEntry
    function.argtypes=[C.c_uint64,C.POINTER(C.c_uint64),C.c_void_p];function.restype=C.c_void_p
    base=C.c_uint64();entry=function(address,C.byref(base),None)
    return entry,base.value


@pytest.mark.parametrize("route",["rel32","absolute","aligned"])
def test_private_hook_install_register_and_exact_restore(host,windows,route):
    sites=PrivateSites(windows,route)
    try:
        assert host.CBMS_TestInstallDecodeHooks(sites.unmarshal,sites.decoder,sites.previous)==1,host.CBMS_DecodeHookError()
        allocation=host.CBMS_TestDecodeAllocation();assert allocation
        patched=C.string_at(sites.decoder,7)
        assert patched[0]==0xe9 and patched[5:]==b"\x90\x90"
        assert sites.decoder+5+struct.unpack("<i",patched[1:5])[0]==allocation
        assert C.string_at(allocation+0x20,7)==PREFIX
        assert struct.unpack("<Q",C.string_at(allocation+0x2d,8))[0]==sites.decoder+7
        assert C.string_at(sites.unmarshal,6)==b"\xff\x25"+bytes(4)
        # Bytes of EEex's longer jump past our 14 stay as they were until removal.
        assert C.string_at(sites.unmarshal+14,len(sites.head)-14)==sites.head[14:]
        assert lookup(allocation+0x20)==(allocation+0x50,allocation)
        assert host.CBMS_TestInstallDecodeHooks(sites.unmarshal,sites.decoder,sites.previous)==0
        assert b"already installed" in host.CBMS_DecodeHookError()
        assert host.CBMS_RemoveDecodeHooks()==1,host.CBMS_DecodeHookError()
        sites.assert_original();assert not host.CBMS_TestDecodeAllocation()
        assert lookup(allocation+0x20)[0] is None
    finally:
        if host.CBMS_TestDecodeAllocation(): assert host.CBMS_RemoveDecodeHooks()==1
        sites.close()


@pytest.mark.parametrize("point",[1,2])
def test_partial_install_restores_original_protection_and_bytes(host,windows,point):
    sites=PrivateSites(windows,"absolute")
    try:
        host.CBMS_TestDecodeFailure(point)
        assert host.CBMS_TestInstallDecodeHooks(sites.unmarshal,sites.decoder,sites.previous)==0
        assert b"injected failure" in host.CBMS_DecodeHookError()
        sites.assert_original();assert not host.CBMS_TestDecodeAllocation()
        assert host.CBMS_TestInstallDecodeHooks(sites.unmarshal,sites.decoder,sites.previous)==1
        assert host.CBMS_RemoveDecodeHooks()==1
    finally:
        if host.CBMS_TestDecodeAllocation(): assert host.CBMS_RemoveDecodeHooks()==1
        sites.close()


def test_later_owner_and_foreign_thread_refuse_before_any_restoration(host,windows):
    sites=PrivateSites(windows,"absolute")
    try:
        assert host.CBMS_TestInstallDecodeHooks(sites.unmarshal,sites.decoder,sites.previous)==1
        decoder,unmarshal=C.string_at(sites.decoder,7),C.string_at(sites.unmarshal,14)
        results=[]
        thread=threading.Thread(target=lambda:results.append(host.CBMS_RemoveDecodeHooks()))
        thread.start();thread.join();assert results==[0]
        assert b"quiescent owner thread" in host.CBMS_DecodeHookError()
        sites.edit(sites.decoder,b"\xcc")
        assert host.CBMS_RemoveDecodeHooks()==0
        assert b"another owner" in host.CBMS_DecodeHookError()
        assert C.string_at(sites.unmarshal,14)==unmarshal
        sites.edit(sites.decoder,decoder)
        assert host.CBMS_RemoveDecodeHooks()==1
        sites.assert_original()
    finally:
        if host.CBMS_TestDecodeAllocation(): assert host.CBMS_RemoveDecodeHooks()==1
        sites.close()


def test_active_previous_callback_prevents_unload(host,windows):
    results=[]
    @PREVIOUS
    def previous(*arguments):
        results.append((arguments,host.CBMS_RemoveDecodeHooks()))
    sites=PrivateSites(windows,"absolute",previous)
    try:
        assert host.CBMS_TestInstallDecodeHooks(sites.unmarshal,sites.decoder,sites.previous)==1
        # Invoke only our compiled carrier and our Python callback, never fixture bytes.
        host.CBMS_UnmarshalCarrier(0x1000,None,0,None,0)
        assert results==[((0x1000,None,0,None,0),0)]
        assert host.CBMS_RemoveDecodeHooks()==1
        sites.assert_original()
    finally:
        if host.CBMS_TestDecodeAllocation(): assert host.CBMS_RemoveDecodeHooks()==1
        sites.close()


@pytest.mark.parametrize("bad",["prefix","route"])
def test_changed_native_or_previous_route_refuses_without_allocation(host,windows,bad):
    sites=PrivateSites(windows,"absolute")
    try:
        if bad=="prefix": sites.edit(sites.decoder,b"\x90")
        else: sites.edit(sites.unmarshal,b"\x90")
        before=(C.string_at(sites.decoder,7),C.string_at(sites.unmarshal,14))
        assert host.CBMS_TestInstallDecodeHooks(sites.unmarshal,sites.decoder,sites.previous)==0
        assert not host.CBMS_TestDecodeAllocation()
        assert (C.string_at(sites.decoder,7),C.string_at(sites.unmarshal,14))==before
    finally:
        sites.close()


@pytest.mark.parametrize("fail",[False,True])
def test_all_three_persistence_entries_one_registration_and_rollback(host,windows,fail):
    sites=PrivateSites(windows,"absolute")
    marshal=sites.base+0x300
    prefix=bytes.fromhex("405356574154415541564881ec88010000")
    sites.edit(marshal,prefix)
    try:
        if fail:host.CBMS_TestDecodeFailure(3)
        ok=host.CBMS_TestInstallPersistenceHooks(sites.unmarshal,sites.decoder,sites.previous,marshal)
        if fail:
            assert ok==0 and b"injected failure" in host.CBMS_DecodeHookError()
            assert not host.CBMS_TestDecodeAllocation()
        else:
            assert ok==1,host.CBMS_DecodeHookError()
            allocation=host.CBMS_TestDecodeAllocation()
            assert lookup(allocation+0x120)==(allocation+0x5c,allocation)
            assert C.string_at(allocation+0x120,len(prefix))==prefix
            assert C.string_at(allocation+0x140,4)==bytes.fromhex("ff642400")
            patched=C.string_at(marshal,len(prefix));assert patched[0]==0xe9
            assert marshal+5+struct.unpack("<i",patched[1:5])[0]==allocation+0x100
            assert host.CBMS_RemoveDecodeHooks()==1
            assert lookup(allocation+0x120)[0] is None
        sites.assert_original();assert C.string_at(marshal,len(prefix))==prefix
    finally:
        if host.CBMS_TestDecodeAllocation():assert host.CBMS_RemoveDecodeHooks()==1
        sites.close()


@pytest.mark.parametrize('fail',[False,True])
def test_all_six_effect_persistence_entries_restore_and_unregister(host,windows,fail):
    sites=PrivateSites(windows,'absolute')
    entries=[sites.base+offset for offset in (0x300,0x600,0x800,0xA00)]
    prefixes=[bytes.fromhex('405356574154415541564881ec88010000'),bytes.fromhex('4c8bdc49895310'),bytes.fromhex('4c8bdc49894b08'),bytes.fromhex('4c8bdc49894b08')]
    for address,prefix in zip(entries,prefixes):sites.edit(address,prefix)
    try:
        if fail:host.CBMS_TestDecodeFailure(3)
        result=host.CBMS_TestInstallEffectPersistenceHooks(sites.unmarshal,sites.decoder,sites.previous,*entries)
        if fail:
            assert result==0 and not host.CBMS_TestDecodeAllocation()
        else:
            assert result==1,host.CBMS_DecodeHookError()
            trampolines=[]
            for index,address in enumerate(entries[1:]):
                patch=C.string_at(address,7);assert patch[0]==0xe9
                relay=address+5+struct.unpack('<i',patch[1:5])[0]
                table,base=lookup(relay+0x20)
                assert table==base+0x300+index*12 and C.string_at(relay+0x20,7)==prefixes[index+1]
                trampolines.append(relay+0x20)
            assert host.CBMS_RemoveDecodeHooks()==1
            assert all(lookup(address)[0] is None for address in trampolines)
        sites.assert_original()
        for address,prefix in zip(entries,prefixes):assert C.string_at(address,len(prefix))==prefix
    finally:
        if host.CBMS_TestDecodeAllocation():assert host.CBMS_RemoveDecodeHooks()==1
        sites.close()
