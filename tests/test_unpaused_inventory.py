"""Offline tests for components 699/700 (cbm_unpaused_inventory_*): Lua, x64 emulation, and WeiDU."""
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

from tests.unpaused_inventory_runtime import (
    ALWAYS_CFG,
    APIS,
    BUILDS,
    COMBAT_CFG,
    FN_ACT,
    FN_ASY,
    FN_STARTTIME,
    FN_TOG,
    PAT_ACT,
    PAT_ASY,
    PAT_TOG,
    P_CHITIN,
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
    _write_key_and_bif,
)

RUNTIMES = ("lua52", "luajit21")
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
def test_reloads_and_repeated_listener_are_idempotent(runtime):
    r = Runtime(runtime=runtime).run(initialize=False)
    r.lua.execute(SOURCE.read_bytes())
    r.lua.execute(b"Meter.listener(); Meter.listener()")
    r.lua.execute(SOURCE.read_bytes())
    assert r.meter[b"registrations"] == 1
    assert r.meter[b"destroyed_registrations"] == 1
    r.assert_active()


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_already_initialized_listener(runtime):
    r = Runtime(runtime=runtime).run(b"EEex_GameState_AddInitializedListener=function(f) f() end")
    r.assert_active()


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("api", APIS)
def test_missing_api_is_one_logged_noop(api, runtime):
    r = Runtime(runtime=runtime).run(f"{api}=nil".encode())
    r.assert_inactive("missing EEex API " + api)
    assert r.meter[b"near"] == r.meter[b"jit"] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("logging", (b"", b"io=nil", b"io.open=function() return nil end"))
def test_no_eeex_and_logging_fallback(runtime, logging):
    r = Runtime(runtime=runtime).run(b"EEex_Active=nil;" + logging)
    r.lua.execute(SOURCE.read_bytes())
    r.assert_inactive("inactive: EEex is required")


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_missing_or_invalid_config_is_clean_inactive_noop(runtime):
    r = Runtime(runtime=runtime).run(b"MockState.configMode=nil; CZUnpausedInventoryConfig=nil")
    r.assert_inactive("missing or invalid CZINVUCF.lua")
    r2 = Runtime(runtime=runtime).run(b"MockState.configMode='bogus'")
    r2.assert_inactive("missing or invalid CZINVUCF.lua")


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("header_case", ("bad_mz", "bad_pe", "bad_machine", "bad_build", "bad_size"))
def test_invalid_executable_header_rejected_before_writing(header_case, runtime):
    data = fixture()
    if header_case == "bad_mz":
        data[0:2] = b"NO"
    elif header_case == "bad_pe":
        data[0x80:0x84] = b"NOPE"
    elif header_case == "bad_machine":
        struct.pack_into("<H", data, 0x84, 0x014C)
    elif header_case == "bad_build":
        struct.pack_into("<I", data, 0x88, 0x12345678)
    else:
        struct.pack_into("<I", data, 0xD0, 0x1234000)
    r = Runtime(data, runtime=runtime).run()
    r.assert_inactive("unsupported")
    assert r.meter[b"writes"] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("which", ("act", "tog", "asy"))
def test_missing_or_duplicate_pattern_rejected_without_writes(which, runtime):
    for duplicate in (False, True):
        data = fixture()
        pat, rva = {
            "act": (PAT_ACT, FN_ACT + 0x29),
            "tog": (PAT_TOG, FN_TOG + 0x47),
            "asy": (PAT_ASY, FN_ASY + 0x2D),
        }[which]
        if duplicate:
            data[0x4500:0x4500 + len(pat)] = pat
        else:
            data[rva] ^= 0xFF
        r = Runtime(data, runtime=runtime).run()
        r.assert_inactive("expected one")
        assert r.meter[b"writes"] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("guard", ("act_prolog", "act_call", "tog_call", "tog_mid", "starttime", "chitin_mismatch"))
def test_guard_mismatch_rejected_without_writes(guard, runtime):
    data = fixture()
    offset = {
        "act_prolog": FN_ACT + 0x02,
        "act_call": FN_ACT + 0x0D,
        "tog_call": FN_ACT + 0x60,
        "tog_mid": FN_TOG + 0x47 + 0x12,
        "starttime": FN_STARTTIME + 2,
        "chitin_mismatch": FN_ACT + 0x25,
    }[guard]
    data[offset] ^= 0x01
    r = Runtime(data, runtime=runtime).run()
    r.assert_inactive("inactive")
    assert r.meter[b"writes"] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("fail_at", (1, 2, 3))
