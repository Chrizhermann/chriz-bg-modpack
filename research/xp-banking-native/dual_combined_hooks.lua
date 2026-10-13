-- Uninstalled extension of dual_manual_hooks. Preflight every signature before
-- configuring a module or writing instructions. It never opens a player screen.
local M={}
local function signed(n)return n>=2147483648 and n-4294967296 or n end
local function unsigned(n)return n<0 and n+4294967296 or n end
local function exact(at,hex)
 for i=1,#hex,2 do assert(EEex_ReadU8(at+(i-1)/2)==tonumber(hex:sub(i,i+1),16),"Combined native ABI mismatch")end
end
-- Target of the first instruction of an EEex after-call relay, or nil. EEex
-- writes `call <callee>`; its AsmJit assembler encodes that as E8 rel32, as
-- REX+E8 rel32 when it assembles relocatable code (40 E8 on 2.7.3.0 with EEex
-- 1.2.0, read from a live game), or as FF 15 through its address table when
-- the callee is out of rel32 range.
local function relayCallTarget(relay)
 local op=EEex_ReadU8(relay)
 if op==0xe8 then return relay+5+signed(EEex_ReadU32(relay+1))end
 if op>=0x40 and op<=0x4f and EEex_ReadU8(relay+1)==0xe8 then
  return relay+6+signed(EEex_ReadU32(relay+2))
 end
 if op==0xff and EEex_ReadU8(relay+1)==0x15 then
  local slot=relay+6+signed(EEex_ReadU32(relay+2))
  return unsigned(EEex_ReadU32(slot))+unsigned(EEex_ReadU32(slot+4))*4294967296
 end
end
local function functionBytes(game,p)
 local h=p.eeexAfterCall
 if not h then return exact(game+p.rva,p.bytes)end
 local at=game+p.rva+h.offset
 exact(game+p.rva,p.bytes:sub(1,h.offset*2))
 exact(at+5,p.bytes:sub((h.offset+5)*2+1))
 if EEex_ReadU8(at)==0xe8 then exact(at,h.bytes);return end
 -- Pinned EEex_Stats_Patch uses HookAfterCall: E9 to a relay whose first
 -- instruction calls the original callee. Preserve EEex stats associations.
 assert(EEex_TryLabel(h.label)==at and EEex_ReadU8(at)==0xe9,"Unrecognized EEex stats hook")
 local relay=at+5+signed(EEex_ReadU32(at+1))
 assert(relayCallTarget(relay)==game+h.calleeRva,"EEex stats relay does not preserve native first call")
end
local function choose(list,stamp,size)
 local found
 for _,p in ipairs(list)do if p.gameTimestamp==stamp and p.gameSize==size then
  assert(not found,"Ambiguous combined engine profile");found=p
 end end
 assert(found,"Unreviewed combined engine profile");return found
end
function M.Preflight(o,game,stamp,size)
 assert(o and o.profiles and o.profProfiles and type(o.profDLLPath)=="string" and type(o.rulesDLLPath)=="string","Concrete combined dependencies required")
 local p=choose(o.profiles,stamp,size);local q=choose(o.profProfiles,stamp,size)
 for _,f in pairs(p.functions)do functionBytes(game,f)end
 for _,f in pairs(q.functions)do functionBytes(game,f)end
 for _,f in ipairs(p.nextCalls)do exact(game+f.rva,f.bytes)end
 for _,f in ipairs(p.getterCalls)do exact(game+f.rva,f.bytes)end
 exact(game+p.combineCall.rva,p.combineCall.bytes)
 exact(game+p.firstSpecialCall.rva,p.firstSpecialCall.bytes)
 exact(game+p.untouchedSpecialReplay.rva,p.untouchedSpecialReplay.bytes)
 return {profile=p,profProfile=q,options=o}
end
function M.Configure(prepared,game,module,proc,config,invoke)
 local p,q=prepared.profile,prepared.profProfile
 local prof=EEex_LoadLibrary(prepared.options.profDLLPath);assert(prof and prof~=0,"Owned allocation DLL unavailable")
 local rules=EEex_LoadLibrary(prepared.options.rulesDLLPath);assert(rules and rules~=0,"Installed rule binding DLL unavailable")
 local function own(n)return proc("CBMDL_"..n,module)end
 local function allocation(n)return proc("CBMDPC_"..n,prof)end
 local values={1,0,proc("CBMDS_Query",module),proc("CBMDS_IsEngineThread",module)}
 for _,n in ipairs({"base_construct","decode_base","add_tail","remove_at"})do values[#values+1]=game+q.functions[n].rva end
 invoke(allocation("Configure"),{config(values)})
 values={1}
 for _,n in ipairs({"next_level","get_hp","get_classes","get_class","get_level","set_level","is_usable",
  "stats_construct","stats_copy","stats_destruct","combine_all"})do values[#values+1]=game+p.functions[n].rva end
 for _,n in ipairs({"ApplyPreview","Restore","Complete","PersistDormant"})do values[#values+1]=allocation(n)end
 for _,n in ipairs({"get_active","get_inactive","set_active"})do values[#values+1]=game+p.functions[n].rva end
 for _,n in ipairs({"ReadActiveAllocation","ReadOldAllocation","SetActiveOwned"})do values[#values+1]=allocation(n)end
 values[#values+1]=game+p.functions.set_inactive.rva;values[#values+1]=game+p.functions.process_effects.rva
 values[#values+1]=allocation("BeginActivePreview")
 values[#values+1]=game+p.functions.add_special.rva
 values[#values+1]=proc("CBMDP_ApplySelectedOldSkills",rules)
 invoke(own("Configure"),{config(values)})
 for _,n in ipairs({"Select","ReadOld","ReadSkill","Dormant"})do
  local name="CBMDCombined"..n.."Native";assert(_G[name]==nil,"Combined native namespace occupied")
  EEex_ExposeToLua(own("Lua"..n),name)
 end
 local result={hp=own("GetHitPoints"),active=own("SetActive"),inactive=own("SetInactive"),
  getActive=own("GetActive"),getInactive=own("GetInactive"),patches={}}
 for _,f in ipairs(p.nextCalls)do result.patches[#result.patches+1]={site=f,target=own("GetNextLevel")}end
 result.patches[#result.patches+1]={site=p.combineCall,target=own("CombineAll")}
 result.patches[#result.patches+1]={site=p.firstSpecialCall,target=own("AddSpecial")}
 for _,f in ipairs(p.getterCalls)do result.patches[#result.patches+1]={site=f,target=f.inactive and result.getInactive or result.getActive}end
 return result
end
return M
