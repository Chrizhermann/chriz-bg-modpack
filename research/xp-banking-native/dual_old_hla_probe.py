"""Actual native HLA-count arithmetic with declared table/string adapters.

No game process, resources, saves, or actor mutations are used. The executable
is read only. Installed-table values below are synthetic variation fixtures,
not an assertion about any user's current LUNUMAB.
"""
import json
import struct
from pathlib import Path

from unicorn import UC_HOOK_CODE
from unicorn import x86_const as x

from dual_prof_commit import Native, STACK, STOP, MD

AI, BEFORE, AFTER, RULES, ARENA, SPRITE = (0x600000,0x601000,0x602000,0x610000,0x620000,0x630000)


class Counter:
    def __init__(self,version):
        self.n=Native(version)
        self.n.uc.mem_map(0x600000,0x60000)
        self.next=ARENA
        self.row={"FIRST_LEVEL":20,"RATE":1.0,"CHANGE_LEVEL":40,"NEW_RATE":1.0}
        self.columns={}
        self.lookups=[]
        self.class_rows=[]
        self.constants={}
        for key in [*self.row,"CLASS_LEVELUP_ABBREVIATIONS","CLASS_LEVELUP_PREFIX","NUM_LEVELUP_ABILITIES"]:
            name=next(name for name in self.n.names if "dynamic_initializer" in name and ("CRuleTables::"+key+"''") in name)
            address=self.n.fn(name)
            instructions=list(MD.disasm(self.n.pe.get_data(address-self.n.base,0x30),address))
            data=next(i for i in instructions if i.mnemonic=="lea" and i.op_str.startswith("rdx, [rip"))
            output=next(i for i in instructions if i.mnemonic=="lea" and i.op_str.startswith("rcx, [rip"))
            text_at=data.address+data.size+data.operands[1].mem.disp
            out_at=output.address+output.size+output.operands[1].mem.disp
            self.n.put(out_at,text_at,8)
            self.constants[key]=self.string(text_at)
            self.columns[out_at]=key
        self.hooks=[]
        for name,callback in [("CRuleTables::GetClassString",self.class_string),
                              ("C2DArray::GetAt",self.table),
                              ("sscanf",self.parse),
                              ("CString::~CString",self.nop),
                              ("CGameObjectArray::GetDeny",self.lookup),
                              ("min",self.before_cap)]:
            address=self.n.fn(name)
            self.hooks.append(self.n.uc.hook_add(UC_HOOK_CODE,callback,begin=address,end=address))
        address=self.n.names["CString::operator="][0]
        self.hooks.append(self.n.uc.hook_add(UC_HOOK_CODE,self.assign,begin=address,end=address))

    def reg(self,register):return self.n.uc.reg_read(register)
    def string(self,address):
        return bytes(self.n.uc.mem_read(address,100)).split(b"\0",1)[0].decode("ascii")
    def allocate_string(self,value):
        address=self.next;self.next+=0x80
        self.n.uc.mem_write(address,str(value).encode("ascii")+b"\0")
        return address
    def ret(self,value=0):
        rsp=self.reg(x.UC_X86_REG_RSP)
        self.n.uc.reg_write(x.UC_X86_REG_RAX,value)
        self.n.uc.reg_write(x.UC_X86_REG_RIP,self.n.get(rsp,8))
        self.n.uc.reg_write(x.UC_X86_REG_RSP,rsp+8)
    def class_string(self,uc,address,size,data):
        assert self.reg(x.UC_X86_REG_RCX)==RULES
        cls=self.reg(x.UC_X86_REG_R8);kit=self.reg(x.UC_X86_REG_R9)
        self.class_rows.append((cls,kit))
        out=self.reg(x.UC_X86_REG_RDX)
        self.n.put(out,self.allocate_string("CLASS"+str(cls)),8)
        self.ret(out)
    def assign(self,uc,address,size,data):
        out=self.reg(x.UC_X86_REG_RCX)
        self.n.put(out,self.n.get(self.reg(x.UC_X86_REG_RDX),8),8)
        self.ret(out)
    def nop(self,uc,address,size,data):self.ret()
    def table(self,uc,address,size,data):
        assert self.reg(x.UC_X86_REG_RCX)==RULES+0x3008
        column=self.columns[self.reg(x.UC_X86_REG_RDX)]
        row=self.string(self.n.get(self.reg(x.UC_X86_REG_R8),8))
        self.lookups.append((row,column))
        text=self.allocate_string(self.row[column])
        out=self.next;self.next+=8;self.n.put(out,text,8);self.ret(out)
    def parse(self,uc,address,size,data):
        text=self.string(self.reg(x.UC_X86_REG_RCX));fmt=self.string(self.reg(x.UC_X86_REG_RDX))
        out=self.reg(x.UC_X86_REG_R8)
        assert fmt in ("%d","%u","%f"),fmt
        value=struct.pack("<f",float(text)) if fmt=="%f" else struct.pack("<I",int(text))
        self.n.uc.mem_write(out,value);self.ret(1)
    def lookup(self,uc,address,size,data):
        assert self.reg(x.UC_X86_REG_RCX)==42
        self.n.put(self.reg(x.UC_X86_REG_RDX),SPRITE,8);self.ret(0)
    def before_cap(self,uc,address,size,data):
        self.raw_count=self.n.get(self.reg(x.UC_X86_REG_RCX))
        assert self.n.get(self.reg(x.UC_X86_REG_RDX))==24

    def run(self,old,new,cls=2,dual=False,row=None):
        self.next=ARENA;self.lookups=[];self.class_rows=[];self.raw_count=None
        if row is not None:self.row=row
        self.n.uc.mem_write(AI,bytes(0x3000))
        self.n.put(AI+0xB,7 if dual else cls,1)
        self.n.put(AI+0xC,42 if dual else 0xFFFFFFFF)
        self.n.put(SPRITE+0x568,8) # real fighter->mage active-class gate
        if dual:
            for stats,level in [(BEFORE,old),(AFTER,new)]:
                self.n.call("CDerivedStats::SetLevel",stats,7,2,level)
                self.n.call("CDerivedStats::SetLevel",stats,7,1,5)
        else:
            self.n.call("CDerivedStats::SetLevel",BEFORE,cls,cls,old)
            self.n.call("CDerivedStats::SetLevel",AFTER,cls,cls,new)
        before=bytes(self.n.uc.mem_read(AI,0x3000))
        self.n.put(STACK+0x28,AI+0x100,8)
        answer=self.n.call("CRuleTables::GetNumLevelUpAbilities",RULES,AI,BEFORE,AFTER)
        after=bytearray(self.n.uc.mem_read(AI,0x3000));after[0x100]=before[0x100]
        assert bytes(after)==before # only caller-provided flags output changes
        assert self.n.get(AI+0x100,1)==1
        assert len(self.lookups)==4 and self.class_rows==[(1 if dual else cls,0x4000)]
        assert answer==min(self.raw_count,24)
        return answer


