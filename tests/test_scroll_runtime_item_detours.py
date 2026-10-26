"""Actual item prologue state and Windows unwind; never invoke game functions."""
import ctypes as C
import importlib.util,struct

import pytest
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
from unicorn import x86_const as X
from test_scroll_runtime_binding import pinned_image,SOURCE
from test_scroll_runtime_binding import windows
from test_scroll_runtime_binding import os_unwinder

spec=importlib.util.spec_from_file_location('item_detours',SOURCE/'item_detours.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
REGS=[getattr(X,'UC_X86_REG_'+name) for name in ['RAX','RBX','RCX','RDX','RBP','RSI','RDI','R8','R9','R10','R11','R12','R13','R14','R15','RSP']]


def execute(image,name,hooked,definitions=module,address=None):
    pe,_,names=image
    if address is None:address=next(a for a,n in names.items() if n==name)
    prefix=bytes.fromhex(definitions.SITES[name][0])
    plan=definitions.plan(name,address,0x150001000,0x150002000,pe.get_data(address-pe.OPTIONAL_HEADER.ImageBase,len(prefix)))
    uc=Uc(UC_ARCH_X86,UC_MODE_64);base=pe.OPTIONAL_HEADER.ImageBase;data=pe.get_memory_mapped_image()
    uc.mem_map(base,(len(data)+4095)&~4095);uc.mem_write(base,data)
    stack,cave=0x20000000,0x150000000
    uc.mem_map(stack,0x10000);uc.mem_map(cave,0x10000);uc.mem_write(cave,plan['trampoline'])
    rsp,return_to=stack+0x8008,stack+0xFFF0;uc.mem_write(rsp,struct.pack('<Q',return_to))
    for i,reg in enumerate(REGS):uc.reg_write(reg,0xCAFE0000+i*0x101)
    uc.reg_write(X.UC_X86_REG_RSP,rsp);uc.reg_write(X.UC_X86_REG_EFLAGS,0x246)
    points=[]
    def event(_,pc,size,user):
        if cave<=pc<cave+plan['instruction_size']:
            points.append(dict(offset=pc-cave,regs=[uc.reg_read(r) for r in REGS],stack=bytes(uc.mem_read(stack,0x10000))))
    uc.hook_add(UC_HOOK_CODE,event)
    uc.emu_start(cave if hooked else address,address+len(prefix),count=100)
    assert uc.reg_read(X.UC_X86_REG_RIP)==address+len(prefix)
    return dict(registers=[uc.reg_read(r) for r in REGS],flags=uc.reg_read(X.UC_X86_REG_EFLAGS),
        stack=bytes(uc.mem_read(stack,0x10000)),points=points,plan=plan)


@pytest.mark.parametrize('name',list(module.SITES))
def test_item_entry_trampoline_preserves_native_state_and_all_instruction_unwind(pinned_image,name,windows,os_unwinder):
    original,hooked=execute(pinned_image,name,False),execute(pinned_image,name,True)
    assert original['registers']==hooked['registers'] and original['flags']==hooked['flags']
    old,new=bytearray(original['stack']),bytearray(hooked['stack'])
    if hooked['plan']['frame']:
        # The native caller-home area is ours after the copied allocation. Only
        # eight bytes there carry the resume address; no original input changes.
        offset=hooked['registers'][15]-0x20000000;old[offset:offset+8]=new[offset:offset+8]
    assert old==new
    cave,stack=0x50000000,0x20000000;allocated=[];plan=hooked['plan']
    try:
        for address in (cave,stack):
            assert windows.VirtualAlloc(address,0x10000,0x3000,4)==address;allocated.append(address)
        C.memmove(cave,plan['trampoline'],len(plan['trampoline']));C.memmove(cave+0x800,plan['unwind'],len(plan['unwind']))
        entry=(C.c_uint32*3)(0,plan['instruction_size'],0x800)
        for point in hooked['points']:
            C.memmove(stack,point['stack'],len(point['stack']));before=(C.c_uint64*16)(*point['regs']);after=(C.c_uint64*17)()
            assert os_unwinder(cave,cave+point['offset'],entry,before,after)==0
            assert after[15]==stack+0x8010 and after[16]==stack+0xFFF0
            for i in (1,4,5,6,11,12,13,14):assert after[i]==0xCAFE0000+i*0x101
    finally:
        for address in reversed(allocated):assert windows.VirtualFree(address,0,0x8000)
