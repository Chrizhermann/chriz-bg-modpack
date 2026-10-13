"""Pin actual shipped EEex lifecycle export registration and entry wrappers."""
import hashlib,json,struct
from pathlib import Path
import pefile
from generate_decode_profiles import profile_inputs,signature
from local_paths import recorded

ROOT=Path(__file__).resolve().parent
DEFINITIONS=[('effect_copy',0xE620,0x50,0x30096,'EEex::Opcode_Hook_OnCopy'),
    ('effect_destroy',0xE670,0x40,0x300C1,'EEex::Opcode_Hook_OnDestruct'),
    ('actor_destroy',0xE8C0,0x40,0x301C3,'EEex::Sprite_Hook_OnDestruct')]
DEFINITIONS12=[('effect_copy',0xD0F0,0x50,0x2E063,'EEex::Opcode_Hook_OnCopy'),
    ('effect_destroy',0xD140,0x40,0x2E08E,'EEex::Opcode_Hook_OnDestruct'),
    ('actor_destroy',0xD390,0x40,0x2E190,'EEex::Sprite_Hook_OnDestruct')]


def main():
    profiles=[]
    for version,_,_,path,digest,eeex_version in profile_inputs():
        raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
        pe=pefile.PE(data=raw);entries=[]
        for name,rva,size,registration,label in DEFINITIONS12 if eeex_version=='1.2' else DEFINITIONS:
            # Exact registration: UTF16 label constructor, then LEA RDX of
            # function passed to exportPattern. Do not infer from near symbols.
            label_at=registration+7+struct.unpack('<i',pe.get_data(registration+3,4))[0]
            assert pe.get_data(registration,3)==bytes.fromhex('488d15')
            assert pe.get_data(label_at,(len(label)+1)*2).decode('utf-16-le')==label+'\0'
            function_at=registration+0x11
            assert pe.get_data(function_at,3)==bytes.fromhex('488d15')
            assert function_at+7+struct.unpack('<i',pe.get_data(function_at+3,4))[0]==rva
            head=pe.get_data(rva,7)
            assert head==bytes.fromhex('4c8bdc49895310' if name=='effect_copy' else '4c8bdc49894b08')
            entries.append(dict(name=name,body=signature(pe,name,rva,size),registration=signature(pe,name+' export',registration,0x2b),prefix=head.hex()))
        profiles.append(dict(version=version,eeex_version=eeex_version,source=recorded(path),sha256=digest,timestamp=pe.FILE_HEADER.TimeDateStamp,entries=entries))
    (ROOT/'lifecycle-profiles.json').write_text(json.dumps(profiles,indent=2)+'\n')
    lines=['// Generated from actual shipped EEex export registrations.','#pragma once','namespace cbm::scroll::binding {',
        'struct LifecycleProfile { unsigned timestamp; DecodeSignature bodies[3],registrations[3]; };','inline constexpr LifecycleProfile lifecycle_profiles[] = {']
    for p in profiles:
        def signatures(key):
            return ','.join('{0x%x,0x%x,{%s}}'%(s[key]['rva'],s[key]['size'],','.join('0x'+s[key]['sha256'][i:i+2] for i in range(0,64,2))) for s in p['entries'])
        lines.append('{%d,{%s},{%s}},'%(p['timestamp'],signatures('body'),signatures('registration')))
    (ROOT/'lifecycle_profiles.hpp').write_text('\n'.join(lines+['};','}'])+'\n')


if __name__=='__main__':main()
