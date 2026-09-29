-- Component 611: native campaign reward tables, independent of character XP.
-- See docs/story-utility-xp.md for vanilla evidence and the EE Fixpack correction.
CBM_StoryXP = {}
local M = CBM_StoryXP

function M.Phase(campaign, endBG1, inToB)
    if campaign ~= "BG1" and campaign ~= "SOD"
        and campaign ~= "SOA" and campaign ~= "TOB" then
        return nil, "Unsupported campaign: " .. tostring(campaign)
    end
    if (endBG1 ~= 0 and endBG1 ~= 1 and endBG1 ~= 2)
        or (inToB ~= 0 and inToB ~= 1) then
        return nil, "Unsupported EET campaign flags."
    end
    -- Story progress wins even when revisiting earlier campaign areas.
    if inToB == 1 or endBG1 == 2 then return "bg2" end
    if campaign == "BG1" or campaign == "SOD" then return "bg1" end
    -- Direct SoA/ToB starts set their globals in the opening area script.
    -- Retry on subsequent updates; never cache the initial zeros as BG1.
    return nil, "Waiting for EET campaign initialization."
end

function M.Rewards(phase, level)
    assert(phase == "bg1" or phase == "bg2", "Unsupported reward phase")
    assert(type(level) == "number" and level >= 1 and level % 1 == 0,
        "Invalid XPBONUS ability level")
    local bracket = level <= 5 and 1 or level <= 10 and 2 or level <= 15 and 3 or 4
    local locks, traps, scribe
    if phase == "bg1" then
        -- Raw BG1/SoD has 15 at level 16+: EE Fixpack corrects this typo to 155.
        locks, traps, scribe = {25, 40, 95, 155}, {10, 17, 27, 32}, 10
    else
        locks, traps, scribe = {250, 400, 950, 1550}, {1000, 1750, 2750, 3250}, 1000
    end
    return {lock = locks[bracket], trap = traps[bracket],
        scribe = level <= 9 and scribe * level or 0}
end
