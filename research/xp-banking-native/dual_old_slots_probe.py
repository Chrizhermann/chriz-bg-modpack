"""Offline native spell-slot class/level routing; no engine process.

Runs actual GetMaxMemorizedSpellsMage/Priest, usability and level accessors.
CString allocation/format, installed table values and object lookup are declared
environment boundaries. Captured table requests prove the selected class level,
not the contents of any particular installed progression table.
"""
import json
import struct
from collections import deque
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import *
from dual_proficiency_probe import EXES, load, cstring
from dual_old_reward_probe import LAYOUTS

ROOT = Path(__file__).parent


def run():
    reports=[]
    for version in EXES:
        pe,names,_=load(version);base=pe.OPTIONAL_HEADER.ImageBase
        uc=Uc(UC_ARCH_X86,UC_MODE_64);uc.mem_map(base,pe.OPTIONAL_HEADER.SizeOfImage)
        uc.mem_write(base,pe.get_memory_mapped_image())
        arena=0x2000000;uc.mem_map(arena,0x40000)
        actor,rules,stats,out,cell=arena,arena+0x6000,arena+0xa000,arena+0xb000,arena+0xb100
        stack,stop=arena+0x38000-8,arena+0x39000
        q=lambda at,n:uc.mem_write(at,struct.pack('<Q',n))
        d=lambda at,n:uc.mem_write(at,struct.pack('<I',n))
        u64=lambda at:struct.unpack('<Q',uc.mem_read(at,8))[0]
        boundaries={names[n]:n for n in ('CString::Format','CString::~CString',
            'C2DArray::GetAt','sscanf','CGameObjectArray::GetDeny','CGameSprite::GetKitMask')}
        heap=arena+0x10000;requests=[];recent=deque(maxlen=12)
        def alloc(s):
            nonlocal heap
            p=heap;heap+=(len(s)+17)//8*8;uc.mem_write(p,s+b'\0');return p
        def hook(u,at,size,_):
            recent.append(hex(at))
            if at==stop:u.emu_stop();return
            if at not in boundaries:return
            rcx,rdx,r8=(u.reg_read(r) for r in (UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8))
            name=boundaries[at];result=0
            if name=='CGameObjectArray::GetDeny':assert rcx==123;q(rdx,actor)
            elif name=='CGameSprite::GetKitMask':assert rcx==actor
            elif name=='CString::Format':
                assert cstring(u,rdx)==b'%d';q(rcx,alloc(str(r8&0xffffffff).encode()))
            elif name=='CString::~CString':pass
            elif name=='C2DArray::GetAt':
                column=int(cstring(u,u64(rdx)));row=int(cstring(u,u64(r8)))
                offset=rcx-rules;requests.append((offset,column,row))
                # Deliberately distinct non-vanilla values. Wisdom bonus separate.
                value=0 if offset==0x818 else row*10+column
                q(cell,alloc(str(value).encode()));result=cell
            elif name=='sscanf':
                assert cstring(u,rdx)==b'%d';d(r8,int(cstring(u,rcx)));result=1
            rsp=u.reg_read(UC_X86_REG_RSP)
            u.reg_write(UC_X86_REG_RAX,result);u.reg_write(UC_X86_REG_RIP,u64(rsp));u.reg_write(UC_X86_REG_RSP,rsp+8)
        uc.hook_add(UC_HOOK_CODE,hook)
        cases=[]
        for layout in LAYOUTS:
            overall,flags,active,old,active_off,old_off=layout
            for active_level in (10,11,12):
                for spell_level in (1,4,7,9):
                    for family in ('Mage','Priest'):
                        heap=arena+0x10000;requests.clear()
                        uc.mem_write(actor,b'\0'*0x5800);uc.mem_write(stats,b'\0'*0xca8)
                        d(actor+0x568,flags);d(actor+0x4ea4,1)
                        for typ in (actor+0x30,actor+0x4b50,actor+0x4b68):
                            uc.mem_write(typ+0xb,bytes([overall]));d(typ+0xc,123)
                        for derived in (actor+0x1120,actor+0x1dc8,stats):
                            uc.mem_write(derived+active_off,bytes([active_level]))
                            uc.mem_write(derived+old_off,b'\x0b')
                            uc.mem_write(derived+0x54,b'\x12\0')
                        q(stack,stop);q(stack+0x28,spell_level if family=='Mage' else out)
                        for reg,value in ((UC_X86_REG_RSP,stack),(UC_X86_REG_RCX,rules),
                            (UC_X86_REG_RDX,actor+0x4b68),(UC_X86_REG_R8,stats),
                            (UC_X86_REG_R9,0x4000 if family=='Mage' else spell_level)):
                            uc.reg_write(reg,value)
                        try:uc.emu_start(names['CRuleTables::GetMaxMemorizedSpells'+family],stop,count=100000)
                        except Exception:print(version,layout,active_level,family,list(recent));raise
                        available={active:active_level}
                        if active_level>11:available[old]=11
                        # Both caster types can share the priest family (ranger/cleric).
                        table_classes={0x700:1,0x658:3,0x850:11,0x6c8:12}
                        relevant={1} if family=='Mage' else {3,11,12}
                        expected={c:lv for c,lv in available.items() if c in relevant}
                        actual={table_classes[off]:row for off,col,row in requests if off!=0x818}
                        assert actual==expected,(version,layout,active_level,family,requests,expected)
                        assert all(col==spell_level for _,col,_ in requests)
                        result=uc.reg_read(UC_X86_REG_RAX)&0xffffffff
                        assert result==max([lv*10+spell_level for lv in expected.values()]+[0]),(requests,result)
                        cases.append(dict(overall=overall,old=old,active=active,activeLevel=active_level,
                            spellLevel=spell_level,family=family,requests=list(requests),slots=result))
        reports.append(dict(version=version,cases=len(cases),results=cases))
    (ROOT/'dual-old-slot-routing-results.json').write_text(json.dumps(reports,indent=2)+'\n')
    return reports


if __name__=='__main__':print(json.dumps([dict(version=x['version'],cases=x['cases']) for x in run()]))
