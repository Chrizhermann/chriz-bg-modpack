"""Uninstalled, version-pinned CAIAction detour byte emitter.

Only emits bytes and a patch plan. Does not allocate executable memory, modify
any module/file, install hooks or claim Windows unwind registration. Tests run
the emitted bridges and actual engine instructions in an emulator.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct

import capstone
import pefile

PINS = {
    "fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580": "2.6.6.0",
    "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57": "2.7.3.0",
}
# Actual saved-register locations at the completed-copy epilogues. The copied
# instructions restore caller RBX and put destination RDI in return RAX.
COPY_TAIL = bytes.fromhex("488b5c2430488bc7")
DESTROY_ENTRY = bytes.fromhex("40534883ec20")


@dataclass(frozen=True)
class Site:
    version: str
    operation: str
    function: int
    body: bytes
    address: int
    original: bytes
    stack_mod16: int


def audited_sites(executable: Path, symbols: Path):
    raw = executable.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest not in PINS:
        raise ValueError("action hooks require an audited executable hash")
    pe = pefile.PE(data=raw)
    records = [(int(at, 16), name) for line in symbols.read_text().splitlines()
               for at, _, name in [line.partition("\t")] if at.startswith("0x")]
    addresses = sorted({address for address, _ in records})
    names = {}
    for address, name in records:
        names.setdefault(name, []).append(address)
    # The first overload is independently traced as the two-argument copy
    # constructor in both builds; retain its full pinned body below.
    definitions = [("copy", min(names["CAIAction::CAIAction"])),
                   ("assign", names["CAIAction::operator="][0]),
                   ("destroy", names["CAIAction::~CAIAction"][0])]
    sites = []
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    for operation, start in definitions:
        end = addresses[addresses.index(start) + 1]
        body = pe.get_data(start - pe.OPTIONAL_HEADER.ImageBase, end - start)
        original = DESTROY_ENTRY if operation == "destroy" else COPY_TAIL
        at = 0 if operation == "destroy" else body.find(original)
        if at < 0 or body[at:at+len(original)] != original or body.find(original, at+1) >= 0:
            raise ValueError(f"{operation}: ambiguous or altered audited boundary")
        instructions = list(md.disasm(original, start + at))
        assert sum(item.size for item in instructions) == len(original)
        assert all(not item.group(capstone.CS_GRP_JUMP) and not item.group(capstone.CS_GRP_CALL) for item in instructions)
        assert all(operand.type != capstone.CS_OP_MEM or operand.mem.base != capstone.x86.X86_REG_RIP
                   for item in instructions for operand in item.operands)
        sites.append(Site(PINS[digest], operation, start, body, start + at, original, 8 if operation == "destroy" else 0))
    return pe, sites


def absolute_jump(target):
    return bytes.fromhex("ff2500000000") + struct.pack("<Q", target)


def unwind_record(actions, chain=b"", prolog_size=0):
    """Windows x64 UNWIND_INFO, retaining caller-owned native chained info."""
    codes = b"".join(bytes([offset]) + operation for offset, operation in reversed(actions))
    count = len(codes) // 2
    assert len(codes) % 2 == 0 and count < 256 and prolog_size < 256
    return bytes([0x21 if chain else 1, prolog_size, count, 0]) + codes + (b"\0\0" if count % 2 else b"") + chain


def native_unwind_entry(pe, site):
    rva = site.function - pe.OPTIONAL_HEADER.ImageBase
    matches = [entry for entry in pe.DIRECTORY_ENTRY_EXCEPTION if entry.struct.BeginAddress == rva]
    if len(matches) != 1:
        raise ValueError("action function lacks one audited native unwind entry")
    entry = matches[0].struct
    return struct.pack("<III", entry.BeginAddress, entry.EndAddress, entry.UnwindData)


def emit(site: Site, *, image_base: int, stub: int, runtime: int, callback: int, observed: bytes):
    """Emit exact version-specific patch/bridge; refuse changed original body.

    `observed` is the actual loaded native function body. A host must establish
    module/page lifetime using the binder's read-only checks before using it.
    No native patch/write function is supplied by this prototype.
    """
    if observed != site.body:
        raise ValueError(f"{site.operation}: native function changed; action ABI audit required")
    if not runtime or not callback:
        raise ValueError("action bridge requires the actual compiled callback/runtime addresses")
    address = image_base + site.address - 0x140000000
    displacement = stub - (address + 5)
    if not -(1 << 31) <= displacement < (1 << 31):
        raise ValueError("action detour stub must be within signed rel32 range")
    # Save all general registers except RSP, then flags. Windows x64 callback
    # preserves XMM6-15; save the six volatile XMM registers explicitly.
    registers = [0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    code = bytearray()
    actions = []
    for register in registers:
        code += (b"\x41" if register >= 8 else b"") + bytes([0x50 + register % 8])
        # Volatile saves occupy stack but are not nonvolatile unwind restores.
        operation = (register << 4) if register in (3, 5, 6, 7, 12, 13, 14, 15) else 2
        actions.append((len(code), bytes([operation])))
    code += b"\x9c"
    actions.append((len(code), b"\x02"))
    reserve = 0x80 + site.stack_mod16
    code += b"\x48\x81\xec" + struct.pack("<I", reserve)
    actions.append((len(code), b"\x01" + struct.pack("<H", reserve // 8)))
    prolog_size = len(code)
    for xmm in range(6):
        code += bytes([0xF3, 0x0F, 0x7F, 0x44 + xmm * 8, 0x24, 0x20 + xmm * 16])
    saved = {register: reserve + 8 * (15 - index) for index, register in enumerate(registers)}
    code += b"\x48\xb9" + struct.pack("<Q", runtime)
    source_register = 1 if site.operation == "destroy" else 3
    code += b"\x48\x8b\x94\x24" + struct.pack("<I", saved[source_register])
    if site.operation != "destroy":
        code += b"\x4c\x8b\x84\x24" + struct.pack("<I", saved[7])
        code += b"\x41\xb9" + struct.pack("<I", int(site.operation == "copy"))
    code += b"\x48\xb8" + struct.pack("<Q", callback)
    call_offset = len(code)
    code += b"\xff\xd0"
    for xmm in range(6):
        code += bytes([0xF3, 0x0F, 0x6F, 0x44 + xmm * 8, 0x24, 0x20 + xmm * 16])
    unwind_region_end = len(code)
    remaining = [(0, operation) for _, operation in actions]
    tails = []
    at = len(code)
    code += b"\x48\x81\xc4" + struct.pack("<I", reserve)
    tails.append((at, len(code), list(remaining)))
    remaining.pop()
    at = len(code)
    code += b"\x9d"
    tails.append((at, len(code), list(remaining)))
    remaining.pop()
    for register in reversed(registers):
        at = len(code)
        code += (b"\x41" if register >= 8 else b"") + bytes([0x58 + register % 8])
        tails.append((at, len(code), list(remaining)))
        remaining.pop()
    restore_offset = len(code)
    code += site.original
    # This is a branch back INTO an active native frame, not a tail return.
    # An ff25 RIP-indirect jump is recognized by Windows as an epilogue and
    # bypasses the native-frame unwind operations. Use a mod=01 memory jump,
    # which is a body instruction under the documented x64 epilogue grammar.
    # These audited sites all have an allocated, callee-owned 32-byte call-home
    # area at RSP; no remaining native instruction reads its contents before
    # another call may overwrite it. Preserve every register and flags.
    target = address + len(site.original)
    code += b"\xc7\x04\x24" + struct.pack("<I", target & 0xFFFFFFFF)
    code += b"\xc7\x44\x24\x04" + struct.pack("<I", target >> 32)
    code += b"\xff\x64\x24\x00"
    return {"site": address, "patch": b"\xe9" + struct.pack("<i", displacement) + b"\x90" * (len(site.original) - 5),
            "stub": stub, "code": bytes(code), "callback": callback, "call_offset": call_offset,
            "restore_offset": restore_offset, "stack_reserve": reserve,
            "unwind_actions": actions, "unwind_prolog_size": prolog_size,
            "unwind_region_end": unwind_region_end, "unwind_tails": tails,
            "status": "uninstalled; Windows unwind registration and full lifecycle coverage still required"}


def unwind_segments(pe, site, plan):
    """Flatten audited native operations with each bridge instruction's state.

    Native SAVE_NONVOL uses the establisher frame, not the changing pop cursor.
    Blind CHAININFO after extra bridge allocation therefore restores the wrong
    native save slots. Adjust those offsets by the actual live bridge depth.
    These are inert records; no RtlAddFunctionTable registration occurs.
    """
    unwind_rva = struct.unpack("<III", native_unwind_entry(pe, site))[2]
    header = pe.get_data(unwind_rva, 4)
    if header[0] != 1 or header[3] != 0:
        raise ValueError("action unwind ABI requires audited handler-free frameless records")
    raw = pe.get_data(unwind_rva+4, header[2]*2)
    native = []
    cursor = 0
    while cursor < len(raw):
        offset, operation = raw[cursor:cursor+2]
        slots = 2 if operation & 15 == 4 else 1
        if operation & 15 not in (0, 2, 4):
            raise ValueError("unreviewed native action unwind operation")
        native.append((offset, raw[cursor+1:cursor+slots*2]))
        cursor += slots*2
    native.reverse()  # chronological list consumed by unwind_record
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    segments = []
    executable_size = len(plan["code"])
    for instruction in md.disasm(plan["code"][:executable_size], 0):
        offset = instruction.address
        if offset < plan["unwind_region_end"]:
            active = [(0, operation) for end, operation in plan["unwind_actions"] if end <= offset]
        elif offset < plan["restore_offset"]:
            matches = [actions for start, end, actions in plan["unwind_tails"] if start <= offset < end]
            if len(matches) != 1:
                raise ValueError("unknown bridge restoring stack state")
            active = matches[0]
        else:
            active = []
        depth = 0
        for _, operation in active:
            code = operation[0] & 15
            if code == 0: depth += 8
            elif code == 2: depth += (operation[0] >> 4)*8 + 8
            elif code == 1: depth += struct.unpack("<H", operation[1:])[0]*8
            else: raise ValueError("unreviewed bridge unwind operation")
        native_progress = offset - plan["restore_offset"] if site.operation == "destroy" else 0xFFFF
        merged = []
        for end, operation in native:
            if end > native_progress:
                continue
            if operation[0] & 15 == 4:
                operation = operation[:1] + struct.pack("<H", struct.unpack("<H", operation[1:])[0] + depth//8)
            merged.append((0, operation))
        merged.extend(active)
        segments.append((offset, offset+instruction.size, unwind_record(merged)))
    if not segments or segments[-1][1] != executable_size:
        raise ValueError("bridge unwind instruction coverage incomplete")
    return segments
