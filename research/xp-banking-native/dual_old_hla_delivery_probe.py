"""Actual CompleteCharacterHighLevelAbilities branching on synthetic memory.

Native allocation/string/array services and final gameplay sinks are declared
adapters. The real instructions clone descriptors, classify GA/AP, select the
marker resource/timing, target AP at self, and destroy the catalog. No spell is
executed and no game/save is opened.
"""
import json
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn import x86_const as x
from dual_old_hla_probe import Eligibility,AI,BEFORE,AFTER,SPRITE,ARENA
from dual_prof_commit import MD

class Delivery(Eligibility):
    def __init__(self,version):
        super().__init__(version)
        self.n.uc.hook_del(self.hooks[5]) # count min hook is irrelevant to resource length min
        self.calls=[];self.freed=[];self.destroyed=[]
        for name,callback in [('CString::Left',self.left),('memcpy',self.copy),
            ('CObArray::SetAtGrow',self.grow),('CObArray::SetSize',self.resize),
            ('CGameEffect::CGameEffect',self.effect_ctor),('CGameSprite::AddSpecialAbility',self.ga),
            ('CGameAIBase::FireSpell',self.ap),('DSOUND_FreeDeviceHandle',self.free)]:
            address=self.n.names[name][0] if name=='CGameEffect::CGameEffect' else self.n.fn(name)
            self.n.uc.hook_add(UC_HOOK_CODE,callback,begin=address,end=address)
        address=self.n.names['operator_new'][0]
        self.n.uc.hook_add(UC_HOOK_CODE,self.allocate,begin=address,end=address)
        self.sink=AFTER+0x800;self.delete=AFTER+0x810
        self.n.uc.mem_write(self.sink,b'\xc3');self.n.uc.mem_write(self.delete,b'\xc3')
        self.n.uc.hook_add(UC_HOOK_CODE,self.marker,begin=self.sink,end=self.sink)
        self.n.uc.hook_add(UC_HOOK_CODE,self.delete_list,begin=self.delete,end=self.delete)

    def left(self,uc,address,size,data):
        source=self.string(self.n.get(self.reg(x.UC_X86_REG_RCX),8));length=self.reg(x.UC_X86_REG_R8)
        out=self.reg(x.UC_X86_REG_RDX);self.n.put(out,self.allocate_string(source[:length]),8);self.ret(out)
    def allocate(self,uc,address,size,data):
        size=self.reg(x.UC_X86_REG_RCX);at=self.heap;self.heap+=(size+15)&~15
        self.n.uc.mem_write(at,bytes(size));self.ret(at)
    def copy(self,uc,address,size,data):
        dst,src,size=(self.reg(r) for r in (x.UC_X86_REG_RCX,x.UC_X86_REG_RDX,x.UC_X86_REG_R8))
        self.n.uc.mem_write(dst,bytes(self.n.uc.mem_read(src,size)));self.ret(dst)
    def grow(self,uc,address,size,data):
        arr,index,row=(self.reg(r) for r in (x.UC_X86_REG_RCX,x.UC_X86_REG_RDX,x.UC_X86_REG_R8))
        assert arr==SPRITE+0x4A88 and index==len(self.clones)
        self.clones.append(bytes(self.n.uc.mem_read(row,0x40)))
        self.n.put(arr+0x10,index+1);self.ret()
    def resize(self,uc,address,size,data):
        assert self.reg(x.UC_X86_REG_RCX)==BEFORE and self.reg(x.UC_X86_REG_RDX)==0
        self.n.put(BEFORE+0x10,0);self.ret()
    def effect_ctor(self,uc,address,size,data):self.ret(self.reg(x.UC_X86_REG_RCX))
    def resref(self,at):return bytes(self.n.uc.mem_read(at,8)).rstrip(b'\0').decode('ascii')
    def ga(self,uc,address,size,data):
        assert self.reg(x.UC_X86_REG_RCX)==SPRITE and self.reg(x.UC_X86_REG_R8)==0
        self.calls.append(('GA',self.resref(self.reg(x.UC_X86_REG_RDX))));self.ret()
    def ap(self,uc,address,size,data):
        assert self.reg(x.UC_X86_REG_RCX)==SPRITE and self.reg(x.UC_X86_REG_R8)==SPRITE and self.reg(x.UC_X86_REG_R9)==0
        rsp=self.reg(x.UC_X86_REG_RSP)
        assert self.n.get(rsp+0x28)==0xFFFFFFFF and self.n.get(rsp+0x38)==1 and self.n.get(rsp+0x40)==0
        self.calls.append(('AP',self.resref(self.reg(x.UC_X86_REG_RDX))));self.ret()
    def marker(self,uc,address,size,data):
        assert self.reg(x.UC_X86_REG_RCX)==SPRITE
        effect=self.reg(x.UC_X86_REG_RDX)
        self.markers.append({'opcode':self.n.get(effect+0x10),'resource':self.resref(effect+0x30),'timing':self.n.get(effect+0x24)})
        self.ret()
    def free(self,uc,address,size,data):
        self.freed.append((self.reg(x.UC_X86_REG_RCX),self.reg(x.UC_X86_REG_RDX)));self.ret()
    def delete_list(self,uc,address,size,data):
        self.destroyed.append(self.reg(x.UC_X86_REG_RCX));self.ret()
    def run(self,effects,selected=None,dormant=True):
        self.next=ARENA;self.heap=SPRITE+0x10000;self.calls=[];self.markers=[];self.clones=[];self.freed=[];self.destroyed=[]
        self.n.uc.mem_write(AI,bytes(0x3000));self.n.uc.mem_write(SPRITE,bytes(0x5000))
        screen,listing,pointers,vtable,actor_vtable=AI,BEFORE,AFTER,AFTER+0x400,AFTER+0x500
        self.n.put(vtable,self.delete,8);self.n.put(listing,vtable,8)
        self.n.put(actor_vtable+0xE8,self.sink,8);self.n.put(SPRITE,actor_vtable,8)
        # Actual dual FIGHTER->MAGE dormant state is deliberately irrelevant to
        # this native helper: it has no class-usability check at all.
        self.n.put(SPRITE+0x568,8 if dormant else 0);self.n.put(SPRITE+0x4B5B,7,1)
        self.n.put(listing+8,pointers,8);self.n.put(listing+0x10,len(effects));self.n.put(screen+0x9E8,listing,8)
        originals=[]
        for i,effect in enumerate(effects):
            row=SPRITE+0x6000+i*0x80;originals.append(row);self.n.put(pointers+i*8,row,8)
            self.n.uc.mem_write(row,b'ICONTEST');self.n.put(row+8,100+i)
            for off,value in [(0x10,effect),(0x28,'GA_PRE'),(0x30,'AP_EX'),(0x38,'ALL_GOOD')]:self.n.put(row+off,self.allocate_string(value),8)
            for off,value in [(0x18,0xFFFFFF7F),(0x1C,99),(0x20,3)]:self.n.put(row+off,value)
        indices=list(range(len(effects))) if selected is None else selected
        assert len(indices)<=24
        for i,index in enumerate(indices):self.n.put(screen+0x9F0+i,index,1)
        self.n.put(screen+0xA08,len(indices),1)
        # Native caller owns the catalog; empty cleanup uses no actor pointer.
        self.n.call('CScreenCreateChar::CompleteCharacterHighLevelAbilities',screen,SPRITE if indices else 0)
        assert self.n.get(screen+0x9E8,8)==0 and self.destroyed==[listing]
        assert self.freed==[(row,0x40) for row in originals]
        assert len(self.clones)==len(indices)
        for cloned,index in zip(self.clones,indices):assert cloned==bytes(self.n.uc.mem_read(originals[index],0x40))
        return {'calls':self.calls,'markers':self.markers,'cloned':len(self.clones),'freed':len(self.freed),'dormant_fixture':dormant}

