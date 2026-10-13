"""Actual native Marshal via emitted trampoline and Windows unwind each instruction."""
import ctypes as C
import importlib.util
import struct

from test_scroll_runtime_effect_marshal import native
from test_scroll_runtime_detours import action_image,SOURCE
from test_scroll_runtime_unwind import os_unwinder
from test_scroll_runtime_binding import windows

spec=importlib.util.spec_from_file_location("marshal_detours",SOURCE/"marshal_detours.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def trace(image):
    pe,_,names=image
    address=next(a for a,n in names.items() if n=="CGameEffectList::Marshal")
    plan=module.plan(address,0x150001000,0x150002000,pe.get_data(address-pe.OPTIONAL_HEADER.ImageBase,len(module.PREFIX)))
    records=[]
    for timing in (9,2,0,9):
        record=bytearray((i*11+4)%256 for i in range(264));struct.pack_into("<I",record,0x1c,timing);records.append(bytes(record))
    return native.marshal(pe,names,records),native.marshal(pe,names,records,trampoline=plan["trampoline"]),plan


def test_native_original_and_trampoline_return_same_filtered_records(action_image):
    original,hooked,_=trace(action_image)
    assert {k:v for k,v in original.items() if k!="points"}=={k:v for k,v in hooked.items() if k!="points"}
    assert [p["offset"] for p in hooked["points"]]==[0,2,3,4,6,8,10,17,24,32]


def test_windows_unwinds_every_marshal_trampoline_instruction(action_image,windows,os_unwinder):
    _,hooked,plan=trace(action_image)
    cave,stack=0x50000000,0x20000000
    pages=[]
    try:
        for address in (cave,stack):
            assert windows.VirtualAlloc(address,0x10000,0x3000,4)==address;pages.append(address)
        C.memmove(cave,plan["trampoline"],len(plan["trampoline"]));C.memmove(cave+0x800,plan["unwind"],len(plan["unwind"]))
        entry=(C.c_uint32*3)(0,len(plan["trampoline"]),0x800)
        for point in hooked["points"]:
            C.memmove(stack,point["stack"],len(point["stack"]))
            before=(C.c_uint64*16)(*point["registers"]);after=(C.c_uint64*17)()
            assert os_unwinder(cave,cave+point["offset"],entry,before,after)==0
            assert after[15]==stack+0x8010 and after[16]==stack+0xFFF0
            for i in (1,4,5,6,11,12,13,14): assert after[i]==0xCAFE0000+i*0x101
    finally:
        for address in reversed(pages):assert windows.VirtualFree(address,0,0x8000)
