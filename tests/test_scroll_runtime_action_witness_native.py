"""Run the real CString and CAIAction bodies of each pinned build in Unicorn,
never the game, against a witness laid out as action_witness.hpp issues it.
Native copies share the witness, replacement and destruction release it, and
every reviewed writer copies a shared block first, so the engine never frees
or writes a witness. Only allocation, freeing, memcpy and CAIObjectType are
substituted; their own CStrings are not the witness field. The audit test
checks that these are the only bodies that ever touch an action's m_source.
"""
import json
import struct
import sys

import capstone
import pytest
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn import x86_const as X

from test_scroll_runtime_binding import pinned_image, SOURCE
from test_scroll_runtime_native import WITNESS_BASELINE

STRINGS = (0x08, 0x20, 0x38, 0x60, 0x68, 0x80)  # every CString a CAIAction owns
STACK, HEAP, RETURN = 0x20000000, 0x30000000, 0x40000000


class Engine:
    def __init__(self, image):
        pe, version, names = image
        self.base = pe.OPTIONAL_HEADER.ImageBase
        self.named = {}
        for address, name in sorted(names.items()):
            self.named.setdefault(name, []).append(address)
        audit = json.loads((SOURCE / f"dispatch-audit-{version}.json").read_text())
        self.string = {label: self.base + row["rva"] for label, row in audit["string_functions"].items()}
        self.default = self.base + next(row["rva"] for row in audit["functions"] if row["label"] == "action_default")
        uc = self.uc = Uc(UC_ARCH_X86, UC_MODE_64)
        mapped = pe.get_memory_mapped_image()
        uc.mem_map(self.base, (len(mapped) + 0xFFF) & ~0xFFF)
        uc.mem_write(self.base, mapped)
        for at, size in ((STACK, 0x10000), (HEAP, 0x100000), (RETURN, 0x1000)):
            uc.mem_map(at, size)
        uc.mem_write(RETURN, b"\xCC")
        self.empty = self.u64(self.base + audit["empty_sentinel_global"])
        assert self.u32(self.empty - 12, signed=True) < 0 and self.u32(self.empty - 8) == 0
        self.next, self.freed, self.allocated = HEAP + 0x1000, [], []
        stubs = {self.only("CString::AllocBuffer"): self.alloc_buffer, self.only("CString::FreeData"): self.free_data,
                 self.only("memcpy"): self.memcpy}
        # CAIObjectType copies its own members; it never sees the +80h field.
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        for function in (self.copy, self.assign, self.default):
            for ins in md.disasm(bytes(uc.mem_read(function, 0x100)), function):
                if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
                    target = int(ins.op_str, 16)
                    if names.get(target, "").startswith("CAIObjectType::"):
                        stubs[target] = lambda: self.reg("rcx")
                if ins.mnemonic == "ret":
                    break
        for address, emulate in stubs.items():
            uc.hook_add(UC_HOOK_CODE, self.stub(emulate), begin=address, end=address)

    def only(self, name):
        found = self.named[name]
        assert len(found) == 1, name
        return found[0]

    @property
    def copy(self):
        # The lowest CAIAction::CAIAction is the copy constructor in both builds:
        # it shares exactly the three action-level CStrings with the CString copy.
        address = min(self.named["CAIAction::CAIAction"])
        assert bytes(self.uc.mem_read(address, 0xB6)).count(b"\xE8") >= 6
        return address

    @property
    def assign(self):
        return self.only("CAIAction::operator=")

    @property
    def destroy(self):
        return self.only("CAIAction::~CAIAction")

    def reg(self, name, value=None):
        register = getattr(X, "UC_X86_REG_" + name.upper())
        if value is None:
            return self.uc.reg_read(register)
        self.uc.reg_write(register, value)

    def u64(self, at):
        return struct.unpack("<Q", self.uc.mem_read(at, 8))[0]

    def u32(self, at, signed=False):
        return struct.unpack("<i" if signed else "<I", self.uc.mem_read(at, 4))[0]

    def put64(self, at, value):
        self.uc.mem_write(at, struct.pack("<Q", value))

    def stub(self, emulate):
        def hook(uc, address, size, user):
            result = emulate()
            back = self.u64(self.reg("rsp"))
            self.reg("rsp", self.reg("rsp") + 8)
            if result is not None:
                self.reg("rax", result)
            self.reg("rip", back)
        return hook

    def alloc(self, size):
        at = self.next
        self.next += (size + 0x1F) & ~0xF
        return at

    def block(self, refs, text=b"", capacity=None):
        capacity = len(text) if capacity is None else capacity
        header = self.alloc(12 + capacity + 1)
        self.uc.mem_write(header, struct.pack("<iii", refs, len(text), capacity) + text + b"\0")
        return header + 12

    def alloc_buffer(self):
        this, length = self.reg("rcx"), self.reg("rdx") & 0xFFFFFFFF
        data = self.empty if not length else self.block(1, capacity=length)
        if length:
            self.uc.mem_write(data - 8, struct.pack("<i", length))
            self.allocated.append(data)
        self.put64(this, data)

    def free_data(self):
        self.freed.append(self.reg("rcx"))

    def memcpy(self):
        destination, source, count = self.reg("rcx"), self.reg("rdx"), self.reg("r8")
        self.uc.mem_write(destination, bytes(self.uc.mem_read(source, count)))
        return destination

    def call(self, function, rcx, rdx=0, r8=0, r9=0):
        rsp = STACK + 0x8000
        self.put64(rsp, RETURN)
        for name, value in (("rcx", rcx), ("rdx", rdx), ("r8", r8), ("r9", r9), ("rsp", rsp)):
            self.reg(name, value)
        self.uc.emu_start(function, RETURN, count=100000)
        assert self.reg("rip") == RETURN
        return self.reg("rax")

    def witness(self, holders=1):
        header = self.alloc(16)
        self.uc.mem_write(header, struct.pack("<iii", WITNESS_BASELINE + holders, 0, 0) + b"\0\0\0\0")
        return header + 12

    def refs(self, data):
        return self.u32(data - 12, signed=True)

    def untouched(self, witness):
        return bytes(self.uc.mem_read(witness - 8, 12)) == bytes(12) and witness - 12 not in self.freed

    def field(self, value=None):
        at = self.alloc(8)
        self.put64(at, self.empty if value is None else value)
        return at

    def action(self, witness=None):
        at = self.alloc(0x88)
        self.uc.mem_write(at, bytes(0x88))
        for offset in STRINGS:
            self.put64(at + offset, self.empty)
        if witness:
            self.put64(at + 0x80, witness)
        return at


