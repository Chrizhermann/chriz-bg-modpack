-- UNINSTALLED research loader. Loading this file has NO native/EEex side effects.
-- Explicit Install({researchOnly=true,dllPath=...,profiles=...}) installs the six
-- audited entry shims using actual pinned InfinityLoader and EEex APIs.
-- Must run on the engine Lua thread BEFORE actors load. Existing actors fail
-- Query instead of receiving guessed identities. No marshal handler is registered.
local M = {}
local actorDestroyEntry
local order = {"copy", "marshal", "export", "import", "construct", "destruct"}
local exports = {copy="CBMI_Copy", marshal="CBMI_Marshal", export="CBMI_CharacterExport",
    import="CBMI_CharacterImport", construct="CBMI_Construct", destruct="CBMI_Destruct"}
local function required(name)
    assert(type(_G[name]) == "function", "Missing native host capability: " .. name)
    return _G[name]
end
local function label(name)
    local value = EEex_TryLabel(name)
    assert(type(value) == "number" and value > 0, "Missing native label: " .. name)
    return value
end
local function pe(base)
    assert(EEex_ReadU16(base) == 0x5A4D, "Native module does not have a DOS header")
    local header = base + EEex_ReadU32(base+0x3C)
    assert(EEex_ReadU32(header) == 0x4550 and EEex_ReadU16(header+4) == 0x8664,
        "Native module is not a Win64 PE")
    return EEex_ReadU32(header+8), EEex_ReadU32(header+0x50)
end

-- Resolve the loaded module before choosing its reviewed lifetime entries.
-- Subtracting one research DLL's function RVA from another DLL's label does
-- not produce a module base, even when the function's ABI is unchanged.
function M.ResolveProfile(profiles)
    local game = EEex_GetImageBase()
    local timestamp, size = pe(game)
    local eeex = required("EEex_LoadLibrary")("EEex.dll")
    assert(type(eeex)=="number" and eeex>0,"Loaded EEex module unavailable")
    local eeexTimestamp, eeexSize = pe(eeex)
    local selected, selectedKey
    for key, candidate in pairs(profiles) do
        if candidate.gameTimestamp==timestamp and candidate.gameSize==size then
            local function consider(build)
                if build.eeexTimestamp~=eeexTimestamp or build.eeexSize~=eeexSize then return end
                assert(not selected,"Ambiguous native game/EEex profile")
                selected={};for name,value in pairs(candidate)do selected[name]=value end
                selected.eeexTimestamp,selected.eeexSize=build.eeexTimestamp,build.eeexSize
                selected.entries={};for name,value in pairs(candidate.entries)do selected.entries[name]=value end
                for name,value in pairs(build.entries)do selected.entries[name]=value end
                selectedKey=key
            end
            consider(candidate)
            for _,build in pairs(candidate.eeexAlternates or{})do consider(build)end
        end
    end
    assert(selected,"Unreviewed native game/EEex build")
    return selected, selectedKey, game, eeex
end

-- EEex's hook writer cannot place the two lifetime entries inside EEex.dll.
-- High-entropy ASLR loads that module more than 2 GB from the game, beside
-- which EEex keeps its code pages, so AsmJit refuses the rel32 jump
-- (RelocOffsetOutOfRange) and EEex_JITAt discards that error. Separately,
-- EEex_DisableCodeProtection leaves EEex.dll's code read-only (lab, EEex 1.2.0
-- on 2.7.3, 2026-10-17). Such an entry instead jumps to a private relay page
-- within rel32 reach that holds one absolute jump to our shim: the entry and
-- relay shape that component 430 authenticates.
local GRANULARITY, REACH = 0x10000, 0x7FFF0000
local PAGE_EXECUTE_READ, PAGE_EXECUTE_READWRITE = 0x20, 0x40

