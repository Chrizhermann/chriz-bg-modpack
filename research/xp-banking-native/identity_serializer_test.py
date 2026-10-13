"""Pinned EEex serializer integration; offline memory and actor fixtures only.

Runs the ACTUAL unmodified size/write/read functions in Lua 5.2 and LuaJIT.
EEex's serializer uses goto and therefore cannot run in stock Lua 5.1. The
banking store/loader itself additionally gets Lua 5.1 checks. No save is read.
"""
from importlib import import_module
from pathlib import Path
import os

import pytest

ROOT = Path(__file__).resolve().parent
EEEX = Path(os.environ.get("CBMI_EEEX_SOURCE", "C:/tmp/scroll-hook-research-20261009/EEex/EEex/copy/EEex_scripts/EEex_Sprite.lua"))


def plain(value):
    if hasattr(value, "items"):
        return {plain(k): plain(v) for k, v in value.items()}
    return value


@pytest.fixture(params=["lua52", "luajit21"])
def wire(request):
    lua = import_module("lupa."+request.param).LuaRuntime(unpack_returned_tuples=True, encoding="latin-1")
    memory = bytearray(65536)
    g = lua.globals()
    def write(at, value, size, signed):
        assert 0 <= at < len(memory)-size
        # InfinityLoader range-checks every typed write (castLuaIntArg).
        low, high = (-(1 << (size*8-1)), (1 << (size*8-1))-1) if signed else (0, (1 << (size*8))-1)
        assert value == int(value) and low <= int(value) <= high, f"arg #2 ({value}) outside {low}..{high}"
        memory[at:at+size] = (int(value) & ((1 << (size*8))-1)).to_bytes(size, "little")
    def read(at, size, signed):
        assert 0 <= at < len(memory)-size
        return int.from_bytes(memory[at:at+size], "little", signed=signed)
    for size in (1, 2, 4, 8):
        for unsigned in (False, True):
            suffix = ("U" if unsigned else "")+str(size*8)
            g["EEex_Write"+suffix] = lambda at, value, n=size, s=not unsigned: write(int(at), value, n, s)
            g["EEex_Read"+suffix] = lambda at, n=size, signed=not unsigned: read(int(at), n, signed)
    def write_string(at, value, count=None):
        data = value.encode("latin-1")
        data = data[:int(count)] if count is not None else data+b"\0"
        assert 0 <= at < len(memory)-len(data)
        memory[int(at):int(at)+len(data)] = data
    def read_string(at):
        at = int(at)
        return bytes(memory[at:memory.index(0, at)]).decode("latin-1")
    def memset(at, value, count): memory[int(at):int(at+count)] = bytes([int(value)])*int(count)
    g.EEex_WriteString, g.EEex_WriteLString = write_string, write_string
    g.EEex_ReadString, g.EEex_Memset = read_string, memset
    lua.execute("""
        CGameEffectBase={sizeof=264}; failures={}
        function EEex_Error(message) error(message) end
        function EEex_RoundUp(n,chunk) return math.ceil(n/chunk)*chunk end
        function EEex_GetUDAux(sprite) return sprite.aux end
        function EEex_Utility_GetOrCreateTable(t,key) t[key]=t[key] or {}; return t[key] end
        function EEex_Utility_TryIgnore(fn,...)
            local ok,value=pcall(fn,...)
            if ok then return value end
            failures[#failures+1]=tostring(value)
        end
        EEex_Sprite_Private_MarshalHandlers={}
        function register(name,exporter,importer)
            EEex_Sprite_Private_MarshalHandlers[name]={exporter=exporter,importer=importer}
        end
    """)
    source = EEEX.read_text(encoding="utf-8")
    start = source.index("EEex_Sprite_Private_MarshalHandlerFieldType = {")
    end = source.index("EEex_Sprite_Private_CustomConcentrationCheckFuncName = nil",start)
    lua.execute(source[start:end])
    g.storeModule = lua.execute((ROOT.parent/"xp-banking/cbmbank_store.lua").read_text())
    lua.execute("""
        adapter={validatePayload=function(p)
            if p.schema~=1 then return 'opaque','future policy' end
            if type(p.bank)~='number' then return nil,'invalid bank' end
            return true
        end}
        function makeStore(payload)
            local s=assert(storeModule.New(adapter))
            assert(s:Import(payload,{verified=true,reason='save_load',ownerKey='owner-A'}))
            return s
        end
        function attach(s,reason)
            register('CBM_BANK',function()
                local value,why=s:Export({verified=true,reason=reason,ownerKey='owner-A'})
                -- Explicit preservation path: EEex otherwise drops handler data
                -- on exceptions. This fixture is not a native save-abort claim.
                if not value then value=select(1,s:View()) end
                return value
            end,function(actor,payload) actor.received=payload end)
        end
        function marshal(actor,afterSize)
            local size=EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize(actor)
            if afterSize then afterSize() end
            EEex_Sprite_Hook_WriteExtraEffectListMarshal(4096)
            local receiver={aux={}}
            local effects=EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal(receiver,4096)
            assert(effects*264==size)
            return receiver.received, size
        end
    """)
    return lua, memory


