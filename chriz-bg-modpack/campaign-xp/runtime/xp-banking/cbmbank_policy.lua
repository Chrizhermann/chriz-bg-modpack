-- Uninstalled design prototype. No engine reads, hooks, XP writes or persistence.
-- Passing these pure policy checks does not establish native award/save safety.
local M = {}
local MAX = 9007199254740991 -- exact integer limit in both supported Lua runtimes
local rank = {BG1 = 1, SOD = 2, SOA = 3, TOB = 4}
local policies = {bg1_sod = true, bg1_sod_soa = true}

local function integer(value)
    return type(value) == "number" and value >= 0 and value <= MAX
        and value % 1 == 0
end

local function checkedSum(a, b)
    if a > MAX - b then return nil, "XP exceeds exact integer storage." end
    return a + b
end

local function detached(value, seen)
    if type(value) ~= "table" then return value end
    seen = seen or {}
    if seen[value] then return seen[value] end
    local result = {}; seen[value] = result
    for key, item in next, value do result[detached(key, seen)] = detached(item, seen) end
    return result
end

function M.Campaign(current, endBG1, inToB, savedPhase)
    if not rank[current] then return nil, "Unsupported campaign." end
    if not integer(endBG1) or endBG1 > 2 or not integer(inToB) or inToB > 1 then
        return nil, "Invalid campaign flags."
    end
    if savedPhase ~= nil and not rank[savedPhase] then
        return nil, "Invalid save-owned campaign progress."
    end
    local phase
    if inToB == 1 then phase = "TOB"
    elseif current == "TOB" then return nil, "Waiting for ToB initialization."
    elseif endBG1 == 2 then phase = "SOA"
    elseif current == "SOA" then return nil, "Waiting for SoA initialization."
    elseif current == "SOD" and endBG1 == 0 then
        return nil, "Waiting for SoD initialization."
    elseif current == "SOD" then phase = "SOD"
    else phase = "BG1" end -- Sarevok's death alone does not begin SoD.
    if savedPhase and rank[savedPhase] > rank[phase] then phase = savedPhase end
    return phase
end

local function cap(policy, phase)
    if phase == "BG1" then return 161000 end
    if phase == "SOD" then return 500000 end
    if phase == "SOA" and policy == "bg1_sod_soa" then return 2950000 end
    return nil -- no campaign cap; native installation rules still apply
end

local function validate(state)
    if type(state) ~= "table" or state.schema ~= 1 then
        return nil, "Unknown bank schema; preserve the original payload."
    end
    if not policies[state.policy] or not rank[state.phase] then
        return nil, "Invalid saved policy or campaign."
    end
    if state.classKind ~= "single" and state.classKind ~= "multi" then
        return nil, "Dual ownership is approved; native reset and deferred progression are unresolved."
    end
    for _, field in ipairs({"usable", "bank", "revision"}) do
        if not integer(state[field]) then return nil, "Invalid " .. field .. "." end
    end
    local total, reason = checkedSum(state.usable, state.bank)
    if not total then return nil, reason end
    return true
end

function M.Adopt(policy, phase, usable, classKind)
    local state = {schema = 1, policy = policy, phase = phase,
        usable = usable, bank = 0, revision = 0, classKind = classKind}
    local ok, reason = validate(state)
    if not ok then return nil, reason end
    -- Existing progress is retained, including XP above the chosen cap.
    -- This does not reconstruct previously lost XP or certify existing saves.
    return state
end

function M.Cap(state)
    local ok, reason = validate(state)
    if not ok then return nil, reason end
    return cap(state.policy, state.phase)
end

local function plan(state, usable, bank, phase, kind)
    if state.revision == MAX then return nil, "Bank revision exhausted." end
    if not checkedSum(usable, bank) then return nil, "XP exceeds exact integer storage." end
    return {schema = 1, policy = state.policy, classKind = state.classKind,
        beforeUsable = state.usable, beforeBank = state.bank,
        beforePhase = state.phase, expectedRevision = state.revision,
        usable = usable, bank = bank, phase = phase,
        usableDelta = usable - state.usable, bankDelta = bank - state.bank,
        revision = state.revision + 1, operation = kind}
