"""Execute compiled observation thunks, compare to actual displaced2.6/2.7
instructions. Does not execute game processes or native HP/RNG routines."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
import capstone
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import *
from dual_proficiency_probe import load, EXES, SHAS, SOURCE

ROOT=Path(__file__).parent
STACK=0x60000000
STOP=0x70000000
GPRS=[UC_X86_REG_RAX,UC_X86_REG_RBX,UC_X86_REG_RCX,UC_X86_REG_RDX,
      UC_X86_REG_RSI,UC_X86_REG_RDI,UC_X86_REG_RBP,UC_X86_REG_R8,
      UC_X86_REG_R9,UC_X86_REG_R10,UC_X86_REG_R11,UC_X86_REG_R12,
      UC_X86_REG_R13,UC_X86_REG_R14,UC_X86_REG_R15]
VOL=[UC_X86_REG_RAX,UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,
     UC_X86_REG_R9,UC_X86_REG_R10,UC_X86_REG_R11]
XMMS=[UC_X86_REG_XMM0+i for i in range(16)]
def machine(image,base):
    u=Uc(UC_ARCH_X86,UC_MODE_64)
    u.mem_map(base,(len(image)+4095)&~4095);u.mem_write(base,image)
    u.mem_map(STACK,0x10000);u.mem_map(STOP,4096)
    for i,r in enumerate(GPRS):u.reg_write(r,0x1a00+i)
    for i,r in enumerate(XMMS):u.reg_write(r,(0x123456789abcdef+i)<<60)
    u.reg_write(UC_X86_REG_EFLAGS,0x246)
    return u
def exit_call(u,result=None):
    if result is not None:u.reg_write(UC_X86_REG_EAX,result)
    sp=u.reg_read(UC_X86_REG_RSP);at=struct.unpack('<Q',u.mem_read(sp,8))[0]
    u.reg_write(UC_X86_REG_RSP,sp+8);u.reg_write(UC_X86_REG_RIP,at)
def clobber(u):
    for r in VOL:u.reg_write(r,0xcafeface)
    for r in XMMS[:6]:u.reg_write(r,0xdeadfeed)
    u.reg_write(UC_X86_REG_EFLAGS,0x202)

def main():
    p=argparse.ArgumentParser();p.add_argument('--dll',required=True,type=Path);args=p.parse_args()
    dll=pefile.PE(str(args.dll));image=dll.get_memory_mapped_image();base=dll.OPTIONAL_HEADER.ImageBase
    exports={s.name.decode():base+s.address for s in dll.DIRECTORY_ENTRY_EXPORT.symbols if s.name}
    md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);md.detail=True
    profiles=[];checks=0
    for version in EXES:
        pe,by_name,spans=load(version)
        names={int(line.split('\t')[0],16):line.split('\t')[1] for line in
            (SOURCE/('v'+version)/'bg2ee/function_names.db').read_text().splitlines() if line.startswith('0x')}
        gamebase=pe.OPTIONAL_HEADER.ImageBase
        core=by_name['CRuleTables::RollHitPoints'];coreend=sorted(names)[sorted(names).index(core)+1]
        instructions=list(md.disasm(pe.get_data(core-gamebase,coreend-core),core))
        candidates=[(a,b) for a,b in zip(instructions,instructions[1:])
                    if (a.mnemonic,a.op_str,b.mnemonic,b.op_str)==('add','r13d, eax','inc','r15d')]
        assert len(candidates)==1
        a,b=candidates[0];displaced=bytes(a.bytes)+bytes(b.bytes);assert len(displaced)==6
        reset=by_name['CScreenCreateChar::ResetLevelUpPanel'];resetend=sorted(names)[sorted(names).index(reset)+1]
        resetins=list(md.disasm(pe.get_data(reset-gamebase,resetend-reset),reset))
        calls=[i for i in resetins if i.mnemonic=='call' and i.operands[0].type==capstone.CS_OP_IMM
               and i.operands[0].imm==by_name['CRuleTables::GetHitPoints']]
        assert len(calls)==1;call=calls[0];idx=resetins.index(call)
        # Confirm exact actor/CON/call context, not nearest-symbol guesses.
        previous=[(x.mnemonic,x.op_str) for x in resetins[idx-6:idx]]
        assert previous==[('movzx','eax, byte ptr [r14 + 0x795]'),('lea','r8, [rbp - 0x30]'),
           ('mov','r9, rsi'),('mov','byte ptr [rsp + 0x20], al'),('mov','rdx, r13'),('mov','rcx, r12')]
        profile={'version':version,'exe_sha256':SHAS[version],'getHP':by_name['CRuleTables::GetHitPoints']-gamebase,
           'gameTimestamp':pe.FILE_HEADER.TimeDateStamp,'gameSize':pe.OPTIONAL_HEADER.SizeOfImage,
           'manualCall':{'rva':call.address-gamebase,'bytes':bytes(call.bytes).hex()},
           'contribution':{'rva':a.address-gamebase,'bytes':displaced.hex()},
           'limits':'No installer or native reward publication; hook-site observation only'}
        profiles.append(profile)
        profile['entries']={}
        for short,symbol in [('reset','CScreenCreateChar::ResetLevelUpPanel'),('commit','CScreenCreateChar::LevelUp'),('cancel','CScreenCreateChar::CancelLevelUp')]:
            at=by_name[symbol];span=0
            for ins in md.disasm(pe.get_data(at-gamebase,32),at):
                assert not any(op.type==capstone.CS_OP_MEM and op.mem.base==capstone.x86_const.X86_REG_RIP for op in ins.operands)
                assert ins.mnemonic not in ('call','jmp')
                span+=ins.size
                if span>=5:break
            profile['entries'][short]={'rva':at-gamebase,'span':span,'bytes':pe.get_data(at-gamebase,span).hex()}
        profile['functions']={}
        for short,symbol in [('setActive','CGameSprite::SetActiveProficiency'),('setInactive','CGameSprite::SetInactiveProficiency'),('getActive','CGameSprite::GetActiveProficiency'),('getInactive','CGameSprite::GetInactiveProficiency'),('getHP','CRuleTables::GetHitPoints')]:
            at=by_name[symbol];profile['functions'][short]={'rva':at-gamebase,'bytes':pe.get_data(at-gamebase,32).hex()}
        choice=by_name['CScreenCreateChar::OnProficiencyPlusMinusButtonClick']
        choiceend=sorted(names)[sorted(names).index(choice)+1]
        choiceins=list(md.disasm(pe.get_data(choice-gamebase,choiceend-choice),choice))
        profcalls=[i for i in choiceins if i.mnemonic=='call' and i.operands[0].type==capstone.CS_OP_IMM
            and i.operands[0].imm in (by_name['CGameSprite::SetActiveProficiency'],by_name['CGameSprite::SetInactiveProficiency'])]
        assert len(profcalls)==4
        assert any(i.mnemonic=='mov' and i.op_str=='rdi, rcx' for i in choiceins[:25])
        profile['choiceCalls']=[]
        for call in profcalls:
            inactive=call.operands[0].imm==by_name['CGameSprite::SetInactiveProficiency']
            profile['choiceCalls'].append({'rva':call.address-gamebase,'bytes':bytes(call.bytes).hex(),'inactive':inactive})
            for pips in (0,1,5,7):
                u=machine(image,base);start=STACK+0x8000
                u.reg_write(UC_X86_REG_RSP,start-8);u.mem_write(start-8,struct.pack('<Q',STOP))
                u.reg_write(UC_X86_REG_RDI,0x12340000)
                for reg,value in ((UC_X86_REG_RCX,0x56780000),(UC_X86_REG_RDX,101),(UC_X86_REG_R8,pips),(UC_X86_REG_R9,1)):
                    u.reg_write(reg,value)
                name='CBMDC_Inactive' if inactive else 'CBMDC_Active';seen=[]
                def prof(uc,at,size,data):
                    if at==exports[name]:
                        sp=uc.reg_read(UC_X86_REG_RSP);assert sp%16==8
                        assert [uc.reg_read(r) for r in (UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9)]==[0x56780000,101,pips,1]
                        assert struct.unpack('<Q',uc.mem_read(sp+0x28,8))[0]==0x12340000
                        seen.append(True);clobber(uc);exit_call(uc)
                u.hook_add(UC_HOOK_CODE,prof);u.emu_start(exports[name+'Thunk'],STOP,count=1000)
                assert seen==[True] and u.reg_read(UC_X86_REG_RSP)==start and u.reg_read(UC_X86_REG_RDI)==0x12340000
                checks+=1
        for level in (1,11,12,254,255):
            for hp,total in ((1,0),(7,77),(300,65530)):
                start=STACK+0x8000
                baseline=machine(displaced,0x40000000)
                baseline.reg_write(UC_X86_REG_RSP,start);baseline.reg_write(UC_X86_REG_R15,level)
                baseline.reg_write(UC_X86_REG_R13,total);baseline.reg_write(UC_X86_REG_RAX,hp)
                baseline.emu_start(0x40000000,0x40000000+6)
                u=machine(image,base);u.reg_write(UC_X86_REG_RSP,start-8);u.mem_write(start-8,struct.pack('<Q',STOP))
                u.reg_write(UC_X86_REG_R15,level);u.reg_write(UC_X86_REG_R13,total);u.reg_write(UC_X86_REG_RAX,hp)
                seen=[]
                def hook(uc,at,size,data):
                    if at==exports['CBMDH_Record']:
                        assert uc.reg_read(UC_X86_REG_RSP)%16==8
                        seen.append((uc.reg_read(UC_X86_REG_ECX),uc.reg_read(UC_X86_REG_EDX)))
                        clobber(uc);exit_call(uc)
                u.hook_add(UC_HOOK_CODE,hook)
                u.emu_start(exports['CBMDH_ContributionThunk'],STOP,count=1000)
                assert seen==[(level,hp)]
                for r in GPRS+XMMS+[UC_X86_REG_RSP,UC_X86_REG_EFLAGS]:
                    assert u.reg_read(r)==baseline.reg_read(r),(version,level,hp,r)
                checks+=1
        for constitution in (1,19,255):
            u=machine(image,base);start=STACK+0x8000
            u.reg_write(UC_X86_REG_RSP,start-8);u.mem_write(start-8,struct.pack('<Q',STOP))
            u.mem_write(start+0x20,bytes([constitution]))
            u.reg_write(UC_X86_REG_R14,0x12345678)
            expected=[u.reg_read(r) for r in (UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9)]
            seen=[]
            def manual(uc,at,size,data):
                if at==exports['CBMDH_Capture']:
                    sp=uc.reg_read(UC_X86_REG_RSP);assert sp%16==8
                    assert [uc.reg_read(r) for r in (UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9)]==expected
                    assert struct.unpack('<Q',uc.mem_read(sp+0x28,8))[0]==constitution
                    assert struct.unpack('<Q',uc.mem_read(sp+0x30,8))[0]==0x12345678
                    seen.append(True);clobber(uc);exit_call(uc,12)
            u.hook_add(UC_HOOK_CODE,manual);u.emu_start(exports['CBMDH_ManualCallThunk'],STOP,count=1000)
            assert seen==[True] and u.reg_read(UC_X86_REG_RAX)==12 and u.reg_read(UC_X86_REG_RSP)==start
            assert u.reg_read(UC_X86_REG_R14)==0x12345678;checks+=1
    out={'profiles':profiles,'instruction_checks':checks,
         'scope':'Compiled HP/proficiency observation thunks versus actual native boundaries; no native HP/RNG/UI acceptance',
         'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for prefix in ('dual_hp_*','dual_choice_*') for p in ROOT.glob(prefix) if p.is_file()}}
    (ROOT/'dual-hp-check-results.json').write_text(json.dumps(out,indent=2)+'\n')
    def lua(value):
        if isinstance(value,dict):return '{'+','.join('['+json.dumps(k)+']='+lua(v) for k,v in value.items())+'}'
        if isinstance(value,list):return '{'+','.join(lua(v) for v in value)+'}'
        if isinstance(value,bool):return 'true' if value else 'false'
        return json.dumps(value)
    (ROOT/'dual_manual_profiles.lua').write_text('-- Generated by dual_hp_probe.py from read-only audited executable bytes.\nreturn '+lua(profiles)+'\n')
    print(f'{checks} compiled HP/proficiency observation thunk checks passed against2.6/2.7 boundaries')
if __name__=='__main__':main()
