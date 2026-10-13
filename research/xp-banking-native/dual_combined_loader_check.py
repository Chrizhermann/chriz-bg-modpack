"""Actual optional Lua loader over synthetic host memory, real DLL exports.
The EEex after-call relay layouts are taken from its actual source, not JITed in
this protocol test. Native scene/UI execution is intentionally not claimed.
"""
from pathlib import Path
import json
import pefile
from lupa.lua51 import LuaRuntime as Lua51
from lupa.luajit21 import LuaRuntime as LuaJIT
from dual_manual_loader_check import HARNESS,ROOT

def main():
 exports={}
 for name in ('dual_hp_observer.dll','dual_prof_commit.dll','dual_native_proficiency.dll'):
  folder='native-prof-commit' if name=='dual_prof_commit.dll' else 'native-dual'
  pe=pefile.PE('C:/tmp/campaign-xp-banking-20261009/'+folder+'/'+name)
  exports[name]={e.name.decode():True for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
 total=0
 for Runtime in (Lua51,LuaJIT):
  for build in (1,2):
   for failure in (None,'bad-native','bad-relay','wrong-label',1,12,25):
    for patched in (False,True):
     lua=Runtime(unpack_returned_tuples=True);g=lua.globals()
     g.exports=lua.table_from(exports['dual_hp_observer.dll']);g.profExports=lua.table_from(exports['dual_prof_commit.dll'])
     g.rulesExports=lua.table_from(exports['dual_native_proficiency.dll'])
     lua.execute(HARNESS)
     profiles=lua.execute((ROOT/'dual_manual_profiles.lua').read_text())
     combined=lua.execute((ROOT/'dual_combined_profiles.lua').read_text())
     prof=lua.execute((ROOT/'dual_prof_commit_profiles.lua').read_text())
     lua.eval('setup')(profiles[build]);g.C=combined[build];g.Q=prof[build];g.afterCall=patched
     lua.execute('''
      labels={}
      for _,p in pairs(C.functions)do hex(0x140000000+p.rva,p.bytes)end
      for _,p in pairs(Q.functions)do hex(0x140000000+p.rva,p.bytes)end
      for _,p in ipairs(C.getterCalls)do hex(0x140000000+p.rva,p.bytes)end
      for _,p in ipairs(C.nextCalls)do hex(0x140000000+p.rva,p.bytes)end
      hex(0x140000000+C.combineCall.rva,C.combineCall.bytes)
      hex(0x140000000+C.firstSpecialCall.rva,C.firstSpecialCall.bytes)
      hex(0x140000000+C.untouchedSpecialReplay.rva,C.untouchedSpecialReplay.bytes)
      for _,p in pairs(C.functions)do local h=p.eeexAfterCall
       if h then local at=0x140000000+p.rva+h.offset;labels[h.label]=at
        if afterCall then local relay=at+0x10000000
         put(at,0xe9,1);put(at+1,(relay-at-5)%4294967296,4)
         put(relay,0xe8,1);put(relay+1,(0x140000000+h.calleeRva-relay-5)%4294967296,4)
        end
       end
      end
      original={};for k,v in pairs(memory)do original[k]=v end
      function EEex_TryLabel(n)return labels[n] or LUA_LABEL end
      -- 15-digit addresses like real 64-bit DLLs, so concatenated assembly would be caught.
      PROF_DLL,RULES_DLL=0x7FF8A2000000,0x7FF8A3000000
      function EEex_LoadLibrary(n)loads=loads+1;return n=='rules-dll' and RULES_DLL or n=='prof-dll' and PROF_DLL or n=='identity-dll' and IDENTITY_DLL or MANUAL_DLL end
      function EEex_GetProcAddressInternal(lib,n)
       if lib==IDENTITY_DLL then assert(n=='CBMI_Query' or n=='CBMI_CanMutate');return IDENTITY_EXPORT end
       assert((lib==RULES_DLL and rulesExports or lib==PROF_DLL and profExports or exports)[n],'Missing actual DLL export '..n)
       return lib+0x1230
      end
      function EEex_JITAt(at,assembly)
       assert(not protected and configs==8 and exposed==9,'Bindings must precede patches')
       patches=patches+1;memory[at]=0xcc;if failAt==patches then error('injected write failure')end
      end
     ''')
     g.loader=lua.execute((ROOT/'dual_manual_hooks.lua').read_text());g.extension=lua.execute((ROOT/'dual_combined_hooks.lua').read_text())
     g.profiles=profiles;g.combined=combined;g.prof=prof
     if failure=='bad-native':lua.execute('memory[0x140000000+C.functions.stats_copy.rva]=0')
     elif failure=='bad-relay':
      if not patched:continue
      lua.execute('memory[labels[C.functions.stats_copy.eeexAfterCall.label]+0x10000000]=0x90')
     elif failure=='wrong-label':
      if not patched:continue
      lua.execute('labels[C.functions.stats_copy.eeexAfterCall.label]=1')
     elif isinstance(failure,int):g.failAt=failure
     try:
      lua.execute('''loader.Install{researchOnly=true,dllPath='manual-dll',identityDLLPath='identity-dll',
       profiles=profiles,adapter=adapter,callbacks={GenLuaCall=EEex_GenLuaCall},
       combined={module=extension,profiles=combined,profProfiles=prof,profDLLPath='prof-dll',rulesDLLPath='rules-dll'}}''')
      ok=True
     except Exception as e:
      ok=False
      if failure is None:raise
     assert ok==(failure is None)
     if ok:
      assert g.patches==25 and g.protected
      # Every configuration call reaches a real-address export, then lua_pushboolean.
      table=g.jitCalls;calls=[table[i] for i in range(1,len(table)+1)]
      exports_called={0x7FF8A0000000+0x1230,0x7FF8A2000000+0x1230,0x7FF8A3000000+0x1230}
      assert len(calls)==2*g.configs and set(calls[0::2])<=exports_called and set(calls[1::2])=={0x140550000},calls
     elif isinstance(failure,int):lua.eval('restored')()
     else:assert g.patches==0 and g.loads==0
     total+=1
 result={'scenarios':total,'scope':'Actual Lua modules, synthetic host memory and real DLL exports; no game/hook installation'}
 (ROOT/'dual-combined-loader-check-results.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
if __name__=='__main__':main()
