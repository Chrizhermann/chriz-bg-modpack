"""Actual native decoder prefix/return semantics plus OS unwind of trampoline."""
import ctypes as C
import importlib.util
import struct

import pytest
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn import x86_const as X

from test_scroll_runtime_detours import action_image, SOURCE
from test_scroll_runtime_unwind import os_unwinder
from test_scroll_runtime_binding import windows

spec = importlib.util.spec_from_file_location("scroll_decoder_detours", SOURCE / "decode_detours.py")
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
REGS = [getattr(X,"UC_X86_REG_"+name) for name in
        ["RAX","RBX","RCX","RDX","RBP","RSI","RDI","R8","R9","R10","R11","R12","R13","R14","R15","RSP"]]


def execute(image, hooked):
    pe, _, names = image
    address = next(a for a,n in names.items() if n=="CGameEffect::DecodeEffectFromBase")
    machine = Uc(UC_ARCH_X86,UC_MODE_64)
    base, mapped = pe.OPTIONAL_HEADER.ImageBase, pe.get_memory_mapped_image()
    machine.mem_map(base,(len(mapped)+4095)&~4095); machine.mem_write(base,mapped)
    stack, data, cave = 0x20000000, 0x30000000, 0x150000000
    for pointer in (stack,data,cave): machine.mem_map(pointer,0x10000)
    record = b"EFF V2.0"+bytes((i*13+7)%256 for i in range(256))
    machine.mem_write(data,record)
    target = data+0x1000
    rsp, stop = stack+0x8008,stack+0xFF00
    machine.mem_write(rsp,struct.pack("<Q",stop))
    for i,reg in enumerate(REGS): machine.reg_write(reg,0xCAFE0000+i*0x101)
    machine.reg_write(X.UC_X86_REG_RSP,rsp);machine.reg_write(X.UC_X86_REG_RCX,data)
    plan = module.plan_decoder(address,cave+0x1000,cave+0x2000,pe.get_data(address-base,7))
    machine.mem_write(cave,plan["trampoline"])
    calls,points=[],[]
    def ret():
        p=machine.reg_read(X.UC_X86_REG_RSP)
        dest=struct.unpack("<Q",machine.mem_read(p,8))[0]
        machine.reg_write(X.UC_X86_REG_RSP,p+8);machine.reg_write(X.UC_X86_REG_RIP,dest)
    def step(_,pc,size,user):
        if cave <= pc < cave+13:
            points.append(dict(offset=pc-cave,registers=[machine.reg_read(r) for r in REGS],stack=bytes(machine.mem_read(stack,0x10000))))
        name=names.get(pc,"")
        if name=="CGameEffect::DecodeEffect":
            # The native factory receives the original opcode and default
            # source/target values. Only allocation/type dispatch is substituted.
            p=machine.reg_read(X.UC_X86_REG_RCX)
            calls.append(("factory",bytes(machine.mem_read(p,2)),machine.reg_read(X.UC_X86_REG_R8)))
            machine.reg_write(X.UC_X86_REG_RAX,target);ret()
        elif name=="CGameEffect::CopyFromBase":
            dest,raw=machine.reg_read(X.UC_X86_REG_RCX),machine.reg_read(X.UC_X86_REG_RDX)
            calls.append(("copy",dest,raw));machine.mem_write(dest+8,bytes(machine.mem_read(raw,264)));ret()
        elif name=="__security_check_cookie":ret()
    machine.hook_add(UC_HOOK_CODE,step)
    machine.emu_start(cave if hooked else address,stop,count=1000)
    assert machine.reg_read(X.UC_X86_REG_RIP)==stop
    assert machine.reg_read(X.UC_X86_REG_RSP)==rsp+8
    assert machine.reg_read(X.UC_X86_REG_RAX)==target
    for i in (1,4,5,6,11,12,13,14): assert machine.reg_read(REGS[i])==0xCAFE0000+i*0x101
    return dict(calls=calls,effect=bytes(machine.mem_read(target+8,264)),points=points,plan=plan)


def test_original_vs_trampoline_actual_native_decoder(action_image):
    original,hooked=execute(action_image,False),execute(action_image,True)
    assert original["calls"]==hooked["calls"] and original["effect"]==hooked["effect"]
    assert [p["offset"] for p in hooked["points"]]==[0,3,7]


def test_os_unwinds_each_decoder_trampoline_instruction(action_image,windows,os_unwinder):
    trace=execute(action_image,True)
    cave,stack=0x50000000,0x20000000
    allocated=[]
    try:
        for address in (cave,stack):
            assert windows.VirtualAlloc(address,0x10000,0x3000,4)==address
            allocated.append(address)
        code,info=trace["plan"]["trampoline"],trace["plan"]["unwind"]
        C.memmove(cave,code,len(code));C.memmove(cave+0x800,info,len(info))
        entry=(C.c_uint32*3)(0,len(code),0x800)
        for point in trace["points"]:
            C.memmove(stack,point["stack"],len(point["stack"]))
            before=(C.c_uint64*16)(*point["registers"]);after=(C.c_uint64*17)()
            assert os_unwinder(cave,cave+point["offset"],entry,before,after)==0
            assert after[15]==stack+0x8010 and after[16]==stack+0xFF00
            for i in (1,4,5,6,11,12,13,14):assert after[i]==0xCAFE0000+i*0x101
    finally:
        for address in reversed(allocated):assert windows.VirtualFree(address,0,0x8000)


def test_exact_chain_and_refusal_rules():
    entry,prior,wrapper=0x140000000,0x18000F2F0,0x170000000
    head=module.absolute_jump(prior)
    plan=module.plan_unmarshal(entry,prior,wrapper,head)
    assert plan["previous"]==prior and plan["original"]==head
    assert struct.unpack_from("<Q",plan["patch"],6)[0]==wrapper
    with pytest.raises(ValueError,match="prologue"):
        module.plan_decoder(entry,entry+0x1000,wrapper,bytes(7))
    with pytest.raises(ValueError,match="rel32"):
        module.plan_decoder(entry,entry+0x90000000,wrapper,module.PREFIX)
    with pytest.raises(ValueError,match="target"):
        module.plan_unmarshal(entry,prior+1,wrapper,head)
