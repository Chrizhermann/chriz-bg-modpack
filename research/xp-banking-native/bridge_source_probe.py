"""Generate the actual banking callback assembly with pinned EEex source.

Only primitive regex/string-label providers are test doubles. GenLuaCall,
flattening, stack tracking and macro processing are the actual Lua source.
The companion CLI uses the loader's real AsmJit/AsmTK sources. No game launch.
"""
from pathlib import Path
import re
import subprocess
import struct
import json
from lupa.lua52 import LuaRuntime
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
from unicorn import x86_const as x
import capstone

ROOT=Path(__file__).resolve().parent
SOURCE=Path('C:/tmp/scroll-hook-research-20261009/EEex/EEex/copy/EEex_scripts')
BUILD=Path('C:/tmp/campaign-xp-banking-20261009/bridge')


def generate(corrected=True):
    lua=LuaRuntime(unpack_returned_tuples=True)
    g=lua.globals()
    def iterate(text,pattern,callback):
        for match in re.finditer(pattern,text,re.MULTILINE):
            groups=lua.table_from({i:s for i,s in enumerate(match.groups(),1) if s is not None})
            result=callback(match.start()+1,match.end(),match.group(),groups)
            if result:break
    g.EEex_IterateRegex=iterate
    g.EEex_GetPatternMap=lambda:lua.table()
    g.EEex_DoFile=lambda name:lua.execute((SOURCE/(name+'.lua')).read_text())
    lua.execute('''
        EEex_Architecture='x86-64';EEex_Error=error
        function EEex_ToDecStr(n) return string.format('%.0f',n) end
        function EEex_GetDebugAssembly() return false end
    ''')
    lua.execute((SOURCE/'EEex_Assembly.lua').read_text())
    # The address/string allocation primitive has no bearing on call ABI.
    labels={};strings={}
    def label(name):
        if name not in labels:labels[name]=0x500000+len(labels)*0x100
        return labels[name]
    def string(value):
        if value not in strings:strings[value]=0x600000+len(strings)*0x100
        return strings[value]
    g.EEex_WriteStringCache=string
    g.EEex_Label=label
    g.EEex_TryLabel=label
    sources={}
    callbacks=(lua.execute((ROOT/'callback_abi.lua').read_text()) if corrected
        else lua.table_from({'GenLuaCall':g.EEex_GenLuaCall}))
    for name,module,method,args in [
        ('cap','cap_hook.lua','assembly',()),
        ('reset','reset_hooks.lua','CallbackAssembly',('CBMBank_PrepareDual','_cbmr_prepare')),
        ('preview','reset_hooks.lua','CallbackAssembly',('CBMBank_CaptureDualPreview','_cbmr_preview')),
        ('award','award_hooks.lua','CallbackAssembly',('CBMBank_BeforeAward','_cbma_before',True)),
        ('writer','writer_hooks.lua','CallbackAssembly',('CBMBank_BeforeWrite','_cbmw_before',True)),
        ('writer_complete','writer_hooks.lua','CallbackAssembly',('CBMBank_CompleteWrite','_cbmw_complete',False)),
        ('manual','dual_manual_hooks.lua','CallbackAssembly',('CBMDManualBegin','_cbmd_Begin')),
        ('entry_eligible','dual_entry_hooks.lua','CallbackAssembly',('CBMDOldEligible','_cbmd_Eligible')),
        ('entry_route','dual_entry_hooks.lua','CallbackAssembly',('CBMDOldRoute','_cbmd_Route')),
    ]:
        mod=lua.execute((ROOT/module).read_text())
        generated=mod[method](*args,callbacks)
        text,state=g.EEex_PreprocessAssembly(generated)
        assert '#' not in text,text
        path=BUILD/(('' if corrected else 'uncorrected-')+name+'.asm')
        path.write_text(text+('\nint3 ; fixture end of inline callback\n' if name=='cap' else ''))
        sources[name]=path
    return sources,labels,strings


