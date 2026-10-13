"""Execute real native cap instructions after the new derived-XP pre-clamp.

The Lua selector is real; class/get-XP helper calls use stated fixture providers.
No game is launched, patched on disk, or installed. EEex bridge not executed.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import struct

import capstone
from lupa.lua51 import LuaRuntime
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.x86_const import *

ROOT = Path(__file__).parent
BUILDS = {
    "fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580":
        ("2.6.6.0", 0x34e71c, 0x34e7b8, 0x249be0),
    "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57":
        ("2.7.3.0", 0x34ed5c, 0x34edf8, 0x249e40),
}


def check(path):
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    version, call, stop, cap_target = BUILDS[sha]
    pe = pefile.PE(data=data)
    base = pe.OPTIONAL_HEADER.ImageBase
    call, start, stop = base + call, base + call + 5, base + stop
    code = pe.get_data(start-base, stop-start)
    call_bytes = pe.get_data(call-base, 5)
    assert call_bytes[0] == 0xE8
    assert call + 5 + struct.unpack("<i", call_bytes[1:])[0] == base + cap_target
    assert pe.get_data(call-base-6, 6).hex() == "488bd6498bcd"
    assert code[:16].hex() == "4c8d442450488bce488d542451448bf0"
    # The actual shared loader signature must select exactly this call.
    pattern = b"\x48\x8b\xd6\x49\x8b\xcd\xe8" + b"...." + bytes.fromhex("4c8d442450488bce488d542451448bf0")
    matches = list(re.finditer(re.escape(pattern[:7]) + b".{4}" + re.escape(pattern[11:]), data, re.DOTALL))
    assert len(matches) == 1 and base + pe.get_rva_from_offset(matches[0].start()) + 6 == call
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    instructions = list(md.disasm(code, start))
    calls = [int(i.op_str, 16) for i in instructions if i.mnemonic == "call"]
    assert len(calls) == 5 and calls[1] == calls[3] and calls[2] == calls[4]
    classes, class_id, get_xp = calls[:3]
    lua = LuaRuntime(unpack_returned_tuples=True)
    hook = lua.execute((ROOT / "cap_hook.lua").read_text(encoding="utf-8"))
    cases = []
    # Independent unhooked controls must exercise the actual native writes,
    # not merely leave an already-bounded value unchanged.
    for kind, retired, expected in [("single", 0, 500000), ("multi", 0, 500000),
                                    ("dual", 125000, 375000), ("dual", 500000, 0)]:
        result = emulate(code, start, stop, calls, 600000, 600000, 500000, kind, retired)
        assert result == dict(base=600000, derived=expected)
        cases.append(dict(control="unhooked native clamp", kind=kind, retired=retired, derived=expected))
    for kind in ["single", "multi", "dual"]:
        for phase in ["BG1", "SOD", "SOA", "TOB"]:
            for policy in ["bg1_sod", "bg1_sod_soa"]:
                for raw in [160999, 161000, 600000, 4000000, 0xfffffff0]:
                    for native in [500000, 8000000, 0xffffffff]:
                        snapshot = dict(eligible=True, policy=policy, phase=phase,
                                        classKind=kind, usableFloor=0)
                        retired = 125000 if kind == "dual" else 0
                        if kind == "dual":
                            snapshot.update(retiredDebit=161000, retiredNativeXP=retired)
                        selected = hook.Select(lua.table_from(snapshot), native, raw)
                        assert isinstance(selected, (int, float))
                        selected = int(selected)
                        result = emulate(code, start, stop, calls, raw, selected, native, kind, retired)
                        assert result["derived"] == selected
                        assert result["base"] == raw
                        cases.append(dict(kind=kind, phase=phase, policy=policy, raw=raw,
                                          native=native, derived=selected, preserved_base=True))
    # Adopted progress and fully consumed old-class allowance.
    for floor, retired in [(200000, 0), (600000, 0), (0, 500000)]:
        snapshot = dict(eligible=True, policy="bg1_sod", phase="BG1", usableFloor=floor,
                        classKind="dual" if retired else "single")
        if retired:
            snapshot.update(retiredDebit=retired, retiredNativeXP=retired)
        value = int(hook.Select(lua.table_from(snapshot), 8000000, 900000))
        result = emulate(code, start, stop, calls, 900000, value, 8000000, snapshot["classKind"], retired)
        assert result["derived"] == value and result["base"] == 900000
        cases.append(dict(floor=floor, retired=retired, derived=value, preserved_base=True))
    return dict(version=version, sha256=sha, call=hex(call), start=hex(start), stop=hex(stop),
                instruction_sha256=hashlib.sha256(code).hexdigest(), cases=len(cases),
                results=cases, bridge_executed=False, game_launched=False)


def emulate(code, start, stop, calls, raw, selected, native, kind, retired):
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    pages = {start & ~0xfff, (stop-1) & ~0xfff, *(x & ~0xfff for x in calls)}
    for page in pages:
        uc.mem_map(page, 0x1000)
    uc.mem_write(start, code)
    actor, stack = 0x200000, 0x300000
    uc.mem_map(actor, 0x4000)
    uc.mem_map(stack, 0x4000)
    put = lambda at, n: uc.mem_write(at, struct.pack("<I", n & 0xffffffff))
    get = lambda at: struct.unpack("<I", uc.mem_read(at, 4))[0]
    put(actor + 0x570, raw)
    put(actor + 0x1180, selected)
    before = bytes(uc.mem_read(actor, 0x4000))
    uc.reg_write(UC_X86_REG_RBX, actor)
    uc.reg_write(UC_X86_REG_R15, actor + 0x1120)
    uc.reg_write(UC_X86_REG_RSI, actor + 0x30)
    uc.reg_write(UC_X86_REG_R12, 0)
    uc.reg_write(UC_X86_REG_RAX, native)
    uc.reg_write(UC_X86_REG_RSP, stack + 0x1000)
    xp_reads = 0

    def call_provider(u, at, size, context):
        nonlocal xp_reads
        if at not in calls:
            return
        if at == calls[0]:
            u.mem_write(u.reg_read(UC_X86_REG_RDX), bytes([2 if kind == "dual" else 4]))
            u.mem_write(u.reg_read(UC_X86_REG_R8), bytes([4]))
        elif at == calls[1]:
            u.reg_write(UC_X86_REG_RAX, 9)
        else:
            u.reg_write(UC_X86_REG_RAX, get(actor+0x1180) if xp_reads == 0 else retired)
            xp_reads += 1
        rsp = u.reg_read(UC_X86_REG_RSP)
        target = struct.unpack("<Q", u.mem_read(rsp, 8))[0]
        u.reg_write(UC_X86_REG_RSP, rsp + 8)
        u.reg_write(UC_X86_REG_RIP, target)

    writes = []
    uc.hook_add(UC_HOOK_CODE, call_provider)
    uc.hook_add(UC_HOOK_MEM_WRITE, lambda u, access, at, size, value, _: writes.append((at, size)))
    uc.emu_start(start, stop, count=100)
    assert uc.reg_read(UC_X86_REG_RIP) == stop
    assert xp_reads == (2 if kind == "dual" else 0)
    for at, size in writes:
        assert stack <= at < stack + 0x4000 or (at == actor+0x1180 and size == 4)
    after = bytes(uc.mem_read(actor, 0x4000))
    assert before[:0x1180] == after[:0x1180] and before[0x1184:] == after[0x1184:]
    return dict(base=get(actor+0x570), derived=get(actor+0x1180))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    results = [check(path) for path in args.exe]
    args.out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{k: v for k, v in r.items() if k != "results"} for r in results], indent=2))
