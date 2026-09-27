"""Read-only offline inspection of item display functions; never attaches to a game.

Developer tool, not release payload. Requires pefile and capstone on PYTHONPATH.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from pathlib import Path

import capstone
import pefile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("symbols", type=Path)
    parser.add_argument("functions", nargs="+")
    parser.add_argument("--callers", action="store_true")
    args = parser.parse_args()
    symbols = {}
    for line in args.symbols.read_text(encoding="utf-8").splitlines():
        address, name = line.split("\t", 1)
        symbols[int(address, 16)] = name
    pe = pefile.PE(str(args.executable))
    image = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    addresses = sorted(symbols)
    disasm = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    disasm.skipdata = True
    wanted = {address: name for address, name in symbols.items() if name in args.functions}
    for address, name in wanted.items():
        end = addresses[bisect_right(addresses, address)]
        print(f"\n{name} at {address:x}")
        for ins in disasm.disasm(image[address - base:end - base], address):
            target = ""
            if ins.mnemonic in {"call", "jmp"} and ins.op_str.startswith("0x"):
                target = symbols.get(int(ins.op_str, 16), "")
            print(f"{ins.address:x}: {ins.bytes.hex():<30} {ins.mnemonic:8} {ins.op_str:45} {target}")
    if args.callers:
        for section in pe.sections:
            if not section.Characteristics & 0x20000000:
                continue
            start = base + section.VirtualAddress
            for ins in disasm.disasm(section.get_data(), start):
                if ins.mnemonic not in {"call", "jmp"} or not ins.op_str.startswith("0x"):
                    continue
                target = int(ins.op_str, 16)
                if target in wanted:
                    parent = addresses[bisect_right(addresses, ins.address) - 1]
                    print(f"CALLER {symbols[parent]} {ins.address:x} -> {wanted[target]}")


if __name__ == "__main__":
    main()
