-- UNINSTALLED RESEARCH PROBE. Loading this module does not install a hook.
-- No XP, effects, bank, saves, files or campaign data are changed by callbacks.
-- A separately authorized disposable native run must explicitly call install().
-- This is an observer of a real native boundary, not an XP-banking component.
local M = {records = {}, errors = {}, pending = {}, serial = 0,
    suppressDepth = 0, busy = false, suppressed = 0, reentrant = 0}
local ENTRY = "4C8BC14C8BCA8B492085C90F848700"
local ADD_BODY = "4183782401418B401C7522018270050000B80100000041C780180100000100000041C7801401000001000000C3"

local function integer(n)
    return type(n) == "number" and n == n and n == math.floor(n)
end

local function remember(list, value)
    if #list == 128 then table.remove(list, 1) end
    list[#list + 1] = value
end

local function signed32(n)
    if n >= 2147483648 then return n - 4294967296 end
    return n
end

local function kind(mode, timing, amount)
    if timing ~= 1 then return "op104:nonpermanent-unclassified" end
    if mode == 1 then return "op104:absolute-set" end
    if mode == 2 then return "op104:percentage" end
    if mode ~= 0 then return "op104:unknown-mode" end
    if amount < 0 then return "op104:add-loss" end
    if amount == 0 then return "op104:add-zero" end
    return "op104:add-positive"
end

-- This guard demonstrates recursion exclusion for a future owned release path.
-- It cannot identify unrelated external writers; callers must never use it to
-- suppress an ordinary earned award. The observer does not perform releases.
function M.with_internal_write(fn)
    M.suppressDepth = M.suppressDepth + 1
    local ok, result = pcall(fn)
    M.suppressDepth = M.suppressDepth - 1
    if not ok then error(result) end
    return result
end

function M.before(effect, sprite)
    if M.suppressDepth > 0 then M.suppressed = M.suppressed + 1; return 0 end
    if M.busy then M.reentrant = M.reentrant + 1; return 0 end
    M.busy = true
    local ok, result = pcall(function()
        local amount = signed32(effect.m_effectAmount)
        local e = {
            actor_id = sprite.m_id,
            opcode = effect.m_effectId,
            mode = effect.m_dWFlags,
            timing = effect.m_durationType,
            amount = amount,
            native_xp_before = sprite.m_baseStats.m_xp,
            source_kind = kind(effect.m_dWFlags, effect.m_durationType, amount),
            source_id = effect.m_sourceId,
            source_type = effect.m_sourceType,
            source_res = effect.m_sourceRes:get(),
            -- These fields do NOT distinguish kill/quest/utility/catch-up.
            origin = "not-preserved-by-this-native-boundary",
            planned_allowance = amount,
            applied_allowance = amount,
        }
        assert(e.opcode == 104, "unexpected opcode at op104 boundary")
        if M.planner and e.source_kind == "op104:add-positive" then
            -- Give the policy only a numeric/string snapshot, never live actor
            -- or effect pointers. Proposal is observed, never applied.
            local snapshot = {}
            for key, value in pairs(e) do snapshot[key] = value end
            local allowance = M.planner(snapshot)
            assert(integer(allowance) and allowance >= 0 and allowance <= amount,
                "invalid proposed allowance")
            e.planned_allowance = allowance
        end
        M.serial = M.serial + 1
        M.pending[M.serial] = e
        return M.serial
    end)
    M.busy = false
    if not ok then remember(M.errors, tostring(result)); return 0 end
    return result
end

function M.after(effect, sprite, nativeResult, token)
    local e = M.pending[token]
    if not e then return end
    M.pending[token] = nil
    local ok, err = pcall(function()
        e.native_result = nativeResult
        e.native_xp_after = sprite.m_baseStats.m_xp
        e.native_delta = e.native_xp_after - e.native_xp_before
        e.native_done = effect.m_done
        e.effect_amount_after = signed32(effect.m_effectAmount)
        if e.source_kind == "op104:add-positive" then
            e.expected_after_u32 = (e.native_xp_before + e.amount) % 4294967296
            e.native_matches_add = nativeResult == 1 and
                e.native_xp_after == e.expected_after_u32
        end
        remember(M.records, e)
    end)
    if not ok then remember(M.errors, tostring(err)) end
end

-- The shim preserves the two input pointers, the probe token and native EAX
-- in its own stack frame. The original leaf function remains authoritative.
-- GenLuaCall reuses this large shadow-space block; saved values at its bottom
-- are beyond its four-argument working region. All Lua errors resume native.
function M.assembly()
    local function arg(reg, usertype)
        return function(offset)
            return {"mov qword ptr ss:[rsp+#$(1)], " .. reg, {offset}, "#ENDL"}, usertype
        end
    end
    return EEex_FlattenTable({
        {[[
            #STACK_MOD(8)
            #MAKE_SHADOW_SPACE(128)
            mov qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-8)], rcx
            mov qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-16)], rdx
        ]]},
        EEex_GenLuaCall("CBMXPProbe_Before", {
            args = {arg("rcx", "CGameEffect"), arg("rdx", "CGameSprite")},
            returnType = EEex_LuaCallReturnType.Number,
            labelSuffix = "_cbmxp_before",
        }),
        {[[
            jmp cbmxp_before_done
            call_error_cbmxp_before:
            xor eax, eax
            cbmxp_before_done:
            mov qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-24)], rax
            mov rcx, qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-8)]
            mov rdx, qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-16)]
            call #L(CBMXPProbe::Original104)
            mov qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-32)], rax
            mov rcx, qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-8)]
            mov rdx, qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-16)]
            mov r8, rax
            mov r9, qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-24)]
        ]]},
        EEex_GenLuaCall("CBMXPProbe_After", {
            args = {arg("rcx", "CGameEffect"), arg("rdx", "CGameSprite"),
                arg("r8"), arg("r9")},
            labelSuffix = "_cbmxp_after",
        }),
        {[[
            call_error_cbmxp_after:
            mov rax, qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-32)]
            #DESTROY_SHADOW_SPACE
            ret
        ]]},
    })