@pytest.mark.parametrize("failure", ("near_throw", "jit_throw", "wrong_target", "silent", "partial"))
def test_failed_patch_rolls_back_all_hook_sites(failure, fail_at, runtime):
    r = Runtime(runtime=runtime, failure=failure, fail_at=fail_at).run()
    r.assert_inactive("inactive; native behavior retained")
    assert r.image_after() == r.original
    assert r.meter[b"disable"] == r.meter[b"enable"]


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_mode_configs_and_combat_detection(runtime):
    # Always mode -> always 1 regardless of combat state
    r_always = Runtime(runtime=runtime).run()
    r_always.assert_active()
    r_always.lua.execute(ALWAYS_CFG.read_bytes())
    assert r_always.eval("CZUnpausedInventory._test.resolveMode()") == b"always"
    assert r_always.eval("CZUnpausedInventory._test.shouldUnpause()") == 1

    # Combat mode -> tests battleSong, secondary counter, and living vs dead party See([EVILCUTOFF])
    data = bytearray(fixture())
    # Give room inside RVA 0x5200..0x5FFF for chitin/game/area structs
    r = Runtime(data, runtime=runtime).run(COMBAT_CFG.read_bytes())
    r.assert_active()
    p_chitin = r.state[b"pChitin"]
    assert p_chitin == r.base + P_CHITIN

    # Build synthetic structs in Malloc memory (addresses > 32-bit, verifying readPtr!)
    chitin = r.lua.eval(b"EEex_Malloc(0x1200)")
    game = r.lua.eval(b"EEex_Malloc(0x7A00)")
    area = r.lua.eval(b"EEex_Malloc(0x1100)")

    def w64(addr, val):
        r.write_bytes(addr, struct.pack("<Q", val))

    def w32(addr, val):
        r.write_bytes(addr, struct.pack("<I", val))

    w64(p_chitin, chitin)
    assert r.eval(f"CZUnpausedInventory._test.readPtr({p_chitin})") == chitin
    w64(chitin + 0x1090, game)
    r.write_bytes(game + 0x6590, b"\x02")  # visIdx = 2
    w64(game + 0x6598 + 2 * 8, area)

    # Out of combat: counters 0, no party sees enemy
    assert r.eval("CZUnpausedInventory._test.isInCombat()") is False
    assert r.eval("CZUnpausedInventory._test.shouldUnpause()") == 0

    # BattleSong > 0
    w32(area + 0xFA4, 5)
    assert r.eval("CZUnpausedInventory._test.isInCombat()") is True
    assert r.eval("CZUnpausedInventory._test.shouldUnpause()") == 1
    w32(area + 0xFA4, 0)

    # Secondary combat counter > 0
    w32(area + 0xFA8, 1)
    assert r.eval("CZUnpausedInventory._test.isInCombat()") is True
    w32(area + 0xFA8, 0)
    assert r.eval("CZUnpausedInventory._test.isInCombat()") is False

    # Party LOS: dead member (STATE_DEAD = 0x800) ignored even if _seesEnemy, living member triggers combat
    r.lua.execute(b"MockState.party = { {_state = 0x800, _seesEnemy = true}, {_state = 0, _seesEnemy = false} }")
    assert r.eval("CZUnpausedInventory._test.isInCombat()") is False
    r.lua.execute(b"MockState.party[2]._seesEnemy = true")
    assert r.eval("CZUnpausedInventory._test.isInCombat()") is True

    # DestroyedListener cleans cached trigger cleanly
    assert r.eval("CZUnpausedInventory.enemyTrigger ~= nil") is True
    r.lua.execute(b"Meter.destroyed_listener()")
    assert r.eval("MockState.triggerFreed") == 1
    assert r.eval("CZUnpausedInventory.enemyTrigger == nil") is True


