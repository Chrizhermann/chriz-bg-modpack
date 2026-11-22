"""Offline tests for component 690 (cbm_fast_traps): Lua, x64 emulation, and WeiDU."""
from __future__ import annotations

import random
import re
import shutil
import struct
import subprocess
from pathlib import Path

from keystone import KS_ARCH_X86, KS_MODE_64, Ks
import pytest
from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_64, Uc
import unicorn.x86_const as x86

from tests.fast_traps_runtime import (
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

COMPONENT = 690
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
        data[FN + 0x23] ^= 1
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
    (SECTION + 8, "I", 0x1000, "invalid function bounds"),
    (FN + 0xF2E, "i", -0x4000000, "invalid door type address"),
    (0x4100, "B", 0, "unexpected door type"),
))
def test_unsupported_engine_is_inactive(offset, fmt, value, reason, runtime):
    data = fixture()
    struct.pack_into("<" + fmt, data, offset, value)
    r = Runtime(data, runtime=runtime).run()
    r.assert_inactive(reason)
    assert r.meter[b"near"] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_negative_rip_displacement(runtime):
    data = fixture()
    data[0x600] = 33
    struct.pack_into("<i", data, FN + 0xF2E, 0x600 - (FN + 0xF32))
    Runtime(data, runtime=runtime).run().assert_active()


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("failure", ("near_throw", "jit_throw", "silent", "partial", "wrong_target"))
@pytest.mark.parametrize("fail_at", (1, 2, 3))
def test_failed_preparation_or_patch_preserves_original_bytes(failure, fail_at, runtime):
    r = Runtime(runtime=runtime, failure=failure, fail_at=fail_at).run()
    r.assert_inactive("inactive; native behavior retained")
    if failure == "near_throw":
        assert r.meter[b"jit"] == r.meter[b"writes"] == 0
        assert r.meter[b"near"] == fail_at
        assert b"injected near failure" in r.state[b"status"]
    else:
        assert r.meter[b"jit"] == fail_at
        assert r.meter[b"enable"] == 1


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_aslr_and_binary_nul_chunk_boundaries(runtime):
    data = fixture()
    # Move the function so its search pattern crosses the reader's 1024-byte
    # chunks; surrounding zero and high-bit bytes exercise the native reader.
    new_fn = 0x13D0
    function = bytes(data[FN:FN + 0x1E20])
    data[0x1000:0x4000] = b"\xCC" * 0x3000
    data[new_fn:new_fn + len(function)] = function
    struct.pack_into("<i", data, new_fn + 0xF2E, 0x4100 - (new_fn + 0xF32))
    Runtime(data, runtime=runtime, base=0x7FF600000000, fn=new_fn).run().assert_active()


