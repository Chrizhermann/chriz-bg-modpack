"""Execute the shipping Scroll Learn Fix Lua against bounded byte arrays; no game process access."""
from __future__ import annotations

from pathlib import Path
import struct

from lupa import lua51, lua52, luajit21

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "chriz-bg-modpack/scroll-learn/m_czsl.lua"
STUBS = Path(__file__).with_name("scroll_learn_stubs.lua")

PATTERNS = {
    "LearnSpell": bytes.fromhex("410FB78E9E0700000FBFE8B800400000663BC8743B"),
    "GetKitMask": bytes.fromhex(
        "4883EC280FB7819E0700000FB7919C070000C1E2100BD0F7C2FFBFFFFF0F95C10FBAE20E0F92C084C87476"
    ),
    "CanWriteSpellScroll": bytes.fromhex("817A1093000000"),
}

LEARN_CHECKS = {
    0x15: "488B05",
    0x1C: "0FB7D1488B8890100000E8",
    0x2B: "488BCF0FB6D8E8",
    0x36: "3AD88B442460750983C00F89442460EB0D83E80F89442460EB048B4424603BF0",
}
GETSCHOOL_CHECKS = {
    0x00: "48895C2408574883EC20488BD9488D15",
    0x44: "488B40680FB67825488B5C2430400FB6C74883C4205F",
}
GETKITMASK_CHECKS = {
    0x98: "8B4424304883C428C38BC24883C428C3",
}
CANWRITE_CHECKS = {
    0x17: "4881C1504B0000",
    0x26: "E8",
}
ISUSABLE_CHECKS = {
    0x24: "0FB6560B",
}

BUILDS = {
    "bgee": (0x6A18D6DC, 0x3524000, 0x1B7BFB, 0x39CF10, 0x24F440),
    "bg2ee": (0x6A18D73D, 0x3532000, 0x1B7BFB, 0x39CF10, 0x24F440),
    "iwdee": (0x6A18D7E9, 0x3563000, 0x1B7C7B, 0x39CF40, 0x24F4C0),
}
APIS = (
    "EEex_GameState_AddInitializedListener", "EEex_GetImageBase", "EEex_ReadLString",
    "EEex_Read8", "EEex_Read16", "EEex_Read32", "EEex_WriteU8",
    "EEex_JITNear", "EEex_JITAt", "EEex_DisableCodeProtection", "EEex_EnableCodeProtection",
)

SECTION = 0x188
LEARN = 0x1800
GETSCHOOL = 0x2000
GETKITMASK = 0x2400
CANWRITE = 0x2800
ISUSABLE = 0x2C00


def fixture(game: str = "bg2ee") -> bytearray:
    """Small synthetic PE mapping. Only bytes read by the mod are populated."""
    data = bytearray(0x5000)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    stamp, size, _, _, _ = BUILDS[game]
    struct.pack_into("<HHI", data, 0x84, 0x8664, 1, stamp)
    struct.pack_into("<H", data, 0x94, 0xF0)
    struct.pack_into("<H", data, 0x98, 0x20B)
    struct.pack_into("<I", data, 0xD0, size)
    struct.pack_into("<II", data, SECTION + 8, 0x3000, 0x1000)
    struct.pack_into("<I", data, SECTION + 36, 0x60000020)

    data[LEARN:LEARN + len(PATTERNS["LearnSpell"])] = PATTERNS["LearnSpell"]
    for offset, hex_bytes in LEARN_CHECKS.items():
        b = bytes.fromhex(hex_bytes)
        data[LEARN + offset:LEARN + offset + len(b)] = b
    struct.pack_into("<i", data, LEARN + 0x32, GETSCHOOL - (LEARN + 0x36))

    for offset, hex_bytes in GETSCHOOL_CHECKS.items():
        b = bytes.fromhex(hex_bytes)
        data[GETSCHOOL + offset:GETSCHOOL + offset + len(b)] = b

    data[GETKITMASK:GETKITMASK + len(PATTERNS["GetKitMask"])] = PATTERNS["GetKitMask"]
    for offset, hex_bytes in GETKITMASK_CHECKS.items():
        b = bytes.fromhex(hex_bytes)
        data[GETKITMASK + offset:GETKITMASK + offset + len(b)] = b

    data[CANWRITE:CANWRITE + len(PATTERNS["CanWriteSpellScroll"])] = PATTERNS["CanWriteSpellScroll"]
    for offset, hex_bytes in CANWRITE_CHECKS.items():
        b = bytes.fromhex(hex_bytes)
        data[CANWRITE + offset:CANWRITE + offset + len(b)] = b
    struct.pack_into("<i", data, CANWRITE + 0x27, ISUSABLE - (CANWRITE + 0x2B))

    for offset, hex_bytes in ISUSABLE_CHECKS.items():
        b = bytes.fromhex(hex_bytes)
        data[ISUSABLE + offset:ISUSABLE + offset + len(b)] = b

    return data


class Runtime:
    def __init__(self, data=None, *, runtime: str = "lua52", base: int = 0x140000000,
                 failure: str = "none", fail_at: int = 0, learn: int = LEARN):
        self.base, self.learn = base, learn
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
        self.lua.execute(SOURCE.read_bytes(), name=b"@M_CZSL.lua")
        if initialize:
            self.lua.execute(b"if Meter.listener then Meter.listener() end")
        return self

    @property
    def state(self):
        return self.lua.globals()[b"CZScrollLearnFix"]

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
        assert self.meter[b"near"] == self.meter[b"jit"] == 1
        assert self.meter[b"disable"] == self.meter[b"enable"] == 1
        assert len(self.meter[b"logs"]) == 1
        at = self.base + self.learn
        assert self.meter[b"sites"][1] == at
        target = self.meter[b"targets"][1]
        expected = bytearray(self.original)
        expected[self.learn:self.learn + 6] = (
            b"\xE9" + struct.pack("<i", target - at - 5) + b"\x90"
        )
        assert self.image_after() == expected  # only the single 6-byte hook site

    def assert_inactive(self, reason: str) -> None:
        assert not self.state[b"installed"]
        assert reason.encode() in self.state[b"status"], self.state[b"status"]
        assert len(self.meter[b"logs"]) == 1
        assert self.meter[b"disable"] == self.meter[b"enable"]
        assert self.image_after() == self.original
