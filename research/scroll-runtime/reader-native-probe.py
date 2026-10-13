"""Bounded read-only native reader class/capability evidence.

Runs pinned PE code in Unicorn, never the game process. GetDeny is substituted
with a synthetic object lookup; no lookup, concurrency, live hooks, or modified
engine acceptance is claimed. Actual class split, level mapping, activity,
capability, and native kit-mask branches execute. No spellbook is populated.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import capstone
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import (
    UC_X86_REG_RAX, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8,
    UC_X86_REG_R9, UC_X86_REG_RSP, UC_X86_REG_RIP,
)

PINS = {
    "fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580": "2.6.6.0",
    "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57": "2.7.3.0",
}
# Independent expected physical class-slot ordering, not generated from code.
CLASSES = {
    1: (1,), 2: (2,), 3: (3,), 4: (4,), 5: (5,), 6: (6,),
    7: (2, 1), 8: (2, 3), 9: (2, 4), 10: (2, 1, 4),
    11: (11,), 12: (12,), 13: (1, 4), 14: (3, 1),
    15: (3, 4), 16: (2, 11), 17: (2, 1, 3), 18: (3, 12),
    19: (19,), 20: (20,), 21: (21,),
}
OLD_BITS = {2: 8, 1: 16, 3: 32, 4: 64, 11: 128, 12: 256}


def probe(exe, symbols):
    raw = exe.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest in PINS, "Unreviewed executable requires a new ABI audit"
    pe = pefile.PE(data=raw)
    base = pe.OPTIONAL_HEADER.ImageBase
    image = pe.get_memory_mapped_image()
    names = {name: int(address, 16) for line in symbols.read_text().splitlines()
             for address, _, name in [line.partition("\t")] if address.startswith("0x")}
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    uc.mem_map(base, (len(image) + 4095) & ~4095)
    uc.mem_write(base, image)
    actor, out, stack, stop = 0x30000000, 0x30010000, 0x20000000, 0x2000FFF0
    uc.mem_map(actor, 0x20000)
    uc.mem_map(stack, 0x10000)
    calls = 0
    lookup_ok = True

    def lookup(_, address, size, __):
        if address != names["CGameObjectArray::GetDeny"]:
            return
        assert uc.reg_read(UC_X86_REG_RCX) == 42
        if lookup_ok:
            uc.mem_write(uc.reg_read(UC_X86_REG_RDX), struct.pack("<Q", actor))
        uc.reg_write(UC_X86_REG_RAX, 0 if lookup_ok else 1)
        rsp = uc.reg_read(UC_X86_REG_RSP)
        target = struct.unpack("<Q", bytes(uc.mem_read(rsp, 8)))[0]
        uc.reg_write(UC_X86_REG_RSP, rsp + 8)
        uc.reg_write(UC_X86_REG_RIP, target)

    uc.hook_add(UC_HOOK_CODE, lookup)

    def call(name, *args):
        nonlocal calls
        before = bytes(uc.mem_read(actor, 0x10000))
        rsp = stack + 0x8008
        uc.mem_write(rsp, struct.pack("<Q", stop))
        uc.reg_write(UC_X86_REG_RSP, rsp)
        for reg, value in zip((UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8,
                               UC_X86_REG_R9), (*args, 0, 0, 0, 0)):
            uc.reg_write(reg, value)
        uc.emu_start(names[name], stop, count=2000)
        assert uc.reg_read(UC_X86_REG_RIP) == stop, name
        assert bytes(uc.mem_read(actor, 0x10000)) == before, name
        calls += 1
        return uc.reg_read(UC_X86_REG_RAX) & 0xFFFFFFFF

    def fixture(composite, levels=(7, 13, 19), flags=0, kit=0x4000,
                use_main=True, temporary=(3, 4, 5)):
        uc.mem_write(actor, b"\0" * 0x10000)
        for offset in (0x30, 0x4B68):
            uc.mem_write(actor + offset + 0xB, bytes([composite]))
            uc.mem_write(actor + offset + 0xC, struct.pack("<I", 42))
        uc.mem_write(actor + 0x568, struct.pack("<I", flags))
        uc.mem_write(actor + 0x79C, struct.pack("<HH", kit >> 16, kit & 0xFFFF))
        uc.mem_write(actor + 0x4EA4, struct.pack("<I", int(use_main)))
        for offset, values in ((0x1120, levels), (0x1DC8, temporary)):
            uc.mem_write(actor + offset + 0x46, struct.pack("<HHH", *values))

    def capabilities():
        # RCX is deliberately unmapped: neither native routine uses UI 'this'.
        return (call("CScreenWizSpell::CanCastMageSpells", 0xDEADBEEF, actor),
                call("CScreenPriestSpell::CanCastPriestSpells", 0xDEADBEEF, actor))

    def split():
        uc.mem_write(out, b"\xFE\xFD")
        call("CAIObjectType::GetActiveInactiveClasses", actor + 0x4B68, out, out + 1)
        return tuple(uc.mem_read(out, 2))

    arcane, divine = {1, 5, 19}, {3, 6, 11, 12, 21}
    results = []
    for composite, slots in CLASSES.items():
        fixture(composite)
        assert split() == (composite, composite)
        active = tuple(c for c in range(1, 22)
                       if call("CAIObjectType::IsUsableSubClass", actor + 0x4B68, c, 1))
        assert set(active) == set(slots), (composite, active, slots)
        for index, c in enumerate(slots):
            level = call("CDerivedStats::GetLevel", actor + 0x1120, composite, c)
            assert level == (7, 13, 19)[index], (composite, c, level)
        maximum = call("CDerivedStats::GetMaximumLevel", actor + 0x1120, composite)
        assert maximum == (7, 13, 19)[len(slots) - 1]
        cap = capabilities()
        assert cap == (int(bool(arcane.intersection(slots))),
                       int(bool(divine.intersection(slots)))), (composite, cap)
        results.append({"class": composite, "active": active, "capability": cap})

    duals = []
    for composite, slots in CLASSES.items():
        if len(slots) != 2:
            continue
        for old in slots:
            new = next(c for c in slots if c != old)
            for new_level in (8, 9, 10):
                levels = tuple(9 if c == old else new_level for c in slots) + (99,)
                fixture(composite, levels, OLD_BITS[old])
                assert split() == (new, old)
                got = {c for c in slots if call("CAIObjectType::IsUsableSubClass",
                                               actor + 0x4B68, c, 1)}
                active = {new} | ({old} if new_level > 9 else set())
                assert got == active, (composite, old, new_level, got)
                cap = capabilities()
                assert cap == (int(bool(arcane.intersection(active))),
                               int(bool(divine.intersection(active))))
                # For a valid two-class dual the new class is always the highest
                # active class, including after the old class reactivates.
                assert call("CDerivedStats::GetLevel", actor + 0x1120,
                            composite, new) == max(9 if c == old else new_level for c in active)
                duals.append([composite, old, new_level, sorted(got)])

    # Exact-equality dormant gate switches with the engine's effective stats.
    fixture(7, (9, 9, 99), 16, use_main=True, temporary=(10, 9, 88))
    assert capabilities() == (0, 0)  # old mage dormant, new fighter9
    uc.mem_write(actor + 0x4EA4, struct.pack("<I", 0))
    assert capabilities() == (1, 0)  # temporary fighter10 > mage9
    fixture(6, kit=0x10)
    assert capabilities() == (0, 0)  # native Inquisitor mask
    for c in (6, 12, 3):
        for flag in (0x200, 0x400):
            fixture(c, flags=flag)
            assert capabilities() == (0, 0)  # final fallen-flags gate is global
    for c in (1, 3, 5, 19, 21):
        fixture(c, (0, 0, 0), kit=0x4025)
        assert capabilities() == (int(c in arcane), int(c in divine))
        # Custom kit ID is accepted without a name/ID whitelist; only Paladin's
        # native mask lookup would consult installed KITLIST (not emulated here).
    fixture(7, (2, 10, 99), 16)
    lookup_ok = False
    assert split() == (7, 7)  # lookup failure silently resembles multiclass
    lookup_ok = True

    # Extract referenced native class constants from the actual capability code.
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    constants = {}
    for name, length in (("CScreenWizSpell::CanCastMageSpells", 0x70),
                         ("CScreenPriestSpell::CanCastPriestSpells", 0xE0)):
        start = names[name]
        refs = []
        for i in md.disasm(pe.get_data(start-base, length), start):
            if i.mnemonic == "movzx" and i.op_str.startswith("edx, byte ptr [rip"):
                target = i.address + i.size + i.operands[1].mem.disp
                refs.append({"address": hex(target), "class": pe.get_data(target-base, 1)[0]})
        constants[name] = refs
    return {"version": PINS[digest], "sha256": digest, "native_calls": calls,
            "all_calls_actor_bytes_unchanged": True,
            "functions": {n: hex(a) for n, a in names.items() if n in (
                "CAIObjectType::GetActiveInactiveClasses", "CAIObjectType::IsUsableSubClass",
                "CDerivedStats::GetLevel", "CDerivedStats::GetMaximumLevel",
                "CScreenWizSpell::CanCastMageSpells", "CScreenPriestSpell::CanCastPriestSpells",
                "CGameSprite::GetCasterLevel", "CSpell::GetCasterType")},
            "class_constants": constants, "single_or_multiclass": results, "dual_cases": duals,
            "limitations": "Synthetic GetDeny only; no live object lookup, installed detour, spellbook, custom Paladin KITLIST mapping, custom casting extension, or game acceptance."}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("exe", type=Path)
    p.add_argument("symbols", type=Path)
    args = p.parse_args()
    print(json.dumps(probe(args.exe, args.symbols), indent=2))
