-- Uninstalled; explicit Install only. Original opcode104 leaf is fully checked.
local M={}
local function label(name)
    local value=EEex_TryLabel(name)
    assert(type(value)=="number" and value>0,"Missing native award label: "..name);return value
end
function M.CallbackAssembly(name,suffix,numberResult,callbacks)
    assert(type(callbacks)=="table" and type(callbacks.GenLuaCall)=="function","Private callback ABI adapter required")
    return EEex_FlattenTable({{"#STACK_MOD(8) #ENDL"},callbacks.GenLuaCall(name,{
        args={
            function(offset)return {"mov qword ptr ss:[rsp+#$(1)], rcx",{offset},"#ENDL"},"CGameSprite" end,
            function(offset)return {"mov qword ptr ss:[rsp+#$(1)], rdx",{offset},"#ENDL"},"CGameEffect" end,
        },returnType=numberResult and EEex_LuaCallReturnType.Number or EEex_LuaCallReturnType.Boolean,labelSuffix=suffix,
    }),{"jmp done",suffix,"#ENDL call_error",suffix,": #ENDL xor eax, eax #ENDL done",suffix,
        ": #ENDL #DESTROY_SHADOW_SPACE #ENDL ret #ENDL"}})
end
function M.Install(options)
    assert(not M.attempted,"Award bridge already attempted; restart required")
    assert(type(options)=="table" and options.researchOnly==true,"Explicit research-only award install required")
    assert(CBMBank_Identity and CBMBank_Identity.installed,"Native identity hooks required")
    assert(type(options.runtime)=="table" and type(options.profiles)=="table" and type(options.dllPath)=="string")
    local callbacks=options.callbacks
    assert(type(callbacks)=="table" and type(callbacks.GenLuaCall)=="function","Private callback ABI adapter required")
    for _,name in ipairs({"BeforeAward","CompleteAward","UncertainAward"}) do
        assert(type(options.runtime[name])=="function","Missing accounting callback: "..name)
    end
    for _,name in ipairs({"CBMBank_Award","CBMBank_BeforeAward","CBMBank_CompleteAward","CBMBank_UncertainAward",
        "CBMBank_AwardConfigure","CBMBank_AwardNativeQuery","CBMBank_AwardNativeFallbacks"}) do
        assert(_G[name]==nil,"Award namespace already owned: "..name)
    end
    local base=EEex_GetImageBase()
    assert(EEex_ReadU16(base)==0x5A4D,"Invalid game module")
    local pe=base+EEex_ReadU32(base+0x3C)
    assert(EEex_ReadU32(pe)==0x4550 and EEex_ReadU16(pe+4)==0x8664,"Not a Win64 PE")
    local stamp,size=EEex_ReadU32(pe+8),EEex_ReadU32(pe+0x50)
    local profile
    for _,p in pairs(options.profiles) do
        if p.gameTimestamp==stamp and p.gameSize==size then assert(not profile,"Ambiguous award profile");profile=p end
    end
    assert(profile,"Unreviewed native XP award build")
    local at,span=base+profile.rva,profile.span
    for i=1,#profile.bytes,2 do assert(EEex_ReadU8(at+(i-1)/2)==tonumber(profile.bytes:sub(i,i+1),16),
        "Native XP leaf changed; re-audit required") end
    local apis={label("Hardcoded_lua_tolstring"),label("Hardcoded_lua_pushstring"),label("Hardcoded_lua_pushboolean")}
    local module=EEex_LoadLibrary(options.dllPath);assert(module and module~=0,"Award DLL load failed")
    local function proc(name)
        local n=EEex_GetProcAddressInternal(module,name);assert(n and n~=0,"Missing award export: "..name);return n
    end
    local configure,target,query=proc("CBMA_Configure"),proc("CBMA_ApplyEffect"),proc("CBMA_LuaQuery")
    local fallbacks=proc("CBMA_LuaFallbacks")
    local original=EEex_JITNear(EEex_FlattenTable({EEex_StoreBytesAssembly(at,span),{"jmp ",at+span,"#ENDL"}}))
    local before=EEex_JITNear(M.CallbackAssembly("CBMBank_BeforeAward","_cbma_before",true,callbacks))
    local complete=EEex_JITNear(M.CallbackAssembly("CBMBank_CompleteAward","_cbma_complete",false,callbacks))
    local uncertain=EEex_JITNear(M.CallbackAssembly("CBMBank_UncertainAward","_cbma_uncertain",false,callbacks))
    local config=EEex_Malloc(7*8);assert(config and config~=0,"Award configuration allocation failed")
    for i,n in ipairs({1,original,before,complete,uncertain,apis[1],apis[2]}) do EEex_Write64(config+(i-1)*8,n) end
    EEex_JITNearAsLuaFunction("CBMBank_AwardConfigure",{
        "push rbx #ENDL sub rsp, 32 #ENDL mov rbx, rcx #ENDL mov rcx, ",config,
        "#ENDL call ",configure,"#ENDL mov edx, eax #ENDL mov rcx, rbx #ENDL call ",apis[3],
        "#ENDL mov eax, 1 #ENDL add rsp, 32 #ENDL pop rbx #ENDL ret #ENDL"})
    M.attempted=true;assert(CBMBank_AwardConfigure(),"Award native configuration refused")
    EEex_ExposeToLua(query,"CBMBank_AwardNativeQuery")
    EEex_ExposeToLua(fallbacks,"CBMBank_AwardNativeFallbacks")
    CBMBank_BeforeAward=options.runtime.BeforeAward
    CBMBank_CompleteAward=options.runtime.CompleteAward
    CBMBank_UncertainAward=options.runtime.UncertainAward
    local bytes={};for i=0,span-1 do bytes[i]=EEex_ReadU8(at+i) end
    EEex_DisableCodeProtection()
    local ok,why=pcall(EEex_HookReplaceFunctionMaintainOriginal,at,span,"CBMA::original_ApplyEffect",target)
    local restored,restoreWhy=true
    if not ok then restored,restoreWhy=pcall(function()for i=0,span-1 do EEex_WriteU8(at+i,bytes[i]) end end) end
    EEex_EnableCodeProtection()
    if not ok then
        if restored then
            CBMBank_AwardNativeQuery=nil;CBMBank_AwardNativeFallbacks=nil
            CBMBank_BeforeAward=nil;CBMBank_CompleteAward=nil;CBMBank_UncertainAward=nil
        end
        assert(restored,"Award rollback failed; restart required: "..tostring(restoreWhy))
        error("Award entry installation rolled back; restart required: "..tostring(why))
    end
    M.installed=true;_G.CBMBank_Award=M;return M
