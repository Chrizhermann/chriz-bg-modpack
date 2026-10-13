"""Concrete Windows registration of emitted action-bridge unwind tables.

Does not allocate/write code, patch engine bytes, or invoke a game function.
The host owns a private allocation containing the exact returned bundle and
must retain it until hooks are removed and no thread can be inside the bridge.
"""
from dataclasses import dataclass
import ctypes
import os
import struct


@dataclass(frozen=True)
class Bundle:
    base: int
    payload: bytes
    table_offset: int
    count: int
    ranges: tuple


def bundle(base, entries):
    """Package (plan, per-instruction unwind segments) in one private region.

    Full bridge instructions and UNWIND_INFO are emitted by action_detours.py;
    here RVAs use the bundle allocation as their base, not the native module.
    All inherited native unwind operations are already flattened by the emitter.
    """
    if not base or not entries:
        raise ValueError("unwind bundle needs a base and action plans")
    ranges, code = [], bytearray()
    last = 0
    for plan, segments in sorted(entries, key=lambda item: item[0]["stub"]):
        offset = plan["stub"] - base
        end = offset + len(plan["code"])
        if offset < last or offset < 0 or end > 0x100000:
            raise ValueError("overlapping/out-of-bounds action bridge allocation")
        code.extend(bytes(end - len(code)))
        code[offset:end] = plan["code"]
        last = end
        previous = 0
        for start, stop, info in segments:
            if start != previous or stop <= start or stop > len(plan["code"]):
                raise ValueError("incomplete or overlapping instruction unwind ranges")
            if len(info) < 4 or info[0] != 1 or info[1] != 0 or info[3] != 0:
                raise ValueError("only flattened handler-free action unwind info is supported")
            expected = 4 + ((info[2] + 1) & ~1) * 2
            if len(info) != expected:
                raise ValueError("truncated action unwind info")
            ranges.append((offset + start, offset + stop, bytes(info)))
            previous = stop
        if previous != len(plan["code"]):
            raise ValueError("action unwind ranges do not cover the bridge")
    code.extend(bytes((-len(code)) % 4))
    records = []
    for start, stop, info in ranges:
        records.append((start, stop, len(code)))
        code.extend(info)
    table_offset = len(code)
    for record in records:
        code.extend(struct.pack("<III", *record))
    return Bundle(base, bytes(code), table_offset, len(records), tuple(records))


class MemoryInfo(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("allocation", ctypes.c_void_p),
                ("allocation_protect", ctypes.c_uint32), ("partition", ctypes.c_uint16),
                ("region", ctypes.c_size_t), ("state", ctypes.c_uint32),
                ("protect", ctypes.c_uint32), ("type", ctypes.c_uint32)]


class RegisteredUnwind:
    # Retain the object until explicit deregistration; accidental Python GC must
    # not invalidate the registration's host bookkeeping. Host still owns pages.
    active = {}

    def __init__(self, package):
        if os.name != "nt" or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise OSError("action unwind registration requires Windows x64")
        if (not package.base or not package.count or package.count != len(package.ranges)
                or package.table_offset < 0 or package.table_offset % 4
                or package.table_offset + package.count * 12 != len(package.payload)
                or len(package.payload) > 0x100000):
            raise ValueError("malformed action function table bounds")
        previous = 0
        for i, record in enumerate(package.ranges):
            start, stop, info = record
            if (start < previous or stop <= start or stop > package.table_offset
                    or info < stop or info % 4 or info + 4 > package.table_offset
                    or struct.unpack_from("<III", package.payload, package.table_offset + i * 12) != record):
                raise ValueError("malformed action instruction/table record")
            header = package.payload[info:info + 4]
            if (header[0] != 1 or header[1] != 0 or header[3] != 0
                    or info + 4 + ((header[2] + 1) & ~1) * 2 > package.table_offset):
                raise ValueError("malformed action unwind record")
            previous = stop
        self.package, self.registered = package, False
        api = self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.VirtualQuery.argtypes = [ctypes.c_void_p, ctypes.POINTER(MemoryInfo), ctypes.c_size_t]
        api.VirtualQuery.restype = ctypes.c_size_t
        api.RtlAddFunctionTable.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint64]
        api.RtlAddFunctionTable.restype = ctypes.c_ubyte
        api.RtlDeleteFunctionTable.argtypes = [ctypes.c_void_p]
        api.RtlDeleteFunctionTable.restype = ctypes.c_ubyte
        api.RtlLookupFunctionEntry.argtypes = [ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64), ctypes.c_void_p]
        api.RtlLookupFunctionEntry.restype = ctypes.c_void_p
        cursor, end = package.base, package.base + len(package.payload)
        while cursor < end:
            info = MemoryInfo()
            if not api.VirtualQuery(cursor, ctypes.byref(info), ctypes.sizeof(info)):
                raise ValueError("unmapped action bundle")
            readable = info.protect & 0xFF in (2, 4, 8, 0x20, 0x40, 0x80)
            if (info.allocation != package.base or info.state != 0x1000 or info.type != 0x20000
                    or not readable or info.protect & 0x100 or info.region <= 0):
                raise ValueError("action bundle must remain one readable committed private allocation")
            cursor = info.base + info.region
        if ctypes.string_at(package.base, len(package.payload)) != package.payload:
            raise ValueError("loaded action bundle differs from audited emitted bytes")
        if package.base in self.active:
            raise ValueError("action bundle already registered")
        for start, stop, _ in package.ranges:
            image = ctypes.c_uint64()
            for pc in (package.base + start, package.base + stop - 1):
                if api.RtlLookupFunctionEntry(pc, ctypes.byref(image), None):
                    raise ValueError("action bridge conflicts with an existing unwind registration")
        self.table = package.base + package.table_offset
        if not api.RtlAddFunctionTable(self.table, package.count, package.base):
            raise OSError("RtlAddFunctionTable refused the action bridge records")
        self.registered = True
        self.active[package.base] = self

    def close(self):
        """Only after the host proves no hook/call/stack can reference the bundle."""
        if self.registered:
            if not self.api.RtlDeleteFunctionTable(self.table):
                raise OSError("RtlDeleteFunctionTable failed; retain the allocation")
            self.registered = False
            del self.active[self.package.base]
