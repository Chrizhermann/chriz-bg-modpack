"""Offline tests for component 695 (cbm_bg1_early_party_xp): Lua, x64 emulation, and WeiDU."""
from __future__ import annotations

import random
import re
import struct
import subprocess
from pathlib import Path

from keystone import KS_ARCH_X86, KS_MODE_64, Ks
import pytest
from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_64, Uc
import unicorn.x86_const as x86

from tests.bg1_early_party_xp_runtime import (
    APIS,
    BUILDS,
    CHECKS,
    FN,
    PATTERN,
    ROOT,
    SECTION,
    SOURCE,
    Runtime,
    fixture,
)
from tests.test_utility_xp_installer import (
    SETUP_NAME,
    WEIDU,
    SyntheticGame,
    _file_tree,
    _is_weidu_artifact,
)

COMPONENT = 695
RUNTIMES = ("lua51", "lua52", "luajit21")
REGS = [
    getattr(x86, "UC_X86_REG_" + name)
    for name in (
        "RAX", "RBX", "RCX", "RDX", "RSI", "RDI", "RBP", "RSP",
        "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15",
    )
]


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("game", BUILDS)
def test_supported_build(game, runtime):
    Runtime(fixture(game), runtime=runtime).run().assert_active()


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_iwdee_build_is_rejected(runtime):
    data = fixture("bg2ee")
    struct.pack_into("<I", data, 0x88, 0x6A18D7E9)
    struct.pack_into("<I", data, 0xD0, 0x3563000)
    r = Runtime(data, runtime=runtime).run()
    r.assert_inactive("unsupported engine build")
    assert r.meter[b"near"] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_reloads_and_repeated_listener_are_idempotent(runtime):
    r = Runtime(runtime=runtime).run(initialize=False)
    r.lua.execute(SOURCE.read_bytes())
    r.lua.execute(b"Meter.listener(); Meter.listener()")
    r.lua.execute(SOURCE.read_bytes())
    assert r.meter[b"registrations"] == 1
    r.assert_active()


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_already_initialized_listener(runtime):
    r = Runtime(runtime=runtime).run(b"EEex_GameState_AddInitializedListener=function(f) f() end")
    r.assert_active()


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("api", [a for a in APIS if a != "EEex_LuaCallReturnType"])
def test_missing_api_is_one_logged_noop(api, runtime):
    r = Runtime(runtime=runtime).run(f"{api}=nil".encode())
    r.assert_inactive("missing EEex API " + api)
    assert r.meter[b"near"] == r.meter[b"jit"] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_missing_return_type_table_is_one_logged_noop(runtime):
    r = Runtime(runtime=runtime).run(b"EEex_LuaCallReturnType=nil")
    r.assert_inactive("missing EEex API EEex_LuaCallReturnType")
    assert r.meter[b"near"] == r.meter[b"jit"] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("logging", (b"", b"io=nil", b"io.open=function() return nil end"))
def test_no_eeex_and_logging_fallback(runtime, logging):
    r = Runtime(runtime=runtime).run(b"EEex_Active=nil;" + logging)
    r.lua.execute(SOURCE.read_bytes())
    r.assert_inactive("EEex is required")
    assert r.meter[b"registrations"] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("offset", CHECKS)
def test_modified_native_guard_bytes_never_write(offset, runtime):
    data = fixture()
    data[FN + offset] ^= 1
    r = Runtime(data, runtime=runtime).run()
    r.assert_inactive("engine layout mismatch")
    assert r.meter[b"near"] == r.meter[b"jit"] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("kind", ("missing", "duplicate", "data_only"))
