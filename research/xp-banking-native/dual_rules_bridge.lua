-- UNINSTALLED. Loads only the private native rules-query DLL. No detours, world
-- mutation or implicit level choices. Parent OldProgression owns XP accounting.
local M={}
function M.Install(o)
 assert(not M.installed and o.researchOnly==true and type(o.dllPath)=="string","Explicit private rules install required")
 assert(CBMDOldTargetNative==nil and CBMDOldRulesConfigure==nil and CBMDOldPlanNative==nil and CBMDOldCapNative==nil and CBMDOldRollNative==nil,"Rules namespace occupied")
 local module=EEex_LoadLibrary(o.dllPath);assert(module and module~=0,"Native rules DLL unavailable")
 local function proc(n)local p=EEex_GetProcAddressInternal(module,n);assert(p and p~=0,"Missing native rules export "..n);return p end
 local function label(n)local p=EEex_TryLabel(n);assert(type(p)=="number" and p>0,"Missing Lua provider "..n);return p end
 local image=EEex_GetImageBase();assert(EEex_ReadU16(image)==0x5a4d,"Invalid PE")
 local header=image+EEex_ReadU32(image+0x3c)
 assert(EEex_ReadU32(header)==0x4550 and EEex_ReadU16(header+4)==0x8664,"Unsupported native rules ABI")
 local values={1,image,EEex_ReadU32(header+0x50),label("Hardcoded_lua_tolstring"),label("Hardcoded_lua_pushstring")}
 local p=EEex_Malloc(#values*8);assert(p and p~=0,"Rules configuration allocation failed")
 local called,ok=pcall(function()
  for i,v in ipairs(values)do EEex_Write64(p+(i-1)*8,v)end
  EEex_JITNearAsLuaFunction("CBMDOldRulesConfigure",{"push rbx #ENDL sub rsp,32 #ENDL mov rbx,rcx #ENDL mov rcx,",p,
   "#ENDL call ",proc("CBMDP_ConfigureLua"),"#ENDL mov edx,eax #ENDL mov rcx,rbx #ENDL call ",label("Hardcoded_lua_pushboolean"),
   "#ENDL mov eax,1 #ENDL add rsp,32 #ENDL pop rbx #ENDL ret #ENDL"})
  return CBMDOldRulesConfigure()
 end)
 -- ConfigureLua copies the provider addresses; Bind owns its separate native
 -- binding allocation. Neither retains this temporary configuration buffer.
 CBMDOldRulesConfigure=nil;EEex_Free(p)
 assert(called and ok,"Native rules signatures or engine thread rejected: "..tostring(ok))
 EEex_ExposeToLua(proc("CBMDP_LuaOldTarget"),"CBMDOldTargetNative")
 EEex_ExposeToLua(proc("CBMDP_LuaOldPlan"),"CBMDOldPlanNative")
 EEex_ExposeToLua(proc("CBMDP_LuaOldCap"),"CBMDOldCapNative")
 EEex_ExposeToLua(proc("CBMDP_LuaOldRoll"),"CBMDOldRollNative");M.installed=true;return M
end
function M.Target(sprite,oldProgression)
 assert(M.installed,"Private native rules bridge is not installed")
 assert(type(oldProgression)=="table","Current owned account snapshot required")
 -- Parent identifies the owned classes; the actual CAIObjectType native query
 -- independently checks both. No duplicated Lua class-layout mapping.
 local active=oldProgression.activeClass
 assert(type(active)=="number" and active%1==0 and active>0 and active<256,"Current active class required")
 local rules=EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_ruleTables
 local status,before,target=CBMDOldTargetNative(string.format("%x",EEex_UDToPtr(sprite)),
  string.format("%x",EEex_UDToPtr(rules)),tostring(active),tostring(oldProgression.oldClass),tostring(oldProgression.oldUsableXP))
 assert(status,"Native target arguments rejected")
 if status~="0"then return nil,"Native old-class target query rejected ("..status..")"end
 assert(tonumber(before)==oldProgression.oldLevel,"Actor level changed since account snapshot")
 return tonumber(target)
end
local function arguments(sprite,account)
 assert(M.installed and type(account.activeClass)=="number" and type(account.oldKit)=="number","Current native old-class identity required")
 local rules=EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_ruleTables
 return {string.format("%x",EEex_UDToPtr(sprite)),string.format("%x",EEex_UDToPtr(rules)),
  tostring(account.activeClass),tostring(account.oldClass),tostring(account.oldUsableXP),tostring(account.oldKit)}
end
function M.Plan(sprite,account)
 local a=arguments(sprite,account)
 local status,before,target,prof,skills=CBMDOldPlanNative(unpack(a))
 assert(status,"Native old choices arguments rejected")
 if status~="0"then return nil,"Native old choices query rejected ("..status..")"end
 assert(tonumber(before)==account.oldLevel,"Actor level changed since account snapshot")
 return {oldLevel=tonumber(before),target=tonumber(target),profPoints=tonumber(prof),skillPoints=tonumber(skills)}
end
function M.Cap(sprite,account,stat)
 assert(type(stat)=="number" and stat%1==0 and stat>=89 and stat<=134,"Native proficiency stat required")
 local a=arguments(sprite,account);a[7]=tostring(stat)
 local status,limit=CBMDOldCapNative(unpack(a))
 assert(status,"Native cap arguments rejected")
 if status~="0"then return nil,"Native old proficiency cap query rejected ("..status..")"end
 -- Native storage is three bits per class even if an installed table supplies
 -- a larger theoretical limit. Never wrap an allocated pip into the other side.
 return math.min(7,tonumber(limit))
end
function M.Roll(sprite,account)
 local status,total,encoded=CBMDOldRollNative(unpack(arguments(sprite,account)))
 assert(status,"Native old HP arguments rejected")
 assert(status=="0","Native old HP roll did not complete; retain pending journal ("..status..")")
 return {total=tonumber(total),encoded=encoded}
end
return M
