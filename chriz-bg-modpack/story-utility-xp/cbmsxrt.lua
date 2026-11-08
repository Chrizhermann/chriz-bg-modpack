-- Only the in-memory XPBONUS reward strings are changed. Native success,
-- ability-level lookup and party XP sharing remain in charge.
CBM_StoryXP_Runtime = {lastError = nil, applied = false}
local R, M = CBM_StoryXP_Runtime, CBM_StoryXP
local baseline

function R.Reset()
    R.lastKey, R.lastPhase, R.lastError = nil, nil, nil
    baseline = nil
    -- Keep only this indication, not native pointers, across session resets:
    -- a reused rule table must not retain our rewards in an unsupported game.
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
    local campaign = string.upper(game.m_sCurrentCampaign.m_pchData:get())
    local phase, reason = M.Phase(campaign,
        EEex_GameState_GetGlobalInt("ENDOFBG1"), EEex_GameState_GetGlobalInt("INTOB"))
    if not phase and not R.applied then
        error(reason, 0)
    end
    local array = game.m_ruleTables.m_tXPBonus
    local width, height = array.m_nSizeX, array.m_nSizeY
    width, height = completeTable(array)
    local key = tostring(EEex_UDToPtr(array.m_pArray)) .. ":" .. width .. ":" .. height

    local rows = {lock = array:findRowLabel("PICK_LOCK"),
        trap = array:findRowLabel("DISARM_TRAP"),
        scribe = array:findRowLabel("LEARN_SPELL")}
    -- Fully prepare and validate before publishing any cells. On unsupported
    -- state, restore the installed resource rather than leaking a previous mode.
    local plan = {}
    if not phase and not baseline then baseline = EEex_Resource_Load2DA("XPBONUS") end
    local labels = {lock = "PICK_LOCK", trap = "DISARM_TRAP", scribe = "LEARN_SPELL"}
    for column = 0, width - 1 do
        local level = tonumber(array:getColumnLabel(column))
        if level and level >= 1 and level % 1 == 0 then
        local reward = phase and M.Rewards(phase, level) or nil
        for name, row in pairs(rows) do
            local value = reward and reward[name]
                or tonumber(baseline:getAtLabels(tostring(level), labels[name]))
            value = math.max(0, math.min(2147483647, math.floor(tonumber(value) or 0)))
            plan[#plan + 1] = {row * width + column, tostring(value)}
        end
        end
    end
    for _, entry in ipairs(plan) do
        local cell = array.m_pArray:getReference(entry[1])
        if cell.m_pchData:get() ~= entry[2] then cell:SetFromChars(entry[2]) end
    end
    R.lastKey, R.lastPhase, R.applied = key, phase, phase ~= nil
    if reason then error(reason, 0) end
end

function R.Refresh()
    local ok, err = pcall(refresh)
    if not ok then
        err = tostring(err)
        if err ~= R.lastError then print("[CBM story utility XP] " .. err) end
        R.lastError = err
    else
        R.lastError = nil
    end
    return false
end

EEex_Menu_AddAfterMainFileLoadedListener(function() EEex_Menu_LoadFile("CBMSXP") end)
local function pushMenu()
    R.Reset()
    Infinity_PushMenu("CBM_StoryXP_Tick")
end
EEex_GameState_AddInitializedListener(pushMenu)
EEex_Menu_AddAfterMainFileReloadedListener(pushMenu)
EEex_GameState_AddDestroyedListener(R.Reset)
EEex_Action_AddSpriteStartedActionListener(function() R.Refresh() end)
