"""Execute the shipping Unpaused Inventory Lua against bounded byte arrays; no game process access."""
from __future__ import annotations

from pathlib import Path
import struct

from lupa import lua52, luajit21

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "chriz-bg-modpack/unpaused-inventory/m_czinvu.lua"
ALWAYS_CFG = ROOT / "chriz-bg-modpack/unpaused-inventory/czinvu_always.lua"
COMBAT_CFG = ROOT / "chriz-bg-modpack/unpaused-inventory/czinvu_combat.lua"
STUBS = Path(__file__).with_name("unpaused_inventory_stubs.lua")

PAT_ACT = bytes.fromhex("488B90101100000FB682BC00000089836C07000085C07536")
PAT_TOG = bytes.fromhex("33FF39BBA40B00000F8531060000440FB683BC000000")
PAT_ASY = bytes.fromhex("8B83D806000085C00F88B40100000F85A6010000")

BUILDS = {
    "bgee": (0x6A18D6DC, 0x3524000),
    "bg2ee": (0x6A18D73D, 0x3532000),
    "iwdee": (0x6A18D7E9, 0x3563000),
    "bg2ee_266": (0x609437B3, 0x3530000),
}

APIS = (
    "EEex_GameState_AddInitializedListener", "EEex_GameState_AddDestroyedListener",
    "EEex_GetImageBase", "EEex_ReadLString",
    "EEex_Read8", "EEex_Read16", "EEex_Read32", "EEex_WriteU8",
    "EEex_JITNear", "EEex_JITAt",
    "EEex_DisableCodeProtection", "EEex_EnableCodeProtection",
    "EEex_GenLuaCall", "EEex_FlattenTable", "EEex_LuaCallReturnType",
    "EEex_Trigger_ParseConditionalString",
    "EEex_Sprite_GetNumCharacters", "EEex_Sprite_GetInPortrait", "EEex_Sprite_GetState",
)

SECTION = 0x188
FN_ACT = 0x1200
FN_TOG = 0x2000
FN_STARTTIME = 0x2800
FN_ASY = 0x3000
P_CHITIN = 0x5000
P_OTHER = 0x5018

SITES = (
    (FN_ACT + 0x30, 15),
    (FN_TOG + 0x55, 8),
    (FN_ASY + 0x2D, 8),
)


def _rel32(next_rva: int, target_rva: int) -> bytes:
    return struct.pack("<i", target_rva - next_rva)


def fixture(game: str = "bg2ee") -> bytearray:
    """Small synthetic PE mapping with all three hook targets and guards populated."""
    data = bytearray(0x6000)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    stamp, size = BUILDS[game]
    struct.pack_into("<HHI", data, 0x84, 0x8664, 1, stamp)
    struct.pack_into("<H", data, 0x94, 0xF0)
    struct.pack_into("<H", data, 0x98, 0x20B)
    struct.pack_into("<I", data, 0xD0, size)
    # Single executable section covering RVA 0x1000 .. 0x6000 (size 0x5000)
    struct.pack_into("<II", data, SECTION + 8, 0x5000, 0x1000)
    struct.pack_into("<I", data, SECTION + 36, 0x60000020)

    # 1. CScreenInventory::EngineActivated (FN_ACT)
    p = FN_ACT
    b = bytes.fromhex("48895C2408574883EC30488BD9")
    data[p:p + len(b)] = b
    data[p + 0x0D] = 0xE8
    data[p + 0x12:p + 0x15] = b"\x48\x8B\x05"
    data[p + 0x15:p + 0x19] = _rel32(p + 0x19, P_OTHER)
    b19 = bytes.fromhex("80B8C9020000007555488B05")
    data[p + 0x19:p + 0x19 + len(b19)] = b19
    data[p + 0x25:p + 0x29] = _rel32(p + 0x29, P_CHITIN)
    data[p + 0x29:p + 0x29 + len(PAT_ACT)] = PAT_ACT
    data[p + 0x41:p + 0x44] = b"\x48\x8B\x0D"
    data[p + 0x44:p + 0x48] = _rel32(p + 0x48, P_CHITIN)
    b48 = bytes.fromhex("4533C98844242841B00133D288442420488B8910110000E8")
    data[p + 0x48:p + 0x48 + len(b48)] = b48
    data[p + 0x60:p + 0x64] = _rel32(p + 0x64, FN_TOG)

    # 2. CScreenWorld::TogglePauseGame (FN_TOG)
    ht = FN_TOG + 0x47
    data[ht:ht + len(PAT_TOG)] = PAT_TOG
    data[ht + 0x0E:ht + 0x19] = bytes.fromhex("440FB683BC0000004C8B0D")
    data[ht + 0x19:ht + 0x1D] = _rel32(ht + 0x1D, P_OTHER)
    data[ht + 0x1D:ht + 0x21] = bytes.fromhex("4180F801")
    data[FN_TOG + 0x448:FN_TOG + 0x450] = bytes.fromhex("4881C1A03F0000E8")
    data[FN_TOG + 0x450:FN_TOG + 0x454] = _rel32(FN_TOG + 0x454, FN_STARTTIME)

    # 3. CTimerWorld::StartTime (FN_STARTTIME)
    data[FN_STARTTIME:FN_STARTTIME + 7] = bytes.fromhex("C6410401488B15")

    # 4. CScreenInventory::TimerAsynchronousUpdate (FN_ASY)
    hs = FN_ASY + 0x2D
    data[hs:hs + len(PAT_ASY)] = PAT_ASY
    data[hs + 0x14:hs + 0x17] = bytes.fromhex("488B05")
    data[hs + 0x17:hs + 0x1B] = _rel32(hs + 0x1B, P_CHITIN)
    return data


