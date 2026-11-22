"""Offline tests for component 470 (cbm_scroll_learn_fix): Lua, x64 emulation, and WeiDU."""
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

from tests.scroll_learn_runtime import (
    APIS,
    BUILDS,
    CANWRITE,
    CANWRITE_CHECKS,
    GETKITMASK,
    GETKITMASK_CHECKS,
    GETSCHOOL,
    GETSCHOOL_CHECKS,
    ISUSABLE,
    ISUSABLE_CHECKS,
    LEARN,
    LEARN_CHECKS,
    PATTERNS,
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

COMPONENT = 470
RUNTIMES = ("lua52", "luajit21")
REGS = [
    getattr(x86, "UC_X86_REG_" + name)
    for name in (
        "RAX", "RBX", "RCX", "RDX", "RSI", "RDI", "RBP", "RSP",
        "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15",
    )
]
MAGE_CLASSES = {1, 7, 10, 13, 14, 17}


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
@pytest.mark.parametrize(
    "base_off,checks",
    (
        *((LEARN, off) for off in LEARN_CHECKS),
        *((GETKITMASK, off) for off in GETKITMASK_CHECKS),
        *((CANWRITE, off) for off in CANWRITE_CHECKS),
        *((GETSCHOOL, off) for off in GETSCHOOL_CHECKS),
        *((ISUSABLE, off) for off in ISUSABLE_CHECKS),
    ),
)
def test_modified_native_guard_bytes_never_write(base_off, checks, runtime):
    data = fixture()
    data[base_off + checks] ^= 1
    r = Runtime(data, runtime=runtime).run()
    r.assert_inactive("engine layout mismatch")
    assert r.meter[b"near"] == r.meter[b"jit"] == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("pattern_name,pat_off", (
    ("LearnSpell", LEARN),
    ("GetKitMask", GETKITMASK),
    ("CanWriteSpellScroll", CANWRITE),
))
@pytest.mark.parametrize("kind", ("missing", "duplicate", "data_only"))
def test_pattern_search_requires_unique_executable_match(pattern_name, pat_off, kind, runtime):
    data = fixture()
    pat = PATTERNS[pattern_name]
    if kind == "missing":
        data[pat_off] ^= 1
    elif kind == "duplicate":
        data[0x1100:0x1100 + len(pat)] = pat
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
    (SECTION + 8, "I", 0x850, "invalid LearnSpell bounds"),
    (LEARN + 0x32, "i", -0x4000000, "invalid CSpell::GetSchool bounds"),
    (CANWRITE + 0x27, "i", -0x4000000, "invalid CAIObjectType::IsUsableSubClass bounds"),
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
    neg_gs = 0x1400
    for offset, hex_bytes in GETSCHOOL_CHECKS.items():
        b = bytes.fromhex(hex_bytes)
        data[neg_gs + offset:neg_gs + offset + len(b)] = b
    struct.pack_into("<i", data, LEARN + 0x32, neg_gs - (LEARN + 0x36))

    neg_iu = 0x1600
    for offset, hex_bytes in ISUSABLE_CHECKS.items():
        b = bytes.fromhex(hex_bytes)
        data[neg_iu + offset:neg_iu + offset + len(b)] = b
    struct.pack_into("<i", data, CANWRITE + 0x27, neg_iu - (CANWRITE + 0x2B))

    Runtime(data, runtime=runtime).run().assert_active()


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("failure", ("near_throw", "jit_throw", "silent", "partial", "wrong_target"))
def test_failed_preparation_or_patch_preserves_original_bytes(failure, runtime):
    r = Runtime(runtime=runtime, failure=failure, fail_at=1).run()
    r.assert_inactive("inactive; native behavior retained")
    if failure == "near_throw":
        assert r.meter[b"jit"] == r.meter[b"writes"] == 0
        assert r.meter[b"near"] == 1
        assert b"injected near failure" in r.state[b"status"]
    else:
        assert r.meter[b"jit"] == 1
        assert r.meter[b"enable"] == 1


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_aslr_and_binary_nul_chunk_boundaries(runtime):
    data = fixture()
    # Place LearnSpell so its pattern spans a 1024-byte ReadLString boundary.
    new_learn = 0x13F8
    learn_blob = bytes(data[LEARN:LEARN + 0x56])
    data[LEARN:LEARN + 0x56] = b"\xCC" * 0x56
    data[new_learn:new_learn + 0x56] = learn_blob
    struct.pack_into("<i", data, new_learn + 0x32, GETSCHOOL - (new_learn + 0x36))
    Runtime(data, runtime=runtime, base=0x7FF600000000, learn=new_learn).run().assert_active()


def _expected_delta(class_id: int, kit_mask: int, school: int, caster_type: int) -> int:
    if caster_type != 1 or class_id not in MAGE_CLASSES:
        return 0
    spec_bits = kit_mask & 0x3FC0
    if spec_bits == 0:
        return 0
    if 1 <= school <= 8 and (spec_bits & (1 << (school + 5))):
        return 15
    return -15


@pytest.mark.parametrize("base", (0x140000000, 0x7FF600000000))
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_generated_hook_instructions_preserve_native_contract(base, runtime):
    r = Runtime(runtime=runtime, base=base).run()
    r.assert_active()
    assembler = Ks(KS_ARCH_X86, KS_MODE_64)
    emulator = Uc(UC_ARCH_X86, UC_MODE_64)
    emulator.mem_map(base, 0x10000)
    emulator.mem_map(0x60000000, 0x10000)  # synthetic CGameSprite (r14)
    emulator.mem_map(0x61000000, 0x10000)  # synthetic CSpell (rdi)
    emulator.mem_map(0x70000000, 0x10000)  # synthetic stack (rsp)
    emulator.mem_map(0x62000000, 0x10000)  # test harness data slot (kit_mask, school)

    # Install patched bytes + trampoline, plus ABI-hostile stubs for GetKitMask & GetSpellSchool
    # that verify input pointer (rcx), clobber volatile regs, and preserve callee-saved rbx/rbp/r12-r15.
    emulator.mem_write(base, r.image_after())

    at = r.meter[b"targets"][1]
    tramp_blob = bytes(assembler.asm(r.meter[b"assembly"][1].decode(), addr=at)[0])
    emulator.mem_map(at, 0x1000)
    emulator.mem_write(at, tramp_blob)

    stub_gkm = bytes(assembler.asm("""
        cmp rcx, 0x60000000
        jne bad
        mov rax, 0x62000000
        mov eax, dword ptr [rax]
        mov rcx, 0x11111111
        mov rdx, 0x22222222
        mov r8,  0x33333333
        mov r9,  0x44444444
        mov r10, 0x55555555
        mov r11, 0x66666666
        ret
    bad:
        ud2
    """, addr=base + GETKITMASK)[0])
    emulator.mem_write(base + GETKITMASK, stub_gkm)

    stub_gs = bytes(assembler.asm("""
        cmp rcx, 0x61000000
        jne bad
        push rbx
        mov rbx, 0xCAFEBABE
        mov rax, 0x62000004
        movzx eax, byte ptr [rax]
        or eax, 0xDEADBA00
        mov rcx, 0x77777777
        mov rdx, 0x88888888
        mov r8,  0x99999999
        mov r9,  0xAAAAAAAA
        mov r10, 0xBBBBBBBB
        mov r11, 0xCCCCCCCC
        pop rbx
        ret
    bad:
        ud2
    """, addr=base + GETSCHOOL)[0])
    emulator.mem_write(base + GETSCHOOL, stub_gs)

    hook_site = base + LEARN
    resume = base + LEARN + 0x50
    seen = []

    def stop(uc, address, size, user):
        if address == resume:
            seen.append(address)
            uc.emu_stop()

    emulator.hook_add(UC_HOOK_CODE, stop)

    cases: list[tuple[int, int, int, int]] = []
    # 1. All 8 specialist wizard masks across all 6 mage classes x schools 0..10
    for cls in sorted(MAGE_CLASSES):
        for school_idx in range(8):
            mask = 1 << (6 + school_idx)
            for spl_school in range(11):
                cases.append((cls, mask, spl_school, 1))
    # 2. Multi-bit custom specialist (Red Wizard C0REDWIZ = 0x1080)
    for spl_school in range(11):
        cases.append((1, 0x1080, spl_school, 1))
    # 3. Trueclass mage (0x4000), Wild Mage (0x80000000), all Bard kits (class 5, including adversarial spec bits)
    for mask in (0x4000, 0x80000000):
        for spl_school in range(11):
            cases.append((1, mask, spl_school, 1))
    for mask in (0x4000, 0x00200000, 0x00400000, 0x00800000, 0x00000040, 0x00003FC0):
        for spl_school in range(11):
            cases.append((5, mask, spl_school, 1))
    # 4. Kitted dual-class mages (Berserker/Kensai/Swashbuckler/Talos/etc.)
    for cls in (7, 13, 14):
        for mask in (0x00000001, 0x00000004, 0x00004000, 0x00100000, 0x01000000):
            for spl_school in range(11):
                cases.append((cls, mask, spl_school, 1))
    # 5. Non-mage classes with specialist bits (GRIZZLY_BEAR 0xFFFFFFFF, Fighter, Thief, Sorcerer, out-of-range)
    for cls, mask in ((2, 0xFFFFFFFF), (2, 0x40), (4, 0x80), (19, 0x4000), (32, 0x40), (255, 0x3FC0)):
        for spl_school in (0, 1, 2, 8):
            cases.append((cls, mask, spl_school, 1))
    # 6. Non-wizard casterType (0, 2, 3, -1) never receives specialist modifier
    for ct in (0, 2, 3, 0xFFFF):
        for spl_school in (0, 1, 2):
            cases.append((1, 0x40, spl_school, ct))

    rng = random.Random(470)
    preserved = (
        x86.UC_X86_REG_RSI,
        x86.UC_X86_REG_RDI,
        x86.UC_X86_REG_RSP,
        x86.UC_X86_REG_R12,
        x86.UC_X86_REG_R13,
        x86.UC_X86_REG_R14,
        x86.UC_X86_REG_R15,
    )
    for cls, mask, spl_school, caster_type in cases:
        registers = {reg: rng.getrandbits(48) for reg in REGS}
        registers[x86.UC_X86_REG_RAX] = (registers[x86.UC_X86_REG_RAX] & ~0xFFFF) | (caster_type & 0xFFFF)
        registers[x86.UC_X86_REG_R14] = 0x60000000
        registers[x86.UC_X86_REG_RDI] = 0x61000000
        registers[x86.UC_X86_REG_RSP] = 0x70008000
        for reg, number in registers.items():
            emulator.reg_write(reg, number)

        emulator.mem_write(0x60004B5B, bytes([cls]))
        emulator.mem_write(0x62000000, mask.to_bytes(4, "little"))
        emulator.mem_write(0x62000004, bytes([spl_school]))
        base_chance = 85
        emulator.mem_write(0x70008000 + 0x60, struct.pack("<i", base_chance))

        seen.clear()
        emulator.emu_start(hook_site, 0, count=200)
        ctx = (cls, hex(mask), spl_school, caster_type)
        assert seen == [resume], ctx
        for reg in preserved:
            assert emulator.reg_read(reg) == registers[reg], (ctx, reg)
        expected_ebp = caster_type - 0x10000 if (caster_type & 0x8000) else caster_type
        assert emulator.reg_read(x86.UC_X86_REG_RBP) & 0xFFFFFFFF == expected_ebp & 0xFFFFFFFF, ctx
        got_chance = struct.unpack("<i", emulator.mem_read(0x70008000 + 0x60, 4))[0]
        assert got_chance == base_chance + _expected_delta(cls, mask, spl_school, caster_type), ctx


def test_api_audit_covers_every_call_and_capability_check():
    names = set(re.findall(r"\bEEex_\w+", SOURCE.read_text(encoding="utf-8"))) - {"EEex_Active"}
    assert names == set(APIS)


def _game_files(root: Path) -> dict[str, bytes]:
    return {
        name: payload
        for name, payload in _file_tree(root).items()
        if not _is_weidu_artifact(name)
    }


def _make_iwdee_game(root: Path, *, eeex: bool) -> SyntheticGame:
    game = SyntheticGame(root, game="bg2ee", eeex=eeex)
    # Replace CHITIN.KEY/BIFF so GAME_IS ~iwdee~ matches via HOWPARTY.2DA (weidu.md).
    data_dir = root / "data"
    for f in data_dir.iterdir():
        f.unlink()
    data_dir.rmdir()
    (root / "chitin.key").unlink()
    _write_key_and_bif(root, [("HOWPARTY", "2DA", b"2DA V1.0\r\n*\r\n")])
    return game


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
         "chriz-bg-modpack/lib/cbm_scroll_learn_fix.tpa"],
        cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=30,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ERROR" not in output and "WARNING" not in output, output


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
@pytest.mark.parametrize("game_type", ("bgee", "bg2ee", "eet", "iwdee"))
@pytest.mark.parametrize("existing", (None, b"-- standalone quick mod\n", b"hand-edited replacement\0\xff"))
def test_install_reinstall_uninstall_across_engines(tmp_path, game_type, existing):
    game_dir = tmp_path / "game"
    if game_type == "iwdee":
        game = _make_iwdee_game(game_dir, eeex=True)
    else:
        game = SyntheticGame(game_dir, game=game_type, eeex=True)
    if existing is not None:
        (game.override / "m_czsl.lua").write_bytes(existing)
    (game.root / "infinityloader.ini").write_text("[General]\nLuaPatchMode=INTERNAL\n", encoding="ascii")
    before = _game_files(game.root)
    payload = SOURCE.read_bytes()

    for _ in range(2):
        transcript = _run_component(game)
        assert "SUCCESSFULLY INSTALLED" in transcript
        assert re.search(rf"(?m)#0\s+#{COMPONENT}\b", game.active_log())
        expected = dict(before)
        expected["OVERRIDE/M_CZSL.LUA"] = payload
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
    assert transcript.count("[CBM scroll learn fix] Inactive: EEex (override/M___EEex.lua) was not found.") == 1
    assert "SUCCESSFULLY INSTALLED" in transcript
    assert _game_files(game.root) == before

    # Installing EEex later and reinstalling 470 installs M_CZSL.lua cleanly.
    (game.override / "m___eeex.lua").write_bytes(b"-- EEex installed later\n")
    transcript = _run_component(game)
    assert "SUCCESSFULLY INSTALLED" in transcript
    assert _game_files(game.root)["OVERRIDE/M_CZSL.LUA"] == SOURCE.read_bytes()

    transcript = _run_component(game, uninstall=True)
    assert "SUCCESSFULLY REMOVED" in transcript
    after_uninstall = _game_files(game.root)
    assert "OVERRIDE/M_CZSL.LUA" not in after_uninstall
    assert after_uninstall["OVERRIDE/M___EEEX.LUA"] == b"-- EEex installed later\n"
