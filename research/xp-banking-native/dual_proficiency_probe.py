"""Offline real native proficiency binding check. Never launches a game.

The compiled CBMDP_GetSlots wrapper and native calculation/class-level/table
instructions run in Unicorn. Only environmental boundaries are substituted:
thread token, object-array lookup, CString allocation/copy/uppercase/destruction,
CRT comparison/sscanf. Their arguments and class selection are checked.
"""
import os
import argparse
import ctypes
import hashlib
import json
import re
import struct
import threading
from collections import deque
from pathlib import Path

import capstone
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.x86_const import *

ROOT = Path(__file__).parent
SOURCE = Path('C:/tmp/scroll-hook-research-20261009/EEex/EEex/loader')
EXES = {
    # Local game folders: set BG2EE_266_ROOT and BG2EE_273_ROOT.
    '2.6.6.0': Path(os.path.expandvars("%BG2EE_266_ROOT%/Baldur.exe")),
    '2.7.3.0': Path(os.path.expandvars("%BG2EE_273_ROOT%/Baldur.exe")),
}
SHAS = {
    '2.6.6.0': 'fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580',
    '2.7.3.0': 'b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57',
}
FUNCTIONS = ['CRuleTables::GetProficiencySlots', 'CAIObjectType::GetActiveInactiveClasses',
             'CGameAnimationType::GetMoveScale', 'CDerivedStats::GetLevel',
             'CRuleTables::GetClassString', 'CString::~CString', 'C2DArray::GetAt',
             'CDerivedStats::GetLevelField','CRuleTables::GetClassProficiency',
             'CRuleTables::GetProficiencyClassIndex','CRuleTables::GetMaximumProficiency',
             'CRuleTables::GetThiefSkillsLevelUp','CRuleTables::GetHPCONBonus',
             'CRuleTables::RollHitPoints@class','CGameSprite::SetSkillValue',
             'CAIObjectType::IsUsableSubClass','CRuleTables::GetNextLevelSubClass','CDerivedStats::SetLevel']

def fnv(data):
    n = 14695981039346656037
    for b in data:
        n = ((n ^ b) * 1099511628211) & 0xffffffffffffffff
    return n

def load(version):
    data = EXES[version].read_bytes()
    assert hashlib.sha256(data).hexdigest() == SHAS[version]
    pe = pefile.PE(data=data)
    base = pe.OPTIONAL_HEADER.ImageBase
    names = {}
    for line in (SOURCE/('v'+version)/'bg2ee/function_names.db').read_text().splitlines():
        address, _, name = line.partition('\t')
        if address.startswith('0x'):
            names[int(address, 16)] = name
    by_name = {}
    for at,name in names.items(): by_name.setdefault(name,at)
    rolls=sorted(at for at,name in names.items() if name=='CRuleTables::RollHitPoints')
    assert len(rolls)==2
    by_name['CRuleTables::RollHitPoints@class']=rolls[1]
    keys = sorted(names)
    spans = []
    for name in FUNCTIONS:
        at = by_name[name]
        end = keys[keys.index(at)+1]
        code = pe.get_data(at-base, end-at)
        spans.append(dict(name=name, rva=at-base, size=end-at, fnv64=fnv(code),
                          sha256=hashlib.sha256(code).hexdigest()))
    skill=pe.get_data(by_name['CRuleTables::GetThiefSkillsLevelUp']-base,0x110)
    assert bytes.fromhex('488d8f38320000') in skill  # native THIEFSKL table
    md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);md.detail=True
    literals=[]
    for ins in md.disasm(skill,by_name['CRuleTables::GetThiefSkillsLevelUp']):
        if ins.mnemonic=='lea' and ins.op_str.startswith('rdx, [rip'):
            addr=ins.address+ins.size+ins.operands[1].mem.disp
            literals.append(pe.get_string_at_rva(addr-base))
    assert b'LEVEL_POINTS' in literals
    return pe, by_name, spans

def generate():
    lines=['// Generated audited instruction spans, not redistributable game code.',
           'static constexpr Build builds[] = {']
    manifests=[]
    for version in EXES:
        pe, names, spans = load(version)
        lines.append(f'    {{0x{pe.OPTIONAL_HEADER.SizeOfImage:x}, {{ // {version}')
        for s in spans:
            lines.append(f'        {{0x{s["rva"]:x},0x{s["size"]:x},0x{s["fnv64"]:016x}ULL}}, // {s["name"]}')
        lines.append('    }},')
        manifests.append(dict(version=version, exe_sha256=SHAS[version], functions=spans))
    lines.append('};')
    (ROOT/'dual_native_proficiency_builds.inc').write_text('\n'.join(lines)+'\n')
    (ROOT/'dual-proficiency-signatures.json').write_text(json.dumps(manifests,indent=2)+'\n')

def cstring(uc, at):
    text=bytearray()
    for i in range(256):
        b=uc.mem_read(at+i,1)[0]
        if not b: return bytes(text)
        text.append(b)
    raise AssertionError('unbounded string')

