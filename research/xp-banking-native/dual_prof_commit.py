"""Offline native proficiency semantics probe; no game process or save opened.

Executes pinned ApplyEffect / GetAtOffset / SetInactiveProficiency machine code
on synthetic mapped memory. The selected contiguous operator+= proficiency
window is executed too. No implementation of those operations is substituted.
This is evidence for a commit design, not an installed proficiency feature.
"""
import hashlib
import json
import struct
from pathlib import Path

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UcError
from unicorn import x86_const as x

from identity_probe import DEFAULT_CACHE, DEFAULT_EXES, MD

ROOT = Path(__file__).resolve().parent
ACTOR, EFFECT, NODE, STACK, STOP, SCRATCH = (0x200000, 0x210000, 0x220000,
                                           0x230008, 0x240000, 0x250000)


class Native:
    def __init__(self, version):
        self.pe = pefile.PE(str(DEFAULT_EXES[version]))
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        folder = "v2.6.6.0" if version == "2.6" else "v2.7.3.0"
        self.names = {}
        for line in (DEFAULT_CACHE/folder/"bg2ee/function_names.db").read_text().splitlines():
            addr, _, name = line.partition("\t")
            if addr.startswith("0x"):
                self.names.setdefault(name, []).append(int(addr, 16))
        self.uc = Uc(UC_ARCH_X86, UC_MODE_64)
        size = (self.pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095
        self.uc.mem_map(self.base, size)
        self.uc.mem_write(self.base, self.pe.get_memory_mapped_image())
        self.uc.mem_map(0x200000, 0x60000)
        # Locate and certify precisely the actual contiguous 46-DWORD fold.
        addr = self.fn("CDerivedStats::operator+=")
        ins = list(MD.disasm(self.pe.get_data(addr-self.base, 0xA70), addr))
        starts = [i for i, v in enumerate(ins)
                  if v.mnemonic == "mov" and v.op_str == "eax, dword ptr [rdi + 0xf8]"]
        assert len(starts) == 1
        k = starts[0]
        for idx in range(46):
            field = 0xF8 + idx*4
            assert ins[k+idx*2].mnemonic == "mov"
            assert ins[k+idx*2].op_str == f"eax, dword ptr [rdi + {field:#x}]"
            assert ins[k+idx*2+1].mnemonic == "add"
            assert ins[k+idx*2+1].op_str == f"dword ptr [rbx + {field:#x}], eax"
        self.fold_start, self.fold_end = ins[k].address, ins[k+92].address

    def fn(self, name):
        assert len(self.names[name]) == 1, name
        return self.names[name][0]

    def put(self, addr, value, size=4):
        self.uc.mem_write(addr, int(value).to_bytes(size, "little", signed=False))

    def get(self, addr, size=4):
        return int.from_bytes(self.uc.mem_read(addr, size), "little")

    def clear(self):
        self.uc.mem_write(ACTOR, bytes(0x60000))
        self.put(ACTOR+0x4EA4, 1)

    def call(self, name, rcx, rdx=0, r8=0, r9=0, home=SCRATCH):
        self.put(STACK, STOP, 8)
        self.put(STACK+8, home, 8)
        for reg, value in [(x.UC_X86_REG_RCX, rcx), (x.UC_X86_REG_RDX, rdx),
                           (x.UC_X86_REG_R8, r8), (x.UC_X86_REG_R9, r9),
                           (x.UC_X86_REG_RSP, STACK)]:
            self.uc.reg_write(reg, value)
        self.uc.emu_start(self.fn(name), STOP, count=10000)
        assert self.uc.reg_read(x.UC_X86_REG_RIP) == STOP
        return self.uc.reg_read(x.UC_X86_REG_RAX)

    def effect(self, at, stat, amount, mode=0, timing=9):
        self.uc.mem_write(at, bytes(0x158))
        for offset, value in [(0x10,233), (0x1C,amount), (0x20,stat | (mode << 16)),
                              (0x24,timing), (0xCC,1)]:
            self.put(at+offset, value)

    def apply(self, at=EFFECT, home=SCRATCH):
        return self.call("CGameEffectProficiency::ApplyEffect", at, ACTOR, home=home)

    def fold(self):
        self.uc.reg_write(x.UC_X86_REG_RBX, ACTOR+0x1120)
        self.uc.reg_write(x.UC_X86_REG_RDI, ACTOR+0x2A70)
        self.uc.emu_start(self.fold_start, self.fold_end, count=100)
        assert self.uc.reg_read(x.UC_X86_REG_RIP) == self.fold_end

    def value(self, stat):
        return self.call("CDerivedStats::GetAtOffset", ACTOR+0x1120, stat)

    def list(self, records):
        self.put(ACTOR+0x4A08, NODE if records else 0, 8)
        self.put(ACTOR+0x4A18, len(records))
        for idx, effect in enumerate(records):
            node = NODE+idx*0x20
            self.put(node, node+0x20 if idx+1 < len(records) else 0, 8)
            self.put(node+0x10, effect, 8)


def checks(version):
    n = Native(version)
    observations = []
    count = 0
    for stat in range(89,135):
        n.clear()
        field = 0x1218+(stat-89)*4
        bonus = 0x2B68+(stat-89)*4
        n.effect(EFFECT,stat,2)
        assert n.apply() == 1
        assert n.value(stat) == 2
        n.effect(EFFECT+0x200,stat,8,mode=1)
        n.apply(EFFECT+0x200)
        values = (n.get(ACTOR+field), n.get(ACTOR+bonus), n.get(SCRATCH))
        expected = (10,0,0) if stat == 92 else ((2,8,8) if stat == 99 else (2,8,0))
        assert values == expected, (version,stat,values)
        n.fold()
        assert n.value(stat) == 10
        count += 1
        if stat in (92,99):
            observations.append({"stat":stat,"before_fold_derived_bonus_home_pointee":values})

    # The halberd branch dereferences uninitialized caller home space. This is
    # an actual access fault, not a guessed semantic inconvenience.
    n.clear()
    n.effect(EFFECT,99,8,mode=1)
    try:
        n.apply(home=0xDEAD0000)
    except UcError:
        assert n.get(ACTOR+0x2B90) == 8
    else:
        raise AssertionError("Halberd unexpectedly ignored poisoned home pointer")
    count += 1

    # An invalid mode0 stat is an actual native success/no-op. A private marker
    # can give this persisted carrier meaning without an unsafe mode1 fallback.
    for stat in (0,88,135,0xFFFF):
        n.clear()
        n.effect(EFFECT,stat,3)
        n.put(EFFECT+0x60,99) # real proficiency (amount2), independent of flags
        n.uc.mem_write(EFFECT+0x94,b"CBMDPRF\0")
        n.uc.mem_write(EFFECT+0xA8,b"0123456789abcdef0123456789abcdef")
        actor_before = bytes(n.uc.mem_read(ACTOR,0x10000))
        effect_before = bytes(n.uc.mem_read(EFFECT,0x158))
        assert n.apply(home=0xDEAD0000) == 1
        assert bytes(n.uc.mem_read(ACTOR,0x10000)) == actor_before
        assert bytes(n.uc.mem_read(EFFECT,0x158)) == effect_before
        count += 1

    # Full actual v2 native Marshal with only allocator substitution, followed
    # by full actual CopyFromBase used by native DecodeEffectFromBase. Real
    # resource assignment/uppercasing, memset, and security checks all execute.
    # This proves the carrier fields survive that EFF codec, not an entire save.
    n.list([EFFECT])
    out, buffer, restored = SCRATCH+0x1000, SCRATCH+0x2000, EFFECT+0x400
    n.put(STACK+0x28,0)
    allocation_calls = []
    def allocator(uc,address,size,data):
        if address != n.fn("operator_new[]"):
            return
        allocation_calls.append(uc.reg_read(x.UC_X86_REG_RCX))
        assert allocation_calls == [0x108]
        rsp = uc.reg_read(x.UC_X86_REG_RSP)
        uc.reg_write(x.UC_X86_REG_RAX,buffer)
        uc.reg_write(x.UC_X86_REG_RIP,n.get(rsp,8))
        uc.reg_write(x.UC_X86_REG_RSP,rsp+8)
    hook = n.uc.hook_add(UC_HOOK_CODE,allocator)
    try:
        assert n.call("CGameEffectList::Marshal",ACTOR+0x4A00,out,1,1) == 0x108
        assert n.get(out,8) == buffer
        assert bytes(n.uc.mem_read(buffer,0x108)) == bytes(n.uc.mem_read(EFFECT+8,0x108))
        n.call("CGameEffect::CopyFromBase",restored,buffer)
    finally:
        n.uc.hook_del(hook)
    for offset,size in [(0x10,4),(0x1C,12),(0x60,4),(0x94,8),(0xA8,32)]:
        assert bytes(n.uc.mem_read(restored+offset,size)) == bytes(n.uc.mem_read(EFFECT+offset,size))
    restored_before = bytes(n.uc.mem_read(restored,0x158))
    assert n.apply(restored,home=0xDEAD0000) == 1
    assert bytes(n.uc.mem_read(restored,0x158)) == restored_before
    count += 1

    # Axe is written into derived stats immediately, so a later temporary SET
    # masks the private inactive increment. Other stats fold additive last.
    for stat, expected in [(89,11),(92,3)]:
        n.clear()
        n.effect(EFFECT,stat,8,mode=1)
        n.apply()
        n.effect(EFFECT+0x200,stat,3,timing=0)
        n.apply(EFFECT+0x200)
        n.fold()
        assert n.value(stat) == expected
        count += 1

    # Even with the correct inactive target, stock setter copies the existing
    # aggregate active bonus into BOTH plain permanent SET records. Timing and
    # full parameter2 filters leave temporary / mode1 records unchanged.
    n.clear()
    stat = 89
    records = [EFFECT+i*0x200 for i in range(4)]
    n.effect(records[0],stat,1 | (2<<3))
    n.effect(records[1],stat,2 | (3<<3))
    n.effect(records[2],stat,5,timing=0)
    n.effect(records[3],stat,1,mode=1)
    n.list(records)
    n.put(ACTOR+0x1218,3 | (3<<3))
    before = [bytes(n.uc.mem_read(e,0x158)) for e in records]
    n.call("CGameSprite::SetInactiveProficiency",ACTOR,stat,4,0)
    assert [n.get(e+0x1C) for e in records] == [35,35,5,1]
    for idx,e in enumerate(records):
        expected = bytearray(before[idx])
        if idx < 2:
            struct.pack_into("<I",expected,0x1C,35)
        assert bytes(n.uc.mem_read(e,0x158)) == expected
    # Re-evaluate the last permanent SET and the unchanged active+1 bonus:
    n.put(ACTOR+0x1218,0)
    n.put(ACTOR+0x2B68,0)
    n.apply(records[1])
    n.apply(records[3])
    n.fold()
    assert n.value(stat) == 36 # active4, old4: prior active3 was inflated.
    count += 1

    # Proposed existing-SET transformation edits only bits3..5 independently.
    # Extra flags/high bits and each individual active base remain untouched.
    # Use actual mode0 native handlers to prove last SET wins, not max/add.
    for ordering in [(0,1),(1,0)]:
        n.clear()
        originals = [0x100 | 1 | (2<<3), 0x200 | 2 | (3<<3)]
        for idx,packed in enumerate(originals):
            n.effect(EFFECT+idx*0x200,89,packed)
            after = (packed & ~0x38) | ((((packed>>3)&7)+1)<<3)
            n.put(EFFECT+idx*0x200+0x1C,after)
        for idx in ordering:
            n.apply(EFFECT+idx*0x200)
        packed = originals[ordering[-1]]
        assert n.value(89) == ((packed & ~0x38) | ((((packed>>3)&7)+1)<<3))
        count += 1

    # Actual stock merge uses cached aggregate rather than class records; a
    # temporary SET can erase earned old pips or become a permanent allocation.
    for mask,expected in [(None,27),(0,0),(4,4)]:
        n.clear();n.effect(EFFECT,89,1|(3<<3));n.list([EFFECT]);n.apply()
        if mask is not None:
            n.effect(EFFECT+0x200,89,mask,timing=0);n.apply(EFFECT+0x200)
        n.call("CGameSprite::CombineActiveInactiveProficiency",ACTOR,89)
        assert n.get(EFFECT+0x1C)==expected
        count += 1

    # Audit the DATA insertion overload, not the misleading CPtrList::AddTail
    # symbol (which appends another list). Real AddTail/NewNode/RemoveAt execute
    # with a seeded native node free-list; no allocator helper is substituted.
    n.clear();linked=ACTOR+0x4A00
    for i in range(3):
        n.put(NODE+i*0x18,NODE+(i+1)*0x18 if i<2 else 0,8)
    n.put(linked+0x20,NODE,8)
    nodes=[]
    for i in range(3):
        node=n.call("CObList::AddTail",linked,EFFECT+i*0x200)
        nodes.append(node)
        assert node==NODE+i*0x18
        assert n.get(node+0x10,8)==EFFECT+i*0x200
        assert n.get(linked+0x18)==i+1
        assert n.get(linked+8,8)==nodes[0] and n.get(linked+0x10,8)==nodes[-1]
        count+=1
    for index in (1,0,2):
        n.call("CObList::RemoveAt",linked,nodes[index])
        remaining=[nodes[i] for i in range(3) if i not in ({1} if index==1 else {1,0} if index==0 else {0,1,2})]
        assert n.get(linked+0x18)==len(remaining)
        assert n.get(linked+8,8)==(remaining[0] if remaining else 0)
        assert n.get(linked+0x10,8)==(remaining[-1] if remaining else 0)
        count+=1

    return {"cases":count,
            "exe_sha256":hashlib.sha256(DEFAULT_EXES[version].read_bytes()).hexdigest(),
            "native_additive_anomalies":observations,
            "actual_functions":["CGameEffectProficiency::ApplyEffect", "CDerivedStats::GetAtOffset",
                                "CGameSprite::SetInactiveProficiency", "CGameEffectList::ModifyAllOfType"],
            "actual_instruction_window":"CDerivedStats::operator+= contiguous proficiency fold",
            "helper_stubs":["operator_new[] returns a synthetic 0x108-byte buffer only during native v2 Marshal"],
            "marshal_scope":"full native v2 Marshal and full CopyFromBase; not whole-save/unmarshal integration",
            "game_launched":False}


if __name__ == "__main__":
    report = {v:checks(v) for v in ("2.6","2.7")}
    profiles=[]
    for version in ("2.6","2.7"):
        n=Native(version)
        all_addresses=sorted({a for addresses in n.names.values() for a in addresses})
        functions={}
        for key,name in {"base_construct":"CGameEffectBase::CGameEffectBase",
                         "decode_base":"CGameEffect::DecodeEffectFromBase",
                         "add_tail":"CObList::AddTail","remove_at":"CObList::RemoveAt"}.items():
            at=n.fn(name);end=all_addresses[all_addresses.index(at)+1]
            functions[key]={"rva":at-n.base,"bytes":n.pe.get_data(at-n.base,end-at).hex(),"name":name}
        profiles.append({"version":version,"gameTimestamp":n.pe.FILE_HEADER.TimeDateStamp,
                         "gameSize":n.pe.OPTIONAL_HEADER.SizeOfImage,"functions":functions})
    def lua(value):
        if isinstance(value,str):return json.dumps(value)
        if isinstance(value,int):return str(value)
        if isinstance(value,list):return "{"+",".join(lua(v) for v in value)+"}"
        return "{"+",".join("["+json.dumps(k)+"]="+lua(v) for k,v in value.items())+"}"
    (ROOT/"dual_prof_commit_profiles.lua").write_text("-- Read-only PE extraction by dual_prof_commit.py; full direct-boundary bodies.\nreturn "+lua(profiles)+"\n")
    (ROOT/"dual-prof-commit-check-results.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
