-- UNINSTALLED: explicit research-only Install is the sole native mutation path.
-- Native DLL must include identity_native.cpp + reset_native.cpp; identity hooks
-- must already be active on the same engine thread, before character loading.
local M={}
local function label(name)
    local n=EEex_TryLabel(name)
    assert(type(n)=="number" and n>0,"Missing reviewed native label: "..name)
    return n
end
local function verify(at,hex)
    for i=1,#hex,2 do assert(EEex_ReadU8(at+(i-1)/2)==tonumber(hex:sub(i,i+1),16),"Reset/cap native ABI mismatch") end
end
-- Win64 entry RSP is eight bytes below a 16-byte boundary. GenLuaCall captures
-- RCX/RDX into its own local area BEFORE clobbering volatile registers, preserves
-- RBX, supplies aligned shadow space and uses the active LuaProvider pcall shim.
function M.CallbackAssembly(name,suffix,callbacks)
    callbacks=callbacks or M.callbacks
    assert(type(callbacks)=="table" and type(callbacks.GenLuaCall)=="function","Private callback ABI adapter required")
    return EEex_FlattenTable({{"#STACK_MOD(8) #ENDL"},callbacks.GenLuaCall(name,{
        args={
            function(offset) return {"mov qword ptr ss:[rsp+#$(1)], rcx",{offset},"#ENDL"},"CGameSprite" end,
            function(offset) return {"movzx eax, dl #ENDL mov qword ptr ss:[rsp+#$(1)], rax",{offset},"#ENDL"} end,
        },returnType=EEex_LuaCallReturnType.Boolean,labelSuffix=suffix,
    }),{"jmp done",suffix,"#ENDL call_error",suffix,": #ENDL xor eax, eax #ENDL done",suffix,
        ": #ENDL #DESTROY_SHADOW_SPACE #ENDL ret #ENDL"}})