@pytest.mark.parametrize("reason", ["save", "chr_export", "unsupported_boundary"])
@pytest.mark.parametrize("future", [False, True])
def test_known_and_opaque_carriers_round_trip(wire, reason, future):
    lua, memory = wire
    payload = lua.execute("""return {storeSchema=1,ownerKey='owner-A',revision=17,mode='active',
        payload={schema=1,bank=439000,usable=161000,phase='BG1',policy='bg1_sod'},
        extension={high=9007199254740991,minus=-4294967297,flag=true,empty={},word='untouched'}}""")
    if future:
        payload.storeSchema = 72
        payload.payload.schema = 901
    before = plain(payload)
    store = lua.globals().makeStore(payload)
    lua.globals().attach(store, reason)
    receiver, size = lua.globals().marshal(lua.table_from({"aux": lua.table()}))
    assert plain(receiver) == before
    assert memory[4096:4104] == b"X-BIV1.0"
    assert size % 264 == 0 and size > 8
    assert len(lua.globals().failures) == 0


def test_size_write_snapshot_is_detached_and_import_failure_preserves_it(wire):
    lua, _ = wire
    result = lua.execute("""
        local p={storeSchema=1,ownerKey='owner-A',revision=3,mode='active',
            payload={schema=1,bank=439000,usable=161000},extension={flag='before'}}
        local s=makeStore(p)
        local bad={}; bad.self=bad
        assert(not s:Import(bad,{verified=true,reason='save_load',ownerKey='owner-A'}))
        attach(s,'save')
        local out=marshal({aux={}},function()
            p.payload.bank=0; p.extension.flag='mutated'
            local detached=s:View(); detached.payload.bank=1
        end)
        assert(out.payload.bank==439000 and out.extension.flag=='before')
        local older=makeStore(out)
        attach(older,'save')
        return marshal({aux={}})
    """)
    assert plain(result[0])["payload"]["bank"] == 439000


def test_absent_handler_fallback_preserves_unknown_payload(wire):
    lua, _ = wire
    received = lua.execute("""
        local future={storeSchema=79,ownerKey='owner-A',newField={bank='000439000'}}
        local actor={aux={EEex_Sprite_FallbackMarshalStorage={CBM_BANK=future}}}
        local size=EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize(actor)
        EEex_Sprite_Hook_WriteExtraEffectListMarshal(4096)
        local recipient={aux={}}
        assert(EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal(recipient,4096)*264==size)
        return recipient.aux.EEex_Sprite_FallbackMarshalStorage.CBM_BANK
    """)
    assert plain(received) == {"storeSchema":79,"ownerKey":"owner-A","newField":{"bank":"000439000"}}


