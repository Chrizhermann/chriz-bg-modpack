"""Read-only pinned EEex 1.2 export registration evidence (never loads DLL)."""
import os
import hashlib
import json
from pathlib import Path
import struct

import capstone as cs
from capstone import x86_const as x
import pefile

from local_paths import recorded

HERE = Path(__file__).resolve().parent
# Local game folders: set BG2EE_266_ROOT and BG2EE_273_ROOT.
DLL = Path(os.path.expandvars("%BG2EE_273_ROOT%/EEex.dll"))
SHA = "adc09b72951a28fed7b56ca1eba530f54c90505a495432f97401ea3c9b19a4c9"
LABELS = ("CGameEffectList::Override_Unmarshal", "EEex::Opcode_Hook_OnCopy",
          "EEex::Opcode_Hook_OnDestruct", "EEex::Sprite_Hook_OnDestruct",
          "CGameEffect::DecodeEffectFromBase")


def analyze():
    raw = DLL.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SHA
    pe = pefile.PE(data=raw)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = cs.Cs(cs.CS_ARCH_X86,cs.CS_MODE_64)
    md.detail = True
    md.skipdata = True
    labels = {}
    targets = {}
    for label in LABELS:
        encoded = (label+'\0').encode('utf-16-le')
        positions = []
        start = 0
        while (at:=raw.find(encoded,start)) >= 0:
            rva = pe.get_rva_from_offset(at)
            positions.append(rva)
            targets[base+rva] = label
            start = at+1
        labels[label] = dict(strings=positions,refs=[])
    instructions = []
    for section in pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        for ins in md.disasm(section.get_data(),base+section.VirtualAddress):
            if not ins.id:
                continue
            instructions.append(ins)
            for op in ins.operands:
                if op.type==x.X86_OP_MEM and op.mem.base==x.X86_REG_RIP:
                    target = ins.address+ins.size+op.mem.disp
                    if target in targets:
                        labels[targets[target]]["refs"].append(ins.address-base)
    def listing(start,size):
        return '\n'.join(f'{i.address-base:08X}  {i.bytes.hex():32} {i.mnemonic} {i.op_str}'
                         for i in md.disasm(pe.get_data(start,size),base+start))
    evidence = []
    for label, record in labels.items():
        evidence.append(label+"\n"+json.dumps(record))
        for ref in record['refs']:
            evidence.append(listing(ref,0x100))
    details = dict(source=recorded(DLL),sha256=SHA,base=base,timestamp=pe.FILE_HEADER.TimeDateStamp,
                   image_size=pe.OPTIONAL_HEADER.SizeOfImage,entry=pe.OPTIONAL_HEADER.AddressOfEntryPoint,
                   labels=labels)
    return pe, details, evidence, listing


def discovered_bodies(pe, details, listing):
    def lea_target(rva, prefix):
        assert pe.get_data(rva,3)==bytes.fromhex(prefix)
        return rva+7+struct.unpack('<i',pe.get_data(rva+3,4))[0]
    def signature(name,rva,size):
        for block in getattr(pe,'DIRECTORY_ENTRY_BASERELOC',[]):
            assert not any(e.type and rva<=e.rva<rva+size for e in block.entries)
        return dict(name=name,rva=rva,size=size,sha256=hashlib.sha256(pe.get_data(rva,size)).hexdigest())
    definitions = []
    for label in LABELS[:4]:
        refs = details['labels'][label]['refs']
        assert len(refs)==1
        registration = refs[0]
        override = label==LABELS[0]
        start = lea_target(registration+(0x64 if override else 0x11),'4c8d05' if override else '488d15')
        size = 606 if override else 80 if label==LABELS[1] else 64
        definitions.append(dict(label=label,body=signature(label,start,size),
                                registration=signature(label+' registration',registration,125 if override else 43),
                                prefix=pe.get_data(start,7).hex()))
    text=[]
    for definition in definitions:
        s=definition['body'];start=s['rva'];end=start+s['size']
        ranges=[dict(begin=e.struct.BeginAddress,end=e.struct.EndAddress,unwind=e.struct.UnwindData,
                     header=pe.get_data(e.struct.UnwindData,4).hex())
                for e in pe.DIRECTORY_ENTRY_EXCEPTION if e.struct.BeginAddress<end and e.struct.EndAddress>start]
        definition['unwind_ranges']=ranges
        text.append(definition['label']+'\n'+json.dumps(ranges,indent=2)+'\n'+listing(start,s['size']))
    text.append('Decode pointer registration helper\n'+listing(0xB8020,0xD0))
    return definitions,text


if __name__=='__main__':
    pe,details,evidence,listing = analyze()
    details['definitions'],bodies=discovered_bodies(pe,details,listing)
    (HERE/'eeex12-registration.json').write_text(json.dumps(details,indent=2)+'\n')
    (HERE/'eeex12-registration.txt').write_text('\n\n'.join(evidence)+'\n')
    (HERE/'eeex12-bodies.txt').write_text('\n\n'.join(bodies)+'\n')
    print(json.dumps(details,indent=2))
