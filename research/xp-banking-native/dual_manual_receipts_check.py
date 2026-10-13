"""Actual wire+receipt modules with offline native-boundary protocol fixtures."""
from pathlib import Path
import json
from lupa.lua51 import LuaRuntime as Lua51
from lupa.luajit21 import LuaRuntime as LuaJIT
from dual_receipts_check import HARNESS
ROOT=Path(__file__).parent
CASES=r'''
local count=0
local function test(f)f();count=count+1 end
local function setup()
 local sprite=fixture();local owner=string.rep("b",32)
 local aux={CBMBank={schema=2,ownerKey=owner,kind="dual",revision=8,unchanged="keep",old={rewardReceipt={manualTransactions={}}}},
  CBMBankLifetime={ownerKey=owner,incarnation="123"}}
 EEex_GetUDAux=function(s)assert(s==sprite);return aux end
 local view={phase="preparing",session="5",incarnation="123",owner="",hpStatus=1,hpCached=false,choiceCount=1}
 local bridge={Query=function()return view end,BindOwner=function(_,key)view.owner=key;return true end,
 HP=function()return {status=1,count=2,total=12,beforeLevels={10,10,0},afterLevels={10,12,0}}end,
 HPSample=function(_,i)return {level=11+i,hp=i==0 and 7 or 5}end,
 Choice=function()return {status=1,stat=101,requested=2,before=1,after=2,inactive=false}end}
 local adapter=NewAdapter();adapter.Configure(Store,M,bridge,Ledger)
 return sprite,aux,view,bridge,adapter
end
function runManual()
 test(function()
  local s,aux,v,b,a=setup();local before=copy(s);assert(a.Begin(s));assert(equal(s,before))
  assert(aux.CBMBank.pendingManualProgression.ownerKey==aux.CBMBank.ownerKey)
  local saved,why=Store.WireSnapshot(aux.CBMBank);assert(saved,why);assert(saved.pendingManualProgression.stage=="preview")
  aux.CBMBank=saved;v.phase="committing";assert(a.PrepareCommit(s))
  assert(aux.CBMBank.pendingManualProgression.hp.samples[2].hp==5)
  assert(aux.CBMBank.pendingManualProgression.stage=="committing")
  -- A legitimate native CLAB XP award may revise root accounting during commit.
  aux.CBMBank.revision=9;aux.CBMBank.newNativeAccountField="preserve native award"
  assert(a.Complete(s));assert(equal(s,before));assert(not aux.CBMBank.pendingManualProgression)
  local r=Ledger.Read(aux.CBMBank.old.rewardReceipt.manualLedger,1)
  assert(r.stage=="committed" and r.ownerKey==string.rep("b",32) and r.ledgerRevision==8)
  assert(aux.CBMBank.revision==9 and aux.CBMBank.newNativeAccountField=="preserve native award")
  assert(aux.CBMBank.unchanged=="keep" and #r.choices==1)
  assert(not pcall(a.Complete,s)) -- never duplicate publication
 end)
 test(function()
  local s,aux,v,b,a=setup();a.Begin(s);v.phase="canceling";assert(a.Cancel(s))
  assert(not aux.CBMBank.pendingManualProgression and not aux.CBMBank.old.rewardReceipt.manualLedger)
 end)
 test(function()
  local s,aux,v,b,a=setup();a.Begin(s);v.phase="committing";a.PrepareCommit(s)
  v.phase="uncertain";assert(a.Uncertain(s));local saved=assert(Store.WireSnapshot(aux.CBMBank))
  assert(saved.pendingManualProgression.stage=="uncertain" and saved.pendingManualProgression.hp.count==2)
  aux.CBMBank=saved;v.phase="preparing";v.owner="";assert(not pcall(a.Begin,s))
  assert(aux.CBMBank.pendingManualProgression.stage=="uncertain")
 end)
 test(function()
  local s,aux,v,b,a=setup();aux.CBMBank.old.rewardReceipt=nil;a.Begin(s);v.phase="committing";a.PrepareCommit(s);a.Complete(s)
  assert(Ledger.Read(aux.CBMBank.manualLedger,1).stage=="committed" and not aux.CBMBank.old.rewardReceipt)
 end)
 for _,change in ipairs({
  function(aux,v)aux.CBMBankLifetime.incarnation="124"end,
  function(aux,v)aux.CBMBank.ownerKey=string.rep("c",32)end,
  function(aux,v)aux.CBMBank.excluded=true end,
  function(aux,v)aux.CBMBank.pendingDual={}end,
 })do test(function()local s,aux,v,b,a=setup();change(aux,v);local old=copy(aux);assert(not pcall(a.Begin,s));assert(equal(aux,old))end)end
 for _,change in ipairs({
  function(aux,v,b)aux.CBMBank.revision=9 end,
  function(aux,v,b)v.hpStatus=2 end,
  function(aux,v,b)v.session="6"end,
  function(aux,v,b)b.HPSample=function()return nil end end,
  function(aux,v,b)b.Choice=function()return {status=2}end end,
 })do test(function()local s,aux,v,b,a=setup();a.Begin(s);v.phase="committing";change(aux,v,b);local old=copy(aux);assert(not pcall(a.PrepareCommit,s));assert(equal(aux,old))end)end
 test(function()
  local s,aux,v,b,a=setup();local effects={};for i=1,203 do effects[i]=effect(233,-129-i,"CUSTOM")end
  s.m_timedEffectList=list(effects);aux.CBMBank.old.rewardReceipt.before=M.CaptureState(s)
  local original=copy(aux.CBMBank.old.rewardReceipt.before)
  for i=1,508 do
   v.phase="preparing";v.session=tostring(i);v.owner="";assert(a.Begin(s))
   assert(not aux.CBMBank.old.rewardReceipt.lastManualSnapshot)
   v.phase="committing";assert(a.PrepareCommit(s));assert(a.Complete(s))
   local saved,why=Store.WireSnapshot(aux.CBMBank);assert(saved,why);aux.CBMBank=saved
  end
  local target=aux.CBMBank.old.rewardReceipt
  assert(#target.manualLedger.records==508 and target.lastManualSnapshot.session=="508")
  assert(equal(target.before,original)and #target.lastManualSnapshot.state.effects.timed==203)
  for i=1,508 do local r=Ledger.Read(target.manualLedger,i)
   assert(r.session==tostring(i)and r.hp.samples[1].hp==7 and r.hp.samples[2].hp==5 and r.choices[1].after==2)
  end
 end)
 test(function()
  local s,aux,v,b,a=setup();aux.CBMBank.revision=9007199254740991;a.Begin(s)
  local p=aux.CBMBank.pendingManualProgression
  local hlas={};for i=1,51 do hlas[i]={id=i,descriptor={schema=1,icon="HLAMARK",nameStrref=4294967295,
   minLevel=1,maxLevel=255,maxRank=3,effect="GA_CUSTOM",prerequisite="PRIOR",excludedBy="OTHER",alignment="ALL"}}end
  p.retired={schema=1,account={ownerKey=p.ownerKey,incarnation=p.incarnation,revision=p.ledgerRevision,
   oldClass=2,activeClass=4,oldKit=16385,oldLevel=10,oldUsableXP=550000,activeUsableXP=200000,hasCleanReceipt=true},
   target=11,choices={proficiencies={{stat=89,delta=0},{stat=101,delta=2}},skills={{id=6,delta=5}},hlas=hlas,
    unusedProfPoints=0,unusedSkillPoints=0,unusedHlaPoints=0},beforeSkills={0,1,2,3,4,5,6},hp={total=4,encoded="11:4;"},hlasEnqueued=true}
  v.phase="committing";a.PrepareCommit(s);p=aux.CBMBank.pendingManualProgression
  p.oldHLA={schema=1,stage="deferred",count=51,added=51}
  p.choices={{stat=101,inactive=false,screenMode=28,selectedClass=4,requested=2,before=1,after=2},
   {stat=101,inactive=false,screenMode=28,selectedClass=4,requested=3,before=2,after=3},
   {stat=101,inactive=false,screenMode=28,selectedClass=4,requested=2,before=3,after=2}}
  a.Complete(s);local target=aux.CBMBank.old.rewardReceipt;local r=Ledger.Read(target.manualLedger,1)
  assert(r.ledgerRevision==9007199254740991 and #r.choices==1 and r.choices[1].before==1 and r.choices[1].after==2)
  assert(#r.retired.choices.proficiencies==1 and r.retired.choices.proficiencies[1].delta==2)
  assert(r.retired.choices.skills[1].id==6 and r.retired.choices.skills[1].delta==5 and #r.retired.choices.hlas==51)
  assert(r.retired.hp.encoded=="11:4;"and r.oldHLA.stage=="deferred"and r.retired.hlasEnqueued)
  assert(Store.WireSnapshot(aux.CBMBank))
  target.manualLedger.previousOwnerKey=target.manualLedger.ownerKey;target.manualLedger.ownerKey=string.rep("c",32)
  assert(Ledger.Read(target.manualLedger,1).ownerKey==string.rep("b",32)) -- CHR association never rewrites provenance
 end)
 return count
end
'''
def main():
    results=[]
    for name,Runtime in [('Lua5.1',Lua51),('LuaJIT2.1',LuaJIT)]:
        lua=Runtime(unpack_returned_tuples=True)
        lua.globals().M=lua.execute((ROOT/'dual_reward_receipts.lua').read_text())
        lua.globals().Store=lua.execute((ROOT.parent/'xp-banking'/'cbmbank_store.lua').read_text())
        lua.globals().Ledger=lua.execute((ROOT/'dual_manual_ledger.lua').read_text())
        lua.globals().NewAdapter=lambda:lua.execute((ROOT/'dual_manual_receipts.lua').read_text())
        lua.execute(HARNESS);lua.execute(CASES)
        results.append({'runtime':name,'scenarios':lua.eval('runManual')(),'passed':True})
        # Compile the actual loader without invoking Install.
        loader=lua.execute((ROOT/'dual_manual_hooks.lua').read_text());assert loader['Install']
    (ROOT/'dual-manual-receipts-check-results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))
if __name__=='__main__':main()
