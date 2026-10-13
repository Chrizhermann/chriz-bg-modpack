"""Actual private entry/rules loaders with declared offline host substitutes.
Checks concrete export names, inert loading, dependency order and rollback.
No JIT execution, menu rendering or game installation is claimed.
"""
from pathlib import Path
import json
import pefile
from lupa.lua51 import LuaRuntime as Lua51
from lupa.luajit21 import LuaRuntime as LuaJIT
from dual_manual_loader_check import HARNESS
ROOT=Path(__file__).parent
MORE=r'''
CBMDManualQueryNative=function()end
function setup(profile)
 P=profile;local base=0x140000000
 put(base,0x5a4d,2);put(base+0x3c,0x100,4);put(base+0x100,0x4550,4);put(base+0x104,0x8664,2)
 put(base+0x108,P.gameTimestamp,4);put(base+0x150,P.gameSize,4)
 for _,p in pairs(P.functions)do hex(base+p.rva,p.bytes)end
 hex(base+P.eligibilityQuery.rva,P.eligibilityQuery.bytes)
 for k,v in pairs(memory)do original[k]=v end
end
function EEex_JITAt(at,assembly)
 assert(not protected and configs==1 and exposed==(routing and 2 or 1),"Bindings must precede native patching")
 patches=patches+1;memory[at]=0xcc;if failAt==patches then error("injected partial patch")end
end
function entryInstall(loader,profiles)
 EngineGlobals={g_pBaldurChitin={m_pObjectGame={address=0x100000}}}
 EEex_UDToPtr=function(s)return s.address end
 EEex_LuaCallReturnType.Number=1
 return loader.Install{researchOnly=true,dllPath="private-test-dll",identityDLLPath="identity-dll",profiles=profiles,
  router=routing and {Eligible=function()return 0 end,Route=function()return 0 end}or nil,
  callbacks={GenLuaCall=EEex_GenLuaCall}}
end
function entryCheck(loader)
 EngineGlobals={g_pBaldurChitin={m_pEngineCharacter={address=0x10000}}}
 EEex_UDToPtr=function(s)return s.address end
 local sprite={address=0x20000};local account={incarnation="18446744073709551614",oldLevel=8}
 CBMDOldEntryCheckNative=function(a,b,i,lo,hi)
  assert(a=="20000" and b=="10000" and i==account.incarnation and lo=="8" and hi=="11");return response
 end
 response="1";assert(loader.Check(sprite,account,11))
 response="0";assert(not loader.Check(sprite,account,11))
 response="-1";assert(not loader.Check(sprite,account,11))
 response="1";assert(not loader.Check(sprite,account,8))
end
function rulesCheck(loader)
 EngineGlobals={g_pBaldurChitin={m_pObjectGame={m_ruleTables={address=0x30000}}}}
 EEex_UDToPtr=function(s)return s.address end
 local s={address=0x20000};local account={activeClass=4,oldClass=2,oldLevel=10,oldUsableXP=550000,oldKit=16385}
 CBMDOldTargetNative=function(a,b,active,old,xp)
  assert(a=="20000" and b=="30000" and active=="4" and old=="2" and xp=="550000");return status,"10","11"
 end
 status="0";assert(loader.Target(s,account)==11)
 CBMDOldPlanNative=function(a,b,active,old,xp,kit)
  assert(a=="20000" and b=="30000" and active=="4" and old=="2" and xp=="550000" and kit=="16385");return "0","10","11","1","75"
 end
 CBMDOldCapNative=function(a,b,active,old,xp,kit,stat)
  assert(kit=="16385" and stat=="89");return "0","5"
 end
 local plan=assert(loader.Plan(s,account));assert(plan.target==11 and plan.profPoints==1 and plan.skillPoints==75)
 assert(loader.Cap(s,account,89)==5);assert(not pcall(loader.Cap,s,account,256))
 status="5";local result,why=loader.Target(s,account);assert(result==nil and why:find("5"))
 status="0";account.oldLevel=9;assert(not pcall(loader.Target,s,account))
 account.oldLevel=10;account.activeClass=nil;assert(not pcall(loader.Target,s,account))
end
'''
def main():
 exports={}
 for name in ('dual_hp_observer.dll','dual_native_proficiency.dll'):
  dll=pefile.PE('C:/tmp/campaign-xp-banking-20261009/native-dual/'+name)
  exports.update({e.name.decode():True for e in dll.DIRECTORY_ENTRY_EXPORT.symbols if e.name})
 total=0
 for runtime in (Lua51,LuaJIT):
  for v in (1,2):
   for routing,fail in [(r,f) for r in (False,True) for f in (None,'mismatch',1,'dependency')]+[(True,3)]:
    lua=runtime(unpack_returned_tuples=True);lua.globals().exports=lua.table_from(exports)
    lua.execute(HARNESS+MORE);profiles=lua.execute((ROOT/'dual_entry_profiles.lua').read_text());lua.eval('setup')(profiles[v])
    lua.globals().routing=routing
    loader=lua.execute((ROOT/'dual_entry_hooks.lua').read_text());assert lua.globals().loads==0
    if fail=='mismatch':lua.execute('memory[0x140000000+P.eligibilityQuery.rva]=0')
    elif fail=='dependency':lua.execute('CBMDManualQueryNative=nil')
    elif fail:lua.globals().failAt=fail
    try:lua.eval('entryInstall')(loader,profiles);ok=True
    except Exception:ok=False
    assert ok==(fail is None)
    if fail is None:
     assert lua.globals().patches==(3 if routing else 1) and lua.globals().protected;lua.eval('entryCheck')(loader)
    elif isinstance(fail,int):lua.eval('restored')()
    else:assert lua.globals().patches==0 and lua.globals().loads==0
    total+=1
   for failure in (None,'reject','exception'):
    lua=runtime(unpack_returned_tuples=True);lua.globals().exports=lua.table_from(exports)
    lua.execute(HARNESS+MORE);profiles=lua.execute((ROOT/'dual_entry_profiles.lua').read_text());lua.eval('setup')(profiles[v])
    bridge=lua.execute((ROOT/'dual_rules_bridge.lua').read_text());assert lua.globals().loads==0
    if failure:
     lua.globals().failure=failure
     lua.execute('function EEex_JITNearAsLuaFunction(name,t) _G[name]=function()configs=configs+1;if failure=="exception"then error("native rejection")end;return false end end')
    try:bridge.Install(lua.table_from({'researchOnly':True,'dllPath':'private-test-dll'}));ok=True
    except Exception:ok=False
    assert ok==(failure is None)
    if ok:lua.eval('rulesCheck')(bridge)
    lua.execute('local count=0;for _ in pairs(freed)do count=count+1 end;assert(count==1 and CBMDOldRulesConfigure==nil)')
    assert lua.globals().patches==0 and lua.globals().configs==1;total+=1
 report={'scenarios':total,'runtimes':['Lua5.1','LuaJIT2.1'],'builds':['2.6','2.7'],
  'scope':'Actual Lua modules, real compiled exports, synthetic host/patch memory; no game'}
 (ROOT/'dual-entry-loader-check-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
