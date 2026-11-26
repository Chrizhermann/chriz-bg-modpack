-- Chriz BG1 Early-Party XP Boost 0.1.0. Windows x64, engine 2.6.6.0 / 2.7.3.0, EEex 1.2.0 / 1.3.1.
-- Grants a +70% party XP pool bonus per additional living companion in BG1 up to 16,000 total XP
-- per character (including retired dual-class XP for both protagonist and companions).
-- Only party-divided XP routed through CInfGame::AddPartyXP is affected.

local CAP_XP = 16000
local BONUS_NUM_PER_EXTRA = 7
local BONUS_DEN = 10
local MAX_SLOTS = 16
local MAX_INT32 = 2147483647
local STATE_DEAD_BIT = 0x800

CZBG1EarlyPartyXP = CZBG1EarlyPartyXP or {status = 'not initialized'}
local state = CZBG1EarlyPartyXP
if state.queued then return end
state.queued = true

local function log(message)
    state.status = message
    if state.logged then return end
    state.logged = true
    message = tostring(message):gsub('[\r\n]+', ' ')
    if io and io.open then
        local f = io.open('chriz_bg1_early_party_xp.log', 'a')
        if f then f:write('Chriz BG1 Early-Party XP: ' .. message .. '\n'); f:close(); return end
    end
    print('Chriz BG1 Early-Party XP: ' .. message) -- engine log only; never a game notice/dialog
end

local function bytes(hex)
    return (hex:gsub('%x%x', function(pair) return string.char(tonumber(pair, 16)) end))
end

local function signed32(v)
    v = v % 0x100000000
    return v >= 0x80000000 and v - 0x100000000 or v
end

local function writeU32(address, value)
    value = math.floor(tonumber(value) or 0) % 0x100000000
    for i = 0, 3 do
        EEex_WriteU8(address + i, math.floor(value / (256 ^ i)) % 256)
    end
end

-- CRE class slots follow CLASS.IDS name order, including both dual directions.
-- Original-class flags identify duals; ordinary multiclass XP is already TOTAL.
local DUAL_SLOTS = {
    [7]  = { 'FIGHTER', 'MAGE' },
    [8]  = { 'FIGHTER', 'CLERIC' },
    [9]  = { 'FIGHTER', 'THIEF' },
    [13] = { 'MAGE', 'THIEF' },
    [14] = { 'CLERIC', 'MAGE' },
    [15] = { 'CLERIC', 'THIEF' },
    [16] = { 'FIGHTER', 'DRUID' },
    [18] = { 'CLERIC', 'RANGER' },
}
local ORIGINAL_CLASS_FLAGS = {
    { 8,   'FIGHTER' },
    { 16,  'MAGE' },
    { 32,  'CLERIC' },
    { 64,  'THIEF' },
    { 128, 'DRUID' },
    { 256, 'RANGER' },
}
local FALLBACK_XPLEVEL = {
    FIGHTER = { 0, 2000, 4000, 8000, 16000, 32000, 64000, 125000, 250000, 500000 },
    MAGE    = { 0, 2500, 5000, 10000, 20000, 40000, 60000, 90000, 135000, 250000 },
    CLERIC  = { 0, 1500, 3000, 6000, 13000, 27500, 55000, 110000, 225000, 450000 },
    THIEF   = { 0, 1250, 2500, 5000, 10000, 20000, 40000, 70000, 110000, 160000 },
    DRUID   = { 0, 2000, 4000, 7500, 12500, 20000, 35000, 60000, 90000, 125000 },
    RANGER  = { 0, 2250, 4500, 9000, 18000, 36000, 75000, 150000, 300000, 600000 },
}

local xpLevelsCache = nil

