"""Read-only record-screen bank projection; synthetic actors, no game UI."""
import pytest

from tests.test_campaign_xp_native_runtime import runtime


@pytest.fixture
def record_runtime(runtime):
    runtime.execute('''
        -- Remember every actor table and field, including table identities.
        -- A draw must not replace even an otherwise identical account table.
        function checkpoint(root)
            local tables={}
            local function visit(value)
                if type(value)~='table' or tables[value] then return end
                local fields={};tables[value]=fields
                for key,item in pairs(value) do fields[key]=item;visit(item) end
            end
            visit(root)
            return function()
                for object,fields in pairs(tables) do
                    for key,item in pairs(fields) do
                        assert(object[key]==item,'changed field: '..tostring(key))
                    end
                    for key,item in pairs(object) do
                        assert(fields[key]==item,'added field: '..tostring(key))
                    end
                end
            end
        end
        function bankedDual()
            phase='SOD';ending=1
            local a=actor(500000,2,0,10);R.Adopt(a)
            a.m_baseStats.m_xp=550000
            assert(R.CaptureDualPreview(a));assert(R.PrepareDual(a,4))
            -- The same native-reset fixture used by the accounting tests.
            resetStage='native';a.m_baseStats.m_xp=0
            a.m_startTypeAI.m_Class=9;a.m_baseStats.m_flags=8
            resetStage='completing';assert(R.CompleteDual(a,4))
            a.m_baseStats.m_xp=200000
            return a
        end
    ''')
    return runtime


@pytest.mark.parametrize("initial,current,native,bank,cap", [
    (1000, 1000, 8000000, 0, 161000),
    (1000, 600000, 8000000, 439000, 161000),
    (700000, 800000, 8000000, 100000, 700000),
    (1000, 600000, 100000, 500000, 100000),
])
def test_draw_uses_existing_cap_floor_and_bank_without_touching_actor(
        record_runtime, initial, current, native, bank, cap):
    record_runtime.globals().initial = initial
    record_runtime.globals().current = current
    record_runtime.globals().native = native
    record_runtime.globals().expectedBank = bank
    record_runtime.globals().expectedCap = cap
    record_runtime.execute('''
        local a=actor(initial);R.Adopt(a);a.m_baseStats.m_xp=current
        a.aux.CBMBank.notices={schema=1,seen={},pending={{key='kept',text='Keep this notice.'}}}
        local unchanged=checkpoint(a)
        for _=1,5 do
            local view=assert(R.RecordView(a,native))
            assert(view.bank==expectedBank and view.cap==expectedCap)
            assert(view.phase=='BG1' and view.policy=='bg1_sod')
            view.bank=-1;view.cap=-1 -- Returned presentation data is detached.
            unchanged()
        end
    ''')


@pytest.mark.parametrize("saved_policy,soa_bank,soa_cap", [
    ("bg1_sod", 0, 8000000),
    ("bg1_sod_soa", 550000, 2950000),
])
def test_campaign_projection_uses_saved_policy_without_saving_or_notifying(
        record_runtime, saved_policy, soa_bank, soa_cap):
    record_runtime.globals().savedPolicy = saved_policy
    record_runtime.globals().soaBank = soa_bank
    record_runtime.globals().soaCap = soa_cap
    record_runtime.execute('''
        R.choice=savedPolicy
        local a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=3500000
        R.choice=savedPolicy=='bg1_sod' and 'bg1_sod_soa' or 'bg1_sod'
        local unchanged=checkpoint(a)
        local checks={{'BG1',0,0,3339000,161000},{'SOD',1,0,3000000,500000},
            {'SOA',2,0,soaBank,soaCap},{'TOB',2,1,0,8000000}}
        for _,check in ipairs(checks) do
            phase,ending,intoB=check[1],check[2],check[3]
            for _=1,3 do
                local view=assert(R.RecordView(a,8000000))
                assert(view.phase==phase and view.policy==savedPolicy)
                assert(view.bank==check[4] and view.cap==check[5])
                unchanged()
            end
        end
        assert(a.aux.CBMBank.phase=='BG1' and a.aux.CBMBank.notices==nil)
    ''')


