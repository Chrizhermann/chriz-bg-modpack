"""Native-field adapter contract; no game/save access or native acceptance.

Uses the real policy/account/runtime/cap modules with EEex-shaped fixtures.
Actual EEex serialization and compiled lifetime/reset bindings are checked by
the independent identity/native harnesses, not claimed by these fixtures.
"""
from importlib import import_module
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1] / "research"


@pytest.fixture(params=["lua51", "luajit21"])
def runtime(request):
    lua = import_module("lupa." + request.param).LuaRuntime(unpack_returned_tuples=True)
    for name, source in {
        "policy": "xp-banking/cbmbank_policy.lua", "account": "xp-banking/native_account.lua",
        "wire": "xp-banking/cbmbank_store.lua", "R": "xp-banking-native/bank_runtime.lua",
        "cap": "xp-banking-native/cap_hook.lua",
        "receipts": "xp-banking-native/dual_reward_receipts.lua",
    }.items():
        lua.globals()[name] = lua.execute((ROOT / source).read_text(encoding="utf-8"))
    lua.execute('''
        phase='BG1'; ending=0; intoB=0
        local game={m_sCurrentCampaign={m_pchData={get=function() return phase end}}}
        EngineGlobals={g_pBaldurChitin={m_pObjectGame=game}}
        function EEex_GameState_GetGlobalInt(key) return key=='ENDOFBG1' and ending or intoB end
        function EEex_GetUDAux(actor) return actor.aux end
        function EEex_Sprite_GetCharacterIndex(actor) return actor.party and 0 or -1 end
        CBMBank_Identity={Query=function(actor) return actor.identity end,
            -- As CBMI_LuaAckReplaced: clears the note only for the lifetime that saw it.
            AckReplaced=function(actor,incarnation)
                local cleared=actor.identity.incarnation==incarnation
                if cleared then actor.identity.nativeReplaced=false;actor.acks=(actor.acks or 0)+1 end
                return cleared
            end}
        levels={FIGHTER={['7']=64000,['10']=500000,['11']=750000},THIEF={['7']=40000}}
        function EEex_Resource_Load2DA(name)
            assert(name=='XPLEVEL')
            return {getAtLabels=function(_,column,row) return levels[row][column] end}
        end
        resetStage='preparing'
        CBMBank_Reset={Query=function(a) return {stage=resetStage,incarnation=a.identity.incarnation,
                preBase=a.m_baseStats.m_xp,newClass=4} end,
            PreviewQuery=function(a) return {stage='capturing',incarnation=a.identity.incarnation,
                preBase=a.m_baseStats.m_xp} end,
            NativeCap=function() return 8000000 end}
        CBMBank_Award={Query=function(a,e)
            if e.actor~=a then return nil end
            return e.boundary
        end}
        function award(a,amount)
            local before=a.m_baseStats.m_xp
            local applied=math.min(amount,4294967295-before)
            return {actor=a,boundary={stage='preparing',incarnation=a.identity.incarnation,
                preBase=before,amount=amount,applied=applied,remainder=amount-applied,
                nativeResult=0,postBase=before}}
        end
        function finishAward(a,e)
            -- Fixture of the separately audited leaf; NOT native execution.
            a.m_baseStats.m_xp=e.boundary.preBase+e.boundary.applied
            e.boundary.postBase=a.m_baseStats.m_xp
            e.boundary.nativeResult=1;e.boundary.stage='completing'
            return R.CompleteAward(a,e)
        end
        CBMBank_Writer={Query=function(a) return a.writeBoundary end,
            Plan=function(a,target)
                assert(a.writeBoundary.stage=='preparing' and a.writeBoundary.plannedBase==nil)
                a.writeBoundary.plannedBase=target;return true
            end}
        function writeXP(a,value,mode,origin)
            a.writeBoundary={stage='preparing',incarnation=a.identity.incarnation,
                preBase=a.m_baseStats.m_xp,rawValue=value,mode=mode,
                origin=origin or 'unclassified',source='stat44',postBase=a.m_baseStats.m_xp}
            return R.BeforeWrite(a)
        end
        function finishWrite(a)
            local b=a.writeBoundary
            a.m_baseStats.m_xp=b.plannedBase;b.postBase=b.plannedBase;b.stage='completing'
            return R.CompleteWrite(a)
        end
        CBMBank_Writer.ApplyOwnedSet=function(a,target,origin)
            assert(writeXP(a,target,0,origin==1 and 'party_average_set' or 'recruitment_catchup')==1)
            return finishWrite(a)
        end
        function EEex_UDToPtr(value) return value.pointer end
        function EEex_Sprite_GetActiveStats(a) return a.m_derivedStats end
        function actor(base,class,flags,level)
            local a={party=true,aux={},m_baseStats={m_xp=base,m_flags=flags or 0,
                    m_level1=level or 1,m_level2=1},m_startTypeAI={m_Class=class or 2},
                m_derivedStats={m_nXP=base,unrelated=123,GetAtOffset=function() return 0 end},
                m_timedEffectList={},m_equipedEffectList={},
                identity={eligible=true,canMutate=true,serializing=false,reason='world',birthReason='world',
                    incarnation='1',ownerToken=string.rep('a',32)}}
            for _,field in ipairs({'m_mageSpecUpperWord','m_mageSpecialization','m_level3','m_maxHitPointsBase',
                'm_hideInShadowsBase','m_detectIllusionBase','m_setTrapsBase','m_lockPickingBase',
                'm_moveSilentlyBase','m_trapsBase','m_pickPocketBase'}) do a.m_baseStats[field]=0 end
            a.m_baseStats.m_proficiencies={}; for i=0,14 do a.m_baseStats.m_proficiencies[i]=0 end
            return a
        end
        R.Configure(policy,account,wire,'bg1_sod',receipts)
        cap.snapshot=R.Snapshot; cap.report=R.Report
    ''')
    return lua


def test_one_native_xp_copy_cap_transition_and_saved_policy(runtime):
    runtime.execute('''
        local a=actor(1000); R.OnLoaded(a)
        a.m_baseStats.m_xp=600000; a.m_derivedStats.m_nXP=600000
        cap.BeforeNativeClamp(a,8000000)
        assert(a.m_derivedStats.m_nXP==161000 and a.m_baseStats.m_xp==600000)
        local view=R.Snapshot(a,8000000)
        assert(view.total==600000 and view.activeBank==439000)
        phase='SOD'; ending=1
        view=R.Snapshot(a,8000000)
        assert(view.activeUsable==500000 and view.activeBank==100000)
        local revision=a.aux.CBMBank.revision
        R.Snapshot(a,8000000); assert(a.aux.CBMBank.revision==revision)
        phase='SOA'; ending=2
        view=R.Snapshot(a,550000)
        assert(view.activeUsable==550000 and view.activeBank==50000)
        view=R.Snapshot(a,8000000)
        assert(view.activeUsable==600000 and view.activeBank==0)
        assert(a.m_baseStats.m_xp==600000 and a.m_derivedStats.unrelated==123)
        assert(a.aux.CBMBank.usable==nil and a.aux.CBMBank.bank==nil)
    ''')


def test_saved_cap_and_release_notices_do_not_repeat_or_award_xp(runtime):
    runtime.execute('''
        local a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=600000
        R.Snapshot(a,8000000)
        local q=R.PendingNotices(a);assert(#q.items==1 and q.items[1].key=='cap:BG1')
        local saved=R.Export(a);R.Snapshot(a,8000000);assert(#R.PendingNotices(a).items==1)
        assert(not R.AckNotice(a,q.ownerKey,'wrong',q.items[1].key))
        assert(R.AckNotice(a,q.ownerKey,q.incarnation,q.items[1].key))
        assert(not R.AckNotice(a,q.ownerKey,q.incarnation,q.items[1].key))
        R.Snapshot(a,8000000);assert(R.PendingNotices(a)==nil)
        phase='SOD';ending=1;R.Snapshot(a,8000000)
        local transition=R.PendingNotices(a)
        assert(#transition.items==2 and transition.items[1].key=='release:BG1:SOD')
        assert(transition.items[1].text:find('339000')and transition.items[2].key=='cap:SOD')
        R.Snapshot(a,8000000);assert(#R.PendingNotices(a).items==2)
        assert(a.m_baseStats.m_xp==600000 and a.aux.CBMBank.revision==1)
        -- A previous save has its own undelivered receipt and campaign state.
        local earlier=actor(600000);earlier.identity.incarnation='3';R.Import(earlier,saved)
        assert(R.PendingNotices(earlier).items[1].key=='cap:BG1')
    ''')


def test_notice_failure_or_serialization_does_not_change_accounting(runtime):
    runtime.execute('''
        local a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=600000
        a.identity.serializing=true;a.identity.canMutate=false
        assert(R.Snapshot(a,8000000).activeBank==439000 and a.aux.CBMBank.notices==nil)
        a.identity.serializing=false;a.identity.canMutate=true
        a.aux.CBMBank.notices={schema=99,opaque='preserved'}
        assert(R.Snapshot(a,8000000).activeBank==439000)
        phase='SOD';ending=1
        assert(R.Snapshot(a,8000000).activeBank==100000)
        assert(a.m_baseStats.m_xp==600000 and a.aux.CBMBank.notices.opaque=='preserved')
    ''')


def test_immediate_dual_keeps_old_and_new_awards_separate(runtime):
    runtime.execute('''
        phase='SOD'; ending=1
        local a=actor(500000,2,0,10); R.Adopt(a)
        a.m_baseStats.m_xp=550000
        assert(R.CaptureDualPreview(a));assert(R.PrepareDual(a,4))
        local saved=R.Export(a)
        assert(saved.pendingDual.after.old.total==550000 and saved.pendingDual.preBase==550000)
        resetStage='native'
        a.m_baseStats.m_xp=0 -- model the audited native reset, not an engine test
        a.m_startTypeAI.m_Class=9; a.m_baseStats.m_flags=8
        assert(R.Snapshot(a,8000000).activeUsable==0)
        resetStage='completing'; assert(R.CompleteDual(a,4))
        a.m_baseStats.m_xp=200000
        local view=R.Snapshot(a,8000000)
        assert(view.total==750000 and view.oldBank==50000 and view.activeBank==200000)
        assert(view.activeUsable==0 and view.retiredDebit==500000)
        phase='SOA'; ending=2
        view=R.Snapshot(a,8000000)
        assert(view.total==750000 and view.oldBank==0 and view.activeBank==0)
        assert(view.retiredDebit==550000 and view.activeUsable==200000)
        assert(a.m_baseStats.m_level1==10 and a.m_baseStats.m_level2==1)
        assert(a.m_baseStats.m_xp==200000 and a.aux.CBMBank.pendingDual==nil)
    ''')


