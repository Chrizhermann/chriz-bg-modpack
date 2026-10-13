"""Pure exact-receipt replacement checks. No native HP mutation or game run."""
from pathlib import Path
import json
from lupa.lua51 import LuaRuntime as Lua51
from lupa.luajit21 import LuaRuntime as LuaJIT
ROOT=Path(__file__).parent
TEST=r'''
local count=0
local function check(f)f();count=count+1 end
local function roll(level,hp)return{level=level,contribution=hp}end
check(function()
 local p=M.Plan(10,12,11,{roll(11,7),roll(12,3)},{roll(11,4)})
 assert(M.Delta(p)==6 and p.replacements[1].replacedActiveContribution==4)
 assert(p.replacements[2].replacedActiveContribution==0)
 local w,why=Store.WireSnapshot(p);assert(w,why);assert(M.Delta(w)==6)
end)
for _,delta in ipairs({-32767,-256,-129,-1,0,1,5,129})do check(function()
 local old,active=1,1-delta;if delta>0 then old,active=1+delta,1 end
 local p=M.Plan(10,11,11,{roll(11,old)},{roll(11,active)})
 assert(M.Delta(p)==delta)
 local w,why=Store.WireSnapshot(p);assert(w,why);assert(M.Delta(w)==delta)
end)end
check(function()local p=M.Plan(10,10,1,{},{});assert(M.Delta(p)==0 and #p.replacements==0)end)
for _,bad in ipairs({
 function()M.Plan(10,11,11,{roll(11,8)},{})end,
 function()M.Plan(10,12,11,{roll(11,8)},{roll(11,4)})end,
 function()M.Plan(10,11,11,{roll(11,8),roll(11,8)},{roll(11,4)})end,
 function()M.Plan(10,11,11,{roll(10,8),roll(11,8)},{roll(11,4)})end,
 function()M.Plan(10,11,11,{roll(11,0)},{roll(11,4)})end,
 function()M.Plan(10,11,11,{roll(11,8)},{roll(11,4),roll(10,4)})end,
 function()M.Plan(11,10,11,{},{})end,
})do check(function()assert(not pcall(bad))end)end
for _,case in ipairs({{40,5,55,45},{40,-5,45,35},{2,-8,42,1},{1,-256,42,1},
 {50,-10,35,35},{0,5,55,0},{-4,8,55,-4},{50,100,70,70}})do check(function()
 assert(M.CurrentAfter(case[1],case[2],case[3])==case[4])
end)end
return count
'''
results=[]
for name,Runtime in [('Lua5.1',Lua51),('LuaJIT2.1',LuaJIT)]:
 lua=Runtime(unpack_returned_tuples=True)
 lua.globals().M=lua.execute((ROOT/'dual_hp_replacement.lua').read_text())
 lua.globals().Store=lua.execute((ROOT.parent/'xp-banking/cbmbank_store.lua').read_text())
 results.append(dict(runtime=name,passed=lua.execute(TEST)))
report=dict(results=results,game_run=False,native_mutation_tested=False)
(ROOT/'dual-hp-replacement-check-results.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
