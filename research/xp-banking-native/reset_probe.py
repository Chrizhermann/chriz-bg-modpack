"""Read-only MakeDualClass boundary profiles and actual pre-reset execution.

Unicorn runs the native prefix through its first XP reset. Called class/string
helpers are explicit stubs; this does not simulate rewards or a running game.
"""
import json
from pathlib import Path
import pefile
import capstone
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn import x86_const as x
from identity_probe import DEFAULT_CACHE, DEFAULT_EXES, MD, profile_entry, check_relocation

ROOT=Path(__file__).resolve().parent

def prefix_check(pe,start,base_xp):
    base=pe.OPTIONAL_HEADER.ImageBase
    uc=Uc(UC_ARCH_X86,UC_MODE_64)
    size=(pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095
    uc.mem_map(base,size)
    uc.mem_write(base,pe.get_memory_mapped_image())
    uc.mem_map(0x100000,0x20000); uc.mem_map(0x200000,0x6000); uc.mem_map(0x300000,0x4000)
    uc.reg_write(x.UC_X86_REG_RSP,0x110008)
    uc.reg_write(x.UC_X86_REG_RCX,0x300000)
    uc.reg_write(x.UC_X86_REG_RDX,0x200000)
    uc.reg_write(x.UC_X86_REG_R8,4)
    uc.mem_write(0x200570,base_xp.to_bytes(4,"little"))
    # Global Chitin pointer in the prefix is read before helpers. Give its game
    # pointer a bounded fixture. The executable's own data is otherwise unchanged.
    instructions=list(MD.disasm(pe.get_data(start,0xB0),base+start))
    chitin_load=next(i for i in instructions if i.mnemonic=="mov" and i.op_str.startswith("rax, qword ptr [rip") and i.address>=base+start+0x30)
    global_ptr=chitin_load.address+chitin_load.size+chitin_load.operands[1].mem.disp
    uc.mem_write(global_ptr,(0x300000).to_bytes(8,"little"))
    uc.mem_write(0x301090,(0x302000).to_bytes(8,"little"))
    calls=[]
    def hook(cpu,address,length,user):
        ins=next(MD.disasm(bytes(cpu.mem_read(address,length)),address))
        if ins.mnemonic=="call":
            calls.append(address)
            # Native prefix makes Set, string-init, GetClass, GetClass, GetLevel.
            # Only helper outputs are synthetic; the reset instruction is real.
            cpu.reg_write(x.UC_X86_REG_RAX,8 if len(calls)==5 else 2)
            cpu.reg_write(x.UC_X86_REG_RIP,address+length)
    uc.hook_add(UC_HOOK_CODE,hook)
    # Exact boundary known from both independently captured native bodies.
    reset=base+start+0xA6
    uc.emu_start(base+start,reset,count=500)
    assert uc.reg_read(x.UC_X86_REG_RIP)==reset
    assert int.from_bytes(uc.mem_read(0x200570,4),"little")==base_xp
    actual=bytes(uc.mem_read(reset,10))
    assert actual==bytes.fromhex("c7837005000000000000"),actual.hex()
    uc.emu_start(reset,reset+10,count=1)
    assert int.from_bytes(uc.mem_read(0x200570,4),"little")==0
    assert len(calls)==5

def caller_check(pe,call,preview,variant,patched):
    """Execute original argument-producing instructions and the real E8 CALL.

    The patched variant goes through a real near JMP thunk to an inert callback;
    both runs must forward identical native arguments and call-frame alignment.
    Callee bodies are intentionally not simulated by this ABI check.
    """
    base=pe.OPTIONAL_HEADER.ImageBase
    uc=Uc(UC_ARCH_X86,UC_MODE_64)
    uc.mem_map(base,(pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    uc.mem_write(base,pe.get_memory_mapped_image())
    uc.mem_map(0x100000,0x20000);uc.mem_map(0x200000,0x6000);uc.mem_map(0x300000,0x6000)
    uc.mem_map(0x600000,0x2000)
    stack=0x110000;actor=0x200000;screen=0x304000
    uc.reg_write(x.UC_X86_REG_RSP,stack);uc.reg_write(x.UC_X86_REG_R14,screen)
    actor_id=123+variant*127;new_class=[1,4,11][variant]
    uc.mem_write(actor+0x48,actor_id.to_bytes(4,"little"))
    uc.mem_write(screen+0xA0C,new_class.to_bytes(4,"little"))
    uc.mem_write(stack+(0x30 if preview else 0x40),actor.to_bytes(8,"little"))
    for ins in MD.disasm(pe.get_data(call["caller"],call["site"]-call["caller"]),base+call["caller"]):
        if ins.mnemonic=="mov" and ins.op_str.startswith("rcx, qword ptr [rip"):
            global_at=ins.address+ins.size+ins.operands[1].mem.disp
            uc.mem_write(global_at,(0x300000).to_bytes(8,"little"))
            uc.mem_write(0x3010B8,screen.to_bytes(8,"little"))
    target=base+call["target"]
    if patched:
        # Near allocation has no frame and jumps into a normal typed DLL entry.
        thunk=base+0x1000
        uc.mem_write(thunk,b"\x48\xB8"+(0x600000).to_bytes(8,"little")+b"\xFF\xE0")
        uc.mem_write(base+call["site"]+1,(thunk-(base+call["site"]+5)).to_bytes(4,"little",signed=True))
        target=0x600000
    seen=[]
    def hook(cpu,address,length,user):
        if address!=target:return
        rsp=cpu.reg_read(x.UC_X86_REG_RSP)
        assert rsp%16==8 and rsp==stack-8
        return_at=int.from_bytes(cpu.mem_read(rsp,8),"little")
        assert return_at==base+call["site"]+5
        seen.append(tuple(cpu.reg_read(reg) for reg in [x.UC_X86_REG_RCX,x.UC_X86_REG_RDX,x.UC_X86_REG_R8,x.UC_X86_REG_R9]))
        cpu.reg_write(x.UC_X86_REG_RSP,rsp+8);cpu.reg_write(x.UC_X86_REG_RIP,return_at)
    uc.hook_add(UC_HOOK_CODE,hook)
    uc.emu_start(base+call["caller"],base+call["site"]+5,count=100)
    assert len(seen)==1
    assert seen[0][:3]==(screen,actor_id,0x18) if preview else seen[0]==(screen,actor,new_class,1)
    assert uc.reg_read(x.UC_X86_REG_RSP)==stack
    return seen[0]

def main():
    profiles={}; report={}
    for version,exe in DEFAULT_EXES.items():
        folder="v2.6.6.0" if version=="2.6" else "v2.7.3.0"
        pe=pefile.PE(str(exe)); base=pe.OPTIONAL_HEADER.ImageBase
        names={}
        for line in (DEFAULT_CACHE/folder/"bg2ee/function_names.db").read_text().splitlines():
            address,_,name=line.partition("\t")
            if address.startswith("0x"): names.setdefault(name,[]).append(int(address,16)-base)
        entry=profile_entry(pe,names["CScreenCharacter::MakeDualClass"][0])
        checks=check_relocation(pe,entry)
        create=profile_entry(pe,names["CScreenCreateChar::MakeDualClass"][0])
        checks+=check_relocation(pe,create)
        remove=names["CScreenCreateChar::RemoveAbilities"][0]
        start=names["CScreenCreateChar::StartEditing"][0]
        done=names["CScreenCreateChar::OnDoneButtonClick"][0]
        button=names["CScreenCharacter::OnDualClassButtonClick"][0]
        deny=names["CGameObjectArray::GetDeny"][0]
        def callsite(caller,length,target,before,after):
            matches=[i for i in MD.disasm(pe.get_data(caller,length),base+caller)
                     if i.mnemonic=="call" and i.operands[0].type==capstone.x86.X86_OP_IMM and i.operands[0].imm==base+target]
            assert len(matches)==1
            at=matches[0].address-base
            return {"site":at,"target":target,"caller":at-before,"callerBytes":pe.get_data(at-before,before+5+after).hex(),
                    "targetBytes":pe.get_data(target,32).hex()}
        remove_call=callsite(done,0x1A00,remove,21,26)
        preview_call=callsite(button,0x77,start,28,6)
        for call,is_preview in [(remove_call,False),(preview_call,True)]:
            for variant in range(3):
                assert caller_check(pe,call,is_preview,variant,False)==caller_check(pe,call,is_preview,variant,True)
        cap=names["CRuleTables::GetXPCap"][0]
        # Entire 0xD0 method includes tail/embedded padding; runtime checks reject
        # a changed native cap method rather than calling an unreviewed ABI.
        profiles[version]={"gameTimestamp":pe.FILE_HEADER.TimeDateStamp,"gameSize":pe.OPTIONAL_HEADER.SizeOfImage,
            "entry":entry,"createEntry":create,"removeCall":remove_call,"previewCall":preview_call,
            "denyRva":deny,"denyBytes":pe.get_data(deny,0x70).hex(),"capRva":cap,"capBytes":pe.get_data(cap,0xD0).hex()}
        for xp in [0,1,161000,500000,600000,4294967295]:
            prefix_check(pe,entry["rva"],xp);prefix_check(pe,create["rva"],xp)
        report[version]={"entry_trampoline_checks":checks,"native_prefix_xp_reset_checks":12,
                         "actual_caller_argument_comparisons":6,
                         "remove_call":remove_call["site"],"preview_call":preview_call["site"]}
    def lua(v):
        if isinstance(v,str):return json.dumps(v)
        if isinstance(v,int):return str(v)
        return "{"+",".join("["+json.dumps(k)+"]="+lua(x) for k,x in v.items())+"}"
    (ROOT/"reset_profiles.lua").write_text("-- Generated by reset_probe.py from pinned native PE files.\nreturn "+lua(profiles)+"\n")
    (ROOT/"reset-check-results.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