def test_native_exception_retains_both_accounts_without_fake_rollback(runtime):
    runtime.execute('''
        phase='SOD'; ending=1
        local a=actor(500000,2,0,10); R.Adopt(a); a.m_baseStats.m_xp=550000
        R.CaptureDualPreview(a);R.PrepareDual(a,4); a.m_baseStats.m_xp=0
        resetStage='uncertain'; R.UncertainDual(a)
        local ok,why=pcall(R.Snapshot,a,8000000)
        assert(not ok and tostring(why):find('reconciliation'))
        local saved=R.Export(a)
        assert(saved.pendingDual.after.old.total==550000 and saved.pendingDual.stage=='uncertain')
        assert(a.m_baseStats.m_xp==0) -- no invented reversal or duplicate credit
    ''')


@pytest.mark.parametrize('threshold', [64000, 60000])
def test_zero_bank_dual_discards_progress_and_round_trips(runtime, threshold):
    runtime.globals().threshold = threshold
    runtime.execute('''
        levels.FIGHTER['7']=threshold -- installed progression, including a modded table
        local a=actor(80000,2,0,7); R.Adopt(a)
        a.aux.CBMBank.extension={unrelated='keep'}
        a.m_baseStats.m_maxHitPointsBase=83;a.m_baseStats.m_proficiencies[0]=3
        local tail={pointer=2,data={m_effectId=17,foreign='hp'}}
        local head={pointer=1,data={m_effectId=142,foreign='icon'},pNext=tail}
        if threshold==60000 then head.pNext=nil;tail.pNext=head;head,tail=tail,head end
        a.m_timedEffectList.m_pNodeHead=head
        assert(R.CaptureDualPreview(a));assert(R.PrepareDual(a,4))
        local pending=R.Export(a).pendingDual
        assert(pending.preBase==80000 and pending.threshold==threshold)
        assert(pending.after.old.total==threshold and pending.after.old.usable==threshold)
        assert(pending.after.old.preUsable==threshold and pending.after.old.preBank==0)
        assert(pending.after.old.rewardReceipt.before.baseXP==80000)
        assert(a.m_baseStats.m_xp==80000) -- accounting never performs the native reset
        resetStage='native';a.m_baseStats.m_xp=0
        a.m_startTypeAI.m_Class=9;a.m_baseStats.m_flags=8
        assert(R.Snapshot(a,8000000).total==threshold)
        resetStage='completing';assert(R.CompleteDual(a,4))
        local empty=R.Snapshot(a,8000000)
        assert(empty.activeUsable==0 and empty.activeBank==0 and empty.oldBank==0)
        local gain=award(a,100000);assert(R.BeforeAward(a,gain));assert(finishAward(a,gain))
        local view=R.Snapshot(a,8000000)
        local usable=math.min(100000,161000-threshold)
        assert(view.retiredDebit==threshold and view.activeUsable==usable)
        assert(view.activeBank==100000-usable and view.oldBank==0)
        assert(view.total==threshold+100000 and view.total+(80000-threshold)==180000)
        a.m_derivedStats.m_nXP=100000;cap.BeforeNativeClamp(a,8000000)
        assert(a.m_derivedStats.m_nXP==usable and a.m_derivedStats.unrelated==123)
        assert(a.m_baseStats.m_maxHitPointsBase==83 and a.m_baseStats.m_proficiencies[0]==3)
        assert(a.m_baseStats.m_level1==7 and a.m_baseStats.m_level2==1)
        assert(a.m_timedEffectList.m_pNodeHead==head and head.pNext==tail)
        assert(head.data.foreign==(threshold==60000 and 'hp' or 'icon'))
        assert(tail.data.foreign==(threshold==60000 and 'icon' or 'hp'))
        local saved=R.Export(a)
        assert(saved.extension.unrelated=='keep' and saved.pendingDual==nil)
        assert(saved.old.rewardReceipt.before.maxHPBase==83)
        assert(saved.old.rewardReceipt.before.legacyProficiencies[1]==3)
        local restored=actor(100000,9,8,7);restored.identity.incarnation='2'
        restored.identity.ownerToken=string.rep('b',32)
        R.Import(restored,saved)
        for _,field in ipairs({'total','activeUsable','activeBank','oldBank','retiredDebit','ownerKey'}) do
            assert(R.Snapshot(restored,8000000)[field]==view[field],field)
        end
        assert(restored.aux.CBMBank.old.rewardReceipt.before.baseXP==80000)
        assert(restored.aux.CBMBank.extension.unrelated=='keep')
        local progression=R.OldProgression(restored)
        assert(progression.oldUsableXP==threshold and progression.oldLevel==7)
        assert(progression.hasCleanReceipt and progression.ownerKey==saved.ownerKey)
        local revision=restored.aux.CBMBank.revision
        R.Snapshot(restored,8000000);assert(restored.aux.CBMBank.revision==revision)
        assert(not pcall(R.CompleteDual,restored,4)) -- no journal replay
        -- An already-dual save adopts only the same native threshold, without invented history.
        local adopted=actor(0,9,8,7);R.Adopt(adopted);adopted.m_baseStats.m_xp=100000
        local historical=R.Snapshot(adopted,8000000)
        assert(historical.total==view.total and historical.activeUsable==view.activeUsable)
        assert(adopted.aux.CBMBank.history=='native_threshold')
    ''')


@pytest.mark.parametrize('policy', ['bg1_sod', 'bg1_sod_soa'])
@pytest.mark.parametrize('dual_phase', ['BG1', 'SOD', 'SOA'])
def test_zero_bank_dual_in_each_campaign_keeps_discarded_xp_discarded(runtime, policy, dual_phase):
    runtime.globals().testPolicy = policy
    runtime.globals().dualPhase = dual_phase
    runtime.execute('''
        R.choice=testPolicy;phase=dualPhase;ending=phase=='BG1' and 0 or phase=='SOD' and 1 or 2
        local a=actor(80000,2,0,7);R.Adopt(a)
        assert(R.CaptureDualPreview(a));assert(R.PrepareDual(a,4))
        a.m_baseStats.m_xp=0;a.m_startTypeAI.m_Class=9;a.m_baseStats.m_flags=8
        resetStage='completing';assert(R.CompleteDual(a,4))
        local e=award(a,4000000);assert(R.BeforeAward(a,e));assert(finishAward(a,e))
        local started=false
        for _,nextPhase in ipairs({'BG1','SOD','SOA','TOB'}) do
            if nextPhase==dualPhase then started=true end
            if started then
                phase=nextPhase;ending=phase=='BG1' and 0 or phase=='SOD' and 1 or 2
                intoB=phase=='TOB' and 1 or 0
                local limit=phase=='BG1' and 161000 or phase=='SOD' and 500000
                    or (phase=='SOA' and testPolicy=='bg1_sod_soa') and 2950000 or 8000000
                local view=R.Snapshot(a,8000000)
                local usable=math.min(4000000,limit-64000)
                assert(view.cap==limit and view.retiredDebit==64000 and view.oldBank==0)
                assert(view.activeUsable==usable and view.activeBank==4000000-usable)
                assert(view.total==4064000 and a.aux.CBMBank.old.total==64000)
                a.m_derivedStats.m_nXP=4000000;cap.BeforeNativeClamp(a,8000000)
                assert(a.m_derivedStats.m_nXP==usable and a.m_baseStats.m_xp==4000000)
                local restored=actor(4000000,9,8,7);restored.identity.incarnation=nextPhase
                R.Import(restored,R.Export(a));a=restored
                assert(R.Snapshot(a,8000000).activeUsable==usable)
            end
        end
        assert(phase=='TOB')
    ''')


@pytest.mark.parametrize('bank', [0, 1, 50000])
def test_bank_presence_selects_vanilla_threshold_or_exact_baseline(runtime, bank):
    runtime.globals().bank = bank
    runtime.execute('''
        -- A retained native cap permits a direct zero/one-XP boundary comparison.
        CBMBank_Reset.NativeCap=function() return 80000 end
        local a=actor(80000,2,0,7);R.Adopt(a);a.m_baseStats.m_xp=80000+bank
        assert(R.Snapshot(a,80000).activeBank==bank)
        assert(R.CaptureDualPreview(a));assert(R.PrepareDual(a,4))
        a.m_baseStats.m_xp=0;a.m_startTypeAI.m_Class=9;a.m_baseStats.m_flags=8
        resetStage='completing';assert(R.CompleteDual(a,4))
        local old=a.aux.CBMBank.old
        local debit=bank>0 and 80000 or 64000
        assert(old.preUsable==debit and old.usable==debit and old.total==debit+bank)
        assert(old.preBank==bank and old.rewardReceipt.before.baseXP==80000+bank)
        local e=award(a,100000);assert(R.BeforeAward(a,e));assert(finishAward(a,e))
        local view=R.Snapshot(a,80000)
        assert(view.retiredDebit==debit and view.activeUsable==80000-debit)
        assert(view.oldBank==bank and view.total==debit+bank+100000)
    ''')


