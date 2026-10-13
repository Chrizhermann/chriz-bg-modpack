"""Execute bounded, unmodified native ability-selector loops in Unicorn.

This does not launch Baldur.exe, install a hook, or access a game/save directory
for writing. The seven instruction windows come from the named read-only PE.
CSpell resource getters and integer max are substituted with fixture providers;
the native compare/branch/header-selection instructions execute unchanged.

Requires capstone 5.0.9, pefile 2024.8.26, unicorn 2.1.4. This proves a scalar
override at each boundary changes header selection. It does NOT prove context
propagation, reflection, charge use, classification, or live engine acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import capstone
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.x86_const import (
    UC_X86_REG_RAX, UC_X86_REG_RBP, UC_X86_REG_RSP, UC_X86_REG_RIP,
    UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_RDI, UC_X86_REG_RBX,
    UC_X86_REG_R12, UC_X86_REG_R13, UC_X86_REG_R14, UC_X86_REG_R15,
)


PINS = {
    "fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580": "2.6.6.0",
    "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57": "2.7.3.0",
}
# start/stop are relative to actual native symbols, not absolute ASLR addresses.
WINDOWS = (
    ("CGameEffect::FireSpell", 0xFD, 0x168, "stack", UC_X86_REG_R13, "146/2"),
    ("CGameAIBase::FireSpell", 0x161, 0x1E1, UC_X86_REG_R8, UC_X86_REG_RAX, "146/1 message"),
    ("CGameAIBase::FireSpellPoint", 0x132, 0x1AB, UC_X86_REG_R8, UC_X86_REG_RAX, "148/1 and 148/2"),
    ("CGameAIBase::ForceSpell", 0x33B, 0x394, UC_X86_REG_R14, UC_X86_REG_RAX, "146/0 action"),
    ("CGameAIBase::ForceSpellPoint", 0x17A, 0x1CB, UC_X86_REG_R12, UC_X86_REG_RAX, "148/0 action"),
    ("CGameSprite::Spell", 0xC6D, 0xCC0, "sprite", UC_X86_REG_R13, "EEex special-bit SpellNoDec selection"),
    ("CGameSprite::SpellPoint", 0xBDB, 0xC3E, "sprite", UC_X86_REG_R13, "EEex special-bit SpellPointNoDec selection"),
)


def probe(executable: Path, symbols: Path):
    raw = executable.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest not in PINS:
        raise ValueError("Unreviewed executable: instruction windows require a new ABI audit")
    pe = pefile.PE(data=raw)
    base = pe.OPTIONAL_HEADER.ImageBase
    image = pe.get_memory_mapped_image()
    addresses = {}
    names = {}
    for line in symbols.read_text(encoding="utf-8").splitlines():
        address, _, name = line.partition("\t")
        if address.startswith("0x"):
            addresses[name] = int(address, 16)
            names[int(address, 16)] = name
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    summary = []
    for name, start_off, stop_off, level_reg, result_reg, modes in WINDOWS:
        start = addresses[name] + start_off
        stop = addresses[name] + stop_off
        code = pe.get_data(start-base, stop-start)
        instructions = {i.address: i for i in md.disasm(code, start)}
        assert sum(i.size for i in instructions.values()) == len(code)
        assert stop == max(i.address+i.size for i in instructions.values())
        cases = []
        for minimums in ((1, 6, 12, 20), (1, 5, 10, 15, 25)):
            for level in (1, 3, 5, 6, 7, 10, 12, 15, 19, 20, 25, 30):
                uc = Uc(UC_ARCH_X86, UC_MODE_64)
                uc.mem_map(base, (len(image)+4095) & ~4095)
                uc.mem_write(base, image)
                stack, data = 0x20000000, 0x30000000
                uc.mem_map(stack, 0x10000)
                uc.mem_map(data, 0x10000)
                rsp, rbp = stack+0x8000, stack+0xA000
                uc.reg_write(UC_X86_REG_RSP, rsp)
                uc.reg_write(UC_X86_REG_RBP, rbp)
                uc.reg_write(UC_X86_REG_R15, data)
                uc.reg_write(UC_X86_REG_RDI, data)
                headers = [data+0x1000+i*0x100 for i in range(len(minimums))]
                for header, minimum in zip(headers, minimums):
                    uc.mem_write(header+0x10, struct.pack("<H", minimum))
                # Native target/item/effect data lives outside the stack. A byte
                # comparison below catches any unexpected resource/actor write.
                uc.mem_write(data+0x8000, b"READER|SCROLL|CHARGES|TARGET|MODE"*64)
                if level_reg == "stack":
                    uc.mem_write(rbp+0x77, struct.pack("<I", level))
                elif level_reg == "sprite":
                    uc.reg_write(UC_X86_REG_RBX, data)
                    uc.reg_write(UC_X86_REG_RDI, 0)
                    uc.reg_write(UC_X86_REG_R15, 0)
                    uc.mem_write(data+0x4C8A, struct.pack("<H", level))
                    uc.mem_write(data+0x4AE0, struct.pack("<Q", data+0x100))
                else:
                    uc.reg_write(level_reg, level)
                sentinel = bytes(uc.mem_read(data, 0x10000))
                calls = []
                writes = []

                def on_write(_, __, address, size, value, ___):
                    writes.append((address, size))
                    assert stack <= address < stack+0x10000

                def on_code(_, address, size, __):
                    ins = instructions[address]
                    if ins.mnemonic != "call":
                        return
                    assert ins.operands[0].type == capstone.CS_OP_IMM
                    target_name = names.get(ins.operands[0].imm)
                    if target_name == "CSpell::GetAbilityCount":
                        result = len(headers)
                    elif target_name == "CSpell::GetAbility":
                        index = uc.reg_read(UC_X86_REG_RDX) & 0xFFFFFFFF
                        result = headers[index] if index < len(headers) else 0
                    elif target_name == "max":
                        values = [struct.unpack("<i", bytes(uc.mem_read(uc.reg_read(reg), 4)))[0]
                                  for reg in (UC_X86_REG_RCX, UC_X86_REG_RDX)]
                        result = max(values)
                    else:
                        raise AssertionError((name, hex(address), target_name))
                    calls.append(target_name)
                    uc.reg_write(UC_X86_REG_RAX, result)
                    uc.reg_write(UC_X86_REG_RIP, address+size)

                uc.hook_add(UC_HOOK_CODE, on_code)
                uc.hook_add(UC_HOOK_MEM_WRITE, on_write)
                uc.emu_start(start, stop, count=1000)
                assert uc.reg_read(UC_X86_REG_RIP) == stop
                chosen = headers.index(uc.reg_read(result_reg))
                expected = max(i for i, minimum in enumerate(minimums) if minimum <= level)
                assert chosen == expected, (name, minimums, level, chosen, expected)
                assert bytes(uc.mem_read(data, 0x10000)) == sentinel
                cases.append({"headers": minimums, "level": level, "chosen": chosen})
        summary.append({"function": name, "modes": modes, "start": hex(start),
                        "stop": hex(stop), "window_sha256": hashlib.sha256(code).hexdigest(),
                        "cases": cases, "resource_actor_writes": 0})
    return {"version": PINS[digest], "exe_sha256": digest, "image_base": hex(base),
            "status": "offline native selector emulation only", "windows": summary,
            "passed": sum(len(row["cases"]) for row in summary)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("symbols", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = probe(args.executable, args.symbols)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"PASS {result['passed']} native selector cases, BG2EE {result['version']}; no game launched")
