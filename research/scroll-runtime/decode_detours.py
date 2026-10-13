"""Exact independent decoder detour plans. Emits bytes, never installs them.

The native seven-byte prefix only copies RSP to volatile R11 and saves RBX in
caller home space; it does not change RSP or RBX. The continuation executes the
remaining original prologue. A compiler-generated wrapper calls this trampoline
and observes the returned effect against its original raw-record argument.
"""
import struct

PREFIX = bytes.fromhex("4c8bdc49895b10")


def absolute_jump(target):
    if not 0 < target < (1 << 64):
        raise ValueError("invalid decoder bridge address")
    return b"\xff\x25\0\0\0\0" + struct.pack("<Q", target)


def plan_decoder(entry, near_relay, wrapper, observed_prefix):
    if observed_prefix != PREFIX:
        raise ValueError("native decoder prologue differs from audited seven-byte prefix")
    delta = near_relay - (entry+5)
    if not -(1 << 31) <= delta < (1 << 31):
        raise ValueError("decoder relay lies outside rel32 range")
    # UWOP_SAVE_NONVOL RBX at entry-RSP+10h, executed at prologue offset7.
    # The absolute jump at offset7 can be treated as a leaf epilogue: RSP and
    # all nonvolatiles are still unchanged there. No native frame is skipped.
    unwind = bytes([1, 7, 2, 0, 7, 0x34, 2, 0])
    return dict(address=entry, original=PREFIX,
                patch=b"\xe9"+struct.pack("<i",delta)+b"\x90\x90",
                relay=absolute_jump(wrapper), trampoline=PREFIX+absolute_jump(entry+7), unwind=unwind)


def plan_unmarshal(entry, previous, wrapper, observed_jump):
    if len(observed_jump) != 14:
        raise ValueError("Unmarshal chain needs the certified fourteen-byte entry snapshot")
    if observed_jump[:1] == b"\xe9":
        target = entry+5+struct.unpack_from("<i",observed_jump,1)[0]
    elif observed_jump[:6] == b"\xff\x25\0\0\0\0":
        target = struct.unpack_from("<Q",observed_jump,6)[0]
    else:
        raise ValueError("unsupported previous Unmarshal jump")
    if target != previous or previous == wrapper:
        raise ValueError("Unmarshal chain target differs or would recurse")
    return dict(address=entry, original=observed_jump, patch=absolute_jump(wrapper), previous=previous)
