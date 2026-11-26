"""Execute the shipping BG1 Early-Party XP Lua against bounded byte arrays; no game process access."""
from __future__ import annotations

from pathlib import Path
import struct

from lupa import lua51, lua52, luajit21

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "chriz-bg-modpack/bg1-early-party-xp/m_czxpbg.lua"
STUBS = Path(__file__).with_name("bg1_early_party_xp_stubs.lua")

PATTERN = bytes.fromhex("8BCB0FAFC8B81F85EB51F7E9C1FA058BC2C1E81F03D003DA440FB79630660000")
CHECKS = {
    0x00: "405355564154415641574881EC8800",
    0x148: "BA0200000066894C244C448BC3488BCE44897C2444E8",
    0x20D: "6685ED7E0D418D470166FFCD89442444EB0544897C24444C8D4C243048C7442430FFFFFFFF41B8",
}
BUILDS = {
    "bgee": (0x6A18D6DC, 0x3524000, 0x26DB60),
    "bg2ee": (0x6A18D73D, 0x3532000, 0x26DB60),
    "bg2ee_266": (0x609437B3, 0x3530000, 0x26D900),
}
APIS = (
    "EEex_GameState_AddInitializedListener", "EEex_GameState_AddDestroyedListener",
    "EEex_GetImageBase", "EEex_ReadLString",
    "EEex_Read8", "EEex_Read16", "EEex_Read32", "EEex_WriteU8",
    "EEex_JITNear", "EEex_JITAt", "EEex_Malloc",
    "EEex_DisableCodeProtection", "EEex_EnableCodeProtection",
    "EEex_GenLuaCall", "EEex_FlattenTable", "EEex_LuaCallReturnType",
    "EEex_GameState_GetGlobalInt", "EEex_Area_GetVisible",
    "EEex_Sprite_GetNumCharacters", "EEex_Sprite_GetInPortrait", "EEex_Sprite_GetState",
    "EEex_Resource_Load2DA", "EEex_GetUDAux",
)
SITES = ((0x152, 6), (0x224, 5))
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
    data[FN + 0x54:FN + 0x54 + len(PATTERN)] = PATTERN
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
        self.lua.execute(SOURCE.read_bytes(), name=b"@M_CZXPBG.lua")
        if initialize:
            self.lua.execute(b"if Meter.listener then Meter.listener() end")
        return self

    def eval(self, expression: str):
        return self.lua.eval(expression.encode())

    @property
    def state(self):
        return self.lua.globals()[b"CZBG1EarlyPartyXP"]

    @property
    def meter(self):
        return self.lua.globals()[b"Meter"]

    def read_plan_buffer(self) -> tuple[int, list[int]]:
        buf = self.state[b"planBuffer"]
        assert isinstance(buf, int) and buf > 0
        mem = self.lua.globals()[b"malloc_mem"]

        def u32(addr: int) -> int:
            return sum((mem[addr + i] or 0) << (8 * i) for i in range(4))

        return u32(buf), [u32(buf + 4 + slot * 4) for slot in range(16)]

    def image_after(self) -> bytes:
        result = bytearray(self.original)
        for address, value in self.lua.globals()[b"edits"].items():
            result[address - self.base] = value
        return bytes(result)

    def assert_active(self) -> None:
        assert self.state[b"installed"] is True, self.state[b"status"]
        assert self.meter[b"near"] == 3
        assert self.meter[b"jit"] == 2
        assert self.meter[b"disable"] == self.meter[b"enable"] == 1
        assert len(self.meter[b"logs"]) == 1
        expected = bytearray(self.original)
        for i, (offset, size) in enumerate(SITES, 1):
            at = self.base + self.fn + offset
            assert self.meter[b"sites"][i] == at
            target = self.meter[b"targets"][i + 1]  # target 1 is planCallee
            patch = b"\xE9" + struct.pack("<i", target - at - 5) + (b"\x90" if size == 6 else b"")
            expected[self.fn + offset:self.fn + offset + size] = patch
        assert self.image_after() == expected

    def assert_inactive(self, reason: str) -> None:
        assert not self.state[b"installed"]
        assert reason.encode() in self.state[b"status"], self.state[b"status"]
        assert len(self.meter[b"logs"]) == 1
        assert self.meter[b"disable"] == self.meter[b"enable"]
        assert self.image_after() == self.original