end
function M.Query(sprite,effect)
    if not M.installed or sprite==nil or effect==nil then return nil,"Award binding unavailable" end
    local stage,incarnation,preBase,amount,applied,remainder,result,postBase=CBMBank_AwardNativeQuery(
        CBMBank_Identity.AddressText(sprite),CBMBank_Identity.AddressText(effect))
    if not stage then return nil,"No matching native actor/effect award" end
    return {stage=stage,incarnation=incarnation,preBase=tonumber(preBase),amount=tonumber(amount),
        applied=tonumber(applied),remainder=tonumber(remainder),nativeResult=tonumber(result),postBase=tonumber(postBase)}
end
-- XP changes the bank could not take that ran the game's own code instead
-- (award and writer bridges, the writer's including stat44 setter writes),
-- process-wide, with each bridge's last reason, then the changes that wrote
-- nothing because their actor's lifetime ended during preparation (status 11),
-- then the setter writes kept unwritten because another thread's lifetime event
-- at their actor's address left it unknown (status 12) and their list.
function M.Fallbacks()
    if not M.installed then return nil,"Award binding unavailable" end
    local total,award,writer,ended,kept,keptList=CBMBank_AwardNativeFallbacks()
    total,award,writer,ended,kept=tonumber(total),tonumber(award),tonumber(writer),tonumber(ended),tonumber(kept)
    if not total or not award or not writer or not ended or not kept or type(keptList)~="string" then
        return nil,"Native XP fallback count unavailable"
    end
    return total,award,writer,ended,kept,keptList
end
return M