def runtime_fixture(lua):
    """The adapter is real; identities here deliberately model native Query.

    The C++ test and real PE probe independently check the identity provider.
    This test does not present synthetic identity data as native execution.
    """
    g=lua.globals()
    g.R=lua.execute((ROOT/"bank_runtime.lua").read_text())
    g.policy=lua.execute((ROOT.parent/"xp-banking/cbmbank_policy.lua").read_text())
    g.account=lua.execute((ROOT.parent/"xp-banking/native_account.lua").read_text())
    g.receipts=lua.execute((ROOT/"dual_reward_receipts.lua").read_text())
    lua.execute("""
        CBMBank_Identity={Query=function(sprite)
            if sprite.identityMissing then return nil,'synthetic missing native lifetime' end
            return sprite.identity
        end}
        EngineGlobals={g_pBaldurChitin={m_pObjectGame={m_sCurrentCampaign={m_pchData={get=function() return 'BG1' end}}}}}
        function EEex_GameState_GetGlobalInt() return 0 end
        function EEex_Sprite_GetCharacterIndex(sprite) return sprite.party or 0 end
        function EEex_UDToPtr(value) return value.pointer end
        function EEex_Sprite_GetActiveStats(a) return a.m_derivedStats end
        function actor(token,generation,birth)
            local a={aux={},party=0,m_baseStats={m_xp=161000,m_flags=0,m_level1=8,m_level2=0},
                m_derivedStats={GetAtOffset=function() return 0 end},
                m_timedEffectList={},m_equipedEffectList={},
                m_startTypeAI={m_Class=2},identity={ownerToken=token,incarnation=generation,
                birthReason=birth or 'world',reason='world',eligible=true,serializing=false,canMutate=true}}
            for _,field in ipairs({'m_mageSpecUpperWord','m_mageSpecialization','m_level3','m_maxHitPointsBase',
                'm_hideInShadowsBase','m_detectIllusionBase','m_setTrapsBase','m_lockPickingBase',
                'm_moveSilentlyBase','m_trapsBase','m_pickPocketBase'}) do a.m_baseStats[field]=0 end
            a.m_baseStats.m_proficiencies={}; for i=0,14 do a.m_baseStats.m_proficiencies[i]=0 end
            return a
        end
        R.Configure(policy,account,storeModule,'bg1_sod',receipts)
        register('CBM_BANK',R.Export,R.Import)
        function runtimeMarshal(sender,receiver)
            sender.identity.serializing=true; sender.identity.canMutate=false
            local size=EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize(sender)
            EEex_Sprite_Hook_WriteExtraEffectListMarshal(4096)
            sender.identity.serializing=false; sender.identity.canMutate=true
            assert(EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal(receiver,4096)*264==size)
        end
        donor=actor(string.rep('a',32),'1'); R.Adopt(donor); donor.m_baseStats.m_xp=600000
    """)


def test_actual_runtime_save_and_chr_provenance_through_real_serializer(wire):
    lua,_=wire
    runtime_fixture(lua)
    lua.execute("""
        local saved=actor(string.rep('b',32),'2'); saved.m_baseStats.m_xp=600000
        donor.identity.reason='save'; runtimeMarshal(donor,saved); R.OnLoaded(saved)
        local view=R.Snapshot(saved,8000000)
        assert(view.total==600000 and view.activeBank==439000 and view.activeUsable==161000)
        assert(saved.aux.CBMBank.ownerKey==string.rep('a',32))
        local chr=actor(string.rep('c',32),'3','chr_import'); chr.m_baseStats.m_xp=600000
        donor.identity.reason='chr_export'; runtimeMarshal(donor,chr)
        assert(chr.aux.CBMBank.ownerKey==string.rep('a',32))
        local ok,reason=pcall(R.Snapshot,chr,8000000)
        assert(not ok and tostring(reason):find('CHR'))
        assert(chr.aux.CBMBank.phase=='BG1' and donor.aux.CBMBank.phase=='BG1')
        assert(#failures==0)
    """)


@pytest.mark.parametrize("future",[False,True])
def test_actual_runtime_clone_exclusion_survives_save_reload(wire,future):
    lua,_=wire
    runtime_fixture(lua)
    lua.globals().future=future
    lua.execute("""
        local original=donor.aux.CBMBank
        if future then
            original={schema=99,futureBank={old=439000},opaqueString='preserve me'}
            donor.aux.CBMBank=original
        end
        local clone=actor('', '2','magical_clone'); clone.identity.eligible=false
        donor.identity.reason='magical_clone'; runtimeMarshal(donor,clone)
        assert(clone.aux.CBMBank.excluded==true)
        if future then assert(clone.aux.CBMBank.carrier.futureBank.old==439000) end
        donor.identity.reason='world'
        local savedClone=actor(string.rep('c',32),'3')
        clone.identity.reason='save'; runtimeMarshal(clone,savedClone)
        assert(not R.Snapshot(savedClone,8000000).eligible)
        if future then assert(savedClone.aux.CBMBank.carrier.futureBank.old==439000) end
        assert(donor.aux.CBMBank==original and #failures==0)
    """)


