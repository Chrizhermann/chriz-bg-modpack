-- UNINSTALLED native derived-XP cap prototype. No hook is installed on load.
-- Base XP is deliberately untouched: native saving retains ordinary excess.
-- Requires reviewed lifecycle/ledger providers and separate native acceptance.
local M={errors={}}
local U32=4294967295
local phase={BG1=true,SOD=true,SOA=true,TOB=true}
local chapterCaps={
    CH1=16000, CH2=16000, CH3=20000, CH4=32000,
    CH5=64000, CH6=85000, CH7=161000,
    CH8=200000, CH9=250000, CH10=350000, CH11=420000,
    CH12=500000, CH13=500000, CH14=1000000, CH15=2500000,
    CH16=2900000, CH17=3250000, CH18=3500000, CH19=3500000,
    CH20=5000000, CH21=8000000, CH22=8900000,
}
local function uint(n) return type(n)=="number" and n>=0 and n<=U32 and n%1==0 end

-- Snapshot is provided by an actor-owned, versioned adapter. retiredDebit is
-- protected old-class entitlement already released; it is NOT a guessed level.
function M.Select(snapshot,nativeCap,derivedXP)
    if not uint(nativeCap) or not uint(derivedXP) then return nil,"Invalid native XP/cap." end
    if type(snapshot)~="table" or type(snapshot.eligible)~="boolean" then return nil,"Missing verified eligibility." end
    if not snapshot.eligible then return derivedXP end
    if snapshot.policy~="bg1_sod" and snapshot.policy~="bg1_sod_soa"
        and snapshot.policy~="chapter_caps" then return nil,"Unknown saved cap policy." end
    local validPhase=(snapshot.policy=="chapter_caps" and chapterCaps[snapshot.phase]~=nil)
        or (snapshot.policy~="chapter_caps" and phase[snapshot.phase]==true)
    if not validPhase or not uint(snapshot.usableFloor) then return nil,"Invalid saved phase/adoption floor." end
    local limit=nativeCap
    if snapshot.policy=="chapter_caps" then limit=chapterCaps[snapshot.phase]
    elseif snapshot.phase=="BG1" then limit=161000
    elseif snapshot.phase=="SOD" then limit=500000
    elseif snapshot.phase=="SOA" and snapshot.policy=="bg1_sod_soa" then limit=2950000 end
    limit=math.min(nativeCap,math.max(limit,snapshot.usableFloor))
    local debit=0
    if snapshot.classKind=="dual" then
        if not uint(snapshot.retiredDebit) or not uint(snapshot.retiredNativeXP)
            or snapshot.retiredDebit<snapshot.retiredNativeXP then
            return nil,"Unreconciled retired-class entitlement."
        end
        debit=snapshot.retiredDebit
    elseif snapshot.classKind~="single" and snapshot.classKind~="multi" then
        return nil,"Unsupported class accounting."
    end
    return math.min(derivedXP,math.max(0,limit-debit))
end

function M.BeforeNativeClamp(sprite,nativeCap)
    local ok,why=pcall(function()
        local before=sprite.m_derivedStats.m_nXP
        local snapshot=M.snapshot(sprite,nativeCap)
        local target,reason=M.Select(snapshot,nativeCap,before)
        assert(target~=nil,reason)
        -- Only this field is owned. No raw base-XP or bank transaction occurs.
        sprite.m_derivedStats.m_nXP=target
    end)
    if not ok then
        if #M.errors==64 then table.remove(M.errors,1) end
        M.errors[#M.errors+1]=tostring(why)
        if M.report then pcall(M.report,tostring(why)) end
    end
end

function M.assembly(callbacks)
    assert(type(callbacks)=="table" and type(callbacks.GenLuaCall)=="function","Private callback ABI adapter required")
    return EEex_FlattenTable({{[[
        #MAKE_SHADOW_SPACE(64)
        mov qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-8)], rax
    ]]},callbacks.GenLuaCall("CBMBank_BeforeNativeClamp",{
        args={
            function(offset) return {"mov qword ptr ss:[rsp+#$(1)], rbx",{offset},"#ENDL"},"CGameSprite" end,
            function(offset) return {"mov qword ptr ss:[rsp+#$(1)], rax",{offset},"#ENDL"} end,
        },labelSuffix="_cbmbank_cap",
    }),{[[
        call_error_cbmbank_cap:
        mov rax, qword ptr ss:[rsp+#SHADOW_SPACE_BOTTOM(-8)]
        #DESTROY_SHADOW_SPACE
    ]]}})
end

-- NEW loader label must select only CheckStatsChange's GetXPCap call.
-- Call signature + surrounding instructions guard the actual reviewed ABI.
-- The provider contract is necessary but is not satisfied by this module.
function M.Install(config)
    assert(not M.installed,"cap hook already installed")
    assert(type(config)=="table" and config.researchOnly==true,"explicit uninstalled research configuration required")
    assert(type(config.snapshot)=="function" and type(config.report)=="function","committed snapshot and visible error reporting required")
    assert(type(config.callbacks)=="table" and type(config.callbacks.GenLuaCall)=="function","Private callback ABI adapter required")
    assert(EEex_Active==true,"EEex required")
    for _,name in ipairs({"EEex_TryLabel","EEex_ReadU8","EEex_Read32","EEex_WriteU8",
        "EEex_DisableCodeProtection","EEex_EnableCodeProtection","EEex_HookAfterCall",
        "EEex_FlattenTable","EEex_GenLuaCall"}) do assert(type(_G[name])=="function","Missing capability: "..name) end
    local at=EEex_TryLabel("CBMBank::CheckStatsChangeGetXPCap")
    local target=EEex_TryLabel("CBMBank::GetXPCap")
    assert(type(at)=="number" and type(target)=="number","reviewed loader labels absent")
    assert(EEex_ReadU8(at)==0xE8 and at+5+EEex_Read32(at+1)==target,"unexpected cap call target")
    local function verify(offset,hex)
        for i=1,#hex,2 do assert(EEex_ReadU8(at+offset+(i-1)/2)==tonumber(hex:sub(i,i+1),16),"cap hook ABI mismatch") end
    end
    verify(-6,"488BD6498BCD") -- RDX=RSI AI type; RCX=R13 rule tables
    verify(5,"4C8D442450488BCE488D542451448BF0")
    assert(_G.CBMBank_BeforeNativeClamp==nil,"cap callback already owned")
    local original={}; for i=0,4 do original[i]=EEex_ReadU8(at+i) end
    M.snapshot,M.report=config.snapshot,config.report
    _G.CBMBank_BeforeNativeClamp=M.BeforeNativeClamp
    EEex_DisableCodeProtection()
    local ok,why=pcall(function() EEex_HookAfterCall(at,M.assembly(config.callbacks)) end)
    if not ok then
        for i=0,4 do EEex_WriteU8(at+i,original[i]) end
        _G.CBMBank_BeforeNativeClamp=nil
    end
    EEex_EnableCodeProtection()
    if not ok then error(why) end
    M.installed=true
    return true
end
return M