if __name__=='__main__':
    report={}
    for version in ('2.6','2.7'):
        probe=Delivery(version);cases=[]
        for effects,selected in [(['GA_alpha','AP_beta'],None),(['AP_second','GA_first'],[1,0]),(['GA_empty'],[]),(['GA_a']*24,None)]:
            got=probe.run(effects,selected);indices=list(range(len(effects))) if selected is None else selected
            expected=[(effects[i][:2],effects[i][3:11].upper()) for i in indices]
            assert got['calls']==expected,(version,got,expected)
            assert all(m['opcode']==313 and m['resource']==e[1] for m,e in zip(got['markers'],expected))
            assert len(got['markers'])==len(expected);cases.append(got)
        report[version]={'cases':cases,'native_executed':['CompleteCharacterHighLevelAbilities full body','CResRef CString copy/uppercase encoding','native min'],
          'adapters':['heap allocation/free','CString copy/Left/Right/destruction','CObArray storage','effect construction','AddSpecialAbility/FireSpell/AddEffect sinks'],
          'game_launched':False,'spells_executed':False}
    Path(__file__).with_name('dual_old_hla_delivery_probe_results.json').write_text(json.dumps(report,indent=2)+'\n')
    print('8 actual native HLA delivery/cleanup cases passed across both pinned builds.')
