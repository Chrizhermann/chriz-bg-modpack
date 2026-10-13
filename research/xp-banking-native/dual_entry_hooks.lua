-- UNINSTALLED, explicit private installation only. One scoped native query
-- callsite, plus optional standard-button eligibility/click routing. No global
-- GetNextLevel replacement or replacement of the user's main menu layout.
local M={}
function M.CallbackAssembly(name,suffix,callbacks)
 return EEex_FlattenTable({{"#STACK_MOD(8) #ENDL"},callbacks.GenLuaCall(name,{
  args={function(offset)return {"mov qword ptr ss:[rsp+#$(1)], rcx",{offset},"#ENDL"},"CGameSprite"end},
  returnType=EEex_LuaCallReturnType.Number,labelSuffix=suffix}),
  {"jmp done",suffix,"#ENDL call_error",suffix,": #ENDL mov rax,-1 #ENDL done",suffix,": #ENDL #DESTROY_SHADOW_SPACE #ENDL ret #ENDL"}})
end
local function verify(address,hex)
 for i=1,#hex,2 do assert(EEex_ReadU8(address+(i-1)/2)==tonumber(hex:sub(i,i+1),16),"Retired entry instruction mismatch")end
end
function M.Install(o)
 assert(not M.installed and o.researchOnly==true and o.dllPath and o.identityDLLPath and o.profiles,"Explicit retired entry dependencies required")
 assert(CBMBank_Identity and CBMBank_Identity.installed and CBMDManualQueryNative,"Native identity and manual scope must be installed first")
 assert(CBMDOldEntryConfigure==nil and CBMDOldEntryCheckNative==nil,"Retired entry namespace occupied")
 if o.router then
  assert(o.callbacks and type(o.callbacks.GenLuaCall)=="function" and type(o.router.Eligible)=="function" and type(o.router.Route)=="function","Concrete entry router and private callback ABI required")
  assert(CBMDOldEligible==nil and CBMDOldRoute==nil and CBMDOldEntryOpenNative==nil,"Retired routing namespace occupied")
 end
 local image=EEex_GetImageBase();assert(EEex_ReadU16(image)==0x5a4d,"Invalid PE")
 local h=image+EEex_ReadU32(image+0x3c)
 assert(EEex_ReadU32(h)==0x4550 and EEex_ReadU16(h+4)==0x8664,"Unsupported retired entry ABI")
 local profile
 for _,p in ipairs(o.profiles)do if p.gameTimestamp==EEex_ReadU32(h+8) and p.gameSize==EEex_ReadU32(h+0x50)then
  assert(not profile,"Ambiguous retired entry build");profile=p
 end end
 assert(profile,"Unreviewed retired entry build")
 for _,p in pairs(profile.functions)do verify(image+p.rva,p.bytes)end
 verify(image+profile.eligibilityQuery.rva,profile.eligibilityQuery.bytes)
 if o.router then for _,p in pairs(profile.entries)do verify(image+p.rva,p.bytes)end end
 local module=EEex_LoadLibrary(o.dllPath);assert(module and module~=0,"Retired entry DLL unavailable")
 local identity=EEex_LoadLibrary(o.identityDLLPath);assert(identity and identity~=0,"Identity DLL unavailable")
 local function proc(lib,n)local p=EEex_GetProcAddressInternal(lib,n);assert(p and p~=0,"Missing native entry export "..n);return p end
 local native={configure=proc(module,"CBMDE_Configure"),query=proc(module,"CBMDE_GetNextLevel"),lua=proc(module,"CBMDE_LuaCheck")}
 local values={1}
 for _,n in ipairs({"clickable","nextLevel","classes","overall","level","setLevel","isUsable"})do
  values[#values+1]=image+profile.functions[n].rva
 end
 values[#values+1]=proc(identity,"CBMI_Query");values[#values+1]=proc(identity,"CBMI_CanMutate")
 local entryTargets={}
 if o.router then
  for key,p in pairs(profile.entries)do
   entryTargets[key]=EEex_JITNear(EEex_FlattenTable({EEex_StoreBytesAssembly(image+p.rva,p.span),{"jmp ",image+p.rva+p.span,"#ENDL"}}))
  end
  values[2]=entryTargets.clickable
  CBMDOldEligible=o.router.Eligible;CBMDOldRoute=o.router.Route
  values[#values+1]=entryTargets.click
  values[#values+1]=EEex_UDToPtr(EngineGlobals.g_pBaldurChitin.m_pObjectGame)
  values[#values+1]=image+profile.functions.getDeny.rva
  values[#values+1]=EEex_JITNear(M.CallbackAssembly("CBMDOldEligible","_cbmd_eligible",o.callbacks))
  values[#values+1]=EEex_JITNear(M.CallbackAssembly("CBMDOldRoute","_cbmd_route",o.callbacks))
 else for i=1,5 do values[#values+1]=0 end end
 local config=EEex_Malloc(#values*8);assert(config and config~=0,"Entry configuration allocation failed")
 for i,v in ipairs(values)do EEex_Write64(config+(i-1)*8,v)end
 local push=EEex_TryLabel("Hardcoded_lua_pushboolean");assert(type(push)=="number" and push>0,"Active Lua provider required")
 EEex_JITNearAsLuaFunction("CBMDOldEntryConfigure",{"push rbx #ENDL sub rsp,32 #ENDL mov rbx,rcx #ENDL mov rcx,",config,
  "#ENDL call ",native.configure,"#ENDL mov edx,eax #ENDL mov rcx,rbx #ENDL call ",push,
  "#ENDL mov eax,1 #ENDL add rsp,32 #ENDL pop rbx #ENDL ret #ENDL"})
 local accepted=CBMDOldEntryConfigure();CBMDOldEntryConfigure=nil;assert(accepted,"Native retired entry configuration rejected")
 EEex_ExposeToLua(native.lua,"CBMDOldEntryCheckNative")
 if o.router then EEex_ExposeToLua(proc(module,"CBMDE_LuaOpen"),"CBMDOldEntryOpenNative")end
 local relay=EEex_JITNear({"jmp ",native.query,"#ENDL"});local p=profile.eligibilityQuery
 local patches={{site=p,assembly={"call short ",relay,"#ENDL"}}}
 if o.router then for key,e in pairs(profile.entries)do
  local to=proc(module,key=="click" and "CBMDE_Click" or "CBMDE_Clickable")
  local trampoline=EEex_JITNear({"jmp ",to,"#ENDL"})
  patches[#patches+1]={site=e,assembly={"jmp short ",trampoline,"#ENDL #REPEAT(#$(1),nop #ENDL)",{e.span-5}}}
 end end
 EEex_DisableCodeProtection()
 local ok,why=pcall(function()for _,patch in ipairs(patches)do EEex_JITAt(image+patch.site.rva,patch.assembly)end end)
 if not ok then for _,patch in ipairs(patches)do local e=patch.site
  for i=1,#e.bytes,2 do EEex_WriteU8(image+e.rva+(i-1)/2,tonumber(e.bytes:sub(i,i+1),16))end
 end end
 EEex_EnableCodeProtection();assert(ok,"Entry patch rolled back; restart required: "..tostring(why))
 M.installed=true;return M
end
function M.Check(sprite,account,target)
 assert(M.installed,"Private old-only entry query is not installed")
 if target<=account.oldLevel then return false end
 local screen=EngineGlobals.g_pBaldurChitin.m_pEngineCharacter
 local status=CBMDOldEntryCheckNative(string.format("%x",EEex_UDToPtr(sprite)),string.format("%x",EEex_UDToPtr(screen)),
  account.incarnation,tostring(account.oldLevel),tostring(target))
 if status=="1"then return true end
 return false,status=="0" and "Normal level-up restrictions apply" or "The actor or old-class level changed"
end
function M.Open(sprite,account,target)
 assert(M.installed and CBMDOldEntryOpenNative,"Private normal-button routing is not installed")
 local screen=EngineGlobals.g_pBaldurChitin.m_pEngineCharacter
 local status=CBMDOldEntryOpenNative(string.format("%x",EEex_UDToPtr(sprite)),string.format("%x",EEex_UDToPtr(screen)),
  account.incarnation,tostring(account.oldLevel),tostring(target))
 assert(status=="1","Ordinary manual screen did not enter its owned preview; retain journal")
 return true
end
return M
