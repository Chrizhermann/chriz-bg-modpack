"""Read-only native proficiency UI callsite inventory; never invokes the game."""
import os
import hashlib
import json
from pathlib import Path

import capstone
import pefile

ROOT = Path(__file__).parent
DB = Path("C:/tmp/scroll-hook-research-20261009/EEex/EEex/loader")
BUILDS = {
    # Local game folders: set BG2EE_266_ROOT and BG2EE_273_ROOT.
    "2.6.6.0": (Path(os.path.expandvars("%BG2EE_266_ROOT%/Baldur.exe")),
                 "fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580"),
    "2.7.3.0": (Path(os.path.expandvars("%BG2EE_273_ROOT%/Baldur.exe")),
                 "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"),
}
FUNCTIONS = ["CScreenCreateChar::" + name for name in (
    "ResetLevelUpPanel", "ResetProficienciesPanel", "UpdateProficienciesPanel",
    "CanSpendProficiencySlots", "OnProficiencyPlusMinusButtonClick")]
QUERIES = {
    "CGameSprite::GetActiveProficiency", "CGameSprite::GetInactiveProficiency",
    "CGameSprite::SetActiveProficiency", "CGameSprite::SetInactiveProficiency",
    "CGameSprite::CombineAllActiveInactiveProficiencies", "CDerivedStats::GetAtOffset",
    "CRuleTables::GetProficiencyId", "CRuleTables::GetMaximumProficiency",
    "CRuleTables::GetProficiencySlots", "CRuleTables::GetClassProficiency",
}


def main():
    reports = []
    for version, (path, expected) in BUILDS.items():
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected, "unreviewed engine image"
        pe = pefile.PE(data=data); base = pe.OPTIONAL_HEADER.ImageBase
        names = {int(a, 16): n for a, n in (line.split("\t", 1) for line in
                 (DB / ("v" + version) / "bg2ee/function_names.db").read_text().splitlines() if "\t" in line)}
        by_name = {name: address for address, name in names.items()}
        addresses = sorted(names)
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); md.detail = True
        report = {"version": version, "sha256": expected, "functions": [], "queries": []}
        listing = [f"Read-only {path}; SHA256 {expected}"]
        for name in FUNCTIONS:
            at = by_name[name]; end = addresses[addresses.index(at) + 1]
            body = pe.get_data(at - base, end - at)
            instructions = list(md.disasm(body, at))
            report["functions"].append({"name": name, "rva": at - base, "size": len(body),
                                        "sha256": hashlib.sha256(body).hexdigest()})
            listing.append("\n" + name)
            for ins in instructions:
                target = names.get(ins.operands[0].imm) if ins.mnemonic in ("call", "jmp") and ins.operands[0].type == capstone.x86.X86_OP_IMM else None
                listing.append(f"{ins.address - base:08x} {ins.bytes.hex():24s} {ins.mnemonic:8s} {ins.op_str}" + (f" ; {target}" if target else ""))
            for i, ins in enumerate(instructions):
                if ins.mnemonic != "call" or ins.operands[0].type != capstone.x86.X86_OP_IMM: continue
                target = names.get(ins.operands[0].imm)
                if target not in QUERIES: continue
                window = instructions[max(0, i - 8):i + 5]
                report["queries"].append({"function": name, "target": target, "rva": ins.address - base,
                    "bytes": ins.bytes.hex(), "window": [f"{x.address - base:08x} {x.mnemonic} {x.op_str}" for x in window]})
        (ROOT / f"dual-active-ui-{version}.txt").write_text("\n".join(listing) + "\n")
        reports.append(report)
    (ROOT / "dual-active-ui-reads.json").write_text(json.dumps(reports, indent=2) + "\n")
    print(json.dumps([{k: (len(v) if isinstance(v, list) else v) for k, v in report.items()} for report in reports]))


if __name__ == "__main__": main()
