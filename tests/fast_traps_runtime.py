"""Execute the shipping Fast Traps Lua against bounded byte arrays; no game process access."""
from __future__ import annotations

from pathlib import Path
import struct

from lupa import lua51, lua52, luajit21

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "chriz-bg-modpack/fast-traps/m_czft.lua"
STUBS = Path(__file__).with_name("fast_traps_stubs.lua")
PATTERN = bytes.fromhex(
    "448B81A4030000B81F85EB51448B4948488BF141F7E0418BC9C1EA056BC264"
    "442BC0B81F85EB5141F7E1C1EA056BC2642BC8443BC1"
)
# Independent excerpts from the 2.7.3.0 native function, not parsed from mod code.
CHECKS = {
    0: "405556488DAC2418FFFFFF4881ECE8010000",
    0x58: "0F859D1D0000FF864C4E0000",
    0x64: "B8201100008B96A44E0000B9C81D000085D20F44C1F704302F0800800F85751D0000",
    0x11C: "0F84E6010000",
    0x308: "0FB68E293A000083E9010F842F14000083E9010F840E0A0000",
    0xF2C: "3A05",
    0xF32: "0F841D010000",
    0x16FB: "4D85ED0F85FCF7FFFF",
    0x1DFB: "488B8DC00000004833CC",
}
BUILDS = {
    "bgee": (0x6A18D6DC, 0x3524000, 0x38CF00),
    "bg2ee": (0x6A18D73D, 0x3532000, 0x38CF00),
    "iwdee": (0x6A18D7E9, 0x3563000, 0x38CF30),
}
APIS = (
    "EEex_GameState_AddInitializedListener", "EEex_GetImageBase", "EEex_ReadLString",
    "EEex_Read8", "EEex_Read16", "EEex_Read32", "EEex_Write8",
    "EEex_JITNear", "EEex_JITAt", "EEex_DisableCodeProtection", "EEex_EnableCodeProtection",
)
SITES = (0xF2C, 0x11C, 0x58)  # main scheduling gate must be last
FN = 0x1800
SECTION = 0x188


def fixture(game: str = "bg2ee") -> bytearray:
    """Small synthetic PE mapping. Only bytes read by the mod are populated."""
    data = bytearray(0x5000)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    stamp, size, _ = BUILDS[game]
    struct.pack_into("<HHI", data, 0x84, 0x8664, 1, stamp)
    struct.pack_into("<H", data, 0x94, 0xF0)
    struct.pack_into("<H", data, 0x98, 0x20B)
    struct.pack_into("<I", data, 0xD0, size)
    struct.pack_into("<II", data, SECTION + 8, 0x3000, 0x1000)
    struct.pack_into("<I", data, SECTION + 36, 0x60000020)
    for offset, value in CHECKS.items():
        data[FN + offset:FN + offset + len(value) // 2] = bytes.fromhex(value)
    data[FN + 0x23:FN + 0x23 + len(PATTERN)] = PATTERN
    struct.pack_into("<i", data, FN + 0xF2E, 0x4100 - (FN + 0xF32))
    data[0x4100] = 33
    return data


class Runtime:
    def __init__(self, data=None, *, runtime: str = "lua52", base: int = 0x140000000,
                 failure: str = "none", fail_at: int = 0, fn: int = FN):
        self.base, self.fn = base, fn
        self.original = bytes(data if data is not None else fixture())
        runtimes = {"lua51": lua51, "lua52": lua52, "luajit21": luajit21}
        self.lua = runtimes[runtime].LuaRuntime(encoding=None)
        self.lua.globals()[b"image"] = self.original
        self.lua.globals()[b"base"] = base
        self.lua.globals()[b"failure"] = failure.encode()
        self.lua.globals()[b"fail_at"] = fail_at
        self.lua.execute(STUBS.read_bytes())

    def run(self, extra: bytes = b"", initialize: bool = True) -> "Runtime":
        self.lua.execute(extra)
        self.lua.execute(SOURCE.read_bytes(), name=b"@M_CZFT.lua")
        if initialize:
            self.lua.execute(b"if Meter.listener then Meter.listener() end")
        return self

    def eval(self, expression: str):
        return self.lua.eval(expression.encode())

    @property
    def state(self):
        return self.lua.globals()[b"CZFastTraps"]

    @property
    def meter(self):
        return self.lua.globals()[b"Meter"]

    def image_after(self) -> bytes:
        result = bytearray(self.original)
        for address, value in self.lua.globals()[b"edits"].items():
            result[address - self.base] = value
        return bytes(result)

    def assert_active(self) -> None:
        assert self.state[b"installed"] is True, self.state[b"status"]
        assert self.state[b"periodTicks"] == 15
        assert self.meter[b"near"] == self.meter[b"jit"] == 3
        assert self.meter[b"disable"] == self.meter[b"enable"] == 1
        assert len(self.meter[b"logs"]) == 1
        expected = bytearray(self.original)
        for i, offset in enumerate(SITES, 1):
            at = self.base + self.fn + offset
            assert self.meter[b"sites"][i] == at
            target = self.meter[b"targets"][i]
            expected[self.fn + offset:self.fn + offset + 6] = (
                b"\xE9" + struct.pack("<i", target - at - 5) + b"\x90"
            )
        assert self.image_after() == expected  # only the three six-byte sites

    def assert_inactive(self, reason: str) -> None:
        assert not self.state[b"installed"]
        assert reason.encode() in self.state[b"status"], self.state[b"status"]
        assert len(self.meter[b"logs"]) == 1
        assert self.meter[b"disable"] == self.meter[b"enable"]
        assert self.image_after() == self.original
