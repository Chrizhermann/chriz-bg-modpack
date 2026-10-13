"""Notice presentation only: synthetic runtime plus pinned EEex listener code.

No game/display engine is launched. Infinity_DisplayString is an observed sink;
the native DisplayText binding was source-audited separately.
"""
from importlib import import_module
from pathlib import Path
import os
import pytest

ROOT=Path(__file__).resolve().parents[1]
EEEX=Path(os.environ.get("CBM_EEEX_SOURCE","C:/tmp/scroll-hook-research-20261009/EEex"))/"EEex/copy/EEex_scripts"

def function(source,name):
    start=source.index("function "+name+"(")
    return source[start:source.index("\nend",start)+4]

@pytest.fixture(params=["lua51","luajit21"])
def runtime(request):
    if not (EEEX/"EEex_Action.lua").exists():pytest.skip("Pinned EEex source needed for actual listener/keyboard implementation")
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
    actions=(EEEX/"EEex_Action.lua").read_text()
    for name in ["EEex_Action_AddSpriteStartedActionListener","EEex_Action_LuaHook_OnAfterSpriteStartedAction"]:
        lua.execute(function(actions,name))
    keys=(EEEX/"EEex_Keybinds.lua").read_text()
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
