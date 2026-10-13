"""Execute emitted action detours + pinned native instructions in Unicorn only."""
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import struct

import pytest
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn import x86_const as x

from test_scroll_runtime_native import native_api, native_scroll_build

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/scroll-runtime"
spec = importlib.util.spec_from_file_location("action_detours", SOURCE / "action_detours.py")
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)
PROFILES = json.loads((SOURCE / "binder-profiles.json").read_text())
GPRS = [getattr(x, "UC_X86_REG_" + name) for name in
        ("RAX", "RBX", "RCX", "RDX", "RBP", "RSI", "RDI", "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15")]
VOLATILE = [getattr(x, "UC_X86_REG_" + name) for name in ("RAX", "RCX", "RDX", "R8", "R9", "R10", "R11")]
XMMS = [getattr(x, f"UC_X86_REG_XMM{i}") for i in range(16)]


@pytest.fixture(params=PROFILES, ids=lambda value: value["version"])
def action_image(request):
    profile = request.param
    executable = Path(os.path.expandvars(profile["source"]))
    if not executable.is_file():
        pytest.skip("offline action detour proof requires unbundled pinned executable")
    symbols = Path(f"C:/tmp/scroll-hook-research-20261009/EEex/EEex/loader/v{profile['version']}/bg2ee/function_names.db")
    pe, sites = module.audited_sites(executable, symbols)
    names = {int(at, 16): name for line in symbols.read_text().splitlines()
             for at, _, name in [line.partition("\t")] if at.startswith("0x")}
    return pe, {site.operation: site for site in sites}, names


def execute(image, site, plan=None, event=None, self_assignment=False, capture=False):
    pe, _, names = image
    base = pe.OPTIONAL_HEADER.ImageBase
    mapped = pe.get_memory_mapped_image()
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    uc.mem_map(base, (len(mapped) + 0xFFF) & ~0xFFF)
    uc.mem_write(base, mapped)
    stack, data, bridge = 0x20000000, 0x30000000, 0x150000000
    uc.mem_map(stack, 0x10000)
    uc.mem_map(data, 0x10000)
    uc.mem_map(bridge, 0x10000)
    source, destination = data + 0x100, data + 0x300
    if self_assignment:
        destination = source
    uc.mem_write(data, bytes((i * 31 + 17) % 256 for i in range(0x10000)))
    for index, register in enumerate(GPRS):
        uc.reg_write(register, 0xCAFE0000 + index * 0x101)
    for index, register in enumerate(XMMS):
        uc.reg_write(register, 0x123456789ABCDEF123456789ABCDEF + index)
    rsp, stop = stack + 0x8008, stack + 0xFF00
    uc.reg_write(x.UC_X86_REG_RSP, rsp)
    uc.reg_write(x.UC_X86_REG_RCX, destination)
    uc.reg_write(x.UC_X86_REG_RDX, source)
    uc.reg_write(x.UC_X86_REG_EFLAGS, 0x246)
    uc.mem_write(rsp, struct.pack("<Q", stop))
    if plan:
        assert plan["stub"] == bridge
        uc.mem_write(plan["site"], plan["patch"])
        uc.mem_write(bridge, plan["code"])
    native_calls, events = [], []
    checkpoints = []

    def return_to_caller():
        current = uc.reg_read(x.UC_X86_REG_RSP)
        target = struct.unpack("<Q", bytes(uc.mem_read(current, 8)))[0]
        uc.reg_write(x.UC_X86_REG_RSP, current + 8)
        uc.reg_write(x.UC_X86_REG_RIP, target)

    def on_instruction(_, address, size, __):
        if capture and plan and bridge <= address < bridge + len(plan["code"]):
            checkpoints.append({"offset": address-bridge, "registers": [uc.reg_read(r) for r in GPRS + [x.UC_X86_REG_RSP]],
                                "stack": bytes(uc.mem_read(stack, 0x10000))})
        if plan and address == plan["callback"]:
            current = uc.reg_read(x.UC_X86_REG_RSP)
            assert current % 16 == 8  # call-pushed return + correctly aligned caller
            # Shadow space is writable and does not overlap saved SIMD/GPRs.
            uc.mem_write(current + 8, b"SHADOW!!" * 4)
            args = tuple(uc.reg_read(register) for register in
                         (x.UC_X86_REG_RCX, x.UC_X86_REG_RDX, x.UC_X86_REG_R8, x.UC_X86_REG_R9))
            events.append((args, len(native_calls)))
            assert event(*args) == 1
            for register in VOLATILE:
                uc.reg_write(register, 0xD00D001122334455)
            for register in XMMS[:6]:
                uc.reg_write(register, (1 << 128) - 17)
            uc.reg_write(x.UC_X86_REG_EFLAGS, 0x202)
            return_to_caller()
            return
        name = names.get(address)
        if name not in ("CAIObjectType::Set", "CString::CString", "CString::operator=", "CString::~CString"):
            return
        rcx, rdx = uc.reg_read(x.UC_X86_REG_RCX), uc.reg_read(x.UC_X86_REG_RDX)
        if name == "CString::~CString":
            uc.mem_write(rcx, b"\0" * 8)
        else:
            count = 24 if name == "CAIObjectType::Set" else 8
            uc.mem_write(rcx, bytes(uc.mem_read(rdx, count)))
        native_calls.append((name, rcx, rdx))
        uc.reg_write(x.UC_X86_REG_RAX, rcx)
        return_to_caller()

    uc.hook_add(UC_HOOK_CODE, on_instruction)
    uc.emu_start(site.function, stop, count=3000)
    assert uc.reg_read(x.UC_X86_REG_RIP) == stop
    return {"registers": [uc.reg_read(register) for register in GPRS + XMMS + [x.UC_X86_REG_RSP, x.UC_X86_REG_EFLAGS]],
            "data": bytes(uc.mem_read(data, 0x10000)), "calls": native_calls, "events": events,
            "source": source, "destination": destination, "checkpoints": checkpoints}


