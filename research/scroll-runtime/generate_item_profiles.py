"""Offline item ABI/call-edge certification from the two pinned executables."""
import hashlib,json
from pathlib import Path
import capstone,pefile
from generate_decode_profiles import EXES,EEEX,signature
from item_detours import SITES
ROOT=Path(__file__).resolve().parent
def main():
    profiles=[]
    for version,path,digest,_ in EXES:
        raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
        pe=pefile.PE(data=raw);base=pe.OPTIONAL_HEADER.ImageBase
        named={n:int(a,16) for line in (EEEX/('v'+version)/'bg2ee/function_names.db').read_text().splitlines()
               for a,_,n in [line.partition('\t')] if a.startswith('0x')}
        ordered=sorted(set(named.values()));engine=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
        spans=[];calls=[]
        for name in [*SITES,'CItem::GetItemType']:
            address=named[name];size=ordered[ordered.index(address)+1]-address
            spans.append(signature(pe,name,address-base,size))
            if name in SITES:assert pe.get_data(address-base,len(bytes.fromhex(SITES[name][0])))==bytes.fromhex(SITES[name][0])
            calls.append([i for i in engine.disasm(pe.get_data(address-base,size),address) if i.mnemonic=='call'])
        roots=[];continuations=[]
        for index in range(4):
            matches=[i for i in calls[index] if i.op_str==hex(named['CItem::GetAbilityEffect'])]
            assert len(matches)==1
            roots.append(matches[0].address+matches[0].size-base)
        for index,name in enumerate(['CGameAIBase::FireItem','CGameAIBase::FireItemPoint']):
            matches=[i for i in calls[index] if i.op_str==hex(named[name])]
            assert len(matches)==1
            continuations.append(matches[0].address+matches[0].size-base)
        profiles.append(dict(version=version,timestamp=pe.FILE_HEADER.TimeDateStamp,spans=spans,root_returns=roots,continuation_returns=continuations))
    (ROOT/'item-profiles.json').write_text(json.dumps(profiles,indent=2)+'\n')
    lines=['// Generated from six audited native bodies and their actual direct CALL edges.','#pragma once',
           'namespace cbm::scroll::binding {','struct ItemProfile { unsigned timestamp; DecodeSignature spans[6]; unsigned roots[4], continuations[2]; };',
           'inline constexpr ItemProfile item_profiles[] = {']
    for p in profiles:
        spans=','.join('{0x%x,0x%x,{%s}}'%(s['rva'],s['size'],','.join('0x'+s['sha256'][i:i+2] for i in range(0,64,2))) for s in p['spans'])
        lines.append('{%d,{%s},{%s},{%s}},'%(p['timestamp'],spans,','.join(hex(x) for x in p['root_returns']),','.join(hex(x) for x in p['continuation_returns'])))
    (ROOT/'item_profiles.hpp').write_text('\n'.join(lines+['};','}'])+'\n')
    lines=['// Generated from item_detours.py; covered by native execution and OS unwind tests.','#pragma once',
           'struct CBMS_ItemHookCode { unsigned char prefix[24]; unsigned prefix_size; unsigned char unwind[32]; unsigned unwind_size; bool frame; };',
           'inline constexpr CBMS_ItemHookCode cbms_item_hook_code[] = {']
    for prefix,unwind,frame in SITES.values():
        p,u=bytes.fromhex(prefix),bytes.fromhex(unwind)
        lines.append('{{%s},%d,{%s},%d,%s},'%(','.join(hex(b) for b in p),len(p),','.join(hex(b) for b in u),len(u),'true' if frame else 'false'))
    (ROOT/'item_hook_code.hpp').write_text('\n'.join(lines+['};'])+'\n')
if __name__=='__main__':main()
