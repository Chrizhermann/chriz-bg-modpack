"""Dispatch ABI profile, preserving the existing EEex mode0 call-site hooks."""
import json
from pathlib import Path
import capstone,pefile
from generate_decode_profiles import EXES,EEEX,signature
from dispatch_native_audit import audit
from dispatch_detours import SITES
ROOT=Path(__file__).resolve().parent
# Engine CString bodies the value-carried action witness relies on.
STRINGS=('copy','assign','destroy','assign_copy','copy_before_write','get_buffer','concat_in_place')
def main():
    profiles=[]
    for version,path,digest,_ in EXES:
        evidence=audit(version,path,digest);pe=pefile.PE(str(path));base=pe.OPTIONAL_HEADER.ImageBase
        named={n:int(a,16) for line in (EEEX/('v'+version)/'bg2ee/function_names.db').read_text().splitlines() for a,_,n in [line.partition('\t')] if a.startswith('0x')}
        cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);cs.detail=True
        functions=evidence['functions'];code=[list(cs.disasm(pe.get_data(f['rva'],f['size']),base+f['rva'])) for f in functions]
        def calls(index,target):return [i for i in code[index] if i.mnemonic=='call' and i.operands[0].type==capstone.x86.X86_OP_IMM and i.operands[0].imm==target]
        add146,add148=calls(0,named['CMessageHandler::AddMessage']),calls(1,named['CMessageHandler::AddMessage'])
        assert len(add146)==2 and len(add148)==1
        owned=[add146[1],add148[0]];spans=[]
        for index,f in enumerate(functions):
            if index<2:
                hook=owned[index].address-base;assert owned[index].size==5
                spans.append(signature(pe,f['label']+' before EEex mode0 route',f['rva'],hook-f['rva']))
                spans.append(signature(pe,f['label']+' after EEex mode0 route',hook+5,f['rva']+f['size']-hook-5))
            else:spans.append(f['signature'])
        returns=[]
        for index,target in [(4,named['CGameAIBase::FireSpell']),(0,named['CGameEffect::FireSpell']),(1,named['CGameAIBase::FireSpellPoint'])]:
            found=calls(index,target);assert len(found)==1;returns.append(found[0].address+found[0].size-base)
        profiles.append(dict(version=version,timestamp=pe.FILE_HEADER.TimeDateStamp,spans=spans,entries=[f['rva'] for f in functions],
            ctor_returns=evidence['message_action_constructor_returns'],fire_add_return=add146[0].address+5-base,
            fire_run_return=returns[0],effect_fire_return=returns[1],point_fire_return=returns[2],
            fire_vtable=evidence['fire_message_vtable_rva'],vtable_slots=evidence['fire_message_vtable_slots'],
            eeex_routes=[dict(rva=i.address-base,original=bytes(i.bytes).hex()) for i in owned],
            strings=[evidence['string_functions'][k]['signature'] for k in STRINGS],
            insert_vtable=evidence['insert_message_vtable_rva'],insert_slots=evidence['insert_message_vtable_slots'],
            empty_string=evidence['empty_sentinel_global']))
    (ROOT/'dispatch-profiles.json').write_text(json.dumps(profiles,indent=2)+'\n')
    lines=['// Generated from audited bodies; existing EEex mode0 routes remain owned by EEex.','#pragma once','namespace cbm::scroll::binding {',
           'struct DispatchProfile { unsigned timestamp,entries[6]; DecodeSignature spans[8]; unsigned ctors[2],add_return,run_return,effect_return,point_return,vtable,slots[7],routes[2]; DecodeSignature strings[7]; unsigned insert_vtable,insert_slots[7],empty_string; };',
           'inline constexpr DispatchProfile dispatch_profiles[] = {']
    for p in profiles:
        def numbers(values):return ','.join(hex(v) for v in values)
        spans=','.join('{0x%x,0x%x,{%s}}'%(s['rva'],s['size'],','.join('0x'+s['sha256'][i:i+2] for i in range(0,64,2))) for s in p['spans'])
        strings=','.join('{0x%x,0x%x,{%s}}'%(s['rva'],s['size'],','.join('0x'+s['sha256'][i:i+2] for i in range(0,64,2))) for s in p['strings'])
        lines.append('{%d,{%s},{%s},{%s},%s,{%s},{%s},{%s},%s,{%s},%s},'%(p['timestamp'],numbers(p['entries']),spans,numbers(p['ctor_returns']),numbers(p[k] for k in ['fire_add_return','fire_run_return','effect_fire_return','point_fire_return','fire_vtable']),numbers(p['vtable_slots']),numbers(x['rva'] for x in p['eeex_routes']),strings,hex(p['insert_vtable']),numbers(p['insert_slots']),hex(p['empty_string'])))
    (ROOT/'dispatch_profiles.hpp').write_text('\n'.join(lines+['};','}'])+'\n')
    lines=['// Generated from the tested dispatch_detours.py recipes.','#pragma once',
           'struct CBMS_DispatchHookCode { unsigned char prefix[24]; unsigned prefix_size; unsigned char unwind[32]; unsigned unwind_size; bool frame; };',
           'inline constexpr CBMS_DispatchHookCode cbms_dispatch_hook_code[] = {']
    for prefix,unwind,frame in SITES.values():
        p,u=bytes.fromhex(prefix),bytes.fromhex(unwind)
        lines.append('{{%s},%d,{%s},%d,%s},'%(','.join(hex(b) for b in p),len(p),','.join(hex(b) for b in u),len(u),'true' if frame else 'false'))
    (ROOT/'dispatch_hook_code.hpp').write_text('\n'.join(lines+['};'])+'\n')
if __name__=='__main__':main()