def test_pattern_search_requires_unique_executable_match(kind, runtime):
    data = fixture()
    if kind == "missing":
        data[FN + 0x54] ^= 1
    elif kind == "duplicate":
        data[0x1100:0x1100 + len(PATTERN)] = PATTERN
    else:
        struct.pack_into("<I", data, SECTION + 36, 0x40000040)
    r = Runtime(data, runtime=runtime).run()
    r.assert_inactive("found 2" if kind == "duplicate" else "found 0")
    assert r.meter[b"near"] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("offset,fmt,value,reason", (
    (0, "B", 0, "unsupported executable header"),
    (0x3C, "I", 0x4000, "invalid PE header offset"),
    (0x80, "B", 0, "unsupported executable format"),
    (0x84, "H", 0x14C, "unsupported executable format"),
    (0x86, "H", 97, "invalid executable sections"),
    (0x94, "H", 16, "invalid executable sections"),
    (0x98, "H", 0x10B, "unsupported optional header"),
    (0x88, "I", 0x12345678, "unsupported engine build"),
    (0xD0, "I", 0x2000, "unsupported engine build"),
    (SECTION + 8, "I", 0xFFFFFFF, "invalid executable section bounds"),
    (SECTION + 12, "I", 0, "invalid executable section bounds"),
    (SECTION + 8, "I", 0x900, "invalid function bounds"),
))
def test_unsupported_engine_is_inactive(offset, fmt, value, reason, runtime):
    data = fixture()
    struct.pack_into("<" + fmt, data, offset, value)
    r = Runtime(data, runtime=runtime).run()
    r.assert_inactive(reason)
    assert r.meter[b"near"] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("failure,fail_at", (
    ("near_throw", 1), ("near_throw", 2), ("near_throw", 3),
    ("jit_throw", 1), ("jit_throw", 2),
    ("silent", 1), ("silent", 2),
    ("partial", 1), ("partial", 2),
    ("wrong_target", 1), ("wrong_target", 2),
))
def test_failed_preparation_or_patch_preserves_original_bytes(failure, fail_at, runtime):
    r = Runtime(runtime=runtime, failure=failure, fail_at=fail_at).run()
    r.assert_inactive("inactive; native behavior retained")
    if failure == "near_throw":
        assert r.meter[b"jit"] == 0
        assert r.meter[b"near"] == fail_at
        assert b"injected near failure" in r.state[b"status"]
    else:
        assert r.meter[b"jit"] == fail_at
        assert r.meter[b"enable"] == 1


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_aslr_and_binary_nul_chunk_boundaries(runtime):
    data = fixture()
    new_fn = 0x13D0
    function = bytes(data[FN:FN + 0x310])
    data[0x1000:0x4000] = b"\xCC" * 0x3000
    data[new_fn:new_fn + len(function)] = function
    Runtime(data, runtime=runtime, base=0x7FF600000000, fn=new_fn).run().assert_active()


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_party_size_scaling_small_awards_and_remainders(runtime):
    r = Runtime(runtime=runtime).run()
    # Solo: inactive -> exact vanilla
    r.lua.execute(b"""
        MockState.party = { { m_baseStats = { m_xp = 0, m_flags = 0 } } }
        res_solo = CBM_BG1EarlyPartyXP_Plan(1000)
    """)
    assert r.eval("res_solo") == 0
    assert r.read_plan_buffer()[0] == 0

    # Zero / negative awards -> inactive
    r.lua.execute(b"""
        MockState.party = {
            { m_baseStats = { m_xp = 0, m_flags = 0 } },
            { m_baseStats = { m_xp = 0, m_flags = 0 } },
        }
        res_zero = CBM_BG1EarlyPartyXP_Plan(0)
        res_neg = CBM_BG1EarlyPartyXP_Plan(-500)
    """)
    assert r.eval("res_zero") == 0
    assert r.eval("res_neg") == 0

    # N = 2..6 for 1000 XP: 850, 800, 775, 760, 750 each
    expected_per_head = {2: 850, 3: 800, 4: 775, 5: 760, 6: 750}
    for n, head in expected_per_head.items():
        members = ", ".join("{ m_baseStats = { m_xp = 0, m_flags = 0 } }" for _ in range(n))
        r.lua.execute(f"MockState.party = {{ {members} }}; res = CBM_BG1EarlyPartyXP_Plan(1000)".encode())
        assert r.eval("res") == head * n
        active, slots = r.read_plan_buffer()
        assert active == 1
        assert slots[:n] == [head] * n

    # Small awards in 6-member party computed before division:
    # 7 XP * 4.5 = 31.5 -> round(31.5) = 32 -> 6,6,5,5,5,5 (sum=32)
    # 5 XP * 4.5 = 22.5 -> round(22.5) = 23 -> 4,4,4,4,4,3 (sum=23)
    # 10 XP * 4.5 = 45 -> 8,8,8,7,7,7 (sum=45)
    members6 = ", ".join("{ m_baseStats = { m_xp = 0, m_flags = 0 } }" for _ in range(6))
    r.lua.execute(f"MockState.party = {{ {members6} }}".encode())
    for raw, exp in (
        (7, [6, 6, 5, 5, 5, 5]),
        (5, [4, 4, 4, 4, 4, 3]),
        (10, [8, 8, 8, 7, 7, 7]),
    ):
        assert r.eval(f"CBM_BG1EarlyPartyXP_Plan({raw})") == sum(exp)
        active, slots = r.read_plan_buffer()
        assert active == 1
        assert slots[:6] == exp


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_dead_members_and_portrait_slot_mapping(runtime):
    r = Runtime(runtime=runtime).run()
    # Slot 0 alive, slot 1 dead (STATE_DEAD 0x800), slot 2 alive, slot 3 dead -> N = 2!
    r.lua.execute(b"""
        MockState.party = {
            { _state = 0,     m_baseStats = { m_xp = 1000, m_flags = 0 } },
            { _state = 0x800, m_baseStats = { m_xp = 1000, m_flags = 0 } },
            { _state = 0,     m_baseStats = { m_xp = 1000, m_flags = 0 } },
            { _state = 0x800, m_baseStats = { m_xp = 1000, m_flags = 0 } },
        }
        res = CBM_BG1EarlyPartyXP_Plan(1000)
    """)
    assert r.eval("res") == 1700
    active, slots = r.read_plan_buffer()
    assert active == 1
    assert slots[0] == 850
    assert slots[1] == 0
    assert slots[2] == 850
    assert slots[3] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_per_character_16000_cap_and_mixed_party(runtime):
    r = Runtime(runtime=runtime).run()
    # 6-member party, rawPartyXP = 1200 -> baseShare = 200, boostedShare = 900.
    # Slot 0: 0 XP -> 900
    # Slot 1: 15,600 XP -> clipped to 400 (lands at 16,000)
    # Slot 2: 15,900 XP -> baseShare (200) > room (100), so stays at 200 (never reduces vanilla!)
    # Slot 3: 40,000 XP (e.g. Baeloth) -> 200 (0 bonus)
    # Slot 4: 16,000 XP -> 200 (0 bonus)
    # Slot 5: 10,000 XP -> 900
    r.lua.execute(b"""
        MockState.party = {
            { m_baseStats = { m_xp = 0,     m_flags = 0 } },
            { m_baseStats = { m_xp = 15600, m_flags = 0 } },
            { m_baseStats = { m_xp = 15900, m_flags = 0 } },
            { m_baseStats = { m_xp = 40000, m_flags = 0 } },
            { m_baseStats = { m_xp = 16000, m_flags = 0 } },
            { m_baseStats = { m_xp = 10000, m_flags = 0 } },
        }
        res = CBM_BG1EarlyPartyXP_Plan(1200)
    """)
    expected = [900, 400, 200, 200, 200, 900]
    assert r.eval("res") == sum(expected)
    active, slots = r.read_plan_buffer()
    assert active == 1
    assert slots[:6] == expected

    # All members >= 16,000 -> inactive plan (returns 0, activeFlag = 0)
    r.lua.execute(b"""
        MockState.party = {
            { m_baseStats = { m_xp = 16000, m_flags = 0 } },
            { m_baseStats = { m_xp = 16000, m_flags = 0 } },
        }
        res_cap = CBM_BG1EarlyPartyXP_Plan(1200)
    """)
    assert r.eval("res_cap") == 0
    assert r.read_plan_buffer()[0] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_dual_class_anti_exploit_for_main_char_and_companions(runtime):
    r = Runtime(runtime=runtime).run()
    # rawPartyXP = 2000 in 2-member party -> baseShare = 1000, boostedShare = 1700.
    # Slot 0 (Player1): Fighter 5 (16,000 retired) dualed to Mage (0 active), flag=8, class=7 -> total=16,000 -> 1000
    # Slot 1 (Imoen): Thief 5 (10,000 retired) dualed to Mage (4,800 active), flag=64, class=13 -> total=14,800 -> room=1200 -> 1200
    r.lua.execute(b"""
        MockState.party = {
            { m_startTypeAI = { m_Class = 7  }, m_baseStats = { m_xp = 0,    m_flags = 8,  m_level1 = 5, m_level2 = 1 } },
            { m_startTypeAI = { m_Class = 13 }, m_baseStats = { m_xp = 4800, m_flags = 64, m_level1 = 1, m_level2 = 5 } },
        }
        res_dual = CBM_BG1EarlyPartyXP_Plan(2000)
    """)
    assert r.eval("res_dual") == 2200
    active, slots = r.read_plan_buffer()
    assert active == 1
    assert slots[:2] == [1000, 1200]

    # Custom XPLEVEL.2DA + CBMBank.old.total (e.g. dualed at 15,000 mid-level) + true multiclass (flags=0)
    r.lua.execute(b"""
        MockState.xplevel = { FIGHTER = { [1]=0, [2]=2000, [3]=4000, [4]=8000, [5]=16000 } }
        CZBG1EarlyPartyXP._test.resetCache()
        MockState.party = {
            { m_startTypeAI = { m_Class = 7 }, m_baseStats = { m_xp = 0, m_flags = 8, m_level1 = 4, m_level2 = 1 },
              _aux = { CBMBank = { old = { total = 15200 } } } },
            { m_startTypeAI = { m_Class = 7 }, m_baseStats = { m_xp = 2000, m_flags = 0, m_level1 = 2, m_level2 = 1 } },
        }
        res_bank = CBM_BG1EarlyPartyXP_Plan(2000)
    """)
    # Slot 0: max(8000, 15200) + 0 = 15200 -> room 800 < baseShare 1000 -> 1000
    # Slot 1: true multiclass (flags=0) -> total = 2000 -> 1700
    assert r.eval("res_bank") == 2700
    active, slots = r.read_plan_buffer()
    assert active == 1
    assert slots[:2] == [1000, 1700]


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_campaign_and_area_gating(runtime):
    r = Runtime(runtime=runtime).run()
    r.lua.execute(b"""
        MockState.party = {
            { m_baseStats = { m_xp = 0, m_flags = 0 } },
            { m_baseStats = { m_xp = 0, m_flags = 0 } },
        }
    """)
    # Active in EET BG1 chapters 0..7
    for ch in (0, 1, 7):
        r.lua.execute(f"MockState.campaign='BG1'; MockState.endBG1=0; MockState.inToB=0; MockState.chapter={ch}".encode())
        assert r.eval("CBM_BG1EarlyPartyXP_Plan(1000)") == 1700
    # Inactive outside BG1 on EET
    for setup in (
        "MockState.campaign='SOD'; MockState.endBG1=1; MockState.inToB=0; MockState.chapter=8",
        "MockState.campaign='BG1'; MockState.endBG1=1; MockState.inToB=0; MockState.chapter=7",
        "MockState.campaign='SOA'; MockState.endBG1=2; MockState.inToB=0; MockState.chapter=13",
        "MockState.campaign='TOB'; MockState.endBG1=2; MockState.inToB=1; MockState.chapter=20",
        "MockState.campaign='BP1'; MockState.endBG1=0; MockState.inToB=0; MockState.chapter=1",
        "MockState.campaign='BG1'; MockState.endBG1=0; MockState.inToB=0; MockState.chapter=8",
        "MockState.campaign='';    MockState.endBG1=0; MockState.inToB=0; MockState.chapter=1",
    ):
        r.lua.execute(setup.encode())
        assert r.eval("CBM_BG1EarlyPartyXP_Plan(1000)") == 0, setup

    # Standalone BG:EE allows empty or BG1 campaign, but blocks SoD/BP/Tutorial areas
    r_bgee = Runtime(fixture("bgee"), runtime=runtime).run()
    r_bgee.lua.execute(b"""
        MockState.party = {
            { m_baseStats = { m_xp = 0, m_flags = 0 } },
            { m_baseStats = { m_xp = 0, m_flags = 0 } },
        }
        MockState.endBG1 = 0; MockState.inToB = 0; MockState.chapter = 1
    """)
    for camp, area, want in (
        ("", "AR2600", 1700),
        ("BG1", "AR2300", 1700),
        ("", "BD0120", 0),
        ("", "OH9310", 0),
        ("", "TU0015", 0),
        ("SOD", "BD1000", 0),
        ("BP1", "OH9310", 0),
    ):
        r_bgee.lua.execute(f"MockState.campaign='{camp}'; MockState.area='{area}'".encode())
        assert r_bgee.eval("CBM_BG1EarlyPartyXP_Plan(1000)") == want, (camp, area)


