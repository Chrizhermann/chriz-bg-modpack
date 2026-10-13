"""Audited item-family entry trampolines, with exact partial-prologue unwind.

Emits inert bytes. Does not install a hook or infer policy from an item prefix.
"""
import struct

SITES={
    'CGameSprite::UseItem':('48895c2418','0105020005340300',False),
    'CGameSprite::UseItemPoint':('48895c2410','0105020005340200',False),
    'CGameAIBase::FireItem':('4055564154415541574881ec80000000','0110060010f209f007d005c003600250',True),
    'CGameAIBase::FireItemPoint':('4055564154415541574883ec40','010d06000d7209f007d005c003600250',True),
    'CItem::GetAbilityEffect':('4053555657415641574883ec58','010d07000da209f007e005700460035002300000',True),
}


def plan(name,entry,relay,wrapper,observed,definitions=SITES):
    raw,unwind,frame=definitions[name];prefix=bytes.fromhex(raw)
    if observed!=prefix:raise ValueError('item-family native prologue changed: '+name)
    delta=relay-entry-5
    if not -(1<<31)<=delta<(1<<31):raise ValueError('item relay outside rel32 range')
    def jump(target):return b'\xff\x25'+bytes(4)+struct.pack('<Q',target)
    target=entry+len(prefix)
    if frame:
        resume=b'\xc7\x04\x24'+struct.pack('<I',target&0xffffffff)
        resume+=b'\xc7\x44\x24\x04'+struct.pack('<I',target>>32)+b'\xff\x64\x24\x00'
    else:resume=jump(target)
    return dict(prefix=prefix,frame=frame,patch=b'\xe9'+struct.pack('<i',delta)+b'\x90'*(len(prefix)-5),
        relay=jump(wrapper),trampoline=prefix+resume,unwind=bytes.fromhex(unwind),
        instruction_size=len(prefix)+(19 if frame else 6))
