"""Execute actual manual loader over synthetic memory with actual source-bound
profiles. Tests rollback/order, not real JIT or game execution."""
from pathlib import Path
import json
import pefile
from lupa.lua51 import LuaRuntime as Lua51
from lupa.luajit21 import LuaRuntime as LuaJIT
ROOT=Path(__file__).parent
HARNESS=r'''
memory={};original={};patches=0;configs=0;exposed=0;loads=0;protected=true;cursor=0x145000000
-- Real 64-bit Windows places DLLs near 0x7FF8xxxxxxxx: 15 decimal digits.
MANUAL_DLL,IDENTITY_DLL=0x7FF8A0000000,0x7FF8A1000000
MANUAL_EXPORT,IDENTITY_EXPORT,LUA_LABEL=0x7FF8A0001230,0x7FF8A1000200,0x140550000
jitCalls={}
function cbm_jit_text(t)
 local text={}
 for i,v in ipairs(t)do
  if type(v)=="number"then assert(v>=0 and v==math.floor(v),"Assembly number must be a non-negative integer");text[i]=("%.0f"):format(v)
  else assert(type(v)=="string","Unexpected assembly element "..type(v));text[i]=v end
 end
 text=table.concat(text)
 assert(not text:find("%d[%.eE]"),"Assembly contains a non-integer number (concatenated address?): "..text)
 for target in text:gmatch("call (%d+)")do jitCalls[#jitCalls+1]=tonumber(target)end
 return text
end
CBMBank_Identity={installed=true}
local base=0x140000000
function put(at,value,n)for i=0,n-1 do memory[at+i]=value%256;value=math.floor(value/256)end end
function hex(at,s)for i=1,#s,2 do memory[at+(i-1)/2]=tonumber(s:sub(i,i+1),16)end end
function setup(profile)
 P=profile
 put(base,0x5a4d,2);put(base+0x3c,0x100,4);put(base+0x100,0x4550,4);put(base+0x104,0x8664,2)
 put(base+0x108,P.gameTimestamp,4);put(base+0x150,P.gameSize,4)
 for _,p in pairs(P.entries)do hex(base+p.rva,p.bytes)end
 for _,p in pairs(P.functions)do hex(base+p.rva,p.bytes)end
 for _,p in ipairs(P.choiceCalls)do hex(base+p.rva,p.bytes)end
 hex(base+P.manualCall.rva,P.manualCall.bytes);hex(base+P.contribution.rva,P.contribution.bytes)
 for k,v in pairs(memory)do original[k]=v end
end
function EEex_ReadU8(at)return memory[at] or 0 end
local function read(at,n)local v=0;for i=n-1,0,-1 do v=v*256+EEex_ReadU8(at+i)end;return v end
function EEex_ReadU16(at)return read(at,2)end
function EEex_ReadU32(at)return read(at,4)end
function EEex_GetImageBase()return base end
function EEex_TryLabel(name)
 assert(name:sub(1,10)=="Hardcoded_","Must select actual active Lua provider")
 return LUA_LABEL
end
function EEex_LoadLibrary()loads=loads+1;return loads==1 and MANUAL_DLL or IDENTITY_DLL end
function EEex_GetProcAddressInternal(lib,name)
 if lib==IDENTITY_DLL then assert(name=="CBMI_Query" or name=="CBMI_CanMutate");return IDENTITY_EXPORT end
 assert(exports[name],"Missing real compiled export "..name);return MANUAL_EXPORT
end
function EEex_FlattenTable(t)return t end
function EEex_StoreBytesAssembly(at,n)return {"replay validated native prologue"}end
function EEex_JITNear(t)cursor=cursor+256;return cursor end
function EEex_Malloc(n)cursor=cursor+256;return cursor end
freed={};function EEex_Free(p)assert(not freed[p]);freed[p]=true end
function EEex_Write64(at,v)end
function EEex_JITNearAsLuaFunction(name,t)cbm_jit_text(t);_G[name]=function()configs=configs+1;return true end end
function EEex_GenLuaCall(name,options)
 assert(type(_G[name])=="function");for _,f in ipairs(options.args)do f(40)end;return {"protected callback"}
end
EEex_LuaCallReturnType={Boolean=0,Number=1}
function EEex_ExposeToLua(at,name)exposed=exposed+1;_G[name]=function()end end
function EEex_DisableCodeProtection()protected=false end
function EEex_EnableCodeProtection()protected=true end
local function cbm_checked(value,min,max)
    assert(type(value)=='number' and value==math.floor(value),'arg #2 must be an integer')
    if value>max then error(('arg #2 (%d) too large (max: %d)'):format(value,max)) end
    if value<min then error(('arg #2 (%d) too small (min: %d)'):format(value,min)) end
    return value
end
function EEex_WriteU8(at,value)assert(not protected);memory[at]=cbm_checked(value,0,255)end
function EEex_Write8(at,value)assert(not protected);memory[at]=cbm_checked(value,-128,127)%256 end
function EEex_JITAt(at,assembly)
 assert(not protected and configs==6 and exposed==5,"All bindings must precede native patching")
 patches=patches+1;memory[at]=0xcc;if failAt==patches then error("injected partial patch")end
end
function restored()assert(protected);for k,v in pairs(original)do assert(memory[k]==v,"Native byte not restored")end end
adapter={Begin=function()end,PrepareCommit=function()end,Complete=function()end,Cancel=function()end,Uncertain=function()end}
function install(loader,profiles)return loader.Install{researchOnly=true,dllPath="private-test-dll",identityDLLPath="identity-dll",profiles=profiles,adapter=adapter,callbacks={GenLuaCall=EEex_GenLuaCall}}end
'''
def main():
    dll=pefile.PE('C:/tmp/campaign-xp-banking-20261009/native-dual/dual_hp_observer.dll')
    export_names={e.name.decode():True for e in dll.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
    total=0
    for runtime in (Lua51,LuaJIT):
        for version in (1,2):
            for fail in (None,'mismatch',1,5,9):
                lua=runtime(unpack_returned_tuples=True);lua.globals().exports=lua.table_from(export_names)
                lua.execute(HARNESS)
                profiles=lua.execute((ROOT/'dual_manual_profiles.lua').read_text())
                lua.eval('setup')(profiles[version]);loader=lua.execute((ROOT/'dual_manual_hooks.lua').read_text())
                assert lua.globals().patches==0 and lua.globals().loads==0
                if fail=='mismatch':lua.execute('memory[0x140000000+P.manualCall.rva]=0')
                elif fail:lua.globals().failAt=fail
                try:lua.eval('install')(loader,profiles);succeeded=True
                except Exception:succeeded=False
                assert succeeded==(fail is None)
                if fail is None:
                    assert lua.globals().patches==9 and lua.globals().protected
                    # Six configuration calls, each to a real-address export, then lua_pushboolean.
                    table=lua.globals().jitCalls;calls=[table[i] for i in range(1,len(table)+1)]
                    assert calls==[0x7FF8A0001230,0x140550000]*6,calls
                elif fail=='mismatch':assert lua.globals().patches==0 and lua.globals().loads==0
                else:lua.eval('restored')()
                total+=1
    result={'scenarios':total,'runtimes':['Lua5.1','LuaJIT2.1'],'builds':['2.6','2.7'],
      'scope':'Actual Lua loader against synthetic host/memory and real DLL export names; no native installation'}
    (ROOT/'dual-manual-loader-check-results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
