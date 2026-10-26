-- Uninstalled, read-only native reward evidence capture. No hooks/register/load
-- side effects; the real MakeDualClass bridge calls this BEFORE its original.
-- Evidence is deliberately not a claim that aggregate effects are class-owned.
local R={schema=1}
local function integer(v,lo,hi,label)
    assert(type(v)=="number" and v%1==0 and v>=lo and v<=hi,"Invalid "..label)
    return v
end
local function uint(v,label) return integer(v,0,4294967295,label) end
-- EEex's current serializer mishandles some negative-width intervals. Preserve
-- exact signed int32 bits as uint32 and declare that encoding in every state.
local function signedBits(v,label) return integer(v,-2147483648,2147483647,label)%4294967296 end
local function scalarText(v,label)
    assert(type(v)=="string" and #v>0,"Missing "..label); return v
end
local function resref(v)
    local s=v:get(); assert(type(s)=="string" and #s<=8,"Invalid native resref"); return s
end
local unsignedFields={"m_effectId","m_targetType","m_spellLevel","m_dWFlags",
    "m_durationType","m_duration","m_probabilityUpper","m_probabilityLower",
    "m_numDice","m_diceSize","m_savingThrow","m_special","m_school",
    "m_JeremyIsAnIdiot","m_minLevel","m_maxLevel","m_flags","m_sourceType",
    "m_sourceFlags","m_projectileType","m_casterLevel","m_firstCall","m_secondaryType"}
local signedFields={"m_effectAmount","m_saveMod","m_effectAmount2","m_effectAmount3",
    "m_effectAmount4","m_effectAmount5","m_slotNum","m_sourceId","m_sourceTarget"}
local skillFields={"m_hideInShadowsBase","m_detectIllusionBase","m_setTrapsBase",
    "m_lockPickingBase","m_moveSilentlyBase","m_trapsBase","m_pickPocketBase"}
local resrefFields={"m_res","m_res2","m_res3","m_sourceRes"}
-- op233_words_v1: ordinal u32, unsignedFields u32 in order above, signedFields
-- two's-complement u32 in order above; then each resref: byte length + bytes.
-- Everything is ASCII hex. One Lua string per record avoids the serializer's
-- field-count limit and preserves duplicate records without verbose dictionaries.
local function word(n) return string.format("%08x",n) end
local function encodeEffect(e,ordinal)
    local parts={word(uint(ordinal,"effect ordinal"))}
    for _,field in ipairs(unsignedFields) do parts[#parts+1]=word(uint(e[field],field)) end
    for _,field in ipairs(signedFields) do parts[#parts+1]=word(signedBits(e[field],field)) end
    for _,field in ipairs(resrefFields) do
        local s=resref(e[field]);parts[#parts+1]=string.format("%02x",#s)
        for i=1,#s do parts[#parts+1]=string.format("%02x",string.byte(s,i)) end
    end
    return table.concat(parts)
end
function R.DecodeEffect(packed)
    assert(type(packed)=="string" and packed:match("^[0-9a-f]+$") and #packed%2==0,
        "Invalid packed op233 evidence")
    local at=1
    local function take(n)
        assert(at+n-1<=#packed,"Truncated packed op233 evidence")
        local value=tonumber(packed:sub(at,at+n-1),16);at=at+n;return value
    end
    local out={listOrdinal=take(8)}
    for _,field in ipairs(unsignedFields) do out[field]=take(8) end
    for _,field in ipairs(signedFields) do out[field]=take(8) end
    for _,field in ipairs(resrefFields) do
        local n=take(2);assert(n<=8,"Invalid packed resref")
        local chars={};for i=1,n do chars[i]=string.char(take(2)) end
        out[field]=table.concat(chars)
    end
    assert(at==#packed+1 and out.m_effectId==233,"Invalid op233 record tail/type")
    return out
end

local function effectEvidence(list)
    local result={}
    -- Traverse the real public CPtrList layout, detecting corruption without a
    -- fixture-derived effect-count limit. Keep duplicate effects and list order.
    local seen={}; local node=list.m_pNodeHead; local ordinal=0
    while node do
        local pointer=EEex_UDToPtr(node)
        assert(not seen[pointer],"Cyclic native effect list")
        seen[pointer]=true; ordinal=ordinal+1
        local e=node.data
        if e.m_effectId==233 then
            result[#result+1]=encodeEffect(e,ordinal)
        end
        node=node.pNext
    end
    return result
end

-- This is a snapshot, not a mutation/replay recipe. Native op233 setters touch
-- all matching effects; neither list order nor source resref proves ownership.
function R.CaptureState(sprite)
    assert(type(EEex_Sprite_GetActiveStats)=="function" and type(EEex_UDToPtr)=="function",
        "Concrete EEex sprite bindings required")
    local base=sprite.m_baseStats
    local stats=EEex_Sprite_GetActiveStats(sprite)
    local state={signedInt32Encoding="uint32_twos_complement",effectRecordEncoding="op233_words_v1",
        baseXP=uint(base.m_xp,"base XP"),flags=uint(base.m_flags,"flags"),
        class=integer(sprite.m_startTypeAI.m_Class,1,255,"native class"),
        kit=integer(base.m_mageSpecUpperWord,0,65535,"kit high")*65536+
            integer(base.m_mageSpecialization,0,65535,"kit low"),
        levels={integer(base.m_level1,0,255,"level 1"),integer(base.m_level2,0,255,"level 2"),
            integer(base.m_level3,0,255,"level 3")},
        maxHPBase=integer(base.m_maxHitPointsBase,0,65535,"base maximum HP"),
        legacyProficiencies={},proficiencies={},skills={},
        effects={timed=effectEvidence(sprite.m_timedEffectList),equipped=effectEvidence(sprite.m_equipedEffectList)}}
    for i=0,14 do
        local n=integer(base.m_proficiencies[i],-128,255,"legacy proficiency")
        state.legacyProficiencies[i+1]=n%256
    end
    for stat=89,134 do
        local bits=signedBits(stats:GetAtOffset(stat),"encoded proficiency")
        state.proficiencies[#state.proficiencies+1]={stat=stat,raw=bits,
            active=bits%8,inactive=math.floor(bits/8)%8}
    end
    for _,field in ipairs(skillFields) do state.skills[field]=integer(base[field],0,255,field) end
    return state
end

local function captureBoundary(sprite,context,isPreview)
    assert(type(context)=="table","Dual receipt context required")
    local owner=scalarText(context.ownerKey,"save owner")
    assert(#owner==32 and string.match(owner,"^[0-9a-f]+$"),"Invalid save owner")
    local incarnation=scalarText(context.incarnation,"native incarnation")
    local revision=integer(context.revision,0,9007199254740991,"ledger revision")
    local oldClass=integer(context.oldClass,1,255,"old class")
    local newClass
    local boundary
    if isPreview then
        assert(type(CBMBank_Reset.PreviewQuery)=="function","Native pre-preview boundary required")
        boundary=CBMBank_Reset.PreviewQuery(sprite)
        assert(boundary and boundary.stage=="capturing" and boundary.incarnation==incarnation,
            "Receipt requires matching native pre-preview boundary")
    else
        newClass=integer(context.newClass,1,255,"new class")
        assert(oldClass~=newClass,"Dual class identity must change")
        boundary=CBMBank_Reset.Query(sprite)
        assert(boundary and boundary.stage=="preparing" and boundary.incarnation==incarnation
            and boundary.newClass==newClass,"Receipt requires matching native pre-reset boundary")
    end
    local before=R.CaptureState(sprite)
    assert(before.class==oldClass and before.baseXP==boundary.preBase,"Native pre-dual state changed")
    -- Original-class flags cannot be present on an eligible single-class source.
    for _,mask in ipairs({8,16,32,64,128,256}) do
        assert(math.floor(before.flags/mask)%2==0,"Receipt source is already dual-class")
    end
    assert(before.levels[1]>=1,"Native old class has no level")
    return {schema=R.schema,kind="pre_dual_reward_evidence",ownerKey=owner,
        incarnation=incarnation,ledgerRevision=revision,oldClass=oldClass,newClass=newClass,
        captureBoundary=isPreview and "before_dual_preview" or "before_native_reset",
        oldLevelAtDual=before.levels[1],before=before,
        ownership="unpartitioned_native_baseline",manualTransactions={}}
end

-- Before StartEditing(mode=DUALCLASS_CLASS), before new-class allocation mutates
-- inactive proficiencies. The new class has not been chosen: leave it absent.
-- Root may add that metadata after validating the matching native reset scope.
function R.CaptureBeforePreview(sprite,context)
    return captureBoundary(sprite,context,true)
end

-- This later snapshot can include accepted NEW-class preview choices. Preserve
-- it as final pre-reset evidence, never substitute it for the clean baseline.
function R.CaptureBeforeDual(sprite,context)
    return captureBoundary(sprite,context,false)
end

return R
