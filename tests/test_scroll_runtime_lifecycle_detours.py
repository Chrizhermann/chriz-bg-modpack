"""Actual shipped EEex wrappers through leaf trampolines, with no DLL invocation."""
import ctypes as C
import hashlib,importlib.util,json,os,struct
from pathlib import Path

import pefile,pytest
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
from unicorn import x86_const as X
from test_scroll_runtime_native import SOURCE
from test_scroll_runtime_binding import windows
from test_scroll_runtime_binding import os_unwinder

spec=importlib.util.spec_from_file_location('life_detours',SOURCE/'lifecycle_detours.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
PROFILES=json.loads((SOURCE/'lifecycle-profiles.json').read_text())
REGS=[getattr(X,'UC_X86_REG_'+name) for name in ['RAX','RBX','RCX','RDX','RBP','RSI','RDI','R8','R9','R10','R11','R12','R13','R14','R15','RSP']]


def execute(profile,entry,hooked):
    source=Path(os.path.expandvars(profile['source']))
    if not source.is_file():pytest.skip('offline lifecycle proof requires the unbundled pinned local executable')
    raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==profile['sha256']
    pe=pefile.PE(data=raw);base=pe.OPTIONAL_HEADER.ImageBase;image=pe.get_memory_mapped_image()
    uc=Uc(UC_ARCH_X86,UC_MODE_64);uc.mem_map(base,(len(image)+4095)&~4095);uc.mem_write(base,image)
    stack,cave=0x20000000,0x50000000
    uc.mem_map(stack,0x10000);uc.mem_map(cave,0x10000)
    address=base+entry['body']['rva'];plan=module.plan(address,base+0x200000,base+0x300000,bytes.fromhex(entry['prefix']))
    uc.mem_write(cave,plan['trampoline']);rsp,stop=stack+0x8008,stack+0xFFF0
    uc.mem_write(rsp,struct.pack('<Q',stop))
    for i,reg in enumerate(REGS):uc.reg_write(reg,0xCAFE0000+i*0x101)
    uc.reg_write(X.UC_X86_REG_RSP,rsp)
    calls,points=[],[]
    def event(_,pc,size,user):
        if cave<=pc<cave+13:points.append(dict(offset=pc-cave,regs=[uc.reg_read(r) for r in REGS],stack=bytes(uc.mem_read(stack,0x10000))))
        if pc==base+0x6400:
            # Substitute only the shared EEex stutter-logging/closure executor.
            # The wrapper builds the actual lambda argument pointers natively.
            p=uc.reg_read(X.UC_X86_REG_RDX)
            count=3 if entry['name']=='effect_copy' else 2
            values=struct.unpack('<'+'Q'*count,uc.mem_read(p,count*8))
            calls.append((uc.reg_read(X.UC_X86_REG_RCX),values[0],tuple(struct.unpack('<Q',uc.mem_read(x,8))[0] for x in values[1:])))
            current=uc.reg_read(X.UC_X86_REG_RSP);target=struct.unpack('<Q',uc.mem_read(current,8))[0]
            uc.reg_write(X.UC_X86_REG_RSP,current+8);uc.reg_write(X.UC_X86_REG_RIP,target)
    uc.hook_add(UC_HOOK_CODE,event);uc.emu_start(cave if hooked else address,stop,count=1000)
    assert uc.reg_read(X.UC_X86_REG_RIP)==stop and uc.reg_read(X.UC_X86_REG_RSP)==rsp+8
    for i in (1,4,5,6,11,12,13,14):assert uc.reg_read(REGS[i])==0xCAFE0000+i*0x101
    return calls,points,plan


@pytest.mark.parametrize('profile',PROFILES,ids=lambda p:p['version'])
@pytest.mark.parametrize('index',[0,1,2],ids=['effect-copy','effect-destroy','actor-destroy'])
def test_actual_eeex_wrapper_and_trampoline_args_returns_unwind(profile,index,windows,os_unwinder):
    entry=profile['entries'][index]
    original,_,_=execute(profile,entry,False);hooked,points,plan=execute(profile,entry,True)
    assert original==hooked
    expected=(0xCAFE0303,0xCAFE0202) if index==0 else (0xCAFE0202,)
    assert hooked[0][2]==expected
    assert [p['offset'] for p in points]==[0,3,7]
    cave,stack=0x50000000,0x20000000;allocated=[]
    try:
        for address in (cave,stack):
            assert windows.VirtualAlloc(address,0x10000,0x3000,4)==address;allocated.append(address)
        C.memmove(cave,plan['trampoline'],len(plan['trampoline']));C.memmove(cave+0x800,plan['unwind'],len(plan['unwind']))
        unwind=(C.c_uint32*3)(0,13,0x800)
        for point in points:
            C.memmove(stack,point['stack'],len(point['stack']));before=(C.c_uint64*16)(*point['regs']);after=(C.c_uint64*17)()
            assert os_unwinder(cave,cave+point['offset'],unwind,before,after)==0
            assert after[15]==stack+0x8010 and after[16]==stack+0xFFF0
            for i in (1,4,5,6,11,12,13,14):assert after[i]==0xCAFE0000+i*0x101
    finally:
        for address in reversed(allocated):assert windows.VirtualFree(address,0,0x8000)
