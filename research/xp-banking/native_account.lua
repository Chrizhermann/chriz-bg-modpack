-- Native-backed account: ordinary XP has ONE authoritative copy, in base m_xp.
-- Only policy/progress/floor and the old account destroyed by dualing are saved.
-- No engine writes. The EEex adapter supplies the actual native base and ceiling.
local M = {}
local MAX, U32 = 9007199254740991, 4294967295
local phases = {BG1=1, SOD=2, SOA=3, TOB=4}
local policies = {bg1_sod=true, bg1_sod_soa=true}
local function integer(n, maximum)
    return type(n)=="number" and n>=0 and n<=(maximum or MAX) and n%1==0
end
local function copy(value, seen)
    if type(value)~="table" then return value end
    seen=seen or {}; if seen[value] then return seen[value] end
    local out={}; seen[value]=out
    for k,v in next,value do out[copy(k,seen)]=copy(v,seen) end
    return out
end
local function checked(a,b)
    assert(integer(a) and integer(b) and a<=MAX-b,"XP exceeds exact storage")
    return a+b
end
local function valid(s)
    assert(type(s)=="table" and s.schema==2,"Unsupported native account; preserve original carrier")
    assert(policies[s.policy] and phases[s.phase],"Invalid saved policy or campaign")
    assert(integer(s.revision) and integer(s.floor,U32) and integer(s.overflow),"Invalid account metadata")
    assert(s.kind=="single" or s.kind=="multi" or s.kind=="dual","Invalid class accounting")
    if s.kind=="dual" then
        local old=s.old
        assert(type(old)=="table" and integer(old.class,255) and old.class>0
            and integer(old.newClass,255) and old.newClass>0 and old.newClass~=old.class
            and integer(old.levelAtDual,255) and old.levelAtDual>0,"Invalid old-class identity")
        assert(integer(old.total) and integer(old.usable) and old.usable<=old.total
            and integer(old.preUsable) and integer(old.preBank)
            and checked(old.preUsable,old.preBank)==old.total,"Invalid frozen old-class account")
        assert(old.usable>=old.preUsable,"Released old-class XP cannot be removed")
    else assert(s.old==nil,"Nondual account has an old-class partition") end
    return true
end
M.Validate=valid
function M.Ceiling(s,native)
    valid(s); assert(integer(native,U32),"Invalid native XP ceiling")
    local own
    if s.phase=="BG1" then own=161000
    elseif s.phase=="SOD" then own=500000
    elseif s.phase=="SOA" and s.policy=="bg1_sod_soa" then own=2950000 end
    return math.min(native,math.max(own or native,s.floor))
end
function M.Adopt(policy,phase,base,kind)
    assert(integer(base,U32),"Invalid native base XP")
    assert(kind=="single" or kind=="multi","Existing dual needs an explicit history-free adoption path")
    local s={schema=2,policy=policy,phase=phase,revision=0,floor=base,overflow=0,kind=kind}
    valid(s); return s
end
function M.AdoptExistingDual(policy,phase,base,oldClass,newClass,oldLevel,threshold)
    assert(integer(base,U32) and integer(threshold,U32),"Invalid existing native XP")
    local s={schema=2,policy=policy,phase=phase,revision=0,
        floor=math.min(U32,checked(base,threshold)),overflow=0,kind="dual",
        old={class=oldClass,newClass=newClass,levelAtDual=oldLevel,total=threshold,
             usable=threshold,preUsable=threshold,preBank=0},history="native_threshold"}
    -- No fictional reconstruction of XP that vanilla discarded before install.
    valid(s); return s
end
function M.Inspect(s,base,native,retiredThreshold)
    valid(s); assert(integer(base,U32),"Invalid native base XP")
    local active=checked(base,s.overflow)
    local totalCap=M.Ceiling(s,native)
    local oldTotal,oldUsable=0,0
    if s.kind=="dual" then
        assert(integer(retiredThreshold,U32) and retiredThreshold<=s.old.usable,
            "Retired native threshold is not reconciled with saved entitlement")
        oldTotal,oldUsable=s.old.total,s.old.usable
    end
    local available=math.min(active,math.max(0,totalCap-oldUsable))
    -- The engine still has only a uint32 word; overflow is not silently credited.
    available=math.min(available,U32)
    return {activeTotal=active,activeUsable=available,activeBank=active-available,
        oldTotal=oldTotal,oldUsable=oldUsable,oldBank=oldTotal-oldUsable,
        total=checked(oldTotal,active),cap=totalCap,
        bank=checked(oldTotal-oldUsable,active-available),
        usable=checked(oldUsable,available)}
end
function M.Advance(s,phase,native)
    valid(s); assert(phases[phase] and phases[phase]>=phases[s.phase],"Invalid campaign regression")
    local nextState=copy(s)
    if phase==s.phase then return nextState end
    assert(s.revision<MAX,"Account revision exhausted")
    nextState.phase,nextState.revision=phase,s.revision+1
    local ceiling=M.Ceiling(nextState,native)
    if s.kind=="dual" then
        -- Old awards occurred first; release them to their own class first.
        nextState.old.usable=math.max(s.old.usable,math.min(s.old.total,ceiling))
    end
    valid(nextState); return nextState