local function lookupThreshold(className, level)
    level = math.max(1, math.floor(tonumber(level) or 1))
    if not xpLevelsCache then
        local ok, table2da = pcall(EEex_Resource_Load2DA, 'XPLEVEL')
        if ok and table2da then xpLevelsCache = table2da end
    end
    if xpLevelsCache then
        local ok, raw = pcall(function()
            return tonumber(xpLevelsCache:getAtLabels(tostring(level), className))
        end)
        if ok and type(raw) == 'number' and raw == raw and raw >= 0 then
            return math.floor(raw)
        end
    end
    local row = FALLBACK_XPLEVEL[className]
    if not row then return 0 end
    return row[math.min(level, #row)]
end

local function computeRetiredDualXP(currentXP, flags, classID, level1, level2, bankOldTotal, thresholdFn)
    local _ = currentXP
    local original
    local numFlags = math.max(0, math.floor(tonumber(flags) or 0))
    for _, flag in ipairs(ORIGINAL_CLASS_FLAGS) do
        if math.floor(numFlags / flag[1]) % 2 == 1 then
            original = flag[2]
            break
        end
    end
    local retired = 0
    if original then
        local slots = DUAL_SLOTS[classID]
        if slots then
            for index, className in ipairs(slots) do
                if className == original then
                    local lvl = index == 1 and level1 or level2
                    local resolved = thresholdFn(className, math.max(1, math.floor(tonumber(lvl) or 1)))
                    if type(resolved) == 'number' and resolved == resolved and resolved > 0 then
                        retired = math.floor(resolved)
                    end
                    break
                end
            end
        end
    end
    if type(bankOldTotal) == 'number' and bankOldTotal == bankOldTotal and bankOldTotal > retired then
        retired = math.floor(bankOldTotal)
    end
    return retired
end

local function computeTotalXP(activeXP, flags, classID, level1, level2, bankOldTotal, thresholdFn)
    local cur = math.max(0, math.floor(tonumber(activeXP) or 0))
    local retired = computeRetiredDualXP(cur, flags, classID, level1, level2, bankOldTotal, thresholdFn)
    return cur + retired
end

local function isBG1Context(buildKind, campaign, endBG1, inToB, chapter, areaResref)
    local camp = type(campaign) == 'string' and string.upper(campaign) or ''
    if endBG1 ~= 0 or inToB ~= 0 then return false end
    if type(chapter) ~= 'number' or chapter < 0 or chapter > 7 then return false end
    local area = type(areaResref) == 'string' and string.upper(areaResref) or ''
    if buildKind == 'bgee' then
        if camp ~= '' and camp ~= 'BG1' then return false end
        if area:sub(1, 2) == 'BD' or area:sub(1, 4) == 'OH93' or area:sub(1, 4) == 'TU00' then
            return false
        end
        return true
    end
    return camp == 'BG1'
end

local function computePartyPlan(rawPartyXP, members)
    rawPartyXP = math.floor(tonumber(rawPartyXP) or 0)
    local count = #members
    if rawPartyXP <= 0 or count <= 1 or count > MAX_SLOTS then
        return false, 0, {}
    end
    local baseQ = math.floor(rawPartyXP / count)
    local baseR = rawPartyXP % count
    local poolNumerator = BONUS_DEN + BONUS_NUM_PER_EXTRA * (count - 1)
    local boostedPool = math.floor((rawPartyXP * poolNumerator + 5) / BONUS_DEN)
    local boostQ = math.floor(boostedPool / count)
    local boostR = boostedPool % count

    local anyChanged = false
    local totalGained = 0
    local sharesBySlot = {}
    for k = 1, count do
        local m = members[k]
        local baseShare = baseQ + (k <= baseR and 1 or 0)
        local boostedShare = boostQ + (k <= boostR and 1 or 0)
        local room = math.max(0, CAP_XP - math.max(0, math.floor(tonumber(m.totalXP) or 0)))
        local finalShare = math.max(baseShare, math.min(boostedShare, room))
        finalShare = math.min(MAX_INT32, finalShare)
        if finalShare > baseShare then anyChanged = true end
        sharesBySlot[m.slot] = finalShare
        totalGained = totalGained + finalShare
    end
    if not anyChanged then
        return false, 0, {}
    end
    return true, math.min(MAX_INT32, totalGained), sharesBySlot
end

local function spriteClassID(sprite)
    if sprite.m_startTypeAI and sprite.m_startTypeAI.m_Class ~= nil then
        return sprite.m_startTypeAI.m_Class
    end
    if sprite.m_typeAI and sprite.m_typeAI.m_Class ~= nil then
        return sprite.m_typeAI.m_Class
    end
    return 0
end

local function spriteBankOldTotal(sprite)
    local ok, aux = pcall(EEex_GetUDAux, sprite)
    if ok and type(aux) == 'table' and type(aux.CBMBank) == 'table'
        and type(aux.CBMBank.old) == 'table' and type(aux.CBMBank.old.total) == 'number' then
        return aux.CBMBank.old.total
    end
    return nil
end

local function currentAreaResref()
    local okArea, area = pcall(EEex_Area_GetVisible)
    if okArea and area and area.m_resref then
        local okRes, res = pcall(function() return area.m_resref:get() end)
        if okRes and type(res) == 'string' then return res end
    end
    return ''
end

local function planPartyXP(rawPartyXP)
    local buf = state.planBuffer
    if not buf then return 0 end
    writeU32(buf, 0)
    rawPartyXP = math.floor(tonumber(rawPartyXP) or 0)
    if rawPartyXP <= 0 then return 0 end

    local game = EngineGlobals and EngineGlobals.g_pBaldurChitin and EngineGlobals.g_pBaldurChitin.m_pObjectGame
    if not game then return 0 end
    local campaign = ''
    if game.m_sCurrentCampaign and game.m_sCurrentCampaign.m_pchData then
        local ok, s = pcall(function() return game.m_sCurrentCampaign.m_pchData:get() end)
        if ok and type(s) == 'string' then campaign = s end
    end
    local endBG1 = tonumber(EEex_GameState_GetGlobalInt('ENDOFBG1')) or 0
    local inToB = tonumber(EEex_GameState_GetGlobalInt('INTOB')) or 0
    local chapter = tonumber(EEex_GameState_GetGlobalInt('CHAPTER')) or 0
    local areaRes = state.buildKind == 'bgee' and currentAreaResref() or ''
    if not isBG1Context(state.buildKind, campaign, endBG1, inToB, chapter, areaRes) then
        return 0
    end

    local numChars = math.floor(tonumber(EEex_Sprite_GetNumCharacters()) or 0)
    if numChars <= 1 or numChars > MAX_SLOTS then return 0 end

    local members = {}
    for slot = 0, numChars - 1 do
        local sprite = EEex_Sprite_GetInPortrait(slot)
        if sprite ~= nil then
            local gstate = math.floor(tonumber(EEex_Sprite_GetState(sprite)) or 0)
            if math.floor(gstate / STATE_DEAD_BIT) % 2 == 0 then
                local base = sprite.m_baseStats
                local totalXP = computeTotalXP(
                    base and base.m_xp or 0,
                    base and base.m_flags or 0,
                    spriteClassID(sprite),
                    base and base.m_level1 or 1,
                    base and base.m_level2 or 1,
                    spriteBankOldTotal(sprite),
                    lookupThreshold
                )
                members[#members + 1] = { slot = slot, totalXP = totalXP }
            end
        end
    end

    local active, totalGained, sharesBySlot = computePartyPlan(rawPartyXP, members)
    if not active then return 0 end

    for slot = 0, MAX_SLOTS - 1 do
        writeU32(buf + 4 + slot * 4, sharesBySlot[slot] or 0)
    end
    writeU32(buf, 1)
    return totalGained
end

state._test = {
    CAP_XP = CAP_XP,
    BONUS_NUM_PER_EXTRA = BONUS_NUM_PER_EXTRA,
    BONUS_DEN = BONUS_DEN,
    lookupThreshold = lookupThreshold,
    computeRetiredDualXP = computeRetiredDualXP,
    computeTotalXP = computeTotalXP,
    isBG1Context = isBG1Context,
    computePartyPlan = computePartyPlan,
    planPartyXP = planPartyXP,
    resetCache = function() xpLevelsCache = nil end,
}

local function install()
    -- ReadLString stops at NUL; bounded chunks plus explicit NULs preserve binary
    -- data without LuaJIT/ffi. Small reads also bound the binding's stack allocation.
    local function read(address, n)
        local parts = {}
        while n > 0 do
            local limit = math.min(n, 1024)
            local part = EEex_ReadLString(address, limit)
            parts[#parts + 1] = part
            address = address + #part
            n = n - #part
            if #part < limit then
                parts[#parts + 1] = '\0'
                address = address + 1
                n = n - 1
            end
        end
        return table.concat(parts)
    end

    local base = EEex_GetImageBase()
    assert(read(base, 2) == 'MZ', 'unsupported executable header')
    local peOffset = EEex_Read32(base + 0x3C)
    assert(peOffset >= 0x40 and peOffset <= 0x800, 'invalid PE header offset')
    local pe = base + peOffset
    assert(read(pe, 4) == 'PE\0\0' and EEex_Read16(pe + 4) % 0x10000 == 0x8664, 'unsupported executable format')
    local count = EEex_Read16(pe + 6)
    local optsize = EEex_Read16(pe + 20)
    assert(count > 0 and count <= 96 and optsize >= 112 and peOffset + 24 + optsize + count * 40 <= 0x1000,
        'invalid executable sections')
    assert(EEex_Read16(pe + 24) == 0x20B, 'unsupported optional header')
    local imageSize = EEex_Read32(pe + 24 + 56)

    -- Supported Windows x64 BG builds only (IWD:EE is intentionally rejected).
    local builds = {
        [0x6A18D6DC] = { size = 0x3524000, name = 'BG:EE 2.7.3.0', kind = 'bgee' },
        [0x6A18D73D] = { size = 0x3532000, name = 'BG2:EE / EET 2.7.3.0', kind = 'bg2ee' },
        [0x609437B3] = { size = 0x3530000, name = 'BG2:EE / EET 2.6.6.0', kind = 'bg2ee' },
    }
    local build = builds[EEex_Read32(pe + 8)]
    assert(build and build.size == imageSize, 'unsupported engine build')

    -- Unique 32-byte RIP-free core inside CInfGame::AddPartyXP (fn + 0x54).
    local pattern = bytes('8BCB0FAFC8B81F85EB51F7E9C1FA058BC2C1E81F03D003DA440FB79630660000')
    local hits = {}
    for i = 0, count - 1 do
        local section = pe + 24 + optsize + i * 40
        local size = EEex_Read32(section + 8)
        local rva = EEex_Read32(section + 12)
        if math.floor(EEex_Read32(section + 36) / 0x20000000) % 2 == 1 then
            assert(rva > 0 and size > 0 and rva + size <= imageSize, 'invalid executable section bounds')
            local text = read(base + rva, size)
            local from = 1
            while true do
                local at = text:find(pattern, from, true)
                if not at then break end
                hits[#hits + 1] = { address = base + rva + at - 1, first = base + rva, last = base + rva + size }
                from = at + 1
            end
        end
    end
    assert(#hits == 1, 'unsupported or modified engine: expected one AddPartyXP pattern, found ' .. #hits)
    local hit = hits[1]
    local fn = hit.address - 0x54
    assert(fn >= hit.first and fn + 0x308 <= hit.last, 'invalid function bounds')

    local function check(offset, hex)
        local expected = bytes(hex)
        assert(read(fn + offset, #expected) == expected, 'engine layout mismatch at ' .. string.format('%X', offset))
    end
    check(0x00, '405355564154415641574881EC8800')
    check(0x148, 'BA0200000066894C244C448BC3488BCE44897C2444E8')
    check(0x20D, '6685ED7E0D418D470166FFCD89442444EB0544897C24444C8D4C243048C7442430FFFFFFFF41B8')

    local planBuf = EEex_Malloc(4 + MAX_SLOTS * 4)
    assert(type(planBuf) == 'number' and planBuf > 0, 'plan buffer allocation failed')
    for slot = 0, MAX_SLOTS do
        writeU32(planBuf + slot * 4, 0)
    end

    state.buildKind = build.kind
    state.planBuffer = planBuf
    CBM_BG1EarlyPartyXP_Plan = function(rawPartyXP)
        local ok, res = pcall(planPartyXP, rawPartyXP)
        if ok and type(res) == 'number' and res > 0 then
            return math.min(MAX_INT32, math.floor(res))
        end
        if state.planBuffer then writeU32(state.planBuffer, 0) end
        return 0
    end

    local function target(value)
        return type(value) == 'number' and string.format('%.0f', value) or value
    end

    local planCallee = EEex_JITNear(EEex_FlattenTable({
        {'#STACK_MOD(8) #ENDL'},
        EEex_GenLuaCall('CBM_BG1EarlyPartyXP_Plan', {
            args = {
                function(offset) return {'mov qword ptr ss:[rsp+#$(1)], rcx #ENDL', {offset}} end,
            },
            returnType = EEex_LuaCallReturnType.Number,
            labelSuffix = '_czxpbg',
        }),
        {'jmp done_czxpbg #ENDL call_error_czxpbg: #ENDL xor eax, eax #ENDL done_czxpbg: #ENDL #DESTROY_SHADOW_SPACE #ENDL ret #ENDL'},
    }))
    assert(type(planCallee) == 'number' and planCallee > 0, 'plan callee allocation failed')

    local plans = {
        {
            at = fn + 0x152,
            size = 6,
            asm = string.format([[
                mov rax, %s
                mov dword ptr [rax], 0
                mov r8d, ebx
                test ebx, ebx
                jle czxpbg_skip
                movsxd rcx, ebx
                call %s
                test eax, eax
                jle czxpbg_restore
                mov r8d, eax
                jmp czxpbg_skip
            czxpbg_restore:
                mov r8d, ebx
            czxpbg_skip:
                mov edx, 2
                mov rcx, rsi
                jmp %s
            ]], target(planBuf), target(planCallee), target(fn + 0x158)),
        },
        {
            at = fn + 0x224,
            size = 5,
            asm = string.format([[
                mov rax, %s
                cmp dword ptr [rax], 1
                jne czxpbg_done_slot
                cmp bx, 16
                jae czxpbg_done_slot
                movzx ecx, bx
                mov ecx, dword ptr [rax + rcx*4 + 4]
                mov dword ptr [rsp+0x44], ecx
            czxpbg_done_slot:
                lea r9, [rsp+0x30]
                jmp %s
            ]], target(planBuf), target(fn + 0x229)),
        },
    }

    for _, p in ipairs(plans) do
        p.original = read(p.at, p.size)
        p.trampoline = EEex_JITNear({p.asm})
    end

    EEex_DisableCodeProtection()
    local ok, err = pcall(function()
        for _, p in ipairs(plans) do
            assert(read(p.at, p.size) == p.original, 'hook site changed during installation')
            if p.size == 6 then
                EEex_JITAt(p.at, {'jmp short ', p.trampoline, ' #ENDL nop #ENDL'})
            else
                EEex_JITAt(p.at, {'jmp short ', p.trampoline, ' #ENDL'})
            end
            local disp = signed32(EEex_Read32(p.at + 1))
            assert(EEex_Read8(p.at) % 256 == 0xE9 and p.at + 5 + disp == p.trampoline,
                'hook write verification failed')
            if p.size == 6 then
                assert(EEex_Read8(p.at + 5) % 256 == 0x90, 'hook nop verification failed')
            end
        end
    end)
    if not ok then
        for _, p in ipairs(plans) do
            for i = 1, #p.original do
                EEex_WriteU8(p.at + i - 1, p.original:byte(i))
            end
        end
    end
    EEex_EnableCodeProtection()
    assert(ok, err)

    EEex_GameState_AddDestroyedListener(function()
        xpLevelsCache = nil
        if state.planBuffer then writeU32(state.planBuffer, 0) end
    end)

    state.planCallee = planCallee
    state.hookSite1 = fn + 0x152
    state.hookSite2 = fn + 0x224
    state.installed = true
    log('active; ' .. build.name .. '; +70% BG1 party XP pool per extra living member up to 16,000 total XP (dual-class aware)')
end

if not EEex_Active then
    log('inactive: EEex is required')
    return
end
for _, name in ipairs({
    'EEex_GameState_AddInitializedListener', 'EEex_GameState_AddDestroyedListener',
    'EEex_GetImageBase', 'EEex_ReadLString',
    'EEex_Read8', 'EEex_Read16', 'EEex_Read32', 'EEex_WriteU8',
    'EEex_JITNear', 'EEex_JITAt', 'EEex_Malloc',
    'EEex_DisableCodeProtection', 'EEex_EnableCodeProtection',
    'EEex_GenLuaCall', 'EEex_FlattenTable',
    'EEex_GameState_GetGlobalInt', 'EEex_Area_GetVisible',
    'EEex_Sprite_GetNumCharacters', 'EEex_Sprite_GetInPortrait', 'EEex_Sprite_GetState',
    'EEex_Resource_Load2DA', 'EEex_GetUDAux',
}) do
    if type(_G[name]) ~= 'function' then
        log('inactive: missing EEex API ' .. name)
        return
    end
end
if type(_G.EEex_LuaCallReturnType) ~= 'table' or type(EEex_LuaCallReturnType.Number) ~= 'number' then
    log('inactive: missing EEex API EEex_LuaCallReturnType')
    return
end
EEex_GameState_AddInitializedListener(function()
    if state.attempted then return end
    state.attempted = true
    local ok, err = pcall(install)
    if not ok then log('inactive; native behavior retained: ' .. tostring(err)) end
end)