@pytest.mark.parametrize('problem,reason', [
    ('missing_preview', 'baseline'), ('stale_preview', 'stale'),
    ('wrong_owner', 'lifetime'), ('serializing', 'serialization'),
    ('missing_threshold', 'XPLEVEL'), ('invalid_threshold', 'XPLEVEL'),
    ('unearned_threshold', 'exceeds usable'),
])
def test_unbanked_dual_still_requires_valid_identity_receipt_and_threshold(runtime, problem, reason):
    runtime.globals().problem = problem
    runtime.globals().reason = reason
    runtime.execute('''
        local a=actor(80000,2,0,7);R.Adopt(a)
        if problem~='missing_preview' then assert(R.CaptureDualPreview(a)) end
        if problem=='stale_preview' then a.m_baseStats.m_xp=80001
        elseif problem=='wrong_owner' then a.aux.CBMBankLifetime.ownerKey=string.rep('b',32)
        elseif problem=='serializing' then a.identity.serializing=true
        elseif problem=='missing_threshold' then levels.FIGHTER['7']=nil
        elseif problem=='invalid_threshold' then levels.FIGHTER['7']=-1
        elseif problem=='unearned_threshold' then levels.FIGHTER['7']=80001 end
        local before=a.m_baseStats.m_xp
        local ok,why=pcall(R.PrepareDual,a,4)
        assert(not ok and tostring(why):find(reason),tostring(why))
        assert(a.m_baseStats.m_xp==before and a.aux.CBMBank.kind=='single')
        assert(a.aux.CBMBank.pendingDual==nil)
    ''')


def test_unbanked_partial_native_dual_retains_recovery_evidence_on_reload(runtime):
    runtime.execute('''
        local a=actor(80000,2,0,7);R.Adopt(a)
        assert(R.CaptureDualPreview(a));assert(R.PrepareDual(a,4))
        a.m_baseStats.m_xp=0;resetStage='uncertain';R.UncertainDual(a)
        local b=actor(0);b.identity.incarnation='2';R.Import(b,R.Export(a))
        local pending=R.Export(b).pendingDual
        assert(pending.stage=='uncertain' and pending.preBase==80000)
        assert(pending.after.old.total==64000 and pending.after.old.rewardReceipt.before.baseXP==80000)
        local ok,why=pcall(R.Snapshot,b,8000000)
        assert(not ok and tostring(why):find('reconciliation'))
        assert(b.m_baseStats.m_xp==0)
    ''')


def test_unbanked_dual_preserves_existing_save_adoption_floor(runtime):
    runtime.execute('''
        local a=actor(550000,2,0,10);R.Adopt(a)
        assert(R.Snapshot(a,8000000).activeBank==0)
        assert(R.CaptureDualPreview(a));assert(R.PrepareDual(a,4))
        a.m_baseStats.m_xp=0;a.m_startTypeAI.m_Class=9;a.m_baseStats.m_flags=8
        resetStage='completing';assert(R.CompleteDual(a,4))
        local view=R.Snapshot(a,8000000)
        assert(view.cap==550000 and view.retiredDebit==500000 and view.total==500000)
        assert(view.activeUsable==0 and a.aux.CBMBank.floor==550000)
        local e=award(a,60000);assert(R.BeforeAward(a,e));assert(finishAward(a,e))
        view=R.Snapshot(a,8000000)
        assert(view.activeUsable==50000 and view.activeBank==10000 and view.total==560000)
    ''')


def test_exact_threshold_unbanked_dual_preserves_native_shared_cap(runtime):
    runtime.execute('''
        local a=actor(64000,2,0,7);R.Adopt(a)
        assert(R.CaptureDualPreview(a));assert(R.PrepareDual(a,4))
        local pending=R.Export(a).pendingDual
        assert(pending.after.old.total==64000 and pending.after.old.preBank==0)
        resetStage='native';a.m_baseStats.m_xp=0
        a.m_startTypeAI.m_Class=9;a.m_baseStats.m_flags=8
        resetStage='completing';assert(R.CompleteDual(a,4))
        local gain=award(a,100000);assert(R.BeforeAward(a,gain));assert(finishAward(a,gain))
        local view=R.Snapshot(a,8000000)
        assert(view.retiredDebit==64000 and view.activeUsable==97000 and view.activeBank==3000)
        assert(view.oldBank==0 and view.total==164000)
        phase='SOA';ending=2;view=R.Snapshot(a,8000000)
        assert(view.activeUsable==100000 and view.retiredDebit==64000 and view.activeBank==0)
    ''')


def test_manual_level_up_distinguishes_unowned_excluded_and_damaged_owned(runtime):
    runtime.execute('''
        local a=actor(1000)
        assert(R.ManualOwnership(a)=='passthrough')
        R.Adopt(a);assert(R.ManualOwnership(a)=='owned')
        a.aux.CBMBank.excluded=true;assert(R.ManualOwnership(a)=='passthrough')
        a.aux.CBMBank.excluded=nil;a.aux.CBMBank.schema=99
        assert(not pcall(R.ManualOwnership,a))
        a.aux.CBMBank.schema=2;a.aux.CBMBank.pendingManualProgression={stage='uncertain'}
        assert(not pcall(R.ManualOwnership,a))
        a.aux.CBMBank.pendingManualProgression=nil
        a.identity.serializing=true;assert(not pcall(R.ManualOwnership,a))
        a.identity.serializing=false;a.aux.CBMBankLifetime.ownerKey='wrong'
        assert(not pcall(R.ManualOwnership,a))
    ''')


def test_existing_dual_only_adopts_native_recoverable_history(runtime):
    runtime.execute('''
        local a=actor(10000,9,8,7); R.Adopt(a)
        local state=a.aux.CBMBank
        assert(state.history=='native_threshold' and state.old.total==64000 and state.old.preBank==0)
        a.m_baseStats.m_xp=200000
        local view=R.Snapshot(a,8000000)
        assert(view.activeUsable==97000 and view.activeBank==103000 and view.total==264000)
    ''')


def test_saved_state_is_not_advanced_by_export_and_older_save_restores_own_phase(runtime):
    runtime.execute('''
        local a=actor(1); R.Adopt(a); a.m_baseStats.m_xp=600000
        local old=R.Export(a)
        phase='SOD'; ending=1
        local withoutTick=R.Export(a)
        assert(withoutTick.phase=='BG1' and withoutTick.revision==old.revision)
        R.Snapshot(a,8000000)
        local restored=actor(600000); restored.identity.incarnation='2'
        restored.identity.ownerToken=string.rep('b',32)
        phase='BG1'; ending=0; R.Import(restored,old)
        local view=R.Snapshot(restored,8000000)
        assert(view.phase=='BG1' and view.activeBank==439000)
        assert(restored.aux.CBMBank.ownerKey==string.rep('a',32))
    ''')


def test_unknown_class_reset_does_not_reconstruct_account(runtime):
    runtime.execute('''
        local a=actor(1); R.Adopt(a); a.m_baseStats.m_xp=600000
        a.m_startTypeAI.m_Class=9; a.m_baseStats.m_flags=8; a.m_baseStats.m_level1=7
        local ok,why=pcall(R.Snapshot,a,8000000)
        assert(not ok and tostring(why):find('mismatch'))
        assert(a.aux.CBMBank.kind=='single' and a.m_baseStats.m_xp==600000)
    ''')


@pytest.mark.parametrize('class_id', [7, 9, 10, 17])
def test_multiclass_cap_is_pooled_and_preserves_native_xp(runtime, class_id):
    runtime.globals().classID = class_id
    runtime.execute('''
        local a=actor(1,classID); R.Adopt(a); a.m_baseStats.m_xp=600001
        a.m_derivedStats.m_nXP=600001; cap.BeforeNativeClamp(a,8000000)
        local view=R.Snapshot(a,8000000)
        assert(view.classKind=='multi' and view.activeUsable==161000 and view.activeBank==439001)
        assert(a.m_baseStats.m_xp==600001 and a.m_derivedStats.m_nXP==161000)
        assert(a.aux.CBMBank.old==nil and view.retiredDebit==0)
        assert(not pcall(R.PrepareDual,a,4) and a.aux.CBMBank.pendingDual==nil)
    ''')


def test_campaign_initialization_does_not_grandfather_the_first_award(runtime):
    runtime.execute('''
        phase='SOA'; ending=0 -- direct-start campaign flags are not initialized
        local a=actor(1000); local adopted,reason=R.Adopt(a)
        assert(adopted==false and reason and a.aux.CBMBank.initializing)
        a.m_baseStats.m_xp=600000
        local pending=R.Snapshot(a,8000000)
        assert(pending.initializing and pending.activeUsable==161000 and pending.activeBank==439000)
        local saved=R.Export(a)
        assert(saved.initializing and saved.baseAtAdoption==1000)
        local loaded=actor(600000); loaded.identity.incarnation='2'; R.Import(loaded,saved)
        phase='BG1'; ending=0
        local resolved=R.Snapshot(loaded,8000000)
        assert(not resolved.initializing and resolved.activeBank==439000)
        assert(loaded.aux.CBMBank.floor==1000 and loaded.m_baseStats.m_xp==600000)
    ''')


def test_chr_import_rebinds_new_run_without_cashing_out_the_bank(runtime):
    runtime.execute('''
        phase='SOD'; ending=1
        local donor=actor(500000); R.Adopt(donor); donor.m_baseStats.m_xp=600000
        donor.identity.reason='chr_export'; donor.identity.serializing=true
        donor.identity.canMutate=false
        local exported=R.Export(donor)
        assert(exported.chrTransfer.usable==500000 and donor.aux.CBMBank.chrTransfer==nil)
        local imported=actor(600000); imported.identity.birthReason='chr_import'
        imported.identity.ownerToken=string.rep('b',32); imported.identity.incarnation='2'
        phase='BG1'; ending=0; R.Import(imported,exported); R.OnLoaded(imported)
        local view=R.Snapshot(imported,8000000)
        assert(view.phase=='BG1' and view.activeUsable==500000 and view.activeBank==100000)
        assert(imported.aux.CBMBank.ownerKey==string.rep('b',32))
        assert(donor.aux.CBMBank.ownerKey==string.rep('a',32) and donor.aux.CBMBank.phase=='SOD')
        assert(imported.m_baseStats.m_xp==600000)
    ''')


