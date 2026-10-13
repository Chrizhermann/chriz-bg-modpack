-- Inert progression assembly for bank_bootstrap. Preflight captures every owned
-- native site before the parent starts its all-or-nothing startup transaction.
local M={}
local function choose(list,stamp,size)
 local found
 for _,p in pairs(list)do if p.gameTimestamp==stamp and p.gameSize==size then
  assert(not found,"Ambiguous progression build");found=p
 end end
 assert(found,"Unreviewed progression build");return found
end
local function verify(at,hex)
 for i=1,#hex,2 do assert(EEex_ReadU8(at+(i-1)/2)==tonumber(hex:sub(i,i+1),16),"Progression startup ABI mismatch")end
end
function M.Preflight(load,image,stamp,size,dllDirectory,remember)
 assert(type(EEex_Menu_AddAfterMainFileLoadedListener)=="function"
  and type(EEex_Menu_AfterMainFileLoadedListeners)=="table","Native menu lifecycle unavailable")
 local p={}
 for key,name in pairs({rules="dual_rules_bridge",skills="dual_skill_rows_bridge",hla="dual_old_hla",
  hlaHooks="dual_old_hla_hooks",hlaReceipts="dual_old_hla_receipts",rows="dual_retired_rows",
  receipts="dual_manual_receipts",ledger="dual_manual_ledger",manual="dual_manual_hooks",combined="dual_combined_hooks",
  entry="dual_entry_hooks",flow="dual_retired_flow",picker="dual_retired_picker",controller="dual_retired_controller"})do
  p[key]=load("xp-banking-native/"..name..".lua")
 end
 p.manualProfiles=load("xp-banking-native/dual_manual_profiles.lua")
 p.combinedProfiles=load("xp-banking-native/dual_combined_profiles.lua")
 p.profProfiles=load("xp-banking-native/dual_prof_commit_profiles.lua")
 p.entryProfiles=load("xp-banking-native/dual_entry_profiles.lua")
 p.hlaProfiles=load("xp-banking-native/dual_old_hla_profiles.lua")
 local directory=dllDirectory:gsub("[/\\]+$","")
 p.dlls={manual=directory.."/dual_hp_observer.dll",rules=directory.."/dual_native_proficiency.dll",
  skills=directory.."/dual_skill_rows.dll",hla=directory.."/dual_old_hla.dll",prof=directory.."/dual_prof_commit.dll"}
 p.combinedOptions={module=p.combined,profiles=p.combinedProfiles,profProfiles=p.profProfiles,
  profDLLPath=p.dlls.prof,rulesDLLPath=p.dlls.rules}
 local combined=p.combined.Preflight(p.combinedOptions,image,stamp,size).profile
 local manual=choose(p.manualProfiles,stamp,size)
 local entry=choose(p.entryProfiles,stamp,size)
 local hla=choose(p.hlaProfiles,stamp,size)
 local function site(s)
  verify(image+s.rva,s.bytes);remember(image+s.rva,s.span or #s.bytes/2)
 end
 for _,f in pairs(manual.functions)do verify(image+f.rva,f.bytes)end
 for _,s in pairs(manual.entries)do site(s)end
 site(manual.manualCall);site(manual.contribution)
 for _,s in ipairs(manual.choiceCalls)do site(s)end
 for _,s in ipairs(combined.nextCalls)do site(s)end
 for _,s in ipairs(combined.getterCalls)do site(s)end
 site(combined.combineCall);site(combined.firstSpecialCall)
 for _,f in pairs(entry.functions)do verify(image+f.rva,f.bytes)end
 site(entry.eligibilityQuery)
 for _,s in pairs(entry.entries)do site(s)end
 for _,f in pairs(hla.functions)do verify(image+f.rva,f.bytes)end
 p.hlaPrepared=p.hlaHooks.Preflight({profiles=p.hlaProfiles},image,stamp,size)
 for _,s in ipairs(p.hlaPrepared.sites)do site(s)end
 p.priorGlobals={}
 for name,value in pairs(_G)do if name:match("^CBMD")then p.priorGlobals[name]=value end end
 return p
end
function M.Install(p,o)
 p.rules.Install{researchOnly=true,dllPath=p.dlls.rules}
 p.skills.Install{researchOnly=true,dllPath=p.dlls.skills}
 p.receipts.Configure(o.wire,o.rewardReceipts,p.manual,p.ledger)
 local rows=p.rows.New(p.skills,p.hla)
 p.ownedFlow=p.flow.New{runtime=o.runtime,rules=p.rules,entry=p.entry,manual=p.manual,receipts=p.receipts,
  pickerModule=p.picker,controllerModule=p.controller,rows=rows,wire=o.wire,hla=p.hla}
 o.runtime.ConfigureOldHLAs(p.hlaReceipts.New{wire=o.wire,account=o.account,manual=p.manual,
  native=p.hla,identity=CBMBank_Identity})
 p.manual.Install{researchOnly=true,dllPath=p.dlls.manual,identityDLLPath=o.identityDLLPath,
  profiles=p.manualProfiles,callbacks=o.callbacks,adapter=p.ownedFlow,combined=p.combinedOptions}
 p.hla.Install{researchOnly=true,dllPath=p.dlls.hla,profiles=p.hlaProfiles,manualDLLPath=p.dlls.manual,
  identity=CBMBank_Identity,pending=o.runtime.PendingHLAs,manualPending=o.runtime.ManualHLAs}
 p.hlaHooks.Install{prepared=p.hlaPrepared,predicate=p.hla.PredicateAddress}
 p.ownedFlow.InstallUI("CBMDOLD")
 -- Last: expose owned old-only/combined progression through the normal button.
 p.entry.Install{researchOnly=true,dllPath=p.dlls.manual,identityDLLPath=o.identityDLLPath,
  profiles=p.entryProfiles,callbacks=o.callbacks,router=p.ownedFlow}
 return p
end
function M.Cleanup(p)
 if p.ownedFlow and p.ownedFlow.UninstallUI then p.ownedFlow.UninstallUI()end
 -- Configuration failures may leave an ephemeral CBMD* initializer. Startup is
 -- synchronous; restore precisely the previously present namespace values.
 for name in pairs(_G)do if name:match("^CBMD")and p.priorGlobals[name]==nil then _G[name]=nil end end
 for name,value in pairs(p.priorGlobals)do _G[name]=value end
end
return M