@pytest.mark.parametrize("class_id", [7, 10])
def test_multiclass_displays_one_shared_bank(record_runtime, class_id):
    record_runtime.globals().classID = class_id
    record_runtime.execute('''
        local a=actor(1000,classID);R.Adopt(a);a.m_baseStats.m_xp=600000
        local unchanged=checkpoint(a)
        assert(a.aux.CBMBank.kind=='multi')
        local view=assert(R.RecordView(a,8000000))
        assert(view.bank==439000 and view.cap==161000)
        unchanged()
    ''')


def test_dual_display_combines_both_banks_and_projects_release_without_committing(record_runtime):
    record_runtime.execute('''
        local a=bankedDual()
        local unchanged=checkpoint(a)
        local view=assert(R.RecordView(a,8000000))
        assert(view.bank==250000 and view.cap==500000 and view.phase=='SOD')
        unchanged()
        phase='SOA';ending=2
        for _=1,3 do
            view=assert(R.RecordView(a,8000000))
            assert(view.bank==0 and view.cap==8000000 and view.phase=='SOA')
            unchanged()
        end
        assert(a.aux.CBMBank.phase=='SOD' and a.aux.CBMBank.old.usable==500000)
        assert(a.aux.CBMBank.old.total==550000 and a.m_baseStats.m_xp==200000)
    ''')


@pytest.mark.parametrize("unresolved", [
    "a.aux.CBMBank=nil",
    "a.aux.CBMBank.excluded=true",
    "a.identity.eligible=false",
    "a.identity.serializing=true",
    "a.aux.CBMBank.initializing=true",
    "a.aux.CBMBank.chrPending={};a.aux.CBMBankLifetime.origin='chr_import'",
    "a.aux.CBMBank.pendingDual={stage='uncertain'}",
    "a.aux.CBMBank.pendingAward={stage='uncertain'}",
    "a.aux.CBMBank.pendingWrite={stage='uncertain'}",
    "a.aux.CBMBank.pendingManualProgression={stage='uncertain'}",
])
def test_unresolved_account_hides_without_reconciliation(record_runtime, unresolved):
    record_runtime.globals().unresolved = unresolved
    record_runtime.execute('''
        a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=600000
        assert(loadstring(unresolved))()
        local unchanged=checkpoint(a)
        for _=1,3 do assert(R.RecordView(a,8000000)==nil);unchanged() end
    ''')


def test_pending_retired_account_hides_without_mutation(record_runtime):
    record_runtime.execute('''
        local a=bankedDual();a.aux.CBMBank.old.pendingHLADelivery={stage='uncertain'}
        local unchanged=checkpoint(a)
        assert(R.RecordView(a,8000000)==nil)
        unchanged()
    ''')


@pytest.mark.parametrize("damage", [
    "a.identity.incarnation='2'",
    "a.aux.CBMBankLifetime.ownerKey='wrong owner'",
    "a.m_startTypeAI.m_Class=7",
])
def test_invalid_lifetime_or_class_never_clears_or_rebinds_bank(record_runtime, damage):
    record_runtime.globals().damage = damage
    record_runtime.execute('''
        a=actor(1000);R.Adopt(a);a.m_baseStats.m_xp=600000
        assert(loadstring(damage))()
        local unchanged=checkpoint(a)
        local ok,why=pcall(R.RecordView,a,8000000)
        assert(not ok and (tostring(why):find('bound') or tostring(why):find('class/account')))
        unchanged()
    ''')


def test_display_neither_decides_nor_shows_a_pending_unbanked_dual(record_runtime):
    record_runtime.execute('''
        local a=actor(80000,2,0,7);R.Adopt(a)
        local unchanged=checkpoint(a)
        assert(R.RecordView(a,8000000).bank==0)
        unchanged()
        -- The no-bank dual rule (vanilla threshold debit) lives in the account;
        -- the record view only reads and hides a half-prepared dual.
        assert(R.CaptureDualPreview(a));assert(R.PrepareDual(a,4))
        assert(a.aux.CBMBank.pendingDual~=nil and a.m_baseStats.m_xp==80000)
        assert(R.RecordView(a,8000000)==nil)
    ''')
