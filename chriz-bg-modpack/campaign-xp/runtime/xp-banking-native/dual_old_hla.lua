-- UNINSTALLED. Explicit read-only native HLA catalog adapter. Loading this file
-- installs nothing and grants no abilities. Durable descriptors contain no
-- process pointers, callbacks, catalog handles, or engine object IDs.
local M={}
local function integer(n,lo,hi)
 return type(n)=="number"and n==n and n%1==0 and n>=lo and n<=hi
end
local function pack(list)
 local out={};for i,s in ipairs(list)do assert(type(s)=="string"and not s:find("\0",1,true),"Invalid native text")
  out[i]=tostring(#s)..":"..s
 end;return table.concat(out)
end
local function descriptor(icon,name,min,max,rank,effect,prereq,excluded,alignment)
 local function bits(value)local n=tonumber(value);return n<0 and n+4294967296 or n end
 return {schema=1,icon=icon,nameStrref=tonumber(name),minLevel=bits(min),maxLevel=bits(max),
  maxRank=bits(rank),effect=effect,prerequisite=prereq,excludedBy=excluded,alignment=alignment}
end
function M.Install(o)
 assert(not M.installed and o.researchOnly==true and type(o.dllPath)=="string","Explicit private HLA install required")
 assert(type(o.pending)=="function","Owned deferred HLA queue reader required")
 local identity=o.identity or CBMBank_Identity
 assert(identity and type(identity.Query)=="function","Native lifetime identity required")
 local image=EEex_GetImageBase();assert(EEex_ReadU16(image)==0x5a4d,"Invalid PE")
 local header=image+EEex_ReadU32(image+0x3c)
 assert(EEex_ReadU32(header)==0x4550 and EEex_ReadU16(header+4)==0x8664,"Unsupported HLA native ABI")
 local profile
 for _,p in ipairs(o.profiles)do
  if p.gameTimestamp==EEex_ReadU32(header+8)and p.gameSize==EEex_ReadU32(header+0x50)then
   assert(not profile,"Ambiguous HLA engine profile");profile=p
  end
 end
 assert(profile,"Unreviewed native HLA engine profile")
 -- Native pointer calls require certified layouts. This does not compare any
 -- installed gameplay table, kit name, spell count, or actor field to a fixture.
 for _,f in pairs(profile.functions)do
  for i=1,#f.bytes,2 do assert(EEex_ReadU8(image+f.rva+(i-1)/2)==tonumber(f.bytes:sub(i,i+1),16),
   "Native HLA method changed: "..f.name)end
 end
 local names={"CBMDHLAOpenNative","CBMDHLARowNative","CBMDHLAChooseNative","CBMDHLACloseNative",
  "CBMDHLADeliverNative","CBMDHLAPrepareManualNative","CBMDHLAClearManualNative","CBMDHLAConfigureNative"}
 for _,name in ipairs(names)do assert(_G[name]==nil,"Native HLA namespace occupied")end
 local module=EEex_LoadLibrary(o.dllPath);assert(module and module~=0,"Native HLA DLL unavailable")
 local manual=o.manualModule
 if not manual and o.manualDLLPath then manual=EEex_LoadLibrary(o.manualDLLPath)end
 assert(manual and manual~=0,"Native manual engine-thread owner unavailable")
 local function proc(handle,n)local p=EEex_GetProcAddressInternal(handle,n);assert(p and p~=0,"Missing native HLA export "..n);return p end
 local function label(n)local p=EEex_TryLabel(n);assert(type(p)=="number"and p>0,"Missing Lua provider "..n);return p end
 local function configure(target,values)
  local ptr=EEex_Malloc(#values*8);assert(ptr and ptr~=0,"Native HLA configuration allocation failed")
  local ok,why=pcall(function()
   for i,v in ipairs(values)do EEex_Write64(ptr+(i-1)*8,v)end
   EEex_JITNearAsLuaFunction("CBMDHLAConfigureNative",{"push rbx #ENDL sub rsp,32 #ENDL mov rbx,rcx #ENDL mov rcx,",ptr,
    "#ENDL call ",target,"#ENDL mov edx,eax #ENDL mov rcx,rbx #ENDL call ",label("Hardcoded_lua_pushboolean"),
    "#ENDL mov eax,1 #ENDL add rsp,32 #ENDL pop rbx #ENDL ret #ENDL"})
   assert(CBMDHLAConfigureNative(),"Native HLA configuration rejected")
  end)
  CBMDHLAConfigureNative=nil;EEex_Free(ptr);if not ok then error(why)end
 end
 local rules=EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_ruleTables
 local values={1,EEex_UDToPtr(rules),proc(manual,"CBMDS_IsEngineThread")}
 for _,key in ipairs({"num_abilities","set_level","class_string","get_at","scan","cstring_destroy"})do
  values[#values+1]=image+profile.functions[key].rva
 end
 for _,key in ipairs({"first_level","rate","change_level","new_rate"})do values[#values+1]=image+profile.constants[key]end
 for _,key in ipairs({"get_abilities","complete_abilities","ability_construct","cstring_construct_chars",
  "cstring_assign_chars","resref_construct_cstring","check_enabled","get_ai_type"})do values[#values+1]=image+profile.functions[key].rva end
 configure(proc(module,"CBMDHLA_Configure"),values)
 configure(proc(module,"CBMDHLA_ConfigureLua"),{1,label("Hardcoded_lua_tolstring"),label("Hardcoded_lua_pushstring")})
 configure(proc(module,"CBMDHLA_ConfigureProjection"),{1,proc(manual,"CBMDS_Query")})
 local delivery={1,proc(manual,"CBMDS_Query"),proc(manual,"CBMDS_IsEngineThread"),proc(manual,"CBMDL_IsDormant")}
 for _,key in ipairs({"allocate","array_construct","array_grow"})do delivery[#delivery+1]=image+profile.functions[key].rva end
 assert(EEex_Read64(image+profile.listVtable)==image+profile.listDestructor,"Native HLA list destructor changed")
 delivery[#delivery+1]=image+profile.listVtable
 for _,key in ipairs({"ability_construct","cstring_assign_chars","cstring_destroy","release","complete_abilities"})do
  delivery[#delivery+1]=image+profile.functions[key].rva
 end
 configure(proc(module,"CBMDHLA_ConfigureDelivery"),delivery)
 for i,export in ipairs({"LuaOpen","LuaRow","LuaChoose","LuaClose","LuaDeliver","LuaPrepareManual","LuaClearManual"})do
  EEex_ExposeToLua(proc(module,"CBMDHLA_"..export),names[i])
 end
 -- Optional only for a read-only research query harness. The full manual flow
 -- must explicitly install the two scoped predicate callsites before opening.
 if o.activeHooks then o.activeHooks.Install{researchOnly=true,profile=profile,image=image,
  target=proc(module,"CBMDHLA_CheckAbilityEnabled")}end
 M.PredicateAddress=proc(module,"CBMDHLA_CheckAbilityEnabled")
 M.pending=o.pending;M.manualPending=o.manualPending;M.identity=identity;M.installed=true;return M
end
function M.Pending(sprite)
 assert(M.installed,"Private native HLA provider is not installed")
 local list,why=M.pending(sprite);assert(type(list)=="table",why or"Deferred HLA queue unavailable")
 return list
end
function M.Open(sprite,account,target,priorDeferred)
 assert(M.installed,"Private native HLA provider is not installed")
 assert(type(account)=="table"and integer(account.oldClass,1,255)and integer(account.oldKit,0,4294967295)
  and integer(account.oldLevel,0,255)and integer(target,account.oldLevel,255),"Current old class interval required")
 local identity,why=M.identity.Query(sprite);assert(identity and identity.incarnation,why or"Native actor lifetime unavailable")
 local incarnation=identity.incarnation
 local address=string.format("%x",EEex_UDToPtr(sprite))
 local pending={}
 for _,entry in ipairs(priorDeferred or M.Pending(sprite))do
  local d=entry.descriptor or entry
  assert(type(d)=="table"and d.schema==1 and type(d.effect)=="string","Invalid deferred HLA descriptor")
  pending[#pending+1]=d.effect
 end
 local encodedPending=pack(pending)
 local ok,handle,points,capped,count,flags=CBMDHLAOpenNative(address,tostring(account.oldClass),tostring(account.oldKit),tostring(account.oldLevel),tostring(target))
 if ok~="1"then return nil,"Native old HLA query rejected ("..tostring(handle)..")"end
 local closed=false;local closeResult,closeReason
 local function close()
  if closed then return closeResult,closeReason end;closed=true
  local status=CBMDHLACloseNative(handle)
  if status~="1"then closeReason="Native HLA cleanup uncertain; do not retry ("..tostring(status)..")";return nil,closeReason end
  closeResult=true;return closeResult
 end
 local success,view=pcall(function()
  local v={points=tonumber(points),nativeCappedPoints=tonumber(capped),eligibilityFlags=tonumber(flags),rows={}}
  local indices={}
  for index=0,tonumber(count)-1 do
   local status,icon,name,min,max,rank,effect,prereq,excluded,alignment=CBMDHLARowNative(handle,tostring(index))
   assert(status=="1","Native HLA catalog row unavailable")
   v.rows[#v.rows+1]={id=index,descriptor=descriptor(icon,name,min,max,rank,effect,prereq,excluded,alignment)}
   indices[index]=true
  end
  function v.CanChoose(id,selected)
   if closed then return false,"HLA catalog is closed"end
   local now,problem=M.identity.Query(sprite)
   if not now or now.incarnation~=incarnation then return false,problem or"Actor lifetime changed; reopen choices"end
   if not indices[id]then return false,"Unknown installed HLA row"end
   local chosen={};for i,row in ipairs(selected)do
    if not indices[row]then return false,"Unknown selected HLA row"end;chosen[i]=tostring(row)
   end
   local result=CBMDHLAChooseNative(handle,address,tostring(id),pack(chosen),encodedPending)
   if result=="1"then return true end
   return false,result=="0"and"Installed HLA requirements are not satisfied"or"Native HLA eligibility query failed"
  end
  v.Close=close;return v
 end)
 if not success then local done,problem=close();return nil,tostring(view)..(done and""or"; "..problem)end
 return view
end
function M.PrepareManual(sprite,account,target,choices,priorDeferred)
 assert(M.installed and type(account)=="table"and type(account.ownerKey)=="string","Owned HLA manual account required")
 local entries
 if M.manualPending then entries=M.manualPending(sprite)else
  entries={};for _,d in ipairs(priorDeferred or M.Pending(sprite))do entries[#entries+1]=d end
  for _,d in ipairs(choices and choices.hlas or{})do entries[#entries+1]=d end
 end
 assert(type(entries)=="table","Owned pending plus selected HLA context required")
 local effects={};for _,entry in ipairs(entries)do
  local d=entry.descriptor or entry;assert(d.schema==1 and type(d.effect)=="string","Invalid manual HLA descriptor")
  effects[#effects+1]=d.effect
 end
 local ok,token=CBMDHLAPrepareManualNative(string.format("%x",EEex_UDToPtr(sprite)),account.ownerKey,pack(effects))
 assert(ok=="1","Actual owned HLA PREPARING scope rejected")
 return token
end
function M.ClearManual(token)
 assert(M.installed and type(token)=="string","Native HLA context token required")
 return CBMDHLAClearManualNative(token)=="1"
end
function M.Deliver(sprite,oldClass,owner,entries)
 assert(M.installed and integer(oldClass,1,255)and type(owner)=="string","Current owned HLA delivery required")
 local fields={}
 for _,entry in ipairs(entries)do
  local d=entry.descriptor or entry
  assert(d.schema==1 and type(d.icon)=="string"and #d.icon<=8,"Invalid persisted HLA descriptor")
  fields[#fields+1]=d.icon
  for _,key in ipairs({"nameStrref","minLevel","maxLevel","maxRank"})do
   assert(integer(d[key],0,4294967295),"Invalid persisted HLA integer bits");fields[#fields+1]=tostring(d[key])
  end
  for _,key in ipairs({"effect","prerequisite","excludedBy","alignment"})do
   assert(type(d[key])=="string","Invalid persisted HLA text");fields[#fields+1]=d[key]
  end
 end
 local status,completed,uncertain=CBMDHLADeliverNative(string.format("%x",EEex_UDToPtr(sprite)),tostring(oldClass),owner,pack(fields))
 assert(status~=nil,"Native HLA delivery arguments rejected")
 -- The native receipt counts abilities whose whole batch returned. Public
 -- queue contract counts batches. An uncertain in-flight batch is never added.
 return tonumber(status),math.ceil(tonumber(completed)/24),tonumber(uncertain)==1
end
return M
