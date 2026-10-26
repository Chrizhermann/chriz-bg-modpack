"""Windows x64 UNWIND_INFO encoding shared by emitted bridges; emits bytes only."""


def unwind_record(actions, chain=b"", prolog_size=0):
    """Windows x64 UNWIND_INFO, retaining caller-owned native chained info."""
    codes = b"".join(bytes([offset]) + operation for offset, operation in reversed(actions))
    count = len(codes) // 2
    assert len(codes) % 2 == 0 and count < 256 and prolog_size < 256
    return bytes([0x21 if chain else 1, prolog_size, count, 0]) + codes + (b"\0\0" if count % 2 else b"") + chain