def test_engine_cstring_bodies_share_release_and_never_write_a_witness(pinned_image):
    e = Engine(pinned_image)
    w = e.witness()
    a, b, c = e.field(w), e.field(0), e.field()
    e.call(e.string["copy"], b, a)
    assert e.u64(b) == w and e.refs(w) == WITNESS_BASELINE + 2
    e.call(e.string["assign"], c, a)
    assert e.u64(c) == w and e.refs(w) == WITNESS_BASELINE + 3
    e.call(e.string["assign"], a, a)  # actual operator= self-assignment
    assert e.u64(a) == w and e.refs(w) == WITNESS_BASELINE + 3
    e.call(e.string["assign"], c, e.field())  # replaced by the engine's empty string
    assert e.u64(c) == e.empty and e.refs(w) == WITNESS_BASELINE + 2
    text = e.block(1, b"SCRIPT")  # one holder: the source field below
    e.call(e.string["assign"], c, a)
    e.call(e.string["assign"], c, e.field(text))  # replaced by an ordinary engine string
    assert e.u64(c) == text and e.refs(text) == 2 and e.refs(w) == WITNESS_BASELINE + 2
    e.call(e.string["destroy"], b)
    assert e.refs(w) == WITNESS_BASELINE + 1
    sentinel = e.refs(e.empty)
    e.call(e.string["destroy"], e.field())  # the shared sentinel is never released
    assert e.refs(e.empty) == sentinel
    # Every reviewed writer first gives a field holding the witness its own block.
    payload = e.block(1, b"xyz")
    for writer, arguments in (("assign_copy", (3, payload)), ("copy_before_write", ()),
                              ("get_buffer", (8,)), ("concat_in_place", (3, payload))):
        d = e.field()
        e.call(e.string["assign"], d, a)
        assert e.refs(w) == WITNESS_BASELINE + 2
        e.call(e.string[writer], d, *arguments)
        assert e.u64(d) != w and e.refs(w) == WITNESS_BASELINE + 1, writer
    assert e.untouched(w) and e.refs(w) == WITNESS_BASELINE + 1