def test_chr_native_xp_change_retains_receipt_for_reconciliation(runtime):
    runtime.execute('''
        local donor=actor(1000); R.Adopt(donor); donor.m_baseStats.m_xp=600000
        donor.identity.reason='chr_export'; local exported=R.Export(donor)
        local imported=actor(161000); imported.identity.birthReason='chr_import'
        imported.identity.ownerToken=string.rep('b',32); R.Import(imported,exported)
        local ok,why=pcall(R.Snapshot,imported,8000000)
        assert(not ok and tostring(why):find('changed XP'))
        local retained=R.Export(imported)
        assert(retained.chrTransfer.base==600000 and retained.chrPending.sourceOwner==string.rep('a',32))
        assert(imported.m_baseStats.m_xp==161000)
    ''')


def test_chr_reassociates_compact_reward_ledger_but_not_incomplete_work(runtime):
    runtime.execute('''
        local donor=actor(10000,9,8,7);R.Adopt(donor)
        donor.aux.CBMBank.manualLedger={schema=1,ownerKey=donor.aux.CBMBank.ownerKey,records={'opaque exact reward packet'}}
        donor.identity.reason='chr_export'
        donor.aux.CBMBank.pendingManualProgression={stage='uncertain'}
        assert(R.Export(donor).chrTransfer==nil)
        donor.aux.CBMBank.pendingManualProgression=nil
        donor.aux.CBMBank.old.pendingHLADelivery={stage='uncertain'}
        assert(R.Export(donor).chrTransfer==nil)
        donor.aux.CBMBank.old.pendingHLADelivery=nil
        local saved=R.Export(donor)
        local other=actor(10000,9,8,7);other.identity.birthReason='chr_import'
        other.identity.ownerToken=string.rep('b',32);other.identity.incarnation='2'
        R.Import(other,saved);R.OnLoaded(other)
        local ledger=other.aux.CBMBank.manualLedger
        assert(ledger.ownerKey==string.rep('b',32) and ledger.previousOwnerKey==string.rep('a',32))
        assert(ledger.records[1]=='opaque exact reward packet')
        assert(donor.aux.CBMBank.manualLedger.ownerKey==string.rep('a',32))
    ''')


def test_award_ordinary_base_is_only_copy_and_overflow_is_saved_once(runtime):
    runtime.execute('''
        local a=actor(1000); R.Adopt(a)
        local e=award(a,500000);assert(R.BeforeAward(a,e)==1)
        assert(a.m_baseStats.m_xp==1000 and a.aux.CBMBank.overflow==0)
        assert(finishAward(a,e))
        assert(a.m_baseStats.m_xp==501000 and a.aux.CBMBank.overflow==0)
        assert(a.aux.CBMBank.pendingAward==nil and a.aux.CBMBank.revision==1)
        a.m_baseStats.m_xp=4294967200
        e=award(a,200000);assert(R.BeforeAward(a,e)==1)
        assert(e.boundary.applied==95 and e.boundary.remainder==199905)
        local before=R.Export(a)
        assert(before.pendingAward.remainder==199905 and before.overflow==0)
        assert(finishAward(a,e))
        local view=R.Snapshot(a,8000000)
        assert(a.m_baseStats.m_xp==4294967295 and view.total==4295167200)
        assert(view.activeOverflow==199905 and view.activeBank==4295006200)
        assert(not pcall(R.CompleteAward,a,e)) -- no replay/double credit
        e=award(a,123);assert(R.BeforeAward(a,e)==1);assert(finishAward(a,e))
        assert(a.aux.CBMBank.overflow==200028 and a.m_baseStats.m_xp==4294967295)
    ''')


def test_first_award_adopts_actual_pre_award_baseline(runtime):
    runtime.execute('''
        local a=actor(1000);local e=award(a,600000)
        assert(R.BeforeAward(a,e)==1 and a.aux.CBMBank.floor==1000)
        assert(finishAward(a,e))
        local view=R.Snapshot(a,8000000)
        assert(view.activeUsable==161000 and view.activeBank==440000)
        local enemy=actor(1000);enemy.party=false
        assert(R.BeforeAward(enemy,award(enemy,100))==2 and enemy.aux.CBMBank==nil)
        local clone=actor(1000);clone.identity.eligible=false
        assert(R.BeforeAward(clone,award(clone,100))==2 and clone.aux.CBMBank==nil)
    ''')


def test_first_cap_check_adopts_unowned_party_member(runtime):
    # A new game's protagonist reaches the party from character creation without a
    # party-ready or loaded adoption; its first native stat check must adopt it with
    # the actual baseline instead of failing the cap callback.
    runtime.execute('''
        local errors=#cap.errors
        local a=actor(64000)
        cap.BeforeNativeClamp(a,8000000)
        assert(#cap.errors==errors and a.m_derivedStats.m_nXP==64000)
        assert(a.aux.CBMBank.floor==64000 and a.aux.CBMBankLifetime.origin=='adopted')
        local e=award(a,200000);assert(R.BeforeAward(a,e)==1);assert(finishAward(a,e))
        local view=R.Snapshot(a,8000000)
        assert(view.activeUsable==161000 and view.activeBank==103000 and a.aux.CBMBank.floor==64000)
        local enemy=actor(1000);enemy.party=false
        assert(R.Snapshot(enemy,8000000).eligible==false and enemy.aux.CBMBank==nil)
        local copy=actor(1000);copy.identity.serializing=true
        local ok,why=pcall(R.Snapshot,copy,8000000)
        assert(not ok and tostring(why):find('not been initialized') and copy.aux.CBMBank==nil)
        phase='SOA';ending=0
        local waiting=actor(89000)
        view=R.Snapshot(waiting,8000000)
        assert(view.initializing and waiting.aux.CBMBank.initializing and waiting.aux.CBMBank.baseAtAdoption==89000)
    ''')


def test_overflow_during_campaign_initialization_keeps_baseline_and_bank(runtime):
    runtime.execute('''
        phase='SOA';ending=0
        local a=actor(1000);R.Adopt(a)
        a.m_baseStats.m_xp=4294967200
        local e=award(a,200000);assert(R.BeforeAward(a,e)==1);assert(finishAward(a,e))
        assert(a.aux.CBMBank.initializing and a.aux.CBMBank.baseAtAdoption==1000)
        assert(a.aux.CBMBank.overflow==199905 and a.aux.CBMBank.revision==1)
        local saved=R.Export(a);local b=actor(4294967295)
        b.identity.incarnation='2';R.Import(b,saved)
        phase='BG1';ending=0
        local view=R.Snapshot(b,8000000)
        assert(view.total==4295167200 and view.activeUsable==161000)
        assert(b.aux.CBMBank.floor==1000 and b.aux.CBMBank.overflow==199905)
    ''')


def test_incomplete_award_survives_reload_without_guess_or_replay(runtime):
    runtime.execute('''
        local a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=4294967200
        local e=award(a,200000);assert(R.BeforeAward(a,e)==1)
        a.m_baseStats.m_xp=4294967295
        e.boundary.stage='uncertain';e.boundary.nativeResult=1
        R.UncertainAward(a,e)
        local saved=R.Export(a)
        assert(saved.pendingAward.remainder==199905 and saved.overflow==0)
        assert(saved.pendingAward.observedBase==4294967295)
        local b=actor(4294967295);b.identity.incarnation='2';R.Import(b,saved)
        local ok,why=pcall(R.Snapshot,b,8000000)
        assert(not ok and tostring(why):find('reconciliation'))
        assert(not pcall(R.BeforeAward,b,award(b,10)))
        assert(R.Export(b).pendingAward.stage=='uncertain' and b.m_baseStats.m_xp==4294967295)
    ''')


def test_withdrawn_journal_leaves_the_account_as_before_its_preparation(runtime):
    # Native code withdraws the journal of a preparation no store followed (what
    # it saw changed during the callback) and retries from a fresh boundary.
    runtime.execute('''
        local a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=600000
        local e=award(a,100);assert(R.BeforeAward(a,e)==1 and a.aux.CBMBank.pendingAward)
        local revision,overflow=a.aux.CBMBank.revision,a.aux.CBMBank.overflow
        e.boundary.stage='withdrawing'
        assert(R.UncertainAward(a,e)==true and a.aux.CBMBank.pendingAward==nil)
        assert(a.aux.CBMBank.revision==revision and a.aux.CBMBank.overflow==overflow)
        e=award(a,100);assert(R.BeforeAward(a,e)==1 and finishAward(a,e) and R.ActiveTotal(a)==600100)
        assert(writeXP(a,700000,0)==1 and a.aux.CBMBank.pendingWrite)
        a.writeBoundary.stage='withdrawing'
        assert(R.UncertainWrite(a)==true and a.aux.CBMBank.pendingWrite==nil and a.aux.CBMBank.lastWrite==nil)
        assert(writeXP(a,700000,0)==1 and finishWrite(a) and R.ActiveTotal(a)==700000)
        phase='SOA';ending=0 -- an account still waiting for its campaign flags
        local c=actor(1000);R.Adopt(c);assert(c.aux.CBMBank.initializing)
        local g=award(c,100);assert(R.BeforeAward(c,g)==1);g.boundary.stage='withdrawing'
        assert(R.UncertainAward(c,g)==true and c.aux.CBMBank.pendingAward==nil and c.aux.CBMBank.initializing)
    ''')