def test_actual_runtime_failed_identity_export_retains_carrier(wire):
    lua,_=wire
    runtime_fixture(lua)
    lua.execute("""
        donor.identityMissing=true
        local recipient=actor(string.rep('d',32),'4'); recipient.m_baseStats.m_xp=600000
        runtimeMarshal(donor,recipient)
        assert(recipient.aux.CBMBank and recipient.aux.CBMBank.excluded
            and recipient.aux.CBMBank.carrier.ownerKey==string.rep('a',32),
            'EEex omitted the carrier after native identity lookup failed')
        assert(not R.Snapshot(recipient,8000000).eligible)
    """)


def test_actual_runtime_failed_identity_import_retains_incoming_carrier(wire):
    lua,_=wire
    runtime_fixture(lua)
    lua.execute("""
        local recipient=actor(string.rep('d',32),'4'); recipient.m_baseStats.m_xp=600000
        recipient.identityMissing=true
        runtimeMarshal(donor,recipient)
        assert(recipient.aux.CBMBank and recipient.aux.CBMBank.excluded
            and recipient.aux.CBMBank.carrier.ownerKey==string.rep('a',32),
            'EEex discarded an incoming carrier after native identity lookup failed')
    """)


def test_stale_uda_aux_cannot_export_previous_lifetimes_bank(wire):
    lua,_=wire
    runtime_fixture(lua)
    lua.execute("""
        local old=donor.aux.CBMBank
        -- Native constructor/destructor independently establish a new lifetime
        -- even if EEex's UDAux pointer entry survived temporary destruction.
        donor.identity.incarnation='999'; donor.identity.ownerToken=string.rep('e',32)
        local receiver=actor(string.rep('f',32),'1000')
        runtimeMarshal(donor,receiver)
        assert(receiver.aux.CBMBank==nil)
        R.OnLoaded(donor)
        assert(donor.aux.CBMBank~=old and donor.aux.CBMBank.ownerKey==string.rep('e',32))
        assert(donor.aux.CBMBank.floor==600000)
    """)


@pytest.mark.parametrize("finish",["complete","uncertain"])
def test_actual_runtime_partial_dual_saves_the_pre_reset_journal(wire,finish):
    lua,_=wire
    runtime_fixture(lua)
    lua.globals().finish=finish
    lua.execute("""
        function EEex_Resource_Load2DA(name)
            assert(name=='XPLEVEL')
            return {getAtLabels=function(self,level,class)
                assert(level=='8' and class=='FIGHTER'); return '125000'
            end}
        end
        local stage='preparing'
        CBMBank_Reset={NativeCap=function() return 8000000 end,PreviewQuery=function(sprite)
            if sprite~=donor then return nil end
            return {stage='capturing',incarnation='1',preBase=600000}
        end,Query=function(sprite)
            if sprite~=donor then return nil end
            return {stage=stage,incarnation='1',preBase=600000,newClass=4}
        end}
        assert(R.CaptureDualPreview(donor)); assert(R.PrepareDual(donor,4))
        assert(donor.aux.CBMBank.pendingDual.preBase==600000)
        stage='native'
        donor.m_baseStats.m_xp=0; donor.m_baseStats.m_flags=8
        donor.m_baseStats.m_level2=1; donor.m_startTypeAI.m_Class=9
        local during=R.Snapshot(donor,8000000)
        assert(during.total==600000 and during.activeBank==0 and during.oldBank==439000)
        local recovered=actor(string.rep('b',32),'2')
        recovered.m_baseStats={m_xp=0,m_flags=8,m_level1=8,m_level2=1}
        recovered.m_startTypeAI.m_Class=9
        runtimeMarshal(donor,recovered)
        assert(recovered.aux.CBMBank.pendingDual.preBase==600000)
        local ok,why=pcall(R.Snapshot,recovered,8000000)
        assert(not ok and tostring(why):find('reconciliation'))
        if finish=='complete' then
            stage='completing'; assert(R.CompleteDual(donor,4))
            assert(donor.aux.CBMBank.pendingDual==nil)
            assert(R.Snapshot(donor,8000000).total==600000)
        else
            stage='uncertain'; R.UncertainDual(donor)
            assert(donor.aux.CBMBank.pendingDual.preBase==600000)
            assert(donor.aux.CBMBank.pendingDual.stage=='uncertain')
            local still={aux={},identity=recovered.identity,party=0}
            runtimeMarshal(donor,still)
            assert(still.aux.CBMBank.pendingDual.preBase==600000)
            assert(still.aux.CBMBank.pendingDual.stage=='uncertain')
        end
        assert(#failures==0)
    """)


