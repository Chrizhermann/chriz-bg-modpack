"""Read-only extraction of direct native HLA query boundary signatures."""
import json
import struct
import bisect
from pathlib import Path
from dual_prof_commit import Native, MD

FUNCTIONS = {
    "num_abilities": ("CRuleTables::GetNumLevelUpAbilities", None),
    "set_level": ("CDerivedStats::SetLevel", None),
    "class_string": ("CRuleTables::GetClassString", None),
    "get_at": ("C2DArray::GetAt", None), "scan": ("sscanf", None),
    "cstring_destroy": ("CString::~CString", None),
    "get_abilities": ("CRuleTables::GetLevelUpAbilities", None),
    "complete_abilities": ("CScreenCreateChar::CompleteCharacterHighLevelAbilities", None),
    "ability_construct": ("CAbilityData::CAbilityData", None),
    # Exact overloads also identified by actual call sites in the native parser
    # and completion helper. Same ordered source overload set on both builds.
    "cstring_construct_chars": ("CString::CString", 1),
    "cstring_assign_chars": ("CString::operator=", 1),
    "resref_construct_cstring": ("CResRef::CResRef", 0),
    "check_enabled": ("CScreenCreateChar::CheckAbilityEnabled", None),
    "get_ai_type": ("CGameObject::GetAIType", None),
    "array_construct": ("CDWordArray::CDWordArray", None),
    "array_grow": ("CObArray::SetAtGrow", None),
    "release": ("DSOUND_FreeDeviceHandle", None),
}

def profile(version):
    n=Native(version)
    addresses=sorted({a for values in n.names.values() for a in values})
    functions={}
    for key,(name,index) in FUNCTIONS.items():
        start=n.fn(name) if index is None else n.names[name][index]
        end=next(a for a in addresses if a>start)
        functions[key]={"name":name,"rva":start-n.base,"bytes":n.pe.get_data(start-n.base,end-start).hex()}
    catalog=n.fn("CRuleTables::GetLevelUpAbilities")
    ins=list(MD.disasm(n.pe.get_data(catalog-n.base,0x80),catalog))
    alloc=next(i.operands[0].imm for i in ins if i.mnemonic=="call")
    end=next(a for a in addresses if a>alloc)
    functions["allocate"]={"name":"operator_new (actual catalog call)","rva":alloc-n.base,"bytes":n.pe.get_data(alloc-n.base,end-alloc).hex()}
    vt=next(i for i in ins if i.mnemonic=="lea"and i.op_str.startswith("rax, [rip"))
    vtable=vt.address+vt.size+vt.operands[1].mem.disp
    destructor=struct.unpack("<Q",n.pe.get_data(vtable-n.base,8))[0]
    end=next(a for a in addresses if a>destructor)
    functions["list_destruct"]={"name":"CGameAbilityList deleting destructor","rva":destructor-n.base,"bytes":n.pe.get_data(destructor-n.base,end-destructor).hex()}
    callers={v:k for k,values in n.names.items() for v in values}
    target=n.fn("CScreenCreateChar::CheckAbilityEnabled");calls=[]
    for section in n.pe.sections:
        if not section.Characteristics&0x20000000:continue
        data=section.get_data();start=n.base+section.VirtualAddress
        for i,b in enumerate(data[:-4]):
            if b==0xE8 and start+i+5+struct.unpack_from("<i",data,i+1)[0]==target:
                at=start+i;owner=addresses[bisect.bisect_right(addresses,at)-1]
                assert callers[owner] in ("CScreenCreateChar::ResetLevelUpPanel","CScreenCreateChar::UpdateHighLevelAbilitiesPanel")
                calls.append({"rva":at-n.base,"bytes":data[i:i+5].hex(),"caller":callers[owner],
                              "contextRva":at-n.base-24,"contextBytes":data[i-24:i+13].hex()})
    assert len(calls)==2
    constants={}
    for key in ("FIRST_LEVEL","RATE","CHANGE_LEVEL","NEW_RATE"):
        name=next(k for k in n.names if "dynamic_initializer" in k and "CRuleTables::"+key+"''" in k)
        start=n.fn(name)
        ins=list(MD.disasm(n.pe.get_data(start-n.base,0x30),start))
        lea=next(i for i in ins if i.mnemonic=="lea" and i.op_str.startswith("rcx, [rip"))
        constants[key.lower()]=lea.address+lea.size+lea.operands[1].mem.disp-n.base
    return {"version":version,"gameTimestamp":n.pe.FILE_HEADER.TimeDateStamp,
            "gameSize":n.pe.OPTIONAL_HEADER.SizeOfImage,"functions":functions,"constants":constants,
            "listVtable":vtable-n.base,"listDestructor":destructor-n.base,"activeCalls":calls}

def lua(value):
    if isinstance(value,dict):return "{"+",".join("["+json.dumps(k)+"]="+lua(v) for k,v in value.items())+"}"
    if isinstance(value,list):return "{"+",".join(map(lua,value))+"}"
    return json.dumps(value)

if __name__=="__main__":
    result=[profile(version) for version in ("2.6","2.7")]
    Path(__file__).with_suffix(".lua").write_text("-- Generated from read-only PE boundaries; no registration.\nreturn "+lua(result)+"\n")
    print("Extracted",sum(len(p["functions"]) for p in result),"direct native HLA boundaries.")
