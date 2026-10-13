"""Offline signatures for the native decoder and existing shipped EEex route."""
import os
import hashlib
import json
from pathlib import Path
import struct

import pefile

from local_paths import recorded

ROOT = Path(__file__).resolve().parent
EEEX = Path("C:/tmp/scroll-hook-research-20261009/EEex/EEex/loader")
EXES = [
    # Local game folders: set BG2EE_266_ROOT and BG2EE_273_ROOT.
    ("2.6.6.0", Path(os.path.expandvars("%BG2EE_266_ROOT%/Baldur.exe")),
     "fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580",
     "85a49bbe19c310ec597160952c30793de1cd89451975208969b785c9d5f69626"),
    ("2.7.3.0", Path(os.path.expandvars("%BG2EE_273_ROOT%/Baldur.exe")),
     "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57",
     "62e110a27bc1ae0530afc276bb5adf41609d133ab499bae3456f046dedef0e35"),
]
EEEX12 = Path(os.path.expandvars("%BG2EE_273_ROOT%/EEex.dll"))
EEEX12_SHA = "adc09b72951a28fed7b56ca1eba530f54c90505a495432f97401ea3c9b19a4c9"
# Each alternate DLL is paired only with the engine build actually audited.
# 1.2 evidence: eeex12-registration.json / eeex12-profiles.json.
# Native Unmarshal bytes kept verbatim: the 14-byte entry plus the first eight
# tail bytes, which covers every EEex jump form the binder accepts (5-21 bytes).
UNMARSHAL_ORIGINAL = 22
DLL_RECIPES = {
    "1.3.1": (0x2D39D, 0xF2F0, 0x137358),
    "1.2": (0x2B3BD, 0xDCB0, 0x1320A8),
}


def profile_inputs():
    for version,path,sha,dllsha in EXES:
        yield version,path,sha,EEEX/('v'+version)/'EEex.dll',dllsha,"1.3.1"
    version,path,sha,_=EXES[1]
    yield version,path,sha,EEEX12,EEEX12_SHA,"1.2"


def signature(pe, name, rva, size):
    for block in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        if any(rva <= entry.rva < rva + size and entry.type for entry in block.entries):
            raise ValueError("signature spans an ASLR relocation: " + name)
    return dict(name=name, rva=rva, size=size, sha256=hashlib.sha256(pe.get_data(rva, size)).hexdigest())


