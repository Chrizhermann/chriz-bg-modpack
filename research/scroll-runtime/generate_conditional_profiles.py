"""Exact common-scroll 326/272/232 edges, from the two read-only native images."""
import hashlib,json
from pathlib import Path
import capstone,pefile
from generate_decode_profiles import EXES,EEEX,signature
ROOT=Path(__file__).resolve().parent
NAMES=['CGameEffectApplySpell::ApplyEffect','CGameEffectRepeatingApplyEffect::ApplyEffect',
 'CPersistantEffectApplyEffect::AIUpdate','CGameEffectContingencyInstance::ApplyEffect',
 'CContingencyList::Process','CContingencyList::ProcessTrigger','CContingencyList::operator=',
 "CContingency::`scalar_deleting_destructor'",'CContingencyList::ClearAll','CGameEffect::operator=']
def main():
 profiles=[]
 for version,path,digest,_ in EXES:
  raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==digest;pe=pefile.PE(data=raw);base=pe.OPTIONAL_HEADER.ImageBase
  names={n:int(a,16) for line in (EEEX/('v'+version)/'bg2ee/function_names.db').read_text().splitlines() for a,_,n in [line.partition('\t')] if a.startswith('0x')};order=sorted(set(names.values()))
  md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
  def extent(n):return names[n],order[order.index(names[n])+1]
  def code(n):a,b=extent(n);return pe.get_data(a-base,b-a)
  def calls(n,target):return [i.address-base for i in md.disasm(code(n),names[n]) if i.mnemonic=='call' and i.op_str==hex(names[target])]
  fire=calls(NAMES[0],'CGameEffect::FireSpell');assert len(fire)==1
  decoder=calls(NAMES[2],'CGameEffect::DecodeEffectFromBase');assert len(decoder)==1
  cast_calls=calls(NAMES[4],'CGameAIBase::FireSpell')+calls(NAMES[5],'CGameAIBase::FireSpell');assert len(cast_calls)==6
  clean_calls=[]
  for n in [NAMES[5],NAMES[6],NAMES[7],NAMES[8]]:
   found=calls(n,'CSound::~CSound');assert len(found)==1;clean_calls+=found
  # EEex owns exactly this source/target SPLPROT fix; preserve its existing cave.
  start,end=extent(NAMES[0]);fix=start-base+code(NAMES[0]).index(bytes.fromhex('4c8bcf8b5320'))+9
  assert pe.get_data(fix,7)==bytes.fromhex('488b8890100000')
  spans=[signature(pe,NAMES[0]+' before EEex fix',start-base,fix-(start-base)),signature(pe,NAMES[0]+' after EEex fix',fix+7,end-base-fix-7)]
  for n in NAMES[1:]:a,b=extent(n);spans.append(signature(pe,n,a-base,b-a))
  update=names[NAMES[2]]-base;assert pe.get_data(update,8)==bytes.fromhex('405341564883ec68')
  profiles.append(dict(version=version,timestamp=pe.FILE_HEADER.TimeDateStamp,spans=spans,fix=fix,
   update=update,decode_call=decoder[0],decoder=names['CGameEffect::DecodeEffectFromBase']-base,
   fire326_return=fire[0]+5,calls=cast_calls+clean_calls,
   targets=[names['CGameAIBase::FireSpell']-base]*6+[names['CSound::~CSound']-base]*4))
 (ROOT/'conditional-profiles.json').write_text(json.dumps(profiles,indent=2)+'\n')
 def sig(s):return '{0x%x,0x%x,{%s}}'%(s['rva'],s['size'],','.join('0x'+s['sha256'][i:i+2] for i in range(0,64,2)))
 lines=['#pragma once','namespace cbm::scroll::binding {','struct ConditionalProfile { unsigned timestamp,fix,update,decode_call,decoder,fire326_return; unsigned calls[10],targets[10]; DecodeSignature spans[11]; };','inline constexpr ConditionalProfile conditional_profiles[] = {']
 for p in profiles:lines.append('{%s,{%s},{%s},{%s}},'%(','.join(str(p[k]) for k in ['timestamp','fix','update','decode_call','decoder','fire326_return']),','.join(map(str,p['calls'])),','.join(map(str,p['targets'])),','.join(sig(s) for s in p['spans'])))
 (ROOT/'conditional_profiles.hpp').write_text('\n'.join(lines+['};','}'])+'\n')
if __name__=='__main__':main()
