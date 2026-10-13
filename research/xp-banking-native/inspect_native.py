"""Read-only PE disassembly for the XP-banking feasibility review.

Dependencies: capstone 5.0.9, pefile 2024.8.26. No executable is launched.
Output is textual disassembly only; no game binary bytes are copied.
"""
import argparse
import bisect
import hashlib
from pathlib import Path

import capstone
import pefile

p = argparse.ArgumentParser()
p.add_argument("exe", type=Path)
p.add_argument("names", type=Path)
p.add_argument("--function", action="append", default=[])
p.add_argument("--xrefs", action="append", default=[])
p.add_argument("--start", type=lambda x: int(x, 0))
p.add_argument("--size", type=lambda x: int(x, 0), default=256)
a = p.parse_args()
data = a.exe.read_bytes()
pe = pefile.PE(data=data)
base = pe.OPTIONAL_HEADER.ImageBase
names = {}
for line in a.names.read_text(encoding="utf-8").splitlines():
    address, _, name = line.partition("\t")
    if address.startswith("0x"):
        names[int(address, 16)] = name
keys = sorted(names)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
print(f"EXE: {a.exe}\nSHA256: {hashlib.sha256(data).hexdigest()}\nImageBase: {base:#x}")


def context(address):
    i = bisect.bisect_right(keys, address) - 1
    return f"{names[keys[i]]}+{address-keys[i]:#x}" if i >= 0 else "?"


def disasm(start, end):
    print(f"\n{context(start)} [{start:#x}, {end:#x})")
    for ins in md.disasm(pe.get_data(start-base, end-start), start):
        comment = ""
        if ins.mnemonic in ("call", "jmp") and ins.operands[0].type == capstone.CS_OP_IMM:
            comment = " ; " + context(ins.operands[0].imm)
        print(f"{ins.address:016x}  {ins.mnemonic:8s} {ins.op_str}{comment}")


for wanted in a.function:
    for i, address in enumerate(keys):
        if names[address] == wanted:
            disasm(address, keys[i+1])
if a.start is not None:
    disasm(a.start, a.start+a.size)
targets = {address for address, name in names.items() if name in a.xrefs}
if targets:
    print("\nDIRECT CALL/JMP XREFS (executable sections; function-name attribution is nearest preceding symbol)")
    for section in pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        # Candidate relative E8/E9 instructions are re-decoded at their address;
        # caller disassembly must establish an actual instruction boundary.
        raw = section.get_data()
        for i, b in enumerate(raw[:-4]):
            if b not in (0xE8, 0xE9):
                continue
            at = base+section.VirtualAddress+i
            target = at+5+int.from_bytes(raw[i+1:i+5], "little", signed=True)
            if target in targets:
                ins = next(md.disasm(raw[i:i+5], at))
                print(f"{at:#x} {ins.mnemonic} {target:#x} {names[target]} FROM {context(at)}")
