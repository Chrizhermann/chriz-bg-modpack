"""Build signatures and execute compiled read-only skill adapter offline."""
import argparse
import ctypes
import json
import re
import struct
import threading
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
from unicorn.x86_const import *
from dual_proficiency_probe import load,EXES,SOURCE,fnv,cstring,keep_or_write
from dual_old_skill_limits import inventory
ROOT=Path(__file__).parent
FUNCTIONS=['CRuleTables::GetClassString','CString::~CString','C2DArray::GetAt',
 'CGameSprite::GetSkillValue','CGameSprite::GetSkillName','CAIObjectType::GetActiveInactiveClasses',
 'atoi','CRuleTables::GetThiefSkillPercentage']
def generate():
 rows=inventory();lines=['// Pinned instruction signatures; no game code.','static constexpr Build builds[]={']
 for version in EXES:
  pe,names,_=load(version);base=pe.OPTIONAL_HEADER.ImageBase
  addresses=sorted(int(line.split('\t')[0],16) for line in (SOURCE/('v'+version)/'bg2ee/function_names.db').read_text().splitlines() if line.startswith('0x'))
  cap=next(r for r in rows if r['version']==version)['displayed_skill_cap']['value_rva']
  lines.append(f'{{0x{pe.OPTIONAL_HEADER.SizeOfImage:x},0x{cap:x},{{ // {version}')
  for name in FUNCTIONS:
   at=names[name];end=addresses[addresses.index(at)+1];data=pe.get_data(at-base,end-at)
   lines.append(f'{{0x{at-base:x},0x{end-at:x},0x{fnv(data):016x}ULL}}, // {name}')
  lines.append('}},')
 lines.append('};');keep_or_write(ROOT/'dual_skill_rows_builds.inc','\n'.join(lines)+'\n')