def checks(version):
    c=Counter(version);cases=[]
    for cls in [1,2,3,4,5,6,11,12,19,20,21]:
        for before,after,expected in [(18,19,0),(18,20,1),(20,23,3),(18,24,5),(0,70,24)]:
            actual=c.run(before,after,cls)
            assert actual==expected,(version,cls,before,after,actual)
            if after==70:assert c.raw_count==51
            cases.append({"class":cls,"before":before,"after":after,"count":actual,"raw_count":c.raw_count})
    native_dual=c.run(18,22,dual=True)
    old_projection=c.run(18,22)
    assert native_dual==0 and old_projection==3
    for before,after,expected in [(4,10,6),(6,10,5),(4,6,1),(4,5,0),(5,6,0)]:
        actual=c.run(before,after,row={"FIRST_LEVEL":5,"RATE":0.5,"CHANGE_LEVEL":8,"NEW_RATE":1.5})
        assert actual==expected,(version,before,after,actual)
        cases.append({"fractional_rate":True,"before":before,"after":after,"count":actual})
    return {"cases":len(cases)+2,"table_constants":c.constants,
            "native_dual_old18_to22_active5_count":native_dual,
            "private_old_fighter18_to22_count":old_projection,
            "fixtures":cases,"count_inputs":"rules, private AI, before stats, after stats, flags output",
            "stubs":["GetClassString uses synthetic class row", "installed C2DArray cells",
                     "CString assignment/destruction", "sscanf integer/float conversion",
                     "GetDeny maps synthetic dual actor id"],
            "native_executed":["GetNumLevelUpAbilities full body", "GetActiveInactiveClasses",
                               "GetLevel/GetLevelField", "SetLevel", "native float arithmetic and min24"],
            "game_launched":False}