def main():
    profiles = []
    for version, path, sha, dllpath, dllsha, eeex_version in profile_inputs():
        raw = path.read_bytes()
        dllraw = dllpath.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == sha
        assert hashlib.sha256(dllraw).hexdigest() == dllsha
        pe, dll = pefile.PE(data=raw), pefile.PE(data=dllraw)
        names = [(int(a, 16), n) for line in (EEEX / ("v"+version) / "bg2ee/function_names.db").read_text().splitlines()
                 for a, _, n in [line.partition("\t")] if a.startswith("0x")]
        ordered = sorted({a for a, _ in names})
        named = dict((name, a) for a, name in names)
        def body(name, skip=0):
            start = named[name]
            end = ordered[ordered.index(start)+1]
            return signature(pe, name, start-pe.OPTIONAL_HEADER.ImageBase+skip, end-start-skip)
        decoder = body("CGameEffect::DecodeEffectFromBase")
        unmarshal = body("CGameEffectList::Unmarshal", 14)
        decoder_head = pe.get_data(decoder["rva"], 7)
        assert decoder_head == bytes.fromhex("4c8bdc49895b10")
        # Verify actual UTF16 export label and the registered function pointer,
        # not a nearby symbol. All five chained hot/cold ranges are included.
        register,override,pointer=DLL_RECIPES[eeex_version]
        assert dll.get_data(register,3)==bytes.fromhex('488d15')
        label_rva=register+7+struct.unpack('<i',dll.get_data(register+3,4))[0]
        target=register+0x64
        assert dll.get_data(target,3)==bytes.fromhex('4c8d05')
        assert target+7+struct.unpack('<i',dll.get_data(target+3,4))[0]==override
        exported = signature(dll, "CGameEffectList::Override_Unmarshal", override, 606)
        registration = signature(dll, "Override_Unmarshal pattern registration", register, 125)
        label = dll.get_data(label_rva, 72).decode("utf-16-le").rstrip("\0")
        assert label == "CGameEffectList::Override_Unmarshal"
        ranges=[e.struct for e in dll.DIRECTORY_ENTRY_EXCEPTION if override<=e.struct.BeginAddress<override+606]
        assert [(e.BeginAddress-override,e.EndAddress-override) for e in ranges]==[(0,184),(184,235),(235,570),(570,578),(578,606)]
        # The actual V1 branch calls precisely this initialized native decoder.
        read_pointer=override+0x206
        assert dll.get_data(read_pointer,3)==bytes.fromhex('488b05')
        assert read_pointer+7+struct.unpack('<i',dll.get_data(read_pointer+3,4))[0]==pointer
        profiles.append(dict(version=version, source=recorded(path), sha256=sha, preferred_base=pe.OPTIONAL_HEADER.ImageBase,
            game_timestamp=pe.FILE_HEADER.TimeDateStamp, decoder=decoder, unmarshal_tail=unmarshal,
            unmarshal_head=pe.get_data(unmarshal["rva"]-14,14).hex(),
            # EEex's aligned absolute jump spans 14-21 bytes; the binder restores
            # exactly the bytes it occupies from these originals before hashing.
            unmarshal_original=pe.get_data(unmarshal["rva"]-14,UNMARSHAL_ORIGINAL).hex(),
            eeex_source=recorded(dllpath), eeex_sha256=dllsha,
            eeex_version=eeex_version, eeex_timestamp=dll.FILE_HEADER.TimeDateStamp, eeex_size=dll.OPTIONAL_HEADER.SizeOfImage,
            eeex_entry=dll.OPTIONAL_HEADER.AddressOfEntryPoint, eeex_override=exported, eeex_registration=registration,
            # Override uses this initialized EEex engine pointer at its actual decode call.
            decode_pointer_rva=pointer))
    (ROOT / "decode-profiles.json").write_text(json.dumps(profiles, indent=2)+"\n")
    def sig(value):
        digest = ",".join("0x"+value["sha256"][i:i+2] for i in range(0,64,2))
        return f'{{0x{value["rva"]:x},0x{value["size"]:x},{{{digest}}}}}'
    content = ['// Generated by generate_decode_profiles.py; audited shipped bodies only.', '#pragma once',
        'namespace cbm::scroll::binding {',
        'struct DecodeSignature { unsigned rva, size; unsigned char sha[32]; };',
        'struct DecodeProfile { const char* version; unsigned game_timestamp, eeex_timestamp, eeex_size, eeex_entry;',
        f' DecodeSignature decoder, unmarshal_tail, eeex_override, eeex_registration; unsigned char unmarshal_original[{UNMARSHAL_ORIGINAL}]; unsigned pointer_rva; }};',
        'inline constexpr DecodeProfile decode_profiles[] = {']
    for p in profiles:
        numbers=','.join(str(p[k]) for k in ('game_timestamp','eeex_timestamp','eeex_size','eeex_entry'))
        signatures=','.join(sig(p[k]) for k in ('decoder','unmarshal_tail','eeex_override','eeex_registration'))
        head=','.join('0x'+p['unmarshal_original'][i:i+2] for i in range(0,2*UNMARSHAL_ORIGINAL,2))
        content.append(f'{{"{p["version"]}",{numbers},{signatures},{{{head}}},0x{p["decode_pointer_rva"]:x}}},')
    content += ['};','}']
    (ROOT / "decode_profiles.hpp").write_text('\n'.join(content)+'\n')


if __name__ == "__main__":
    main()
