"""Real WeiDU patch on generated fixtures; no game/save/native acceptance."""
from importlib import import_module
from pathlib import Path
import re
import pytest

from tests.test_recruitment_xp import make_game, install, invoke, decompile_script, compile_script, tree
from tests.test_utility_xp_installer import WEIDU, ROOT
from tests.test_campaign_xp_native_runtime import runtime as bank_runtime_fixture

PATCH = ROOT / "research/xp-banking-native/bank_recruitment_patch.tpa"
COMPAT = ROOT / "research/xp-banking-native/bank_compat.lua"
IMOEN = ROOT / "chriz-bg-modpack/imoen-xp/m_cbmixp.lua"
LOADER = ROOT / "chriz-bg-modpack/campaign-xp/m_cbmbnk.lua"
pytestmark = pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")


def patch(game, *, uninstall=False):
    setup=game.root / "setup-bank-compat.tp2"
    setup.write_text('BACKUP ~bank-compat-backup~\nAUTHOR ~research~\n'
        'BEGIN ~Uninstalled banking recruitment compatibility fixture~\n'
        f'INCLUDE ~{PATCH.as_posix()}~\nLAF cbmbank_patch_recruitment END\n',encoding="utf-8")
    return invoke(game,setup.name,"--force-uninstall-list" if uninstall else "--force-install-list","0")


def prepare(game):
    with (game.override / "action.ids").open("a",encoding="ascii") as f:
        f.write('472 EEex_LuaAction(S:Code*)\n')


@pytest.mark.parametrize("sr,converted,reverse",[(False,False,False),(True,True,True)])
def test_own_blocks_only_preserve_story_idempotence_and_uninstall(tmp_path,sr,converted,reverse):
    game=make_game(tmp_path,sr=sr,converted=converted,reversed_blocks=reverse)
    prepare(game)
    for component in (237,238):
        result,log=install(game,component);assert result.returncode==0,log
    unrelated='IF\n Global("ForeignXP","LOCALS",0)\nTHEN\n RESPONSE #100\n ChangeStat(Myself,XP,555000,SET)\nEND\n'
    for script in ("CBMFXP","CBMEXP"):
        original=decompile_script(game,script)
        compile_script(game,script,original+unrelated)
    (game.override / "m_cbmixp.lua").write_text(IMOEN.read_text()+"\n-- foreign harmless comment\n",encoding="utf-8")
    before=tree(game)
    result,log=patch(game);assert result.returncode==0,log
    first={}
    for script in ("CBMFXP","CBMEXP"):
        source=decompile_script(game,script)
        assert source.count('CBMBank_Catchup(')==6
        assert source.count('SetGlobal("CBM_SoARecruitXP","LOCALS",1)')==1 # only fallback
        assert 'ChangeStat(Myself,XP,555000,SET)' in source
        assert 'QuestAlpha' in source and 'QuestBeta' in source
        first[script]=(game.override / (script.lower()+'.bcs')).read_bytes()
    lua=(game.override / "m_cbmixp.lua").read_text()
    assert 'total = total + CBMBank_ActiveXP(member)' in lua
    assert 'CBMBank_ImoenXPSet(sprite, target)' in lua
    assert 'math.min(3000000, math.floor(total / count))' in lua
    assert '-- foreign harmless comment' in lua
    # Execute same patch twice in one fixture component (no uninstall between).
    second=game.root / "setup-bank-second.tp2"
    second.write_text('BACKUP ~bank-second-backup~\nAUTHOR ~research~\nBEGIN ~Repeat~\n'
        f'INCLUDE ~{PATCH.as_posix()}~\nLAF cbmbank_patch_recruitment END\n',encoding="utf-8")
    result,log=invoke(game,second.name,"--force-install-list","0");assert result.returncode==0,log
    for script,data in first.items():assert (game.override / (script.lower()+'.bcs')).read_bytes()==data
    assert (game.override / 'm_cbmixp.lua').read_text()==lua
    result,log=invoke(game,second.name,"--force-uninstall-list","0");assert result.returncode==0,log
    result,log=patch(game,uninstall=True);assert result.returncode==0,log
    after=tree(game)
    for name,data in before.items():assert after[name]==data,name


def test_absent_optional_recruitment_resources_are_noop(tmp_path):
    game=make_game(tmp_path);prepare(game)
    before=tree(game)
    result,log=patch(game);assert result.returncode==0,log
    after=tree(game)
    for name,data in before.items():assert after[name]==data,name


