"""Seven-byte existing EEex callback entry trampolines; emit only."""
import struct

COPY=bytes.fromhex('4c8bdc49895310')
DESTROY=bytes.fromhex('4c8bdc49894b08')


def plan(entry,relay,callback,prefix):
    if prefix not in (COPY,DESTROY):raise ValueError('unreviewed EEex lifecycle prologue')
    delta=relay-entry-5
    if not -(1<<31)<=delta<(1<<31):raise ValueError('lifecycle relay outside rel32 range')
    jump=lambda address:b'\xff\x25'+bytes(4)+struct.pack('<Q',address)
    # RSP/nonvolatiles are unchanged. Only volatile RCX/RDX is written to
    # caller home space before the rest of the original native prologue.
    return dict(patch=b'\xe9'+struct.pack('<i',delta)+b'\x90\x90',relay=jump(callback),
        trampoline=prefix+jump(entry+7),unwind=bytes([1,7,0,0]))