@pytest.mark.parametrize("base", (0x140000000, 0x7FF600000000))
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_generated_hook_instructions_preserve_native_contract(base, runtime):
    r = Runtime(runtime=runtime, base=base).run()
    r.assert_active()
    assembler = Ks(KS_ARCH_X86, KS_MODE_64)
    emulator = Uc(UC_ARCH_X86, UC_MODE_64)
    emulator.mem_map(base, 0x10000)
    emulator.mem_map(0x60000000, 0x10000)  # synthetic CInfGame
    emulator.mem_map(0x70000000, 0x10000)  # synthetic stack
    plan_buf = r.state[b"planBuffer"]
    buf_page = plan_buf & ~0xFFF
    emulator.mem_map(buf_page, 0x1000)

    emulator.mem_write(base, r.image_after())
    callee_addr = r.meter[b"targets"][1]
    t1_addr = r.meter[b"targets"][2]
    t2_addr = r.meter[b"targets"][3]
    for at, assembly in (
        (t1_addr, r.meter[b"assembly"][2].decode()),
        (t2_addr, r.meter[b"assembly"][3].decode()),
    ):
        blob = bytes(assembler.asm(assembly, addr=at)[0])
        emulator.mem_map(at, 0x1000)
        emulator.mem_write(at, blob)

    # Stub callee at callee_addr: records RCX, returns [callee_page + 0x800], resets active flag if 0.
    callee_page = callee_addr & ~0xFFF
    emulator.mem_map(callee_page, 0x1000)
    callee_code = bytes(assembler.asm(
        f"mov qword ptr [{callee_page + 0x810}], rcx; "
        f"mov eax, dword ptr [{callee_page + 0x800}]; "
        "mov edx, 0xDEAD0001; mov r8d, 0xDEAD0002; mov r9d, 0xDEAD0003; ret",
        addr=callee_addr,
    )[0])
    emulator.mem_write(callee_addr, callee_code)

    fn = base + FN
    destinations = {fn + 0x158, fn + 0x229}
    seen = []

    def stop(uc, address, size, user):
        if address in destinations:
            seen.append(address)
            uc.emu_stop()

    emulator.hook_add(UC_HOOK_CODE, stop)
    rng = random.Random(695)

    # Test Site 1 (fn + 0x152 -> trampoline1 -> fn + 0x158)
    for ebx_val, stub_ret in ((1000, 4500), (1000, 0), (0, 9999), (-50, 9999)):
        registers = {reg: rng.getrandbits(48) for reg in REGS}
        registers.update({
            x86.UC_X86_REG_RSI: 0x60000000,
            x86.UC_X86_REG_RSP: 0x70008000,
            x86.UC_X86_REG_RBX: ebx_val & 0xFFFFFFFFFFFFFFFF,
        })
        for reg, number in registers.items():
            emulator.reg_write(reg, number)
        emulator.mem_write(plan_buf, struct.pack("<I", 1))
        emulator.mem_write(callee_page + 0x800, struct.pack("<i", stub_ret))
        emulator.mem_write(callee_page + 0x810, b"\x00" * 8)
        seen.clear()
        emulator.emu_start(fn + 0x152, 0, count=200)
        assert seen == [fn + 0x158]
        # Nonvolatile registers + RSP preserved
        for reg in (x86.UC_X86_REG_RBX, x86.UC_X86_REG_RSI, x86.UC_X86_REG_RDI,
                    x86.UC_X86_REG_RBP, x86.UC_X86_REG_RSP,
                    x86.UC_X86_REG_R12, x86.UC_X86_REG_R14, x86.UC_X86_REG_R15):
            assert emulator.reg_read(reg) == registers[reg]
        # planBuf[0] cleared before call
        assert struct.unpack("<I", bytes(emulator.mem_read(plan_buf, 4)))[0] == 0
        # RDX == 2, RCX == RSI, R8D == stub_ret if (ebx>0 and stub_ret>0) else ebx
        assert emulator.reg_read(x86.UC_X86_REG_RDX) == 2
        assert emulator.reg_read(x86.UC_X86_REG_RCX) == 0x60000000
        expected_r8 = (stub_ret if ebx_val > 0 and stub_ret > 0 else ebx_val) & 0xFFFFFFFF
        assert emulator.reg_read(x86.UC_X86_REG_R8) & 0xFFFFFFFF == expected_r8
        if ebx_val > 0:
            got_arg = struct.unpack("<q", bytes(emulator.mem_read(callee_page + 0x810, 8)))[0]
            assert got_arg == ebx_val

    # Test Site 2 (fn + 0x224 -> trampoline2 -> fn + 0x229)
    slot_values = [100 + s * 111 for s in range(16)]
    emulator.mem_write(plan_buf + 4, struct.pack("<16I", *slot_values))
    for active in (0, 1):
        emulator.mem_write(plan_buf, struct.pack("<I", active))
        for slot in (0, 1, 5, 15, 16, 20):
            registers = {reg: rng.getrandbits(48) for reg in REGS}
            registers.update({
                x86.UC_X86_REG_RBX: (registers[x86.UC_X86_REG_RBX] & ~0xFFFF) | slot,
                x86.UC_X86_REG_RSP: 0x70008000,
            })
            for reg, number in registers.items():
                emulator.reg_write(reg, number)
            emulator.mem_write(0x70008044, struct.pack("<I", 777))
            seen.clear()
            emulator.emu_start(fn + 0x224, 0, count=200)
            assert seen == [fn + 0x229]
            for reg in (x86.UC_X86_REG_RBX, x86.UC_X86_REG_RSI, x86.UC_X86_REG_RDI,
                        x86.UC_X86_REG_RBP, x86.UC_X86_REG_RSP,
                        x86.UC_X86_REG_R12, x86.UC_X86_REG_R14, x86.UC_X86_REG_R15):
                assert emulator.reg_read(reg) == registers[reg]
            assert emulator.reg_read(x86.UC_X86_REG_R9) == 0x70008030
            got_xp = struct.unpack("<I", bytes(emulator.mem_read(0x70008044, 4)))[0]
            want_xp = slot_values[slot] if (active == 1 and slot < 16) else 777
            assert got_xp == want_xp


