-- Component 620: called once by Imoen's override script after maze recruitment.
local marker = "CBM_ImoenSpellholdXP"
local maze = { AR1512 = true, AR1513 = true, AR1514 = true }
local lastError

local function apply(sprite)
    if not sprite or EEex_Sprite_GetLocalInt(sprite, marker) ~= 0 then return end
    local area = sprite.m_pArea
    if not area or not maze[area.m_resref:get():upper()] then return end

    local total, count, found = 0, 0, false
    for portrait = 0, 5 do
        local member = EEex_Sprite_GetInPortrait(portrait)
        if member then
            -- Compare engine IDs: separate userdata can wrap the same sprite.
            if member.m_id == sprite.m_id then
                found = true
            else
                -- Native XP is pooled for multiclasses and active-class XP for
                -- dual classes. Retired-class XP is deliberately not added.
                total = total + member.m_baseStats.m_xp
                count = count + 1
            end
        end
    end
    if not found then return end -- declined recruitment / already left the party
    assert(count > 0 and count + 1 == EEex_Sprite_GetNumCharacters(),
        "Cannot read the complete party for Imoen's XP average")
    local target = math.min(3000000, math.floor(total / count))

    -- ChangeStat is in INSTANT.IDS; use the engine's native XP setter without
    -- replacing the Lua action or touching levels, HP, spells or thief skills.
    EEex_Action_ExecuteResponseStringOnAIBaseInstantly(
        string.format("ChangeStat(Myself,XP,%d,SET)", target), sprite)
    -- Vanilla finishes at 1; EET uses 1 for a pending retired-thief deduction
    -- and 2 for completion. Setting 2 satisfies both without losing thief XP.
    EEex_Sprite_SetLocalInt(sprite, "BD_JOINXP", 2)
    EEex_Sprite_SetLocalInt(sprite, marker, 1)
end

function CBM_ImoenXP_Apply(sprite)
    local ok, err = pcall(apply, sprite)
    if not ok then
        err = tostring(err)
        if err ~= lastError then print("[CBM Imoen XP] " .. err) end
        lastError = err
    else
        lastError = nil
    end
    -- No return value: EEex_LuaAction treats numeric returns as action statuses.
end

if not EEex_Active then
    print("[CBM Imoen XP] EEex is inactive; launch through InfinityLoader.")
end
