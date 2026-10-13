-- Explicit private query binding. Loading this file does not call the engine.
local M={}
function M.Install(o)
 assert(not M.installed and o.researchOnly==true and type(o.dllPath)=="string","Explicit private skill query install required")
 assert(CBMDOldSkillRowsNative==nil and CBMDOldSkillRowsConfigure==nil,"Skill query namespace occupied")
 local module=EEex_LoadLibrary(o.dllPath);assert(module and module~=0,"Skill query DLL unavailable")
 local function proc(n)local p=EEex_GetProcAddressInternal(module,n);assert(p and p~=0,"Missing skill query export "..n);return p end
 local function label(n)local p=EEex_TryLabel(n);assert(type(p)=="number"and p>0,"Missing native Lua provider "..n);return p end
 local image=EEex_GetImageBase();assert(EEex_ReadU16(image)==0x5a4d,"Invalid PE")
 local pe=image+EEex_ReadU32(image+0x3c)
 assert(EEex_ReadU32(pe)==0x4550 and EEex_ReadU16(pe+4)==0x8664,"Unsupported skill query ABI")
 local values={1,image,EEex_ReadU32(pe+0x50),label("Hardcoded_lua_tolstring"),label("Hardcoded_lua_pushstring")}
 local p=EEex_Malloc(#values*8);assert(p and p~=0,"Skill query configuration allocation failed")
 local success,why=pcall(function()
  for i,v in ipairs(values)do EEex_Write64(p+(i-1)*8,v)end
  EEex_JITNearAsLuaFunction("CBMDOldSkillRowsConfigure",{"push rbx #ENDL sub rsp,32 #ENDL mov rbx,rcx #ENDL mov rcx,",p,
   "#ENDL call ",proc("CBMDS_ConfigureLua"),"#ENDL mov edx,eax #ENDL mov rcx,rbx #ENDL call ",label("Hardcoded_lua_pushboolean"),
   "#ENDL mov eax,1 #ENDL add rsp,32 #ENDL pop rbx #ENDL ret #ENDL"})
  assert(CBMDOldSkillRowsConfigure(),"Native skill query signatures or engine thread rejected")
 end)
 CBMDOldSkillRowsConfigure=nil;EEex_Free(p)
 if not success then error(why)end
 EEex_ExposeToLua(proc("CBMDS_LuaRows"),"CBMDOldSkillRowsNative");M.installed=true;return M
end
function M.Read(sprite,account)
 assert(M.installed,"Private skill query binding is not installed")
 local rules=EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_ruleTables
 local encoded=CBMDOldSkillRowsNative(string.format("%x",EEex_UDToPtr(sprite)),
  string.format("%x",EEex_UDToPtr(rules)),tostring(account.oldClass),tostring(account.oldKit))
 assert(type(encoded)=="string","Native skill query rejected arguments or thread")
 local status,body=encoded:match("^(%d+);(.*)$");assert(status=="0","Native skill query rejected ("..tostring(status)..")")
 local rows={};local consumed=""
 for raw in body:gmatch("([^;]+);")do
  consumed=consumed..raw..";"
  local id,name,base,display,limit,percentage=raw:match("^(%d+),(%d+),(%-?%d+),(%-?%d+),(%-?%d+),(%-?%d+)$")
  assert(id,"Malformed native skill row")
  id,name,base,display,limit,percentage=tonumber(id),tonumber(name),tonumber(base),tonumber(display),tonumber(limit),tonumber(percentage)
  assert(id==#rows and id<=6 and base>=0 and base<=255 and limit>=0 and limit<=255 and percentage>=0,
   "Invalid native skill row bounds")
  rows[#rows+1]={id=id,nameStrref=name,value=base,display=display,limit=limit,percentage=percentage}
 end
 assert(consumed==body and #rows==7,"Incomplete native skill row set")
 return rows
end
return M
