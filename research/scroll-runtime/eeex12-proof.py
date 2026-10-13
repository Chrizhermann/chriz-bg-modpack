"""Bounded offline 1.2 comparison/proof; no DLL or game function is invoked."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

import capstone as cs
from capstone import x86_const as x
import pefile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parents[1]/'tests'))
from generate_decode_profiles import signature
from local_paths import resolve
from test_scroll_runtime_lifecycle_detours import execute


def normalized(pe,start,size):
    base=pe.OPTIONAL_HEADER.ImageBase
    md=cs.Cs(cs.CS_ARCH_X86,cs.CS_MODE_64);md.detail=True
    result=bytearray();references=[]
    for ins in md.disasm(pe.get_data(start,size),base+start):
        raw=bytearray(ins.bytes)
        for op in ins.operands:
            if op.type==x.X86_OP_MEM and op.mem.base==x.X86_REG_RIP:
                target=ins.address+ins.size+op.mem.disp-base
                references.append(dict(offset=ins.address-base-start,kind='rip',target=target,
                                       prefix=pe.get_data(target,80).split(b'\0',1)[0].decode('ascii',errors='replace')))
                raw[ins.disp_offset:ins.disp_offset+ins.disp_size]=bytes(ins.disp_size)
        if ins.mnemonic in ('call','jmp') and ins.operands[0].type==x.X86_OP_IMM:
            target=ins.operands[0].imm-base
            if not start<=target<start+size:
                references.append(dict(offset=ins.address-base-start,kind='branch',target=target))
                raw[ins.imm_offset:ins.imm_offset+ins.imm_size]=bytes(ins.imm_size)
        result.extend(raw)
    assert len(result)==size
    return bytes(result),references


def main():
    spec=importlib.util.spec_from_file_location('eeex12_audit',HERE/'eeex12-audit.py')
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    pe,details,_,listing=audit.analyze()
    definitions,_=audit.discovered_bodies(pe,details,listing)
    existing=next(p for p in json.loads((HERE/'decode-profiles.json').read_text())
                  if p['version']=='2.7.3.0' and p.get('eeex_version','1.3.1')=='1.3.1')
    current=pefile.PE(str(resolve(existing['eeex_source'])))
    life=next(p for p in json.loads((HERE/'lifecycle-profiles.json').read_text())
              if p['version']=='2.7.3.0' and p.get('eeex_version','1.3.1')=='1.3.1')
    comparisons=[]
    for old,new in zip(definitions,[existing['eeex_override']]+[e['body'] for e in life['entries']]):
        a,refs_a=normalized(pe,old['body']['rva'],old['body']['size'])
        b,refs_b=normalized(current,new['rva'],new['size'])
        assert a==b,old['label']
        comparisons.append(dict(label=old['label'],normalized_sha256=hashlib.sha256(a).hexdigest(),
                                equal=True,eeex12_references=refs_a,eeex131_references=refs_b))
    entries=[]
    for definition,name in zip(definitions[1:],('effect_copy','effect_destroy','actor_destroy')):
        entries.append(dict(name=name,body=definition['body'],registration=definition['registration'],prefix=definition['prefix']))
    profile=dict(version='2.7.3.0',eeex_version='1.2',source=details['source'],sha256=details['sha256'],timestamp=details['timestamp'],entries=entries)
    # Execute the actual unchanged 1.2 wrappers and existing trampoline recipe
    # in Unicorn. Substitute only their shared EEex Lua closure executor.
    cases=[]
    for i,entry in enumerate(entries):
        original,_,_=execute(profile,entry,False)
        hooked,points,plan=execute(profile,entry,True)
        assert original==hooked
        expected=(0xCAFE0303,0xCAFE0202) if i==0 else (0xCAFE0202,)
        assert hooked[0][2]==expected
        assert [p['offset'] for p in points]==[0,3,7]
        cases.append(dict(name=entry['name'],original_and_trampoline_equal=True,
                          preserved_native_argument_order=list(expected),trampoline=plan['trampoline'].hex(),
                          unwind=plan['unwind'].hex()))
    # Label registration calls the typed pattern resolver which writes exactly
    # the same global that the native V1 decoder branch reads.
    pointer=0x1320A8
    assert 0xDEB6+7+struct.unpack('<i',pe.get_data(0xDEB6+3,4))[0]==pointer
    assert pe.get_data(0xDEB6,3)==bytes.fromhex('488b05')
    assert 0xB8094+7+struct.unpack('<i',pe.get_data(0xB8094+3,4))[0]==pointer
    assert pe.get_data(0xB8094,3)==bytes.fromhex('488905')
    decode=dict(existing)
    decode.update(eeex_version='1.2',eeex_source=details['source'],eeex_sha256=details['sha256'],
                  eeex_timestamp=details['timestamp'],eeex_size=details['image_size'],eeex_entry=details['entry'],
                  eeex_override=definitions[0]['body'],eeex_registration=definitions[0]['registration'],
                  decode_pointer_rva=pointer)
    result=dict(decode_profile=decode,lifecycle_profile=profile,
                pointer_registration=signature(pe,'DecodeEffectFromBase pointer registration',0xB0AEF,0x2D),
                pointer_resolver=signature(pe,'DecodeEffectFromBase pointer resolver',0xB8020,0xC3),
                comparisons=comparisons,lifecycle_native_cases=cases,
                scope='Read-only pinned EEex1.2 DLL and Unicorn. Only matching installed BG2EE2.7.3.0 profile; no claim for another1.2 binary.')
    (HERE/'eeex12-profiles.json').write_text(json.dumps(result,indent=2)+'\n')
    print('4 normalized bodies identical; 3 original/trampoline native-wrapper pairs passed; decoder pointer matched.')


if __name__=='__main__':main()
