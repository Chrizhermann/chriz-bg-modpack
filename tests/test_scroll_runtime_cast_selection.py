"""Actual native selector loops plus emitted CALL bridges and OS unwind.
Only getter/resource and policy callbacks are substituted. No game launch.
"""
import ctypes as C
import importlib.util,struct,sys
import pytest
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
from unicorn import x86_const as X
from test_scroll_runtime_binding import pinned_image,SOURCE
from test_scroll_runtime_binding import windows
from test_scroll_runtime_binding import os_unwinder
from test_scroll_runtime_item_detours import REGS
sys.path.insert(0,str(SOURCE))
import cast_selection_detours as bridge
START=(0xFD,0x161,0x132,0x33B,0x17A,0xC6D,0xBDB)
STOP=(0x168,0x1E1,0x1AB,0x394,0x1CB,0xCC0,0xC3E)

def execute(image,path,replacement):
    pe,_,names=image;base=pe.OPTIONAL_HEADER.ImageBase;named={n:a for a,n in names.items()}
    entry=named[bridge.NAMES[path]];site=entry+bridge.CALL_OFFSETS[path];getter=named['CSpell::GetAbilityCount']
    cave,callback,stack,data=0x150000000,0x150008000,0x20000000,0x30000000
    plan=bridge.emit(path,site,cave,callback,getter,pe.get_data(site-base,5));uc=Uc(UC_ARCH_X86,UC_MODE_64)
    image_data=pe.get_memory_mapped_image();uc.mem_map(base,(len(image_data)+4095)&~4095);uc.mem_write(base,image_data)
    for at in (cave,stack,data):uc.mem_map(at,0x10000)
    uc.mem_write(cave,plan['code']);uc.mem_write(site,plan['patch'])
    rsp,rbp=stack+0x8000,stack+0xA000
    for i,reg in enumerate(REGS):uc.reg_write(reg,0xCAFE0000+i*0x101)
    uc.reg_write(X.UC_X86_REG_RSP,rsp);uc.reg_write(X.UC_X86_REG_RBP,rbp)
    uc.reg_write(X.UC_X86_REG_R15,data);uc.reg_write(X.UC_X86_REG_RDI,data)
    # ForceSpell's audited predecessor zeroes R13 before this bounded window;
    # the first header index is copied from R13W, not initialized in the loop.
    uc.reg_write(X.UC_X86_REG_R13,0)
    headers=[data+0x1000+i*0x100 for i in range(4)]
    for header,level in zip(headers,(1,6,12,20)):uc.mem_write(header+0x10,struct.pack('<H',level))
    if path==0:uc.mem_write(rbp+0x77,struct.pack('<I',7))
    elif path in (5,6):
        uc.reg_write(X.UC_X86_REG_RBX,data);uc.reg_write(X.UC_X86_REG_RDI,0);uc.reg_write(X.UC_X86_REG_R15,0)
        uc.mem_write(data+0x4AE0,struct.pack('<Q',data+0x100));uc.mem_write(data+0x4C8A,struct.pack('<H',7))
    else:uc.reg_write([None,X.UC_X86_REG_R8,X.UC_X86_REG_R8,X.UC_X86_REG_R14,X.UC_X86_REG_R12][path],7)
    points=[];calls=[];origin=None
    def returned(value):
        at=uc.reg_read(X.UC_X86_REG_RSP);to=struct.unpack('<Q',bytes(uc.mem_read(at,8)))[0]
        uc.reg_write(X.UC_X86_REG_RAX,value);uc.reg_write(X.UC_X86_REG_RSP,at+8);uc.reg_write(X.UC_X86_REG_RIP,to)
    def event(_,pc,size,user):
        nonlocal origin
        if pc==site:origin=[uc.reg_read(r) for r in REGS]
        if cave<=pc<cave+plan['tail']+6:
            points.append(dict(offset=pc-cave,regs=[uc.reg_read(r) for r in REGS],stack=bytes(uc.mem_read(stack,0x10000))))
        if pc==callback:
            assert uc.reg_read(X.UC_X86_REG_RCX)==path
            at=uc.reg_read(X.UC_X86_REG_RDX);saved=struct.unpack('<17Q',bytes(uc.mem_read(at,17*8)));assert saved[16]==site+5
            if replacement:
                if path==0:uc.mem_write(saved[11]+0x77,struct.pack('<I',replacement))
                elif path==1:uc.mem_write(at+17*8+0x58,struct.pack('<I',replacement))
                elif path==2:
                    uc.mem_write(at+3*8,struct.pack('<Q',replacement));uc.mem_write(at+17*8+0x6C,struct.pack('<I',replacement))
                elif path in (3,4):uc.mem_write(at+(2 if path==3 else 4)*8,struct.pack('<Q',replacement))
                else:uc.mem_write(saved[12]+0x4C8A,struct.pack('<H',replacement))
            # Deliberately trash volatile native ABI state inside the callback.
            for register in (X.UC_X86_REG_RAX,X.UC_X86_REG_RCX,X.UC_X86_REG_RDX,X.UC_X86_REG_R8,X.UC_X86_REG_R9,X.UC_X86_REG_R10,X.UC_X86_REG_R11):uc.reg_write(register,0xDEAD0000)
            returned(0);calls.append('policy')
        elif pc==getter:returned(len(headers));calls.append('count')
        elif pc==named['CSpell::GetAbility']:
            index=uc.reg_read(X.UC_X86_REG_RDX)&0xFFFFFFFF;returned(headers[index] if index<len(headers) else 0)
        elif pc==named['max']:
            values=[struct.unpack('<i',bytes(uc.mem_read(uc.reg_read(reg),4)))[0] for reg in (X.UC_X86_REG_RCX,X.UC_X86_REG_RDX)];returned(max(values))
    uc.hook_add(UC_HOOK_CODE,event);uc.emu_start(entry+START[path],entry+STOP[path],count=2000)
    assert uc.reg_read(X.UC_X86_REG_RIP)==entry+STOP[path]
    output=uc.reg_read(X.UC_X86_REG_R13 if path in (0,5,6) else X.UC_X86_REG_RAX)
    assert headers.index(output)==(2 if replacement else 1) and calls.count('policy')==1
    return plan,points,origin,rsp,site

@pytest.mark.parametrize('path',range(7))
@pytest.mark.parametrize('replacement',[0,12])
def test_native_selector_call_bridge_preserves_getter_return_and_selects_policy_header(pinned_image,path,replacement):
    execute(pinned_image,path,replacement)

@pytest.mark.parametrize('path',range(7))
def test_every_selector_bridge_instruction_has_valid_windows_unwind(pinned_image,path,windows,os_unwinder):
    plan,points,origin,rsp,site=execute(pinned_image,path,0);cave,stack=0x50000000,0x20000000;allocations=[]
    try:
        for at in (cave,stack):assert windows.VirtualAlloc(at,0x10000,0x3000,4)==at;allocations.append(at)
        C.memmove(cave,plan['code'],len(plan['code']))
        for point in points:
            begin,end,info=next(row for row in plan['segments'] if row[0]==point['offset']);C.memmove(cave+0x800,info,len(info))
            rf=(C.c_uint32*3)(begin,end,0x800);C.memmove(stack,point['stack'],len(point['stack']))
            before=(C.c_uint64*16)(*point['regs']);after=(C.c_uint64*17)()
            assert os_unwinder(cave,cave+point['offset'],rf,before,after)==0
            assert after[15]==rsp and after[16]==site+5
            for i in (1,4,5,6,11,12,13,14):assert after[i]==origin[i]
    finally:
        for at in reversed(allocations):assert windows.VirtualFree(at,0,0x8000)
