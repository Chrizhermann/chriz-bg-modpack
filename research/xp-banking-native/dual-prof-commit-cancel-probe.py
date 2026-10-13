"""Bounded native Cancel proficiency/list execution, without a game process.

Executes the actual CancelLevelUp proficiency loop and actual SetActive,
ModifyAllOfType, HandleList, ResolveEffect, and opcode233 bodies. The installed
WEAPPROF lookup is a declared mapping stub. ProcessEffectList is substituted
ONLY by its actual timed HandleList call, excluding the wider game pipeline.
"""
import json
from pathlib import Path

from unicorn import UC_HOOK_CODE
from unicorn import x86_const as x

from dual_prof_commit import Native, ACTOR, EFFECT, NODE, STACK, SCRATCH, MD


def check(version):
    n = Native(version)
    n.clear()
    screen, rules, saved = SCRATCH, SCRATCH+0x2000, SCRATCH+0x4000
    actor_vtable, effect_vtable = SCRATCH+0x5000, SCRATCH+0x5100
    n.put(ACTOR, actor_vtable, 8)
    n.put(actor_vtable+0x20, n.fn("CGameObject::GetAIType"), 8)
    n.put(ACTOR+0x38, 0xFF, 1)  # concrete nonempty AI type
    n.put(effect_vtable+0x10, n.fn("CGameEffectProficiency::ApplyEffect"), 8)
    n.put(effect_vtable+0x18, n.fn("CGameEffect::ResolveEffect"), 8)
    n.put(screen+0x988, saved, 8)
    n.put(rules+0x19CA, 46, 2)
    records = []
    for index in range(46):
        effect = EFFECT+index*0x180
        n.effect(effect, 89+index, 3)
        n.put(effect, effect_vtable, 8)
        n.put(saved+index*8, index % 3, 1)
        n.put(ACTOR+0x1218+index*4, 3)
        records.append(effect)
    # A duplicate class SET, a private native-inert carrier, and unrelated
    # temporary / additive records all keep their original node identities.
    extras = [EFFECT+(46+i)*0x180 for i in range(4)]
    n.effect(extras[0],89,4)
    n.effect(extras[1],0xFFFF,2)
    n.put(extras[1]+0x60,99)
    n.put(extras[1]+0x64,1)
    n.uc.mem_write(extras[1]+0x94,b"CBMDPRF\0")
    n.uc.mem_write(extras[1]+0xA8,b"0123456789abcdef0123456789abcdef")
    n.effect(extras[2],89,6,timing=1)
    n.effect(extras[3],89,1,mode=1)
    for effect in extras:
        n.put(effect,effect_vtable,8)
    records += extras
    n.list(records)
    n.put(ACTOR+0x4A10,NODE+(len(records)-1)*0x20,8)
    for index in range(len(records)):
        n.put(NODE+index*0x20+8,NODE+(index-1)*0x20 if index else 0,8)
    nodes_before = bytes(n.uc.mem_read(NODE,len(records)*0x20))
    before = [bytes(n.uc.mem_read(effect,0x158)) for effect in records]
    counts = {"lookup":0,"recalculation":0,"resolve":0,"apply":0}

    def return_value(uc,value):
        rsp=uc.reg_read(x.UC_X86_REG_RSP)
        uc.reg_write(x.UC_X86_REG_RAX,value)
        uc.reg_write(x.UC_X86_REG_RIP,n.get(rsp,8))
        uc.reg_write(x.UC_X86_REG_RSP,rsp+8)

    def lookup(uc,address,size,data):
        assert uc.reg_read(x.UC_X86_REG_RCX)==rules
        index=uc.reg_read(x.UC_X86_REG_RDX)
        assert index==counts["lookup"] and index<46
        counts["lookup"]+=1
        return_value(uc,89+index)

    def recalculate(uc,address,size,data):
        assert uc.reg_read(x.UC_X86_REG_RCX)==ACTOR
        assert uc.reg_read(x.UC_X86_REG_RDX)==1
        counts["recalculation"]+=1
        # A tail call executes real list traversal and real effect resolution;
        # no Python implementation decides whether nodes survive.
        uc.reg_write(x.UC_X86_REG_RCX,ACTOR+0x4A00)
        uc.reg_write(x.UC_X86_REG_RDX,ACTOR)
        uc.reg_write(x.UC_X86_REG_RIP,n.fn("CGameEffectList::HandleList"))

    def seen(uc,address,size,key):
        counts[key]+=1

    hooks=[]
    for name,callback,userdata in [
        ("CRuleTables::GetProficiencyId",lookup,None),
        ("CGameSprite::ProcessEffectList",recalculate,None),
        ("CGameEffect::ResolveEffect",seen,"resolve"),
        ("CGameEffectProficiency::ApplyEffect",seen,"apply")]:
        address=n.fn(name)
        hooks.append(n.uc.hook_add(UC_HOOK_CODE,callback,userdata,begin=address,end=address))
    function=n.fn("CScreenCreateChar::CancelLevelUp")
    start,end=function+0x1DA,function+0x23A
    instructions=list(MD.disasm(n.pe.get_data(start-n.base,end-start),start))
    assert instructions[0].op_str=="r14d, word ptr [r15 + 0x19ca]"
    assert any(i.mnemonic=="call" and int(i.op_str,16)==n.fn("CGameSprite::SetActiveProficiency") for i in instructions)
    rsp=STACK+8  # aligned function body stack; [rsp+50] holds denied actor
    n.put(rsp+0x50,ACTOR,8)
    for register,value in [(x.UC_X86_REG_RDI,screen),(x.UC_X86_REG_R15,rules),
        (x.UC_X86_REG_R12,0),(x.UC_X86_REG_RSP,rsp)]:
        n.uc.reg_write(register,value)
    try:
        n.uc.emu_start(start,end,count=500000)
    finally:
        for hook in hooks:n.uc.hook_del(hook)
    assert n.uc.reg_read(x.UC_X86_REG_RIP)==end
    assert counts=={"lookup":46,"recalculation":46,"resolve":2300,"apply":2300},counts
    assert bytes(n.uc.mem_read(NODE,len(records)*0x20))==nodes_before
    assert n.get(ACTOR+0x4A08,8)==NODE
    assert n.get(ACTOR+0x4A10,8)==NODE+(len(records)-1)*0x20
    assert n.get(ACTOR+0x4A18)==len(records)
    for index,effect in enumerate(records):
        expected=bytearray(before[index])
        if index<46 or index==46:
            stat=89+index if index<46 else 89
            # The selected fixture has old bits zero after the merge. Each
            # native setter restores its saved active pips without replacing.
            expected[0x1C:0x20]=((stat-89)%3).to_bytes(4,"little")
        if index==49:
            # Real opcode233 mode1 caches its first-call amount2 and clears
            # firstCall. These are native bookkeeping, not node replacement.
            expected[0x60:0x64]=(1).to_bytes(4,"little")
            expected[0xCC:0xD0]=bytes(4)
        actual=bytes(n.uc.mem_read(effect,0x158))
        assert actual==expected,(version,index,[(hex(i),a,b) for i,(a,b) in enumerate(zip(actual,expected)) if a!=b])
    return {"native_cancel_window":[hex(start-n.base),hex(end-n.base)],
            "class_records":47,"unchanged_extra_records":2,
            "additive_native_bookkeeping_records":1,"observed_calls":counts,
            "all_original_effect_and_node_identities_preserved":True,
            "stubs":["installed GetProficiencyId maps indices to stat89..134",
                     "ProcessEffectList routes to actual timed HandleList, not full game recalc"],
            "scope":"ordinary surviving timing9 records; arbitrary external effect mutation remains guarded",
            "game_launched":False}


if __name__=="__main__":
    report={version:check(version) for version in ("2.6","2.7")}
    Path(__file__).with_name("dual-prof-commit-cancel-results.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