class Catalog(Counter):
    """Execute actual old-kit catalog selection up to the resource demand."""
    def __init__(self,version):
        super().__init__(version)
        self.expected_class=11;self.expected_kit=0x34568000
        self.abbrev="ZZOLD"
        for name,callback in [("operator_new",self.new),
                              ("_mbscmp",self.compare),
                              ("CString::Format",self.format)]:
            if name=="operator_new":
                start=self.n.fn("CRuleTables::GetLevelUpAbilities")
                address=int(next(i.op_str for i in MD.disasm(self.n.pe.get_data(start-self.n.base,0x60),start) if i.mnemonic=="call"),16)
                assert address in self.n.names[name]
            else:address=self.n.fn(name)
            self.hooks.append(self.n.uc.hook_add(UC_HOOK_CODE,callback,begin=address,end=address))
        address=self.n.names["CString::CString"][1]
        self.hooks.append(self.n.uc.hook_add(UC_HOOK_CODE,self.construct,begin=address,end=address))
    def new(self,uc,address,size,data):
        assert self.reg(x.UC_X86_REG_RCX)==0x20
        out=self.next;self.next+=0x100;self.n.uc.mem_write(out,bytes(0x20));self.ret(out)
    def class_string(self,uc,address,size,data):
        assert self.reg(x.UC_X86_REG_R8)==self.expected_class
        assert self.reg(x.UC_X86_REG_R9)==self.expected_kit
        out=self.reg(x.UC_X86_REG_RDX)
        self.n.put(out,self.allocate_string("CUSTOM_OLD_KIT"),8);self.ret(out)
    def construct(self,uc,address,size,data):
        out=self.reg(x.UC_X86_REG_RCX);self.n.put(out,self.reg(x.UC_X86_REG_RDX),8);self.ret(out)
    def table(self,uc,address,size,data):
        assert self.reg(x.UC_X86_REG_RCX)==RULES+0x2FD0
        assert self.string(self.n.get(self.reg(x.UC_X86_REG_RDX),8))=="ABBREV"
        assert self.string(self.n.get(self.reg(x.UC_X86_REG_R8),8))=="CUSTOM_OLD_KIT"
        out=self.next;self.next+=8;self.n.put(out,self.allocate_string(self.abbrev),8);self.ret(out)
    def compare(self,uc,address,size,data):
        a=self.string(self.reg(x.UC_X86_REG_RCX));b=self.string(self.reg(x.UC_X86_REG_RDX))
        self.ret(0 if a==b else 1)
    def format(self,uc,address,size,data):
        assert self.string(self.reg(x.UC_X86_REG_RDX))=="%s%s"
        value=self.string(self.reg(x.UC_X86_REG_R8))+self.string(self.reg(x.UC_X86_REG_R9))
        out=self.reg(x.UC_X86_REG_RCX);self.n.put(out,self.allocate_string(value),8);self.ret()
    def run_catalog(self):
        self.n.put(SPRITE+0x4B50+0xB,self.expected_class,1)
        self.n.put(SPRITE+0x4B50+0xC,0xFFFFFFFF)
        self.n.put(SPRITE+0x79C,self.expected_kit>>16,2)
        self.n.put(SPRITE+0x79E,self.expected_kit&0xFFFF,2)
        before=bytes(self.n.uc.mem_read(SPRITE,0x5000))
        start=self.n.fn("CRuleTables::GetLevelUpAbilities")
        instructions=list(MD.disasm(self.n.pe.get_data(start-self.n.base,0x600),start))
        end=next(i.address for i in instructions if i.mnemonic=="call" and i.op_str==hex(self.n.fn("dimmResourceExists")))
        self.n.put(STACK,STOP,8)
        for register,value in [(x.UC_X86_REG_RCX,RULES),(x.UC_X86_REG_RDX,SPRITE),(x.UC_X86_REG_RSP,STACK)]:
            self.n.uc.reg_write(register,value)
        self.n.uc.emu_start(start,end,count=10000)
        assert self.n.uc.reg_read(x.UC_X86_REG_RIP)==end
        assert self.string(self.reg(x.UC_X86_REG_RCX))=="LUZZOLD"
        assert self.reg(x.UC_X86_REG_RDX)==0x3F4 # 2DA resource type
        assert bytes(self.n.uc.mem_read(SPRITE,0x5000))==before
        return {"entry_rva":hex(start-self.n.base),"resource_demand_rva":hex(end-self.n.base),
                "old_class":self.expected_class,"old_kit":hex(self.expected_kit),
                "synthetic_installed_abbreviation":self.abbrev,"requested_table":"LUZZOLD",
                "private_sprite_unchanged":True,
                "scope":"actual native class/kit/ABBREV/prefix selection; resource parsing and picker not executed",
                "extra_stubs":["allocator","ASCII string comparison/constructor/Format"]}