@pytest.mark.parametrize("base", (0x140000000, 0x7FF600000000))
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_generated_hook_trampolines_preserve_abi_and_execute_all_paths(base, runtime):
    r = Runtime(runtime=runtime, base=base).run()
    r.assert_active()

    assembler = Ks(KS_ARCH_X86, KS_MODE_64)
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    uc.mem_map(base, 0x10000)
    uc.mem_map(0x60000000, 0x20000)  # chitin (0x60000000), world (+0x2000), inv (+0x4000), game (+0x6000), other (+0xE000)
    uc.mem_map(0x62000000, 0x1000)   # harness counters / flags
    uc.mem_map(0x70000000, 0x10000)  # stack

    chitin = 0x60000000
    world = 0x60002000
    inv = 0x60004000
    game = 0x60006000
    other_screen = 0x6000E000

    # Counters in 0x62000000:
    # +0x00: dword should_unpause_ret (0 or 1)
    # +0x04: dword query_calls
    # +0x08: dword tog_calls
    # +0x0C: dword starttime_calls
    # +0x10: dword vanilla_pause_taken
    CTRL = 0x62000000

    uc.mem_write(base, r.image_after())
    p_chitin_addr = base + P_CHITIN
    uc.mem_write(p_chitin_addr, struct.pack("<Q", chitin))
    uc.mem_write(chitin + 0x1090, struct.pack("<Q", game))
    uc.mem_write(chitin + 0x10C8, struct.pack("<Q", inv))
    uc.mem_write(chitin + 0x1110, struct.pack("<Q", world))

    # Populate native instructions AFTER hook points so we observe exact destinations:
    # At fnAct + 0x3F: jnz fnAct+0x77; else sets vanilla_pause_taken=1 and stops at fnAct+0x41.
    # Replace fnAct+0x3F with `75 36` (already 0x75 0x36 in PAT_ACT? Yes!).
    # Wait: fill fnAct+0x77 with `nop`, and place a marker write at fnAct+0x41? Better: stop hook at fnAct+0x41 AND fnAct+0x77!
    # Map and assemble queryCallee (target 1) and the three hook trampolines (targets 2, 3, 4).
    q_addr = r.meter[b"targets"][1]
    q_page = q_addr & ~0xFFF
    uc.mem_map(q_page, 0x1000)
    # ABI-hostile queryCallee: increments query_calls, returns [CTRL], clobbers all volatile regs, preserves callee-saved.
    q_code = bytes(assembler.asm(f"""
        mov rax, {CTRL}
        inc dword ptr [rax+4]
        mov eax, dword ptr [rax]
        mov rcx, 0x11111111
        mov rdx, 0x22222222
        mov r8,  0x33333333
        mov r9,  0x44444444
        mov r10, 0x55555555
        mov r11, 0x66666666
        ret
    """, addr=q_addr)[0])
    uc.mem_write(q_addr, q_code)

    for idx in (2, 3, 4):
        at = r.meter[b"targets"][idx]
        blob = bytes(assembler.asm(r.meter[b"assembly"][idx].decode(), addr=at)[0])
        uc.mem_map(at & ~0xFFF, 0x1000)
        uc.mem_write(at, blob)

    # Stub CTimerWorld::StartTime (FN_STARTTIME): verifies rcx == game + 0x3FA0, sets bActive=1, increments [CTRL+0x0C], ret.
    st_code = bytes(assembler.asm(f"""
        mov rax, {game + 0x3FA0}
        cmp rcx, rax
        jne bad_st
        mov byte ptr [rcx+4], 1
        mov rax, {CTRL}
        inc dword ptr [rax+12]
        mov rcx, 0xAAAAAAAA
        mov rdx, 0xBBBBBBBB
        ret
    bad_st:
        ud2
    """, addr=base + FN_STARTTIME)[0])
    uc.mem_write(base + FN_STARTTIME, st_code)

    # Stub fnTog (base + FN_TOG) ONLY when entered from start (direct call from InvAct / InvAsync):
    # Wait: Site 2 patches fnTog + 0x55! Put stub at fnTog + 0x00 that jumps to +0x70 to verify args,
    # unpause [rcx+0xBC] = 0, increment [CTRL+8], and ret!
    # Also place simple stop sentinels at fnTog+0x5D (allowed) and fnTog+0x47+0x0E+0x0631 (togEpilogue = suppressed).
    tog_epilogue = base + FN_TOG + 0x47 + 0x0E + 0x0631
    tog_entry_code = bytes(assembler.asm(f"""
        cmp rcx, {world}
        jne bad_tog
        test edx, edx
        jnz bad_tog
        cmp r8b, 1
        jne bad_tog
        test r9d, r9d
        jnz bad_tog
        cmp byte ptr [rsp+0x28], 0
        jnz bad_tog
        cmp byte ptr [rsp+0x30], 0
        jnz bad_tog
        mov byte ptr [rcx+0xBC], 0
        mov rax, {game + 0x3FA0}
        mov byte ptr [rax+4], 1
        mov rax, {CTRL}
        inc dword ptr [rax+8]
        xor eax, eax
        ret
    bad_tog:
        ud2
    """, addr=base + FN_TOG)[0])
    # FN_TOG + 0x47 is hitTog, so 0x47 bytes available -> check length!
    assert len(tog_entry_code) <= 0x47, len(tog_entry_code)
    uc.mem_write(base + FN_TOG, tog_entry_code)

    stop_addrs = {
        base + FN_ACT + 0x41,          # vanilla pause path
        base + FN_ACT + 0x77,          # unpaused / skipped pause path
        base + FN_TOG + 0x5D,          # TogglePause allowed
        tog_epilogue,                  # TogglePause suppressed
        base + FN_ASY + 0x35,          # InvAsync resumed
    }
    stopped_at = []

    def on_code(emu, address, size, user):
        if address in stop_addrs:
            stopped_at.append(address)
            emu.emu_stop()

    uc.hook_add(UC_HOOK_CODE, on_code)
    rng = random.Random(696)

    def reset_state(should_unp: int, paused: int, timer_active: int, multi: int = 0, active_eng: int = inv):
        uc.mem_write(CTRL, struct.pack("<5I", should_unp, 0, 0, 0, 0))
        uc.mem_write(chitin + 0x2C9, bytes((multi,)))
        uc.mem_write(chitin + 0x208, struct.pack("<Q", active_eng))
        uc.mem_write(world + 0xBC, bytes((paused,)))
        uc.mem_write(world + 0xBA4, struct.pack("<I", 0))
        uc.mem_write(world + 0xB9C, struct.pack("<I", 0))
        uc.mem_write(world + 0xB98, struct.pack("<I", 0))
        uc.mem_write(game + 0x3FA4, bytes((timer_active,)))
        uc.mem_write(inv + 0x76C, struct.pack("<I", 0xCAFE))
        uc.mem_write(inv + 0x6D8, struct.pack("<i", -1))

    def read_ctrl():
        return struct.unpack("<5I", bytes(uc.mem_read(CTRL, 20)))

    # ---- Test Site 1: InvAct (FN_ACT + 0x30) ----
    for should_unp, paused, timer_before, exp_stop, exp_was_paused, exp_paused, exp_timer, exp_tog, exp_st in (
        # Vanilla (out of combat), unpaused before -> pauses natively (m_bWasPaused=0 -> vanilla pause path)
        (0, 0, 0, base + FN_ACT + 0x41, 0, 0, 0, 0, 0),
        # Vanilla (out of combat), already paused -> skips pause natively (m_bWasPaused=1)
        (0, 1, 0, base + FN_ACT + 0x77, 1, 1, 0, 0, 0),
        # Unpaused mode, ALREADY unpaused before (CScreenWorld::EngineDeactivated stopped timer=0) -> StartTime restores timer!
        (1, 0, 0, base + FN_ACT + 0x77, 1, 0, 1, 0, 1),
        # Unpaused mode, PAUSED before -> TogglePauseGame unpauses & starts timer, m_bWasPaused=1
        (1, 1, 0, base + FN_ACT + 0x77, 1, 0, 1, 1, 0),
    ):
        reset_state(should_unp, paused, timer_before)
        regs = {reg: rng.getrandbits(48) for reg in REGS}
        regs.update({
            x86.UC_X86_REG_RBX: inv,
            x86.UC_X86_REG_RDX: world,
            x86.UC_X86_REG_RSP: 0x70008000,
        })
        for reg, val in regs.items():
            uc.reg_write(reg, val)
        stopped_at.clear()
        uc.emu_start(base + FN_ACT + 0x30, 0, count=200)
        assert stopped_at == [exp_stop]
        for reg in (x86.UC_X86_REG_RBX, x86.UC_X86_REG_RSI, x86.UC_X86_REG_RDI, x86.UC_X86_REG_RBP,
                    x86.UC_X86_REG_RSP, x86.UC_X86_REG_R12, x86.UC_X86_REG_R14, x86.UC_X86_REG_R15):
            assert uc.reg_read(reg) == regs[reg]
        assert struct.unpack("<I", bytes(uc.mem_read(inv + 0x76C, 4)))[0] == exp_was_paused
        assert bytes(uc.mem_read(world + 0xBC, 1))[0] == exp_paused
        assert bytes(uc.mem_read(game + 0x3FA4, 1))[0] == exp_timer
        _, q_cnt, tog_cnt, st_cnt, _ = read_ctrl()
        assert q_cnt == 1 and tog_cnt == exp_tog and st_cnt == exp_st

    # ---- Test Site 2: TogglePause (FN_TOG + 0x55) ----
    for should_unp, paused, multi, eng, exp_stop, exp_q in (
        (1, 0, 0, inv, tog_epilogue, 1),          # singleplayer in Inventory trying to pause -> suppressed
        (0, 0, 0, inv, base + FN_TOG + 0x5D, 1),  # combat-only out of combat -> allowed
        (1, 1, 0, inv, base + FN_TOG + 0x5D, 0),  # already paused (unpausing) -> allowed immediately
        (1, 0, 0, other_screen, base + FN_TOG + 0x5D, 0),  # Spellbook/World -> allowed immediately
        (1, 0, 1, inv, base + FN_TOG + 0x5D, 0),  # multiplayer -> allowed immediately
    ):
        reset_state(should_unp, paused, 0, multi=multi, active_eng=eng)
        regs = {reg: rng.getrandbits(48) for reg in REGS}
        regs.update({
            x86.UC_X86_REG_RBX: world,
            x86.UC_X86_REG_RDI: 0,
            x86.UC_X86_REG_RSP: 0x70008000,
        })
        for reg, val in regs.items():
            uc.reg_write(reg, val)
        stopped_at.clear()
        uc.emu_start(base + FN_TOG + 0x55, 0, count=200)
        assert stopped_at == [exp_stop]
        if exp_stop == base + FN_TOG + 0x5D:
            assert uc.reg_read(x86.UC_X86_REG_R8) & 0xFF == paused
        _, q_cnt, _, _, _ = read_ctrl()
        assert q_cnt == exp_q

    # ---- Test Site 3: InvAsync (FN_ASY + 0x2D) ----
    for should_unp, paused, multi, eng, exp_paused, exp_was_paused, exp_q, exp_tog in (
        # Already unpaused -> zero Lua query overhead!
        (1, 0, 0, inv, 0, 0xCAFE, 0, 0),
        # Paused in Inventory and should_unp==1 (e.g. combat just started!) -> unpauses and sets m_bWasPaused=1
        (1, 1, 0, inv, 0, 1, 1, 1),
        # Paused in Inventory but should_unp==0 (out of combat) -> stays paused
        (0, 1, 0, inv, 1, 0xCAFE, 1, 0),
        # Multiplayer or not active engine -> skipped without Lua call
        (1, 1, 1, inv, 1, 0xCAFE, 0, 0),
        (1, 1, 0, other_screen, 1, 0xCAFE, 0, 0),
    ):
        reset_state(should_unp, paused, 0, multi=multi, active_eng=eng)
        uc.mem_write(inv + 0x6D8, struct.pack("<i", 42))
        regs = {reg: rng.getrandbits(48) for reg in REGS}
        regs.update({
            x86.UC_X86_REG_RBX: inv,
            x86.UC_X86_REG_RSP: 0x70008000,
        })
        for reg, val in regs.items():
            uc.reg_write(reg, val)
        stopped_at.clear()
        uc.emu_start(base + FN_ASY + 0x2D, 0, count=200)
        assert stopped_at == [base + FN_ASY + 0x35]
        assert uc.reg_read(x86.UC_X86_REG_RAX) & 0xFFFFFFFF == 42
        assert bytes(uc.mem_read(world + 0xBC, 1))[0] == exp_paused
        assert struct.unpack("<I", bytes(uc.mem_read(inv + 0x76C, 4)))[0] == exp_was_paused
        _, q_cnt, tog_cnt, _, _ = read_ctrl()
        assert q_cnt == exp_q and tog_cnt == exp_tog


