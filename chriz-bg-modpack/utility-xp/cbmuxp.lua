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
        return math.ceil(value / step) * step
    end
    return math.floor(value / step + 0.5) * step
end

function M.Validate(config)
    assert(type(config) == "table", "utility XP configuration must be a table")
    local step = config.roundingStep == nil and 1 or config.roundingStep
    assert(numberInRange(step, MAX_XP) and step >= 1 and step % 1 == 0,
        "roundingStep must be a positive integer")
    assert(config.roundingMode == nil or config.roundingMode == "up"
        or config.roundingMode == "nearest", "roundingMode must be up or nearest")
    assert(type(config.anchors) == "table" and #config.anchors >= 2,
        "utility XP needs at least two anchors")
    local previous = -1
    for i, anchor in ipairs(config.anchors) do
        assert(type(anchor) == "table", "invalid utility XP anchor " .. i)
        assert(numberInRange(anchor.xp, MAX_XP) and anchor.xp % 1 == 0
            and anchor.xp > previous, "anchor XP must be increasing nonnegative integers")
        for _, key in ipairs(keys) do
            assert(numberInRange(anchor[key], MAX_XP), "invalid anchor reward: " .. key)
            if i > 1 then
                assert(anchor[key] >= config.anchors[i - 1][key],
                    "anchor rewards must not decrease: " .. key)
            end
        end
        previous = anchor.xp
    end
    assert(config.anchors[1].xp == 0, "first utility XP anchor must start at zero")
    for _, key in ipairs(keys) do
        local multiplier = config[key .. "Multiplier"]
        assert(numberInRange(multiplier, MAX_XP), "invalid multiplier: " .. key)
        local highest = config.anchors[#config.anchors][key] * multiplier
        assert(roundReward(config, highest * (key == "scribe" and 9 or 1)) <= MAX_XP,
            "utility XP reward exceeds engine integer range: " .. key)
    end
    return config
end

function M.Rewards(config, xp)
    assert(numberInRange(xp, MAX_XP), "invalid protagonist XP")
    local anchors = config.anchors
    local low, high = anchors[#anchors], anchors[#anchors]
    for i = 2, #anchors do
        if xp < anchors[i].xp then
            low, high = anchors[i - 1], anchors[i]
            break
        end
    end
    local fraction = low == high and 0 or (xp - low.xp) / (high.xp - low.xp)
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
    assert(numberInRange(currentXP, MAX_XP), "invalid current character XP")
    local original
    for _, flag in ipairs(originalFlags) do
        if math.floor(flags / flag[1]) % 2 == 1 then
            assert(not original, "multiple original-class flags on protagonist")
            original = flag[2]
        end
    end
    if not original then return currentXP end
    local slots = classes[classID]
    assert(slots and #slots == 2, "unsupported dual-class combination")
    for index, className in ipairs(slots) do
        if className == original then
            local level = levels[index]
            assert(type(level) == "number" and level >= 1 and level % 1 == 0,
                "invalid retired class level")
            local retiredXP = threshold(className, level)
            assert(numberInRange(retiredXP, MAX_XP), "missing retired class XP threshold")
            return math.min(MAX_XP, currentXP + retiredXP)
        end
    end
    error("original class does not match protagonist class")
end
