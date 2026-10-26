"""Notice presentation only: synthetic runtime plus pinned EEex listener code.

No game/display engine is launched. Infinity_DisplayString is an observed sink;
the native DisplayText binding was source-audited separately.
"""
from importlib import import_module
from pathlib import Path
import pytest

from tests.pinned_eeex import pinned_eeex_script

ROOT=Path(__file__).resolve().parents[1]

def function(source,name):
    start=source.index("function "+name+"(")
    return source[start:source.index("\nend",start)+4]

@pytest.fixture(params=["lua51","luajit21"])
def runtime(request):
    # The actual listener/keyboard implementation; CI fetches these, so there a missing script is a failure.
    action,keybinds=pinned_eeex_script("EEex_Action.lua"),pinned_eeex_script("EEex_Keybinds.lua")
    lua=import_module("lupa."+request.param).LuaRuntime(unpack_returned_tuples=True)
    lua.globals().N=lua.execute((ROOT/"research/xp-banking-native/bank_notice.lua").read_text())
    lua.execute('''
      function copy(v)if type(v)~='table'then return v end local out={};for k,x in pairs(v)do out[k]=copy(x)end return out end
      EEex={DeepCopy=copy};EEex_Keybinds_FireType={UP=true,DOWN=false}
      EEex_Keybinds_Private_Definitions={}
      EEex_Action_Private_SpriteStartedActionListeners={}
      EEex_Action_Private_SpriteStartedNextActionListeners={}
      function EEex_Utility_TryIgnore(fn,...)if fn then pcall(fn,...)end end
      displayed={};reported={};actionContinuations=0;ackCalls=0
      actor={owner='1234567890abcdef1234567890abcdef',inc='abc',queue={{key='cap:BG1',text='Cap reached.'},
       {key='release:SOD',text='Released 123 XP.'}},m_curAction={m_actionID=99},xp=500000}
      function Infinity_DisplayString(text)
       if displayError then error('display unavailable')end
       displayed[#displayed+1]=text
       if onDisplay then onDisplay()end
      end
      function EEex_Sprite_GetSelected()if noSelection then return nil end return actor end
      R={Report=function(text)reported[#reported+1]=text end,
       PendingNotices=function(a)
        if pendingError then error('read failed')end
        if a.unowned then return nil end
        return {ownerKey=a.owner,incarnation=a.inc,items=copy(a.queue)}
       end,
       AckNotice=function(a,owner,inc,key)
        ackCalls=ackCalls+1
        if owner~=a.owner or inc~=a.inc then return false end
        for i,item in ipairs(a.queue)do if item.key==key then table.remove(a.queue,i);return true end end
        return false
       end,
       Status=function(a,cap)assert(a==actor and cap==161000);return 'Usable XP: 161000; banked XP: 339000; cap: 161000'end}
      reset={NativeCap=function(a)assert(a==actor);return 161000 end}
    ''')
    actions=action.read_text()
    for name in ["EEex_Action_AddSpriteStartedActionListener","EEex_Action_LuaHook_OnAfterSpriteStartedAction"]:
        lua.execute(function(actions,name))
    keys=keybinds.read_text()
    for name in ["EEex_Keybinds_Get","EEex_Keybinds_Reset","EEex_Keybinds_Update"]:
        lua.execute(function(keys,name))
    return lua

def test_one_shot_delivery_and_ordinary_action_preserved(runtime):
    runtime.execute('''
      local ordinary=function(a,action)assert(a==actor and action.m_actionID==99);actionContinuations=actionContinuations+1 end
      EEex_Action_AddSpriteStartedActionListener(ordinary)
      N.Install{researchOnly=true,runtime=R,reset=reset}
      assert(next(EEex_Keybinds_Private_Definitions)==nil)
      EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#displayed==2 and #actor.queue==0 and ackCalls==2 and actionContinuations==2 and actor.xp==500000)
      assert(actor.m_curAction.m_actionID==99 and N.Remove()and N.Remove())
      assert(#EEex_Action_Private_SpriteStartedActionListeners==1 and EEex_Action_Private_SpriteStartedActionListeners[1]==ordinary)
      assert(CBMBank_Status==nil)
    ''')

