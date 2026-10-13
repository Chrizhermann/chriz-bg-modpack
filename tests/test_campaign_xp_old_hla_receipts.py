"""Durable ownership/ordering checks; native effects are explicit test doubles."""
from importlib import import_module, util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1] / 'research'


def setup(lua):
    for name, path in {'Store':'xp-banking/cbmbank_store.lua', 'Account':'xp-banking/native_account.lua',
                       'Receipts':'xp-banking-native/dual_old_hla_receipts.lua'}.items():
        lua.globals()[name] = lua.execute((ROOT/path).read_text())
    lua.execute('''
        function EEex_GetUDAux(s)return s.aux end
        function copy(x)local v,e=Store.WireSnapshot(x);assert(v,e);return v end
        owner=string.rep('a',32)
        c=Account.AdoptExistingDual('bg1_sod','SOA',100000,2,4,10,500000)
        c.ownerKey=owner;c.old.pendingHLAs={}
        s={aux={CBMBank=c,CBMBankLifetime={ownerKey=owner,incarnation='7',origin='save_load'}}}
        identity={eligible=true,canMutate=true,serializing=false,incarnation='7'}
        v={phase='committing',incarnation='7',owner=owner,session='12'}
        function item(i)
            return {id=i,descriptor={schema=1,icon='SPCL900',nameStrref=4294967295,
              minLevel=4294967096,maxLevel=4294927296,maxRank=4294967295,
              effect='GA_ABILITY'..i,prerequisite='*',excludedBy='*',alignment='ALL_GOOD'}}
        end
        a={ownerKey=owner,incarnation='7',oldClass=2,activeClass=4,oldKit=16384,
           oldLevel=10,hasCleanReceipt=true}
        function begin(choices)
          s.aux.CBMBank.pendingManualProgression={schema=1,ownerKey=owner,incarnation='7',
            session=v.session,stage='committing',retired={account=copy(a),target=11,choices={hlas=choices}}}
        end
        dormant=true;calls=0;outcome=1
        native={Deliver=function(actor,old,saved,list)
          calls=calls+1;assert(actor==s and old==2 and saved==owner)
          local journal=s.aux.CBMBank.old.pendingHLADelivery
          assert(journal and journal.stage=='delivering' and journal.count==#list)
          assert(not dormant)
          if beforeDelivery then beforeDelivery(list)end
          if outcome=='error'then error('native interruption')end
          return outcome,math.ceil(#list/24)
        end}
        q=Receipts.New{wire=Store,account=Account,identity={Query=function()return identity end},
          manual={Query=function()return v end,Dormant=function()return dormant end},native=native}
    ''')
    return lua


@pytest.fixture(params=['lua51','luajit21'])
def lua(request):
    return setup(import_module('lupa.'+request.param).LuaRuntime(unpack_returned_tuples=True))


def test_preview_is_detached_and_never_grants_or_double_counts(lua):
    lua.execute('''
      s.aux.CBMBank.old.pendingHLAs={item(1)};begin({item(2),item(2)})
      local selected=q.Preview(s);assert(#selected==3 and calls==0)
      selected[1].descriptor.effect='changed';assert(q.Pending(s)[1].descriptor.effect=='GA_ABILITY1')
      assert(q.Prepare(s));assert(#q.Preview(s)==3 and calls==0)
      assert(not pcall(q.Prepare,s));assert(#q.Pending(s)==3)
    ''')


def test_dormancy_retains_order_for_later_active_only_commit(lua):
    lua.execute('''
      begin({item(0),item(3)});q.Prepare(s);q.Commit(s)
      assert(calls==0 and #q.Pending(s)==2)
      assert(s.aux.CBMBank.pendingManualProgression.oldHLA.stage=='deferred')
      -- A later ordinary active level-up has no new old interval/choices.
      s.aux.CBMBank.pendingManualProgression=nil;v.session='13';begin({})
      s.aux.CBMBank.pendingManualProgression.retired=nil
      dormant=false;q.Prepare(s);q.Commit(s)
      assert(calls==1 and #q.Pending(s)==0)
      assert(not pcall(q.Commit,s))
    ''')