def test_tp2_parse_checks():
    if WEIDU is None:
        pytest.skip("set WEIDU_BIN to run WeiDU syntax checks")
    for kind, target in (
        ("tp2", "setup-chriz-bg-modpack.tp2"),
        ("tpa", "chriz-bg-modpack/lib/cbm_unpaused_inventory_always.tpa"),
        ("tpa", "chriz-bg-modpack/lib/cbm_unpaused_inventory_combat.tpa"),
    ):
        completed = subprocess.run(
            [str(WEIDU), "--noautoupdate", "--nogame", "--no-exit-pause", "--parse-check", kind, target],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr


def _game_files(root: Path) -> dict[str, bytes]:
    return {k: v for k, v in _file_tree(root).items() if not _is_weidu_artifact(k)}


def _make_game(root: Path, game_type: str, *, eeex: bool) -> SyntheticGame:
    if game_type == "iwdee":
        game = SyntheticGame(root, game="bg2ee", eeex=eeex)
        data_dir = root / "data"
        for f in data_dir.iterdir():
            f.unlink()
        data_dir.rmdir()
        (root / "chitin.key").unlink()
        _write_key_and_bif(root, [("HOWPARTY", "2DA", b"2DA V1.0\r\n*\r\n")])
        return game
    return SyntheticGame(root, game=game_type, eeex=eeex)


def _run_component(game: SyntheticGame, component: int, *, uninstall: bool = False) -> subprocess.CompletedProcess[str]:
    assert WEIDU is not None
    return subprocess.run(
        [
            str(WEIDU),
            SETUP_NAME,
            "--game", str(game.root),
            "--force-uninstall-list" if uninstall else "--force-install-list",
            str(component),
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


@pytest.mark.parametrize("component,cfg_file,expected_log", (
    (699, ALWAYS_CFG, "[CBM unpaused inventory] Installed override/M_CZINVU.lua + CZINVUCF.lua"),
    (700, COMBAT_CFG, "[CBM unpaused inventory] Installed override/M_CZINVU.lua + CZINVUCF.lua"),
))
@pytest.mark.parametrize("game_type", ("bgee", "bg2ee", "eet", "iwdee"))
def test_weidu_install_overwrite_exclusivity_and_uninstall(tmp_path, game_type, component, cfg_file, expected_log):
    if WEIDU is None:
        pytest.skip("set WEIDU_BIN to run WeiDU installer tests")
    shipped_runtime = SOURCE.read_bytes()
    shipped_cfg = cfg_file.read_bytes()
    other = 700 if component == 699 else 699

    # 1. With EEex + preexisting files (We Overwrite), plus mutual exclusion check
    game = _make_game(tmp_path / f"{game_type}-{component}-eeex", game_type, eeex=True)
    (game.override / "m_czinvu.lua").write_bytes(b"-- prior runtime\r\n\xff")
    (game.override / "czinvucf.lua").write_bytes(b"-- prior cfg\r\n\xff")
    game.before = _game_files(game.root)
    result = _run_component(game, component)
    transcript = result.stdout + result.stderr
    assert result.returncode == 0, transcript
    assert expected_log in transcript
    assert re.search(rf"(?m)^~?{SETUP_NAME.upper()}~? #\d+ #{component}\b", game.active_log())
    expected = dict(game.before)
    expected["OVERRIDE/M_CZINVU.LUA"] = shipped_runtime
    expected["OVERRIDE/CZINVUCF.LUA"] = shipped_cfg
    assert _game_files(game.root) == expected

    # Trying to install the mutually exclusive sibling refuses cleanly
    conflict = _run_component(game, other)
    conflict_text = conflict.stdout + conflict.stderr
    assert "SKIPPING" in conflict_text or "Uninstall" in conflict_text, conflict_text
    assert not re.search(rf"(?m)^~?{SETUP_NAME.upper()}~? #\d+ #{other}\b", game.active_log())

    # Uninstall restores prior files byte-for-byte
    uninstalled = _run_component(game, component, uninstall=True)
    assert uninstalled.returncode == 0, uninstalled.stdout + uninstalled.stderr
    assert _game_files(game.root) == game.before

    # 2. Without EEex: succeeds cleanly with inactive notice and writes nothing to override/
    no_eeex = _make_game(tmp_path / f"{game_type}-{component}-noeeex", game_type, eeex=False)
    no_eeex.before = _game_files(no_eeex.root)
    res_no = _run_component(no_eeex, component)
    txt_no = res_no.stdout + res_no.stderr
    assert res_no.returncode == 0, txt_no
    assert "[CBM unpaused inventory] Inactive: EEex (override/M___EEex.lua) was not found." in txt_no
    assert _game_files(no_eeex.root) == no_eeex.before
    un_no = _run_component(no_eeex, component, uninstall=True)
    assert un_no.returncode == 0
    assert _game_files(no_eeex.root) == no_eeex.before