@pytest.mark.parametrize("finish",["complete","uncertain"])
def test_actual_runtime_overflow_award_carrier_and_pending_recovery_round_trip(wire,finish):
    lua,_=wire
    runtime_fixture(lua)
    lua.globals().finish=finish
    lua.execute("""
        donor.m_baseStats.m_xp=4294967280
        local effect={pointer=0x1234}
        local stage='preparing'
        CBMBank_Reset={NativeCap=function()return 8000000 end}
        CBMBank_Award={Query=function(sprite,actualEffect)
            if sprite~=donor or effect~=actualEffect then return nil end
            return {stage=stage,incarnation='1',preBase=4294967280,amount=32,
                applied=15,remainder=17,nativeResult=stage=='preparing' and 0 or 1,
                postBase=stage=='preparing' and 4294967280 or 4294967295}
        end}
        assert(R.BeforeAward(donor,effect)==1)
        assert(donor.aux.CBMBank.pendingAward.preBase==4294967280)
        assert(donor.aux.CBMBank.pendingAward.remainder==17 and donor.aux.CBMBank.overflow==0)
        -- The actual native leaf and C++ amount restore are independently run
        -- by award_native_test.cpp; this fixture joins real runtime + serializer.
        donor.m_baseStats.m_xp=4294967295
        if finish=='complete' then
            stage='completing';assert(R.CompleteAward(donor,effect))
            assert(donor.aux.CBMBank.pendingAward==nil and donor.aux.CBMBank.overflow==17)
        else
            stage='uncertain';R.UncertainAward(donor,effect)
            assert(donor.aux.CBMBank.pendingAward.observedBase==4294967295)
            assert(donor.aux.CBMBank.pendingAward.amount==32)
        end
        local recovered=actor(string.rep('b',32),'2');recovered.m_baseStats.m_xp=4294967295
        runtimeMarshal(donor,recovered)
        if finish=='complete' then
            assert(recovered.aux.CBMBank.overflow==17)
            assert(R.Snapshot(recovered,8000000).total==4294967312)
        else
            assert(recovered.aux.CBMBank.pendingAward.preBase==4294967280)
            assert(recovered.aux.CBMBank.pendingAward.remainder==17)
            local ok,why=pcall(R.Snapshot,recovered,8000000)
            assert(not ok and tostring(why):find('reconciliation'))
        end
        assert(#failures==0)
    """)


