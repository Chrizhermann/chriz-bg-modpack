-- Uninstalled dual-class ownership policy; no engine reads, writes or hooks.
-- Native dual/level-up and persistence transactions must publish this state
-- together with verified native results. Pure policy success is not that proof.
local M = {}
local MAX = 9007199254740991
local phases = {BG1=1, SOD=2, SOA=3, TOB=4}
local policies = {bg1_sod=true, bg1_sod_soa=true}
local fields = {"schema", "classKind", "policy", "phase", "revision",
    "oldClass", "newClass", "oldLevelAtDual", "preResetUsable", "preResetBank",
    "retiredThreshold", "nativeDiscarded", "retiredUsable", "retiredBank",
    "usable", "bank"}
local owned={}; for _,field in ipairs(fields) do owned[field]=true end

local function integer(n)
    return type(n)=="number" and n>=0 and n<=MAX and n%1==0
end
local function sum(...)
    local total=0
    for i=1,select("#",...) do
        local n=select(i,...)
        if not integer(n) or total>MAX-n then return nil end
        total=total+n
    end
    return total
end
local function copy(t,seen)
    if type(t)~="table" then return t end
    seen=seen or {}
    if seen[t] then return seen[t] end
    local out={}; seen[t]=out
    for k,v in next,t do out[copy(k,seen)]=copy(v,seen) end
    return out
end
local function class(n) return integer(n) and n>0 and n<256 end
local function cap(policy,phase,nativeCeiling)
    if nativeCeiling~=nil and not integer(nativeCeiling) then
        return nil,"Invalid retained native ceiling."
    end
    local result
    if phase=="BG1" then result=161000
    elseif phase=="SOD" then result=500000
    elseif phase=="SOA" and policy=="bg1_sod_soa" then result=2950000 end
    if nativeCeiling~=nil then result=result and math.min(result,nativeCeiling) or nativeCeiling end
    return result
end
local function validate(s)
    if type(s)~="table" or s.schema~=1 or s.classKind~="dual" then
        return nil,"Unsupported dual state; preserve its original payload."
    end
    if not policies[s.policy] or not phases[s.phase] then return nil,"Invalid saved policy or phase." end
    if not class(s.oldClass) or not class(s.newClass) or s.oldClass==s.newClass
        or not class(s.oldLevelAtDual) then return nil,"Invalid dual class identity or level." end
    for _,k in ipairs({"revision","preResetUsable","preResetBank","retiredThreshold",
        "nativeDiscarded","retiredUsable","retiredBank","usable","bank"}) do
        if not integer(s[k]) then return nil,"Invalid "..k.."." end
    end
    if s.retiredThreshold>s.preResetUsable then return nil,"Retired threshold exceeds pre-reset usable XP." end
    local oldTotal=sum(s.preResetUsable,s.preResetBank)
    local actual=sum(s.retiredUsable,s.retiredBank,s.nativeDiscarded)
    if not oldTotal or actual~=oldTotal then return nil,"Old-class entitlement changed." end
    if s.preResetBank>0 then
        -- The owned bank preserves the planned old-class build, including its
        -- exact pre-reset baseline. Threshold + bank would lose part of it.
        if s.nativeDiscarded~=0 or s.retiredUsable<s.preResetUsable
            or s.retiredBank>s.preResetBank then return nil,"Invalid protected old-class account." end
    elseif s.nativeDiscarded~=s.preResetUsable-s.retiredThreshold
        or s.retiredUsable~=s.retiredThreshold or s.retiredBank~=0 then
        return nil,"Ordinary unbanked dual must preserve native reset accounting."
    end
    if not sum(s.retiredUsable,s.retiredBank,s.usable,s.bank,s.nativeDiscarded) then
        return nil,"XP exceeds exact storage."
    end
    return true
end
M.Validate=validate