def test_only_the_exact_prepared_journal_is_withdrawn(runtime):
    runtime.execute('''
        local a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=600000
        local e=award(a,100);assert(R.BeforeAward(a,e)==1);e.boundary.stage='withdrawing'
        local function kept(change,undo)
            change();assert(not pcall(R.UncertainAward,a,e) and a.aux.CBMBank.pendingAward.stage=='prepared');undo()
        end
        kept(function()e.boundary.nativeResult=1 end,function()e.boundary.nativeResult=0 end) -- the leaf ran
        kept(function()e.boundary.postBase=600100 end,function()e.boundary.postBase=600000 end)
        kept(function()e.boundary.amount=101;e.boundary.applied=101 end,
            function()e.boundary.amount=100;e.boundary.applied=100 end)
        kept(function()a.aux.CBMBank.revision=a.aux.CBMBank.revision+1 end,
            function()a.aux.CBMBank.revision=a.aux.CBMBank.revision-1 end)
        kept(function()a.identity.serializing=true end,function()a.identity.serializing=false end)
        kept(function()a.identity.canMutate=false end,function()a.identity.canMutate=true end)
        kept(function()a.identity.incarnation='2' end,function()a.identity.incarnation='1' end)
        a.aux.CBMBank.pendingAward.stage='uncertain' -- an earlier uncertain journal is never withdrawn
        assert(not pcall(R.UncertainAward,a,e) and a.aux.CBMBank.pendingAward.stage=='uncertain')
        a.aux.CBMBank.pendingAward.stage='prepared'
        e.boundary.stage='uncertain';R.UncertainAward(a,e) -- not withdrawn: marked as before
        assert(a.aux.CBMBank.pendingAward.stage=='uncertain' and not pcall(R.Snapshot,a,8000000))
        local b=actor(1000);R.Adopt(b);b.m_baseStats.m_xp=600000
        assert(writeXP(b,700000,0)==1);b.writeBoundary.stage='withdrawing'
        b.writeBoundary.postBase=700000 -- the store happened
        assert(not pcall(R.UncertainWrite,b) and b.aux.CBMBank.pendingWrite)
        b.writeBoundary.postBase=600000;b.writeBoundary.plannedBase=700001
        assert(not pcall(R.UncertainWrite,b) and b.aux.CBMBank.pendingWrite)
        b.writeBoundary.plannedBase=700000;assert(R.UncertainWrite(b)==true and b.aux.CBMBank.pendingWrite==nil)
    ''')


def test_award_completion_requires_same_native_split_revision_and_lifetime(runtime):
    runtime.execute('''
        local a=actor(1000);R.Adopt(a);local e=award(a,100)
        assert(R.BeforeAward(a,e)==1)
        assert(not pcall(R.BeforeAward,a,award(a,100))) -- reentry cannot replace journal
        a.m_baseStats.m_xp=1100;e.boundary.stage='completing'
        e.boundary.nativeResult=1;e.boundary.postBase=1100
        e.boundary.amount=101;e.boundary.applied=101
        assert(not pcall(R.CompleteAward,a,e))
        e.boundary.amount=100;e.boundary.applied=100
        a.aux.CBMBank.revision=1;assert(not pcall(R.CompleteAward,a,e))
        a.aux.CBMBank.revision=0;a.identity.incarnation='2'
        assert(not pcall(R.CompleteAward,a,e))
        assert(a.aux.CBMBank.overflow==0 and a.aux.CBMBank.pendingAward.amount==100)
    ''')


def test_exact_storage_refusal_happens_before_native_award(runtime):
    runtime.execute('''
        local a=actor(1);R.Adopt(a);a.m_baseStats.m_xp=4294967295
        a.aux.CBMBank.overflow=9007199254740991-4294967295
        local ok,why=pcall(R.BeforeAward,a,award(a,1))
        assert(not ok and tostring(why):find('exact storage'))
        assert(a.m_baseStats.m_xp==4294967295 and a.aux.CBMBank.pendingAward==nil)
    ''')


def test_native_writer_classification_conserves_add_loss_and_replaces_set(runtime):
    runtime.execute('''
        local a=actor(1);R.Adopt(a);a.m_baseStats.m_xp=4294967200
        assert(writeXP(a,200000,1)==1 and a.m_baseStats.m_xp==4294967200)
        assert(finishWrite(a));local view=R.Snapshot(a,8000000)
        assert(view.total==4295167200 and view.activeOverflow==199905)
        assert(a.aux.CBMBank.lastWrite.classification=='native_add')
        assert(writeXP(a,4294767296,1)==1);assert(finishWrite(a)) -- loss200000
        view=R.Snapshot(a,8000000)
        assert(view.total==4294967200 and view.activeOverflow==0 and a.m_baseStats.m_xp==4294967200)
        assert(a.aux.CBMBank.lastWrite.classification=='native_loss')
        assert(writeXP(a,200000,99)==1);assert(finishWrite(a)) -- native unknownmode=SET
        view=R.Snapshot(a,8000000)
        assert(view.total==200000 and view.activeOverflow==0)
        local receipt=a.aux.CBMBank.lastWrite
        assert(receipt.classification=='unclassified_absolute_set' and receipt.replacedBank)
        assert(receipt.activeBefore==4294967200 and receipt.activeAfter==200000)
        assert(R.lastError:find('purpose is unknown'))
    ''')


def test_owned_recruitment_uses_retained_total_and_imoen_keeps_exact_set_policy(runtime):
    runtime.execute('''
        local a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=1600000
        assert(R.OwnedSet(a,1250000,2)) -- no loss when cappedvisibleXPlooks lower
        assert(a.m_baseStats.m_xp==1600000 and a.writeBoundary==nil)
        assert(R.OwnedSet(a,2000000,2))
        assert(R.ActiveTotal(a)==2000000 and a.aux.CBMBank.lastWrite.classification=='recruitment_catchup')
        a.m_baseStats.m_xp=4294967295;a.aux.CBMBank.overflow=123
        assert(R.OwnedSet(a,1750000,1)) -- independent authored party-average SET
        assert(R.ActiveTotal(a)==1750000 and a.aux.CBMBank.overflow==0)
        assert(a.aux.CBMBank.lastWrite.classification=='party_average_set')
    ''')


def test_active_writer_does_not_move_or_erase_the_old_class_bank(runtime):
    runtime.execute('''
        phase='SOD';ending=1
        local a=actor(500000,2,0,10);R.Adopt(a);a.m_baseStats.m_xp=550000
        R.CaptureDualPreview(a);R.PrepareDual(a,4);a.m_baseStats.m_xp=0
        a.m_startTypeAI.m_Class=9;a.m_baseStats.m_flags=8
        resetStage='completing';R.CompleteDual(a,4)
        assert(writeXP(a,200000,1)==1);assert(finishWrite(a))
        assert(R.ActiveTotal(a)==200000 and a.aux.CBMBank.old.total==550000)
        assert(R.OwnedSet(a,100000,1))
        local view=R.Snapshot(a,8000000)
        assert(view.total==650000 and view.activeBank==100000 and view.oldBank==50000)
        assert(a.aux.CBMBank.old.total==550000 and a.m_baseStats.m_level1==10)
    ''')


def test_uncertain_writer_retains_exact_before_and_after_for_reload(runtime):
    runtime.execute('''
        local a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=600000
        assert(writeXP(a,750000,0,'recruitment_catchup')==1)
        assert(not pcall(R.Snapshot,a,8000000))
        a.m_baseStats.m_xp=750000;a.writeBoundary.stage='uncertain'
        a.writeBoundary.postBase=750000;R.UncertainWrite(a)
        local saved=R.Export(a)
        assert(saved.pendingWrite.preBase==600000 and saved.pendingWrite.plannedBase==750000)
        assert(saved.pendingWrite.after.lastWrite.activeAfter==750000)
        local b=actor(750000);b.identity.incarnation='2';R.Import(b,saved)
        assert(not pcall(R.Snapshot,b,8000000))
        assert(b.m_baseStats.m_xp==750000 and b.aux.CBMBank.pendingWrite.stage=='uncertain')
    ''')


def test_refused_writer_plan_leaves_no_journal_behind_the_native_fallback(runtime):
    # CEBG #19: any error in BeforeWrite makes native code run the original
    # opcode-104 write. A journal published before the plan would then refuse
    # this actor's every later award and write as an unreconciled transaction.
    runtime.execute('''
        local a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=600000
        local plan,order=CBMBank_Writer.Plan,{}
        local function observe(s) order[#order+1]=s.aux.CBMBank.pendingWrite==nil and 'unjournaled' or 'journaled' end
        CBMBank_Writer.Plan=function(s) observe(s);return false end
        local ok,why=pcall(writeXP,a,750000,0)
        assert(not ok and tostring(why):find('refused its prepared plan'))
        assert(order[1]=='unjournaled' and a.aux.CBMBank.pendingWrite==nil)
        CBMBank_Writer.Plan=function(s) observe(s);error('native plan unavailable') end
        assert(not pcall(writeXP,a,750000,0) and a.aux.CBMBank.pendingWrite==nil)
        a.m_baseStats.m_xp=750000 -- the original SET ran unbanked instead
        CBMBank_Writer.Plan=function(s,target) observe(s);return plan(s,target) end
        assert(writeXP(a,800000,0)==1 and order[3]=='unjournaled')
        assert(a.aux.CBMBank.pendingWrite.plannedBase==800000 and finishWrite(a))
        assert(R.ActiveTotal(a)==800000 and a.aux.CBMBank.pendingWrite==nil)
        local e=award(a,100);assert(R.BeforeAward(a,e)==1 and finishAward(a,e))
        assert(R.ActiveTotal(a)==800100)
    ''')


def test_refused_setter_write_is_recapped_at_the_next_cap_check(runtime):
    # A refused stat44 setter write is the game's own store and banks nothing.
    # Base XP is the one authoritative copy, so the next cap check (the native
    # stat check deriving XP from base, then GetXPCap) restores the cap and
    # re-derives the bank; no journal is left and the next banked change works.
    runtime.execute('''
        local a=actor(150000);R.OnLoaded(a)
        local function check() -- the native stat check derives from base XP
            a.m_derivedStats.m_nXP=a.m_baseStats.m_xp;cap.BeforeNativeClamp(a,8000000)
            return a.m_derivedStats.m_nXP,R.Snapshot(a,8000000)
        end
        local errors=#cap.errors
        local derived,view=check();assert(derived==150000 and view.activeBank==0)
        a.m_baseStats.m_xp=a.m_baseStats.m_xp+50000 -- ADD over the cap
        derived,view=check();assert(derived==161000 and view.activeUsable==161000 and view.activeBank==39000)
        a.m_baseStats.m_xp=100000 -- SET below it: nothing stays banked
        derived,view=check();assert(derived==100000 and view.activeBank==0)
        a.m_baseStats.m_xp=400000 -- SET above it
        derived,view=check();assert(derived==161000 and view.activeBank==239000)
        a.m_baseStats.m_xp=a.m_baseStats.m_xp-300000 -- a loss
        derived,view=check();assert(derived==100000 and view.activeBank==0)
        assert(#cap.errors==errors and a.aux.CBMBank.pendingWrite==nil and a.aux.CBMBank.pendingAward==nil)
        local e=award(a,100000);assert(R.BeforeAward(a,e)==1 and finishAward(a,e))
        derived,view=check();assert(derived==161000 and view.activeBank==39000)
        assert(writeXP(a,250000,0)==1 and finishWrite(a))
        derived,view=check();assert(derived==161000 and view.activeBank==89000 and #cap.errors==errors)
    ''')


