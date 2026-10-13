"""Offline checks only: parse Lua, inspect PE, emulate the real opcode104 leaf.

Never launches an executable, writes game files, or reads saves. The emulator
executes only the extracted 224-byte leaf against synthetic actor/effect memory.
It does not emulate EEex/Lua bridging or claim native game acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import capstone
from lupa.lua51 import LuaRuntime
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64
from unicorn.x86_const import UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_RSP, UC_X86_REG_RAX

ROOT = Path(__file__).parent
ENTRY = bytes.fromhex("4C8BC14C8BCA8B492085C90F848700")
BODY = bytes.fromhex("4183782401418B401C7522018270050000B80100000041C780180100000100000041C7801401000001000000C3")
FUNC_HASH = "b82b9164057049bbca1f2f7cbe5c98e3edf3595bc09aa1ab53ace0912e626c86"


def native_case(code, xp, amount, mode=0, timing=1):
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    code_at, effect, actor, stack = 0x100000, 0x200000, 0x300000, 0x400000
    for at, size in [(code_at, 0x1000), (effect, 0x1000), (actor, 0x4000), (stack, 0x1000)]:
        uc.mem_map(at, size)
    uc.mem_write(code_at, code)
    put = lambda at, n: uc.mem_write(at, struct.pack("<I", n & 0xffffffff))
    get = lambda at: struct.unpack("<I", uc.mem_read(at, 4))[0]
    put(effect + 0x1c, amount)
    put(effect + 0x20, mode)
    put(effect + 0x24, timing)
    put(actor + 0x570, xp)
    put(actor + 0x1180, 4321)
    put(actor + 0x2ad0, 1234)
    # RET exits to the emulation stop address. No engine code outside this leaf.
    uc.mem_write(stack + 0x800, struct.pack("<Q", code_at + len(code)))
    uc.reg_write(UC_X86_REG_RCX, effect)
    uc.reg_write(UC_X86_REG_RDX, actor)
    uc.reg_write(UC_X86_REG_RSP, stack + 0x800)
    uc.emu_start(code_at, code_at + len(code), count=100)
    return {"base": get(actor + 0x570), "derived": get(actor + 0x1180),
            "bonus": get(actor + 0x2ad0), "return": uc.reg_read(UC_X86_REG_RAX),
            "done": get(effect + 0x114), "force_repass": get(effect + 0x118)}


def check_exe(path):
    data = path.read_bytes()
    pe = pefile.PE(data=data)
    assert pe.FILE_HEADER.Machine == 0x8664
    assert data.count(ENTRY) == 1, "missing/ambiguous native entry signature"
    offset = data.index(ENTRY)
    rva = pe.get_rva_from_offset(offset)
    code = pe.get_data(rva, 0xe0)
    assert code[0x98:0x98+len(BODY)] == BODY
    assert hashlib.sha256(code).hexdigest() == FUNC_HASH
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    ins = list(md.disasm(code[:9], rva))
    assert [x.size for x in ins] == [3, 3, 3]
    assert [(x.mnemonic, x.op_str) for x in ins] == [
        ("mov", "r8, rcx"), ("mov", "r9, rdx"), ("mov", "ecx, dword ptr [rcx + 0x20]")]
    # Ordinary, boundary, huge, consecutive and explicit native-loss behavior.
    cases = [(0, 1), (160999, 1), (161000, 25), (499999, 99999999),
             (2950000, 2147483647), (0xfffffff0, 32), (1000, -27), (1000, 0)]
    for xp, amount in cases:
        result = native_case(code, xp, amount)
        assert result == {"base": (xp + amount) & 0xffffffff, "derived": 4321,
            "bonus": 1234, "return": 1, "done": 1, "force_repass": 1}
    for mode, amount, expected in [(1, 123, 123), (2, 25, 250)]:
        assert native_case(code, 1000, amount, mode)["base"] == expected
    result = native_case(code, 1000, 50, timing=0)
    assert result["base"] == 1000 and result["bonus"] == 1284 and result["done"] == 0
    xp = 160995
    for amount in [2, 3, 4, 2147483647]:
        xp = native_case(code, xp, amount)["base"]
    assert xp == (160995 + 2 + 3 + 4 + 2147483647) & 0xffffffff
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
            "opcode104_rva": hex(rva), "entry_signature_matches": 1,
            "function_sha256": FUNC_HASH, "emulated_cases": len(cases) + 2 + 1 + 4,
            "restored_instructions": [f"{i.mnemonic} {i.op_str}" for i in ins]}


def check_lua():
    lua = LuaRuntime(unpack_returned_tuples=True)
    module = lua.execute((ROOT / "xp_probe.lua").read_text(encoding="utf-8"))
    lua.globals().probe = module
    # Contract tests exercise the Lua snapshot/guard code only; no native APIs
    # are mocked into existence and install() must reject this environment.
    lua.execute(r'''
        local effect={m_effectAmount=17,m_effectId=104,m_dWFlags=0,m_durationType=1,
            m_sourceId=-1,m_sourceType=0,m_sourceRes={get=function() return "" end},m_done=1}
        local sprite={m_id=123,m_baseStats={m_xp=160999}}
        probe.planner=function(e) assert(e.actor_id==123); return 1 end
        local token=probe.before(effect,sprite)
        assert(token>0 and sprite.m_baseStats.m_xp==160999 and effect.m_effectAmount==17)
        assert(probe.pending[token].planned_allowance==1)
        assert(probe.pending[token].source_kind=="op104:add-positive")
        sprite.m_baseStats.m_xp=161016
        probe.after(effect,sprite,1,token)
        assert(probe.pending[token]==nil and #probe.records==1)
        assert(probe.records[1].native_delta==17 and probe.records[1].native_matches_add)
        probe.after(effect,sprite,1,token)
        assert(#probe.records==1) -- repeated callback cannot duplicate a record
        probe.with_internal_write(function() assert(probe.before(effect,sprite)==0) end)
        assert(probe.suppressed==1 and probe.suppressDepth==0)
        local ok=pcall(probe.with_internal_write,function() error("release failure") end)
        assert(not ok and probe.suppressDepth==0)
        probe.planner=function() return 18 end
        assert(probe.before(effect,sprite)==0 and #probe.errors==1)
        assert(sprite.m_baseStats.m_xp==161016 and effect.m_effectAmount==17)
        probe.planner=function() error("planner failure") end
        assert(probe.before(effect,sprite)==0 and #probe.errors==2 and not probe.busy)
        probe.planner=function() assert(probe.before(effect,sprite)==0); return 0 end
        assert(probe.before(effect,sprite)>0 and probe.reentrant==1)
        probe.planner=nil
        for _,entry in ipairs({{1,17,"op104:absolute-set"},{2,17,"op104:percentage"},
            {0,4294967295,"op104:add-loss"},{0,0,"op104:add-zero"}}) do
            effect.m_dWFlags, effect.m_effectAmount=entry[1],entry[2]
            local t=probe.before(effect,sprite)
            assert(probe.pending[t].source_kind==entry[3])
            probe.after(effect,sprite,1,t)
        end
        effect.m_dWFlags,effect.m_effectAmount,effect.m_durationType=0,17,0
        local t=probe.before(effect,sprite)
        assert(probe.pending[t].source_kind=="op104:nonpermanent-unclassified")
        probe.after(effect,sprite,1,t)
        assert(not pcall(probe.install,{observeOnly=true,engineVersion="2.6.6.0"}))
        assert(not probe.installed)
    ''')
    return "Lua 5.1 parsed; observer contract, proposal validation, errors, reentrancy, exclusion and absent-capability rejection passed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps({"executables": [check_exe(p) for p in args.exe],
                      "lua_checks": check_lua(),
                      "native_bridge_executed": False,
                      "game_launched": False}, indent=2))
