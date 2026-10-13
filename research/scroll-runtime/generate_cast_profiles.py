"""Read-only ABI profile from both pinned images and pinned EEex fix sites."""
import hashlib,json,struct
from pathlib import Path
import pefile,capstone
from generate_decode_profiles import EXES,EEEX,signature
from cast_selection_detours import NAMES,CALL_OFFSETS,emit
from cast_entry_detours import SITES
ROOT=Path(__file__).resolve().parent
FIXES=(('E9C40F0000',34,5),('663BF8745B',3,5),('7CB24D85ED',43,5),('8B4B48488B442460',-20,7))
def main():
    profiles=[]
    for version,path,digest,_ in EXES:
        raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
        pe=pefile.PE(data=raw);base=pe.OPTIONAL_HEADER.ImageBase;image=pe.get_memory_mapped_image()
        named={n:int(a,16) for line in (EEEX/('v'+version)/'bg2ee/function_names.db').read_text().splitlines() for a,_,n in [line.partition('\t')] if a.startswith('0x')}
        order=sorted(set(named.values()));cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
        holes=[]
        for pattern,delta,size in FIXES:
            token=bytes.fromhex(pattern);at=image.find(token);assert at>=0 and image.find(token,at+1)<0
            at+=delta;assert image[at]==(0xE8 if size==5 and pattern in ('E9C40F0000','7CB24D85ED') else 0x74)
            holes.append(dict(rva=at,size=size,original=image[at:at+size].hex()))
        spans=[];entries=[];children=[];selection=[];extras=[];bodies=[]
        for index,name in enumerate([*SITES,'CSpell::GetAbilityCount']):
            start=named[name]-base;end=order[order.index(named[name])+1]-base;entries.append(start)
            body=pe.get_data(start,end-start);bodies.append(dict(name=name,rva=start,size=end-start))
            if name in SITES:assert body.startswith(bytes.fromhex(SITES[name][0]))
            pieces=[h for h in holes if start<=h['rva']<end];cursor=start
            for hole in sorted(pieces,key=lambda h:h['rva']):
                spans.append(signature(pe,name+' before EEex fix',cursor,hole['rva']-cursor));cursor=hole['rva']+hole['size']
            spans.append(signature(pe,name+' tail',cursor,end-cursor))
            if index<7:
                code=list(cs.disasm(body,base+start));calls=[i for i in code if i.mnemonic=='call' and i.op_str==hex(named['CSpell::GetAbilityEffect'])]
                assert len(calls)==1;children.append(calls[0].address+calls[0].size-base)
                call=base+start+CALL_OFFSETS[index];assert pe.get_data(call-base,5)==b'\xE8'+struct.pack('<i',named['CSpell::GetAbilityCount']-call-5);selection.append(call-base)
                if index>=5:
                    calls=[i for i in code if i.mnemonic=='call' and i.op_str==hex(named[NAMES[index-4]])];assert len(calls)==1;extras.append(calls[0].address+5-base)
        assert len(spans)==13
        profiles.append(dict(version=version,timestamp=pe.FILE_HEADER.TimeDateStamp,spans=spans,bodies=bodies,entries=entries[:8],getter=entries[8],selection=selection,children=children,extras=extras,eeex_fixes=holes))
    (ROOT/'cast-profiles.json').write_text(json.dumps(profiles,indent=2)+'\n')
    lines=['// Generated from reviewed native bodies and four pinned EEex fix boundaries.','#pragma once','namespace cbm::scroll::binding {',
        'struct CastProfile { unsigned timestamp,entries[8],getter,selection[7],children[7],extras[2],fixes[4],fix_sizes[4]; DecodeSignature spans[13]; };','inline constexpr CastProfile cast_profiles[] = {']
    def nums(values):return ','.join(hex(v) for v in values)
    for p in profiles:
        spans=','.join('{0x%x,0x%x,{%s}}'%(s['rva'],s['size'],','.join('0x'+s['sha256'][i:i+2] for i in range(0,64,2))) for s in p['spans'])
        lines.append('{%d,{%s},%s,{%s},{%s},{%s},{%s},{%s},{%s}},'%(p['timestamp'],nums(p['entries']),hex(p['getter']),nums(p['selection']),nums(p['children']),nums(p['extras']),nums(h['rva'] for h in p['eeex_fixes']),nums(h['size'] for h in p['eeex_fixes']),spans))
    (ROOT/'cast_profiles.hpp').write_text('\n'.join(lines+['};','}'])+'\n')
    lines=['// Generated from tested cast_entry_detours.py recipes.','#pragma once','struct CBMS_CastHookCode { unsigned char prefix[32]; unsigned prefix_size; unsigned char unwind[32]; unsigned unwind_size; bool frame; };','inline constexpr CBMS_CastHookCode cbms_cast_hook_code[] = {']
    for prefix,unwind,frame in SITES.values():
        a,b=bytes.fromhex(prefix),bytes.fromhex(unwind);lines.append('{{%s},%d,{%s},%d,%s},'%(nums(a),len(a),nums(b),len(b),'true' if frame else 'false'))
    (ROOT/'cast_hook_code.hpp').write_text('\n'.join(lines+['};'])+'\n')
    plan=emit(0,0x140001000,0x140010000,0x1122334455667788,0x140002000,b'\xe8'+struct.pack('<i',0x140002000-0x140001005))
    code=plan['code'];callback=code.index(struct.pack('<Q',0x1122334455667788));getter=code.index(struct.pack('<Q',0x140002000));selector=code.index(b'\xb9\x00\x00\x00\x00')+1
    lines=['// Generated from tested cast_selection_detours.py; exact instruction ranges.','#pragma once',
           'inline constexpr unsigned char cbms_selection_code[] = {%s};'%nums(code),
           'inline constexpr unsigned cbms_selection_callback=%d,cbms_selection_getter=%d,cbms_selection_selector=%d;'%(callback,getter,selector),
           'struct CBMS_SelectionUnwind { unsigned begin,end,size; unsigned char info[48]; };','inline constexpr CBMS_SelectionUnwind cbms_selection_unwind[] = {']
    for start,end,info in plan['segments']:
        assert len(info)<=48;lines.append('{%d,%d,%d,{%s}},'%(start,end,len(info),nums(info)))
    (ROOT/'cast_selection_code.hpp').write_text('\n'.join(lines+['};'])+'\n')
if __name__=='__main__':main()
