"""Real Lua flow/controller/picker/journal/store with explicit engine doubles.
Checks handoff, saved ownership, Cancel/reopen HP cache and uncertain RNG. This
is not native rendering or engine reward execution.
"""
from pathlib import Path
import json
from lupa.lua51 import LuaRuntime as Lua51
from lupa.luajit21 import LuaRuntime as LuaJIT
ROOT=Path(__file__).parent
CASE=r'''
local count=0
local function check(f)f();count=count+1 end
local function copy(x)local v,e=Store.WireSnapshot(x);assert(v,e);return v end
local function setup()
 local sprite={};local owner=string.rep('a',32)
 local a={ownerKey=owner,incarnation='8',revision=9,oldClass=2,activeClass=1,oldKit=16384,oldLevel=10,
  oldUsableXP=550000,activeUsableXP=200000,hasCleanReceipt=true}
 local aux={CBMBank={schema=2,ownerKey=owner,kind='dual',revision=9,old={rewardReceipt={}}},CBMBankLifetime={ownerKey=owner,incarnation='8'}}
 local v={phase='preparing',session='1',incarnation='8',owner='',hpStatus=1,choiceCount=0,hpCached=false}
 local target=11;local rolls=0;local selected=0;local failRoll=false;local flow
 local constitution=18;local failSkills=false;local failClose=false;local badModel=false;local closes=0;local validations=0
 local ownership='owned';local queries=0
 EEex_GetUDAux=function(s)assert(s==sprite);return aux end
 EEex_UDToPtr=function(s)assert(s==sprite);return 111 end
 local runtime={ManualOwnership=function()if ownership=='error'then error('damaged owned carrier')end;return ownership end,
  PrepareOldHLAs=function()assert(v.phase=='committing'and aux.CBMBank.pendingManualProgression.stage=='committing');return true end,
  CommitOldHLAs=function()assert(v.phase=='committing'and aux.CBMBank.pendingManualProgression.stage=='committing');return true end,
  OldProgression=function(s)queries=queries+1;assert(s==sprite);if aux.CBMBank.pendingManualProgression then return nil,'journal' end;return copy(a)end}
 local rules={Target=function()return target end,Roll=function()
  rolls=rolls+1;assert(aux.CBMBank.oldManualHPPreview.stage=='rolling');if failRoll then error('native RNG uncertain')end
  return {total=target>a.oldLevel and 4 or 0,encoded=target>a.oldLevel and '11:4;'or''}
 end}
 local manual={Query=function()return v end,BindOwner=function(_,o)v.owner=o;return true end,
  Dormant=function()return true end,Constitution=function()return constitution end,ReadSkills=function()return{0,0,0,0,0,0,0}end,
  SelectOld=function(s,account,t,hp,choices,before)
   assert(s==sprite and account.ownerKey==owner and t==target and before[1]==0)
   assert(aux.CBMBank.pendingManualProgression.retired.hp.encoded==hp.encoded)
   assert(aux.CBMBank.oldManualHPPreview.stage=='complete');selected=selected+1;return true
  end,
  HP=function()return{status=1,count=1,total=4,beforeLevels={10,1,0},afterLevels={11,1,0}}end,
  HPSample=function()return{level=11,hp=4}end}
 local receipts=NewReceipts();receipts.Configure(Store,{CaptureState=function()
  return{class=7,kit=16384,flags=16,levels={10,1,0},maxHPBase=50,skills={m_lockPickingBase=0,m_trapsBase=0,
   m_pickPocketBase=0,m_moveSilentlyBase=0,m_hideInShadowsBase=0,m_detectIllusionBase=0,m_setTrapsBase=0},
   legacyProficiencies={},proficiencies={},effects={timed={},equipped={}}}
 end},manual,Ledger)
 local entry={Check=function()return true end,Open=function(s)
  v.phase='preparing';v.owner='';assert(flow.Begin(s));v.phase='preview';return true
 end}
 local rows={Build=function()
  return{className='Fighter',oldLevel=a.oldLevel,target=target,profPoints=badModel and -1 or 1,skillPoints=0,
   proficiencies={{stat=89,label='Long sword',value=0,limit=2}},skills={},onClose=function()
    closes=closes+1;if failClose then error('uncertain native catalog close')end
   end},{0,0,0,0,0,0,0}
 end,ValidateSkills=function()
  validations=validations+1;assert(not failSkills,'changed installed skill limit');return true
 end}
 local hla={PrepareManual=function(s,account,t,choices)
  assert(s==sprite and account.ownerKey==owner and t==target and v.phase=='preparing'and v.owner==owner)
  assert(aux.CBMBank.pendingManualProgression);return 'actual-session-token'
 end,ClearManual=function(token)assert(token=='actual-session-token'and(v.phase=='committing'or v.phase=='canceling'or v.phase=='uncertain'));return true end}
 flow=Flow.New{runtime=runtime,rules=rules,entry=entry,manual=manual,receipts=receipts,pickerModule=Picker,hla=hla,
  controllerModule=Controller,rows=rows,wire=Store}
 local reset={};for name in pairs(_G)do if type(name)=='string' and name:sub(1,13)=='CBMDOldPicker' then reset[#reset+1]=name end end
 for _,name in ipairs(reset)do _G[name]=nil end
 Infinity_PushMenu=function(n)assert(n=='CBMD_OLD_PICKER')end
 Infinity_PopMenu=function(n)assert(n=='CBMD_OLD_PICKER');CBMDOldPickerClosed()end
 local loads=0;EEex_Menu_LoadFile=function(n)assert(n=='CBMDOLD');loads=loads+1 end
 local other=function()end;EEex_Menu_AfterMainFileLoadedListeners={other}
 EEex_Menu_AddAfterMainFileLoadedListener=function(f)table.insert(EEex_Menu_AfterMainFileLoadedListeners,f)end
 flow.InstallUI('CBMDOLD')
 assert(loads==0 and #EEex_Menu_AfterMainFileLoadedListeners==2)
 EEex_Menu_AfterMainFileLoadedListeners[2]();assert(loads==1)
 local function open()assert(flow.Route(sprite)==1);assert(CBMDOldPickerAdjust('proficiencies',1));assert(flow.Continue())end
 return {flow=flow,s=sprite,a=a,aux=aux,v=v,open=open,rolls=function()return rolls end,selected=function()return selected end,
  target=function(n)target=n end,fail=function()failRoll=true end,constitution=function(n)constitution=n end,
  failSkills=function()failSkills=true end,failClose=function()failClose=true end,badModel=function()badModel=true end,
  closes=function()return closes end,validations=function()return validations end,
  ownership=function(n)ownership=n end,queries=function()return queries end,loads=function()return loads end,other=other}
end
check(function()
 local c=setup();assert(c.flow.Eligible(c.s)==1);c.open();assert(c.rolls()==1 and c.selected()==1)
 local p=c.aux.CBMBank.pendingManualProgression;assert(p.retired.choices.proficiencies[1].delta==1)
 assert(Store.WireSnapshot(c.aux.CBMBank));c.v.phase='canceling';assert(c.flow.Cancel(c.s))
 assert(not c.aux.CBMBank.pendingManualProgression and c.aux.CBMBank.oldManualHPPreview.rolls.total==4)
 c.constitution(25);c.v.session='2';c.open();assert(c.rolls()==1 and c.selected()==2) -- Cancel/CON change never rerolls
 c.v.phase='committing';assert(c.flow.PrepareCommit(c.s));assert(c.flow.Complete(c.s))
 assert(not c.aux.CBMBank.oldManualHPPreview and not c.aux.CBMBank.pendingManualProgression)
 assert(Ledger.Read(c.aux.CBMBank.old.rewardReceipt.manualLedger,1).retired.target==11)
end)
check(function()
 local c=setup();c.fail();assert(c.flow.Route(c.s)==1);assert(CBMDOldPickerAdjust('proficiencies',1))
 assert(not pcall(c.flow.Continue));assert(c.rolls()==1 and c.selected()==0)
 assert(c.aux.CBMBank.oldManualHPPreview.stage=='rolling');c.v.phase='uncertain';assert(c.flow.Uncertain(c.s))
 assert(c.aux.CBMBank.pendingManualProgression.stage=='uncertain')
 assert(not pcall(c.flow.Eligible,c.s));assert(c.rolls()==1)
end)
check(function()
 local c=setup();assert(c.flow.Route(c.s)==1);assert(CBMDOldPickerAdjust('proficiencies',1));c.a.revision=10
 assert(not pcall(c.flow.Continue));assert(c.selected()==0 and c.rolls()==0 and not c.aux.CBMBank.pendingManualProgression)
end)
check(function()
 local c=setup();c.target(10);assert(c.flow.Eligible(c.s)==0 and c.flow.Route(c.s)==0)
 assert(c.flow.Begin(c.s));assert(c.selected()==1 and c.aux.CBMBank.pendingManualProgression.retired.target==10)
 assert(#c.aux.CBMBank.pendingManualProgression.retired.choices.proficiencies==0)
end)
check(function()
 local c=setup();assert(c.flow.Route(c.s)==1);CBMDOldPickerCancel()
 assert(c.rolls()==0 and c.selected()==0 and not c.aux.CBMBank.pendingManualProgression)
 assert(c.closes()==1)
end)
check(function()
 local c=setup();c.badModel();assert(not pcall(c.flow.Route,c.s));assert(c.closes()==1)
 assert(c.rolls()==0 and c.selected()==0 and not c.aux.CBMBank.pendingManualProgression)
end)
check(function()
 local c=setup();assert(c.flow.Route(c.s)==1);assert(CBMDOldPickerAdjust('proficiencies',1));c.failClose()
 assert(not pcall(c.flow.Continue));assert(c.closes()==1 and c.rolls()==0 and c.selected()==0)
 CBMDOldPickerClosed();assert(c.closes()==1) -- a possibly freed native catalog is not retried
 assert(not pcall(c.flow.Begin,c.s));assert(not c.aux.CBMBank.pendingManualProgression) -- stale launch was discarded
end)
check(function()
 local c=setup();assert(c.flow.Route(c.s)==1);assert(CBMDOldPickerAdjust('proficiencies',1));c.failSkills()
 assert(not pcall(c.flow.Continue));assert(c.validations()==1 and c.rolls()==0 and c.selected()==0)
 assert(not c.aux.CBMBank.pendingManualProgression)
end)
check(function()
 local c=setup();c.ownership('passthrough')
 assert(c.flow.Eligible(c.s)==0 and c.flow.Route(c.s)==0 and c.flow.Begin(c.s)==2)
 assert(c.queries()==0 and c.selected()==0 and c.rolls()==0 and not c.aux.CBMBank.pendingManualProgression)
end)
check(function()
 local c=setup();c.ownership('error')
 assert(not pcall(c.flow.Eligible,c.s)and not pcall(c.flow.Route,c.s)and not pcall(c.flow.Begin,c.s))
 assert(c.queries()==0 and c.selected()==0 and c.rolls()==0 and not c.aux.CBMBank.pendingManualProgression)
end)
check(function()
 local c=setup();assert(c.flow.Route(c.s)==1);EEex_Menu_AfterMainFileLoadedListeners[2]()
 assert(c.closes()==1 and c.loads()==2 and not CBMDOldPickerCanContinue())
 c.flow.UninstallUI();assert(#EEex_Menu_AfterMainFileLoadedListeners==1 and EEex_Menu_AfterMainFileLoadedListeners[1]==c.other)
 assert(c.closes()==1 and CBMDOldPickerContinue==nil)
end)
return count
'''
def main():
 results=[]
 for Runtime in (Lua51,LuaJIT):
  l=Runtime(unpack_returned_tuples=True);g=l.globals()
  g.Store=l.execute((ROOT.parent/'xp-banking/cbmbank_store.lua').read_text())
  g.Ledger=l.execute((ROOT/'dual_manual_ledger.lua').read_text())
  for name,file in [('Flow','dual_retired_flow.lua'),('Picker','dual_retired_picker.lua'),('Controller','dual_retired_controller.lua')]:
   g[name]=l.execute((ROOT/file).read_text())
  g.NewReceipts=lambda:l.execute((ROOT/'dual_manual_receipts.lua').read_text())
  results.append({'runtime':Runtime.__module__,'scenarios':l.execute(CASE)})
 report={'results':results,'scope':'Actual modules and store, explicit engine/native boundary doubles; no rendered/game acceptance'}
 (ROOT/'dual-retired-flow-check-results.json').write_text(json.dumps(report,indent=2)+'\n');print(report)
if __name__=='__main__':main()
