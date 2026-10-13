-- Uninstalled concrete EEex adapter. Loading does not register/install anything.
-- Native ordinary base XP stays authoritative; no polling delta is called earned.
-- Copy/import identity and pre-dual transaction hooks must be connected before use.
local R={key="CBMBank", bindingKey="CBMBankLifetime", lastError=nil}
local slots={ [1]={1},[2]={2},[3]={3},[4]={4},[5]={5},[6]={6},
    [7]={2,1},[8]={2,3},[9]={2,4},[10]={2,1,4},[11]={11},[12]={12},
    [13]={1,4},[14]={3,1},[15]={3,4},[16]={2,11},[17]={2,1,3},
    [18]={3,12},[19]={19},[20]={20},[21]={21} }
local oldFlags={{8,2},{16,1},{32,3},{64,4},{128,11},{256,12}}
local classNames={ [1]="MAGE",[2]="FIGHTER",[3]="CLERIC",[4]="THIEF",
    [11]="DRUID",[12]="RANGER" }
local xpLevels
local function uint(n) return type(n)=="number" and n>=0 and n<=4294967295 and n%1==0 end

-- This is the native class/slot contract audited in reader-native-probe.py,
-- not a kit whitelist or guessed allocation from a particular companion.
function R.ClassInfo(sprite)
    local base=sprite.m_baseStats
    local composite=sprite.m_startTypeAI.m_Class
    local selected=slots[composite]
    assert(selected,"Unsupported native class identity")
    assert(uint(base.m_flags),"Invalid native creature flags")
    local old
    for _,entry in ipairs(oldFlags) do
        if math.floor(base.m_flags/entry[1])%2==1 then
            assert(not old,"Ambiguous native original-class flags")
            old=entry[2]
        end
    end
    if not old then return {kind=#selected>1 and "multi" or "single",class=composite} end
    assert(#selected==2,"Original-class flags do not identify a native two-class dual")
    local index=selected[1]==old and 1 or (selected[2]==old and 2 or nil)
    assert(index,"Original class is not part of the native composite")
    local level=index==1 and base.m_level1 or base.m_level2
    assert(type(level)=="number" and level>=1 and level<=255 and level%1==0,"Invalid retired level")
    return {kind="dual",class=composite,oldClass=old,newClass=selected[3-index],oldLevel=level}
end
function R.RetiredThreshold(info)
    if info.kind~="dual" then return nil end
    if not xpLevels then xpLevels=EEex_Resource_Load2DA("XPLEVEL") end
    local value=tonumber(xpLevels:getAtLabels(tostring(info.oldLevel),classNames[info.oldClass]))
    assert(uint(value),"Installed XPLEVEL lacks a valid retired threshold")
    return value
end
function R.CurrentPhase(saved)
    local game=EngineGlobals.g_pBaldurChitin.m_pObjectGame
    local campaign=string.upper(game.m_sCurrentCampaign.m_pchData:get())
    local phase,reason=R.policy.Campaign(campaign,EEex_GameState_GetGlobalInt("ENDOFBG1"),
        EEex_GameState_GetGlobalInt("INTOB"),saved)
    assert(phase,reason); return phase
end
function R.Report(message)
    message=tostring(message)
    if message~=R.lastError then print("[CBM campaign XP] "..message) end
    R.lastError=message
end
function R.Configure(policy,account,wire,choice,receipts)
    assert(type(policy)=="table" and type(policy.Campaign)=="function","Campaign policy module required")
    assert(type(account)=="table" and type(account.Inspect)=="function","Native account module required")
    assert(type(wire)=="table" and type(wire.WireSnapshot)=="function","Marshal wire validator required")
    assert(choice=="bg1_sod" or choice=="bg1_sod_soa","Invalid component choice")
    assert(not R.policy,"Runtime already configured")
    R.policy,R.account,R.wire,R.choice=policy,account,wire,choice
    R.receipts=receipts
end

local function identityOf(sprite)
    assert(type(CBMBank_Identity)=="table" and type(CBMBank_Identity.Query)=="function",
        "Native identity hooks are unavailable")
    local identity,reason=CBMBank_Identity.Query(sprite)
    assert(identity,reason)
    return identity
end
local function detached(payload)
    local result,reason=R.wire.WireSnapshot(payload)
    assert(result,reason); return result
end
local function validateOwned(payload)
    R.account.Validate(payload)
    assert(type(payload.ownerKey)=="string" and #payload.ownerKey==32
        and payload.ownerKey:match("^[0-9a-f]+$"),"Invalid saved bank owner")
end
local function stageNotices(state,view,released,previousPhase)
    local capped=state.phase=="BG1" or state.phase=="SOD" or
        (state.phase=="SOA" and state.policy=="bg1_sod_soa")
    local seen=state.notices and state.notices.seen or {}
    local reachedKey="cap:"..state.phase
    local releaseKey="release:"..tostring(previousPhase)..":"..state.phase
    local reached=capped and view.usable>=view.cap and not seen[reachedKey]
    local release=released and released>0 and not seen[releaseKey]
    if not reached and not release then return state end
    local n=detached(state)
    n.notices=n.notices or {schema=1,seen={},pending={}}
    assert(n.notices.schema==1,"Unsupported bank notice schema")
    local function add(key,message)
        n.notices.seen[key]=true
        n.notices.pending[#n.notices.pending+1]={key=key,text=message}
    end
    if release then add(releaseKey,string.format("Campaign change: %.0f banked XP is now available for level-up.",released)) end
    if reached then add(reachedKey,string.format("Campaign XP limit reached: %.0f. Further XP will be saved for a later campaign.",view.cap)) end
    return detached(n)
end
local function bind(aux,identity,state,origin)
    validateOwned(state)
    aux[R.bindingKey]={incarnation=identity.incarnation,ownerKey=state.ownerKey,origin=origin}
end
local function currentAux(sprite,identity)
    local aux=EEex_GetUDAux(sprite)
    local binding=aux[R.bindingKey]
    if binding and binding.incarnation~=identity.incarnation then
        -- A proved NEW native lifetime at a reused address cannot inherit the
        -- destroyed object's runtime UDAux. This is never done by an exporter.
        aux[R.key],aux[R.bindingKey]=nil,nil
    end
    return aux
end
local function assertBound(aux,identity,state)
    local binding=aux[R.bindingKey]
    assert(binding and binding.incarnation==identity.incarnation
        and binding.ownerKey==state.ownerKey,"Bank is not bound to this native actor lifetime")
    assert(binding.origin~="chr_import","CHR bank requires explicit new-run reconciliation")
end
local function accountFromSeed(seed,info,phase)
    assert(seed.schema==2 and seed.initializing==true and type(seed.info)=="table"
        and seed.info.kind==info.kind and seed.info.class==info.class,
        "Pending adoption no longer matches native class")
    local result
    if info.kind=="dual" then
        assert(seed.info.oldClass==info.oldClass and seed.info.newClass==info.newClass
            and seed.info.oldLevel==info.oldLevel,"Pending retired class changed")
        result=R.account.AdoptExistingDual(seed.policy,phase,seed.baseAtAdoption,
            info.oldClass,info.newClass,info.oldLevel,seed.retiredThreshold)
    else result=R.account.Adopt(seed.policy,phase,seed.baseAtAdoption,info.kind) end
    result.overflow=seed.overflow or 0
    result.revision=seed.revision or 0
    result.ownerKey=seed.ownerKey
    if seed.lastWrite then result.lastWrite=detached(seed.lastWrite) end
    if seed.dualPreview then result.dualPreview=detached(seed.dualPreview) end
    validateOwned(result)
    return result
end

-- Called only by the native identity/adoption path, not from a marshal exporter.
-- A real party-member lookup is required as well as the scoped identity result.
function R.Adopt(sprite)
    assert(R.account,"Runtime is not configured")
    local identity=identityOf(sprite)
    assert(identity.eligible and identity.canMutate and not identity.serializing
        and type(identity.ownerToken)=="string","Real mutable actor identity not established")
    assert(EEex_Sprite_GetCharacterIndex(sprite)>=0,"First adoption requires actual party membership")
    local aux=currentAux(sprite,identity)
    assert(aux[R.key]==nil,"Existing carrier must be imported/reconciled, never replaced by adoption")
    local info=R.ClassInfo(sprite)
    local seed={schema=2,initializing=true,policy=R.choice,ownerKey=identity.ownerToken,
        baseAtAdoption=sprite.m_baseStats.m_xp,info=info,retiredThreshold=R.RetiredThreshold(info),
        overflow=0,revision=0}
    -- Capture the actual first-party baseline even if EET's campaign flags are
    -- not initialized yet. Later awards must not become grandfathered progress.
    accountFromSeed(seed,info,"BG1") -- validate the complete captured baseline
    aux[R.key]=detached(seed)
    aux[R.bindingKey]={incarnation=identity.incarnation,ownerKey=seed.ownerKey,origin="adopted"}
    local known,phase=pcall(R.CurrentPhase)
    if not known then return false,phase end
    local state=accountFromSeed(seed,info,phase)
    bind(aux,identity,state,"adopted")
    aux[R.key]=state
    return true
end

-- The engine calls these from its actual versioned EEex marshal handler. An
-- imported table is preserved even when its schema or semantics are unknown.
-- Validation failure does not erase it or silently turn it into an empty bank.
function R.Import(sprite,payload)
    assert(R.account,"Runtime is not configured")
    if type(payload)=="table" and next(payload)==nil then return end
    local state=detached(payload)
    local ok,identity=pcall(identityOf,sprite)
    local aux=ok and currentAux(sprite,identity) or EEex_GetUDAux(sprite)
    if aux[R.key]~=nil then
        -- Never overwrite either side of an unexplained repeated import.
        aux[R.key]={schema=2,excluded=true,fault="repeated_import",
            carrier=detached(aux[R.key]),incoming=state}
        R.Report("Repeated bank importer needs reconciliation")
        return
    end
    if not ok then
        aux[R.key]={schema=2,excluded=true,fault="unverified_import_lifetime",carrier=state}
        R.Report(identity)
        return
    end
    if identity.birthReason=="chr_import" and state.schema==2 and not state.excluded then
        state.chrPending={newOwner=identity.ownerToken,sourceOwner=state.ownerKey}
    end
    local origin=(identity.birthReason=="chr_import" or state.chrPending) and "chr_import" or "save_load"
    aux[R.key]=state
    aux[R.bindingKey]={incarnation=identity.incarnation,ownerKey=state.ownerKey,
        origin=origin}
    if not identity.eligible or state.excluded or state.initializing then return end
    local ok,reason=pcall(bind,aux,identity,state,origin)
    if not ok then R.Report(reason) end
end
function R.Export(sprite)
    local aux=EEex_GetUDAux(sprite)
    local state=aux[R.key]
    if not state then return {} end
    local ok,identity=pcall(identityOf,sprite)
    if not ok then
        R.Report(identity)
        -- EEex ignores exporter exceptions, which would erase the carrier.
        -- Retain recovery evidence without falsely assigning it to a lifetime.
        return {schema=2,excluded=true,fault="unverified_lifetime",carrier=detached(state)}
    end
    local binding=aux[R.bindingKey]
    if binding and binding.incarnation~=identity.incarnation then return {} end
    if not binding then
        return {schema=2,excluded=true,fault="unbound_carrier",carrier=detached(state)}
    end
    if state.excluded==true then return detached(state) end
    if identity.birthReason=="magical_clone" or identity.birthReason=="preview"
        or identity.birthReason=="other_copy" or identity.reason=="magical_clone"
        or identity.reason=="preview" or identity.reason=="other_copy" then
        if state.schema~=2 then return {schema=2,excluded=true,carrier=detached(state)} end
        return {schema=2,excluded=true}
    end
    -- No adoption, phase advancement, revision, identity or XP mutation here.
    -- In particular, unknown newer schemas survive an ordinary save/export.
    local exported=detached(state)
    if identity.reason=="chr_export" and state.schema==2 and not state.initializing
        and not state.pendingDual and not state.pendingAward and not state.pendingWrite and not state.chrPending
        and not state.pendingManualProgression and not (state.old and state.old.pendingHLADelivery) then
        local success,transfer=pcall(function()
            validateOwned(state)
            local info=R.ClassInfo(sprite)
            assert(info.kind==state.kind,"CHR export class/account mismatch")
            local view=R.account.Inspect(state,sprite.m_baseStats.m_xp,
                CBMBank_Reset.NativeCap(sprite),R.RetiredThreshold(info))
            return {schema=1,base=sprite.m_baseStats.m_xp,usable=view.usable,
                sourceOwner=state.ownerKey}
        end)
        if success then exported.chrTransfer=transfer else R.Report(transfer) end
    end
    return exported
end
function R.ReconcileCHR(sprite)
    local identity=identityOf(sprite)
    assert(identity.eligible and identity.canMutate and not identity.serializing,
        "Cannot reconcile CHR during native serialization/copy")
    assert(EEex_Sprite_GetCharacterIndex(sprite)>=0,"CHR association requires actual party membership")
    local aux=currentAux(sprite,identity)
    local state=aux[R.key]
    validateOwned(state)
    local association=aux[R.bindingKey]
    assert(association and association.incarnation==identity.incarnation
        and association.origin=="chr_import" and association.ownerKey==state.ownerKey,
        "CHR association is not bound to this native lifetime")
    local pending,receipt=state.chrPending,state.chrTransfer
    assert(type(pending)=="table" and type(receipt)=="table" and receipt.schema==1,
        "CHR bank requires a native export entitlement receipt")
    assert(not state.pendingDual and not state.pendingAward and not state.pendingWrite
        and not state.pendingManualProgression and not (state.old and state.old.pendingHLADelivery),
        "CHR contains an incomplete native transaction")
    assert(type(pending.newOwner)=="string" and #pending.newOwner==32
        and pending.newOwner:match("^[0-9a-f]+$") and pending.sourceOwner==state.ownerKey
        and receipt.sourceOwner==state.ownerKey,"CHR owner association is inconsistent")
    assert(uint(receipt.base) and uint(receipt.usable) and sprite.m_baseStats.m_xp==receipt.base,
        "Native CHR import changed XP; separate entitlement reconciliation required")
    local info=R.ClassInfo(sprite)
    assert(info.kind==state.kind and (info.kind~="dual" or
        (info.oldClass==state.old.class and info.newClass==state.old.newClass)),
        "Native CHR import changed class identity")
    local nextState=detached(state)
    nextState.phase=R.CurrentPhase() -- NEW run: never carry the old run's high-water mark
    nextState.floor=receipt.usable -- retain already usable progress, not the bank
    nextState.ownerKey=pending.newOwner
    assert(nextState.revision<9007199254740991,"Account revision exhausted")
    nextState.revision=nextState.revision+1
    nextState.chrPending,nextState.chrTransfer=nil,nil
    if nextState.old and nextState.old.rewardReceipt then
        nextState.old.rewardReceipt.previousOwnerKey=nextState.old.rewardReceipt.ownerKey
        nextState.old.rewardReceipt.ownerKey=nextState.ownerKey
    end
    for _,container in ipairs({nextState,nextState.old and nextState.old.rewardReceipt or {}}) do
        if container.manualLedger then
            assert(container.manualLedger.ownerKey==state.ownerKey,"CHR reward ledger owner differs from its carrier")
            container.manualLedger.previousOwnerKey=container.manualLedger.ownerKey
            container.manualLedger.ownerKey=nextState.ownerKey
        end
    end
    validateOwned(nextState)
    aux[R.key]=nextState
    bind(aux,identity,nextState,"chr_reconciled")
    return true
end
function R.OnLoaded(sprite)
    local identity=identityOf(sprite)
    if not identity.eligible or not identity.canMutate or identity.serializing then return end
    local aux=currentAux(sprite,identity)
    if aux[R.key]==nil and EEex_Sprite_GetCharacterIndex(sprite)>=0 then R.Adopt(sprite) end
    if aux[R.key] and aux[R.key].chrPending and EEex_Sprite_GetCharacterIndex(sprite)>=0 then R.ReconcileCHR(sprite) end
end

-- Called only from the actual permanent positive opcode-104 leaf wrapper. The
-- wrapper has already captured both native pointers, lifetime and pre-award XP.
-- It calls the original exactly once and temporarily narrows only a wrapping
-- positive amount. Other opcode modes and nonowned actors stay native.
local function awardBoundary(sprite,effect,stage,identity)
    assert(type(CBMBank_Award)=="table" and type(CBMBank_Award.Query)=="function",
        "Native XP award binding is unavailable")
    local boundary=CBMBank_Award.Query(sprite,effect)
    assert(boundary and boundary.stage==stage and boundary.incarnation==identity.incarnation,
        "Missing matching native XP award boundary")
    assert(uint(boundary.preBase) and uint(boundary.amount) and boundary.amount>0
        and boundary.amount<=2147483647
        and boundary.applied==math.min(boundary.amount,4294967295-boundary.preBase)
        and boundary.remainder==boundary.amount-boundary.applied,"Invalid native XP award split")
    return boundary
end
function R.BeforeAward(sprite,effect)
    local identity=identityOf(sprite)
    if not identity.eligible then return 2 end
    assert(identity.canMutate and not identity.serializing,"Cannot award banked XP during serialization/copy")
    local aux=currentAux(sprite,identity)
    local state=aux[R.key]
    if type(state)=="table" and state.excluded==true then return 2 end
    if state==nil and EEex_Sprite_GetCharacterIndex(sprite)<0 then return 2 end
    local boundary=awardBoundary(sprite,effect,"preparing",identity)
    assert(sprite.m_baseStats.m_xp==boundary.preBase,"Native XP changed before award preparation")
    if state==nil then R.Adopt(sprite) end -- capture this pre-award baseline only
    R.Snapshot(sprite,CBMBank_Reset.NativeCap(sprite))
    state=aux[R.key]
    assertBound(aux,identity,state)
    assert(not state.pendingAward and not state.pendingDual and not state.pendingWrite,
        "An earlier native XP transaction needs reconciliation")
    local account=state.initializing and accountFromSeed(state,R.ClassInfo(sprite),"BG1") or state
    -- Validate the complete resulting balance and exact storage BEFORE allowing
    -- the native leaf to write anything. No overflow is credited at preparation.
    R.account.CompleteAward(account,boundary.preBase,boundary.amount,boundary.applied,
        boundary.remainder,boundary.preBase+boundary.applied)
    local prepared=detached(state)
    prepared.pendingAward={stage="prepared",incarnation=identity.incarnation,
        ownerKey=state.ownerKey,revision=account.revision,preBase=boundary.preBase,
        amount=boundary.amount,applied=boundary.applied,remainder=boundary.remainder,
        preOverflow=account.overflow}
    aux[R.key]=detached(prepared)
    return 1
end
function R.CompleteAward(sprite,effect)
    local identity=identityOf(sprite)
    assert(identity.eligible and identity.canMutate and not identity.serializing,
        "Cannot finish banked XP award during serialization/copy")
    local boundary=awardBoundary(sprite,effect,"completing",identity)
    local aux=EEex_GetUDAux(sprite)
    local state=aux[R.key]
    assertBound(aux,identity,state)
    local pending=state.pendingAward
    local account=state.initializing and accountFromSeed(state,R.ClassInfo(sprite),"BG1") or state
    assert(pending and pending.stage=="prepared" and pending.incarnation==identity.incarnation
        and pending.ownerKey==state.ownerKey and pending.revision==account.revision
        and pending.preOverflow==account.overflow,"XP completion has no unchanged prepared journal")
    for _,key in ipairs({"preBase","amount","applied","remainder"}) do
        assert(pending[key]==boundary[key],"XP award boundary differs from its prepared journal")
    end
    assert(boundary.nativeResult==1 and boundary.postBase==sprite.m_baseStats.m_xp,
        "Native XP award result is not verified")
    local committed=R.account.CompleteAward(account,boundary.preBase,boundary.amount,
        boundary.applied,boundary.remainder,boundary.postBase)
    if state.initializing then
        local seed=detached(state)
        seed.overflow,seed.revision=committed.overflow,committed.revision
        committed=seed -- preserve the real pre-award adoption floor
    end
    committed.pendingAward=nil
    aux[R.key]=detached(committed)
    return true
end
function R.UncertainAward(sprite,effect)
    local identity=identityOf(sprite)
    local boundary=awardBoundary(sprite,effect,"uncertain",identity)
    local aux=EEex_GetUDAux(sprite)
    local state=aux[R.key]
    assertBound(aux,identity,state)
    assert(state.pendingAward,"Missing XP award recovery journal")
    local retained=detached(state)
    retained.pendingAward.stage="uncertain"
    retained.pendingAward.observedBase=sprite.m_baseStats.m_xp
    retained.pendingAward.nativeResult=boundary.nativeResult
    aux[R.key]=retained
    R.Report("An XP award did not finish normally; its exact amount and bank are retained for reconciliation. Do not replay the award.")
end

local function writeBoundary(sprite,stage,identity)
    assert(type(CBMBank_Writer)=="table" and type(CBMBank_Writer.Query)=="function",
        "Native XP setter binding is unavailable")
    local boundary=CBMBank_Writer.Query(sprite)
    assert(boundary and boundary.stage==stage and boundary.incarnation==identity.incarnation,
        "Missing matching native XP setter boundary")
    assert(uint(boundary.preBase) and uint(boundary.rawValue) and uint(boundary.mode),
        "Invalid native XP setter arguments")
    assert(boundary.source=="stat44" or boundary.source=="opcode104",
        "Native XP writer did not identify its actual source")
    return boundary
end
function R.BeforeWrite(sprite)
    local identity=identityOf(sprite)
    if not identity.eligible then return 2 end
    assert(identity.canMutate and not identity.serializing,"Cannot write banked XP during serialization/copy")
    local aux=currentAux(sprite,identity)
    local state=aux[R.key]
    if type(state)=="table" and state.excluded==true then return 2 end
    if state==nil and EEex_Sprite_GetCharacterIndex(sprite)<0 then return 2 end
    local boundary=writeBoundary(sprite,"preparing",identity)
    assert(sprite.m_baseStats.m_xp==boundary.preBase,"Native XP changed before setter preparation")
    if state==nil then R.Adopt(sprite) end
    local view=R.Snapshot(sprite,CBMBank_Reset.NativeCap(sprite))
    state=aux[R.key]
    assertBound(aux,identity,state)
    assert(not state.pendingAward and not state.pendingDual and not state.pendingWrite,
        "An earlier native XP transaction needs reconciliation")
    local account=state.initializing and accountFromSeed(state,R.ClassInfo(sprite),"BG1") or state
    local after,target,receipt=R.account.PrepareWrite(account,boundary.preBase,
        boundary.rawValue,boundary.mode,boundary.origin,boundary.source,boundary.effectMode)
    if state.initializing then
        local seed=detached(state)
        seed.overflow,seed.revision=after.overflow,after.revision
        after=seed
    end
    -- Keep the last explicit native setter's operands/balances, not an invented
    -- quest origin or a guessed earned delta. Unknown SET is native replacement.
    after.lastWrite=receipt
    after.lastWrite.replacedBank=view.activeBank>0 and receipt.activeAfter<receipt.activeBefore
    local prepared=detached(state)
    prepared.pendingWrite={stage="prepared",incarnation=identity.incarnation,
        ownerKey=state.ownerKey,revision=account.revision,preOverflow=account.overflow,
        preBase=boundary.preBase,rawValue=boundary.rawValue,mode=boundary.mode,
        origin=boundary.origin,source=boundary.source,effectMode=boundary.effectMode,
        plannedBase=target,after=after}
    aux[R.key]=detached(prepared)
    assert(CBMBank_Writer.Plan(sprite,target),"Native XP setter refused its prepared plan")
    return 1
end
function R.CompleteWrite(sprite)
    local identity=identityOf(sprite)
    assert(identity.eligible and identity.canMutate and not identity.serializing,
        "Cannot finish banked XP setter during serialization/copy")
    local boundary=writeBoundary(sprite,"completing",identity)
    local aux=EEex_GetUDAux(sprite)
    local state=aux[R.key]
    assertBound(aux,identity,state)
    local pending=state.pendingWrite
    local account=state.initializing and accountFromSeed(state,R.ClassInfo(sprite),"BG1") or state
    assert(pending and pending.stage=="prepared" and pending.incarnation==identity.incarnation
        and pending.ownerKey==state.ownerKey and pending.revision==account.revision
        and pending.preOverflow==account.overflow,"XP setter completion has no unchanged prepared journal")
    for _,key in ipairs({"preBase","rawValue","mode","origin","source","effectMode","plannedBase"}) do
        assert(pending[key]==boundary[key],"XP setter differs from its prepared journal")
    end
    assert(boundary.source~="opcode104" or boundary.nativeResult==1,
        "Native XP effect did not complete successfully")
    assert(boundary.postBase==pending.plannedBase and sprite.m_baseStats.m_xp==pending.plannedBase,
        "Native XP setter did not store the prepared result")
    local committed=detached(pending.after)
    aux[R.key]=committed
    if committed.lastWrite.classification=="unclassified_absolute_set"
        and committed.lastWrite.replacedBank then
        R.Report("An external XP SET replaced retained active XP. Its before/after amounts are saved; its purpose is unknown. Owned recruitment uses a separate catch-up path.")
    end
    return true
end
function R.UncertainWrite(sprite)
    local identity=identityOf(sprite)
    local boundary=writeBoundary(sprite,"uncertain",identity)
    local aux=EEex_GetUDAux(sprite)
    local state=aux[R.key]
    assertBound(aux,identity,state)
    assert(state.pendingWrite,"Missing XP setter recovery journal")
    local retained=detached(state)
    retained.pendingWrite.stage="uncertain"
    retained.pendingWrite.observedBase=sprite.m_baseStats.m_xp
    retained.pendingWrite.nativePostBase=boundary.postBase
    aux[R.key]=retained
    R.Report("An XP setter did not finish normally; its previous balance and requested result are retained for reconciliation.")
end

-- Explicit adapters for the independently authored recruitment policies. These
-- calls use a real native RAII writer scope, never a caller-supplied snapshot.
function R.ActiveTotal(sprite)
    local view=R.Snapshot(sprite,CBMBank_Reset.NativeCap(sprite))
    if not view.eligible then return sprite.m_baseStats.m_xp end
    return view.activeUsable+view.activeBank
end
function R.OwnedSet(sprite,target,origin)
    assert(uint(target),"Invalid owned XP target")
    assert(origin==1 or origin==2,"Unknown owned XP setter policy")
    local before=R.ActiveTotal(sprite)
    local expected=origin==2 and math.max(before,target) or target
    if origin==2 and before>=target then return true end
    assert(CBMBank_Writer.ApplyOwnedSet(sprite,target,origin),"Native owned XP setter failed")
    local actual=R.ActiveTotal(sprite) -- also rejects any unresolved native journal
    local state=EEex_GetUDAux(sprite)[R.key]
    if state and not state.excluded then
        -- The native setter recalculates effects AFTER its write transaction.
        -- Legitimate effects may award more XP there; confirm our write receipt,
        -- not equality with the final balance after those independent awards.
        assert(state.lastWrite and state.lastWrite.activeAfter==expected
            and state.lastWrite.classification==(origin==2 and "recruitment_catchup" or "party_average_set"),
            "Owned XP setter did not publish its complete balance")
    else assert(actual==expected,"Unowned native XP setter did not store its target") end
    return true
end

-- Both native dual UI paths start here before new-class spell/proficiency
-- choices can modify the actor. The reset-time aggregate is already too late
-- to be the old class's baseline, even though XP has not yet been cleared.
function R.CaptureDualPreview(sprite)
    local identity=identityOf(sprite)
    assert(identity.eligible and identity.canMutate and not identity.serializing,
        "Cannot capture dual preview during serialization/copy")
    local boundary=CBMBank_Reset.PreviewQuery(sprite)
    assert(boundary and boundary.stage=="capturing" and boundary.incarnation==identity.incarnation
        and boundary.preBase==sprite.m_baseStats.m_xp,"Missing native pre-preview boundary")
    R.Snapshot(sprite,CBMBank_Reset.NativeCap(sprite))
    local aux=EEex_GetUDAux(sprite)
    local state=aux[R.key]
    assertBound(aux,identity,state)
    assert(not state.initializing and not state.pendingDual and not state.pendingAward and not state.pendingWrite,
        "An XP transaction or campaign initialization must finish before dual preview")
    local info=R.ClassInfo(sprite)
    assert(info.kind=="single","Native dual preview source must be single-class")
    assert(type(R.receipts)=="table" and type(R.receipts.CaptureBeforePreview)=="function",
        "Clean pre-preview reward capture is unavailable")
    local receipt=R.receipts.CaptureBeforePreview(sprite,{ownerKey=state.ownerKey,
        incarnation=identity.incarnation,revision=state.revision,oldClass=info.class})
    local previous=state.dualPreview
    if previous then
        assert(previous.captureBoundary=="before_dual_preview" and previous.ownerKey==state.ownerKey
            and type(previous.before)=="table","Unrecognized previous dual preview")
        -- Reopening the native dual UI is not proof that it restored every
        -- field. Preserve earliest and latest evidence separately. Neither is
        -- an authoritative allocation: derived pips include equipment/effects,
        -- and legitimate same-level changes to HP/skills/kit may have occurred.
        -- Aggregate equality would reject those ordinary changes, not prove
        -- class ownership. Deferred reward code must apply its owned increments
        -- to the current actor; these snapshots are never replay recipes.
        if previous.oldClass==info.class and previous.oldLevelAtDual==receipt.oldLevelAtDual then
            local latest=receipt.before
            receipt=detached(previous)
            receipt.firstPreviewBaseXP=receipt.firstPreviewBaseXP or receipt.before.baseXP
            receipt.latestBeforePreview=latest
            receipt.incarnation=identity.incarnation
            receipt.ledgerRevision=state.revision
            receipt.before.baseXP=boundary.preBase
        end
    end
    local nextState=detached(state)
    nextState.dualPreview=receipt
    aux[R.key]=detached(nextState)
    return true
end

-- Called by the typed native MakeDualClass wrapper. The journal is saved before
-- original code can clear base XP; a failed/partial native operation keeps both
-- accounts as recovery evidence and is never represented as a successful dual.
function R.PrepareDual(sprite,newClass)
    local identity=identityOf(sprite)
    assert(identity.eligible and identity.canMutate and not identity.serializing,
        "Cannot start dual accounting during serialization/copy")
    assert(type(CBMBank_Reset)=="table" and type(CBMBank_Reset.NativeCap)=="function",
        "Native dual/cap binding is unavailable")
    local boundary=CBMBank_Reset.Query(sprite)
    assert(boundary and boundary.stage=="preparing","Missing native pre-dual boundary")
    local nativeCap=CBMBank_Reset.NativeCap(sprite)
    R.Snapshot(sprite,nativeCap) -- reconcile confirmed phase before freezing it
    local aux=EEex_GetUDAux(sprite)
    local before=aux[R.key]
    assert(not before.pendingDual and not before.pendingAward and not before.pendingWrite,
        "An XP transaction is already unresolved")
    local info=R.ClassInfo(sprite)
    assert(info.kind=="single","Native dual source must be single-class")
    local level=sprite.m_baseStats.m_level1
    local threshold=R.RetiredThreshold({kind="dual",oldClass=info.class,oldLevel=level})
    local after=R.account.PrepareDual(before,sprite.m_baseStats.m_xp,nativeCap,
        info.class,newClass,level,threshold)
    local preview=before.dualPreview
    assert(type(preview)=="table" and preview.captureBoundary=="before_dual_preview"
        and preview.ownerKey==before.ownerKey and preview.incarnation==identity.incarnation
        and preview.ledgerRevision==before.revision and preview.oldClass==info.class
        and preview.oldLevelAtDual==level and preview.before.baseXP==boundary.preBase,
        "Clean old-class reward baseline is missing or stale; reopen the native dual preview")
    after.old.rewardReceipt=detached(preview)
    after.old.rewardReceipt.newClass=newClass
    after.dualPreview=nil
    local prepared=detached(before)
    prepared.pendingDual={stage="prepared",preBase=sprite.m_baseStats.m_xp,
        oldClass=info.class,newClass=newClass,oldLevel=level,threshold=threshold,
        after=after}
    -- Validate the complete wire record before the original native reset can
    -- happen, including the detached pre-reset reward evidence.
    aux[R.key]=detached(prepared)
    return true
end
function R.CompleteDual(sprite,newClass)
    local identity=identityOf(sprite)
    assert(identity.eligible and identity.canMutate and not identity.serializing,
        "Cannot finish dual accounting during serialization/copy")
    local boundary=CBMBank_Reset.Query(sprite)
    assert(boundary and boundary.stage=="completing","Missing native completed-dual boundary")
    local aux=EEex_GetUDAux(sprite)
    local state=aux[R.key]
    validateOwned(state); assertBound(aux,identity,state)
    local pending=state.pendingDual
    assert(pending and pending.stage=="prepared" and pending.newClass==newClass,
        "Dual completion has no matching prepared journal")
    local info=R.ClassInfo(sprite)
    assert(info.kind=="dual" and info.oldClass==pending.oldClass
        and info.newClass==newClass and info.oldLevel==pending.oldLevel,
        "Native dual result differs from the captured class/level")
    assert(uint(sprite.m_baseStats.m_xp),"Native active XP is invalid")
    validateOwned(pending.after)
    aux[R.key]=detached(pending.after)
    return true
end
function R.UncertainDual(sprite)
    local identity=identityOf(sprite)
    local aux=EEex_GetUDAux(sprite)
    local state=aux[R.key]
    assertBound(aux,identity,state)
    assert(state.pendingDual,"Missing dual recovery journal")
    local retained=detached(state)
    retained.pendingDual.stage="uncertain"
    aux[R.key]=retained
    R.Report("Native dual-classing did not finish normally; both XP accounts are retained for reconciliation.")
end

-- Concrete provider for cap_hook.lua. It reads actual EEex fields and installed
-- XPLEVEL, and advances saved metadata on a confirmed campaign transition.
-- This is a cap callback, not an exporter; it never writes base XP or levels.
function R.Snapshot(sprite,nativeCap)
    assert(R.account and uint(nativeCap),"Runtime/cap is unresolved")
    local identity=identityOf(sprite)
    if not identity.eligible then return {eligible=false} end
    local aux=EEex_GetUDAux(sprite)
    local state=aux[R.key]
    if type(state)=="table" and state.excluded==true then return {eligible=false} end
    if state==nil then
        -- Existing unowned enemies/summons are not silently adopted here.
        assert(EEex_Sprite_GetCharacterIndex(sprite)<0,"Party bank has not been initialized before cap check")
        return {eligible=false}
    end
    if state.chrPending then
        R.ReconcileCHR(sprite)
        state=aux[R.key]
    end
    assertBound(aux,identity,state)
    assert(not state.pendingAward and not state.pendingWrite,"Incomplete native XP award/setter needs reconciliation")
    local info=R.ClassInfo(sprite)
    local initializing=false
    if state.initializing then
        local known,phase=pcall(R.CurrentPhase)
        state=accountFromSeed(state,info,known and phase or "BG1")
        if known then
            assert(identity.canMutate and not identity.serializing,"Cannot finish adoption during serialization")
            aux[R.key]=state
        else initializing=true end
    end
    validateOwned(state)
    local inDual=state.pendingDual~=nil
    if inDual then
        local pending=state.pendingDual
        local boundary=type(CBMBank_Reset)=="table" and CBMBank_Reset.Query(sprite)
        assert(pending.stage=="prepared" and boundary
            and (boundary.stage=="native" or boundary.stage=="completing"),
            "Incomplete native dual transaction needs reconciliation")
        if info.kind~="single" or sprite.m_baseStats.m_xp~=pending.preBase then
            -- Native reset has occurred. Never treat the cleared old word as
            -- an XP loss, nor transfer its saved entitlement to the new class.
            state=pending.after
            info={kind="dual",oldClass=pending.oldClass,newClass=pending.newClass,oldLevel=pending.oldLevel}
        end
    end
    assert(info.kind==state.kind,"Native class/account mismatch: reset or respec needs reconciliation")
    if info.kind=="dual" then
        assert(info.oldClass==state.old.class and info.newClass==state.old.newClass,
            "Native dual identity differs from the saved account")
    end
    local phase=initializing and state.phase or R.CurrentPhase(state.phase)
    local nextState=state
    if phase~=state.phase then
        assert(not inDual,"Campaign changed during native dual transaction")
        assert(identity.canMutate and not identity.serializing,"Cannot advance bank during native serialization")
        nextState=R.account.Advance(state,phase,nativeCap)
    end
    local threshold=R.RetiredThreshold(info)
    local view=R.account.Inspect(nextState,sprite.m_baseStats.m_xp,nativeCap,threshold)
    if not initializing and not inDual and identity.canMutate and not identity.serializing then
        local released
        if phase~=state.phase then
            local before=R.account.Inspect(state,sprite.m_baseStats.m_xp,nativeCap,threshold)
            released=view.usable-before.usable
        end
        -- Notices are cosmetic. A newer notice schema or exhausted message
        -- storage must not prevent an otherwise valid XP/campaign operation.
        local ok,noticed=pcall(stageNotices,nextState,view,released,state.phase)
        if ok then nextState=noticed else R.Report("XP notice unavailable; accounting retained: "..tostring(noticed)) end
    end
    -- Fully validate before publishing one replacement metadata reference.
    if nextState~=state then aux[R.key]=nextState end
    return {eligible=true,initializing=initializing,policy=nextState.policy,phase=nextState.phase,
        usableFloor=nextState.floor,classKind=nextState.kind,
        retiredDebit=view.oldUsable,retiredNativeXP=threshold,
        activeUsable=view.activeUsable,activeBank=view.activeBank,oldBank=view.oldBank,
        activeOverflow=nextState.overflow,
        total=view.total,cap=view.cap,ownerKey=nextState.ownerKey}
end
-- Record-screen reads must not adopt/reconcile actors, advance saved metadata,
-- stage notices, or clear stale UDAux. Resolve the current lifetime every time.
function R.RecordView(sprite,nativeCap)
    assert(R.account and uint(nativeCap),"Runtime/cap is unresolved")
    local identity=identityOf(sprite)
    if not identity.eligible or identity.serializing then return nil end
    local aux=EEex_GetUDAux(sprite)
    local state=aux[R.key]
    if state==nil or state.excluded or state.chrPending then return nil end
    assertBound(aux,identity,state)
    if state.initializing or state.pendingDual or state.pendingAward
        or state.pendingWrite or state.pendingManualProgression then return nil end
    validateOwned(state)
    if state.old and state.old.pendingHLADelivery then return nil end
    local info=R.ClassInfo(sprite)
    assert(info.kind==state.kind,"Native class/account mismatch")
    if info.kind=="dual" then
        assert(info.oldClass==state.old.class and info.newClass==state.old.newClass,
            "Native dual identity differs from the saved account")
    end
    local phase=R.CurrentPhase(state.phase)
    -- Advance returns a copy; a record-screen draw never publishes it.
    local projected=phase==state.phase and state or R.account.Advance(state,phase,nativeCap)
    local view=R.account.Inspect(projected,sprite.m_baseStats.m_xp,nativeCap,R.RetiredThreshold(info))
    return {bank=view.bank,cap=view.cap,phase=phase,policy=state.policy}
end
function R.Status(sprite,nativeCap)
    local s=R.Snapshot(sprite,nativeCap)
    if not s.eligible then return "Campaign XP banking is not assigned to this actor." end
    return string.format("Usable XP: %.0f; banked XP: %.0f; cap: %.0f; campaign: %s",
        s.activeUsable+s.retiredDebit,s.activeBank+s.oldBank,s.cap,
        s.initializing and "waiting for campaign initialization" or s.phase)
end
function R.PendingNotices(sprite)
    local identity=identityOf(sprite)
    if not identity.eligible or identity.serializing or not identity.canMutate then return nil end
    local aux=currentAux(sprite,identity)
    local state=aux[R.key]
    if not state or state.excluded or state.initializing or state.chrPending then return nil end
    validateOwned(state);assertBound(aux,identity,state)
    if not state.notices or #state.notices.pending==0 then return nil end
    assert(state.notices.schema==1,"Unsupported bank notice schema")
    return detached({ownerKey=state.ownerKey,incarnation=identity.incarnation,items=state.notices.pending})
end
function R.AckNotice(sprite,ownerKey,incarnation,key)
    local identity=identityOf(sprite)
    if identity.incarnation~=incarnation then return false end
    local view=R.PendingNotices(sprite)
    if not view or view.ownerKey~=ownerKey then return false end
    local aux=EEex_GetUDAux(sprite)
    for i,item in ipairs(view.items)do if item.key==key then
        local n=detached(aux[R.key]);table.remove(n.notices.pending,i)
        aux[R.key]=n;return true
    end end
    return false
end

-- Ownership is separate from native actor eligibility. An ordinary unowned or
-- explicitly excluded actor retains native level-up; a damaged owned carrier
-- must not silently lose its entitlement through that passthrough.
function R.ManualOwnership(sprite)
    local identity=identityOf(sprite)
    if not identity.eligible then return "passthrough" end
    local aux=currentAux(sprite,identity)
    local state=aux[R.key]
    if state==nil or (type(state)=="table" and state.excluded==true) then return "passthrough" end
    assert(identity.canMutate and not identity.serializing,"Cannot level an owned actor during serialization/copy")
    assertBound(aux,identity,state)
    assert(not state.initializing and not state.chrPending,"Owned campaign account is not initialized")
    validateOwned(state)
    assert(not state.pendingDual and not state.pendingAward and not state.pendingWrite
        and not state.pendingManualProgression,"An earlier owned progression transaction needs reconciliation")
    assert(not (state.old and state.old.pendingHLADelivery),"Old HLA delivery needs reconciliation")
    return "owned"
end

-- HLA selection and effect delivery have separate lifetimes. The queue owns
-- complete native descriptors; catalog row indexes are presentation data only.
function R.ConfigureOldHLAs(receipts)
    assert(not R.oldHLAs and type(receipts)=="table" and type(receipts.Pending)=="function",
        "Concrete old HLA receipts required exactly once")
    R.oldHLAs=receipts
end
function R.PendingHLAs(sprite)
    assert(R.oldHLAs,"Old HLA receipts are not configured")
    return R.oldHLAs.Pending(sprite)
end
function R.ManualHLAs(sprite)
    assert(R.oldHLAs,"Old HLA receipts are not configured")
    return R.oldHLAs.Preview(sprite)
end
function R.PrepareOldHLAs(sprite)
    assert(R.oldHLAs,"Old HLA receipts are not configured")
    return R.oldHLAs.Prepare(sprite)
end
function R.CommitOldHLAs(sprite)
    assert(R.oldHLAs,"Old HLA receipts are not configured")
    return R.oldHLAs.Commit(sprite)
end

-- Concrete input to the retired-level controller. Native rule-table bindings
-- resolve the target level; this provider never derives one from a vanilla XP
-- table or changes a class/level/HP value. A saved receipt is historical evidence
-- of this actor's own dual, not permission to replay its aggregate proficiencies.
function R.OldProgression(sprite)
    local ok,result=pcall(function()
        local identity=identityOf(sprite)
        assert(identity.eligible and identity.canMutate and not identity.serializing,
            "Retired progression needs a mutable original actor")
        local view=R.Snapshot(sprite,CBMBank_Reset.NativeCap(sprite))
        assert(view.eligible and not view.initializing,"Campaign banking is not initialized for this actor")
        local info=R.ClassInfo(sprite)
        assert(info.kind=="dual","This actor has no retired class")
        local aux=EEex_GetUDAux(sprite)
        local state=aux[R.key]
        assertBound(aux,identity,state)
        assert(not state.pendingDual and not state.pendingAward and not state.pendingWrite
            and not state.pendingManualProgression,"An earlier native progression transaction must finish first")
        local old=state.old
        assert(not old.pendingHLADelivery,"Old HLA delivery needs reconciliation")
        assert(old.class==info.oldClass and old.newClass==info.newClass
            and uint(old.usable) and uint(view.activeUsable),"Retired progression entitlement is not native-representable")
        local evidence=old.rewardReceipt
        local clean=type(evidence)=="table" and evidence.schema==1
            and evidence.captureBoundary=="before_dual_preview"
            and evidence.ownerKey==state.ownerKey and evidence.oldClass==old.class
            and evidence.newClass==old.newClass and type(evidence.before)=="table"
        local captured=clean and (evidence.latestBeforePreview or evidence.before)
        local kit=captured and captured.kit or
            sprite.m_baseStats.m_mageSpecUpperWord*65536+sprite.m_baseStats.m_mageSpecialization
        assert(uint(kit),"Retired kit identity is invalid")
        return detached({ownerKey=state.ownerKey,revision=state.revision,
            incarnation=identity.incarnation,oldClass=old.class,activeClass=info.newClass,oldKit=kit,
            oldLevel=info.oldLevel,oldUsableXP=old.usable,
            activeUsableXP=view.activeUsable,hasCleanReceipt=clean})
    end)
    if not ok then return nil,tostring(result) end
    return result
end
function R.ResetResourceCache() xpLevels=nil end
function R.Register()
    assert(R.account and not R.registered,"Runtime must be configured exactly once")
    assert(CBMBank_Identity and CBMBank_Identity.installed,"Native identity hooks required before actor loading")
    assert(type(EEex_Sprite_AddMarshalHandlers)=="function" and type(EEex_Sprite_AddLoadedListener)=="function",
        "EEex marshal and loaded-listener APIs are required")
    assert(EEex_Sprite_Private_MarshalHandlers[R.key]==nil,"Bank marshal handler already owned")
    EEex_Sprite_AddMarshalHandlers(R.key,R.Export,R.Import)
    EEex_Sprite_AddLoadedListener(function(sprite)
        local ok,why=pcall(R.OnLoaded,sprite)
        if not ok then R.Report(why) end
    end)
    R.registered=true
end
return R
