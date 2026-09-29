"""Lua and x64-emulated display checks, without a game process or game files."""
from pathlib import Path

import pytest
from lupa import lua51, luajit21
from keystone import Ks, KS_ARCH_X86, KS_MODE_64
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_PROT_READ
from unicorn import x86_const as x86

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "chriz-bg-modpack/unidentified-items"


def hook_rows():
    rows = []
    for line in (SOURCE / "hooks.2da").read_text().splitlines()[3:]:
        name, pattern, offset, register, field, mapping = line.split()
        rows.append(dict(name=name, pattern=pattern, callOffset=int(offset),
                         itemRegister=register, fieldOffset=int(field), mapOffset=int(mapping)))
    return rows


@pytest.fixture(params=[lua51.LuaRuntime, luajit21.LuaRuntime], ids=["lua51", "luajit21"])
def runtime(request):
    lua = request.param(unpack_returned_tuples=True)
    lua.execute((SOURCE / "cbmid.lua").read_text())
    lua.execute('''
        calls = {allocated=0, freed=0, writes=0, hooks=0, disabled=0, enabled=0}
        memory, labels, patched, strings = {}, {}, {}, {}
        EEex_Active = true
        EEex_HookIntegrityWatchdogRegister = {R8=8}
        EEex_TryLabel = function(name) return labels[name] end
        EEex_ReadU8 = function(addr) assert(memory[addr], "Invalid read"); return memory[addr] end
        EEex_Read32 = function(addr)
            local n = 0
            for i=0,3 do n = n + EEex_ReadU8(addr+i) * 256^i end
            if n >= 2147483648 then n = n - 4294967296 end
            return n
        end
        EEex_Write8 = function(addr, val) calls.writes=calls.writes+1; memory[addr]=val end
        EEex_Malloc = function(size) calls.allocated=calls.allocated+1; allocationSize=size; return 0x300000 end
        EEex_Free = function(ptr) calls.freed=calls.freed+1 end
        EEex_WriteLString = function(ptr, val, size)
            if failWrite then error("simulated allocation population failure") end
            assert(size==8); strings[ptr]=val
        end
        EEex_DisableCodeProtection = function() calls.disabled=calls.disabled+1 end
        EEex_EnableCodeProtection = function() calls.enabled=calls.enabled+1 end
        EEex_HookBeforeCallWithLabels = function(addr, labelPairs, asm)
            calls.hooks=calls.hooks+1
            assert(labelPairs[1][1]=="hook_integrity_watchdog_ignore_registers")
            assert(labelPairs[1][2][1]==8)
            patched[#patched+1] = {addr=addr, asm=asm[1]}
            for i=0,4 do memory[addr+i]=0x90 end
            if failHook == calls.hooks then error("simulated hook failure") end
        end
        config = {schema=1, fallback={inventory="NEUTRAL",ground="SACK",picture=""},
            types={[1]={inventory="AMULET",ground="GAMUL",picture="CAMUL"},
                   [72]={inventory="HAT",ground="GHAT",picture="CHAT"}}, hooks={}}
    ''')
    config = lua.globals().config
    memory = lua.globals().memory
    for index, row in enumerate(hook_rows(), 1):
        config.hooks[index] = lua.table_from(row)
        address = 0x10000 + index * 0x100
        lua.globals().labels["CBMID::" + row["name"]] = address
        prefix = bytes.fromhex(row["pattern"])
        for offset, value in enumerate(prefix):
            memory[address - len(prefix) + offset] = value
        call = b'\xe8' + (0x5000 - address - 5).to_bytes(4, 'little', signed=True)
        for offset, value in enumerate(call):
            memory[address + offset] = value
    return lua


def snapshot(lua):
    return dict(lua.globals().memory.items())


def test_all_hooks_and_process_lifetime_mapping(runtime):
    g = runtime.globals()
    assert g.CBMID.install(g.config) is True
    assert g.calls.hooks == 4
    assert g.calls.disabled == g.calls.enabled == 1
    assert g.strings[0x300000] == 'NEUTRAL\0'
    assert g.strings[0x300000 + 2 * 32] == 'AMULET\0\0'
    assert g.strings[0x300000 + 4 * 32] == 'NEUTRAL\0'
    assert g.strings[0x300000 + 73 * 32] == 'HAT\0\0\0\0\0'
    assert g.strings[0x300000 + 16] == '\0' * 8
    # A UI/script reload must not patch a hook twice or free its data.
    runtime.execute((SOURCE / "cbmid.lua").read_text())
    assert g.CBMID.install(g.config) is False
    assert g.calls.hooks == 4 and g.calls.allocated == 1 and g.calls.freed == 0