end

function M.install(config)
    assert(not M.installed, "probe already installed")
    assert(config and config.observeOnly == true,
        "research observer requires explicit observeOnly=true")
    assert(config.engineVersion == "2.6.6.0" or config.engineVersion == "2.7.3.0",
        "executable version outside reviewed range")
    assert(EEex_Active == true, "EEex must be active")
    for _, name in ipairs({"EEex_TryLabel", "EEex_ReadU8", "EEex_Write8",
        "EEex_DisableCodeProtection", "EEex_EnableCodeProtection", "EEex_FlattenTable",
        "EEex_HookShimFunctionMaintainOriginal", "EEex_GenLuaCall"}) do
        assert(type(_G[name]) == "function", "missing native capability: " .. name)
    end
    assert(EEex_LuaCallReturnType and EEex_LuaCallReturnType.Number,
        "missing native Lua numeric return capability")
    local address = EEex_TryLabel("CBMXPProbe::Opcode104Apply")
    assert(type(address) == "number" and address > 0,
        "new loader label absent; stock EEex has no XP callback")
    local function verify(offset, hex)
        for i = 1, #hex, 2 do
            assert(EEex_ReadU8(address + offset + (i - 1) / 2) ==
                tonumber(hex:sub(i, i + 1), 16), "native op104 code mismatch")
        end
    end
    verify(0, ENTRY)
    verify(0x98, ADD_BODY)
    assert(_G.CBMXPProbe_Before == nil and _G.CBMXPProbe_After == nil,
        "probe callback names already owned")
    local original = {}
    for i = 0, 8 do original[i] = EEex_ReadU8(address + i) end
    M.planner = config.planner
    _G.CBMXPProbe_Before, _G.CBMXPProbe_After = M.before, M.after
    EEex_DisableCodeProtection()
    local ok, err = pcall(function()
        EEex_HookShimFunctionMaintainOriginal(address, 9,
            "CBMXPProbe::Original104", M.assembly())
    end)
    if not ok then
        for i = 0, 8 do EEex_Write8(address + i, original[i]) end
        _G.CBMXPProbe_Before, _G.CBMXPProbe_After = nil, nil
    end
    EEex_EnableCodeProtection()
    if not ok then error(err) end
    M.installed = true
    return true
end

return M
