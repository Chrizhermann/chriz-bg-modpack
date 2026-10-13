"""Offline EEex-field receipt protocol checks; no engine/game/save is run."""
from pathlib import Path
import hashlib
import json
from lupa.lua51 import LuaRuntime as Lua51
from lupa.luajit21 import LuaRuntime as LuaJIT

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'dual_reward_receipts.lua'
HARNESS=r'''
local nextPointer=0
EEex_UDToPtr=function(object)
    return object.pointer
end
EEex_Sprite_GetActiveStats=function(sprite)
    return sprite.m_bAllowEffectListCall~=0 and sprite.m_derivedStats or sprite.m_tempStats
end
local function ptr(object) nextPointer=nextPointer+1;object.pointer=nextPointer;return object end
local function rr(text) return {get=function() return text end} end
local ufields={"m_effectId","m_targetType","m_spellLevel","m_dWFlags","m_durationType","m_duration",
 "m_probabilityUpper","m_probabilityLower","m_numDice","m_diceSize","m_savingThrow","m_special",
 "m_school","m_JeremyIsAnIdiot","m_minLevel","m_maxLevel","m_flags","m_sourceType",
 "m_sourceFlags","m_projectileType","m_casterLevel","m_firstCall","m_secondaryType"}
local sfields={"m_effectAmount","m_saveMod","m_effectAmount2","m_effectAmount3","m_effectAmount4",
 "m_effectAmount5","m_slotNum","m_sourceId","m_sourceTarget"}
function effect(op,amount,source)
 local e={};for _,k in ipairs(ufields) do e[k]=0 end;for _,k in ipairs(sfields) do e[k]=-1 end
 e.m_effectId=op;e.m_effectAmount=amount;e.m_durationType=9;e.m_dWFlags=101
 for _,k in ipairs({"m_res","m_res2","m_res3","m_sourceRes"}) do e[k]=rr(source) end
 return e
end
function list(values)
 local head;for i=#values,1,-1 do head=ptr{data=values[i],pNext=head} end;return {m_pNodeHead=head}
end
function fixture()
 local b={m_xp=550000,m_flags=1,m_mageSpecUpperWord=32768,m_mageSpecialization=65535,
 m_level1=10,m_level2=0,m_level3=0,m_maxHitPointsBase=77,m_proficiencies={}}
 for i=0,14 do b.m_proficiencies[i]=i-7 end
 for _,k in ipairs({"m_hideInShadowsBase","m_detectIllusionBase","m_setTrapsBase","m_lockPickingBase",
 "m_moveSilentlyBase","m_trapsBase","m_pickPocketBase"}) do b[k]=45 end
 local function stats(raw) return {GetAtOffset=function(_,id) return raw+id-89 end} end
 local sprite={m_baseStats=b,m_startTypeAI={m_Class=2},m_bAllowEffectListCall=1,
 m_derivedStats=stats(17),m_tempStats=stats(-42),m_timedEffectList=list{effect(233,35,"OLDPROF"),effect(12,999,"UNRELATE"),effect(233,35,"OLDPROF")},
 m_equipedEffectList=list{effect(233,7,"MODITEM")}}
 local context={ownerKey=string.rep("a",32),incarnation="123",revision=8,oldClass=2,newClass=4}
 local boundary={stage="preparing",incarnation="123",newClass=4,preBase=550000}
 CBMBank_Reset={Query=function() return boundary end}
 return sprite,context,boundary
end
function equal(a,b,seen)
 if type(a)~=type(b) then return false end
 if type(a)~="table" then return a==b end
 seen=seen or {};if seen[a]==b then return true end;seen[a]=b
 for k,v in pairs(a) do if not equal(v,b[k],seen) then return false end end
 for k in pairs(b) do if a[k]==nil then return false end end
 return true
end
function copy(t,seen)
 if type(t)~="table" then return t end
 seen=seen or {};if seen[t] then return seen[t] end;local n={};seen[t]=n
 for k,v in pairs(t) do n[k]=copy(v,seen) end;return n
end
function serializable(t,seen)
 local ty=type(t);if ty=="number" or ty=="string" or ty=="boolean" then return true end
 assert(ty=="table","Non-detached receipt value")
 seen=seen or {};assert(not seen[t],"Receipt alias/cycle");seen[t]=true
 for k,v in pairs(t) do assert(type(k)=="number" or type(k)=="string");serializable(v,seen) end
end
local count=0
function check(fn) fn();count=count+1 end
function reject(edit)
 local s,c,b=fixture();edit(s,c,b);local before=copy(s);local cbefore=copy(c)
 local ok=pcall(M.CaptureBeforeDual,s,c);assert(not ok);assert(equal(s,before));assert(equal(c,cbefore))
end
function run()
 check(function()
  local s,c,b=fixture();c.newClass=nil;b.stage="capturing";CBMBank_Reset.PreviewQuery=function() return b end
  local saved=copy(s);local r=M.CaptureBeforePreview(s,c)
  assert(r.captureBoundary=="before_dual_preview" and r.newClass==nil)
  assert(r.oldClass==2 and r.oldLevelAtDual==10 and equal(saved,s))
  local wire,why=Store.WireSnapshot(r);assert(wire,why);assert(equal(wire,r))
  s.m_derivedStats.GetAtOffset=function() return 57 end
  assert(r.before.proficiencies[1].raw==17) -- detached from later new-class choices
 end)
 for _,change in ipairs({function(b)b.stage="preview" end,function(b)b.incarnation="stale" end,
    function(b)b.preBase=0 end}) do check(function()
  local s,c,b=fixture();b.stage="capturing";CBMBank_Reset.PreviewQuery=function()return b end
  change(b);local saved=copy(s);assert(not pcall(M.CaptureBeforePreview,s,c));assert(equal(saved,s))
 end) end
 check(function()
  local s,c=fixture();local before=copy(s);local cc=copy(c);local r=M.CaptureBeforeDual(s,c)
  assert(equal(s,before) and equal(c,cc));serializable(r)
  assert(r.before.kit==2147549183 and r.oldLevelAtDual==10 and r.before.maxHPBase==77)
  assert(#r.before.proficiencies==46 and #r.before.legacyProficiencies==15)
  assert(r.before.proficiencies[1].active==1 and r.before.proficiencies[1].inactive==2)
  assert(r.before.legacyProficiencies[1]==249 and r.before.legacyProficiencies[15]==7)
  assert(#r.before.effects.timed==2 and M.DecodeEffect(r.before.effects.timed[2]).listOrdinal==3)
  assert(M.DecodeEffect(r.before.effects.equipped[1]).m_sourceRes=="MODITEM")
  r.before.effects.timed[1]="changed";r.before.proficiencies[1].raw=0
  assert(equal(s,before));assert(M.DecodeEffect(M.CaptureBeforeDual(s,c).before.effects.timed[1]).m_effectAmount==35)
 end)
 check(function()
  local s,c=fixture();s.m_bAllowEffectListCall=0;local r=M.CaptureBeforeDual(s,c)
  assert(r.before.proficiencies[1].raw==4294967254 and r.before.proficiencies[1].active==6 and r.before.proficiencies[1].inactive==2)
  assert(r.before.signedInt32Encoding=="uint32_twos_complement")
 end)
 for _,value in ipairs({-129,-256,-32769,-65536,-8388609,-16777216,-2147483648,2147483647}) do check(function()
  local s,c=fixture();s.m_derivedStats.GetAtOffset=function() return value end
  s.m_timedEffectList.m_pNodeHead.data.m_effectAmount=value
  local r=M.CaptureBeforeDual(s,c);assert(r.before.proficiencies[1].raw==value%4294967296)
  assert(M.DecodeEffect(r.before.effects.timed[1]).m_effectAmount==value%4294967296)
 end) end
 for _,value in ipairs({4294967296,9007199254740991}) do check(function()
  local s,c=fixture();c.revision=value;assert(M.CaptureBeforeDual(s,c).ledgerRevision==value)
 end) end
 for _,size in ipairs({0,1,37,203}) do check(function()
  local s,c=fixture();local effects={};for i=1,size do effects[i]=effect(i%3==0 and 233 or 12,i,"CUSTOM") end
  s.m_timedEffectList=list(effects);local original=copy(s);local r=M.CaptureBeforeDual(s,c)
  assert(#r.before.effects.timed==math.floor(size/3));assert(equal(s,original))
  for i,e in ipairs(r.before.effects.timed) do local d=M.DecodeEffect(e);assert(d.listOrdinal==i*3 and d.m_effectAmount==i*3) end
 end) end
 check(function()
  local s,c=fixture();local effects={};for i=1,203 do effects[i]=effect(233,-129-i,"CUSTOM") end
  s.m_timedEffectList=list(effects);local r=M.CaptureBeforeDual(s,c)
  local wire,why=Store.WireSnapshot(r);assert(wire,why);assert(equal(wire,r))
  assert(#wire.before.effects.timed==203)
  for i,e in ipairs(wire.before.effects.timed) do
   local d=M.DecodeEffect(e);assert(d.listOrdinal==i and d.m_effectAmount==(-129-i)%4294967296)
  end
 end)
 for _,packed in ipairs({"", "z123", "00", string.rep("0",500)}) do check(function()
  assert(not pcall(M.DecodeEffect,packed))
 end) end
 for _,flag in ipairs({8,16,32,64,128,256}) do check(function() reject(function(s) s.m_baseStats.m_flags=flag end) end) end
 local bad={
  function(s,c,b) b.stage="native" end,function(s,c,b) b.stage="completing" end,
  function(s,c,b) b.incarnation="124" end,function(s,c,b) b.newClass=1 end,
  function(s,c,b) b.preBase=0 end,function(s,c) c.ownerKey="bad" end,
  function(s,c) c.ownerKey=string.rep("A",32) end,function(s,c) c.incarnation=123 end,
  function(s,c) c.revision=-1 end,function(s,c) c.revision=1.1 end,function(s,c) c.revision=9007199254740992 end,
  function(s,c) c.newClass=c.oldClass end,function(s,c) c.oldClass=1 end,
  function(s) s.m_baseStats.m_level1=0 end,function(s) s.m_baseStats.m_maxHitPointsBase=65536 end,
  function(s) s.m_baseStats.m_mageSpecUpperWord=-1 end,function(s) s.m_baseStats.m_proficiencies[7]=1.1 end,
  function(s) s.m_derivedStats.GetAtOffset=function() return 2147483648 end end,
  function(s) local h=s.m_timedEffectList.m_pNodeHead;h.pNext.pNext.pNext=h end,
  function(s) s.m_equipedEffectList.m_pNodeHead.data.m_sourceRes=rr("TOO_LONG_RES") end,
 }
 for _,f in ipairs(bad) do check(function() reject(f) end) end
 return count
end
'''

def main():
    results=[]
    for name,Runtime in [('Lua 5.1',Lua51),('LuaJIT 2.1',LuaJIT)]:
        lua=Runtime(unpack_returned_tuples=True)
        lua.globals().M=lua.execute(SOURCE.read_text())
        lua.globals().Store=lua.execute((ROOT.parent/'xp-banking'/'cbmbank_store.lua').read_text())
        lua.execute(HARNESS)
        count=lua.eval('run')()
        results.append({'runtime':name,'scenarios':count,'passed':True})
    output={'scope':'Offline public EEex-field capture protocol; not a live engine or reward mutation test',
            'results':results,'sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
    (ROOT/'dual-receipts-check-results.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))

if __name__=='__main__':main()
