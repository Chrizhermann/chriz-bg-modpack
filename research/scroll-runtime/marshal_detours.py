"""Audited Marshal entry trampoline; no game writes or loading."""
import struct

PREFIX=bytes.fromhex("405356574154415541564881ec88010000")
# Six native pushes and the native 0x188 allocation; no language-handler RVA
# from the remaining native function is copied to this partial prologue.
UNWIND=bytes.fromhex("01110800110131000ae008d006c0047003600230")


def plan(entry,relay,wrapper,observed):
    if observed!=PREFIX: raise ValueError("native Marshal entry differs from audited prologue")
    delta=relay-entry-5
    if not -(1<<31)<=delta<(1<<31): raise ValueError("Marshal relay outside rel32 reach")
    target=entry+len(PREFIX)
    # Return INTO active frame: FF25 would be mistaken for a Windows epilogue.
    # Native prologue has allocated call-home space; preserve GPRs and flags.
    resume=b"\xc7\x04\x24"+struct.pack("<I",target&0xffffffff)
    resume+=b"\xc7\x44\x24\x04"+struct.pack("<I",target>>32)+b"\xff\x64\x24\x00"
    return dict(patch=b"\xe9"+struct.pack("<i",delta)+b"\x90"*(len(PREFIX)-5),
                relay=b"\xff\x25"+bytes(4)+struct.pack("<Q",wrapper),
                trampoline=PREFIX+resume,unwind=UNWIND)