def test_refused_owned_set_reports_the_game_write_and_catchup_finishes_once(runtime):
    runtime.execute('''
        local a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=600000
        local banked=CBMBank_Writer.ApplyOwnedSet
        -- The bridge refused it: the game's own SET ran (status 5), nothing banked.
        CBMBank_Writer.ApplyOwnedSet=function(s,target) s.m_baseStats.m_xp=target;return false,65535,5 end
        local ok,why=pcall(R.OwnedSet,a,750000,2)
        assert(not ok and tostring(why):find('own write without the bank (status 5)',1,true))
        assert(a.m_baseStats.m_xp==750000 and a.aux.CBMBank.pendingWrite==nil)
        -- The catch-up's next attempt finds its target reached and writes nothing again.
        CBMBank_Writer.ApplyOwnedSet=function() error('must not write again') end
        assert(R.OwnedSet(a,750000,2) and R.ActiveTotal(a)==750000)
        CBMBank_Writer.ApplyOwnedSet=function() return false end
        ok,why=pcall(R.OwnedSet,a,800000,1)
        assert(not ok and tostring(why):find('was not invoked',1,true))
        -- The actor's lifetime ended while the bank prepared it: nothing was written.
        CBMBank_Writer.ApplyOwnedSet=function() return false,65535,11 end
        ok,why=pcall(R.OwnedSet,a,800000,1)
        assert(not ok and tostring(why):find('wrote nothing',1,true) and not tostring(why):find('own write',1,true))
        assert(a.m_baseStats.m_xp==750000)
        -- Another thread's lifetime event at its address: kept, never written (12).
        CBMBank_Writer.ApplyOwnedSet=function() return false,65535,12 end
        ok,why=pcall(R.OwnedSet,a,800000,1)
        assert(not ok and tostring(why):find('the write is kept, not applied (status 12)',1,true)
            and not tostring(why):find('own write',1,true))
        assert(a.m_baseStats.m_xp==750000)
        CBMBank_Writer.ApplyOwnedSet=banked
        assert(R.OwnedSet(a,800000,1) and R.ActiveTotal(a)==800000)
    ''')


def overflowed(runtime):
    # 4,295,167,200 XP: the word is full and the bank holds 199,905 above it,
    # as a banked award past the word leaves it.
    runtime.execute('''
        a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=4294967200
        local e=award(a,200000);assert(R.BeforeAward(a,e)==1 and finishAward(a,e))
        local view=R.Snapshot(a,8000000)
        assert(view.total==4295167200 and a.aux.CBMBank.overflow==199905 and a.m_baseStats.m_xp==4294967295)
    ''')


def test_refused_set_takes_the_stored_word_at_export_reload_and_next_banking_point(runtime):
    # Codex: a refused SET to 100,000 left base 100,000 but an active total of
    # 299,905, which survived export/import. The game's own SET replaced the word;
    # native code noted it (CBMI_NoteReplaced) and the account now matches it.
    overflowed(runtime)
    runtime.execute('''
        a.m_baseStats.m_xp=100000;a.identity.nativeReplaced=true -- the game's own SET (status 5)
        local revision=a.aux.CBMBank.revision
        -- Saved before any banking point: the save already matches the stored word,
        -- and the save itself changes nothing live.
        local saved=R.Export(a)
        assert(saved.overflow==0 and saved.revision==revision+1)
        assert(a.aux.CBMBank.overflow==199905 and a.aux.CBMBank.revision==revision and a.identity.nativeReplaced)
        local b=actor(100000);b.identity.incarnation='2';R.Import(b,saved)
        local view=R.Snapshot(b,8000000)
        assert(view.total==100000 and view.activeOverflow==0 and view.activeBank==0)
        -- The record screen shows what the next cap check publishes, without publishing it.
        assert(R.RecordView(a,8000000).bank==0 and a.aux.CBMBank.overflow==199905 and a.acks==nil)
        -- The next safe banking point publishes it once and clears the note.
        view=R.Snapshot(a,8000000)
        assert(view.total==100000 and view.activeOverflow==0 and view.activeUsable==100000)
        assert(a.aux.CBMBank.overflow==0 and a.aux.CBMBank.revision==revision+1)
        assert(a.acks==1 and not a.identity.nativeReplaced)
        assert(R.lastError:find('199905 XP the bank held above the 32-bit native word',1,true))
        R.Snapshot(a,8000000);assert(a.aux.CBMBank.revision==revision+1 and a.acks==1)
        local again=R.Export(a);local c=actor(100000);c.identity.incarnation='3';R.Import(c,again)
        assert(R.Snapshot(c,8000000).total==100000 and again.revision==revision+1)
        -- Later changes bank normally from the matched account.
        local e=award(a,100);assert(R.BeforeAward(a,e)==1 and finishAward(a,e) and R.ActiveTotal(a)==100100)
        assert(writeXP(a,200000,1)==1 and finishWrite(a) and R.ActiveTotal(a)==300100)
    ''')


