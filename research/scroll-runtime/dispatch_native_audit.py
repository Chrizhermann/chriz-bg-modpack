"""Read-only dispatch/lifetime ABI evidence from the actual pinned images.
Never maps executable memory or invokes any native function.
"""
import hashlib,json,struct
from pathlib import Path
import capstone,pefile
from generate_decode_profiles import EXES,EEEX,signature
ROOT=Path(__file__).resolve().parent

def audit(version,path,digest):
    raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
    pe=pefile.PE(data=raw);base=pe.OPTIONAL_HEADER.ImageBase
    rows=[(int(a,16),n) for line in (EEEX/('v'+version)/'bg2ee/function_names.db').read_text().splitlines()
          for a,_,n in [line.partition('\t')] if a.startswith('0x')]
    ordered=sorted({a for a,_ in rows});named={n:a for a,n in rows}
    cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);cs.detail=True
    def body(address):return pe.get_data(address-base,ordered[ordered.index(address)+1]-address)
    def instructions(address):return list(cs.disasm(body(address),address))
    dispatch=[named['CGameEffectCastSpell::ApplyEffect'],named['CGameEffectCastSpellPoint::ApplyEffect']]
    ctors={a for a,n in rows if n=='CAIAction::CAIAction'}
    message_default=[]
    for address in dispatch:
        code=instructions(address);matches=[]
        for i,ins in enumerate(code):
            if ins.mnemonic!='call' or ins.operands[0].type!=capstone.x86.X86_OP_IMM or ins.operands[0].imm not in ctors:continue
            prior=code[max(0,i-3):i]
            # Both actual bodies explicitly construct the inline action at
            # message+10h; their temporary stack actions have other locations.
            if any(p.mnemonic=='lea' and p.op_str in ('rcx, [r14 + 0x10]','rcx, [rsi + 0x10]') for p in prior):
                matches.append((ins.address+ins.size,ins.operands[0].imm))
        assert len(matches)==1;message_default.append(matches[0])
    assert message_default[0][1]==message_default[1][1]
    default=message_default[0][1]
    # Resolve the actual FireSpell vtable by its independently named Run and
    # subtype slots, not by a nearest folded-destructor symbol label.
    tables=[]
    for ins in instructions(dispatch[0]):
        if ins.mnemonic!='lea' or ins.operands[0].reg!=capstone.x86.X86_REG_RAX or ins.operands[1].type!=capstone.x86.X86_OP_MEM:continue
        mem=ins.operands[1].mem
        if mem.base!=capstone.x86.X86_REG_RIP:continue
        address=ins.address+ins.size+mem.disp
        data=pe.get_data(address-base,56)
        if len(data)==56:
            slots=struct.unpack('<7Q',data)
            if slots[3]==named['CMessageFireSpell::GetMsgSubType'] and slots[6]==named['CMessageFireSpell::Run']:
                tables.append((address,slots))
    assert len(tables)==1
    table,slots=tables[0];destroy=slots[0]
    definitions=[('apply146',dispatch[0]),('apply148',dispatch[1]),('action_default',default),
                 ('add_message',named['CMessageHandler::AddMessage']),('fire_message_run',slots[6]),('fire_message_destroy',destroy)]
    result=dict(version=version,sha256=digest,message_action_constructor_returns=[pc-base for pc,_ in message_default],
        fire_message_vtable_rva=table-base,fire_message_vtable_slots=[pc-base for pc in slots],functions=[])
    for label,address in definitions:
        end=ordered[ordered.index(address)+1]
        rf=next(r for r in pe.DIRECTORY_ENTRY_EXCEPTION if r.struct.BeginAddress==address-base)
        unwind_rva=rf.struct.UnwindData;head=pe.get_data(unwind_rva,4);count=head[2]
        unwind=pe.get_data(unwind_rva,4+((count+1)&~1)*2)
        result['functions'].append(dict(label=label,rva=address-base,size=end-address,prefix=body(address)[:32].hex(),
            unwind=unwind.hex(),signature=signature(pe,label,address-base,end-address),
            instructions=[f'{ins.address-base:08x} {ins.mnemonic} {ins.op_str}' for ins in instructions(address)[:16]]))
    result['fire_message_destroy_body']=[f'{ins.address-base:08x} {ins.mnemonic} {ins.op_str}' for ins in instructions(destroy)]
    return result

def main():
    for version,path,digest,_ in EXES:
        out=audit(version,path,digest)
        (ROOT/('dispatch-audit-'+version+'.json')).write_text(json.dumps(out,indent=2)+'\n')
        print(version,[(x['label'],hex(x['rva']),x['unwind']) for x in out['functions']])
if __name__=='__main__':main()