@pytest.mark.parametrize("flavor",["lua51","luajit21"])
def test_callback_marks_only_success_and_keeps_numeric_action_status_absent(flavor):
    lua=import_module("lupa."+flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        actor={marker=0,xp=1600000};calls=0;fail=false
        function EEex_Sprite_GetLocalInt(a) return a.marker end
        function EEex_Sprite_SetLocalInt(a,k,v) a.marker=v end
        function EEex_Sprite_GetCharacterIndex() return 0 end
        runtime={ActiveTotal=function(a) return a.xp end,Report=function(e) problem=e end,
            OwnedSet=function(a,t,origin)
                calls=calls+1;assert(origin==2);assert(not fail,'injected native failure')
                a.xp=math.max(a.xp,t);return true
            end}
    ''')
    compat=lua.execute(COMPAT.read_text())
    compat.Install(lua.globals().runtime)
    lua.execute('''
        fail=true;assert(CBMBank_Catchup(actor,1250000)==nil)
        assert(actor.marker==0 and actor.xp==1600000 and problem)
        fail=false;assert(CBMBank_Catchup(actor,1250000)==nil)
        assert(actor.marker==1 and actor.xp==1600000 and calls==2)
        CBMBank_Catchup(actor,1250000);assert(calls==2)
    ''')


def test_patched_imoen_executes_against_retained_native_accounts(tmp_path,bank_runtime_fixture):
    game=make_game(tmp_path);prepare(game)
    (game.override / "m_cbmixp.lua").write_bytes(IMOEN.read_bytes())
    result,log=patch(game);assert result.returncode==0,log
    lua=bank_runtime_fixture
    compat=lua.execute(COMPAT.read_text())
    compat.Install(lua.globals().R)
    lua.execute('''
        EEex_Active=true
        phase='SOA';ending=2
        imoen=actor(1);imoen.m_id=42;imoen.locals={}
        imoen.m_pArea={m_resref={get=function() return 'AR1512' end}}
        R.Adopt(imoen);imoen.m_baseStats.m_xp=1250000
        member1=actor(1);member1.m_id=1;R.Adopt(member1)
        member1.m_baseStats.m_xp=1500000
        member2=actor(1,9,8,7);member2.m_id=2;R.Adopt(member2)
        member2.m_baseStats.m_xp=2500000 -- retired F7=64k must NOT enter average
        party={member1,imoen,member2}
        function EEex_Sprite_GetInPortrait(i) return party[i+1] end
        function EEex_Sprite_GetNumCharacters() return #party end
        function EEex_Sprite_GetLocalInt(a,key) return a.locals[key] or 0 end
        function EEex_Sprite_SetLocalInt(a,key,value) a.locals[key]=value end
    ''')
    lua.execute((game.override / "m_cbmixp.lua").read_text())
    lua.execute('''
        CBM_ImoenXP_Apply(imoen)
        assert(R.ActiveTotal(imoen)==2000000)
        assert(imoen.locals.BD_JOINXP==2 and imoen.locals.CBM_ImoenSpellholdXP==1)
        assert(member2.aux.CBMBank.old.total==64000 and R.ActiveTotal(member2)==2500000)
        -- The independent 3M bound still applies when another actor's retained
        -- active XP includes native overflow. There is no old-class transfer.
        member1.m_baseStats.m_xp=4294967295;member1.aux.CBMBank.overflow=100000
        imoen.locals.CBM_ImoenSpellholdXP=0
        CBM_ImoenXP_Apply(imoen)
        assert(R.ActiveTotal(imoen)==3000000 and imoen.aux.CBMBank.overflow==0)
        assert(member1.aux.CBMBank.overflow==100000 and member2.aux.CBMBank.old.total==64000)
    ''')


@pytest.mark.parametrize("flavor",["lua51","luajit21"])
def test_failed_bank_startup_keeps_rerouted_paths_at_pre_650_behavior(tmp_path,flavor):
    game=make_game(tmp_path);prepare(game)
    (game.override / "m_cbmixp.lua").write_bytes(IMOEN.read_bytes())
    result,log=patch(game);assert result.returncode==0,log
    lua=import_module("lupa."+flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        EEex_Active=true;responses={};printed={}
        gameReady=false;initListeners={}
        function EEex_GameState_AddInitializedListener(f) initListeners[#initListeners+1]=f end
        function initialize() gameReady=true;for _,f in ipairs(initListeners) do f() end;initListeners={} end
        function Infinity_DoFile(name) CBMBank_Config={schema=1,policy='bg1_sod'} end
        function dofile() return {Install=function()
            error('EEex stats relay does not preserve native first call') end} end
        function print(s) printed[#printed+1]=s end
        function EEex_Action_ExecuteResponseStringOnAIBaseInstantly(s,sprite)
            responses[#responses+1]={s,sprite} end
    ''')
    # Both M_ files load with the UI; the bank starts (and here fails) at initialization.
    lua.execute(LOADER.read_text())
    lua.execute((game.override / "m_cbmixp.lua").read_text())
    lua.execute("assert(#printed==0);initialize()")
    lua.execute('''
        assert(printed[1]:find('Startup failed',1,true))
        local function actor(id,xp) return {m_id=id,m_baseStats={m_xp=xp},locals={},
            m_pArea={m_resref={get=function() return 'AR1512' end}}} end
        function EEex_Sprite_GetLocalInt(a,k) return a.locals[k] or 0 end
        function EEex_Sprite_SetLocalInt(a,k,v) a.locals[k]=v end
        imoen=actor(42,1250000);party={actor(1,1500000),imoen,actor(2,2500000)}
        function EEex_Sprite_GetInPortrait(i) return party[i+1] end
        function EEex_Sprite_GetNumCharacters() return #party end
        -- Patched Imoen: native XP average and a plain ChangeStat SET, as before 650.
        CBM_ImoenXP_Apply(imoen)
        assert(#responses==1 and responses[1][2]==imoen)
        assert(responses[1][1]=='ChangeStat(Myself,XP,2000000,SET)')
        assert(imoen.locals.BD_JOINXP==2 and imoen.locals.CBM_ImoenSpellholdXP==1)
        -- Rerouted recruitment block: the original SET and its completion marker.
        recruit=actor(7,0)
        assert(CBMBank_Catchup(recruit,1250000)==nil)
        assert(#responses==2 and responses[2][2]==recruit)
        assert(responses[2][1]=='ChangeStat(Myself,XP,1250000,SET)')
        assert(recruit.locals.CBM_SoARecruitXP==1)
    ''')
