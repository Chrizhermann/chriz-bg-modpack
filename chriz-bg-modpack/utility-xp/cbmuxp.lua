-- Pure calculations: no engine access, file IO, character or save mutations.
CBM_UtilityXP = {}
local M = CBM_UtilityXP
local keys = { "lock", "trap", "scribe" }
local MAX_XP = 2147483647

local function numberInRange(value, maximum)
    return type(value) == "number" and value == value
        and value >= 0 and value <= maximum
end

local function roundReward(config, value)
    local step = config.roundingStep == nil and 1 or config.roundingStep
    if config.roundingMode == "up" then
        return math.min(MAX_XP, math.ceil(value / step) * step)
    end
    return math.min(MAX_XP, math.floor(value / step + 0.5) * step)
end

local defaults = {
    -- XP is the protagonist's current total XP plus the minimum XP required
    -- for a retired dual-class level. Discarded excess XP cannot be recovered.
    -- Rewards interpolate linearly between milestones and stop at the last one.
    -- scribe is multiplied by SPELL level (1-9), never by caster level.
    anchors = {
        -- XP       lock   trap   scribe
        { xp =       0, lock =   25, trap =   10, scribe =   10 },
        { xp =   10000, lock =   25, trap =   10, scribe =   10 },
        { xp =   40000, lock =   50, trap =  100, scribe =   50 },
        { xp =   89000, lock =  150, trap =  500, scribe =  250 },
        { xp =  161000, lock =  400, trap = 1750, scribe =  500 },
        { xp =  440000, lock =  950, trap = 2750, scribe = 1000 },
        { xp = 1320000, lock = 1550, trap = 3250, scribe = 1000 },
    },
    lockMultiplier = 1.0,
    trapMultiplier = 1.0,
    scribeMultiplier = 1.0,
    -- Round each final party award up to a multiple of 10 (732.08 -> 740).
    -- For original whole-XP rounding, use step 1 and mode "nearest".
    -- Scribing rounds AFTER multiplication by spell level.
    roundingStep = 10,
    roundingMode = "up", -- "up" or "nearest"
}

-- Editable configuration values are decoded independently. Missing values use
-- the authored defaults, and arithmetic stays within the engine integer range.
function M.Normalize(config)
    config = type(config) == "table" and config or {}
    local result = {anchors = {}}
    for _, key in ipairs(keys) do
        local value = tonumber(config[key .. "Multiplier"])
        result[key .. "Multiplier"] = numberInRange(value, MAX_XP) and value or 1
    end
    local step = config.roundingStep == nil and 1 or tonumber(config.roundingStep)
    result.roundingStep = numberInRange(step, MAX_XP) and step >= 1 and math.floor(step) or 10
    result.roundingMode = (config.roundingMode == nil or config.roundingMode == "nearest") and "nearest" or "up"
    local source = type(config.anchors) == "table" and config.anchors or defaults.anchors
    for i = 1, math.max(2, #source) do
        local fallback = defaults.anchors[math.min(i, #defaults.anchors)]
        local entry = type(source[i]) == "table" and source[i] or fallback
        local anchor = {}
        for _, key in ipairs({"xp", "lock", "trap", "scribe"}) do
            local value = tonumber(entry[key])
            anchor[key] = numberInRange(value, MAX_XP) and value or fallback[key]
        end
        anchor.xp = math.floor(anchor.xp)
        result.anchors[#result.anchors + 1] = anchor
    end
    table.sort(result.anchors, function(a, b) return a.xp < b.xp end)
    result.anchors[1].xp = 0
    return result
end

function M.Rewards(config, xp)
    config = M.Normalize(config)
    xp = math.max(0, math.min(MAX_XP, tonumber(xp) or 0))
    local anchors = config.anchors
    local low, high = anchors[#anchors], anchors[#anchors]
    for i = 2, #anchors do
        if xp < anchors[i].xp then
            low, high = anchors[i - 1], anchors[i]
            break
        end
    end
    local fraction = low == high and 0 or (xp - low.xp) / math.max(1, high.xp - low.xp)
    local rewards = { spells = {} }
    for _, key in ipairs(keys) do
        local value = (low[key] + (high[key] - low[key]) * fraction)
            * config[key .. "Multiplier"]
        if key == "scribe" then
            for level = 1, 9 do
                rewards.spells[level] = roundReward(config, value * level)
            end
        else
            rewards[key] = roundReward(config, value)
        end
    end
    return rewards
end

-- CRE class slots follow CLASS.IDS name order, including both dual directions.
-- Original-class flags identify duals; ordinary multiclass XP is already TOTAL.
local classes = {
    [7] = { "FIGHTER", "MAGE" },
    [8] = { "FIGHTER", "CLERIC" },
    [9] = { "FIGHTER", "THIEF" },
    [10] = { "FIGHTER", "MAGE", "THIEF" },
    [13] = { "MAGE", "THIEF" },
    [14] = { "CLERIC", "MAGE" },
    [15] = { "CLERIC", "THIEF" },
    [16] = { "FIGHTER", "DRUID" },
    [17] = { "FIGHTER", "MAGE", "CLERIC" },
    [18] = { "CLERIC", "RANGER" },
}
local originalFlags = {
    { 8, "FIGHTER" }, { 16, "MAGE" }, { 32, "CLERIC" },
    { 64, "THIEF" }, { 128, "DRUID" }, { 256, "RANGER" },
}

function M.LifetimeXP(currentXP, flags, classID, levels, threshold)
    currentXP = math.max(0, math.min(MAX_XP, tonumber(currentXP) or 0))
    local original
    for _, flag in ipairs(originalFlags) do
        if not original and math.floor((tonumber(flags) or 0) / flag[1]) % 2 == 1 then
            original = flag[2]
        end
    end
    if not original then return currentXP end
    local slots = classes[classID]
    if not slots then return currentXP end
    for index, className in ipairs(slots) do
        if className == original then
            local level = math.max(1, math.floor(tonumber(levels[index]) or 1))
            local retiredXP = math.max(0, math.min(MAX_XP, tonumber(threshold(className, level)) or 0))
            return math.min(MAX_XP, currentXP + retiredXP)
        end
    end
    return currentXP
end