def test_real_eeex_preprocess_assembly_compiles_all_snippets():
    """Run m_czxpbg.lua's JIT snippets through pinned EEex_Assembly / EEex_Assembly_x86-64 preprocessing + Keystone."""
    from lupa import luajit21
    from tests.pinned_eeex import pinned_eeex_script

    assembly_lua = pinned_eeex_script("EEex_Assembly.lua")
    x64_lua = pinned_eeex_script("EEex_Assembly_x86-64.lua")
    script_files = {
        "EEex_Assembly": assembly_lua,
        "EEex_Assembly_x86-64": x64_lua,
    }

    # Capture generated assembly directly from real EEex_JITNear / EEex_JITAt / EEex_PreprocessAssembly
    data = fixture("bg2ee")
    lua = luajit21.LuaRuntime(encoding=None)
    lua.globals()[b"image"] = bytes(data)
    lua.globals()[b"base"] = 0x140000000
    lua.globals()[b"failure"] = b"none"
    lua.globals()[b"fail_at"] = 0

    from tests.bg1_early_party_xp_runtime import STUBS
    lua.execute(STUBS.read_bytes())

    # Replace stubbed EEex_GenLuaCall / EEex_JITNear / EEex_JITAt with real EEex preprocessor pipeline
    captured: list[tuple[str, int, str]] = []
    alloc_cursor = [0x140000000 + 0x4000000]
    str_cursor = [0x140000000 + 0x4100000]

    def py_iterate_regex(text, pattern, cb):
        s = text.decode("latin1") if isinstance(text, bytes) else str(text)
        pat = pattern.decode("latin1") if isinstance(pattern, bytes) else str(pattern)
        for m in re.finditer(pat, s, re.MULTILINE):
            groups = {}
            for idx, g in enumerate(m.groups(), start=1):
                if g is not None:
                    groups[idx] = g.encode("latin1")
            pos = m.start() + 1
            end_pos = m.end()
            matched = m.group(0).encode("latin1")
            lua_groups = lua.table_from(groups)
            if cb(pos, end_pos, matched, lua_groups):
                break

    def py_to_dec_str(val):
        return str(int(val)).encode("ascii")

    def py_write_string_auto(val):
        addr = str_cursor[0]
        raw = val if isinstance(val, bytes) else str(val).encode("utf-8")
        str_cursor[0] += len(raw) + 16
        return addr

    def py_alloc_code_page():
        addr = alloc_cursor[0]
        alloc_cursor[0] += 0x10000
        return addr

    def _assemble_asmjit_with_keystone(asm_text: str, addr: int) -> bytes:
        # Normalize AsmJit-specific syntax (`ss:`, `qword ptr` on `lea`, `;` comments, `jmp short`) for Keystone.
        cleaned_lines = []
        for raw_line in asm_text.splitlines():
            line = raw_line.split(";", 1)[0].strip()
            if not line:
                continue
            line = re.sub(r"\bss:\[", "[", line)
            line = re.sub(r"^(lea\s+\w+\s*,\s*)qword\s+ptr\s+", r"\1", line)
            line = re.sub(r"\bjmp\s+short\s+", "jmp ", line)
            cleaned_lines.append(line)
        cleaned_lines.append("nop")
        ks_asm = "\n".join(cleaned_lines)
        assembler = Ks(KS_ARCH_X86, KS_MODE_64)
        try:
            encoding, _ = assembler.asm(ks_asm, addr=int(addr))
        except Exception as exc:
            raise AssertionError(f"Keystone failed at 0x{addr:X}: {exc}\n--- ASM ---\n{ks_asm}") from exc
        return bytes(encoding)

    def py_jit_at_internal(dst, check_jit, asm_str):
        s = asm_str.decode("latin1") if isinstance(asm_str, bytes) else str(asm_str)
        blob = _assemble_asmjit_with_keystone(s, int(dst))
        assert len(blob) > 0
        rc = check_jit(len(blob))
        assert rc == 0, f"unexpected relocation request: {rc}"
        captured.append(("near" if dst >= 0x144000000 else "at", int(dst), s))
        return lua.table_from({
            b"errorType": None,
            b"labelAddresses": lua.table_from({b"hook_start": int(dst), b"hook_end": int(dst) + len(blob)}),
        })

    g = lua.globals()
    g[b"EEex_Active"] = True
    g[b"EEex_Architecture"] = b"x86-64"
    g[b"EEex_GetPatternMap"] = lambda: lua.table_from({})
    g[b"EEex_IterateRegex"] = py_iterate_regex
    g[b"EEex_ToDecStr"] = py_to_dec_str
    g[b"EEex_WriteStringAuto"] = py_write_string_auto
    g[b"_py_alloc_code_page"] = py_alloc_code_page
    g[b"EEex_JITAtInternal"] = py_jit_at_internal
    g[b"EEex_DoFile"] = lambda name: lua.execute(
        script_files[name.decode("ascii") if isinstance(name, bytes) else name].read_bytes()
    )
    lua.execute(b"""
        function EEex_AllocCodePageInternal()
            return _py_alloc_code_page(), 0x10000
        end
    """)

    lua.execute(assembly_lua.read_bytes(), name=b"@EEex_Assembly.lua")
    g[b"EEex_Assembly_Private_PostJIT"] = lambda *args: None
    for idx, label in enumerate((
        "Hardcoded_InternalLuaState",
        "Hardcoded_lua_getglobal",
        "Hardcoded_lua_getfield",
        "Hardcoded_lua_pushstring",
        "Hardcoded_lua_pushinteger",
        "Hardcoded_lua_pcallk",
        "EEex_CheckCallError",
        "Hardcoded_lua_settop",
        "Hardcoded_lua_tointegerx",
    ), start=1):
        lua.eval(f"EEex_DefineAssemblyLabel('{label}', 0x{0x140500000 + idx * 0x100:X})".encode("ascii"))

    # Keep EEex_JITAt recording our stub writes in `edits` while assembling via Keystone.
    orig_jit_at = g[b"EEex_JITAt"]
    lua.execute(b"""
        local real_JITAt = EEex_JITAt
        function EEex_JITAt(dst, assemblyT)
            local asm = EEex_PreprocessAssembly(assemblyT)
            local blob = _py_assemble_at(dst, asm)
            for i = 1, #blob do
                EEex_WriteU8(dst + i - 1, blob:byte(i))
            end
            return real_JITAt(dst, assemblyT)
        end
    """)

    def py_assemble_at(dst, asm_str):
        s = asm_str.decode("latin1") if isinstance(asm_str, bytes) else str(asm_str)
        return _assemble_asmjit_with_keystone(s, int(dst))

    g[b"_py_assemble_at"] = py_assemble_at
    # Ensure Meter.near counts real EEex_JITNear calls too if asserted
    lua.execute(SOURCE.read_bytes(), name=b"@M_CZXPBG.lua")
    lua.execute(b"if Meter.listener then Meter.listener() end")

    logs = [v.decode("latin1") if isinstance(v, bytes) else v for v in g[b"Meter"][b"logs"].values()]
    assert lua.eval("CZBG1EarlyPartyXP.installed") is True, logs
    # 3 near blocks (planCallee, trampoline1, trampoline2) + 2 hook-site patches
    near_blocks = [entry for entry in captured if entry[0] == "near"]
    at_blocks = [entry for entry in captured if entry[0] == "at"]
    assert len(near_blocks) == 3
    assert len(at_blocks) == 2
    assert "CBM_BG1EarlyPartyXP_Plan" not in near_blocks[0][2]  # resolved via WriteStringCache
    assert "dword ptr" in near_blocks[1][2] and "dword ptr" in near_blocks[2][2]


