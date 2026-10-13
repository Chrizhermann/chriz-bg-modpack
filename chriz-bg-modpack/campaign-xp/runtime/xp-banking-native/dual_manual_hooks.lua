-- UNINSTALLED research entry point. Loading defines functions only. The explicit
-- Install requires native identity hooks BEFORE any tracked screen can open.
local M={}
local function label(name)local p=EEex_TryLabel(name);assert(type(p)=="number" and p>0,"Missing native label "..name);return p end
local function verify(address,hex)
 for i=1,#hex,2 do assert(EEex_ReadU8(address+(i-1)/2)==tonumber(hex:sub(i,i+1),16),"Manual progression ABI mismatch") end
end
function M.CallbackAssembly(name,suffix,callbacks)
 local begin=name=="CBMDManualBegin"
 return EEex_FlattenTable({{"#STACK_MOD(8) #ENDL"},callbacks.GenLuaCall(name,{
  args={function(offset)return {"mov qword ptr ss:[rsp+#$(1)], rcx",{offset},"#ENDL"},"CGameSprite" end},
  returnType=begin and EEex_LuaCallReturnType.Number or EEex_LuaCallReturnType.Boolean,labelSuffix=suffix}),
  {"jmp done",suffix,"#ENDL call_error",suffix,begin and ": #ENDL mov rax,-1 #ENDL done" or ": #ENDL xor eax,eax #ENDL done",suffix,": #ENDL #DESTROY_SHADOW_SPACE #ENDL ret #ENDL"}})
