"""Offline profile extraction and real entry-trampoline checks. No EXE launch.

Only reads the explicitly supplied PE files, and the cached pinned loader DBs.
Writes our own Lua/text/JSON evidence; no game resource or save is opened.
"""
import os
import argparse
import hashlib
import json
from pathlib import Path

import capstone
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn import x86_const as x

ROOT = Path(__file__).resolve().parent
DEFAULT_CACHE = Path("C:/tmp/scroll-hook-research-20261009/EEex/EEex/loader")
DEFAULT_EXES = {
    # Local game folders: set BG2EE_266_ROOT and BG2EE_273_ROOT.
    "2.6": Path(os.path.expandvars("%BG2EE_266_ROOT%/Baldur.exe")),
    "2.7": Path(os.path.expandvars("%BG2EE_273_ROOT%/Baldur.exe")),
}
GAME_FUNCTIONS = {
    "copy": ("CGameSprite::Copy", 0),
    "marshal": ("CGameSprite::Marshal", 1),
    "export": ("CInfGame::CharacterExport", 0),
    "import": ("CInfGame::CharacterImport", 0),
}
DLL_FUNCTIONS = {"construct": "EEex::Sprite_Hook_OnConstruct", "destruct": "EEex::Sprite_Hook_OnDestruct"}
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
MD.detail = True


def dll_registration(pe, name):
    """Find actual compiled exportPattern(name, function), not a guessed RVA."""
    raw, base = pe.__data__, pe.OPTIONAL_HEADER.ImageBase
    needle = name.encode("utf-16le") + b"\0\0"
    offset = raw.find(needle)
    assert offset >= 0 and raw.find(needle, offset + 1) < 0, name
    target = base + pe.get_rva_from_offset(offset)
    matches = []
    for sec in pe.sections:
        if not sec.Characteristics & 0x20000000:
            continue
        code = sec.get_data()
        for i in range(len(code)-7):
            if code[i:i+3] != b"\x48\x8d\x15":
                continue
            at = base + sec.VirtualAddress + i
            if at + 7 + int.from_bytes(code[i+3:i+7], "little", signed=True) != target:
                continue
            instructions = list(MD.disasm(pe.get_data(at-base, 48), at))
            # lea rdx,label; lea rcx,temp; call string ctor; nop;
            # lea rdx,function; lea rcx,temp; call exportPattern
            assert [v.mnemonic for v in instructions[:7]] == ["lea", "lea", "call", "nop", "lea", "lea", "call"]
            fn = instructions[4]
            assert fn.op_str.startswith("rdx, [rip ")
            matches.append(fn.address + fn.size + fn.operands[1].mem.disp - base)
    assert len(matches) == 1, (name, matches)
    return matches[0]


def profile_entry(pe, rva):
    span = 0
    for ins in MD.disasm(pe.get_data(rva, 32), pe.OPTIONAL_HEADER.ImageBase+rva):
        # EEex StoreBytesAssembly does not relocate RIP memory / control flow.
        assert ins.mnemonic in {"mov", "push", "sub", "lea"}, ins
        assert not any(o.type == capstone.CS_OP_MEM and o.mem.base == capstone.x86.X86_REG_RIP for o in ins.operands)
        span += ins.size
        if span >= 5:
            return {"rva": rva, "span": span, "bytes": pe.get_data(rva, span).hex()}
    raise AssertionError("No safe entry span")


