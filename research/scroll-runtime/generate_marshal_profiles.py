"""Pin native Marshal ABI spans, preserving the two existing EEex hook sites."""
import hashlib,json
from pathlib import Path
import pefile
from generate_decode_profiles import EXES,EEEX,signature
from marshal_detours import PREFIX

ROOT=Path(__file__).resolve().parent


def main():
    profiles=[]
    for version,path,digest,_ in EXES:
        raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
        pe=pefile.PE(data=raw)
        names={name:int(address,16) for line in (EEEX/("v"+version)/"bg2ee/function_names.db").read_text().splitlines()
               for address,_,name in [line.partition("\t")] if address.startswith("0x")}
        entry=names["CGameEffectList::Marshal"]-pe.OPTIONAL_HEADER.ImageBase
        assert pe.get_data(entry,len(PREFIX))==PREFIX
        # Actual loader source hooks OverrideSize at JLE and WriteExtra at
        # allocation CALL. Do not demand pristine bytes at those owned sites.
        branch,call=entry+0x2A4,entry+0x2AD
        assert pe.get_data(branch,2)==b"\x0f\x8e" and pe.get_data(call,1)==b"\xe8"
        spans=[signature(pe,"Marshal prologue and filter/count",entry,branch-entry),
               signature(pe,"Marshal allocation argument",branch+6,call-(branch+6)),
               signature(pe,"Marshal native writer and return",call+5,entry+0x3A0-(call+5))]
        profiles.append(dict(version=version,rva=entry,timestamp=pe.FILE_HEADER.TimeDateStamp,
            spans=spans,branch_rva=branch,branch=pe.get_data(branch,6).hex(),call_rva=call,call=pe.get_data(call,5).hex()))
    (ROOT/"marshal-profiles.json").write_text(json.dumps(profiles,indent=2)+"\n")
    lines=['// Generated from pinned original code; two existing EEex sites stay owned by EEex.','#pragma once',
        'namespace cbm::scroll::binding {','struct MarshalProfile { unsigned timestamp,rva,branch_rva,call_rva; DecodeSignature spans[3]; unsigned char branch[6],call[5]; };',
        'inline constexpr MarshalProfile marshal_profiles[] = {']
    for p in profiles:
        spans=','.join('{0x%x,0x%x,{%s}}'%(s['rva'],s['size'],','.join('0x'+s['sha256'][i:i+2] for i in range(0,64,2))) for s in p['spans'])
        branch=','.join('0x'+p['branch'][i:i+2] for i in range(0,12,2));call=','.join('0x'+p['call'][i:i+2] for i in range(0,10,2))
        lines.append('{%d,0x%x,0x%x,0x%x,{%s},{%s},{%s}},'%(p['timestamp'],p['rva'],p['branch_rva'],p['call_rva'],spans,branch,call))
    (ROOT/"marshal_profiles.hpp").write_text('\n'.join(lines+['};','}'])+'\n')


if __name__=='__main__': main()
