"""Pinned, read-only retired reward delivery source inventory."""
import hashlib
import json
from pathlib import Path

import capstone
import pefile
from dual_active_ui_reads import BUILDS, DB

ROOT = Path(__file__).parent
FUNCTIONS = [
    "CScreenCreateChar::LevelUp", "CGameSprite::AddNewSpecialAbilities",
    "CGameSprite::AddClassAbilities", "CGameSprite::AddNewSpellsPriest",
    "CRuleTables::GetNumLevelUpAbilities", "CRuleTables::GetLevelUpAbilities",
    "CScreenCreateChar::CompleteCharacterHighLevelAbilities", "CRuleTables::GetSavingThrow",
    "CRuleTables::GetTHAC0", "CRuleTables::GetMaxMemorizedSpellsMage",
    "CRuleTables::GetMaxMemorizedSpellsPriest", "CRuleTables::FindSavingThrow",
    "CRuleTables::FindTHAC0",
]


def inventory():
    reports = []
    for version, (path, expected) in BUILDS.items():
        data = path.read_bytes(); assert hashlib.sha256(data).hexdigest() == expected
        pe = pefile.PE(data=data); base = pe.OPTIONAL_HEADER.ImageBase
        names = {int(a, 16): n for a, n in (line.split("\t", 1) for line in
                 (DB / ("v" + version) / "bg2ee/function_names.db").read_text().splitlines() if "\t" in line)}
        by_name = {name: address for address, name in names.items()}; addresses = sorted(names)
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); md.detail = True
        report = {"version": version, "sha256": expected, "functions": []}
        listing = [f"Read-only {path}; SHA256 {expected}"]
        for name in FUNCTIONS:
            at = by_name[name]; end = addresses[addresses.index(at) + 1]
            body = pe.get_data(at - base, end - at); instructions = list(md.disasm(body, at))
            function = {"name": name, "rva": at - base, "size": len(body),
                        "sha256": hashlib.sha256(body).hexdigest(), "calls": []}
            listing.append("\n" + name)
            for i, ins in enumerate(instructions):
                target = names.get(ins.operands[0].imm) if ins.mnemonic in ("call", "jmp") and ins.operands[0].type == capstone.x86.X86_OP_IMM else None
                listing.append(f"{ins.address - base:08x} {ins.bytes.hex():24s} {ins.mnemonic:8s} {ins.op_str}" + (f" ; {target}" if target else ""))
                if ins.mnemonic == "call" and target:
                    function["calls"].append({"target": target, "rva": ins.address - base, "bytes": ins.bytes.hex(),
                        "window": [f"{x.address - base:08x} {x.mnemonic} {x.op_str}" for x in instructions[max(0, i - 6):i + 3]]})
            report["functions"].append(function)
        (ROOT / f"dual-old-reward-delivery-{version}.txt").write_text("\n".join(listing) + "\n")
        reports.append(report)
    (ROOT / "dual-old-reward-delivery.json").write_text(json.dumps(reports, indent=2) + "\n")
    return reports


if __name__ == "__main__":
    print(json.dumps([{ "version": r["version"], "functions": len(r["functions"])} for r in inventory()]))