def test_failed_display_keeps_pending_and_does_not_block_actions(runtime):
    runtime.execute('''
      N.Install{researchOnly=true,runtime=R,reset=reset};displayError=true
      EEex_Action_AddSpriteStartedActionListener(function()actionContinuations=actionContinuations+1 end)
      EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#actor.queue==2 and ackCalls==0 and #reported==1 and actionContinuations==1)
      displayError=false;EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#actor.queue==0 and #displayed==2 and actionContinuations==2)
    ''')

def test_reentrant_display_cannot_repeat_before_ack(runtime):
    runtime.execute('''
      N.Install{researchOnly=true,runtime=R,reset=reset}
      onDisplay=function()local ok,n=N.Flush(actor);assert(ok and n==0)end
      local ok,count=N.Flush(actor)
      assert(ok and count==2 and #displayed==2 and ackCalls==2 and #actor.queue==0)
    ''')

def test_lifetime_change_during_display_cannot_ack_or_show_later_entries(runtime):
    runtime.execute('''
      N.Install{researchOnly=true,runtime=R,reset=reset};onDisplay=function()actor.inc='new'end
    ''')
    runtime.execute('''
      local ok,count,why=N.Flush(actor)
      assert(not ok and count==0 and why:find('changed')and #displayed==1 and #actor.queue==2)
      assert(ackCalls==1 and actor.xp==500000)
    ''')

def test_status_uses_actual_selection_cap_and_optional_native_name(runtime):
    runtime.execute('''
      N.Install{researchOnly=true,runtime=R,reset=reset}
      actor.m_sName={m_pchData={get=function()return 'Dynaheir'end}}
      assert(CBMBank_Status()==nil)
      assert(#displayed==3 and displayed[1]=='Dynaheir: Cap reached.')
      assert(displayed[3]:find('Dynaheir: Usable XP: 161000',1,true)and actor.xp==500000)
      noSelection=true;CBMBank_Status();assert(displayed[4]=='Select a party member to see campaign XP.')
    ''')

def test_explicit_key_and_remove_preserve_other_definitions(runtime):
    runtime.execute('''
      EEex_Keybinds_Update('OtherMod',{keys={55},callback=function()end})
      N.Install{researchOnly=true,runtime=R,reset=reset,keybind={keys={88},modifierKeys={17},fireType=false}}
      local def=EEex_Keybinds_Get('CBMBank_Status');assert(def.keys[1]==88 and def.modifierKeys[1]==17 and def.fireType==false)
      def.callback();assert(#displayed==3)
      local external=function()end;CBMBank_Status=external
      assert(N.Remove()and CBMBank_Status==external)
      assert(EEex_Keybinds_Get('CBMBank_Status')==nil and EEex_Keybinds_Get('OtherMod').keys[1]==55)
    ''')

def test_registration_failure_removes_only_partial_owned_listener(runtime):
    runtime.execute('''
      local original=EEex_Action_AddSpriteStartedActionListener
      EEex_Action_AddSpriteStartedActionListener(function()end)
      EEex_Action_AddSpriteStartedActionListener=function(fn)original(fn);error('registration interrupted')end
      local ok=pcall(N.Install,{researchOnly=true,runtime=R,reset=reset})
      assert(not ok and #EEex_Action_Private_SpriteStartedActionListeners==1 and CBMBank_Status==nil and not N.installed)
    ''')

def test_unowned_or_unreadable_notice_data_stays_out_of_accounting(runtime):
    runtime.execute('''
      N.Install{researchOnly=true,runtime=R,reset=reset};actor.unowned=true
      assert(N.Flush(actor)and #displayed==0 and #actor.queue==2)
      actor.unowned=false;pendingError=true
      EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#displayed==0 and #actor.queue==2 and actor.xp==500000 and #reported==1)
    ''')

