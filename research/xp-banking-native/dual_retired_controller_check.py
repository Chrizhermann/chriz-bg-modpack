"""Actual controller protocol with declared account/native boundary fixtures.
Does not claim to render a menu or apply retired rewards.
"""
from pathlib import Path
import json
from lupa.lua51 import LuaRuntime as Lua51
from lupa.luajit21 import LuaRuntime as LuaJIT
ROOT=Path(__file__).parent
CASES=r'''
local function copy(a)local n={};for k,v in pairs(a)do n[k]=v end;return n end
local actor={};local current={ownerKey=string.rep("b",32),incarnation="18446744073709551614",
 revision=9007199254740991,oldClass=2,activeClass=4,oldKit=0x4001,oldLevel=10,
 oldUsableXP=550000,activeUsableXP=200000,hasCleanReceipt=true}
local count=0;local missing=false;local target=11;local blocked=false
local runtime={OldProgression=function(s)assert(s==actor);if missing then return nil,"Pending manual journal"end;return copy(current)end}
local rules={Target=function(s,a)assert(s==actor and a.oldUsableXP==current.oldUsableXP);return target end}
local entry={Check=function(s,a,n)assert(s==actor and n==target);return not blocked,"Native restriction"end}
local c=Module.New(runtime,rules,entry)
local prepared=assert(c.Preflight(actor));assert(c.Revalidate(actor,prepared));count=count+1
for _,key in ipairs({"ownerKey","incarnation","revision","oldClass","activeClass","oldKit","oldLevel","oldUsableXP","activeUsableXP"})do
 local original=current[key];current[key]=type(original)=="number" and original-1 or "changed"
 assert(not c.Revalidate(actor,prepared));current[key]=original;count=count+1
end
target=12;assert(not c.Revalidate(actor,prepared));target=11;count=count+1
current.arbitraryEquipmentChanged=true;assert(c.Revalidate(actor,prepared));count=count+1
target=10;assert(not c.Preflight(actor));target=11;count=count+1
current.hasCleanReceipt=false;assert(not c.Preflight(actor));current.hasCleanReceipt=true;count=count+1
blocked=true;assert(not c.Preflight(actor));blocked=false;count=count+1
missing=true;assert(not c.Preflight(actor));count=count+1
return count
'''
def main():
 out=[]
 for runtime in (Lua51,LuaJIT):
  l=runtime(unpack_returned_tuples=True);l.globals().Module=l.execute((ROOT/'dual_retired_controller.lua').read_text())
  count=l.execute(CASES);out.append({'runtime':runtime.__module__,'cases':count})
 report={'results':out,'scope':'Detached controller/account/native boundary protocol only; no rendered UI or game mutation'}
 (ROOT/'dual-retired-controller-check-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