-- Capture before MakeDualClass resets XP. Metadata comes from installed rules,
-- not hardcoded level tables; class eligibility remains the native UI's choice.
-- Return is a proposed snapshot, not permission to bypass/call native dualing.
function M.Start(single,meta)
    if type(single)~="table" or single.schema~=1 or single.classKind~="single"
        or not policies[single.policy] or not phases[single.phase]
        or not integer(single.revision) or single.revision==MAX
        or not sum(single.usable,single.bank) then return nil,"Invalid pre-dual snapshot." end
    if type(meta)~="table" or not class(meta.oldClass) or not class(meta.newClass)
        or not class(meta.oldLevel) then return nil,"Missing or invalid installed dual metadata." end
    local protected=single.bank>0
    local s={schema=1,classKind="dual",policy=single.policy,phase=single.phase,
        revision=single.revision+1,oldClass=meta.oldClass,newClass=meta.newClass,
        oldLevelAtDual=meta.oldLevel,preResetUsable=single.usable,preResetBank=single.bank,
        retiredThreshold=meta.retiredThreshold,retiredUsable=protected and single.usable or meta.retiredThreshold,
        retiredBank=single.bank,usable=0,bank=0}
    if not integer(meta.retiredThreshold) then return nil,"Invalid installed retired threshold." end
    s.nativeDiscarded=protected and 0 or single.usable-meta.retiredThreshold
    local detached=copy(single)
    for k,v in pairs(detached) do if not owned[k] then s[k]=v end end
    local ok,why=validate(s)
    if not ok then return nil,why end
    return s
end

function M.Status(s,nativeCeiling)
    local ok,why=validate(s); if not ok then return nil,why end
    local limit; limit,why=cap(s.policy,s.phase,nativeCeiling); if why then return nil,why end
    return {retiredUsable=s.retiredUsable,retiredBank=s.retiredBank,
        activeUsable=s.usable,activeBank=s.bank,cap=limit,
        usable=s.retiredUsable+s.usable,bank=s.retiredBank+s.bank,
        entitlement=s.retiredUsable+s.retiredBank+s.usable+s.bank,
        nativeDiscarded=s.nativeDiscarded}
end

local function plan(s,kind,amount,phase,nativeCeiling)
    local ok,why=validate(s); if not ok then return nil,why end
    if s.revision==MAX then return nil,"Revision exhausted." end
    if not phases[phase] or phases[phase]<phases[s.phase] then return nil,"Invalid forward campaign." end
    local limit; limit,why=cap(s.policy,phase,nativeCeiling); if why then return nil,why end
    local result=copy(s)
    local room=limit and math.max(0,limit-s.retiredUsable-s.usable) or MAX
    if kind=="earn" then
        if not integer(amount) or not sum(s.retiredUsable,s.retiredBank,s.usable,s.bank,s.nativeDiscarded,amount) then
            return nil,"Invalid or overflowing earned entitlement."
        end
        local grant=math.min(room,amount)
        result.usable=s.usable+grant
        result.bank=s.bank+amount-grant
    elseif kind=="advance" then
        if phase~=s.phase then
            -- Old awards happened first. Restore their own class first, then
            -- release post-dual awards; neither amount changes ownership.
            local old=math.min(room,s.retiredBank)
            local new=math.min(room-old,s.bank)
            result.retiredUsable=s.retiredUsable+old
            result.retiredBank=s.retiredBank-old
            result.usable=s.usable+new
            result.bank=s.bank-new
        end
    else return nil,"Unsupported operation." end
    result.phase=phase
    result.revision=s.revision+1
    ok,why=validate(result); if not ok then return nil,why end
    local before={}
    for _,k in ipairs(fields) do before[k]=s[k] end
    return {before=before,after=result,operation=kind,amount=amount,nativeCeiling=nativeCeiling}
end
function M.Earn(s,amount,nativeCeiling) return plan(s,"earn",amount,s and s.phase,nativeCeiling) end
function M.Advance(s,phase,nativeCeiling) return plan(s,"advance",nil,phase,nativeCeiling) end

function M.Apply(s,p)
    local ok,why=validate(s); if not ok then return nil,why end
    if type(p)~="table" or type(p.before)~="table" or type(p.after)~="table" then return nil,"Malformed plan." end
    for _,k in ipairs(fields) do
        if s[k]~=p.before[k] then return nil,"Stale dual plan." end
    end
    local expected
    if p.operation=="earn" then expected,why=M.Earn(s,p.amount,p.nativeCeiling)
    elseif p.operation=="advance" then expected,why=M.Advance(s,p.after.phase,p.nativeCeiling)
    else return nil,"Unsupported operation." end
    if not expected then return nil,why end
    for _,k in ipairs(fields) do
        if p.after[k]~=expected.after[k] then return nil,"Inconsistent dual plan." end
    end
    -- Never accept caller-supplied extensions as mutations through a plan.
    local result=copy(s)
    for _,k in ipairs(fields) do result[k]=expected.after[k] end
    return result
end

return M
