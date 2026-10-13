"""Execute pinned native V1 effect-list serialization in an offline emulator.

Only allocation, empty base construction and stack-cookie validation are
substituted. Selection/filtering/order/0x108-byte copies execute engine code.
No process/game function is launched, and no save is read or written.
"""
import hashlib
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RAX, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9, UC_X86_REG_RSP, UC_X86_REG_RIP
from unicorn import x86_const as X


def marshal(pe, names, records, *, permanent_only=False, skip_equipped=True, trampoline=None):
    # names is the exact pinned address->symbol table already audited by the
    # action-image fixture. No pattern from an unknown executable is accepted.
    address = next(a for a, n in names.items() if n == "CGameEffectList::Marshal")
    end = min(a for a in names if a > address)
    body = pe.get_data(address - pe.OPTIONAL_HEADER.ImageBase, end - address)
    boundary = bytes.fromhex("498bd1b902000000")  # audited mov rdx,r9; mov ecx,2
    if body.count(boundary) != 1:
        raise ValueError("ambiguous native V1 emitted-record boundary")
    before_copy = address + body.index(boundary)
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    base, image = pe.OPTIONAL_HEADER.ImageBase, pe.get_memory_mapped_image()
    uc.mem_map(base, (len(image) + 4095) & ~4095)
    uc.mem_write(base, image)
    stack, data = 0x20000000, 0x30000000
    uc.mem_map(stack, 0x10000)
    uc.mem_map(data, 0x20000)
    cave=0x150000000
    if trampoline:
        uc.mem_map(cave,0x10000);uc.mem_write(cave,trampoline)
    output, out_pointer = data + 0x10000, data + 0x80
    nodes, effects = data + 0x1000, data + 0x2000
    if len(records) > 32 or any(len(record) != 0x108 for record in records):
        raise ValueError("bounded probe accepts at most32 native base records")
    uc.mem_write(data + 8, struct.pack("<Q", nodes if records else 0))
    uc.mem_write(data + 0x18, struct.pack("<I", len(records)))
    for i, record in enumerate(records):
        node, effect = nodes + i * 0x20, effects + i * 0x200
        uc.mem_write(node, struct.pack("<QQQ", node + 0x20 if i + 1 < len(records) else 0, 0, effect))
        uc.mem_write(effect + 8, record)
    rsp, stop = stack + 0x8008, stack + 0xFFF0
    uc.mem_write(rsp, struct.pack("<Q", stop))
    uc.mem_write(rsp + 0x28, struct.pack("<I", int(skip_equipped)))
    registers=[getattr(X,"UC_X86_REG_"+name) for name in ["RAX","RBX","RCX","RDX","RBP","RSI","RDI","R8","R9","R10","R11","R12","R13","R14","R15","RSP"]]
    for index,register in enumerate(registers): uc.reg_write(register,0xCAFE0000+index*0x101)
    for register, value in [(UC_X86_REG_RCX, data), (UC_X86_REG_RDX, out_pointer),
                            (UC_X86_REG_R8, 1), (UC_X86_REG_R9, int(permanent_only)), (UC_X86_REG_RSP, rsp)]:
        uc.reg_write(register, value)
    emitted, allocations,points = [], [],[]
    def return_now():
        current = uc.reg_read(UC_X86_REG_RSP)
        destination = struct.unpack("<Q", uc.mem_read(current, 8))[0]
        uc.reg_write(UC_X86_REG_RSP, current + 8)
        uc.reg_write(UC_X86_REG_RIP, destination)
    def event(_, pc, size, unused):
        if trampoline and cave<=pc<cave+len(trampoline):
            points.append(dict(offset=pc-cave,registers=[uc.reg_read(register) for register in registers],stack=bytes(uc.mem_read(stack,0x10000))))
        if pc == before_copy:
            source = uc.reg_read(UC_X86_REG_RAX)
            destination = uc.reg_read(UC_X86_REG_R9)
            emitted.append({"effect": source - 8, "ordinal": (destination-output)//0x108,
                            "bytes": bytes(uc.mem_read(source, 0x108)),
                            "wire_sha256": hashlib.sha256(uc.mem_read(source, 0x108)).hexdigest()})
            return
        name = names.get(pc, "")
        if name == "operator_new[]":
            allocations.append(uc.reg_read(UC_X86_REG_RCX))
            uc.reg_write(UC_X86_REG_RAX, output)
            return_now()
        elif name == "CGameEffectBase::CGameEffectBase":
            uc.mem_write(uc.reg_read(UC_X86_REG_RCX), bytes(0x108))
            return_now()
        elif name == "__security_check_cookie":
            return_now()
    uc.hook_add(UC_HOOK_CODE, event)
    uc.emu_start(cave if trampoline else address, stop, count=30000)
    length = uc.reg_read(UC_X86_REG_RAX)
    pointer = struct.unpack("<Q", uc.mem_read(out_pointer, 8))[0]
    if uc.reg_read(UC_X86_REG_RIP) != stop or uc.reg_read(UC_X86_REG_RSP) != rsp + 8:
        raise AssertionError("native serializer did not return normally")
    for i in (1,4,5,6,11,12,13,14):
        if uc.reg_read(registers[i])!=0xCAFE0000+i*0x101: raise AssertionError("Marshal corrupted a nonvolatile register")
    return {"length": length, "pointer": pointer, "buffer": bytes(uc.mem_read(output, length)),
            "emitted": emitted, "allocations": allocations, "boundary": before_copy,
            "source_effect_base": effects, "body_sha256": hashlib.sha256(body).hexdigest(),"points":points}