@pytest.mark.parametrize("operation", ["copy", "assign", "destroy", "self_assign"])
@pytest.mark.parametrize("owned", [False, True], ids=["unowned", "owned"])
def test_actual_action_bridge_registers_stack_copy_and_lifetime(action_image, native_api, operation, owned):
    api, resolver_type, reporter_type = native_api
    api.CBMS_ActionCopied.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint32]
    api.CBMS_ActionCopied.restype = ctypes.c_int
    api.CBMS_ActionBeforeDestroy.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    api.CBMS_ActionBeforeDestroy.restype = ctypes.c_int
    errors = []

    @resolver_type
    def resolve(reader, generation, spell, spell_type, output, user):
        assert reader == 0x9000
        output.contents.count = 1
        output.contents.level[0] = 12
        output.contents.active[0] = 1
        return 1

    @reporter_type
    def report(message, user): errors.append(message.decode())

    runtime = api.CBMS_Create(resolve, report, None)
    assert runtime
    name = "assign" if operation == "self_assign" else operation
    site = action_image[1][name]
    baseline = execute(action_image, site, self_assignment=operation == "self_assign")
    source, destination = baseline["source"], baseline["destination"]
    # Source ownership uses the already compiled original-item/dispatcher API.
    assert api.CBMS_Construct(runtime, 0, 0x9000) == 1
    assert api.CBMS_Construct(runtime, 1, 0x9001) == 1
    use = ctypes.c_uint64()
    assert api.CBMS_ItemBegin(runtime, 0x9000, b"SCROLL", 2, 0, ctypes.byref(use)) == 1
    assert api.CBMS_ItemChild(runtime, use, 0x9001, 4) == 1
    assert api.CBMS_ItemEnd(runtime, use) == 1
    if owned:
        owner = destination if name == "destroy" else source
        assert api.CBMS_Construct(runtime, 3, owner) == 1
        assert api.CBMS_Dispatch(runtime, 0x9001, 146, 0, 0, 3, owner) == 1
    elif operation == "assign":
        # Incoming unowned assignment must clear the reusable action's old use.
        assert api.CBMS_Construct(runtime, 3, destination) == 1
        assert api.CBMS_Dispatch(runtime, 0x9001, 146, 0, 0, 3, destination) == 1
    callback = 0x150008000
    plan = module.emit(site, image_base=action_image[0].OPTIONAL_HEADER.ImageBase,
                       stub=0x150000000, runtime=runtime, callback=callback, observed=site.body)

    def event(actual_runtime, first, second, construction):
        assert actual_runtime == runtime
        if name == "destroy":
            assert first == destination
            return api.CBMS_ActionBeforeDestroy(runtime, first)
        assert first == source and second == destination and construction == (name == "copy")
        return api.CBMS_ActionCopied(runtime, first, second, construction)

    try:
        hooked = execute(action_image, site, plan, event, self_assignment=operation == "self_assign")
        assert hooked["registers"] == baseline["registers"]
        assert hooked["data"] == baseline["data"]
        assert hooked["calls"] == baseline["calls"]
        assert len(hooked["events"]) == 1
        assert hooked["events"][0][1] == (0 if name == "destroy" else len(baseline["calls"]))
        frame, level = ctypes.c_uint64(), ctypes.c_uint32(99)
        result = api.CBMS_BeginCast(runtime, 3, destination, 3, 0xD000, b"CHILD", 0,
                                    10, 20, 30, 40, ctypes.byref(frame))
        if name == "destroy":
            assert result == -1 and "construction registration" in errors[-1]
        else:
            assert result == 1
            assert api.CBMS_Select(runtime, frame, 3, 0xD000, ctypes.byref(level)) == int(owned)
            assert level.value == (6 if owned else 99)
            assert api.CBMS_EndCast(runtime, frame) == 1
            assert errors == []
    finally:
        for address in {source, destination}:
            assert api.CBMS_ActionBeforeDestroy(runtime, address) == 1
        assert api.CBMS_Destruct(runtime, 1, 0x9001) == 1
        assert api.CBMS_Destroy(runtime) == 1


def test_action_emitter_refuses_changed_native_code_and_far_stub(action_image):
    for site in action_image[1].values():
        args = dict(image_base=action_image[0].OPTIONAL_HEADER.ImageBase, stub=0x150000000,
                    runtime=1, callback=2, observed=site.body)
        with pytest.raises(ValueError, match="native function changed"):
            module.emit(site, **{**args, "observed": site.body[:-1] + bytes([site.body[-1] ^ 1])})
        with pytest.raises(ValueError, match="rel32"):
            module.emit(site, **{**args, "stub": 0x9000000000})