def test_more_than_24_and_native_xp_awards_survive_delivery(lua):
    lua.execute('''
      local selected={};for i=1,55 do selected[i]=item(i)end
      begin(selected);q.Prepare(s);dormant=false
      beforeDelivery=function(list)
        assert(#list==55 and list[55].descriptor.effect=='GA_ABILITY55')
        local changed=copy(s.aux.CBMBank);changed.revision=changed.revision+1
        changed.overflow=71;s.aux.CBMBank=changed
      end
      q.Commit(s);assert(s.aux.CBMBank.overflow==71 and s.aux.CBMBank.revision==1)
      assert(s.aux.CBMBank.pendingManualProgression.oldHLA.completedBatches==3)
    ''')


@pytest.mark.parametrize('outcome',['-1','0',"'error'"])
def test_failed_delivery_keeps_journal_and_never_retries(lua,outcome):
    lua.execute("outcome="+outcome)
    lua.execute('''
      begin({item(4)});q.Prepare(s);dormant=false
      assert(not pcall(q.Commit,s));assert(calls==1)
      assert(s.aux.CBMBank.old.pendingHLADelivery.stage=='uncertain')
      assert(#s.aux.CBMBank.old.pendingHLAs==1)
      assert(not pcall(q.Pending,s) and not pcall(q.Preview,s) and not pcall(q.Commit,s))
      assert(calls==1 and Store.WireSnapshot(s.aux.CBMBank))
    ''')


@pytest.mark.parametrize('change',[
    "identity.incarnation='8'", "s.aux.CBMBankLifetime.ownerKey='wrong'",
    "v.session='other'", "v.phase='preview'", "identity.serializing=true",
    "s.aux.CBMBank.pendingManualProgression.retired.account.hasCleanReceipt=false",
])
def test_wrong_owner_boundary_or_unearned_choices_never_publish(lua,change):
    lua.execute('begin({item(1)})')
    lua.execute(change)
    lua.execute('''
      local original=s.aux.CBMBank
      assert(not pcall(q.Prepare,s));assert(s.aux.CBMBank==original and calls==0)
    ''')


def test_oversized_queue_fails_before_native_commit(lua):
    lua.execute('''
      local selected={};for i=1,250 do selected[i]=item(i)end
      begin(selected);local original=s.aux.CBMBank
      assert(not pcall(q.Prepare,s));assert(s.aux.CBMBank==original and calls==0)
    ''')


def test_zero_choices_require_no_dormancy_or_native_call(lua):
    lua.execute('''
      begin({});q.Prepare(s);q.Commit(s)
      assert(calls==0 and s.aux.CBMBank.pendingManualProgression.oldHLA.stage=='complete')
    ''')


# Execute the pinned unmodified EEex serializer on the real queue shape.
spec = util.spec_from_file_location('old_hla_serializer_fixture',ROOT/'xp-banking-native/identity_serializer_test.py')
serializer = util.module_from_spec(spec)
spec.loader.exec_module(serializer)
wire = serializer.wire


def test_actual_eeex_marshal_preserves_descriptors_and_uncertain_journal(wire):
    runtime,_ = wire
    setup(runtime)
    original = runtime.execute('''
      begin({item(0),item(1)});q.Prepare(s);dormant=false;outcome='error';pcall(q.Commit,s)
      register('CBMBank',function()return copy(s.aux.CBMBank)end,function(actor,p)actor.received=p end)
      return copy(s.aux.CBMBank)
    ''')
    restored,_ = runtime.globals().marshal(runtime.table_from({'aux':runtime.table()}))
    assert serializer.plain(restored) == serializer.plain(original)