@pytest.mark.parametrize("finish",["complete","uncertain"])
@pytest.mark.parametrize("pre,overflow,raw,effect_mode,mode,target",[
    (4294967295,100,4294967096,0,1,4294967195),
    (600000,0,1234,1,0,1234),
    (2147483648,0,100,2,2,0),
])
def test_actual_permanent_effect_writer_journal_round_trip(wire,finish,pre,overflow,raw,effect_mode,mode,target):
    lua,_=wire
    runtime_fixture(lua)
    for name,value in locals().copy().items():
        if name in {"finish","pre","overflow","raw","effect_mode","mode","target"}:lua.globals()[name]=value
    lua.execute("""
        donor.m_baseStats.m_xp=pre; donor.aux.CBMBank.overflow=overflow
        local stage='preparing'; local planned
        CBMBank_Reset={NativeCap=function()return 8000000 end}
        CBMBank_Writer={Query=function(a)
            if a~=donor then return nil end
            return {stage=stage,incarnation='1',preBase=pre,rawValue=raw,mode=mode,
                origin='unclassified',source='opcode104',effectMode=effect_mode,
                plannedBase=planned,postBase=donor.m_baseStats.m_xp,nativeResult=stage=='preparing' and 0 or 1}
        end,Plan=function(a,n) assert(a==donor and n==target);planned=n;return true end}
        assert(R.BeforeWrite(donor)==1 and planned==target)
        assert(donor.aux.CBMBank.pendingWrite.source=='opcode104')
        donor.m_baseStats.m_xp=target
        if finish=='complete' then
            stage='completing';assert(R.CompleteWrite(donor))
        else
            stage='uncertain';R.UncertainWrite(donor)
        end
        local recovered=actor(string.rep('b',32),'2');recovered.m_baseStats.m_xp=target
        runtimeMarshal(donor,recovered)
        if finish=='complete' then
            assert(recovered.aux.CBMBank.pendingWrite==nil and recovered.aux.CBMBank.overflow==0)
            assert(R.Snapshot(recovered,8000000).total==target)
            assert(recovered.aux.CBMBank.lastWrite.source=='opcode104')
        else
            local p=recovered.aux.CBMBank.pendingWrite
            assert(p.source=='opcode104' and p.effectMode==effect_mode and p.rawValue==raw)
            assert(p.preBase==pre and p.preOverflow==overflow and p.plannedBase==target)
            local ok,why=pcall(R.Snapshot,recovered,8000000)
            assert(not ok and tostring(why):find('reconciliation'))
        end
        assert(#failures==0)
    """)


def test_ambiguous_native_percentage_with_overflow_preserves_real_carrier(wire):
    lua,_=wire
    runtime_fixture(lua)
    lua.execute("""
        donor.m_baseStats.m_xp=4294967295; donor.aux.CBMBank.overflow=100
        local original=donor.aux.CBMBank
        CBMBank_Reset={NativeCap=function()return 8000000 end}
        CBMBank_Writer={Query=function(a)
            return {stage='preparing',incarnation='1',preBase=4294967295,rawValue=50,mode=2,
                origin='unclassified',source='opcode104',effectMode=2}
        end,Plan=function()error('Rejected percentage must not publish a native plan')end}
        local ok,why=pcall(R.BeforeWrite,donor)
        assert(not ok and tostring(why):lower():find('overflow'))
        -- Reading this over-cap account stages its cosmetic cap notice (a new
        -- carrier table); the refused write changes nothing else.
        local function same(a,b,top)
            if type(a)~='table' or type(b)~='table' then return a==b end
            for k,v in pairs(a) do if not(top and k=='notices') and not same(v,b[k]) then return false end end
            for k in pairs(b) do if not(top and k=='notices') and a[k]==nil then return false end end
            return true
        end
        local now=donor.aux.CBMBank
        assert(same(now,original,true) and now.pendingWrite==nil and now.overflow==100)
        local recovered=actor(string.rep('b',32),'2');recovered.m_baseStats.m_xp=4294967295
        runtimeMarshal(donor,recovered)
        assert(R.Snapshot(recovered,8000000).total==4294967395 and #failures==0)
    """)


@pytest.mark.parametrize("runtime", ["lua51", "lua52", "luajit21"])
def test_loader_is_inert_until_explicit_install_and_query_needs_native_lifetime(runtime):
    lua = import_module("lupa."+runtime).LuaRuntime(unpack_returned_tuples=True)
    module = lua.execute((ROOT/"identity_hooks.lua").read_text())
    assert module.installed is None
    assert module.Query(lua.table())[0] is None
    with pytest.raises(Exception, match="Explicit research-only"):
        module.Install(lua.table())
    for address in (0xFFFFFFFF,0x7FF812345678,0x7FFFFFFFFFFF):
        lua.globals().address=address
        lua.execute("function EEex_UDToPtr() return address end")
        assert module.AddressText(lua.table())==format(address,"x")
