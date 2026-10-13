"""Read-only source/profile proof and native eligibility restriction execution.

Actual IsLevelUpButtonClickable instructions run in Unicorn. Environmental
CString/derived-copy, effect-list query and progression-query calls are declared
stubs here. Progression itself has separate real-instruction checks in
dual_proficiency_probe.py. No process launch or installed bytes are changed.
"""
import json,struct
from pathlib import Path
import capstone
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
from unicorn.x86_const import *
from dual_proficiency_probe import load,EXES,SHAS,SOURCE
ROOT=Path(__file__).parent
def main():
 profiles=[];checks=[]
 for version in EXES:
  pe,names,_=load(version);base=pe.OPTIONAL_HEADER.ImageBase
  raw={int(x.split('\t')[0],16):x.split('\t')[1] for x in
   (SOURCE/('v'+version)/'bg2ee/function_names.db').read_text().splitlines() if x.startswith('0x')}
  keys=sorted(raw);md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);md.detail=True
  at=names['CScreenCharacter::IsLevelUpButtonClickable'];end=keys[keys.index(at)+1]
  instructions=list(md.disasm(pe.get_data(at-base,end-at),at))
  calls=[i for i in instructions if i.mnemonic=='call' and i.operands[0].type==capstone.CS_OP_IMM]
  query=next(i for i in calls if raw.get(i.operands[0].imm)=='CRuleTables::GetNextLevel')
  idx=instructions.index(query)
  assert [(i.mnemonic,i.op_str) for i in instructions[idx-3:idx]]==[
   ('lea','r8, [rsp + 0x20]'),('mov','rcx, r14'),('lea','rdx, [rdi + 0x4b50]')]
  click=names['CScreenCharacter::OnLevelUpButtonClick'];clickend=keys[keys.index(click)+1]
  clickins=list(md.disasm(pe.get_data(click-base,clickend-click),click))
  starts=[i for i in clickins if i.mnemonic=='call' and i.operands[0].type==capstone.CS_OP_IMM
   and raw.get(i.operands[0].imm)=='CScreenCreateChar::StartEditing']
  assert len(starts)==1
  profile={'version':version,'exe_sha256':SHAS[version],
    'gameTimestamp':pe.FILE_HEADER.TimeDateStamp,'gameSize':pe.OPTIONAL_HEADER.SizeOfImage,
    'eligibilityQuery':{'rva':query.address-base,'bytes':bytes(query.bytes).hex()},
    'manualStartCall':{'rva':starts[0].address-base,'bytes':bytes(starts[0].bytes).hex()},'functions':{},'entries':{}}
  for short,symbol in [('clickable','CScreenCharacter::IsLevelUpButtonClickable'),
   ('nextLevel','CRuleTables::GetNextLevel'),('classes','CAIObjectType::GetActiveInactiveClasses'),
   ('overall','CGameAnimationType::GetMoveScale'),('level','CDerivedStats::GetLevel'),
   ('setLevel','CDerivedStats::SetLevel'),('isUsable','CAIObjectType::IsUsableSubClass'),
   ('startEditing','CScreenCreateChar::StartEditing'),('onLevelUp','CScreenCharacter::OnLevelUpButtonClick'),
   ('getDeny','CGameObjectArray::GetDeny')]:
   p=names[symbol];profile['functions'][short]={'rva':p-base,'bytes':pe.get_data(p-base,32).hex()}
  for key,symbol in [('clickable','CScreenCharacter::IsLevelUpButtonClickable'),('click','CScreenCharacter::OnLevelUpButtonClick')]:
   entry_at=names[symbol];span=0
   for i in md.disasm(pe.get_data(entry_at-base,32),entry_at):
    assert i.mnemonic not in ('call','jmp') and 'rip' not in i.op_str
    span+=i.size
    if span>=5:break
   profile['entries'][key]={'rva':entry_at-base,'bytes':pe.get_data(entry_at-base,span).hex(),'span':span}
  profiles.append(profile)
  for oldslot in (0x46,0x48):
   for variant in ('owed-only','ordinary-no-owed','not-controlled','other-player','owned-network',
                   'incapacitated','level-drained','pending-spell-not-controlled'):
    u=Uc(UC_ARCH_X86,UC_MODE_64);u.mem_map(base,pe.OPTIONAL_HEADER.SizeOfImage)
    u.mem_write(base,pe.get_memory_mapped_image())
    arena=0x50000000;u.mem_map(arena,0x30000);stop=arena+0x2f000
    chitin,game,screen,actor=arena,arena+0x3000,arena+0x5000,arena+0x7000
    sp=arena+0x28000-8
    def q(a,v):u.mem_write(a,struct.pack('<Q',v))
    def d(a,v):u.mem_write(a,struct.pack('<I',v))
    def ret(value=None):
     if value is not None:u.reg_write(UC_X86_REG_RAX,value)
     s=u.reg_read(UC_X86_REG_RSP);r=struct.unpack('<Q',u.mem_read(s,8))[0]
     u.reg_write(UC_X86_REG_RSP,s+8);u.reg_write(UC_X86_REG_RIP,r)
    for i,ins in enumerate(instructions):
     if ins.mnemonic=='mov' and ins.op_str=='r14, qword ptr [rax + 0x1090]':
      p=next(x for x in reversed(instructions[:i]) if x.mnemonic=='mov' and x.op_str.startswith('rax, qword ptr [rip'))
      q(p.address+p.size+p.operands[1].mem.disp,chitin)
     if ins.mnemonic=='mov' and ins.op_str.startswith('r8, qword ptr [rip'):
      q(ins.address+ins.size+ins.operands[1].mem.disp,chitin)
    q(chitin+0x1090,game);d(screen+0x6d0,0 if variant in ('not-controlled','pending-spell-not-controlled') else 1)
    u.mem_write(chitin+0x2c9,bytes([1 if variant in ('other-player','owned-network') else 0]))
    d(chitin+0x374,7);d(actor+0x50,8 if variant=='other-player' else 7)
    u.mem_write(actor+0x1120+oldslot,b'\x08')
    if variant=='incapacitated':d(actor+0x1120,0x800)
    if variant=='pending-spell-not-controlled':u.mem_write(actor+0x52fc,b'\x01')
    native_before=bytes(u.mem_read(actor,0x6000));queries=[]
    targets={i.operands[0].imm:raw.get(i.operands[0].imm) for i in calls}
    def hook(machine,p,size,data):
     if p==stop:machine.emu_stop();return
     if p not in targets:return
     name=targets[p];rcx,rdx,r8=[u.reg_read(r) for r in (UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8)]
     if name=='CDerivedStats::CDerivedStats':u.mem_write(rcx,b'\0'*0xca8);ret(rcx)
     elif name=='CDerivedStats::operator=':u.mem_write(rcx,bytes(u.mem_read(rdx,0xca8)));ret(rcx)
     elif name=='CRuleTables::GetNextLevel':
      assert rdx==actor+0x4b50 and r8!=actor+0x1120;queries.append(r8)
      if variant!='ordinary-no-owed':u.mem_write(r8+oldslot,b'\x0b')
      ret()
     elif name=='CGameEffectList::IsTypeOnList':
      assert rcx==actor+0x4a00 and rdx&0xffff==216;ret(int(variant=='level-drained'))
     elif name in ('CDerivedStats::~CDerivedStats','__security_check_cookie'):ret()
     else:raise AssertionError(name)
    u.hook_add(UC_HOOK_CODE,hook);q(sp,stop)
    for r,v in [(UC_X86_REG_RSP,sp),(UC_X86_REG_RCX,screen),(UC_X86_REG_RDX,actor)]:u.reg_write(r,v)
    u.emu_start(at,stop,count=20000)
    result=u.reg_read(UC_X86_REG_EAX)
    expected=int(variant in ('owed-only','owned-network','pending-spell-not-controlled'))
    assert result==expected,(version,oldslot,variant,result)
    # Our Check additionally rejects native pending-spell-only true results if
    # the private query was skipped. It cannot bypass denied screen ownership.
    assert int(bool(result and queries))==int(variant in ('owed-only','owned-network'))
    assert native_before==bytes(u.mem_read(actor,0x6000))
    checks.append({'version':version,'oldSlot':oldslot,'case':variant,'nativeResult':result,'queryRan':bool(queries)})
 def lua(x):
  if isinstance(x,dict):return '{'+','.join('['+json.dumps(k)+']='+lua(v) for k,v in x.items())+'}'
  if isinstance(x,list):return '{'+','.join(map(lua,x))+'}'
  return json.dumps(x)
 (ROOT/'dual_entry_profiles.lua').write_text('-- Audited read-only executable profiles.\nreturn '+lua(profiles)+'\n')
 report={'checks':len(checks),'results':checks,'profiles':profiles,'gameLaunched':False,
   'boundaries':['derived constructor/copy/destructor','progression query separately proven','effect presence','security cookie'],
   'limits':'Native restrictions executed; no UI layout/render or full retired reward transaction acceptance.'}
 (ROOT/'dual-entry-check-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'checks':len(checks),'gameLaunched':False}))
if __name__=='__main__':main()