end
-- Only the verified positive permanent opcode-104 leaf supplies these values.
-- The ordinary portion is already in the native base word. Store ONLY the part
-- that would have wrapped, never another copy of an ordinary earned balance.
function M.CompleteAward(s,preBase,amount,applied,remainder,postBase)
    valid(s)
    assert(integer(preBase,U32) and integer(amount,2147483647) and amount>0,
        "Invalid native positive XP award")
    assert(applied==math.min(amount,U32-preBase) and remainder==amount-applied
        and postBase==preBase+applied,"Native XP award did not match its prepared split")
    assert(s.revision<MAX,"Account revision exhausted")
    local nextState=copy(s)
    nextState.overflow=checked(s.overflow,remainder)
    checked(postBase,nextState.overflow) -- reject precision loss before publication
    if s.old then checked(s.old.total,checked(postBase,nextState.overflow)) end
    nextState.revision=s.revision+1
    valid(nextState); return nextState
end
-- SetAtOffset's stat44 contract is exact: modifier1 adds, every other modifier
-- replaces. A native scoped caller may additionally identify owned monotonic
-- recruitment or the separately authored party-average replacement policy.
-- This is never inferred from the size or sign of a polled XP difference.
function M.PrepareWrite(s,base,rawValue,modifier,origin,source,effectMode)
    valid(s)
    assert(integer(base,U32) and integer(rawValue,U32) and integer(modifier,U32),
        "Invalid native XP writer arguments")
    assert(origin=="unclassified" or origin=="recruitment_catchup"
        or origin=="party_average_set","Unrecognized native XP writer scope")
    source=source or "stat44"
    assert(source=="stat44" or source=="opcode104","Unrecognized native XP writer source")
    if source=="opcode104" then
        assert(origin=="unclassified" and integer(effectMode,2)
            and modifier==(effectMode==0 and 1 or effectMode==1 and 0 or 2),
            "Opcode-104 source and native modifier disagree")
    else assert(effectMode==nil,"Stat44 setter cannot claim an effect mode") end
    assert(s.revision<MAX,"Account revision exhausted")
    local before=checked(base,s.overflow)
    local total,classification
    if source=="opcode104" and effectMode==2 then
        assert(s.overflow==0,
            "Unsupported opcode-104 percentage of an overflow bank; retained XP was not changed")
        -- Actual native math is unsigned division of the LOW32 product by100.
        -- Keep that engine behavior, including its wrapping multiply, without
        -- pretending it defines a percentage policy for our overflow carrier.
        local loA,loB=base%65536,rawValue%65536
        local hiA,hiB=math.floor(base/65536),math.floor(rawValue/65536)
        local product=(loA*loB+((hiA*loB+loA*hiB)%65536)*65536)%4294967296
        total=math.floor(product/100);classification="native_percent_low32"
    elseif modifier==1 then
        assert(origin=="unclassified","Owned XP replacement invoked as ADD")
        if rawValue<=2147483647 then
            total=checked(before,rawValue);classification="native_add"
        else
            local loss=4294967296-rawValue
            assert(loss<=before,"Native XP loss exceeds retained active XP; reconciliation required")
            total=before-loss;classification="native_loss"
        end
    elseif origin=="recruitment_catchup" then
        total=math.max(before,rawValue);classification=origin
    else
        total=rawValue;classification=origin=="party_average_set" and origin or "unclassified_absolute_set"
    end
    local nextState=copy(s)
    local target=math.min(U32,total)
    nextState.overflow=total-target
    nextState.revision=s.revision+1
    if s.old then checked(s.old.total,total) end
    valid(nextState)
    return nextState,target,{classification=classification,activeBefore=before,
        activeAfter=total,rawValue=rawValue,modifier=modifier,source=source,effectMode=effectMode}
end
function M.PrepareDual(s,base,native,oldClass,newClass,oldLevel,retiredThreshold)
    valid(s); assert(s.kind=="single","Only a single-class character can begin a native dual")
    local view=M.Inspect(s,base,native)
    assert(integer(retiredThreshold,U32) and retiredThreshold<=view.activeUsable,
        "Installed retired threshold exceeds usable XP")
    -- With no bank, vanilla retains only the installed current-level threshold;
    -- between-level progress is discarded, not transferred or reserved as XP.
    -- A pre-existing bank instead protects the exact pre-reset usable baseline.
    local oldUsable=view.activeBank>0 and view.activeUsable or retiredThreshold
    assert(s.revision<MAX,"Account revision exhausted")
    local nextState=copy(s)
    nextState.kind,nextState.overflow,nextState.revision="dual",0,s.revision+1
    nextState.old={class=oldClass,newClass=newClass,levelAtDual=oldLevel,
        total=checked(oldUsable,view.activeBank),usable=oldUsable,
        preUsable=oldUsable,preBank=view.activeBank}
    valid(nextState); return nextState
end
return M