def test_api_audit_covers_every_call_and_capability_check():
    names = set(re.findall(r"\bEEex_\w+", SOURCE.read_text(encoding="utf-8"))) - {"EEex_Active"}
    assert names == set(APIS)


def _game_files(root: Path) -> dict[str, bytes]:
    return {
        name: payload
        for name, payload in _file_tree(root).items()
        if not _is_weidu_artifact(name)
    }


def _run_component(game: SyntheticGame, *, uninstall: bool = False) -> str:
    assert WEIDU is not None
    result = subprocess.run(
        [
            str(WEIDU),
            SETUP_NAME,
            "--game", str(game.root),
            "--force-uninstall-list" if uninstall else "--force-install-list",
            str(COMPONENT),
            "--language", "0",
            "--use-lang", "en_us",
            "--no-exit-pause",
            "--noautoupdate",
            "--no-auto-tp2",
            "--quick-log",
        ],
        cwd=game.root,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=90,
        check=False,
    )
    transcript = result.stdout + result.stderr
    assert result.returncode == 0, transcript
    assert "ERROR:" not in transcript and "INSTALLED WITH WARNINGS" not in transcript, transcript
    return transcript


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
def test_weidu_parse_check():
    result = subprocess.run(
        [str(WEIDU), "--noautoupdate", "--nogame", "--parse-check", "TPA",
         "chriz-bg-modpack/lib/cbm_bg1_early_party_xp.tpa"],
        cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=30,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ERROR" not in output and "WARNING" not in output, output


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
@pytest.mark.parametrize("game_type", ("bgee", "eet"))
@pytest.mark.parametrize("existing", (None, b"-- prior early xp\n", b"hand-edited replacement\0\xff"))
def test_install_reinstall_uninstall_across_bgee_and_eet(tmp_path, game_type, existing):
    game = SyntheticGame(tmp_path / "game", game=game_type, eeex=True)
    if existing is not None:
        (game.override / "m_czxpbg.lua").write_bytes(existing)
    before = _game_files(game.root)
    payload = SOURCE.read_bytes()

    for _ in range(2):
        transcript = _run_component(game)
        assert "SUCCESSFULLY INSTALLED" in transcript
        assert re.search(rf"(?m)#0\s+#{COMPONENT}\b", game.active_log())
        expected = dict(before)
        expected["OVERRIDE/M_CZXPBG.LUA"] = payload
        assert _game_files(game.root) == expected

    transcript = _run_component(game, uninstall=True)
    assert "SUCCESSFULLY REMOVED" in transcript
    assert not re.search(rf"(?m)#0\s+#{COMPONENT}\b", game.active_log())
    assert _game_files(game.root) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
def test_bg2ee_without_eet_skips_cleanly(tmp_path):
    game = SyntheticGame(tmp_path / "game", game="bg2ee", eeex=True)
    before = _game_files(game.root)
    result = subprocess.run(
        [
            str(WEIDU), SETUP_NAME, "--game", str(game.root),
            "--force-install-list", str(COMPONENT),
            "--language", "0", "--use-lang", "en_us",
            "--no-exit-pause", "--noautoupdate", "--no-auto-tp2", "--quick-log",
        ],
        cwd=game.root, capture_output=True, text=True, errors="replace", timeout=90, check=False,
    )
    transcript = result.stdout + result.stderr
    assert result.returncode == 0, transcript
    assert "BG1 early-party XP boost supports BG:EE and EET." in transcript
    assert _game_files(game.root) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
def test_missing_eeex_logs_inactive_and_enables_on_reinstall(tmp_path):
    game = SyntheticGame(tmp_path / "game", game="eet", eeex=False)
    before = _game_files(game.root)

    transcript = _run_component(game)
    assert transcript.count("[CBM BG1 early-party XP] Inactive: EEex (override/M___EEex.lua) was not found.") == 1
    assert "SUCCESSFULLY INSTALLED" in transcript
    assert _game_files(game.root) == before

    (game.override / "m___eeex.lua").write_bytes(b"-- EEex installed later\n")
    transcript = _run_component(game)
    assert "SUCCESSFULLY INSTALLED" in transcript
    assert _game_files(game.root)["OVERRIDE/M_CZXPBG.LUA"] == SOURCE.read_bytes()

    transcript = _run_component(game, uninstall=True)
    assert "SUCCESSFULLY REMOVED" in transcript
    after_uninstall = _game_files(game.root)
    assert "OVERRIDE/M_CZXPBG.LUA" not in after_uninstall
    assert after_uninstall["OVERRIDE/M___EEEX.LUA"] == b"-- EEex installed later\n"