class Eligibility(Counter):
    def __init__(self,version):
        super().__init__(version)
        for key in ("LEVELUP_ALIGN_ALL_GOOD","LEVELUP_ALIGN_ALL_EVIL"):
            name=next(name for name in self.n.names if "dynamic_initializer" in name and ("CRuleTables::"+key+"''") in name)
            at=self.n.fn(name);ins=list(MD.disasm(self.n.pe.get_data(at-self.n.base,0x30),at))
            a=next(i for i in ins if i.op_str.startswith("rdx, [rip"));b=next(i for i in ins if i.op_str.startswith("rcx, [rip"))
            data=a.address+a.size+a.operands[1].mem.disp;target=b.address+b.size+b.operands[1].mem.disp
            self.n.put(target,data,8);self.constants[key]=self.string(data)
        for name,callback in [("CString::Right",self.right),("_mbscmp",self.compare)]:
            address=self.n.fn(name);self.hooks.append(self.n.uc.hook_add(UC_HOOK_CODE,callback,begin=address,end=address))
        address=self.n.names["CString::CString"][0]
        self.hooks.append(self.n.uc.hook_add(UC_HOOK_CODE,self.assign,begin=address,end=address))
    def allocate_string(self,value):
        value=str(value);at=self.next+16;self.next+=0x100
        self.n.put(at-8,len(value));self.n.uc.mem_write(at,value.encode("ascii")+b"\0");return at
    def right(self,uc,address,size,data):
        source=self.string(self.n.get(self.reg(x.UC_X86_REG_RCX),8));length=self.reg(x.UC_X86_REG_R8)
        out=self.reg(x.UC_X86_REG_RDX);self.n.put(out,self.allocate_string(source[-length:] if length else ""),8);self.ret(out)
    def compare(self,uc,address,size,data):
        a=self.string(self.reg(x.UC_X86_REG_RCX));b=self.string(self.reg(x.UC_X86_REG_RDX));self.ret(0 if a==b else 1)
    def run_predicate(self,effect="GA_A",prereq="*",excluded="*",max_rank=2,minimum=1,maximum=99,flags=1,
                      selected=(),earned=(),alignment="*",actor_alignment=0x11):
        self.next=ARENA
        screen,row,array,pointers,vtable=AI,BEFORE,AFTER,AFTER+0x100,AFTER+0x500
        self.n.uc.mem_write(AI,bytes(0x3000));self.n.uc.mem_write(SPRITE,bytes(0x5000))
        self.n.put(SPRITE,vtable,8);self.n.put(vtable+0x20,self.n.fn("CGameObject::GetAIType"),8)
        self.n.put(SPRITE+0x30+0x17,actor_alignment,1)
        for offset,value in [(0x10,effect),(0x28,prereq),(0x30,excluded),(0x38,alignment)]:self.n.put(row+offset,self.allocate_string(value),8)
        for offset,value in [(0x18,minimum),(0x1C,maximum),(0x20,max_rank)]:self.n.put(row+offset,value&0xFFFFFFFF)
        self.n.put(screen+0x9E0,flags,1);self.n.put(screen+0x9E8,array,8);self.n.put(array+8,pointers,8)
        assert len(selected)<=24
        for i,text in enumerate(selected):
            entry=self.next;self.next+=0x80;self.n.put(entry+0x10,self.allocate_string(text),8)
            self.n.put(pointers+i*8,entry,8);self.n.put(screen+0x9F0+i,i,1)
        self.n.put(screen+0xA08,len(selected),1)
        nodes=SPRITE+0x6000
        for i,resref in enumerate(earned):
            node=nodes+i*0x80;obj=node+0x20
            self.n.put(node,node+0x80 if i+1<len(earned) else 0,8);self.n.put(node+0x10,obj,8)
            self.n.put(obj+0x10,313);self.n.uc.mem_write(obj+0x30,resref.encode("ascii")[:8].ljust(8,b"\0"))
        self.n.put(SPRITE+0x4A08,nodes if earned else 0,8)
        return self.n.call("CScreenCreateChar::CheckAbilityEnabled",screen,SPRITE,row)


