-- EEex adapter. Only the engine-owned XPBONUS strings are changed in memory.
-- The normal successful-action award and party distribution remain in charge.
CBM_UtilityXP_Runtime = { lastError = nil }
local R = CBM_UtilityXP_Runtime
local M = CBM_UtilityXP
local config = M.Validate(CBM_UtilityXP_Config)
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
    if width == 0 or height == 0 then return end -- startup / session transition
    assert(width >= 9 and height >= 3, "XPBONUS has an unsupported shape")
    local key = tostring(EEex_UDToPtr(array.m_pArray)) .. ":" .. width .. ":" .. height
    if R.lastKey == key and R.lastXP == xp then return end

    local rows = {
        lock = array:findRowLabel("PICK_LOCK"),
        trap = array:findRowLabel("DISARM_TRAP"),
        spells = array:findRowLabel("LEARN_SPELL"),
    }
    for name, row in pairs(rows) do
        assert(row >= 0 and row < height, "XPBONUS is missing row " .. name)
    end
    -- The native parser can allocate trailing unnamed columns (a 50-level
    -- XPBONUS was observed with m_nSizeX == 51). Preserve that padding, while
    -- retaining the allocated width as the row stride below.
    local levelCount = width
    while levelCount > 0 and array:getColumnLabel(levelCount - 1) == "" do
        levelCount = levelCount - 1
    end
    assert(levelCount >= 9, "XPBONUS has too few level columns")
    -- Reject interior gaps and custom/reordered headers before writing cells.
    for column = 0, levelCount - 1 do
        assert(tonumber(array:getColumnLabel(column)) == column + 1,
            "XPBONUS columns must be consecutive levels starting at 1")
    end
    local rewards = M.Rewards(config, xp)
    local function put(row, column, value)
        local cell = array.m_pArray:getReference(row * width + column)
        local text = tostring(value)
        if cell.m_pchData:get() ~= text then
            -- CString assignment owns allocation; never overwrite char buffers.
            cell:SetFromChars(text)
        end
    end
    for column = 0, levelCount - 1 do
        put(rows.lock, column, rewards.lock)
        put(rows.trap, column, rewards.trap)
        if column < 9 then put(rows.spells, column, rewards.spells[column + 1]) end
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