def run(dll_path):
    dll=ctypes.CDLL(str(dll_path))
    dll.CBMDP_Bind.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_void_p)]
    dll.CBMDP_Bind.restype=ctypes.c_int
    dll.CBMDP_Destroy.argtypes=[ctypes.c_void_p]
    dll.CBMDP_Destroy.restype=ctypes.c_int
    dll.CBMDP_GetSlots.argtypes=[ctypes.c_void_p]*5+[ctypes.c_uint8,ctypes.c_uint8,ctypes.c_void_p]
    dll.CBMDP_GetSlots.restype=ctypes.c_int
    dll.CBMDP_GetChoiceCap.argtypes=[ctypes.c_void_p]*4+[ctypes.c_uint8]*2+[ctypes.c_uint32]*2+[ctypes.c_void_p]
    dll.CBMDP_GetChoiceCap.restype=ctypes.c_int
    dll.CBMDP_GetSkillBudget.argtypes=[ctypes.c_void_p]*5+[ctypes.c_uint8]*2+[ctypes.c_uint32,ctypes.c_void_p]
    dll.CBMDP_GetSkillBudget.restype=ctypes.c_int
    dll.CBMDP_RollOldHP.argtypes=[ctypes.c_void_p]*5+[ctypes.c_uint8]*2+[ctypes.c_uint32,ctypes.c_uint8,ctypes.c_void_p]
    dll.CBMDP_RollOldHP.restype=ctypes.c_int
    dll.CBMDP_ApplyOldSkills.argtypes=[ctypes.c_void_p]*5+[ctypes.c_uint8]*2+[ctypes.c_uint32,ctypes.c_void_p,ctypes.c_void_p]
    dll.CBMDP_ApplyOldSkills.restype=ctypes.c_int
    dll.CBMDP_GetOldTarget.argtypes=[ctypes.c_void_p]*4+[ctypes.c_uint8]*2+[ctypes.c_uint32,ctypes.c_void_p]
    dll.CBMDP_GetOldTarget.restype=ctypes.c_int
    dll_pe=pefile.PE(str(dll_path))
    dll_base=dll_pe.OPTIONAL_HEADER.ImageBase
    exports={s.name.decode():s.address for s in dll_pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name}
    # Thread-token boundary is a named internal symbol from this compilation.
    maptext=dll_path.with_suffix('.map').read_text()
    match=re.search(r'\bCBMDP_ThreadToken\s+([0-9a-fA-F]+)',maptext)
    assert match, 'MSVC map must retain the thread boundary'
    token_addr=int(match.group(1),16)
    results=[]
    for version in EXES:
        pe,names,spans=load(version)
        base=pe.OPTIONAL_HEADER.ImageBase
        mapped=pe.get_memory_mapped_image().ljust(pe.OPTIONAL_HEADER.SizeOfImage,b'\0')
        image=ctypes.create_string_buffer(mapped)
        binding=ctypes.c_void_p()
        assert dll.CBMDP_Bind(image,len(mapped),ctypes.byref(binding))==0
        imageptr,buildptr,owner=struct.unpack('<QQQ',ctypes.string_at(binding,24))
        buildrva=buildptr-dll._handle
        assert 0<=buildrva<dll_pe.OPTIONAL_HEADER.SizeOfImage
        wrong=[]
        def foreign_thread():
            other=ctypes.c_void_p();result=ctypes.create_string_buffer(16)
            wrong.append(dll.CBMDP_Bind(image,len(mapped),ctypes.byref(other)))
            wrong.append(dll.CBMDP_GetSlots(binding,1,1,1,1,1,2,result))
            wrong.append(dll.CBMDP_GetChoiceCap(binding,1,1,1,1,2,0x4000,89,result))
            wrong.append(dll.CBMDP_GetSkillBudget(binding,1,1,1,1,1,2,0x4000,result))
            wrong.append(dll.CBMDP_RollOldHP(binding,1,1,1,1,1,2,0x4000,18,result))
            wrong.append(dll.CBMDP_ApplyOldSkills(binding,1,1,1,1,1,2,0x4000,result,result))
            wrong.append(dll.CBMDP_GetOldTarget(binding,1,1,1,1,2,123,result))
            wrong.append(dll.CBMDP_Destroy(binding))
        worker=threading.Thread(target=foreign_thread);worker.start();worker.join()
        assert wrong==[3]*8,wrong
        # Changed executable must be rejected before the invalid dummy native
        # pointers can be dereferenced, also on an already-bound context.
        image[spans[0]['rva']]=bytes([mapped[spans[0]['rva']] ^ 1])
        assert dll.CBMDP_GetSlots(binding,1,1,1,1,1,2,ctypes.create_string_buffer(16))==2
        image[spans[0]['rva']]=bytes([mapped[spans[0]['rva']]])
        assert dll.CBMDP_Destroy(binding)==0
        # Unknown/modified executable code cannot call into the native engine.
        altered=bytearray(mapped); altered[spans[0]['rva']]^=1
        changed=ctypes.create_string_buffer(bytes(altered))
        assert dll.CBMDP_Bind(changed,len(mapped),ctypes.byref(binding))==2
        assert dll.CBMDP_Bind(image,len(mapped)-1,ctypes.byref(binding))==2
        uc=Uc(UC_ARCH_X86,UC_MODE_64)
        uc.mem_map(base,pe.OPTIONAL_HEADER.SizeOfImage)
        uc.mem_write(base,mapped)
        uc.mem_map(dll_base,dll_pe.OPTIONAL_HEADER.SizeOfImage)
        uc.mem_write(dll_base,dll_pe.get_memory_mapped_image())
        arena,stop=0x2000000,0x3000000
        uc.mem_map(arena,0x60000); uc.mem_map(stop,0x1000)
        stack=arena+0x20000
        rules,typ,before,after,actor=arena,arena+0x4000,arena+0x5000,arena+0x6000,arena+0x7000
        context,out=arena+0xc000,arena+0xc100
        heap=arena+0x10000
        q=lambda at,n:uc.mem_write(at,struct.pack('<Q',n))
        d=lambda at,n:uc.mem_write(at,struct.pack('<I',n))
        u64=lambda at:struct.unpack('<Q',uc.mem_read(at,8))[0]
        # The loader normally runs these CString global initializers. Resolve
        # their literal and destination from actual instructions, rather than
        # substituting our assumed class-to-English-name mapping.
        md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);md.detail=True
        initialized=[]
        for name,at in names.items():
            if not name.startswith("`dynamic_initializer_for_'CRuleTables::"):continue
            regs={}
            for ins in md.disasm(pe.get_data(at-base,0x25),at):
                if ins.mnemonic=='lea' and len(ins.operands)==2 and ins.operands[1].type==capstone.CS_OP_MEM and ins.operands[1].mem.base==capstone.x86.X86_REG_RIP:
                    regs[ins.reg_name(ins.operands[0].reg)]=ins.address+ins.size+ins.operands[1].mem.disp
                elif ins.mnemonic=='call':
                    if 'rcx' in regs and 'rdx' in regs:
                        literal=cstring(uc,regs['rdx'])
                        q(regs['rcx'],regs['rdx'])
                        initialized.append(dict(name=name,destination=hex(regs['rcx']),literal=literal.decode('ascii',errors='replace')))
                    break
        q(context,base);q(context+8,dll_base+buildrva);q(context+16,owner)
        q(typ+0xc,123)
        environment={names[n]:n for n in ['CGameObjectArray::GetDeny', 'CString::CString',
                'CString::operator=', 'CString::~CString','CString::MakeUpper','_mbscmp','sscanf','atoi']}
        raw_names={int(line.split('\t')[0],16):line.split('\t')[1] for line in
            (SOURCE/('v'+version)/'bg2ee/function_names.db').read_text().splitlines() if line.startswith('0x')}
        for symbol in ['CString::Format','C2DArray::Load','C2DArray::~C2DArray','__security_check_cookie','rand']:
            environment[names[symbol]]=symbol
        # Resolve the specific constructor overloads from actual higher-roll
        # call instructions (the name database has repeated C++ overload names).
        hi=names['CRuleTables::RollHitPoints@class']
        for ins in md.disasm(pe.get_data(hi-base,0x190),hi):
            if ins.mnemonic!='call' or ins.operands[0].type!=capstone.CS_OP_IMM: continue
            at=ins.operands[0].imm;symbol=raw_names.get(at)
            if symbol in ['CString::CString','CResRef::CResRef','CTlkFileOverride::CTlkFileOverride','CResRef::operator=']:
                environment[at]=symbol+' (HP overload)'
        hp_fixture=None;random_values=[];hp_loads=[];random_calls=[];hp_trace=[]
        def alloc(text):
            nonlocal heap
            at=heap; heap+=(len(text)+17)//8*8
            uc.mem_write(at,text+b'\0');return at
        recent=deque(maxlen=12)
        def hook(u,at,size,_):
            recent.append(hex(at))
            if hp_fixture is not None and at in (names['CRuleTables::RollHitPoints@class'],names['CRuleTables::RollHitPoints'],names['CRuleTables::RollHitPoints@class']+0x184,names['CRuleTables::RollHitPoints']+0x219):
                hp_trace.append((hex(at),*[u.reg_read(r) for r in (UC_X86_REG_RAX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9)]))
            if at==stop: u.emu_stop();return
            if at!=token_addr and at not in environment: return
            rcx,rdx,r8=(u.reg_read(reg) for reg in (UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8))
            result=0
            if at==token_addr: result=owner
            else:
                name=environment[at]
                if name=='CGameObjectArray::GetDeny':
                    assert rcx==123; q(rdx,actor)
                elif name in ('CString::CString','CString::operator='):
                    q(rcx,u64(rdx));result=rcx
                elif name=='CString::MakeUpper':
                    q(rcx,alloc(cstring(u,u64(rcx)).upper()))
                elif name=='CString::~CString': pass
                elif name=='_mbscmp':
                    a,b=cstring(u,rcx),cstring(u,rdx);result=(a>b)-(a<b)
                elif name=='sscanf':
                    assert cstring(u,rdx)==b'%d'
                    value=int(cstring(u,rcx));d(r8,value & 0xffffffff);result=1
                elif name=='atoi':result=int(cstring(u,rcx))
                elif name=='CString::CString (HP overload)':q(rcx,alloc(cstring(u,rdx)));result=rcx
                elif name=='CString::Format':
                    assert cstring(u,rdx)==b'%d';q(rcx,alloc(str(r8&0xffffffff).encode()))
                elif name=='CResRef::CResRef (HP overload)':
                    text=cstring(u,u64(rdx));assert 0<len(text)<=8
                    u.mem_write(rcx,text.ljust(8,b'\0'));result=rcx
                elif name in ('CTlkFileOverride::CTlkFileOverride (HP overload)','CResRef::operator= (HP overload)'):
                    u.mem_write(rcx,b'\0'*8);result=rcx
                elif name=='C2DArray::Load':
                    resource=bytes(u.mem_read(rdx,8)).rstrip(b'\0')
                    assert resource==b'CUSTOMHP',resource;hp_loads.append(resource.decode())
                    columns,rows,values=hp_fixture
                    table_fixture(rcx,columns,rows,values,arena+0xe000,default='0');result=1
                elif name=='C2DArray::~C2DArray':pass
                elif name=='__security_check_cookie':result=u.reg_read(UC_X86_REG_RAX)
                elif name=='rand':
                    assert random_values,'Unexpected native RNG consumption'
                    result=random_values.pop(0);random_calls.append(result)
            rsp=u.reg_read(UC_X86_REG_RSP)
            u.reg_write(UC_X86_REG_RAX,result & 0xffffffffffffffff)
            u.reg_write(UC_X86_REG_RIP,u64(rsp));u.reg_write(UC_X86_REG_RSP,rsp+8)
        uc.hook_add(UC_HOOK_CODE,hook)
        writes=[]
        def write(u,access,address,size,value,_):
            if any(p<=address<p+n for p,n in [(rules,0x4000),(typ,0x80),(before,0x100),(after,0x100),(actor,0x1000)]):
                writes.append((address,size))
        uc.hook_add(UC_HOOK_MEM_WRITE,write)
        # Native class routing: all dual-capable combined class IDs; both retired
        # positions, including ranger/cleric and mage/cleric/thief layouts.
        layouts=[(7,8,1,2,0x48,0x46),(7,16,2,1,0x46,0x48),
                 (9,8,4,2,0x48,0x46),(9,64,2,4,0x46,0x48),
                 (8,8,3,2,0x48,0x46),(8,32,2,3,0x46,0x48),
                 (13,16,4,1,0x48,0x46),(13,64,1,4,0x46,0x48),
                 (14,16,3,1,0x46,0x48),(14,32,1,3,0x48,0x46),
                 (15,32,4,3,0x48,0x46),(15,64,3,4,0x46,0x48),
                 (16,8,11,2,0x48,0x46),(16,128,2,11,0x46,0x48),
                 (18,32,12,3,0x48,0x46),(18,256,3,12,0x46,0x48)]
        class_names={1:'MAGE',2:'FIGHTER',3:'CLERIC',4:'THIEF',11:'DRUID',12:'RANGER'}
        cases=[]
        def execute(layout,lo,hi,rate='3',first='4',invalid=None):
            nonlocal heap
            heap=arena+0x10000
            overall,flags,active,old,active_off,old_off=layout
            uc.mem_write(typ,b'\0'*0x80);uc.mem_write(typ+0xb,bytes([overall]));d(typ+0xc,123)
            uc.mem_write(actor,b'\0'*0x1000);d(actor+0x568,flags)
            uc.mem_write(before,b'\xa5'*0x100);uc.mem_write(after,b'\xa5'*0x100)
            for ptr in before,after:
                uc.mem_write(ptr+0x46,b'\x03\xa5\x03\xa5\x03')
                uc.mem_write(ptr+active_off,b'\x0c')
            uc.mem_write(before+old_off,bytes([lo]));uc.mem_write(after+old_off,bytes([hi]))
            if invalid=='projection':uc.mem_write(after+active_off,b'\x0d')
            columns=['UNRELATED','RATE','FIRST_LEVEL']
            rows=['UNUSED',class_names[old],'FIGHTER_MAGE_THIEF']
            cells=[['17','71','9'],['99',rate,first],['7','8','9']]
            if invalid in ('missing','default'): rows[1]='OTHER'
            if invalid=='duplicate':rows.append(rows[1]);cells.append(cells[1])
            table=rules+0x118
            colptr,rowptr,cellptr=rules+0x1000,rules+0x1100,rules+0x1200
            for i,text in enumerate(columns):q(colptr+8*i,alloc(text.encode()))
            for i,text in enumerate(rows):q(rowptr+8*i,alloc(text.encode()))
            for i,row in enumerate(cells):
                for j,text in enumerate(row):q(cellptr+8*(i*len(columns)+j),alloc(text.encode()))
            q(table+0x10,colptr);q(table+0x18,rowptr);q(table+0x20,cellptr);q(table+0x28,alloc(b'5' if invalid=='default' else b'0'))
            uc.mem_write(table+0x30,struct.pack('<hh',len(columns),len(rows)))
            uc.mem_write(out,b'\xcc'*16)
            saved=[bytes(uc.mem_read(p,n)) for p,n in [(rules,0x2000),(typ,0x80),(before,0x100),(after,0x100),(actor,0x1000)]]
            writes.clear()
            rsp=stack+0x8000-8;q(rsp,stop)
            for off,value in [(0x28,after),(0x30,active),(0x38,old),(0x40,out)]:q(rsp+off,value)
            for reg,value in [(UC_X86_REG_RSP,rsp),(UC_X86_REG_RCX,context),(UC_X86_REG_RDX,rules),
                              (UC_X86_REG_R8,typ),(UC_X86_REG_R9,before)]:uc.reg_write(reg,value)
            try:
                uc.emu_start(dll_base+exports['CBMDP_GetSlots'],stop,count=1000000)
            except Exception:
                print('emulation failure',recent,'regs',[(r,hex(uc.reg_read(r))) for r in (UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_RAX,UC_X86_REG_RIP)])
                raise
            status=uc.reg_read(UC_X86_REG_RAX)&0xffffffff
            assert not writes, writes
            assert saved==[bytes(uc.mem_read(p,n)) for p,n in [(rules,0x2000),(typ,0x80),(before,0x100),(after,0x100),(actor,0x1000)]]
            if invalid=='projection' or hi<lo: assert status==6,status
            elif invalid=='missing' or rate in ('0','-1','bogus','3x','2147483648'):
                assert status==5,(status,invalid,rate)
                assert bytes(uc.mem_read(out,16))==b'\xcc'*16
            else:
                assert status==0,(version,layout,lo,hi,rate,status)
                picks,first_n,rate_n,a,o,l,h=struct.unpack('<IIIBBBB',uc.mem_read(out,16))
                if invalid=='default': first=rate='5'
                expected=int(first) if lo==0 and hi==1 else hi//int(rate)-lo//int(rate)
                assert (picks,first_n,rate_n,a,o,l,h)==(expected,int(first),int(rate),active,old,lo,hi)
            cases.append(dict(overall=overall,old=old,lo=lo,hi=hi,rate=rate,status=status))
        for layout in layouts:
            for lo,hi in [(0,1),(7,8),(8,9),(9,15),(15,15),(254,255)]:
                for rate in ['1','3','4','7','255']:
                    execute(layout,lo,hi,rate,first='6')
        for rate in ['0','-1','bogus','3x','2147483648']:
            execute(layouts[0],8,9,rate)
        for invalid in ['missing','duplicate','default','projection']:
            execute(layouts[0],8,9,invalid=invalid)
        execute(layouts[0],9,8)
        execute(layouts[0],8,9,rate=' +3 ')
        caps=[]
        def table_fixture(at,columns,rows,values,storage,default='0'):
            colptr=storage;rowptr=storage+len(columns)*8;cellptr=rowptr+len(rows)*8
            for i,s in enumerate(columns):q(colptr+8*i,alloc(s.encode()))
            for i,s in enumerate(rows):q(rowptr+8*i,alloc(s.encode()))
            for i,row in enumerate(values):
                for j,s in enumerate(row):q(cellptr+8*(i*len(columns)+j),alloc(str(s).encode()))
            q(at+0x10,colptr);q(at+0x18,rowptr);q(at+0x20,cellptr);q(at+0x28,alloc(default.encode()))
            uc.mem_write(at+0x30,struct.pack('<hh',len(columns),len(rows)))
        for layout in layouts:
            for selected_column in [2,7,31]:
              for limit in [-1,0,5]:
                execute(layout,8,9)
                overall,flags,active,old,active_off,old_off=layout
                # WEAPPROF order/stat IDs and KITLIST column mapping are supplied
                # by this synthetic installed table, not assumed by the wrapper.
                values=[[114]+[0]*39,[89]+[0]*39,[134]+[0]*39]
                values[0][selected_column]=limit
                table_fixture(rules+0x1998,['ID']+[f'C{i}' for i in range(1,40)],
                    ['STYLE','WEAPON','EXTRA'],values,rules+0x2800)
                kit=[0]*8;kit[5]=selected_column;kit[7]=old
                table_fixture(rules+0x2610,[str(i) for i in range(8)],['NONE','CUSTOM'],
                    [[0]*8,kit],rules+0x3300)
                table_fixture(rules+0x150,['FIRST_LEVEL','OTHER','6','9','255'],
                    ['UNRELATED',class_names[old]],[[1]*5,[1,2,3,4,5]],rules+0x3500)
                uc.mem_write(out,b'\xcc'*16)
                saved=bytes(uc.mem_read(rules,0x8000));writes.clear()
                rsp=stack+0x8000-8;q(rsp,stop)
                for off,value in [(0x28,active),(0x30,old),(0x38,0x4001),(0x40,114),(0x48,out)]:q(rsp+off,value)
                for reg,value in [(UC_X86_REG_RSP,rsp),(UC_X86_REG_RCX,context),
                    (UC_X86_REG_RDX,rules),(UC_X86_REG_R8,typ),(UC_X86_REG_R9,after)]:uc.reg_write(reg,value)
                uc.emu_start(dll_base+exports['CBMDP_GetChoiceCap'],stop,count=1000000)
                status=uc.reg_read(UC_X86_REG_RAX)&0xffffffff
                assert status==0,(version,layout,selected_column,status,recent)
                actual=struct.unpack('<iiI',uc.mem_read(out,12))
                assert actual==(limit,4,max(0,min(limit,4))),actual
                assert not writes and saved==bytes(uc.mem_read(rules,0x8000))
                caps.append(dict(old=old,column=selected_column,kit=0x4001,stat=114,
                                 weapon_limit=limit,level_limit=4,effective=max(0,min(limit,4))))
        skills_results=[]
        for layout in layouts:
          for per_level in [0,15,20,25,37]:
            execute(layout,8,11)
            overall,flags,active,old,active_off,old_off=layout
            kit=['CUSTOM_OLD',0,0,0,0,7,0,old]
            table_fixture(rules+0x2610,[str(i) for i in range(8)],['NONE','CUSTOM'],
                [[0]*8,kit],rules+0x3300)
            table_fixture(rules+0x3238,['START_POINTS','LEVEL_POINTS','UNRELATED'],
                ['UNUSED','CUSTOM_OLD'],[[9,99,1],[40,per_level,7]],rules+0x3500)
            uc.mem_write(out,b'\xcc'*16)
            saved=bytes(uc.mem_read(rules,0x8000));writes.clear()
            rsp=stack+0x8000-8;q(rsp,stop)
            for off,value in [(0x28,after),(0x30,active),(0x38,old),(0x40,0x4001),(0x48,out)]:q(rsp+off,value)
            for reg,value in [(UC_X86_REG_RSP,rsp),(UC_X86_REG_RCX,context),
                (UC_X86_REG_RDX,rules),(UC_X86_REG_R8,typ),(UC_X86_REG_R9,before)]:uc.reg_write(reg,value)
            uc.emu_start(dll_base+exports['CBMDP_GetSkillBudget'],stop,count=1000000)
            status=uc.reg_read(UC_X86_REG_RAX)&0xffffffff
            assert status==0,(version,layout,per_level,status,recent)
            actual=struct.unpack('<III',uc.mem_read(out,12))
            assert actual==(per_level,3,per_level*3),actual
            assert not writes and saved==bytes(uc.mem_read(rules,0x8000))
            skills_results.append(dict(old=old,kit=0x4001,per_level=per_level,gained=3,points=per_level*3))
        hp_results=[]
        # Resolve the actual global chitin pointer read by the lower native HP
        # routine. Only game options/CRT RNG/resource I/O are environmental stubs.
        core=names['CRuleTables::RollHitPoints']
        instructions=list(md.disasm(pe.get_data(core-base,0x220),core))
        globals_at=[]
        for i,ins in enumerate(instructions):
            if ins.mnemonic=='mov' and ins.op_str=='rcx, qword ptr [rax + 0x1090]':
                prev=next(x for x in reversed(instructions[:i]) if x.mnemonic=='mov' and x.op_str.startswith('rax, qword ptr [rip'))
                globals_at.append(prev.address+prev.size+prev.operands[1].mem.disp)
        assert len(globals_at)==1
        chitin,game=arena+0x30000,arena+0x38000
        q(globals_at[0],chitin);q(chitin+0x1090,game)
        target_results=[]
        for layout in layouts:
          for variation,xp,prior,target in [('below',999,8,8),('equal',1000,8,9),
             ('between',1699,8,10),('several',1700,8,11),('terminal',999999,8,12),
             ('beyond40',1700,41,44),('byte255',1700,253,255),('nonterminal-wrap',1700,253,None),
             ('malformed',1700,8,None)]:
            execute(layout,prior,prior)
            overall,flags,active,old,active_off,old_off=layout
            columns=[str(prior+4),str(prior+1),'77',str(prior+3),str(prior+2)]
            values=[9999,1000,4,1700,1500]
            if variation=='byte255':columns=['254','255'];values=[1000,1500]
            if variation=='nonterminal-wrap':columns=['254','255'];values=[1000,1500]
            if variation=='malformed':values[1]='bad'
            table_fixture(rules+0x9a0,columns,['UNRELATED',class_names[old]],
                [[8]*len(columns),values],rules+0x3500,default='0' if variation=='nonterminal-wrap' else '-1')
            saved=bytes(uc.mem_read(rules,0x8000));writes.clear();uc.mem_write(out,b'\xcc'*8)
            rsp=stack+0x8000-8;q(rsp,stop)
            for off,value in [(0x28,active),(0x30,old),(0x38,xp),(0x40,out)]:q(rsp+off,value)
            for reg,value in [(UC_X86_REG_RSP,rsp),(UC_X86_REG_RCX,context),
                (UC_X86_REG_RDX,rules),(UC_X86_REG_R8,typ),(UC_X86_REG_R9,before)]:uc.reg_write(reg,value)
            uc.emu_start(dll_base+exports['CBMDP_GetOldTarget'],stop,count=1000000)
            status=uc.reg_read(UC_X86_REG_RAX)&0xffffffff
            assert status==(5 if target is None else 0),(version,layout,variation,status,recent)
            if target is not None:assert struct.unpack('<IBBBB',uc.mem_read(out,8))==(xp,prior,target,active,old)
            else:assert bytes(uc.mem_read(out,8))==b'\xcc'*8
            assert not writes and saved==bytes(uc.mem_read(rules,0x8000))
            target_results.append(dict(old=old,variation=variation,old_usable_xp=xp,before=prior,target=target,status=status))
            if variation=='several':
                kit=['CUSTOM_OLD',0,0,0,0,7,0,old]
                table_fixture(rules+0x2610,[str(i) for i in range(8)],['NONE','CUSTOM'],[[0]*8,kit],rules+0x3300)
                table_fixture(rules+0x3238,['OTHER','LEVEL_POINTS'],['UNUSED','CUSTOM_OLD'],[[9,99],[0,25]],rules+0x3600)
                table_fixture(rules+0x1998,['ID']+[f'C{i}' for i in range(1,10)],['WEAPON'],[[89]+[4]*9],rules+0x2800)
                # MAXPROFS intentionally reserves FIRST_LEVEL/OTHER and its
                # final column. Native scanning starts at index2 and excludes
                # the last column; a three-column table uses OTHER, not11.
                table_fixture(rules+0x150,['FIRST_LEVEL','OTHER','9','11','255'],['UNRELATED',class_names[old]],[[1]*5,[1,2,4,5,6]],rules+0x3700)
                for symbol in ('CBMDP_GetOldPlan','CBMDP_GetOldCap'):
                    saved=bytes(uc.mem_read(rules,0x8000));writes.clear();uc.mem_write(out,b'\xcc'*16)
                    rsp=stack+0x8000-8;q(rsp,stop)
                    args=[active,old,xp,0x4001]+([89] if symbol.endswith('Cap') else [])+[out]
                    for i,value in enumerate(args):q(rsp+0x28+i*8,value)
                    for reg,value in [(UC_X86_REG_RSP,rsp),(UC_X86_REG_RCX,context),
                        (UC_X86_REG_RDX,rules),(UC_X86_REG_R8,typ),(UC_X86_REG_R9,before)]:uc.reg_write(reg,value)
                    uc.emu_start(dll_base+exports[symbol],stop,count=2000000)
                    result=uc.reg_read(UC_X86_REG_RAX)&0xffffffff
                    assert result==0,(version,layout,symbol,result,recent)
                    if symbol.endswith('Plan'):assert struct.unpack('<IBBBBII',uc.mem_read(out,16))==(1700,8,11,active,old,1,75)
                    else:
                        actual=struct.unpack('<iiI',uc.mem_read(out,12));assert actual==(4,5,4),(version,layout,symbol,actual)
                    assert not writes and saved==bytes(uc.mem_read(rules,0x8000))
                    target_results.append(dict(old=old,variation=symbol,status=result))
        for i,ins in enumerate(instructions):
            if ins.mnemonic=='cmp' and ins.op_str=='byte ptr [rax + 0x2c9], 1':
                prev=next(x for x in reversed(instructions[:i]) if x.mnemonic=='mov' and x.op_str.startswith('rax, qword ptr [rip'))
                q(prev.address+prev.size+prev.operands[1].mem.disp,chitin)
        for layout in layouts:
          for maximum in (0,1):
           for sides,rolls,modifier,minimum in [(10,1,0,1),(4,2,9,3),(0,0,3,1),(12,1,0,5)]:
            execute(layout,8,11)
            overall,flags,active,old,active_off,old_off=layout
            kit=['CUSTOM_OLD',0,0,0,0,7,0,old]
            table_fixture(rules+0x2610,[str(i) for i in range(8)],['NONE','CUSTOM'],[[0]*8,kit],rules+0x3300)
            table_fixture(rules+0x578,['UNRELATED','TABLE'],['UNUSED','CUSTOM_OLD'],
                [['OTHERHP','NOPE'],['OTHERHP','CUSTOMHP']],rules+0x3400)
            table_fixture(rules+0x5b0,['MIN_ROLL','WARRIOR','OTHER'],['3','18','25'],
                [[minimum,2,-1],[minimum,4,2],[minimum,7,3]],rules+0x3500)
            table_fixture(rules+0x9a0,['11','9','10'],[class_names[old]],[[1700,1000,1500]],rules+0x3600,default='-1')
            # Alternate order plus unrelated columns/rows; real GetAt selects
            # ROLLS/SIDES/MODIFIER and each decimal level, including fixed gains.
            hp_fixture=(['UNRELATED','MODIFIER','ROLLS','SIDES'],['11','9','77','10'],
                [[99,modifier,rolls,sides],[99,modifier,rolls,sides],[7,40,8,100],[99,modifier,rolls,sides]])
            d(game+0x7ec0,maximum);d(game+0x7d48,0);d(game+0x7d4c,0)
            random_values[:]=[1,2]*rolls*3 if not maximum else []
            random_calls.clear();hp_loads.clear();hp_trace.clear()
            uc.mem_write(out,b'\xcc'*2056)
            saved=bytes(uc.mem_read(rules,0x8000));writes.clear()
            rsp=stack+0x8000-8;q(rsp,stop)
            symbol='CBMDP_RollOldPlan' if maximum else 'CBMDP_RollOldHP'
            args=[active,old,1700,0x4001,18,out] if maximum else [after,active,old,0x4001,18,out]
            for i,value in enumerate(args):q(rsp+0x28+i*8,value)
            for reg,value in [(UC_X86_REG_RSP,rsp),(UC_X86_REG_RCX,context),
                (UC_X86_REG_RDX,rules),(UC_X86_REG_R8,typ),(UC_X86_REG_R9,before)]:uc.reg_write(reg,value)
            try:uc.emu_start(dll_base+exports[symbol],stop,count=2000000)
            except Exception:
                print('HP failure',version,layout,maximum,sides,rolls,modifier,minimum,recent)
                print([(r,hex(uc.reg_read(r))) for r in (UC_X86_REG_RIP,UC_X86_REG_RAX,UC_X86_REG_RCX,UC_X86_REG_RDX)])
                raise
            status=uc.reg_read(UC_X86_REG_RAX)&0xffffffff
            assert status==0,(version,layout,status,recent,hp_trace)
            count,total,con,minroll=struct.unpack('<Iiii',uc.mem_read(out,16))
            expected=max(1,(sides*rolls if maximum else max(3,minimum)*rolls) if rolls else modifier)
            assert (count,total,minroll)==(3,expected*3,minimum),(count,total,minroll,expected)
            assert con==(4 if old in (2,12) else 2),(old,con)
            assert [struct.unpack('<Ii',uc.mem_read(out+16+i*8,8)) for i in range(3)]==[(9,expected),(10,expected),(11,expected)]
            assert len(hp_loads)==3 and not random_values
            assert not writes and saved==bytes(uc.mem_read(rules,0x8000))
            hp_results.append(dict(binding=symbol,old=old,kit=0x4001,maximum=maximum,sides=sides,rolls=rolls,
                modifier=modifier,minimum=minimum,base_contribution=expected,total=total,con_bonus=con,
                native_rng_calls=len(random_calls)))
        hp_fixture=None;skill_mutations=[]
        actor=arena+0x48000;typ=actor+0x4b68
        skill_offsets=[0x5c2,0x5bf,0x5c1,0x5c0,0x59d,0x5bc,0x5bd]
        for layout in layouts:
          for variation in ('ordinary','all-seven','unused','overbudget','stale','decrease','already-usable'):
            execute(layout,8,11)
            overall,flags,active,old,active_off,old_off=layout
            d(actor+0x4ea4,1)
            uc.mem_write(actor+0x1120+active_off,bytes([9 if variation=='already-usable' else 1]))
            uc.mem_write(actor+0x1120+old_off,b'\x08')
            kit=['CUSTOM_OLD',0,0,0,0,7,0,old]
            table_fixture(rules+0x2610,[str(i) for i in range(8)],['NONE','CUSTOM'],[[0]*8,kit],rules+0x3300)
            table_fixture(rules+0x3238,['OTHER','LEVEL_POINTS'],['CUSTOM_OLD','UNUSED'],[[0,25],[9,99]],rules+0x3500)
            table_fixture(rules+0x9a0,['11','9','10'],[class_names[old]],[[1700,1000,1500]],rules+0x3600,default='-1')
            prior=list(range(10,17));selected=prior[:]
            if variation=='all-seven':selected=[n+10 for n in prior]
            elif variation=='unused':pass
            elif variation=='overbudget':selected[0]+=76
            elif variation=='decrease':selected[0]-=1
            else:selected[0]+=30
            for offset,n in zip(skill_offsets,prior):uc.mem_write(actor+offset,bytes([n]))
            uc.mem_write(out+0x80,bytes(prior+selected));d(out,0xcccccccc)
            if variation=='stale':uc.mem_write(actor+skill_offsets[3],b'\x4a')
            saved=bytes(uc.mem_read(actor,0x6000));saved_rules=bytes(uc.mem_read(rules,0x4000));writes.clear()
            rsp=stack+0x8000-8;q(rsp,stop)
            is_plan=variation in ('ordinary','all-seven','unused')
            args=[old,1700,0x4001,out+0x80,out] if is_plan else [after,active,old,0x4001,out+0x80,out]
            for i,value in enumerate(args):q(rsp+0x28+i*8,value)
            for reg,value in [(UC_X86_REG_RSP,rsp),(UC_X86_REG_RCX,context),(UC_X86_REG_RDX,rules),
                 (UC_X86_REG_R8,actor),(UC_X86_REG_R9,active if is_plan else before)]:uc.reg_write(reg,value)
            uc.emu_start(dll_base+exports['CBMDP_ApplyOldPlanSkills' if is_plan else 'CBMDP_ApplyOldSkills'],stop,count=1000000)
            status=uc.reg_read(UC_X86_REG_RAX)&0xffffffff
            expected=4 if variation=='already-usable' else 6 if variation in ('overbudget','stale','decrease') else 0
            assert status==expected,(version,layout,variation,status,recent)
            actual=bytes(uc.mem_read(actor,0x6000));allowed=bytearray(saved)
            if not expected:
                for offset,n in zip(skill_offsets,selected):allowed[offset]=n
                assert struct.unpack('<I',uc.mem_read(out,4))[0]==75-sum(b-a for a,b in zip(prior,selected))
            else:assert struct.unpack('<I',uc.mem_read(out,4))[0]==0xcccccccc
            assert actual==bytes(allowed) and saved_rules==bytes(uc.mem_read(rules,0x4000))
            assert all(address-actor in skill_offsets and width==1 for address,width in writes),writes
            skill_mutations.append(dict(old=old,variation=variation,status=status,unrelated_bytes_preserved=True))
        results.append(dict(version=version,cases=len(cases),exe_sha256=SHAS[version],
            compiled_wrapper_executed_in_emulator=True,native_instruction_execution=True,
            real_game_process=False,environment_stubs=list(environment.values())+['thread token'],
            slot_results=cases,choice_cap_results=caps,skill_budget_results=skills_results,hp_roll_results=hp_results,skill_mutation_results=skill_mutations,old_target_results=target_results))
    report=dict(builds=results,total_cases=sum(r['cases']+len(r['choice_cap_results'])+len(r['skill_budget_results'])+len(r['hp_roll_results'])+len(r['skill_mutation_results'])+len(r['old_target_results']) for r in results),game_launched=False,
                complete_retired_progression=False)
    report['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
        ['dual_native_proficiency.h','dual_native_proficiency.cpp','dual_native_proficiency_builds.inc','dual_proficiency_probe.py']}
    (ROOT/'dual-proficiency-check-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='builds'}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--generate',action='store_true')
    parser.add_argument('--dll',type=Path)
    args=parser.parse_args()
    if args.generate:generate()
    if args.dll:run(args.dll)