class Runtime:
    def __init__(self, data=None, *, runtime: str = "lua52", base: int = 0x140000000,
                 failure: str = "none", fail_at: int = 0,
                 act_rva: int = FN_ACT, tog_rva: int = FN_TOG, asy_rva: int = FN_ASY,
                 p_chitin_rva: int = P_CHITIN):
        self.base = base
        self.act_rva = act_rva
        self.tog_rva = tog_rva
        self.asy_rva = asy_rva
        self.p_chitin_rva = p_chitin_rva
        self.original = bytes(data if data is not None else fixture())
        runtimes = {"lua52": lua52, "luajit21": luajit21}
        self.lua = runtimes[runtime].LuaRuntime(encoding=None)
        self.lua.globals()[b"image"] = self.original
        self.lua.globals()[b"base"] = base
        self.lua.globals()[b"failure"] = failure.encode()
        self.lua.globals()[b"fail_at"] = fail_at
        self.lua.execute(STUBS.read_bytes())

    def run(self, extra: bytes = b"", initialize: bool = True) -> "Runtime":
        self.lua.execute(extra)
        self.lua.execute(SOURCE.read_bytes(), name=b"@M_CZINVU.lua")
        if initialize:
            self.lua.execute(b"if Meter.listener then Meter.listener() end")
        return self

    def eval(self, expression: str):
        return self.lua.eval(expression.encode())

    @property
    def state(self):
        return self.lua.globals()[b"CZUnpausedInventory"]

    @property
    def meter(self):
        return self.lua.globals()[b"Meter"]

    def image_after(self) -> bytes:
        result = bytearray(self.original)
        for address, value in self.lua.globals()[b"edits"].items():
            result[address - self.base] = value
        return bytes(result)

    def write_bytes(self, address: int, payload: bytes) -> None:
        fn = self.lua.eval(b"function(a, v) EEex_WriteU8(a, v) end")
        for i, byte in enumerate(payload):
            fn(address + i, byte)

    def assert_active(self) -> None:
        assert self.state[b"installed"] is True, self.state[b"status"]
        assert self.state[b"pChitin"] == self.base + self.p_chitin_rva
        assert self.meter[b"near"] == 4
        assert self.meter[b"jit"] == 3
        assert self.meter[b"disable"] == self.meter[b"enable"] == 1
        assert len(self.meter[b"logs"]) == 1
        expected = bytearray(self.original)
        sites = (
            (self.act_rva + 0x30, 15),
            (self.tog_rva + 0x55, 8),
            (self.asy_rva + 0x2D, 8),
        )
        for i, (rva, size) in enumerate(sites, 1):
            at = self.base + rva
            assert self.meter[b"sites"][i] == at
            target = self.meter[b"targets"][i + 1]  # target 1 is queryCallee
            patch = b"\xE9" + struct.pack("<i", target - at - 5) + b"\x90" * (size - 5)
            expected[rva:rva + size] = patch
        assert self.image_after() == expected

    def assert_inactive(self, reason: str) -> None:
        assert not self.state[b"installed"]
        assert reason.encode() in self.state[b"status"], self.state[b"status"]
        assert len(self.meter[b"logs"]) == 1
        assert self.meter[b"disable"] == self.meter[b"enable"]
        assert self.image_after() == self.original
