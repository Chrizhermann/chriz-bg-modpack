"""Use Windows' OS unwinder on inert bridge/native metadata and copied stacks."""
import ctypes
import os
import subprocess
from pathlib import Path

import pytest
from test_scroll_runtime_native import compiler_environment
from test_scroll_runtime_binding import windows, MappedImage
from test_scroll_runtime_detours import action_image, execute, module, SOURCE, PROFILES

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows x64 unwind metadata")


@pytest.fixture(scope="session")
def os_unwinder(tmp_path_factory):
    build = tmp_path_factory.mktemp("scroll-unwind-probe")
    compiler, environment, msvc = compiler_environment()
    assert msvc
    target = build / "scroll_unwind_probe.dll"
    command = [compiler, "/nologo", "/std:c++20", "/EHsc", "/W4", "/WX", "/LD",
               str(SOURCE / "unwind_probe.cpp"), f"/Fe{target}"]
    result = subprocess.run(command, cwd=build, env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    library = ctypes.CDLL(str(target))
    callback = library.ScrollTestUnwind
    callback.argtypes = [ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p,
                         ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64)]
    callback.restype = ctypes.c_uint32
    return callback


@pytest.mark.parametrize("operation", ["copy", "assign", "destroy"])
def test_os_unwinds_every_emitted_instruction_to_native_caller(action_image, windows, os_unwinder, operation):
    pe, sites, _ = action_image
    site = sites[operation]
    profile = next(profile for profile in PROFILES if profile["version"] == site.version)
    image = MappedImage(windows, profile, 0x200000000)
    cave, stack = 0x210000000, 0x20000000
    allocated = []
    try:
        for address in (cave, stack):
            actual = windows.VirtualAlloc(address, 0x10000, 0x3000, 4)
            assert actual == address
            allocated.append(actual)
        emulated_plan = module.emit(site, image_base=pe.OPTIONAL_HEADER.ImageBase, stub=0x150000000,
                                    runtime=1, callback=0x150008000, observed=site.body)
        trace = execute(action_image, site, emulated_plan, lambda *args: 1, capture=True)
        host_plan = module.emit(site, image_base=image.base, stub=cave,
                               runtime=1, callback=cave+0x7000, observed=site.body)
        segments = module.unwind_segments(pe, site, host_plan)
        ctypes.memmove(cave, host_plan["code"], len(host_plan["code"]))
        # The private cave is never executable, and no engine/stub pointer is
        # invoked. RtlVirtualUnwind only reads instructions, records and stacks.
        for point in trace["checkpoints"]:
            offset = point["offset"]
            matches = [(start, end, info) for start, end, info in segments if start <= offset < end]
            assert len(matches) == 1
            start, end, info = matches[0]
            ctypes.memmove(cave+0x8000, info, len(info))
            ctypes.memmove(stack, point["stack"], len(point["stack"]))
            entry = (ctypes.c_uint32 * 3)(cave-image.base+start, cave-image.base+end, cave-image.base+0x8000)
            input_state = (ctypes.c_uint64 * 16)(*point["registers"])
            output_state = (ctypes.c_uint64 * 17)()
            status = os_unwinder(image.base, cave+offset, entry, input_state, output_state)
            assert status == 0, (site.version, operation, hex(offset), hex(status))
            assert output_state[15] == 0x20008010, (site.version, operation, hex(offset), "RSP", hex(output_state[15]))
            assert output_state[16] == 0x2000FF00, (site.version, operation, hex(offset), "RIP", hex(output_state[16]))
            for index in (1, 4, 5, 6, 11, 12, 13, 14):
                assert output_state[index] == 0xCAFE0000+index*0x101, (site.version, operation, hex(offset), index, hex(output_state[index]))
    finally:
        for address in reversed(allocated):
            assert windows.VirtualFree(address, 0, 0x8000)
        image.close()
