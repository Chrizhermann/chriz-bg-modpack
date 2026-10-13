"""Combined dual preflight against the encodings EEex really writes for relays.

EEex_Stats_Patch hooks three CDerivedStats calls with HookAfterCall: the call
site becomes E9 to a relay whose first instruction calls the original callee.
EEex assembles that `call` with AsmJit, which may encode it as E8 rel32,
REX+E8 rel32 (relocatable form) or FF 15 through its address table. The LIVE
bytes below were read from a real 2.7.3.0 game's memory (EEex 1.2.0); that
game refused to start banking while the preflight accepted only plain E8.
"""
from importlib import import_module
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "research/xp-banking-native"
STAMP, SIZE = 1780012861, 55779328  # Baldur.exe 2.7.3.0
RELAY_ERROR = "EEex stats relay does not preserve native first call"

# label: (relay address, relay's first instruction) at image base 0x140000000
LIVE = {
    "Hook-CDerivedStats::Construct()-FirstCall": (0x1435553C8, "40e8a2a4eafc"),
    "Hook-CDerivedStats::operator_equ()-FirstCall": (0x143555540, "40e80a2fcafc"),
    "Hook-CDerivedStats::Destruct()-FirstCall": (0x143555404, "40e8d635cafc"),
}

HARNESS = r'''
BASE=0x140000000
function le32(n) n=n%4294967296 local s='' for _=1,4 do s=s..string.format('%02x',n%256) n=math.floor(n/256) end return s end
function le64(n) return le32(n%4294967296)..le32(math.floor(n/4294967296)) end
function run(form,signedProvider)
 memory={};labels={}
 local function put(at,hex) for i=1,#hex,2 do memory[at+(i-1)/2]=tonumber(hex:sub(i,i+1),16) end end
 function EEex_ReadU8(at) local v=memory[at] if v==nil then error('unmapped native read',0) end return v end
 -- The shipped LuaJIT provider can expose uint32 through a signed integer.
 function EEex_ReadU32(at) local v=0 for i=3,0,-1 do v=v*256+EEex_ReadU8(at+i) end
  if signedProvider and v>=2147483648 then v=v-4294967296 end return v end
 function EEex_TryLabel(n) return labels[n] end
 local C,Q
 for _,p in ipairs(combined) do if p.gameTimestamp==STAMP then C=p end end
 for _,p in ipairs(prof) do if p.gameTimestamp==STAMP then Q=p end end
 for _,p in pairs(C.functions) do put(BASE+p.rva,p.bytes) end
 for _,p in pairs(Q.functions) do put(BASE+p.rva,p.bytes) end
 for _,f in ipairs(C.nextCalls) do put(BASE+f.rva,f.bytes) end
 for _,f in ipairs(C.getterCalls) do put(BASE+f.rva,f.bytes) end
 for _,k in ipairs({'combineCall','firstSpecialCall','untouchedSpecialReplay'}) do put(BASE+C[k].rva,C[k].bytes) end
 if form~='untouched' then
  for _,p in pairs(C.functions) do local h=p.eeexAfterCall
   if h then
    local site,callee=BASE+p.rva+h.offset,BASE+h.calleeRva
    local relay=form=='live' and live[h.label][1] or site+0x10000000
    labels[h.label]=site
    put(site,'e9'..le32(relay-site-5))
    if form=='live' then put(relay,live[h.label][2])
    elseif form=='e8' then put(relay,'e8'..le32(callee-relay-5))
    elseif form=='rex48' then put(relay,'48e8'..le32(callee-relay-6))
    elseif form=='table' then put(relay,'ff15'..le32(0x10));put(relay+0x16,le64(callee))
    elseif form=='wrong-rex' then put(relay,'40e8'..le32(callee+1-relay-6))
    elseif form=='wrong-table' then put(relay,'ff15'..le32(0x10));put(relay+0x16,le64(callee+16))
    elseif form=='nop-call' then put(relay,'90e8'..le32(callee-relay-6))
    else error('unknown form '..form) end
   end
  end
 end
 return pcall(hooks.Preflight,{profiles=combined,profProfiles=prof,profDLLPath='p',rulesDLLPath='r'},
  BASE,STAMP,SIZE)
end
'''


@pytest.fixture(params=["lua51", "luajit21"])
def lua(request):
    runtime = import_module("lupa." + request.param).LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(f"STAMP={STAMP} SIZE={SIZE}")
    runtime.execute("live={" + ",".join(
        f'["{label}"]={{{relay},"{first}"}}' for label, (relay, first) in LIVE.items()) + "}")
    runtime.execute(HARNESS)
    g = runtime.globals()
    g.combined = runtime.execute((NATIVE / "dual_combined_profiles.lua").read_text())
    g.prof = runtime.execute((NATIVE / "dual_prof_commit_profiles.lua").read_text())
    g.hooks = runtime.execute((NATIVE / "dual_combined_hooks.lua").read_text())
    return runtime


@pytest.mark.parametrize("signed", [False, True])
@pytest.mark.parametrize("form", ["live", "e8", "rex48", "table", "untouched"])
def test_preflight_accepts_every_encoding_of_the_original_first_call(lua, form, signed):
    ok, result = lua.globals().run(form, signed)
    assert ok, result


@pytest.mark.parametrize("signed", [False, True])
@pytest.mark.parametrize("form", ["wrong-rex", "wrong-table", "nop-call"])
def test_preflight_still_refuses_a_relay_that_does_not_call_the_original_first(lua, form, signed):
    ok, result = lua.globals().run(form, signed)
    assert not ok
    assert RELAY_ERROR in str(result)
