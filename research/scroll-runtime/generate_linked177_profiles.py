"""Offline opcode177 parent/decode boundary; no game is loaded or modified."""
import hashlib,json
from pathlib import Path
import capstone,pefile
from generate_decode_profiles import EXES,EEEX,signature
ROOT=Path(__file__).resolve().parent
def main():
    profiles=[]
    for version,path,digest,_ in EXES:
        raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==digest;pe=pefile.PE(data=raw);base=pe.OPTIONAL_HEADER.ImageBase
        named={n:int(a,16) for line in (EEEX/('v'+version)/'bg2ee/function_names.db').read_text().splitlines() for a,_,n in [line.partition('\t')] if a.startswith('0x')};order=sorted(set(named.values()))
        start=named['CGameEffectApplyEffect::ApplyEffect'];end=order[order.index(start)+1];body=pe.get_data(start-base,end-start)
        assert body.startswith(bytes.fromhex('48895c2418'))
        calls=[i for i in capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64).disasm(body,start) if i.mnemonic=='call' and i.op_str==hex(named['CGameEffect::DecodeEffectFromBase'])]
        assert len(calls)==1 and calls[0].size==5
        decoder=named['CGameEffect::DecodeEffectFromBase'];decodeend=order[order.index(decoder)+1]
        profiles.append(dict(version=version,timestamp=pe.FILE_HEADER.TimeDateStamp,parent=signature(pe,'opcode177 ApplyEffect',start-base,end-start),decoder=signature(pe,'native decoder before scroll hooks',decoder-base,decodeend-decoder),call=calls[0].address-base))
    (ROOT/'linked177-profiles.json').write_text(json.dumps(profiles,indent=2)+'\n')
    def sig(s):return '{0x%x,0x%x,{%s}}'%(s['rva'],s['size'],','.join('0x'+s['sha256'][i:i+2] for i in range(0,64,2)))
    lines=['// Generated exact opcode177 parent and decoder signatures.','#pragma once','namespace cbm::scroll::binding {','struct Linked177Profile { unsigned timestamp,call; DecodeSignature parent,decoder; };','inline constexpr Linked177Profile linked177_profiles[] = {']
    for p in profiles:lines.append('{%d,%d,%s,%s},'%(p['timestamp'],p['call'],sig(p['parent']),sig(p['decoder'])))
    (ROOT/'linked177_profiles.hpp').write_text('\n'.join(lines+['};','}'])+'\n')
if __name__=='__main__':main()