@pytest.mark.parametrize("base", (0x140000000, 0x7FF600000000))
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_generated_hook_instructions_preserve_native_contract(base, runtime):
    r = Runtime(runtime=runtime, base=base).run()
    r.assert_active()
    assembler = Ks(KS_ARCH_X86, KS_MODE_64)
    emulator = Uc(UC_ARCH_X86, UC_MODE_64)
    emulator.mem_map(base, 0x10000)
    emulator.mem_map(0x60000000, 0x10000)  # synthetic sprite
    emulator.mem_map(0x70000000, 0x10000)  # synthetic stack
    # Install the exact rel32 hooks verified by the runtime test, then execute
    # through those bytes rather than jumping directly into each trampoline.
    emulator.mem_write(base, r.image_after())
    for i in range(1, 4):
        at = r.meter[b"targets"][i]
        assembly = r.meter[b"assembly"][i].decode()
        blob = bytes(assembler.asm(assembly, addr=at)[0])
        emulator.mem_map(at, 0x1000)
        emulator.mem_write(at, blob)
    fn = base + FN
    destinations = {fn + offset for offset in (0x16FB, 0xF32, 0x308, 0x122, 0x5E, 0x64, 0x1DFB)}
    seen = []

    def stop(uc, address, size, user):
        if address in destinations:
            seen.append(address)
            uc.emu_stop()

    emulator.hook_add(UC_HOOK_CODE, stop)
    rng = random.Random(400)
    cases = 0
    phases = [(c, i) for c in range(301) for i in (0, 1, 15, 99, 100, 101, 0xFFFFFFFF)]
    phases += [(0xFFFFFFFF, 0xFFFFFFFF), (0xFFFFFFFF, 0), (0x80000000, 1)]
    for counter, actor_id in phases:
        native = counter % 100 == actor_id % 100
        fast = counter % 15 == actor_id % 15
        for which, values, site in (
            ("gate", range(6), 0x58), ("secret", (0, 1), 0x11C),
            ("filter", (0x11, 0x21, 0x31, 0x41, 0, 255), 0xF2C),
        ):
            for value in values:
                registers = {reg: rng.getrandbits(48) for reg in REGS}
                registers.update({x86.UC_X86_REG_RSI: 0x60000000, x86.UC_X86_REG_RSP: 0x70008000})
                if which == "filter":
                    registers[x86.UC_X86_REG_RAX] = (registers[x86.UC_X86_REG_RAX] & ~255) | value
                for reg, number in registers.items():
                    emulator.reg_write(reg, number)
                emulator.mem_write(0x600003A4, counter.to_bytes(4, "little"))
                emulator.mem_write(0x60000048, actor_id.to_bytes(4, "little"))
                emulator.mem_write(0x60003A29, bytes([value if which == "gate" else 2]))
                zero = native if which == "gate" else bool(value) if which == "secret" else False
                emulator.reg_write(x86.UC_X86_REG_EFLAGS, 0x202 | (0x40 if zero else 0))
                seen.clear()
                emulator.emu_start(fn + site, 0, count=150)
                if which == "gate":
                    expected = fn + (0x5E if native else 0x64 if value == 2 and fast else 0x1DFB)
                elif which == "secret":
                    expected = fn + (0x308 if value or not native else 0x122)
                else:
                    due = fast if value in (0x11, 0x21, 0x41) else native
                    expected = fn + (0xF32 if due else 0x16FB)
                context = (which, counter, actor_id, value)
                assert seen == [expected], context
                assert all(emulator.reg_read(reg) == number for reg, number in registers.items()), context
                if which == "filter" and expected == fn + 0xF32:
                    flags = emulator.reg_read(x86.UC_X86_REG_EFLAGS)
                    assert bool(flags & 0x40) == (value == 0x21), context
                    assert bool(flags & 1) == (value < 0x21), context
                cases += 1
    assert cases == 29540  # 118,160 cases across the four parameter sets


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
         "chriz-bg-modpack/lib/cbm_fast_traps.tpa"],
        cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=30,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ERROR" not in output and "WARNING" not in output, output


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
@pytest.mark.parametrize("game_type", ("bgee", "bg2ee", "eet"))
@pytest.mark.parametrize("existing", (None, b"-- standalone quick mod\n", b"hand-edited replacement\0\xff"))
def test_install_reinstall_uninstall_across_engines(tmp_path, game_type, existing):
    game = SyntheticGame(tmp_path / "game", game=game_type, eeex=True)
    if existing is not None:
        (game.override / "m_czft.lua").write_bytes(existing)
    (game.root / "infinityloader.ini").write_text("[General]\nLuaPatchMode=INTERNAL\n", encoding="ascii")
    before = _game_files(game.root)
    payload = SOURCE.read_bytes()

    for _ in range(2):
        transcript = _run_component(game)
        assert "SUCCESSFULLY INSTALLED" in transcript
        assert re.search(rf"(?m)#0\s+#{COMPONENT}\b", game.active_log())
        expected = dict(before)
        expected["OVERRIDE/M_CZFT.LUA"] = payload
        assert _game_files(game.root) == expected

    transcript = _run_component(game, uninstall=True)
    assert "SUCCESSFULLY REMOVED" in transcript
    assert not re.search(rf"(?m)#0\s+#{COMPONENT}\b", game.active_log())
    assert _game_files(game.root) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
def test_missing_eeex_logs_inactive_and_enables_on_reinstall(tmp_path):
    game = SyntheticGame(tmp_path / "game", game="bg2ee", eeex=False)
    before = _game_files(game.root)

    transcript = _run_component(game)
    assert transcript.count("[CBM fast traps] Inactive: EEex (override/M___EEex.lua) was not found.") == 1
    assert "SUCCESSFULLY INSTALLED" in transcript
    assert _game_files(game.root) == before

    # Installing EEex later and reinstalling 690 installs M_CZFT.lua cleanly.
    (game.override / "m___eeex.lua").write_bytes(b"-- EEex installed later\n")
    transcript = _run_component(game)
    assert "SUCCESSFULLY INSTALLED" in transcript
    assert _game_files(game.root)["OVERRIDE/M_CZFT.LUA"] == SOURCE.read_bytes()

    transcript = _run_component(game, uninstall=True)
    assert "SUCCESSFULLY REMOVED" in transcript
    after_uninstall = _game_files(game.root)
    assert "OVERRIDE/M_CZFT.LUA" not in after_uninstall
    assert after_uninstall["OVERRIDE/M___EEEX.LUA"] == b"-- EEex installed later\n"
