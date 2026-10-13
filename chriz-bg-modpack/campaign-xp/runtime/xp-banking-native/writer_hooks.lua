-- Uninstalled exact stat44 branch bridge. The generic recalc tail stays native.
local M={}
local names={"CBMBank_Writer","CBMBank_BeforeWrite","CBMBank_CompleteWrite","CBMBank_UncertainWrite",
    "CBMBank_WriterConfigure","CBMBank_WriterNativeQuery","CBMBank_WriterNativePlan","CBMBank_WriterNativeOwnedSet"}
local function verify(at,hex)
    for i=1,#hex,2 do assert(EEex_ReadU8(at+(i-1)/2)==tonumber(hex:sub(i,i+1),16),"Native XP writer ABI mismatch") end
end
local function label(name)local n=EEex_TryLabel(name);assert(type(n)=="number" and n>0,"Missing native writer label: "..name);return n end
function M.CallbackAssembly(name,suffix,numeric,callbacks)
    assert(type(callbacks)=="table" and type(callbacks.GenLuaCall)=="function","Private callback ABI adapter required")
    return EEex_FlattenTable({{"#STACK_MOD(8) #ENDL"},callbacks.GenLuaCall(name,{
        args={function(offset)return {"mov qword ptr ss:[rsp+#$(1)], rcx",{offset},"#ENDL"},"CGameSprite" end},
        returnType=numeric and EEex_LuaCallReturnType.Number or EEex_LuaCallReturnType.Boolean,labelSuffix=suffix,
    }),{"jmp done",suffix,"#ENDL call_error",suffix,": #ENDL xor eax, eax #ENDL done",suffix,
        ": #ENDL #DESTROY_SHADOW_SPACE #ENDL ret #ENDL"}})