def check_relocation(pe, entry):
    """Execute the actual stolen native instructions at original and JIT address.

    Tests nonvolatile/volatile registers, flags, full stack writes and return
    to original+span. Neither native game nor native EEex process is launched.
    """
    original = pe.OPTIONAL_HEADER.ImageBase + entry["rva"]
    trampoline = original + 0x1000000
    code = bytes.fromhex(entry["bytes"])
    results = []
    regs = [x.UC_X86_REG_RAX, x.UC_X86_REG_RBX, x.UC_X86_REG_RCX, x.UC_X86_REG_RDX,
            x.UC_X86_REG_RSI, x.UC_X86_REG_RDI, x.UC_X86_REG_RBP, x.UC_X86_REG_R8,
            x.UC_X86_REG_R9, x.UC_X86_REG_R10, x.UC_X86_REG_R11, x.UC_X86_REG_R12,
            x.UC_X86_REG_R13, x.UC_X86_REG_R14, x.UC_X86_REG_R15, x.UC_X86_REG_RSP,
            x.UC_X86_REG_EFLAGS]
    for seed in range(5):
        pair = []
        for start in (original, trampoline):
            uc = Uc(UC_ARCH_X86, UC_MODE_64)
            uc.mem_map(original & ~0xFFF, 0x2000)
            uc.mem_map(trampoline & ~0xFFF, 0x2000)
            uc.mem_map(0x100000, 0x20000)
            uc.mem_write(original, code + b"\xcc")
            disp = (original+len(code)) - (trampoline+len(code)+5)
            uc.mem_write(trampoline, code + b"\xe9" + disp.to_bytes(4, "little", signed=True))
            uc.mem_write(0x100000, bytes((i*17+seed)%256 for i in range(0x20000)))
            for i, reg in enumerate(regs[:-2]):
                uc.reg_write(reg, 0xF0100000 + i*0x105 + seed)
            uc.reg_write(x.UC_X86_REG_RSP, 0x110008)
            uc.reg_write(x.UC_X86_REG_EFLAGS, 0x202 | (seed & 1))
            uc.emu_start(start, original+len(code), count=40)
            assert uc.reg_read(x.UC_X86_REG_RIP) == original+len(code)
            pair.append(([uc.reg_read(r) for r in regs], bytes(uc.mem_read(0x100000, 0x20000))))
        assert pair[0] == pair[1], entry
        results.append(True)
    return len(results)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--exe26", type=Path, default=DEFAULT_EXES["2.6"])
    p.add_argument("--exe27", type=Path, default=DEFAULT_EXES["2.7"])
    p.add_argument("--eeex27-default", type=Path,
                   default=DEFAULT_EXES["2.7"].parent / "EEex.dll")
    args = p.parse_args()
    profiles, reports = {}, {}
    for version, exe in [("2.6", args.exe26), ("2.7", args.exe27)]:
        folder = "v2.6.6.0" if version == "2.6" else "v2.7.3.0"
        dll = args.cache / folder / "EEex.dll"
        game, eeex = pefile.PE(str(exe)), pefile.PE(str(dll))
        names = {}
        for line in (args.cache/folder/"bg2ee/function_names.db").read_text().splitlines():
            address, _, name = line.partition("\t")
            if address.startswith("0x"):
                names.setdefault(name, []).append(int(address, 16)-game.OPTIONAL_HEADER.ImageBase)
        profile = {"gameTimestamp": game.FILE_HEADER.TimeDateStamp,
                   "gameSize": game.OPTIONAL_HEADER.SizeOfImage,
                   "eeexTimestamp": eeex.FILE_HEADER.TimeDateStamp,
                   "eeexSize": eeex.OPTIONAL_HEADER.SizeOfImage,
                   "entries": {}}
        checks = 0
        for slot, (name, index) in GAME_FUNCTIONS.items():
            entry = profile_entry(game, names[name][index])
            entry["module"] = "game"
            profile["entries"][slot] = entry
            checks += check_relocation(game, entry)
        for slot, name in DLL_FUNCTIONS.items():
            entry = profile_entry(eeex, dll_registration(eeex, name))
            entry.update(module="eeex", label=name)
            profile["entries"][slot] = entry
            checks += check_relocation(eeex, entry)
        profiles[version] = profile
        reports[version] = {"entry_trampoline_checks": checks,
                            "game_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
                            "eeex_sha256": hashlib.sha256(dll.read_bytes()).hexdigest()}
    # The collection's current EEex 1.2 uses the same typed lifetime ABI at
    # different RVAs. Inspect its actual compiled registrations and relocate
    # its instructions; do not require an upgrade to the research version.
    default_eeex = pefile.PE(str(args.eeex27_default))
    alternate = {"eeexTimestamp": default_eeex.FILE_HEADER.TimeDateStamp,
                 "eeexSize": default_eeex.OPTIONAL_HEADER.SizeOfImage,
                 "entries": {}}
    alternate_checks = 0
    for slot, name in DLL_FUNCTIONS.items():
        entry = profile_entry(default_eeex, dll_registration(default_eeex, name))
        entry.update(module="eeex", label=name)
        alternate["entries"][slot] = entry
        alternate_checks += check_relocation(default_eeex, entry)
    profiles["2.7"]["eeexAlternates"] = {"collection-1.2": alternate}
    reports["2.7-collection-1.2"] = {
        "entry_trampoline_checks": alternate_checks,
        "eeex_sha256": hashlib.sha256(args.eeex27_default.read_bytes()).hexdigest()}
    def lua(v):
        if isinstance(v, str): return json.dumps(v)
        if isinstance(v, int): return str(v)
        return "{" + ",".join("["+json.dumps(k)+"]="+lua(value) for k,value in v.items()) + "}"
    (ROOT/"identity_profiles.lua").write_text("-- Generated from pinned read-only PEs by identity_probe.py.\nreturn " + lua(profiles) + "\n")
    (ROOT/"identity-check-results.json").write_text(json.dumps({"profiles": reports, "game_launched": False}, indent=2)+"\n")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__": main()
