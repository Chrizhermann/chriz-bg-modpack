"""Seven concrete preselection CALL bridges; emits inert bytes only.

Each patched CALL is the first CSpell::GetAbilityCount before the native
minimum-level loop. The bridge enters with an ordinary return address, preserves
all registers/flags/XMM0-5 around the callback, then tail-calls the real getter.
The callback may change only the audited saved scalar or its native working
memory. This avoids pretending a branch into an active native frame is a return.
"""
import struct
import capstone
from unwind_records import unwind_record

NAMES=("CGameEffect::FireSpell","CGameAIBase::FireSpell","CGameAIBase::FireSpellPoint",
       "CGameAIBase::ForceSpell","CGameAIBase::ForceSpellPoint","CGameSprite::Spell","CGameSprite::SpellPoint")
# Actual call offsets in both audited builds. Changing these requires a new
# native audit, not a loose search for an arbitrary getter call.
CALL_OFFSETS=(0x114,0x18C,0x160,0x342,0x187,0xC76,0xBE5)
REGISTERS=(0,1,2,3,5,6,7,8,9,10,11,12,13,14,15)
RESERVE=0x88

def emit(selector,site,stub,callback,getter,observed):
    if selector not in range(7) or not callback or not getter:raise ValueError('invalid concrete cast selection bridge')
    expected=b'\xE8'+struct.pack('<i',getter-site-5)
    if observed!=expected:raise ValueError('preselection is no longer the audited CSpell::GetAbilityCount CALL')
    delta=stub-site-5
    if not -(1<<31)<=delta<(1<<31):raise ValueError('selector relay outside rel32 range')
    code=bytearray();actions=[]
    for register in REGISTERS:
        code+=(b'\x41' if register>=8 else b'')+bytes([0x50+register%8])
        actions.append((len(code),bytes([(register<<4) if register in (3,5,6,7,12,13,14,15) else 2])))
    code+=b'\x9c';actions.append((len(code),b'\x02'))
    code+=b'\x48\x81\xec'+struct.pack('<I',RESERVE);actions.append((len(code),b'\x01'+struct.pack('<H',RESERVE//8)))
    for xmm in range(6):code+=bytes([0xF3,0x0F,0x7F,0x44+xmm*8,0x24,0x20+xmm*16])
    code+=b'\xb9'+struct.pack('<I',selector)
    code+=b'\x48\x8d\x94\x24'+struct.pack('<I',RESERVE)
    code+=b'\x48\xb8'+struct.pack('<Q',callback)
    call_offset=len(code);code+=b'\xff\xd0'
    for xmm in range(6):code+=bytes([0xF3,0x0F,0x6F,0x44+xmm*8,0x24,0x20+xmm*16])
    region_end=len(code);remaining=[(0,op) for _,op in actions];tails=[]
    at=len(code);code+=b'\x48\x81\xc4'+struct.pack('<I',RESERVE);tails.append((at,len(code),list(remaining)));remaining.pop()
    at=len(code);code+=b'\x9d';tails.append((at,len(code),list(remaining)));remaining.pop()
    for register in reversed(REGISTERS):
        at=len(code);code+=(b'\x41' if register>=8 else b'')+bytes([0x58+register%8]);tails.append((at,len(code),list(remaining)));remaining.pop()
    # This really is a tail call: our frame is gone and the original native
    # CALL return pointer remains. FF25 is the documented legal x64 epilogue.
    tail=len(code);code+=b'\xff\x25'+bytes(4)+struct.pack('<Q',getter)
    md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);segments=[]
    for ins in md.disasm(bytes(code[:tail+6]),0):
        at=ins.address
        if at<region_end:active=[(0,op) for end,op in actions if end<=at]
        elif at<tail:active=next(ops for start,stop,ops in tails if start<=at<stop)
        else:active=[]
        segments.append((at,at+ins.size,unwind_record(active)))
    if not segments or segments[-1][1]!=tail+6:raise ValueError('incomplete selector bridge instruction boundaries')
    return dict(site=site,stub=stub,patch=b'\xE8'+struct.pack('<i',delta),code=bytes(code),
                callback=callback,getter=getter,call_offset=call_offset,tail=tail,segments=segments)