-- Three kernel32 calls sharing one argument block: [0] address, [8] size,
-- [16] protection, [24] result, [32] previous protection.
function M.NativeMemory()
    local kernel = required("EEex_LoadLibrary")("kernel32.dll")
    assert(type(kernel) == "number" and kernel > 0, "kernel32 is unavailable")
    local function import(name)
        local value = EEex_GetProcAddressInternal(kernel, name)
        assert(type(value) == "number" and value > 0, "Missing kernel32 export: " .. name)
        return value
    end
    local cell = EEex_Malloc(40)
    assert(cell and cell ~= 0, "Native memory helper allocation failed")
    local function stub(name, body)
        local assembly = {"push rbx #ENDL sub rsp, 32 #ENDL mov rbx, ", cell, " #ENDL "}
        for _, part in ipairs(body) do assembly[#assembly+1] = part end
        assembly[#assembly+1] = "xor eax, eax #ENDL add rsp, 32 #ENDL pop rbx #ENDL ret #ENDL"
        EEex_JITNearAsLuaFunction(name, assembly)
        local fn = _G[name]
        _G[name] = nil -- Private: only this module holds the helper.
        assert(type(fn) == "function", "Native memory helper unavailable: " .. name)
        return fn
    end
    local allocate = stub("CBMBank_IdentityVirtualAlloc", {"mov rcx, qword ptr [rbx] #ENDL mov edx, 4096 #ENDL ",
        "mov r8d, 12288 #ENDL mov r9d, 4 #ENDL call ", import("VirtualAlloc"),
        " #ENDL mov qword ptr [rbx+24], rax #ENDL "})
    local protect = stub("CBMBank_IdentityVirtualProtect", {"mov rcx, qword ptr [rbx] #ENDL ",
        "mov rdx, qword ptr [rbx+8] #ENDL mov r8d, dword ptr [rbx+16] #ENDL lea r9, qword ptr [rbx+32] #ENDL call ",
        import("VirtualProtect"), " #ENDL mov dword ptr [rbx+24], eax #ENDL "})
    local flush = stub("CBMBank_IdentityFlushCode", {"call ", import("GetCurrentProcess"),
        " #ENDL mov rcx, rax #ENDL mov rdx, qword ptr [rbx] #ENDL mov r8, qword ptr [rbx+8] #ENDL call ",
        import("FlushInstructionCache"), " #ENDL mov dword ptr [rbx+24], eax #ENDL "})
    local function invoke(fn, at, size, protection)
        EEex_Write64(cell, at); EEex_Write64(cell+8, size or 0); EEex_Write64(cell+16, protection or 0)
        EEex_Write64(cell+24, 0); EEex_Write64(cell+32, 0)
        fn()
    end
    local memory = {}
    function memory.Allocate(at) -- One committed read/write page, or 0 when that address is taken.
        invoke(allocate, at)
        return EEex_ReadU32(cell+24) + EEex_ReadU32(cell+28)*4294967296
    end
    function memory.Protect(at, size, protection) -- Returns the previous protection.
        invoke(protect, at, size, protection)
        assert(EEex_ReadU32(cell+24) ~= 0, "Native code page protection change refused")
        return EEex_ReadU32(cell+32)
    end
    function memory.Flush(at, size)
        invoke(flush, at, size)
        assert(EEex_ReadU32(cell+24) ~= 0, "Native instruction cache flush failed")
    end
    return memory
end

-- Same search as 430's relay pages: the nearest free allocation granule.
function M.AllocateNear(memory, entry)
    local center = entry - entry % GRANULARITY
    for distance = GRANULARITY, REACH - GRANULARITY, GRANULARITY do
        for _, at in ipairs({center + distance, center - distance}) do
            if at > 0 then
                local page = memory.Allocate(at)
                if page ~= 0 then
                    assert(page == at, "Native relay page was not placed where requested")
                    return page
                end
            end
        end
    end
    error("No free page within rel32 reach of a native lifetime entry")
end

local function relativeJump(at, span, destination)
    local delta = destination - (at+5)
    assert(delta >= -2147483648 and delta <= 2147483647, "Native relay is outside rel32 reach")
    delta = delta % 4294967296
    local bytes = {[0]=0xE9}
    for i=1,4 do bytes[i] = delta % 256; delta = math.floor(delta/256) end
    for i=5,span-1 do bytes[i] = 0x90 end
    return bytes
end
local function absoluteJump(target)
    local bytes = {[0]=0xFF, 0x25, 0, 0, 0, 0}
    for i=6,13 do bytes[i] = target % 256; target = math.floor(target/256) end
    return bytes
end

-- Writes an entry that EEex_DisableCodeProtection does not make writable, then
-- restores the protection it had before our first change, even after a failed
-- restore left it writable.
local function writeFar(e, bytes)
    local previous = M.memory.Protect(e.at, e.span, PAGE_EXECUTE_READWRITE)
    e.protection = e.protection or previous
    local ok, why = pcall(function()
        for i=0,e.span-1 do if EEex_ReadU8(e.at+i) ~= bytes[i] then EEex_WriteU8(e.at+i, bytes[i]) end end
    end)
    M.memory.Protect(e.at, e.span, e.protection)
    M.memory.Flush(e.at, e.span)
    if not ok then error(why, 0) end
end

-- Follows an installed entry: E9 to its relay, then E9 or FF25 to the handler.
-- Nil for anything else, including an entry EEex left unwritten.
function M.JumpTarget(at, span)
    if EEex_ReadU8(at) ~= 0xE9 then return nil end
    for i=5,span-1 do if EEex_ReadU8(at+i) ~= 0x90 then return nil end end
    local relay = at + 5 + EEex_Read32(at+1)
    local op = EEex_ReadU8(relay)
    if op == 0xE9 then return relay + 5 + EEex_Read32(relay+1) end
    if op == 0xFF and EEex_ReadU8(relay+1) == 0x25 then
        local slot = relay + 6 + EEex_Read32(relay+2)
        return EEex_ReadU32(slot) + EEex_ReadU32(slot+4)*4294967296
    end
end

-- The bootstrap's rollback restores remembered ranges; these addresses need
-- the protection-aware writer.
function M.IsFar(at) return M.far ~= nil and M.far[at] ~= nil end
function M.RestoreFar(at, bytes, count)
    local e = M.far and M.far[at]
    assert(e and count == e.span, "Not an identity entry outside the game image")
    for i=0,count-1 do
        if EEex_ReadU8(at+i) ~= bytes[i] then return writeFar(e, bytes) end
    end
end

function M.Install(options)
    assert(not M.installed and not M.attempted, "Identity hooks already attempted; restart required")
    assert(type(options) == "table" and options.researchOnly == true,
        "Explicit research-only identity installation required")
    assert(type(options.dllPath) == "string" and type(options.profiles) == "table")
    assert(EEex_Active == true, "EEex is required")
    for _, name in ipairs({"EEex_LoadLibrary", "EEex_GetProcAddressInternal", "EEex_ExposeToLua",
        "EEex_JITNearAsLuaFunction", "EEex_JITNear", "EEex_StoreBytesAssembly", "EEex_FlattenTable",
        "EEex_HookReplaceFunctionMaintainOriginal", "EEex_GetImageBase", "EEex_TryLabel", "EEex_DefineAssemblyLabel",
        "EEex_ReadU8", "EEex_ReadU16", "EEex_ReadU32", "EEex_Read32", "EEex_WriteU8", "EEex_Write64",
        "EEex_Malloc", "EEex_DisableCodeProtection", "EEex_EnableCodeProtection", "EEex_UDToPtr"}) do required(name) end
    assert(_G.CBMBank_Identity == nil and _G.CBMBank_IdentityNativeQuery == nil
        and _G.CBMBank_IdentityConfigure == nil, "Identity namespace already owned")
    local profile, _, game, eeex = M.ResolveProfile(options.profiles)
    local entries = {}
    for _, slot in ipairs(order) do
        local e = profile.entries[slot]
        assert(#e.bytes == e.span*2 and e.span >= 5, "Malformed reviewed entry profile")
        local at = (e.module == "game" and game or eeex) + e.rva
        if e.label then assert(label(e.label) == at, "Native lifetime label mismatch") end
        local bytes = {}
        for i=0,e.span-1 do
            bytes[i] = EEex_ReadU8(at+i)
            assert(bytes[i] == tonumber(e.bytes:sub(i*2+1,i*2+2),16),
                "Native entry already modified or ABI mismatch: " .. slot)
        end
        entries[slot] = {at=at, span=e.span, bytes=bytes, far=e.module ~= "game"}
    end
    -- Resolve every host capability and native export BEFORE modifying code.
    local apis = {label("Hardcoded_lua_tolstring"),label("Hardcoded_lua_pushstring"),label("Hardcoded_lua_pushboolean"),
        label("EEex::bStripUUID"),label("EEex::bNoUUID")}
    local module = EEex_LoadLibrary(options.dllPath)
    assert(type(module) == "number" and module > 0, "Identity research DLL failed to load")
    local function proc(name)
        local value = EEex_GetProcAddressInternal(module,name)
        assert(type(value) == "number" and value > 0, "Missing identity DLL export: " .. name)
        return value
    end
    local configure, query = proc("CBMI_Configure"), proc("CBMI_LuaQuery")
    for _, slot in ipairs(order) do entries[slot].target = proc(exports[slot]) end
    -- Relays for entries outside EEex's reach exist before any entry is patched.
    for _, slot in ipairs(order) do
        local e = entries[slot]
        if e.far then
            M.memory = M.memory or M.NativeMemory()
            e.relay = M.AllocateNear(M.memory, e.at)
            local code = absoluteJump(e.target)
            for i=0,13 do EEex_WriteU8(e.relay+i, code[i]) end
            M.memory.Protect(e.relay, 0x1000, PAGE_EXECUTE_READ)
            M.memory.Flush(e.relay, 14)
            M.far = M.far or {}
            M.far[e.at] = e
        end
    end
    -- Prebuild valid originals before ANY entry can reach a replacement. The
    -- stock hook API makes an equivalent second original label during patching.
    local config = EEex_Malloc(12*8)
    assert(config and config ~= 0, "Identity configuration allocation failed")
    EEex_Write64(config,1)
    for i, slot in ipairs(order) do
        local e = entries[slot]
        e.original = EEex_JITNear(EEex_FlattenTable({EEex_StoreBytesAssembly(e.at,e.span),
            {"jmp ",e.at+e.span,"#ENDL"}}))
        EEex_Write64(config+i*8,e.original)
    end
    for i, value in ipairs(apis) do EEex_Write64(config+(6+i)*8,value) end
    EEex_JITNearAsLuaFunction("CBMBank_IdentityConfigure", {
        "push rbx #ENDL sub rsp, 32 #ENDL mov rbx, rcx #ENDL mov rcx, ",config,
        "#ENDL call ",configure,"#ENDL mov edx, eax #ENDL mov rcx, rbx #ENDL call ",apis[3],
        "#ENDL mov eax, 1 #ENDL add rsp, 32 #ENDL pop rbx #ENDL ret #ENDL"})
    M.attempted = true -- Native Configure is intentionally one-shot, even after rollback.
    assert(CBMBank_IdentityConfigure(), "Identity DLL already configured or invalid host ABI")
    -- Publish the callable query before any actor can enter a replacement.
    EEex_ExposeToLua(query,"CBMBank_IdentityNativeQuery")
    local changed = {}
    EEex_DisableCodeProtection()
    local ok, why = pcall(function()
        for _, slot in ipairs(order) do
            local e = entries[slot]
            changed[#changed+1] = e -- Include an entry if the write itself fails.
            if e.far then
                writeFar(e, relativeJump(e.at, e.span, e.relay))
                EEex_DefineAssemblyLabel("CBMI::original_"..slot, e.original)
            else
                EEex_HookReplaceFunctionMaintainOriginal(e.at,e.span,"CBMI::original_"..slot,e.target)
            end
            -- A write EEex could not encode leaves the entry unchanged without an error.
            assert(M.JumpTarget(e.at, e.span) == e.target, "Native lifetime entry was not installed: " .. slot)
            e.replacement={}
            for i=0,e.span-1 do e.replacement[i]=EEex_ReadU8(e.at+i) end
        end
    end)
    local restored, restoreWhy = true
    if not ok then restored,restoreWhy=pcall(function()
        for _, e in ipairs(changed) do
            if e.far then writeFar(e, e.bytes)
            else for i=0,e.span-1 do EEex_WriteU8(e.at+i,e.bytes[i]) end end
        end
    end) end
    EEex_EnableCodeProtection()
    if not ok then
        CBMBank_IdentityNativeQuery=nil
        if not restored then error("Identity rollback failed; restart required: "..tostring(restoreWhy)) end
        error("Identity hook installation rolled back; restart required: " .. tostring(why))
    end
    M.installed = true
    actorDestroyEntry=entries.destruct
    _G.CBMBank_Identity = M
    return M
end

-- Component 430 starts after M_ files and needs this same destruction boundary.
-- Offer only our still-owned entry and configured typed handler. Scroll also
-- authenticates CBMI_Destruct against the loaded DLL and checks the original
-- EEex function body. It calls the handler, never relocates our current JMP.
function M.ActorDestroyChain(expectedEntry)
    local entry=actorDestroyEntry
    if not M.installed or not entry or expectedEntry~=entry.at then
        return nil,"Banking does not own the requested actor destruction entry"
    end
    if entry.span~=7 or entry.replacement[0]~=0xe9 or
        entry.replacement[5]~=0x90 or entry.replacement[6]~=0x90 then
        return nil,"Banking destruction entry has no reviewed chaining shape"
    end
    local original,replacement={},{}
    for i=0,entry.span-1 do
        if EEex_ReadU8(entry.at+i)~=entry.replacement[i] then
            return nil,"Actor destruction entry has a later owner"
        end
        original[#original+1]=string.format("%02x",entry.bytes[i])
        replacement[#replacement+1]=string.format("%02x",entry.replacement[i])
    end
    return {schema=1,entry=entry.at,handler=entry.target,
        original=table.concat(original),replacement=table.concat(replacement)}
end

function M.AddressText(sprite)
    local address=EEex_UDToPtr(sprite)
    assert(type(address)=="number" and address>0 and address<=9007199254740991 and address%1==0,
        "Native actor address is not exactly representable")
    -- Stock Lua 5.1/5.2's %x can truncate/reject a 64-bit address. Each half
    -- below is an exact unsigned 32-bit value on all three audited Lua hosts.
    local high=math.floor(address/4294967296)
    local low=address%4294967296
    return high==0 and string.format("%x",low) or string.format("%x%08x",high,low)
end
function M.Query(sprite)
    if not M.installed or sprite == nil then return nil,"Identity hooks unavailable" end
    local birth, reason, incarnation, owner, serializing, eligible, canMutate =
        CBMBank_IdentityNativeQuery(M.AddressText(sprite))
    if not birth then return nil,"Actor lifetime unobserved or wrong native thread" end
    return {birthReason=birth, reason=reason, incarnation=incarnation,
        ownerToken=owner ~= "" and owner or nil, serializing=serializing,
        eligible=eligible, canMutate=canMutate}
end
return M