end
function M.Install(options)
    assert(not M.installed and not M.attempted,"Reset bridge already attempted; restart required")
    assert(type(options)=="table" and options.researchOnly==true,"Explicit research-only reset install required")
    assert(CBMBank_Identity and CBMBank_Identity.installed,"Native identity hooks required first")
    assert(type(options.runtime)=="table" and type(options.profiles)=="table" and type(options.dllPath)=="string")
    local callbacks=options.callbacks
    assert(type(callbacks)=="table" and type(callbacks.GenLuaCall)=="function","Private callback ABI adapter required")
    for _,name in ipairs({"PrepareDual","CompleteDual","UncertainDual","CaptureDualPreview"}) do
        assert(type(options.runtime[name])=="function","Missing root accounting callback: "..name)
    end
    for _,name in ipairs({"CBMBank_Reset","CBMBank_PrepareDual","CBMBank_CompleteDual","CBMBank_UncertainDual",
        "CBMBank_ResetConfigure","CBMBank_ResetNativeQuery","CBMBank_ResetNativeCap",
        "CBMBank_CaptureDualPreview","CBMBank_ResetNativePreviewQuery"}) do
        assert(_G[name]==nil,"Reset namespace already owned: "..name)
    end
    local game=EEex_GetImageBase()
    assert(EEex_ReadU16(game)==0x5A4D,"Invalid game module")
    local header=game+EEex_ReadU32(game+0x3C)
    assert(EEex_ReadU32(header)==0x4550 and EEex_ReadU16(header+4)==0x8664,"Not a Win64 PE")
    local timestamp,size=EEex_ReadU32(header+8),EEex_ReadU32(header+0x50)
    local profile
    for _,candidate in pairs(options.profiles) do
        if candidate.gameTimestamp==timestamp and candidate.gameSize==size then
            assert(not profile,"Ambiguous reset profile"); profile=candidate
        end
    end
    assert(profile,"Unreviewed reset game build")
    local at,span=game+profile.entry.rva,profile.entry.span
    verify(at,profile.entry.bytes)
    verify(game+profile.createEntry.rva,profile.createEntry.bytes)
    for _,call in ipairs({profile.removeCall,profile.previewCall}) do
        verify(game+call.caller,call.callerBytes);verify(game+call.target,call.targetBytes)
        assert(EEex_ReadU8(game+call.site)==0xE8 and game+call.site+5+EEex_Read32(game+call.site+1)==game+call.target,
            "Dual UI call target changed")
    end
    verify(game+profile.denyRva,profile.denyBytes)
    verify(game+profile.capRva,profile.capBytes)
    local chitin=label("g_pBaldurChitin")
    local luaAPI={label("Hardcoded_lua_tolstring"),label("Hardcoded_lua_pushstring"),label("Hardcoded_lua_pushboolean")}
    local module=EEex_LoadLibrary(options.dllPath)
    assert(module and module~=0,"Reset native DLL failed to load")
    local function proc(name)
        local result=EEex_GetProcAddressInternal(module,name)
        assert(result and result~=0,"Reset DLL lacks "..name); return result
    end
    local target,configure,query,cap=proc("CBMR_MakeDualClass"),proc("CBMR_Configure"),proc("CBMR_LuaQuery"),proc("CBMR_LuaNativeCap")
    local createTarget,removeTarget,startTarget,previewQuery=proc("CBMR_CreateMakeDualClass"),proc("CBMR_RemoveAbilities"),
        proc("CBMR_StartEditing"),proc("CBMR_LuaPreviewQuery")
    local original=EEex_JITNear(EEex_FlattenTable({EEex_StoreBytesAssembly(at,span),{"jmp ",at+span,"#ENDL"}}))
    local createAt,createSpan=game+profile.createEntry.rva,profile.createEntry.span
    local originalCreate=EEex_JITNear(EEex_FlattenTable({EEex_StoreBytesAssembly(createAt,createSpan),{"jmp ",createAt+createSpan,"#ENDL"}}))
    local prepare=EEex_JITNear(M.CallbackAssembly("CBMBank_PrepareDual","_cbmr_prepare",callbacks))
    local complete=EEex_JITNear(M.CallbackAssembly("CBMBank_CompleteDual","_cbmr_complete",callbacks))
    local uncertain=EEex_JITNear(M.CallbackAssembly("CBMBank_UncertainDual","_cbmr_uncertain",callbacks))
    local preview=EEex_JITNear(M.CallbackAssembly("CBMBank_CaptureDualPreview","_cbmr_preview",callbacks))
    local callPatches={}
    for _,item in ipairs({{profile.removeCall,removeTarget},{profile.previewCall,startTarget}}) do
        local site=game+item[1].site
        local thunk=EEex_JITNear({"jmp ",item[2],"#ENDL"})
        local displacement=thunk-(site+5)
        assert(displacement>=-2147483648 and displacement<=2147483647,"Dual UI thunk out of call range")
        callPatches[#callPatches+1]={site=site,displacement=displacement}
    end
    local config=EEex_Malloc(14*8)
    assert(config and config~=0,"Reset configuration allocation failed")
    local values={2,original,prepare,complete,uncertain,game+profile.capRva,chitin,luaAPI[1],luaAPI[2],
        originalCreate,game+profile.removeCall.target,game+profile.previewCall.target,game+profile.denyRva,preview}
    for i,value in ipairs(values) do EEex_Write64(config+(i-1)*8,value) end
    EEex_JITNearAsLuaFunction("CBMBank_ResetConfigure",{"push rbx #ENDL sub rsp, 32 #ENDL mov rbx, rcx #ENDL mov rcx, ",config,
        "#ENDL call ",configure,"#ENDL mov edx, eax #ENDL mov rcx, rbx #ENDL call ",luaAPI[3],
        "#ENDL mov eax, 1 #ENDL add rsp, 32 #ENDL pop rbx #ENDL ret #ENDL"})
    M.attempted=true
    assert(CBMBank_ResetConfigure(),"Reset native configuration refused")
    local exposed,exposeWhy=pcall(function()
        EEex_ExposeToLua(query,"CBMBank_ResetNativeQuery")
        EEex_ExposeToLua(cap,"CBMBank_ResetNativeCap")
        EEex_ExposeToLua(previewQuery,"CBMBank_ResetNativePreviewQuery")
    end)
    if not exposed then
        CBMBank_ResetNativeQuery=nil; CBMBank_ResetNativeCap=nil; CBMBank_ResetNativePreviewQuery=nil
        error("Reset query exposure failed before patching; restart required: "..tostring(exposeWhy))
    end
    CBMBank_PrepareDual=options.runtime.PrepareDual
    CBMBank_CompleteDual=options.runtime.CompleteDual
    CBMBank_UncertainDual=options.runtime.UncertainDual
    CBMBank_CaptureDualPreview=options.runtime.CaptureDualPreview
    local saved={}
    for _,range in ipairs({{at,span},{createAt,createSpan},{callPatches[1].site,5},{callPatches[2].site,5}}) do
        for i=0,range[2]-1 do saved[range[1]+i]=EEex_ReadU8(range[1]+i) end
    end
    EEex_DisableCodeProtection()
    local ok,why=pcall(function()
        EEex_HookReplaceFunctionMaintainOriginal(at,span,"CBMR::original_MakeDualClass",target)
        EEex_HookReplaceFunctionMaintainOriginal(createAt,createSpan,"CBMR::original_CreateMakeDualClass",createTarget)
        for _,patch in ipairs(callPatches) do EEex_Write32(patch.site+1,patch.displacement) end
    end)
    local restored,restoreWhy=true
    if not ok then restored,restoreWhy=pcall(function() for address,byte in pairs(saved) do EEex_WriteU8(address,byte) end end) end
    EEex_EnableCodeProtection()
    if not ok then
        CBMBank_PrepareDual=nil; CBMBank_CompleteDual=nil; CBMBank_UncertainDual=nil
        CBMBank_CaptureDualPreview=nil; CBMBank_ResetNativePreviewQuery=nil
        CBMBank_ResetNativeQuery=nil; CBMBank_ResetNativeCap=nil
        if not restored then error("Reset rollback failed; restart required: "..tostring(restoreWhy)) end
        error("Reset entry installation rolled back; restart required: "..tostring(why))
    end
    M.installed=true; M.callbacks=callbacks; _G.CBMBank_Reset=M
    return M
end
function M.Query(sprite)
    if not M.installed or sprite==nil then return nil,"Reset bridge unavailable" end
    local stage,incarnation,before,newClass,path=CBMBank_ResetNativeQuery(CBMBank_Identity.AddressText(sprite))
    if not stage then return nil,"No native reset for this actor lifetime" end
    return {stage=stage,incarnation=incarnation,preBase=tonumber(before),newClass=tonumber(newClass),path=path}
end
function M.PreviewQuery(sprite)
    if not M.installed or sprite==nil then return nil,"Reset bridge unavailable" end
    local stage,incarnation,before=CBMBank_ResetNativePreviewQuery(CBMBank_Identity.AddressText(sprite))
    if not stage then return nil,"No native pre-preview scope for this actor lifetime" end
    return {stage=stage,incarnation=incarnation,preBase=tonumber(before)}
end
function M.NativeCap(sprite)
    assert(M.installed and sprite~=nil,"Reset bridge unavailable")
    local cap=CBMBank_ResetNativeCap(CBMBank_Identity.AddressText(sprite))
    assert(cap,"Native ceiling unavailable for this actor lifetime")
    return tonumber(cap)
end
return M