def eligibility_checks(version):
    e=Eligibility(version);cases=[]
    fixtures=[({},1),({"max_rank":0},0),({"minimum":2},0),
              ({"prereq":"GA_OLD"},0),({"prereq":"GA_OLD","selected":["GA_OLD"]},1),
              ({"prereq":"GA_OLD","selected":["AP_OLD"]},0),
              ({"prereq":"GA_OLD","earned":["old"]},1),
              ({"excluded":"AP_X","selected":["GA_X"]},1),
              ({"excluded":"AP_X","earned":["x"]},0),
              ({"selected":["GA_A"],"earned":["A"]},0),
              ({"selected":["ga_a"],"earned":["A"]},1)]
    for args,expected in fixtures:
        actual=e.run_predicate(**args);assert actual==expected,(version,args,actual)
        cases.append({"args":args,"allowed":actual})
    # Minimal selected-prefix projection preserves the exact native predicate:
    # prerequisite/exclusion representatives, plus adjusted remaining maxRank.
    prefixes=[[],["GA_A"],["GA_P"],["AP_X"],["GA_A"]*18+["GA_P","AP_X"],["GA_A"]*18+["GA_P"]]
    for prefix in prefixes:
        for rank in [1,20,40]:
            args={"effect":"GA_A","prereq":"GA_P","excluded":"AP_X","max_rank":rank,"selected":prefix}
            native=e.run_predicate(**args)
            representatives=[text for text in ("GA_P","AP_X") if text in prefix]
            matching=prefix.count("GA_A")
            projected=0 if matching>=rank else e.run_predicate(**{**args,"selected":representatives,"max_rank":rank-matching})
            assert native==projected,(version,args,native,projected)
            cases.append({"projection_prefix_size":len(prefix),"rank":rank,"allowed":native})
    alignments={}
    for key in ("LEVELUP_ALIGN_ALL_GOOD","LEVELUP_ALIGN_ALL_EVIL"):
        restriction=e.constants[key]
        alignments[restriction]={hex(alignment):e.run_predicate(alignment=restriction,actor_alignment=alignment) for alignment in (0x11,0x21,0x31,0x13,0x23,0x33,0x22)}
        blocked=(0x11,0x21,0x31) if key.endswith("ALL_GOOD") else (0x13,0x23,0x33)
        assert all(value==(0 if int(alignment,16) in blocked else 1) for alignment,value in alignments[restriction].items())
    return {"cases":len(cases)+sum(map(len,alignments.values())),"fixtures":cases,"alignment_results":alignments,
            "native_executed":["CheckAbilityEnabled", "AbilityCountInEffectList", "AbilityExistsInEffectList",
                               "CountInSelectedList", "ExistsInSelectedList", "CResRef::operator==", "GetAIType"],
            "stubs":["CString allocation/copy/Right/destruction", "ASCII _mbscmp"],"game_launched":False}


if __name__=="__main__":
    report={version:checks(version) for version in ("2.6","2.7")}
    for version in report:report[version]["old_kit_catalog"]=Catalog(version).run_catalog()
    for version in report:report[version]["eligibility"]=eligibility_checks(version)
    Path(__file__).with_name("dual_old_hla_probe_results.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({key:{"cases":value["cases"],"constants":value["table_constants"]} for key,value in report.items()},indent=2))