end
function M.Install(options)
    assert(not M.attempted,"Writer bridge already attempted; restart required")
    assert(type(options)=="table" and options.researchOnly==true,"Explicit research-only writer install required")
    assert(CBMBank_Identity and CBMBank_Identity.installed,"Native identity required")
    assert(type(options.profiles)=="table" and type(options.runtime)=="table" and type(options.dllPath)=="string")
    local callbacks=options.callbacks
    assert(type(callbacks)=="table" and type(callbacks.GenLuaCall)=="function","Private callback ABI adapter required")
    for _,n in ipairs({"BeforeWrite","CompleteWrite","UncertainWrite"}) do assert(type(options.runtime[n])=="function","Missing writer callback: "..n) end
    for _,n in ipairs(names) do assert(_G[n]==nil,"Writer namespace already owned: "..n) end
    local base=EEex_GetImageBase();assert(EEex_ReadU16(base)==0x5A4D,"Invalid game module")
    local pe=base+EEex_ReadU32(base+0x3C)
    assert(EEex_ReadU32(pe)==0x4550 and EEex_ReadU16(pe+4)==0x8664,"Not a Win64 PE")
    local stamp,size=EEex_ReadU32(pe+8),EEex_ReadU32(pe+0x50);local profile
    for _,p in pairs(options.profiles) do if p.gameTimestamp==stamp and p.gameSize==size then assert(not profile,"Ambiguous writer profile");profile=p end end
    assert(profile,"Unreviewed native writer build")
    local entry=base+profile.rva;local at,tail=entry+profile.branch,entry+profile.tail
    verify(entry,profile.entryBytes);verify(at,profile.branchBytes);verify(tail,profile.tailBytes)
    assert(EEex_ReadU32(entry+profile.tableXP)==profile.rva+profile.branch,"Native stat44 dispatch changed")
    local api={label("Hardcoded_lua_tolstring"),label("Hardcoded_lua_pushstring"),label("Hardcoded_lua_pushboolean")}
    local module=EEex_LoadLibrary(options.dllPath);assert(module and module~=0,"Writer DLL load failed")
    local function proc(n)local p=EEex_GetProcAddressInternal(module,n);assert(p and p~=0,"Missing writer export: "..n);return p end
    local configure,target,query,plan,owned=proc("CBMW_Configure"),proc("CBMW_Write"),proc("CBMW_LuaQuery"),proc("CBMW_LuaPlan"),proc("CBMW_LuaApplyOwnedSet")
    local before=EEex_JITNear(M.CallbackAssembly("CBMBank_BeforeWrite","_cbmw_before",true,callbacks))
    local complete=EEex_JITNear(M.CallbackAssembly("CBMBank_CompleteWrite","_cbmw_complete",false,callbacks))
    local uncertain=EEex_JITNear(M.CallbackAssembly("CBMBank_UncertainWrite","_cbmw_uncertain",false,callbacks))
    local config=EEex_Malloc(8*8);assert(config and config~=0,"Writer configuration allocation failed")
    for i,n in ipairs({1,entry,before,complete,uncertain,api[1],api[2],api[3]}) do EEex_Write64(config+(i-1)*8,n) end
    local thunk=EEex_JITNear({"jmp ",target,"#ENDL"})
    local displacement=thunk-(at+5)
    assert(displacement>=-2147483648 and displacement<=2147483647,"Writer thunk outside native call range")
    EEex_JITNearAsLuaFunction("CBMBank_WriterConfigure",{
        "push rbx #ENDL sub rsp, 32 #ENDL mov rbx, rcx #ENDL mov rcx, ",config,
        "#ENDL call ",configure,"#ENDL mov edx, eax #ENDL mov rcx, rbx #ENDL call ",api[3],
        "#ENDL mov eax, 1 #ENDL add rsp, 32 #ENDL pop rbx #ENDL ret #ENDL"})
    M.attempted=true;assert(CBMBank_WriterConfigure(),"Native writer configure refused")
    EEex_ExposeToLua(query,"CBMBank_WriterNativeQuery")
    EEex_ExposeToLua(plan,"CBMBank_WriterNativePlan")
    EEex_ExposeToLua(owned,"CBMBank_WriterNativeOwnedSet")
    CBMBank_BeforeWrite=options.runtime.BeforeWrite;CBMBank_CompleteWrite=options.runtime.CompleteWrite;CBMBank_UncertainWrite=options.runtime.UncertainWrite
    local span=#profile.branchBytes/2;local original={};for i=0,span-1 do original[i]=EEex_ReadU8(at+i) end
    EEex_DisableCodeProtection()
    local ok,why=pcall(function()
        -- A real CALL gives the DLL a proper native return/unwind point. Its
        -- return restores RCX before the unchanged ProcessEffectList tail.
        EEex_WriteU8(at,0xE8);EEex_Write32(at+1,displacement)
        EEex_WriteU8(at+5,0x48);EEex_WriteU8(at+6,0x8B);EEex_WriteU8(at+7,0xC8)
        EEex_WriteU8(at+8,0xE9);EEex_Write32(at+9,tail-(at+13))
        for i=13,span-1 do EEex_WriteU8(at+i,0x90) end
    end)
    local restored,restoreWhy=true
    if not ok then restored,restoreWhy=pcall(function()for i=0,span-1 do EEex_WriteU8(at+i,original[i]) end end) end
    EEex_EnableCodeProtection()
    if not ok then
        if restored then for _,n in ipairs(names) do _G[n]=nil end end
        assert(restored,"Writer rollback failed; restart required: "..tostring(restoreWhy))
        error("Writer branch installation rolled back; restart required: "..tostring(why))
    end
    M.installed=true;_G.CBMBank_Writer=M;return M
end
function M.Query(sprite)
    if not M.installed or sprite==nil then return nil,"Writer binding unavailable" end
    local stage,incarnation,value,mode,before,after,origin,planned,source,effectMode,nativeResult=
        CBMBank_WriterNativeQuery(CBMBank_Identity.AddressText(sprite))
    if not stage then return nil,"No matching native XP write" end
    return {stage=stage,incarnation=incarnation,rawValue=tonumber(value),mode=tonumber(mode),preBase=tonumber(before),
        postBase=tonumber(after),origin=origin,plannedBase=tonumber(planned),source=source,
        effectMode=source=="opcode104" and tonumber(effectMode) or nil,nativeResult=tonumber(nativeResult)}
end
local function uint(n)return type(n)=="number" and n>=0 and n<=4294967295 and n%1==0 end
function M.Plan(sprite,target)
    assert(M.installed and uint(target),"Invalid native writer plan")
    return CBMBank_WriterNativePlan(CBMBank_Identity.AddressText(sprite),string.format("%.0f",target))
end
function M.ApplyOwnedSet(sprite,target,origin)
    assert(M.installed and uint(target) and (origin==1 or origin==2),"Invalid owned native writer request")
    local native,status=CBMBank_WriterNativeOwnedSet(CBMBank_Identity.AddressText(sprite),string.format("%.0f",target),tostring(origin))
    status=tonumber(status)
    return native~=nil and (status==1 or status==6),tonumber(native),status
end
return M