def main():
    BUILD.mkdir(parents=True,exist_ok=True)
    raw_sources,raw_labels,raw_strings=generate(False)
    raw=raw_sources['reset'];binary=raw.with_suffix('.bin')
    subprocess.run([str(BUILD/'bridge_assembler.exe'),str(raw),str(binary),'0x100000'],check=True)
    try:
        execute('reset',binary.read_bytes(),raw_labels,raw_strings,False,1)
    except AssertionError as why:
        assert 'ctx is not initialized' in str(why),why
        negative_control=str(why)
    else:
        raise AssertionError('Pinned uncorrected generator unexpectedly passed; review source change')
    sources,labels,strings=generate()
    evidence=[]
    for name,path in sources.items():
        output=path.with_suffix('.bin')
        subprocess.run([str(BUILD/'bridge_assembler.exe'),str(path),str(output),'0x100000'],check=True)
        assert output.stat().st_size>0
        for failure in (False,True):
            for returned in ((1,2) if name in ('award','writer','manual') else (0,1,-1) if name.startswith('entry_') else (1,)):
                evidence.append(execute(name,output.read_bytes(),labels,strings,failure,returned))
    report={'actual_source_assembly_cases':len(evidence),'cases':evidence,
        'provider_API_calls':'Win64 ABI stubs including volatile/home-space clobbers, not an engine Lua host',
        'stack_initialized':'nonzero poison; continuation arguments checked at native six-argument offsets',
        'uncorrected_generator_negative_control':negative_control,
        'game_launched':False}
    (BUILD/'bridge-check-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


def execute(name,code,labels,strings,failure,returned):
    uc=Uc(UC_ARCH_X86,UC_MODE_64)
    for at,size in ((0x100000,0x10000),(0x200000,0x20000),(0x500000,0x10000),(0x600000,0x10000)):
        uc.mem_map(at,size)
    uc.mem_write(0x100000,code)
    # Zero-filled emulator memory would hide uninitialized stack arguments.
    uc.mem_write(0x200000,b'\xa5'*0x20000)
    for address in labels.values():uc.mem_write(address,b'\xc3')
    for value,address in strings.items():uc.mem_write(address,value.encode()+b'\0')
    top=0x210000 if name=='cap' else 0x210008
    stop=0x10f000
    if name=='cap':
        # Inline AfterCall body exits at its exact end, before native tail.
        stop=next(i.address for i in capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64).disasm(code,0x100000)
            if i.mnemonic=='int3')
    else:uc.mem_write(top,struct.pack('<Q',stop))
    def get(reg):return uc.reg_read(reg)
    def put(reg,value):uc.reg_write(reg,value)
    nonvolatile=[x.UC_X86_REG_RBX,x.UC_X86_REG_RBP,x.UC_X86_REG_RSI,x.UC_X86_REG_RDI,
        x.UC_X86_REG_R12,x.UC_X86_REG_R13,x.UC_X86_REG_R14,x.UC_X86_REG_R15]
    initial={reg:0x710000+index*0x100 for index,reg in enumerate(nonvolatile)}
    actor,effect,cap,newclass=0x710000,0x730000,8000000,4
    for reg,value in initial.items():put(reg,value)
    put(x.UC_X86_REG_RSP,top);put(x.UC_X86_REG_RAX,cap)
    put(x.UC_X86_REG_RCX,actor);put(x.UC_X86_REG_RDX,effect if name=='award' else newclass)
    reverse={v:k for k,v in labels.items()};pushed=[];calls=[];seen_result=None
    expected_fn={'cap':'CBMBank_BeforeNativeClamp','reset':'CBMBank_PrepareDual',
        'preview':'CBMBank_CaptureDualPreview','award':'CBMBank_BeforeAward',
        'writer':'CBMBank_BeforeWrite','writer_complete':'CBMBank_CompleteWrite',
        'manual':'CBMDManualBegin','entry_eligible':'CBMDOldEligible','entry_route':'CBMDOldRoute'}[name]
    expected_args=([actor] if name.startswith(('writer','entry_')) or name=='manual' else [actor,cap] if name=='cap'
        else [actor,effect if name=='award' else newclass])
    def hook(_uc,address,_size,_data):
        nonlocal seen_result
        provider=reverse.get(address)
        if provider is None:return
        calls.append(provider)
        assert get(x.UC_X86_REG_RSP)%16==8,(name,provider,'unaligned Win64 call')
        assert get(x.UC_X86_REG_RCX)==labels['Hardcoded_InternalLuaState'],(name,provider)
        output=0
        if provider=='Hardcoded_lua_getglobal':
            assert get(x.UC_X86_REG_RDX) in (strings['debug'],strings[expected_fn])
        elif provider in ('Hardcoded_tolua_pushusertype','Hardcoded_lua_pushinteger'):
            value=get(x.UC_X86_REG_RDX);pushed.append(value)
            if provider=='Hardcoded_tolua_pushusertype':
                typename='CGameEffect' if value==effect else 'CGameSprite'
                assert get(x.UC_X86_REG_R8)==strings[typename]
        elif provider=='Hardcoded_lua_pcallk':
            assert pushed==expected_args,(name,pushed,expected_args)
            assert get(x.UC_X86_REG_RDX)==len(expected_args)
            assert get(x.UC_X86_REG_R8)==(0 if name=='cap' else 1)
            assert get(x.UC_X86_REG_R9)==(-2-len(expected_args))&0xffffffffffffffff
            rsp=get(x.UC_X86_REG_RSP)
            # Callee RSP includes its return address and the caller supplies
            # 32 bytes of register home space. ctx/k are arguments five/six.
            assert struct.unpack('<Q',uc.mem_read(rsp+40,8))[0]==0,(name,'ctx is not initialized')
            assert struct.unpack('<Q',uc.mem_read(rsp+48,8))[0]==0,(name,'continuation is not null')
        elif provider=='EEex_CheckCallError':output=int(failure)
        elif provider in ('Hardcoded_lua_toboolean','Hardcoded_lua_tointegerx'):
            assert not failure;output=returned;seen_result=returned
            if provider=='Hardcoded_lua_tointegerx':assert get(x.UC_X86_REG_R8)==0
        # The native callee owns every register-home slot, even when this
        # particular provider implementation happens not to use them.
        uc.mem_write(get(x.UC_X86_REG_RSP)+8,b'\x5a'*32)
        # Deliberately clobber every volatile GPR, as any native provider may.
        for index,reg in enumerate((x.UC_X86_REG_RAX,x.UC_X86_REG_RCX,x.UC_X86_REG_RDX,
            x.UC_X86_REG_R8,x.UC_X86_REG_R9,x.UC_X86_REG_R10,x.UC_X86_REG_R11)):
            put(reg,0xdead0000+index)
        put(x.UC_X86_REG_RAX,output & 0xffffffffffffffff)
    uc.hook_add(UC_HOOK_CODE,hook)
    uc.emu_start(0x100000,stop,count=1000)
    assert get(x.UC_X86_REG_RIP)==stop
    assert all(get(r)==v for r,v in initial.items()),(name,'nonvolatile register lost')
    assert get(x.UC_X86_REG_RSP)==top+(0 if name=='cap' else 8),(name,'stack not restored')
    error_value=-1 if name=='manual' or name.startswith('entry_') else 0
    assert get(x.UC_X86_REG_RAX)==((cap if name=='cap' else error_value if failure else returned)&0xffffffffffffffff)
    assert pushed==expected_args
    return {'callback':name,'protected_error':failure,'result':get(x.UC_X86_REG_RAX),
        'provider_calls':len(calls),'volatile_clobbers':True,'actual_source':True}


if __name__=='__main__':main()
