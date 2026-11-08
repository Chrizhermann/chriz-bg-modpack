-- EEex adapter. Only the engine-owned XPBONUS strings are changed in memory.
-- The normal successful-action award and party distribution remain in charge.
CBM_UtilityXP_Runtime = { lastError = nil }
local R = CBM_UtilityXP_Runtime
local M = CBM_UtilityXP
local config = CBM_UtilityXP_Config
local xpLevels

local function retiredThreshold(className, level)
    if not xpLevels then xpLevels = EEex_Resource_Load2DA("XPLEVEL") end
    return tonumber(xpLevels:getAtLabels(tostring(level), className))
end

function R.Reset()
    R.lastKey = nil
    R.lastError = nil
    R.lastXP = nil
    R.lastRewards = nil
    xpLevels = nil
end

local function completeTable(array)
    local width, height = array.m_nSizeX, array.m_nSizeY
    local needs = false
    for _, label in ipairs({"PICK_LOCK", "DISARM_TRAP", "LEARN_SPELL"}) do
        local row = array:findRowLabel(label)
        if row < 0 or row >= height then needs = true end
    end
    local columns = {}
    for column = 0, width - 1 do
        local level = tonumber(array:getColumnLabel(column))
        if level and level >= 1 and level % 1 == 0 then columns[level] = true end
    end
    for level = 1, 9 do if not columns[level] then needs = true end end
    if needs then
        EEex_RunWithStackManager({
            {name="resref", struct="CResRef", constructor={args={"CBMXPB"}}}},
            function(manager) array:Load(manager:getUD("resref")) end)
    end
    return array.m_nSizeX, array.m_nSizeY
end

local function refresh()
    local game = EngineGlobals.g_pBaldurChitin.m_pObjectGame
    if game.m_nCharacters < 1 then return end
    -- Player1 is join slot zero, independent of selection and portrait ordering.
    local protagonist = EEex_GameObject_Get(game.m_characters:get(0))
    if not protagonist then return end
    local base = protagonist.m_baseStats
    local xp = M.LifetimeXP(base.m_xp, base.m_flags, protagonist.m_typeAI.m_Class,
        { base.m_level1, base.m_level2, base.m_level3 }, retiredThreshold)
    local array = game.m_ruleTables.m_tXPBonus
    local width, height = array.m_nSizeX, array.m_nSizeY
    width, height = completeTable(array)
    local key = tostring(EEex_UDToPtr(array.m_pArray)) .. ":" .. width .. ":" .. height

    local rows = {
        lock = array:findRowLabel("PICK_LOCK"),
        trap = array:findRowLabel("DISARM_TRAP"),
        spells = array:findRowLabel("LEARN_SPELL"),
    }
    local rewards = M.Rewards(config, xp)
    local function put(row, column, value)
        local cell = array.m_pArray:getReference(row * width + column)
        local text = tostring(value)
        if cell.m_pchData:get() ~= text then
            -- CString assignment owns allocation; never overwrite char buffers.
            cell:SetFromChars(text)
        end
    end
    for column = 0, width - 1 do
        local level = tonumber(array:getColumnLabel(column))
        if level and level >= 1 and level % 1 == 0 then
            put(rows.lock, column, rewards.lock)
            put(rows.trap, column, rewards.trap)
            if level <= 9 then put(rows.spells, column, rewards.spells[level]) end
        end
    end
    R.lastKey, R.lastXP, R.lastRewards = key, xp, rewards
end

function R.Refresh()
    local ok, err = pcall(refresh)
    if not ok then
        err = tostring(err)
        if err ~= R.lastError then
            print("[CBM utility XP] Update failed: " .. err)
        end
        R.lastError = err
    else
        R.lastError = nil
    end
    return false -- invisible, noninteractive menu label
end

-- This menu's enabled callback also runs while the inventory is paused.
-- It is intentionally idempotent: enabled can run several times per frame.
EEex_Menu_AddAfterMainFileLoadedListener(function()
    EEex_Menu_LoadFile("CBMUXP")
end)
local function pushMenu()
    R.Reset()
    Infinity_PushMenu("CBM_UtilityXP_Tick")
end
EEex_GameState_AddInitializedListener(pushMenu)
EEex_Menu_AddAfterMainFileReloadedListener(pushMenu)
EEex_GameState_AddDestroyedListener(R.Reset)
-- Refresh immediately when an action starts, in addition to UI refreshes.
EEex_Action_AddSpriteStartedActionListener(function() R.Refresh() end)
