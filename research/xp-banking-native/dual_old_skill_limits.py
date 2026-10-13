"""Read-only native old-skill UI source inventory."""
import hashlib
import json
import struct
from pathlib import Path
import capstone
from dual_proficiency_probe import load,EXES,SOURCE
ROOT=Path(__file__).parent
FUNCTIONS=['CScreenCreateChar::IsThiefSkillPlusMinusButtonClickable',
 'CScreenCreateChar::OnThiefSkillPlusMinusButtonClick','CGameSprite::GetSkillName',
 'CGameSprite::GetSkillValue','CRuleTables::GetThiefSkillPercentage',
 'CScreenCreateChar::ResetProficienciesPanel']
def inventory():
 reports=[]
 for version in EXES:
  pe,names,_=load(version);base=pe.OPTIONAL_HEADER.ImageBase
  by_address={int(line.split('\t')[0],16):line.split('\t')[1] for line in
   (SOURCE/('v'+version)/'bg2ee/function_names.db').read_text().splitlines() if line.startswith('0x')}
  keys=sorted(by_address);md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);md.detail=True
  lines=[];report={'version':version,'functions':[]}
  update=names['CScreenCreateChar::UpdateProficienciesPanel']
  # Seven direct allocation rows plus native composite stealth presentation row.
  row_keys=[]
  for ins in md.disasm(pe.get_data(update-base,0x1000),update):
   if ins.mnemonic=='lea' and len(ins.operands)==2 and ins.operands[1].type==capstone.CS_OP_MEM and ins.operands[1].mem.base==capstone.x86.X86_REG_RIP:
    ptr=ins.address+ins.size+ins.operands[1].mem.disp
    if base<=ptr<base+pe.OPTIONAL_HEADER.SizeOfImage:
     value=pe.get_string_at_rva(ptr-base)
     if value in (b'PICK_POCKETS',b'OPEN_LOCKS',b'FIND_TRAPS',b'MOVE_SILENTLY',b'HIDE_IN_SHADOWS',b'DETECT_ILLUSION',b'SET_TRAPS',b'STEALTH'):
      row_keys.append({'at':ins.address-base,'key':value.decode()})
  report['skill_key_references']=row_keys
  click=names['CScreenCreateChar::OnThiefSkillPlusMinusButtonClick']
  for ins in md.disasm(pe.get_data(click-base,0x100),click):
   if ins.mnemonic=='cmp' and ins.op_str.startswith('esi, dword ptr [rip'):
    ptr=ins.address+ins.size+ins.operands[1].mem.disp
    report['displayed_skill_cap']={'instruction_rva':ins.address-base,'value_rva':ptr-base,'value':struct.unpack('<i',pe.get_data(ptr-base,4))[0]}
  for name in FUNCTIONS:
   start=names[name];end=keys[keys.index(start)+1];body=pe.get_data(start-base,end-start)
   lines.append('\n'+name);report['functions'].append({'name':name,'rva':start-base,'size':len(body),'sha256':hashlib.sha256(body).hexdigest()})
   for ins in md.disasm(body,start):
    target=by_address.get(ins.operands[0].imm) if ins.mnemonic in ('call','jmp') and ins.operands[0].type==capstone.CS_OP_IMM else None
    lines.append(f'{ins.address-base:08x} {ins.mnemonic:8s} {ins.op_str}'+(' ; '+target if target else ''))
  (ROOT/f'dual-old-skill-limits-{version}.txt').write_text('\n'.join(lines)+'\n');reports.append(report)
 (ROOT/'dual-old-skill-limits.json').write_text(json.dumps(reports,indent=2)+'\n')
 return reports
if __name__=='__main__':print(json.dumps([{ 'version':r['version'],'functions':len(r['functions'])} for r in inventory()]))