def test_only_the_banks_notices_and_the_status_request_display_anything():
    # Christopher (2026-10-25): no technical notices in the game. The fallback,
    # ended-lifetime and kept-write counts go to the loader log only; the module
    # shows the bank's own notices and the status the player asks for.
    source=(ROOT/"research/xp-banking-native/bank_notice.lua").read_text()
    rest=source
    for name in ("M.Flush","M.Status","M.Install"):
        rest=rest.replace(function(source,name),"")
    assert "Infinity_DisplayString" not in rest
    install=function(source,"M.Install")
    assert install.count("Infinity_DisplayString")==1 and 'type(Infinity_DisplayString)=="function"' in install

def test_native_fallback_is_logged_once_per_loaded_game_and_never_shown(runtime):
    # CEBG #19: a refused opcode-104 change runs the game's own effect. The
    # count is process-wide; each loaded game logs its first one only, and the
    # game shows nothing of it.
    runtime.execute('''
      fallbacks={total=0,award=0,writer=0}
      local provider=function()return fallbacks.total,fallbacks.award,fallbacks.writer end
      EEex_Action_AddSpriteStartedActionListener(function()actionContinuations=actionContinuations+1 end)
      N.Install{researchOnly=true,runtime=R,reset=reset,fallbacks=provider};actor.unowned=true
      EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#displayed==0 and #reported==0 and actionContinuations==1)
      fallbacks.total=2;fallbacks.award=5
      EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#displayed==0 and actionContinuations==2)
      assert(#reported==1 and reported[1]:find('2 XP changes in this game (2 since launch)',1,true)
       and reported[1]:find('award: the bank refused it',1,true))
      -- The count includes ChangeStat setter writes, which are not effects.
      assert(reported[1]:find("ran the game's own code without the bank",1,true))
      fallbacks.total=3;fallbacks.writer=4
      EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#displayed==0 and #reported==1 and actionContinuations==3)
      N.ResetGame() -- the next loaded game counts from here
      EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#displayed==0 and #reported==1)
      fallbacks.total=4
      EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#displayed==0 and #reported==2 and reported[2]:find('1 XP change in this game (4 since launch)',1,true))
      assert(reported[2]:find('write: an earlier XP change awaits reconciliation',1,true)and actor.xp==500000)
      assert(N.Remove()and #EEex_Action_Private_SpriteStartedActionListeners==1)
    ''')

def test_native_fallback_reasons_name_every_setter_outcome(runtime):
    # A refused stat44 setter write (script ChangeStat) is the game's own write,
    # counted with the writer bridge; the log line names each new reason.
    runtime.execute('''
      fallbacks={total=0,award=0,writer=0}
      local provider=function()return fallbacks.total,fallbacks.award,fallbacks.writer end
      N.Install{researchOnly=true,runtime=R,reset=reset,fallbacks=provider};actor.unowned=true
      local reasons={[7]='it did not finish normally and its journal awaits reconciliation',
       [8]='it changed while the bank prepared it',[9]='the game was saving',
       [10]='another XP change of that character was in progress'}
      for status=7,10 do
       N.ResetGame();fallbacks.total=fallbacks.total+1;fallbacks.writer=status
       EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
       assert(reported[#reported]:find('write: '..reasons[status],1,true))
      end
      assert(#displayed==0 and #reported==4)
      assert(N.Remove())
    ''')

def test_ended_lifetime_changes_get_their_own_line_and_no_notice(runtime):
    # Status 11: the actor's lifetime ended while the bank prepared the change,
    # so nothing ran and nothing was written. That is no fallback: one log line
    # of its own per loaded game, and nothing in the game.
    runtime.execute('''
      counts={total=0,award=0,writer=0,ended=0}
      local provider=function()return counts.total,counts.award,counts.writer,counts.ended end
      N.Install{researchOnly=true,runtime=R,reset=reset,fallbacks=provider};actor.unowned=true
      counts.ended=1;EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#displayed==0 and #reported==1)
      assert(reported[1]:find('1 XP change in this game (1 since launch) wrote nothing',1,true)
       and reported[1]:find('lifetime ended while the bank prepared it (status 11)',1,true))
      counts.ended=3;EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor);assert(#reported==1)
      counts.total=1;counts.writer=5;EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#displayed==0 and #reported==2 and reported[2]:find("ran the game's own code without the bank",1,true))
      N.ResetGame();counts.ended=5;EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#displayed==0 and #reported==3 and reported[3]:find('2 XP changes in this game (5 since launch) wrote nothing',1,true)
       and reported[3]:find('prepared them',1,true))
      EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor);assert(#reported==3)
      counts.ended='broken';local ok=N.FlushFallbacks() -- a malformed count disables the lines quietly
      assert(not ok and #reported==4 and reported[4]:find('ended-lifetime count unavailable',1,true))
      assert(N.Remove())
    ''')