@pytest.mark.parametrize('bad', ['missing_label', 'changed_prefix', 'changed_call', 'wrong_target'])
def test_all_sites_validated_before_any_native_write(runtime, bad):
    g = runtime.globals()
    address = g.labels['CBMID::LuaPicture']
    if bad == 'missing_label': g.labels['CBMID::LuaPicture'] = None
    if bad == 'changed_prefix': g.memory[address - 1] = 0
    if bad == 'changed_call': g.memory[address] = 0xE9
    if bad == 'wrong_target': g.memory[address + 1] = (g.memory[address + 1] + 1) % 256
    before = snapshot(runtime)
    with pytest.raises(Exception): g.CBMID.install(g.config)
    assert snapshot(runtime) == before
    assert g.calls.allocated == g.calls.hooks == g.calls.disabled == 0


@pytest.mark.parametrize('failure', [1, 2, 3, 4])
def test_partial_install_rolls_back_every_original_call(runtime, failure):
    g = runtime.globals()
    before = snapshot(runtime)
    g.failHook = failure
    with pytest.raises(Exception, match='simulated hook failure'): g.CBMID.install(g.config)
    assert snapshot(runtime) == before
    assert g.calls.freed == 1 and g.calls.enabled == 1
    assert g.CBMID_State is None


def test_failed_population_frees_buffer_without_changing_code(runtime):
    g = runtime.globals()
    g.failWrite = True
    with pytest.raises(Exception): g.CBMID.install(g.config)
    assert g.calls.freed == 1 and g.calls.disabled == g.calls.hooks == 0


@pytest.mark.parametrize('bad', ['schema', 'resref', 'type', 'duplicate', 'register', 'missing_eeex'])
def test_invalid_configuration_refuses_before_mutation(runtime, bad):
    g = runtime.globals()
    if bad == 'schema': g.config.schema = 2
    if bad == 'resref': g.config.fallback.inventory = 'TOOLONGICON'
    if bad == 'type': g.config.types[65536] = g.config.fallback
    if bad == 'duplicate': g.config.hooks[4] = g.config.hooks[1]
    if bad == 'register': g.config.hooks[4].itemRegister = 'rax'
    if bad == 'missing_eeex': g.EEex_Active = False
    with pytest.raises(Exception): g.CBMID.install(g.config)
    assert g.calls.allocated == g.calls.hooks == g.calls.disabled == 0


@pytest.mark.parametrize('hook', hook_rows(), ids=lambda h: h['name'])
@pytest.mark.parametrize('item_type', [0, 1, 35, 72, 73, 255, 65535])
@pytest.mark.parametrize('flags', [0, 1, 2, 3, 0x80, 0x81, 0xFFFFFFFF])
def test_x64_stub_preserves_everything_except_unidentified_art(hook, item_type, flags):
    # Run the ACTUAL generated assembly, not a Python translation of its logic.
    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    lua.execute((SOURCE / 'cbmid.lua').read_text())
    code, stack, item, header, buffer = 0x100000, 0x200000, 0x300000, 0x400000, 0x123450000
    max_type = 72
    assembly = lua.globals().CBMID.assembly(lua.table_from(hook), buffer, max_type)
    encoded, _ = Ks(KS_ARCH_X86, KS_MODE_64).asm(assembly, addr=code)
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    for address in [code, stack, item, header, buffer]: uc.mem_map(address, 0x1000)
    uc.mem_write(code, bytes(encoded))
    uc.mem_write(item + 0x24, flags.to_bytes(4, 'little'))
    uc.mem_write(header + 0x1C, item_type.to_bytes(2, 'little'))
    # Write protection catches any attempted change to the item/resource/map.
    for address in [item, header, buffer]: uc.mem_protect(address, 0x1000, UC_PROT_READ)
    registers = [getattr(x86, 'UC_X86_REG_' + name) for name in
                 ['RAX', 'RBX', 'RCX', 'RDX', 'RSI', 'RDI', 'RBP', 'RSP',
                  'R8', 'R9', 'R10', 'R11', 'R12', 'R13', 'R14', 'R15', 'EFLAGS']]
    for index, register in enumerate(registers): uc.reg_write(register, 0xF1230000 + index)
    uc.reg_write(x86.UC_X86_REG_RSP, stack + 0x800)
    uc.reg_write(getattr(x86, 'UC_X86_REG_' + hook['itemRegister'].upper()), item)
    uc.reg_write(x86.UC_X86_REG_R8, header + hook['fieldOffset'])
    uc.reg_write(x86.UC_X86_REG_EFLAGS, 0xAD7)
    before = {r: uc.reg_read(r) for r in registers}
    uc.emu_start(code, code + len(encoded))
    after = {r: uc.reg_read(r) for r in registers}
    expected = before.copy()
    if not flags & 1:
        entry = item_type + 1 if item_type <= max_type else 0
        expected[x86.UC_X86_REG_R8] = buffer + entry * 32 + hook['mapOffset']
    assert after == expected