end

-- Input is one character's final native entitlement, never a party-total award.
-- Native source/mode classification and exact party splitting belong to the hook.
function M.Earn(state, amount)
    local ok, reason = validate(state)
    if not ok then return nil, reason end
    if not integer(amount) then return nil, "Invalid earned entitlement." end
    local total
    total, reason = checkedSum(state.usable + state.bank, amount)
    if not total then return nil, reason end
    local limit = cap(state.policy, state.phase)
    local granted = limit and math.min(amount, math.max(0, limit - state.usable)) or amount
    local result
    result, reason = plan(state, state.usable + granted, state.bank + amount - granted,
        state.phase, "earn")
    if result then result.entitlement = amount end
    return result, reason
end

function M.Advance(state, nextPhase)
    local ok, reason = validate(state)
    if not ok then return nil, reason end
    if not rank[nextPhase] then return nil, "Unsupported campaign." end
    if rank[nextPhase] < rank[state.phase] then
        return nil, "Campaign regression requires loading that save's own state."
    end
    if nextPhase == state.phase then
        return plan(state, state.usable, state.bank, state.phase, "unchanged")
    end
    local limit = cap(state.policy, nextPhase)
    local released = limit and math.min(state.bank, math.max(0, limit - state.usable)) or state.bank
    return plan(state, state.usable + released, state.bank - released, nextPhase, "release")
end

-- Only monotonic catch-up such as 237/238; absolute SET/respec/loss are excluded.
-- Target is compared against entitlement so hidden XP cannot be awarded twice.
function M.CatchUp(state, target)
    local ok, reason = validate(state)
    if not ok then return nil, reason end
    if not integer(target) then return nil, "Invalid catch-up target." end
    local result
    result, reason = M.Earn(state, math.max(0, target - state.usable - state.bank))
    if result then result.operation, result.target = "catch_up", target end
    return result, reason
end

-- Pure snapshot application only. This is NOT a native XP/marshal transaction.
-- Returning a new state leaves the original payload (including extensions) intact.
function M.Apply(state, proposed)
    local ok, reason = validate(state)
    if not ok then return nil, reason end
    if type(proposed) ~= "table" or proposed.expectedRevision ~= state.revision
        or proposed.beforeUsable ~= state.usable or proposed.beforeBank ~= state.bank
        or proposed.beforePhase ~= state.phase or proposed.policy ~= state.policy
        or proposed.classKind ~= state.classKind then
        return nil, "Stale or mismatched operation; no changes applied."
    end
    local expected
    if proposed.operation == "earn" then
        expected, reason = M.Earn(state, proposed.entitlement)
    elseif proposed.operation == "catch_up" then
        expected, reason = M.CatchUp(state, proposed.target)
    elseif proposed.operation == "release" or proposed.operation == "unchanged" then
        expected, reason = M.Advance(state, proposed.phase)
    else
        return nil, "Unrecognized operation; no changes applied."
    end
    if not expected then return nil, reason end
    for _, field in ipairs({"schema", "usable", "bank", "phase", "revision",
        "usableDelta", "bankDelta", "operation", "entitlement", "target"}) do
        if proposed[field] ~= expected[field] then
            return nil, "Inconsistent operation; no changes applied."
        end
    end
    local result = detached(state)
    result.usable, result.bank, result.phase = proposed.usable, proposed.bank, proposed.phase
    result.revision = proposed.revision
    ok, reason = validate(result)
    if not ok then return nil, reason end
    if result.revision ~= state.revision + 1 or rank[result.phase] < rank[state.phase] then
        return nil, "Invalid operation revision or campaign."
    end
    return result
end

return M