end
function M.Install(o)
 assert(not M.installed and type(o)=="table" and o.researchOnly==true,"Explicit research-only manual install required")
 assert(CBMBank_Identity and CBMBank_Identity.installed,"Native identity hooks required before manual capture")
 assert(type(o.dllPath)=="string" and type(o.identityDLLPath)=="string" and type(o.profiles)=="table" and o.adapter,"Missing manual dependencies")
 assert(o.callbacks and type(o.callbacks.GenLuaCall)=="function","Audited private callback ABI helper required")
 for _,n in ipairs({"Begin","PrepareCommit","Complete","Cancel","Uncertain"})do assert(type(o.adapter[n])=="function","Missing concrete manual journal method "..n)end
 local names={"CBMDManualBegin","CBMDManualPrepare","CBMDManualComplete","CBMDManualCancel","CBMDManualUncertain",
  "CBMDManualQueryNative","CBMDManualHPNative","CBMDManualSampleNative","CBMDManualChoiceNative","CBMDManualBindNative"}
 for _,n in ipairs(names)do assert(_G[n]==nil,"Manual namespace occupied: "..n)end
 local game=EEex_GetImageBase();assert(EEex_ReadU16(game)==0x5a4d,"Invalid game PE")
 local header=game+EEex_ReadU32(game+0x3c)
 assert(EEex_ReadU32(header)==0x4550 and EEex_ReadU16(header+4)==0x8664,"Unsupported game ABI")
 local stamp,size=EEex_ReadU32(header+8),EEex_ReadU32(header+0x50);local profile
 for _,p in ipairs(o.profiles)do if p.gameTimestamp==stamp and p.gameSize==size then assert(not profile,"Ambiguous manual build");profile=p end end
 assert(profile,"Unreviewed manual game build")
 local combinedPrepared
 if o.combined then
  assert(o.combined.module and type(o.combined.module.Preflight)=="function" and type(o.combined.module.Configure)=="function","Combined binding module required")
  combinedPrepared=o.combined.module.Preflight(o.combined,game,stamp,size)
 end
 for _,p in pairs(profile.entries)do verify(game+p.rva,p.bytes)end
 for _,p in pairs(profile.functions)do verify(game+p.rva,p.bytes)end
 for _,p in ipairs(profile.choiceCalls)do verify(game+p.rva,p.bytes)end
 verify(game+profile.manualCall.rva,profile.manualCall.bytes);verify(game+profile.contribution.rva,profile.contribution.bytes)
 local module=EEex_LoadLibrary(o.dllPath);assert(module and module~=0,"Manual DLL unavailable")
 local identityModule=EEex_LoadLibrary(o.identityDLLPath);assert(identityModule and identityModule~=0,"Identity DLL unavailable")
 local function proc(name,lib)local p=EEex_GetProcAddressInternal(lib or module,name);assert(p and p~=0,"Missing export "..name);return p end
 local native={};for _,name in ipairs({"Configure","Reset","Commit","Cancel","OnHP","OnChoice","ConfigureLua","LuaQuery","LuaHP","LuaHPSample","LuaChoice","LuaBindOwner"})do native[name]=proc("CBMDS_"..name)end
 local getIdentity=proc("CBMI_Query",identityModule)
 local canMutate=proc("CBMI_CanMutate",identityModule)
 local api={tolstring=label("Hardcoded_lua_tolstring"),pushstring=label("Hardcoded_lua_pushstring"),pushboolean=label("Hardcoded_lua_pushboolean")}
 local ordinal=0
 local function invoke(at,args)
  ordinal=ordinal+1;local name="CBMDManualConfig"..ordinal;assert(_G[name]==nil,"Manual init namespace occupied")
  -- Addresses stay number elements, which EEex writes exactly (EEex_ToDecStr). Concatenated, the
  -- game's Lua 5.2 formats them with "%.14g": a 15-digit DLL address becomes lossy scientific
  -- notation that EEex's assembler rejects ("EEex_JITNear() failed: InvalidState").
  local function address(value)
   assert(type(value)=="number" and value>=0 and value==math.floor(value),"Manual configuration needs integer addresses")
   return value
  end
  assert(#args<=4,"Manual configuration takes at most four register arguments")
  local assembly={"push rbx #ENDL sub rsp,32 #ENDL mov rbx,rcx #ENDL"}
  for i,value in ipairs(args)do
   assembly[#assembly+1]=({"mov rcx, ","mov rdx, ","mov r8, ","mov r9, "})[i]
   assembly[#assembly+1]=address(value);assembly[#assembly+1]=" #ENDL"
  end
  assembly[#assembly+1]="call ";assembly[#assembly+1]=address(at)
  assembly[#assembly+1]=" #ENDL mov edx,eax #ENDL mov rcx,rbx #ENDL call ";assembly[#assembly+1]=address(api.pushboolean)
  assembly[#assembly+1]=" #ENDL mov eax,1 #ENDL add rsp,32 #ENDL pop rbx #ENDL ret #ENDL"
  EEex_JITNearAsLuaFunction(name,assembly);local ok=_G[name]();_G[name]=nil;assert(ok,"Native manual configuration rejected")
 end
 local function config(values)
  local p=EEex_Malloc(#values*8);assert(p and p~=0,"Manual configuration allocation failed")
  for i,n in ipairs(values)do EEex_Write64(p+(i-1)*8,n)end;return p
 end
 local original={}
 for name,p in pairs(profile.entries)do original[name]=EEex_JITNear(EEex_FlattenTable({EEex_StoreBytesAssembly(game+p.rva,p.span),{"jmp ",game+p.rva+p.span,"#ENDL"}}))end
 local adapter=o.adapter
 CBMDManualBegin=adapter.Begin;CBMDManualPrepare=adapter.PrepareCommit;CBMDManualComplete=adapter.Complete
 CBMDManualCancel=adapter.Cancel;CBMDManualUncertain=adapter.Uncertain
 local callbacks={};for _,name in ipairs({"Begin","Prepare","Complete","Cancel","Uncertain"})do callbacks[name]=EEex_JITNear(M.CallbackAssembly("CBMDManual"..name,"_cbmd_"..name,o.callbacks))end
 invoke(native.Configure,{config({1,original.reset,original.commit,original.cancel,getIdentity,canMutate,callbacks.Begin,
  callbacks.Prepare,callbacks.Complete,callbacks.Cancel,callbacks.Uncertain})})
 local combined
 if combinedPrepared then combined=o.combined.module.Configure(combinedPrepared,game,module,proc,config,invoke)end
 invoke(proc("CBMDH_Configure"),{config({1,combined and combined.hp or game+profile.functions.getHP.rva})})
 invoke(proc("CBMDC_Configure"),{config({1,combined and combined.active or game+profile.functions.setActive.rva,
  combined and combined.inactive or game+profile.functions.setInactive.rva,
  combined and combined.getActive or game+profile.functions.getActive.rva,combined and combined.getInactive or game+profile.functions.getInactive.rva})})
 invoke(native.ConfigureLua,{api.tolstring,api.pushstring})
 invoke(proc("CBMDH_SetSink"),{native.OnHP});invoke(proc("CBMDC_SetSink"),{native.OnChoice})
 for _,pair in ipairs({{"LuaQuery","CBMDManualQueryNative"},{"LuaHP","CBMDManualHPNative"},{"LuaHPSample","CBMDManualSampleNative"},
  {"LuaChoice","CBMDManualChoiceNative"},{"LuaBindOwner","CBMDManualBindNative"}})do EEex_ExposeToLua(native[pair[1]],pair[2])end
 -- Prepare every allocation/relay before modifying any native instruction.
 local patches={}
 local function add(p,assembly)patches[#patches+1]={address=game+p.rva,hex=p.bytes,assembly=assembly}end
 for name,p in pairs(profile.entries)do
  local target=native[name:sub(1,1):upper()..name:sub(2)]
  local relay=EEex_JITNear({"jmp ",target,"#ENDL"})
  add(p,{"jmp short ",relay,"#ENDL #REPEAT(#$(1),nop #ENDL)",{p.span-5}})
 end
 local function callPatch(p,target,extra)
  local relay=EEex_JITNear({"jmp ",target,"#ENDL"});add(p,{"call short ",relay,"#ENDL",extra or ""})
 end
 callPatch(profile.manualCall,proc("CBMDH_ManualCallThunk"))
 callPatch(profile.contribution,proc("CBMDH_ContributionThunk"),"nop #ENDL")
 for _,p in ipairs(profile.choiceCalls)do callPatch(p,proc(p.inactive and "CBMDC_InactiveThunk" or "CBMDC_ActiveThunk"))end
 if combined then for _,p in ipairs(combined.patches)do callPatch(p.site,p.target)end end
 EEex_DisableCodeProtection()
 local ok,why=pcall(function()for _,p in ipairs(patches)do EEex_JITAt(p.address,p.assembly)end end)
 if not ok then for _,p in ipairs(patches)do for i=1,#p.hex,2 do EEex_WriteU8(p.address+(i-1)/2,tonumber(p.hex:sub(i,i+1),16))end end end
 EEex_EnableCodeProtection()
 assert(ok,"Manual hook patching rolled back; native module remains configured, restart required: "..tostring(why))
 M.installed=true;return M
end
local function pointer(s)return string.format("%x",EEex_UDToPtr(s))end
function M.Query(s)
 local phase,session,incarnation,owner,hp,cached,count=CBMDManualQueryNative(pointer(s))
 if not phase then return nil,"No matching native manual session" end
 return {phase=phase,session=session,incarnation=incarnation,owner=owner,hpStatus=tonumber(hp),hpCached=cached=="1",choiceCount=tonumber(count)}
end
function M.BindOwner(s,owner)return CBMDManualBindNative(pointer(s),owner)=="1"end
function M.HP(s)
 local status,total,count,a,b,c,d,e,f=CBMDManualHPNative(pointer(s));if not status then return nil end
 return {status=tonumber(status),total=tonumber(total),count=tonumber(count),beforeLevels={tonumber(a),tonumber(b),tonumber(c)},afterLevels={tonumber(d),tonumber(e),tonumber(f)}}
end
function M.HPSample(s,i)local level,hp=CBMDManualSampleNative(pointer(s),tostring(i));if not level then return nil end;return {level=tonumber(level),hp=tonumber(hp)}end
function M.Choice(s,i)
 local stat,inactive,mode,selected,status,requested,before,after=CBMDManualChoiceNative(pointer(s),tostring(i));if not stat then return nil end
 return {stat=tonumber(stat),inactive=inactive=="1",screenMode=tonumber(mode),selectedClass=tonumber(selected),status=tonumber(status),requested=tonumber(requested),before=tonumber(before),after=tonumber(after)}
end
function M.ReadOld(s,stat)
 local value=CBMDCombinedReadOldNative(pointer(s),tostring(stat));assert(value,"Native old allocation unavailable");return tonumber(value)
end
function M.ReadSkills(s)
 local result={};for i=0,6 do local n=CBMDCombinedReadSkillNative(pointer(s),tostring(i));assert(n,"Native base skill unavailable");result[i+1]=tonumber(n)end
 return result
end
function M.Constitution(s)return EEex_ReadU8(EEex_UDToPtr(s)+0x795)end
function M.Dormant(s,old)
 local value=CBMDCombinedDormantNative(pointer(s),tostring(old));assert(value and value~="-1","Native old class identity changed");return value=="1"
end
function M.SelectOld(s,account,target,rolls,choices,beforeSkills)
 local view,why=M.Query(s);assert(view and view.phase=="preparing",why or "Wrong manual selection phase")
 local prof={};for _,row in ipairs(choices.proficiencies)do if row.delta>0 then prof[#prof+1]=row.stat..":"..row.delta..";"end end
 local selected={};for i=1,7 do selected[i]=beforeSkills[i]end
 for _,row in ipairs(choices.skills)do assert(row.id>=0 and row.id<=6 and row.id%1==0,"Unknown native skill choice");selected[row.id+1]=selected[row.id+1]+row.delta end
 local before,after={},{};for i=1,7 do before[i]=(i-1)..":"..beforeSkills[i]..";";after[i]=(i-1)..":"..selected[i]..";"end
 assert(CBMDCombinedSelectNative(pointer(s),view.session,view.incarnation,tostring(account.activeClass),tostring(account.oldClass),
  tostring(account.oldLevel),tostring(target),rolls.encoded,table.concat(prof),tostring(account.oldUsableXP),tostring(account.oldKit),
  table.concat(before),table.concat(after))=="1","Native retired selection rejected; pending journal retained")
 return true
end
return M