def run(dll_path):
 dll=ctypes.CDLL(str(dll_path));dll.CBMDS_Bind.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_void_p)]
 dll.CBMDS_Query.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint8,ctypes.c_uint32,ctypes.c_void_p]
 dll.CBMDS_Destroy.argtypes=[ctypes.c_void_p]
 dp=pefile.PE(str(dll_path));db=dp.OPTIONAL_HEADER.ImageBase
 exports={s.name.decode():s.address for s in dp.DIRECTORY_ENTRY_EXPORT.symbols if s.name}
 token=int(re.search(r'\bCBMDS_ThreadToken\s+([0-9a-fA-F]+)',dll_path.with_suffix('.map').read_text()).group(1),16)
 reports=[]
 for version in EXES:
  pe,names,_=load(version);base=pe.OPTIONAL_HEADER.ImageBase;size=pe.OPTIONAL_HEADER.SizeOfImage
  mapped=pe.get_memory_mapped_image().ljust(size,b'\0');image=ctypes.create_string_buffer(mapped);binding=ctypes.c_void_p()
  assert dll.CBMDS_Bind(image,size,ctypes.byref(binding))==0
  ptr,build,owner=struct.unpack('<QQI4x',ctypes.string_at(binding,24));build_rva=build-dll._handle
  results=[]
  def foreign():results.append(dll.CBMDS_Query(binding,1,1,4,0x4000,1));results.append(dll.CBMDS_Destroy(binding))
  thread=threading.Thread(target=foreign);thread.start();thread.join();assert results==[3,3]
  assert dll.CBMDS_Destroy(binding)==0
  uc=Uc(UC_ARCH_X86,UC_MODE_64);uc.mem_map(base,size);uc.mem_write(base,mapped)
  uc.mem_map(db,dp.OPTIONAL_HEADER.SizeOfImage);uc.mem_write(db,dp.get_memory_mapped_image())
  arena=0x2000000;uc.mem_map(arena,0x50000)
  rules,actor,context,out,cell=arena,arena+0x5000,arena+0xb000,arena+0xb100,arena+0xb300
  stop,stack=arena+0x3f000,arena+0x3e000-8
  q=lambda at,n:uc.mem_write(at,struct.pack('<Q',n));d=lambda at,n:uc.mem_write(at,struct.pack('<I',n&0xffffffff))
  u64=lambda at:struct.unpack('<Q',uc.mem_read(at,8))[0]
  q(context,base);q(context+8,db+build_rva);d(context+16,owner)
  cap=next(r for r in json.loads((ROOT/'dual-old-skill-limits.json').read_text()) if r['version']==version)['displayed_skill_cap']['value_rva']
  heap=arena+0x10000;fixture={};lookups=[];classes=[]
  def alloc(s):
   nonlocal heap
   at=heap;heap+=(len(s)+17)//8*8;uc.mem_write(at,s+b'\0');return at
  boundaries={names[n]:n for n in ('CRuleTables::GetClassString','CString::~CString','C2DArray::GetAt',
   'atoi','CGameObjectArray::GetDeny','CRuleTables::GetSkillBonusValue')}
  # Native GetSkillValue global game/rules indirection; resolved from its source.
  import capstone
  md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);md.detail=True
  at=names['CGameSprite::GetSkillValue']
  for ins in md.disasm(pe.get_data(at-base,0x100),at):
   if ins.mnemonic=='mov' and ins.op_str.startswith('rcx, qword ptr [rip'):
    q(ins.address+ins.size+ins.operands[1].mem.disp,arena+0xd000);q(arena+0xd000+0x1090,rules)
  def hook(u,at,n,_):
   if at==stop:u.emu_stop();return
   if at!=token and at not in boundaries:return
   rcx,rdx,r8,r9=(u.reg_read(r) for r in (UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9))
   rsp=u.reg_read(UC_X86_REG_RSP);result=0
   if at==token:result=owner
   else:
    name=boundaries[at]
    if name=='CGameObjectArray::GetDeny':assert rcx==123;q(rdx,actor)
    elif name=='CRuleTables::GetClassString':
     assert rcx==rules and r9==fixture['kit'];classes.append(r8);q(rdx,alloc(str(r8).encode()));result=rdx
    elif name=='CString::~CString':pass
    elif name=='C2DArray::GetAt':
     assert rcx==rules+0x3270
     row=int(cstring(u,u64(rdx)));key=cstring(u,u64(r8)).decode();lookups.append((row,key))
     value=fixture['old'] if row==4 else fixture['default']
     text=alloc(str(value).encode());result=alloc(b'\0'*8);q(result,text)
    elif name=='atoi':result=int(cstring(u,rcx))
    elif name=='CRuleTables::GetSkillBonusValue':
     assert rcx==rules and rdx==actor+0x4b68
     # Seven actual output pointer slots; native GetSkillValue performs addition.
     outputs=[r9]+[u64(rsp+0x28+i*8) for i in range(6)]
     for p in outputs:d(p,fixture['bonus'])
   u.reg_write(UC_X86_REG_RAX,result&0xffffffffffffffff)
   u.reg_write(UC_X86_REG_RIP,u64(rsp));u.reg_write(UC_X86_REG_RSP,rsp+8)
  uc.hook_add(UC_HOOK_CODE,hook);cases=[]
  for percent,default in ((100,0),(0,0),(-1,0),(0,75),(37,-1)):
   for bonus in (-30,0,25,300):
    for limit in (180,250,300):
     heap=arena+0x10000;lookups.clear();classes.clear()
     fixture.update(old=percent,default=default,bonus=bonus,kit=0x12344000)
     uc.mem_write(actor,b'\0'*0x5800);uc.mem_write(actor+0x4b73,b'\x09');d(actor+0x4b74,123);d(actor+0x568,64);d(actor+0x4ea4,1)
     for off in (0x5c2,0x5bf,0x5c1,0x5c0,0x59d,0x5bc,0x5bd):uc.mem_write(actor+off,b'\x28')
     d(base+cap,limit);q(stack,stop);q(stack+0x28,fixture['kit']);q(stack+0x30,out)
     for reg,value in ((UC_X86_REG_RSP,stack),(UC_X86_REG_RCX,context),(UC_X86_REG_RDX,rules),(UC_X86_REG_R8,actor),(UC_X86_REG_R9,4)):uc.reg_write(reg,value)
     before=bytes(uc.mem_read(actor,0x5800))
     uc.emu_start(db+exports['CBMDS_Query'],stop,count=300000)
     assert uc.reg_read(UC_X86_REG_RAX)==0
     rows=[struct.unpack('<IIiiii',uc.mem_read(out+i*24,24)) for i in range(7)]
     assert classes==[4,0] and len(lookups)==14
     assert before==bytes(uc.mem_read(actor,0x5800))
     for i,row in enumerate(rows):
      assert row[0]==i and row[1]!=0xffffffff
      assert row[2:]==(40,40+bonus,max(0,min(255,limit-bonus)),max(0,percent,default)),row
     cases.append(dict(percentage=percent,default=default,bonus=bonus,displayCap=limit))
  reports.append(dict(version=version,cases=len(cases),results=cases))
 keep_or_write(ROOT/'dual-skill-row-results.json',json.dumps(reports,indent=2)+'\n');return reports
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--generate',action='store_true');p.add_argument('--dll',type=Path);args=p.parse_args()
 if args.generate:generate()
 if args.dll:print(json.dumps([dict(version=x['version'],cases=x['cases']) for x in run(args.dll)]))