def test_engine_action_bodies_carry_and_release_the_witness(pinned_image):
    e = Engine(pinned_image)
    w = e.witness()
    source = e.action(w)
    built = e.alloc(0x88)
    e.uc.mem_write(built, b"\xA5" * 0x88)
    e.call(e.default, built)  # native construction writes only the shared sentinel
    assert all(e.u64(built + offset) == e.empty for offset in (0x60, 0x68, 0x80))
    copied = e.alloc(0x88)
    e.uc.mem_write(copied, b"\xA5" * 0x88)
    for offset in (0x08, 0x20, 0x38):
        e.put64(copied + offset, e.empty)  # CAIObjectType::Set is substituted
    e.call(e.copy, copied, source)  # InsertAction's queue node
    assert e.u64(copied + 0x80) == w and e.refs(w) == WITNESS_BASELINE + 2
    current = e.action()
    e.call(e.assign, current, copied)  # GetNextAction / SetCurrAction assignment
    assert e.u64(current + 0x80) == w and e.refs(w) == WITNESS_BASELINE + 3
    e.call(e.destroy, copied)
    e.call(e.destroy, source)
    assert e.refs(w) == WITNESS_BASELINE + 1
    e.call(e.assign, current, e.action())  # the next, unrelated action
    assert e.u64(current + 0x80) == e.empty and e.refs(w) == WITNESS_BASELINE
    assert e.untouched(w)


@pytest.mark.parametrize("version", ["2.6.6.0", "2.7.3.0"])
def test_audit_confines_m_source_to_the_emulated_bodies(version):
    """dispatch_native_audit.action_value_evidence over every .pdata body: an
    action's m_source reaches only the copy, assignment and destruction bodies
    emulated above, no code reads or writes its pointer directly except inline
    construction storing the empty string, no bulk copy in a body that handles
    actions copies an action, and saves never carry queued or current actions."""
    audit = json.loads((SOURCE / f"dispatch-audit-{version}.json").read_text())
    reviewed = {label: audit["string_functions"][label]["rva"] for label in ("copy", "assign", "destroy")}
    members = audit["m_source_members"]
    assert {(row["label"], row["rva"]) for row in members} == set(reviewed.items())
    assert {(row["label"], row["role"]) for row in members} >= {("copy", "this"), ("assign", "this"), ("destroy", "this")}
    assert audit["action_value_bodies"] > 0 and audit["action_values"] >= audit["action_value_bodies"]
    assert audit["m_source_direct_accesses"] == [] and audit["m_source_empty_stores"] > 0
    # Every formed address of m_source is the this/argument of a member call.
    assert audit["m_source_aliases"] == [] and audit["m_source_addresses"] == sum(row["sites"] for row in members)
    assert sorted(entry.split("+")[0] for entry in audit["action_body_bulk_copies"]) == [
        "CGameSprite::ProcessEffectList", "CGameSprite::ProcessEffectList", "CGameSprite::QuickLoad",
        "CMessageInsertResponse::MarshalMessage", "CMessageInsertResponse::MarshalMessage",
        "CMessageInsertResponse::MarshalMessage"]
    assert audit["action_save_load_functions"] == [
        "CGameSprite::QuickLoad", "CMessageInsertResponse::MarshalMessage", "CMessageInsertResponse::UnmarshalMessage"]


@pytest.mark.parametrize("version", ["2.6.6.0", "2.7.3.0"])
def test_committed_audit_is_what_the_scanner_finds_in_the_pinned_build(version):
    """The confinement test reads committed evidence. This reruns the scanner
    over the pinned executable, when it is available, and requires exactly that
    evidence. It cannot show that the pattern-based scanner is complete
    (action-witness-evidence.md)."""
    sys.path.insert(0, str(SOURCE))
    import dispatch_native_audit
    from generate_decode_profiles import EXES
    _, path, digest, _ = next(entry for entry in EXES if entry[0] == version)
    if not path.is_file():
        pytest.skip("offline native proof requires the unbundled pinned executable")
    fresh = json.loads(json.dumps(dispatch_native_audit.audit(version, path, digest)))
    assert fresh == json.loads((SOURCE / f"dispatch-audit-{version}.json").read_text())
