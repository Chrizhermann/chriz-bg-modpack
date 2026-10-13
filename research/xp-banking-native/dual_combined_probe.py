"""Derive scoped combined-preview callsites from pinned read-only executables.
This is instruction/signature evidence, not execution of a game or its UI.
"""
from pathlib import Path
import json
import capstone
from dual_proficiency_probe import load,EXES,SHAS,SOURCE
ROOT=Path(__file__).parent
def main():
 profiles=[]
 for version in EXES:
  pe,names,_=load(version);base=pe.OPTIONAL_HEADER.ImageBase
  raw={int(x.split('\t')[0],16):x.split('\t')[1] for x in
   (SOURCE/('v'+version)/'bg2ee/function_names.db').read_text().splitlines() if x.startswith('0x')}
  keys=sorted(raw);md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);md.detail=True
  p={'version':version,'exe_sha256':SHAS[version],'gameTimestamp':pe.FILE_HEADER.TimeDateStamp,
   'gameSize':pe.OPTIONAL_HEADER.SizeOfImage,'functions':{},'nextCalls':[]}
  pairs=[('next_level','CRuleTables::GetNextLevel'),('get_hp','CRuleTables::GetHitPoints'),
   ('get_classes','CAIObjectType::GetActiveInactiveClasses'),('get_class','CGameAnimationType::GetMoveScale'),
   ('get_level','CDerivedStats::GetLevel'),('set_level','CDerivedStats::SetLevel'),('is_usable','CAIObjectType::IsUsableSubClass'),
   ('stats_construct','CDerivedStats::CDerivedStats'),('stats_copy','CDerivedStats::operator='),
   ('stats_destruct','CDerivedStats::~CDerivedStats'),('combine_all','CGameSprite::CombineAllActiveInactiveProficiencies'),
   ('get_active','CGameSprite::GetActiveProficiency'),('get_inactive','CGameSprite::GetInactiveProficiency'),
   ('set_active','CGameSprite::SetActiveProficiency'),('set_inactive','CGameSprite::SetInactiveProficiency'),
   ('add_special','CGameSprite::AddNewSpecialAbilities')]
  for key,symbol in pairs:
   at=names[symbol];end=keys[keys.index(at)+1]
   p['functions'][key]={'rva':at-base,'bytes':pe.get_data(at-base,end-at).hex(),'name':symbol}
  # ProcessEffectList contains several intentional EEex hooks deep inside its
  # body. Bind its untouched ABI entry; calls/arguments below prove our branch.
  at=names['CGameSprite::ProcessEffectList'];ins=list(md.disasm(pe.get_data(at-base,40),at));n=0
  for x in ins:
   n+=x.size
   if n>=16:break
  p['functions']['process_effects']={'rva':at-base,'bytes':pe.get_data(at-base,n).hex(),
   'name':'CGameSprite::ProcessEffectList','signatureScope':'complete entry instructions'}
  setter=names['CGameSprite::SetActiveProficiency'];end=keys[keys.index(setter)+1]
  seq=list(md.disasm(pe.get_data(setter-base,end-setter),setter))
  hits=[i for i,x in enumerate(seq) if x.mnemonic=='call' and x.operands[0].type==capstone.CS_OP_IMM and x.operands[0].imm==at]
  assert len(hits)==1
  i=hits[0];assert [(x.mnemonic,x.op_str) for x in seq[i-3:i]]==[
   ('mov','edx, 1'),('mov','dword ptr [rdi + 0x4ba4], 1'),('mov','rcx, rdi')]
  p['activeRefresh']={'callRva':seq[i].address-base,'forceOffset':0x4ba4,'argument':1}
  # Required EEex wraps exactly these native calls, preserving the original
  # callee as the first instruction in its after-call relay. Do not reject the
  # required extension by demanding an unpatched entire function body.
  image=pe.get_memory_mapped_image()
  for key,pattern,offset,label in [
   ('stats_construct','48894C24085741544155415641574883EC20488BF1',28,'Construct'),
   ('stats_destruct','488981500C0000',14,'Destruct'),
   ('stats_copy','48894424288B02',641,'operator_equ')]:
   pattern=bytes.fromhex(pattern);assert image.count(pattern)==1
   rva=image.index(pattern)+offset;f=p['functions'][key]
   assert f['rva']<=rva< f['rva']+len(f['bytes'])//2 and image[rva]==0xe8
   f['eeexAfterCall']={'offset':rva-f['rva'],'bytes':image[rva:rva+5].hex(),
    'label':'Hook-CDerivedStats::'+label+'()-FirstCall',
    'calleeRva':rva+5+int.from_bytes(image[rva+1:rva+5],'little',signed=True)}
  at=names['CScreenCreateChar::ResetLevelUpPanel'];end=keys[keys.index(at)+1]
  ins=list(md.disasm(pe.get_data(at-base,end-at),at))
  for i,x in enumerate(ins):
   if x.mnemonic!='call' or x.operands[0].type!=capstone.CS_OP_IMM:continue
   target=x.operands[0].imm
   if target==names['CRuleTables::GetNextLevel']:
    assert [(a.mnemonic,a.op_str) for a in ins[i-3:i]]==[('mov','r8, rsi'),('mov','rdx, r13'),('mov','rcx, r12')]
    p['nextCalls'].append({'rva':x.address-base,'bytes':bytes(x.bytes).hex()})
   elif target==names['CGameSprite::CombineAllActiveInactiveProficiencies']:
    assert ins[i-1].mnemonic=='mov' and ins[i-1].op_str=='rcx, r14'
    assert 'combineCall' not in p;p['combineCall']={'rva':x.address-base,'bytes':bytes(x.bytes).hex()}
  assert len(p['nextCalls'])==2 and 'combineCall' in p
  reads=next(x for x in json.loads((ROOT/'dual-active-ui-reads.json').read_text()) if x['version']==version)
  p['getterCalls']=[{'rva':x['rva'],'bytes':x['bytes'],
   'inactive':x['target'].endswith('GetInactiveProficiency')} for x in reads['queries']
   if x['target'] in ('CGameSprite::GetActiveProficiency','CGameSprite::GetInactiveProficiency')]
  assert len(p['getterCalls'])==12
  start=names['CScreenCreateChar::LevelUp'];end=keys[keys.index(start)+1]
  seq=list(md.disasm(pe.get_data(start-base,end-start),start))
  calls=[x for x in seq if x.mnemonic=='call' and x.operands[0].type==capstone.CS_OP_IMM
   and x.operands[0].imm==names['CGameSprite::AddNewSpecialAbilities']]
  assert len(calls)==2
  p['firstSpecialCall']={'rva':calls[0].address-base,'bytes':bytes(calls[0].bytes).hex()}
  p['untouchedSpecialReplay']={'rva':calls[1].address-base,'bytes':bytes(calls[1].bytes).hex()}
  profiles.append(p)
 def lua(x):
  if isinstance(x,dict):return '{'+','.join('['+json.dumps(k)+']='+lua(v) for k,v in x.items())+'}'
  if isinstance(x,list):return '{'+','.join(map(lua,x))+'}'
  return json.dumps(x)
 (ROOT/'dual_combined_profiles.lua').write_text('-- Source-derived private combined preview boundaries.\nreturn '+lua(profiles)+'\n')
 (ROOT/'dual-combined-profile-results.json').write_text(json.dumps({'profiles':profiles,'gameLaunched':False},indent=2)+'\n')
 print('Two source-bound GetNextLevel calls and one scoped CombineAll call verified per build')
if __name__=='__main__':main()
