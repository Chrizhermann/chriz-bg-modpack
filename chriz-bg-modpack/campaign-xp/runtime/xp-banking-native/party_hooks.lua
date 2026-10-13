-- Inert until explicit Install. Changes ONE call in AddCharacterToParty after
-- native party membership is written, before later recruitment awards. It does
-- not replace GetNameRef globally or infer membership from a portrait number.
local M={}
local function label(name)
    local value=EEex_TryLabel(name)
    assert(type(value)=="number" and value>0,"Missing native label: "..name)
    return value
end
local function verify(at,hex)
    for i=1,#hex,2 do
        assert(EEex_ReadU8(at+(i-1)/2)==tonumber(hex:sub(i,i+1),16),
            "Native party boundary changed; re-audit required")
    end
end
function M.Install(options)
    assert(not M.installed,"Party hook already installed")
    assert(type(options)=="table" and options.researchOnly==true,"Explicit research-only install required")
    assert(CBMBank_Identity and CBMBank_Identity.installed,"Native identity hooks required first")
    assert(type(options.runtime)=="table" and type(options.runtime.OnLoaded)=="function")
    assert(type(options.resetHooks)=="table" and type(options.resetHooks.CallbackAssembly)=="function")
    assert(type(options.profiles)=="table" and type(options.dllPath)=="string")
    assert(_G.CBMBank_OnPartyReady==nil and _G.CBMBank_PartyConfigure==nil,"Party callback namespace already owned")
    local base=EEex_GetImageBase()
    assert(EEex_ReadU16(base)==0x5A4D,"Invalid native game module")
    local header=base+EEex_ReadU32(base+0x3C)
    assert(EEex_ReadU32(header)==0x4550 and EEex_ReadU16(header+4)==0x8664,"Not a Win64 PE")
    local timestamp,size=EEex_ReadU32(header+8),EEex_ReadU32(header+0x50)
    local profile
    for _,candidate in pairs(options.profiles) do
        if candidate.gameTimestamp==timestamp and candidate.gameSize==size then
            assert(not profile,"Ambiguous native party profile"); profile=candidate
        end
    end
    assert(profile,"Native party build has not been reviewed")
    verify(base+profile.caller,profile.callerBytes)
    verify(base+profile.target,profile.targetBytes)
    local at=base+profile.site
    assert(EEex_ReadU8(at)==0xE8 and at+5+EEex_Read32(at+1)==base+profile.target,
        "Native party call target mismatch")
    local module=EEex_LoadLibrary(options.dllPath)
    assert(module and module~=0,"Bank native DLL failed to load")
    local function proc(name)
        local result=EEex_GetProcAddressInternal(module,name)
        assert(result and result~=0,"Missing native party export: "..name); return result
    end
    local configure,target=proc("CBMP_Configure"),proc("CBMP_OnPartyReady")
    local pushBoolean=label("Hardcoded_lua_pushboolean")
    local notify=EEex_JITNear(options.resetHooks.CallbackAssembly("CBMBank_OnPartyReady","_cbmp_ready"))
    local config=EEex_Malloc(3*8)
    assert(config and config~=0,"Party configuration allocation failed")
    EEex_Write64(config,1); EEex_Write64(config+8,base+profile.target); EEex_Write64(config+16,notify)
    -- The E8 retains its ordinary return address. This near leaf thunk adds no
    -- frame; the compiled C++ target has normal compiler-owned unwind metadata.
    local thunk=EEex_JITNear({"jmp ",target,"#ENDL"})
    local displacement=thunk-(at+5)
    assert(displacement>=-2147483648 and displacement<=2147483647,"Party thunk is out of call range")
    EEex_JITNearAsLuaFunction("CBMBank_PartyConfigure",{
        "push rbx #ENDL sub rsp, 32 #ENDL mov rbx, rcx #ENDL mov rcx, ",config,
        "#ENDL call ",configure,"#ENDL mov edx, eax #ENDL mov rcx, rbx #ENDL call ",pushBoolean,
        "#ENDL mov eax, 1 #ENDL add rsp, 32 #ENDL pop rbx #ENDL ret #ENDL"})
    assert(CBMBank_PartyConfigure(),"Party native configuration refused")
    CBMBank_OnPartyReady=function(sprite) options.runtime.OnLoaded(sprite); return true end
    local original=EEex_Read32(at+1)
    EEex_DisableCodeProtection()
    local ok,why=pcall(EEex_Write32,at+1,displacement)
    if not ok then EEex_Write32(at+1,original) end
    EEex_EnableCodeProtection()
    if not ok then CBMBank_OnPartyReady=nil; error("Party hook installation rolled back: "..tostring(why)) end
    M.installed=true
    return M
end
return M