def test_kept_setter_writes_get_their_own_line_and_no_notice(runtime):
    # Status 12: another thread created or destroyed a character at the address
    # of the character a setter write was meant for, so the bank kept the write
    # unapplied rather than write into what may be another character. That is
    # no fallback: one log line of its own per loaded game that lists what was
    # kept, and nothing in the game.
    runtime.execute('''
      counts={total=0,award=0,writer=0,ended=0,kept=0,list=''}
      local provider=function()return counts.total,counts.award,counts.writer,counts.ended,counts.kept,counts.list end
      N.Install{researchOnly=true,runtime=R,reset=reset,fallbacks=provider};actor.unowned=true
      EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor);assert(#displayed==0 and #reported==0)
      counts.kept=1;counts.list='add 1000';EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#displayed==0 and #reported==1)
      assert(reported[1]:find('1 XP setter write in this game (1 since launch: add 1000) was kept and not applied',1,true)
       and reported[1]:find('at the address of the character it was meant for',1,true)
       and reported[1]:find('(status 12)',1,true)and reported[1]:find('until the game restarts',1,true))
      counts.kept=2;counts.list='add 1000, set 54321';EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#reported==1)
      -- A fallback in the same game still gets its own line.
      counts.total=1;counts.award=3;EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#displayed==0 and #reported==2 and reported[2]:find("ran the game's own code without the bank",1,true))
      N.ResetGame();counts.kept=4;counts.list='add 1000, set 54321, set 1, add 2'
      EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(#displayed==0 and #reported==3 and reported[3]:find(
       '2 XP setter writes in this game (4 since launch: add 1000, set 54321, set 1, add 2) were kept',1,true)
       and reported[3]:find('at the addresses of the characters they were meant for',1,true))
      EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor);assert(#reported==3)
      counts.kept='broken';local ok=N.FlushFallbacks() -- a malformed count disables the lines quietly
      assert(not ok and #reported==4 and reported[4]:find('kept-write count unavailable',1,true))
      assert(N.Remove())
    ''')

def test_native_fallback_line_needs_no_display_and_broken_count_disables_quietly(runtime):
    runtime.execute('''
      local total,calls=1,0
      local provider=function()calls=calls+1;if total==nil then error('count unavailable')end return total,5,0 end
      N.Install{researchOnly=true,runtime=R,reset=reset,fallbacks=provider};actor.unowned=true
      displayError=true -- nothing is displayed, so a failing display changes nothing
      local ok,n=N.FlushFallbacks();assert(ok and n==1 and #displayed==0 and #reported==1)
      local seen=calls;ok,n=N.FlushFallbacks()
      assert(ok and n==0 and calls==seen and #reported==1) -- logged once; nothing more to read in this game
      total=nil;N.ResetGame() -- a broken count disables these lines, never actions
      assert(#reported==2 and reported[2]:find('count unavailable',1,true))
      seen=calls;ok=N.FlushFallbacks();EEex_Action_LuaHook_OnAfterSpriteStartedAction(actor)
      assert(ok and calls==seen and #displayed==0 and #reported==2)
      assert(N.Remove()and not pcall(N.Install,{researchOnly=true,runtime=R,reset=reset,fallbacks=7}))
      assert(not N.installed and CBMBank_Status==nil and #EEex_Action_Private_SpriteStartedActionListeners==0)
    ''')