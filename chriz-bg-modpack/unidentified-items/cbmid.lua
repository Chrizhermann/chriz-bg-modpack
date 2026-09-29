-- Generic artwork for unidentified item *instances*. Never edits an ITM, TLK,
-- saved item, or the CItem itself. See docs/unidentified-items.md for evidence.
CBMID = {}
local M = CBMID
local fields = {"inventory", "ground", "picture"}
local expected = {
    Inventory = {"rdi", 58, 0}, Ground = {"rdi", 68, 8},
    LuaIcon = {"rbx", 58, 0}, LuaPicture = {"rbx", 88, 16},
}

local function checkArt(art)
    assert(type(art) == "table", "Missing generic artwork")
    for _, key in ipairs(fields) do
        local value = art[key]
        assert(type(value) == "string" and #value <= 8
            and (value == "" or value:match("^[%w_#%-]+$")), "Invalid BAM reference: " .. key)
        if key == "inventory" then assert(value ~= "", "Missing inventory artwork") end
    end
end

function M.validate(config)
    assert(type(config) == "table" and config.schema == 1, "Unsupported artwork configuration")
    checkArt(config.fallback)
    assert(type(config.types) == "table" and type(config.hooks) == "table", "Incomplete configuration")
    local maxType = 0
    for itemType, art in pairs(config.types) do
        assert(type(itemType) == "number" and itemType % 1 == 0
            and itemType >= 0 and itemType <= 65535, "Invalid item type")
        checkArt(art)
        maxType = math.max(maxType, itemType)
    end
    assert(#config.hooks == 4, "All four display hooks are required")
    local seen = {}
    for _, hook in ipairs(config.hooks) do
        local spec = expected[hook.name]
        assert(spec and not seen[hook.name], "Invalid or duplicate display hook")
        seen[hook.name] = true
        assert(hook.itemRegister == spec[1] and hook.fieldOffset == spec[2]
            and hook.mapOffset == spec[3], "Unexpected display hook layout")
        assert(type(hook.pattern) == "string" and hook.pattern:match("^%x+$")
            and #hook.pattern % 2 == 0 and #hook.pattern >= 20
            and hook.callOffset == #hook.pattern / 2, "Invalid display hook signature")
    end
    return maxType
end

-- This small stub runs without Lua callbacks or resource lookups during paint.
-- R8 is the input CResRef pointer for the native copy call. Every other
-- register and the flags are preserved, including on the identified path.
function M.assembly(hook, buffer, maxType)
    return string.format([[
        pushfq
        push rax
        test byte ptr [%s+0x24], 1
        jnz cbmid_keep
        movzx eax, word ptr [r8-%d]
        cmp eax, %d
        ja cbmid_fallback
        inc eax
        jmp cbmid_selected
    cbmid_fallback:
        xor eax, eax
    cbmid_selected:
        shl rax, 5
        mov r8, %.0f
        add r8, rax
    cbmid_keep:
        pop rax
        popfq
    ]], hook.itemRegister, hook.fieldOffset - 0x1C, maxType, buffer + hook.mapOffset)
end

function M.install(config)
    -- M_ scripts may be evaluated again when the UI is reloaded.
    if CBMID_State and CBMID_State.installed then return false end
    assert(EEex_Active, "Generic unidentified artwork requires EEex / InfinityLoader")
    for _, name in ipairs({"EEex_TryLabel", "EEex_ReadU8", "EEex_Read32", "EEex_Write8",
        "EEex_Malloc", "EEex_Free", "EEex_WriteLString", "EEex_HookBeforeCallWithLabels",
        "EEex_DisableCodeProtection", "EEex_EnableCodeProtection"}) do
        assert(type(_G[name]) == "function", "Required EEex API is missing: " .. name)
    end
    assert(EEex_HookIntegrityWatchdogRegister and EEex_HookIntegrityWatchdogRegister.R8,
        "Required EEex hook support is missing")
    local maxType = M.validate(config)
    local hooks, target, addresses = {}, nil, {}
    -- Check *all* hook sites before allocating or modifying native code. This
    -- rejects stale loader addresses and another mod already owning a site.
    for _, hook in ipairs(config.hooks) do
        local address = EEex_TryLabel("CBMID::" .. hook.name)
        assert(type(address) == "number" and address > hook.callOffset
            and not addresses[address], "Missing or duplicate display address: " .. hook.name)
        addresses[address] = true
        for i = 1, #hook.pattern, 2 do
            assert(EEex_ReadU8(address - hook.callOffset + (i - 1) / 2)
                == tonumber(hook.pattern:sub(i, i + 1), 16),
                "Unsupported or modified display code: " .. hook.name)
        end
        assert(EEex_ReadU8(address) == 0xE8, "Display call already changed: " .. hook.name)
        local callTarget = address + 5 + EEex_Read32(address + 1)
        assert(not target or target == callTarget, "Display copy targets do not match")
        target = callTarget
        local saved = {}
        for i = 0, 4 do saved[i + 1] = EEex_ReadU8(address + i) end
        hooks[#hooks + 1] = {definition = hook, address = address, saved = saved}
    end
    -- Entry 0 is the fallback; type N lives at entry N+1. Unknown/custom
    -- types are bounded before indexing and never reveal the original icon.
    local buffer = EEex_Malloc((maxType + 2) * 32)
    assert(type(buffer) == "number" and buffer > 0, "Could not allocate generic artwork")
    local ok, err = pcall(function()
        for itemType = -1, maxType do
            local art = config.types[itemType] or config.fallback
            for index, key in ipairs(fields) do
                local padded = art[key] .. string.rep("\0", 8 - #art[key])
                EEex_WriteLString(buffer + (itemType + 1) * 32 + (index - 1) * 8, padded, 8)
            end
        end
    end)
    if not ok then EEex_Free(buffer); error(err) end

    EEex_DisableCodeProtection()
    ok, err = pcall(function()
        for _, hook in ipairs(hooks) do
            EEex_HookBeforeCallWithLabels(hook.address, {
                {"hook_integrity_watchdog_ignore_registers", {EEex_HookIntegrityWatchdogRegister.R8}},
            }, {M.assembly(hook.definition, buffer, maxType)})
        end
    end)
    if not ok then
        -- Startup is synchronous. Restore all original call bytes before any
        -- game screen can execute a partially installed set of hooks.
        for _, hook in ipairs(hooks) do
            for i = 1, 5 do EEex_Write8(hook.address + i - 1, hook.saved[i]) end
        end
    end
    EEex_EnableCodeProtection()
    if not ok then EEex_Free(buffer); error(err) end
    -- Keep this process-owned buffer for the hooks' lifetime; no game object
    -- pointers or campaign-specific data are retained across loads.
    CBMID_State = {installed = true, buffer = buffer}
    return true
end
