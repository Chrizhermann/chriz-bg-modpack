-- Component 610: editable party-total rewards. See docs/utility-xp.md.
-- Edit this source before installation, or override/CBMUXPC.lua afterwards.
-- Restart the game after editing. No save editing or character respec is needed.
CBM_UtilityXP_Config = {
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
