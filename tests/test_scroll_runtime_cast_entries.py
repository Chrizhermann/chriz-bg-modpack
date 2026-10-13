"""Eight actual cast entry prefixes, preserving state and OS unwind."""
import ctypes as C
import sys
import pytest
from test_scroll_runtime_detours import action_image,SOURCE
from test_scroll_runtime_binding import windows
from test_scroll_runtime_unwind import os_unwinder
from test_scroll_runtime_item_detours import execute
sys.path.insert(0,str(SOURCE))
import cast_entry_detours as recipes
@pytest.mark.parametrize('name',list(recipes.SITES))
def test_native_cast_entry_prefix_and_every_instruction_windows_unwind(action_image,name,windows,os_unwinder):
    original,hooked=[execute(action_image,name,value,recipes) for value in (False,True)]
    assert original['registers']==hooked['registers'] and original['flags']==hooked['flags']
    old,new=bytearray(original['stack']),bytearray(hooked['stack'])
    if hooked['plan']['frame']:
        at=hooked['registers'][15]-0x20000000;old[at:at+8]=new[at:at+8]
    assert old==new
    cave,stack=0x50000000,0x20000000;allocated=[];plan=hooked['plan']
    try:
        for at in (cave,stack):assert windows.VirtualAlloc(at,0x10000,0x3000,4)==at;allocated.append(at)
        C.memmove(cave,plan['trampoline'],len(plan['trampoline']));C.memmove(cave+0x800,plan['unwind'],len(plan['unwind']))
        rf=(C.c_uint32*3)(0,plan['instruction_size'],0x800)
        for point in hooked['points']:
            C.memmove(stack,point['stack'],len(point['stack']));before=(C.c_uint64*16)(*point['regs']);after=(C.c_uint64*17)()
            assert os_unwinder(cave,cave+point['offset'],rf,before,after)==0
            assert after[15]==stack+0x8010 and after[16]==stack+0xFFF0
            for i in (1,4,5,6,11,12,13,14):assert after[i]==0xCAFE0000+i*0x101
    finally:
        for at in reversed(allocated):assert windows.VirtualFree(at,0,0x8000)