@pytest.mark.parametrize("change,stored,replaced", [
    # ADD past the word: SetAtOffset's `add dword ptr [rcx+0x570], r8d` wraps.
    ("add", (4294967295 + 200000) % 4294967296, True),
    # A loss the word covers: the store subtracts from the word; overflow stays XP.
    ("loss", 4294967295 - 1000, False),
    # opcode-104 percentage: the low 32 bits of base*percent, divided by 100.
    ("percent", ((4294967295 * 50) & 0xffffffff) // 100, True),
])
def test_unbanked_store_neither_double_counts_nor_keeps_stale_overflow(runtime, change, stored, replaced):
    # What the game's own store produced is the native word (writer_native_test
    # runs the unpatched SetAtOffset window for the same values). Native code
    # notes a replaced word; any other store kept base plus overflow exact.
    overflowed(runtime)
    runtime.globals().stored = stored
    runtime.globals().replaced = replaced
    runtime.globals().change = change
    runtime.execute('''
        if change=='percent' then
            a.writeBoundary={stage='preparing',incarnation=a.identity.incarnation,preBase=4294967295,
                rawValue=50,mode=2,source='opcode104',effectMode=2,origin='unclassified'}
            assert(not pcall(R.BeforeWrite,a)) -- refused: the bank has no percentage of overflow
        end
        a.m_baseStats.m_xp=stored;a.identity.nativeReplaced=replaced
        local shown=R.RecordView(a,8000000).bank -- The record screen, before the cap check.
        local view=R.Snapshot(a,8000000)
        assert(shown==view.activeBank and R.RecordView(a,8000000).bank==shown)
        if replaced then
            assert(view.total==stored and view.activeOverflow==0 and a.aux.CBMBank.overflow==0)
        else
            -- The bank's own result for a 1,000 XP loss: 4,295,167,200 - 1,000.
            assert(view.total==4295166200 and view.activeOverflow==199905)
        end
        local b=actor(stored);b.identity.incarnation='2';R.Import(b,R.Export(a))
        assert(R.Snapshot(b,8000000).total==view.total)
    ''')


def test_unresolved_journal_keeps_its_account_and_records_the_later_replacement(runtime):
    # An account with an uncertain journal is already held for reconciliation;
    # it is not settled around that journal. The save records that the word was
    # replaced after it, and the note stays until a matched account exists.
    runtime.execute('''
        local a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=4294967295;a.aux.CBMBank.overflow=199905
        local e=award(a,100);assert(R.BeforeAward(a,e)==1)
        e.boundary.stage='uncertain';e.boundary.nativeResult=1;R.UncertainAward(a,e)
        a.m_baseStats.m_xp=100000;a.identity.nativeReplaced=true
        local saved=R.Export(a)
        assert(saved.overflow==199905 and saved.pendingAward.laterNativeReplace==true)
        assert(a.aux.CBMBank.pendingAward.laterNativeReplace==nil)
        local ok,why=pcall(R.Snapshot,a,8000000)
        assert(not ok and tostring(why):find('reconciliation') and a.identity.nativeReplaced and a.acks==nil)
        assert(a.aux.CBMBank.overflow==199905 and R.RecordView(a,8000000)==nil)
        local b=actor(100000);b.identity.incarnation='2';R.Import(b,saved)
        assert(b.aux.CBMBank.pendingAward.laterNativeReplace==true and not pcall(R.Snapshot,b,8000000))
    ''')


def test_replaced_word_during_save_is_projected_not_published(runtime):
    # A cap check while the game saves may not change the bank: it reports the
    # matched account but publishes nothing and keeps the note for later.
    overflowed(runtime)
    runtime.execute('''
        a.m_baseStats.m_xp=100000;a.identity.nativeReplaced=true
        a.identity.serializing=true;a.identity.canMutate=false
        local revision=a.aux.CBMBank.revision
        local view=R.Snapshot(a,8000000)
        assert(view.total==100000 and view.activeOverflow==0)
        assert(a.aux.CBMBank.overflow==199905 and a.aux.CBMBank.revision==revision and a.acks==nil)
        a.identity.serializing=false;a.identity.canMutate=true
        assert(R.Snapshot(a,8000000).total==100000 and a.aux.CBMBank.overflow==0 and a.acks==1)
    ''')


def test_replaced_word_settles_an_account_still_waiting_for_its_campaign(runtime):
    runtime.execute('''
        phase='SOA';ending=0
        local a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=4294967200
        local e=award(a,200000);assert(R.BeforeAward(a,e)==1 and finishAward(a,e))
        assert(a.aux.CBMBank.initializing and a.aux.CBMBank.overflow==199905 and a.aux.CBMBank.revision==1)
        a.m_baseStats.m_xp=100000;a.identity.nativeReplaced=true
        local view=R.Snapshot(a,8000000)
        assert(view.initializing and view.total==100000 and a.aux.CBMBank.initializing)
        assert(a.aux.CBMBank.overflow==0 and a.aux.CBMBank.revision==2 and a.aux.CBMBank.baseAtAdoption==1000)
        phase='BG1';ending=0
        view=R.Snapshot(a,8000000)
        assert(view.total==100000 and a.aux.CBMBank.floor==1000 and a.aux.CBMBank.overflow==0)
    ''')


def test_chr_export_receipt_uses_the_matched_account(runtime):
    overflowed(runtime)
    runtime.execute('''
        a.m_baseStats.m_xp=100000;a.identity.nativeReplaced=true;a.identity.reason='chr_export'
        local saved=R.Export(a)
        -- Stale overflow would have shown 161,000 usable (100,000 + 199,905, capped).
        assert(saved.overflow==0 and saved.chrTransfer.usable==100000 and saved.chrTransfer.base==100000)
    ''')


def test_owned_set_handles_initialization_and_later_independent_native_awards(runtime):
    runtime.execute('''
        phase='SOA';ending=0
        local a=actor(1000);R.Adopt(a)
        assert(R.OwnedSet(a,750000,2))
        assert(a.aux.CBMBank.initializing and a.aux.CBMBank.baseAtAdoption==1000)
        phase='BG1';ending=0
        assert(R.ActiveTotal(a)==750000 and a.aux.CBMBank.lastWrite.activeAfter==750000)
        local native=CBMBank_Writer.ApplyOwnedSet
        CBMBank_Writer.ApplyOwnedSet=function(s,target,origin)
            local result=native(s,target,origin)
            -- Simulate a separate proven award in ProcessEffectList AFTER the
            -- stat44 write completes; the source-owned target must stay750k.
            local e=award(s,1000);assert(R.BeforeAward(s,e)==1);assert(finishAward(s,e))
            return result
        end
        assert(R.OwnedSet(a,1000000,2) and R.ActiveTotal(a)==1001000)
        assert(a.aux.CBMBank.lastWrite.activeAfter==1000000)
    ''')


def test_dual_baseline_precedes_new_class_preview_choices(runtime):
    runtime.execute('''
        phase='SOD';ending=1
        local a=actor(500000,2,0,10);R.Adopt(a);a.m_baseStats.m_xp=550000
        a.m_baseStats.m_proficiencies[0]=2;a.m_baseStats.m_maxHitPointsBase=80
        assert(R.CaptureDualPreview(a))
        -- The native choice UI changes real actor proficiencies before reset.
        -- These new-class choices are not retroactively assigned to Fighter.
        a.m_baseStats.m_proficiencies[0]=1
        assert(R.PrepareDual(a,4))
        local after=a.aux.CBMBank.pendingDual.after
        assert(after.old.rewardReceipt.before.legacyProficiencies[1]==2)
        assert(after.old.rewardReceipt.before.maxHPBase==80)
        assert(after.old.rewardReceipt.newClass==4 and after.dualPreview==nil)
        assert(after.old.rewardReceipt.ownership=='unpartitioned_native_baseline')
        assert(a.m_baseStats.m_proficiencies[0]==1 and a.m_baseStats.m_xp==550000)
    ''')


def test_missing_or_stale_dual_preview_is_not_reconstructed_late(runtime):
    runtime.execute('''
        phase='SOD';ending=1
        local a=actor(500000,2,0,10);R.Adopt(a);a.m_baseStats.m_xp=550000
        local ok,why=pcall(R.PrepareDual,a,4)
        assert(not ok and tostring(why):find('baseline'))
        assert(R.CaptureDualPreview(a))
        local e=award(a,1);assert(R.BeforeAward(a,e)==1);assert(finishAward(a,e))
        ok,why=pcall(R.PrepareDual,a,4)
        assert(not ok and tostring(why):find('stale'))
        assert(a.aux.CBMBank.pendingDual==nil and a.m_baseStats.m_xp==550001)
        assert(R.CaptureDualPreview(a));assert(R.PrepareDual(a,4))
        assert(a.aux.CBMBank.pendingDual.after.old.total==550001)
    ''')


def test_reopened_dual_keeps_earliest_old_receipt_through_cancelled_inactive_choices(runtime):
    runtime.execute('''
        phase='SOD';ending=1
        local a=actor(500000,2,0,10);R.Adopt(a);a.m_baseStats.m_xp=550000
        a.m_baseStats.m_maxHitPointsBase=80;a.m_baseStats.m_proficiencies[0]=2
        a.m_derivedStats.GetAtOffset=function(_,stat) return stat==89 and 2 or 0 end
        assert(R.CaptureDualPreview(a))
        -- A cancelled new-class choice has no authority over the old receipt.
        -- Its inactive bits/legacy representation can differ without making
        -- the unchanged active old allocation ambiguous.
        a.m_derivedStats.GetAtOffset=function(_,stat) return stat==89 and 26 or 0 end
        a.m_baseStats.m_proficiencies[0]=26
        local e=award(a,1);assert(R.BeforeAward(a,e)==1);assert(finishAward(a,e))
        assert(R.CaptureDualPreview(a))
        local p=a.aux.CBMBank.dualPreview
        assert(p.before.proficiencies[1].active==2 and p.before.proficiencies[1].inactive==0)
        assert(p.before.legacyProficiencies[1]==2 and p.before.baseXP==550001)
        assert(p.ledgerRevision==a.aux.CBMBank.revision)
        assert(a.m_baseStats.m_proficiencies[0]==26)
        assert(R.PrepareDual(a,4))
    ''')


@pytest.mark.parametrize('changed', ['proficiency', 'skills', 'hp', 'kit'])
def test_same_level_mod_changes_preserve_both_preview_snapshots_without_value_gate(runtime,changed):
    runtime.globals().changed=changed
    runtime.execute('''
        phase='SOD';ending=1
        local a=actor(500000,2,0,10);R.Adopt(a);a.m_baseStats.m_xp=550000
        assert(R.CaptureDualPreview(a));local original=a.aux.CBMBank.dualPreview
        if changed=='proficiency' then
            a.m_derivedStats.GetAtOffset=function(_,stat) return stat==89 and 1 or 0 end
        elseif changed=='skills' then a.m_baseStats.m_pickPocketBase=1
        elseif changed=='hp' then a.m_baseStats.m_maxHitPointsBase=1
        else a.m_baseStats.m_mageSpecialization=1 end
        assert(R.CaptureDualPreview(a))
        local p=a.aux.CBMBank.dualPreview
        assert(p.ownership=='unpartitioned_native_baseline' and p.latestBeforePreview)
        assert(p.before.kit==original.before.kit and p.before.maxHPBase==original.before.maxHPBase)
        if changed=='proficiency' then assert(p.latestBeforePreview.proficiencies[1].active==1)
        elseif changed=='skills' then assert(p.latestBeforePreview.skills.m_pickPocketBase==1)
        elseif changed=='hp' then assert(p.latestBeforePreview.maxHPBase==1)
        else assert(p.latestBeforePreview.kit==1) end
        assert(a.aux.CBMBank.pendingDual==nil)
        -- An actual later old level establishes a fresh progression baseline.
        phase='SOA';ending=2
        a.m_baseStats.m_level1=11;a.m_baseStats.m_xp=750000
        assert(R.CaptureDualPreview(a))
        assert(a.aux.CBMBank.dualPreview.oldLevelAtDual==11)
    ''')


@pytest.mark.parametrize('base,percent',[(1000000,25),(50000000,100),(4294967295,4294967295),(161000,0)])
def test_effect_percent_preserves_native_low32_arithmetic(runtime,base,percent):
    runtime.globals().testBase=base
    runtime.globals().testPercent=percent
    runtime.globals().expectedPercent=((base*percent)&0xffffffff)//100
    runtime.execute('''
        local a=actor(1);R.Adopt(a);a.m_baseStats.m_xp=testBase
        a.writeBoundary={stage='preparing',incarnation=a.identity.incarnation,preBase=testBase,
            rawValue=testPercent,mode=2,source='opcode104',effectMode=2,origin='unclassified'}
        assert(R.BeforeWrite(a)==1 and a.writeBoundary.plannedBase==expectedPercent)
        a.writeBoundary.nativeResult=1;assert(finishWrite(a))
        assert(R.ActiveTotal(a)==expectedPercent)
        assert(a.aux.CBMBank.lastWrite.classification=='native_percent_low32')
        assert(a.aux.CBMBank.lastWrite.source=='opcode104')
    ''')


def test_percentage_with_overflow_reports_concrete_unsupported_policy(runtime):
    runtime.execute('''
        local a=actor(1);R.Adopt(a);a.m_baseStats.m_xp=4294967295;a.aux.CBMBank.overflow=100
        a.writeBoundary={stage='preparing',incarnation=a.identity.incarnation,preBase=4294967295,
            rawValue=50,mode=2,source='opcode104',effectMode=2,origin='unclassified'}
        local ok,why=pcall(R.BeforeWrite,a)
        assert(not ok and tostring(why):find('Unsupported opcode%-104 percentage'))
        assert(a.m_baseStats.m_xp==4294967295 and a.aux.CBMBank.overflow==100)
        assert(a.aux.CBMBank.pendingWrite==nil and a.writeBoundary.plannedBase==nil)
        -- The same numeric mode in SetAtOffset is SET, never percentage.
        assert(writeXP(a,50,2)==1);assert(finishWrite(a));assert(R.ActiveTotal(a)==50)
    ''')


def test_old_progression_supplies_released_entitlement_and_saved_kit_without_auto_level(runtime):
    runtime.execute('''
        phase='SOD';ending=1
        local a=actor(500000,2,0,10);R.Adopt(a);a.m_baseStats.m_xp=550000
        a.m_baseStats.m_mageSpecialization=123
        assert(R.CaptureDualPreview(a));assert(R.PrepareDual(a,4))
        a.m_startTypeAI.m_Class=9;a.m_baseStats.m_flags=8;a.m_baseStats.m_xp=0
        resetStage='completing';assert(R.CompleteDual(a,4))
        a.m_baseStats.m_xp=200000
        local s=R.OldProgression(a)
        assert(s.oldUsableXP==500000 and s.activeUsableXP==0 and s.oldLevel==10)
        assert(s.oldClass==2 and s.activeClass==4 and s.oldKit==123 and s.hasCleanReceipt)
        assert(s.ownerKey==a.aux.CBMBank.ownerKey and s.incarnation==a.identity.incarnation)
        phase='SOA';ending=2
        s=R.OldProgression(a)
        assert(s.oldUsableXP==550000 and s.activeUsableXP==200000 and s.oldLevel==10)
        assert(s.revision==a.aux.CBMBank.revision)
        assert(a.m_baseStats.m_level1==10 and a.m_baseStats.m_level2==1 and a.m_baseStats.m_xp==200000)
        s.oldUsableXP=1;assert(a.aux.CBMBank.old.usable==550000)
        -- Save evidence belongs to the saved owner, not an obsolete address's
        -- incarnation. A normal reload can still prove this actor's own dual.
        local payload=R.Export(a)
        local b=actor(200000,9,8,10);b.identity.incarnation='2'
        b.identity.ownerToken=string.rep('b',32);R.Import(b,payload)
        local reloaded=R.OldProgression(b)
        assert(reloaded.hasCleanReceipt and reloaded.oldKit==123 and reloaded.incarnation=='2')
    ''')


def test_old_progression_does_not_invent_history_or_resume_incomplete_manual_work(runtime):
    runtime.execute('''
        local a=actor(1000,9,8,7);R.Adopt(a)
        local s=R.OldProgression(a)
        assert(s.oldUsableXP==64000 and s.oldLevel==7 and not s.hasCleanReceipt)
        a.aux.CBMBank.pendingManualProgression={stage='uncertain'}
        local result,why=R.OldProgression(a)
        assert(result==nil and why:find('earlier native progression'))
        assert(a.aux.CBMBank.pendingManualProgression.stage=='uncertain')
        a.aux.CBMBank.pendingManualProgression=nil;a.identity.serializing=true
        result,why=R.OldProgression(a)
        assert(result==nil and why:find('mutable original actor'))
        local ordinary=actor(1000);R.Adopt(ordinary)
        result,why=R.OldProgression(ordinary)
        assert(result==nil and why:find('no retired class'))
    ''')


def test_chapter_caps_runtime_advances_stages_notices_and_supports_cdtweaks_ceiling(runtime):
    runtime.execute('''
        chapter=1
        function EEex_GameState_GetGlobalInt(key)
            if key=='ENDOFBG1' then return ending end
            if key=='INTOB' then return intoB end
            if key=='CHAPTER' then return chapter end
            error('unexpected global: '..tostring(key))
        end
        R.choice='chapter_caps'
        local a=actor(1000); R.OnLoaded(a)
        assert(a.aux.CBMBank.policy=='chapter_caps' and a.aux.CBMBank.phase=='CH1')
        a.m_baseStats.m_xp=9000000; a.m_derivedStats.m_nXP=9000000
        -- 4294967295 (0xFFFFFFFF) is the native ceiling when cdtweaks #2090 is installed.
        cap.BeforeNativeClamp(a,4294967295)
        assert(a.m_derivedStats.m_nXP==16000 and a.m_baseStats.m_xp==9000000)
        local notices=R.PendingNotices(a)
        assert(#notices.items==1 and notices.items[1].key=='cap:CH1')
        assert(notices.items[1].text=='Chapter XP limit reached: 16000. Further XP will be saved for a later chapter.')
        assert(R.AckNotice(a,notices.ownerKey,notices.incarnation,'cap:CH1'))
        -- Chapter 2 shares the 16,000 cap; no XP is released.
        chapter=2
        local view=R.Snapshot(a,4294967295)
        assert(view.phase=='CH2' and view.activeUsable==16000 and view.activeBank==8984000)
        notices=R.PendingNotices(a)
        assert(#notices.items==1 and notices.items[1].key=='cap:CH2')
        assert(R.AckNotice(a,notices.ownerKey,notices.incarnation,'cap:CH2'))
        -- Chapter 3 raises the cap to 20,000 and releases 4,000 banked XP.
        chapter=3
        view=R.Snapshot(a,4294967295)
        assert(view.phase=='CH3' and view.activeUsable==20000 and view.activeBank==8980000)
        notices=R.PendingNotices(a)
        assert(#notices.items==2 and notices.items[1].key=='release:CH2:CH3')
        assert(notices.items[1].text=='Chapter change: 4000 banked XP is now available for level-up.')
        assert(notices.items[2].key=='cap:CH3')
        -- Walk remaining EET chapters through ToB Finale (CH22 = 8,900,000).
        local schedule={
            {'BG1',0,0,4,'CH4',32000},
            {'BG1',0,0,5,'CH5',64000},
            {'BG1',0,0,6,'CH6',85000},
            {'BG1',0,0,7,'CH7',161000},
            {'SOD',1,0,7,'CH7',161000},
            {'SOD',1,0,8,'CH8',200000},
            {'SOD',1,0,9,'CH9',250000},
            {'SOD',1,0,10,'CH10',350000},
            {'SOD',1,0,11,'CH11',420000},
            {'SOD',1,0,12,'CH12',500000},
            {'SOD',1,0,13,'CH13',500000},
            {'SOA',2,0,13,'CH13',500000},
            {'SOA',2,0,14,'CH14',1000000},
            {'SOA',2,0,15,'CH15',2500000},
            {'SOA',2,0,16,'CH16',2900000},
            {'SOA',2,0,17,'CH17',3250000},
            {'SOA',2,0,18,'CH18',3500000},
            {'SOA',2,0,19,'CH19',3500000},
            {'TOB',2,1,20,'CH20',5000000},
            {'TOB',2,1,21,'CH21',8000000},
            {'TOB',2,1,22,'CH22',8900000},
        }
        for _,step in ipairs(schedule) do
            phase,ending,intoB,chapter=step[1],step[2],step[3],step[4]
            view=R.Snapshot(a,4294967295)
            assert(view.phase==step[5] and view.cap==step[6])
            assert(view.activeUsable==step[6] and view.activeBank==9000000-step[6])
        end
        assert(R.Status(a,4294967295)=='Usable XP: 8900000; banked XP: 100000; cap: 8900000; campaign: CH22')
    ''')


def test_chapter_caps_awards_and_setters_during_chapter_initialization(runtime):
    # With chapter caps, a party member adopted before CHAPTER is initialized (EET's BG1
    # prologue runs at CHAPTER 0) must still receive XP awards and setters. The pending
    # adoption is validated against the policy's first phase (CH1), not the BG1 campaign.
    runtime.execute('''
        chapter=0
        function EEex_GameState_GetGlobalInt(key)
            if key=='ENDOFBG1' then return ending end
            if key=='INTOB' then return intoB end
            if key=='CHAPTER' then return chapter end
            error('unexpected global: '..tostring(key))
        end
        R.choice='chapter_caps'
        local a=actor(0); R.OnLoaded(a)
        assert(a.aux.CBMBank.initializing and a.aux.CBMBank.policy=='chapter_caps')
        local e=award(a,100); assert(R.BeforeAward(a,e)==1); assert(finishAward(a,e))
        assert(a.m_baseStats.m_xp==100 and a.aux.CBMBank.initializing and a.aux.CBMBank.baseAtAdoption==0)
        assert(writeXP(a,40,1)==1); assert(finishWrite(a))
        assert(a.m_baseStats.m_xp==140 and a.aux.CBMBank.initializing)
        local fresh=actor(0); e=award(fresh,50)
        assert(R.BeforeAward(fresh,e)==1); assert(finishAward(fresh,e))
        assert(fresh.m_baseStats.m_xp==50 and fresh.aux.CBMBank.baseAtAdoption==0)
        chapter=1
        local view=R.Snapshot(a,4294967295)
        assert(view.phase=='CH1' and view.activeUsable==140 and a.aux.CBMBank.floor==0)
        e=award(a,20000); assert(R.BeforeAward(a,e)==1); assert(finishAward(a,e))
        view=R.Snapshot(a,4294967295)
        assert(view.activeUsable==16000 and view.activeBank==4140)
    ''')


def test_chapter_caps_standalone_mode_maps_bg2_chapters_to_canonical_phases(runtime):
    runtime.execute('''
        chapter=1; ending=0; intoB=0; phase='SOA'
        function EEex_GameState_GetGlobalInt(key)
            if key=='ENDOFBG1' then return ending end
            if key=='INTOB' then return intoB end
            if key=='CHAPTER' then return chapter end
            error('unexpected global: '..tostring(key))
        end
        R.choice='chapter_caps'; R.standalone=true
        local a=actor(89000); R.OnLoaded(a)
        assert(a.aux.CBMBank.phase=='CH13')
        a.m_baseStats.m_xp=9000000
        local schedule={
            {'SOA',0,1,'CH13',500000},
            {'SOA',0,2,'CH14',1000000},
            {'SOA',0,3,'CH15',2500000},
            {'SOA',0,4,'CH16',2900000},
            {'SOA',0,5,'CH17',3250000},
            {'SOA',0,6,'CH18',3500000},
            {'SOA',0,7,'CH19',3500000},
            {'TOB',1,8,'CH20',5000000},
            {'TOB',1,9,'CH21',8000000},
            {'TOB',1,10,'CH22',8900000},
        }
        for _,step in ipairs(schedule) do
            phase,intoB,chapter=step[1],step[2],step[3]
            local view=R.Snapshot(a,4294967295)
            assert(view.phase==step[4] and view.cap==step[5] and view.activeUsable==step[5])
        end
    ''')

