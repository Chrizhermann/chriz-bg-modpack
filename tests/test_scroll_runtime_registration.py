"""Register actual bridge UNWIND_INFO with Windows, without running the bridges."""
import ctypes
import importlib.util
import os
import sys
from dataclasses import replace

import pytest
from test_scroll_runtime_binding import windows
from test_scroll_runtime_detours import action_image, module, SOURCE

spec = importlib.util.spec_from_file_location("action_loader", SOURCE / "action_loader.py")
loader = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = loader
spec.loader.exec_module(loader)
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows native function tables")


def make_package(action_image, base):
    pe, sites, _ = action_image
    entries = []
    for i, operation in enumerate(("copy", "assign", "destroy")):
        site = sites[operation]
        plan = module.emit(site, image_base=pe.OPTIONAL_HEADER.ImageBase, stub=base + i * 0x1000,
                           runtime=1, callback=base + 0xF000, observed=site.body)
        entries.append((plan, module.unwind_segments(pe, site, plan)))
    return loader.bundle(base, entries)


def test_real_windows_registration_lookup_and_release(action_image, windows):
    base = windows.VirtualAlloc(0x150000000, 0x10000, 0x3000, 4)
    assert base == 0x150000000
    registered = None
    try:
        package = make_package(action_image, base)
        ctypes.memmove(base, package.payload, len(package.payload))
        old = ctypes.c_uint32()
        assert windows.VirtualProtect(base, 0x10000, 2, ctypes.byref(old))  # PAGE_READONLY, never executable
        registered = loader.RegisteredUnwind(package)
        for i, (start, stop, info) in enumerate(package.ranges):
            for offset in (start, stop - 1):
                actual_base = ctypes.c_uint64()
                entry = registered.api.RtlLookupFunctionEntry(base + offset, ctypes.byref(actual_base), None)
                assert entry == base + package.table_offset + i * 12
                assert actual_base.value == base
                assert tuple((ctypes.c_uint32 * 3).from_address(entry)) == (start, stop, info)
        with pytest.raises(ValueError, match="already registered"):
            loader.RegisteredUnwind(package)
        registered.close()
        for start, _, _ in package.ranges:
            image = ctypes.c_uint64()
            assert not registered.api.RtlLookupFunctionEntry(base + start, ctypes.byref(image), None)
        registered.close()  # stable cleanup
    finally:
        if registered:
            registered.close()
        assert windows.VirtualFree(base, 0, 0x8000)


def test_changed_or_unmapped_bundle_refuses_before_registration(action_image, windows):
    package = make_package(action_image, 0x150000000)
    with pytest.raises(ValueError, match="table bounds"):
        loader.RegisteredUnwind(replace(package, count=package.count + 1))
    with pytest.raises(ValueError, match="readable|unmapped"):
        loader.RegisteredUnwind(package)
    base = windows.VirtualAlloc(package.base, 0x10000, 0x3000, 4)
    assert base == package.base
    try:
        ctypes.memmove(base, package.payload, len(package.payload))
        ctypes.c_ubyte.from_address(base + 2).value ^= 1
        with pytest.raises(ValueError, match="differs"):
            loader.RegisteredUnwind(package)
        assert base not in loader.RegisteredUnwind.active
    finally:
        assert windows.VirtualFree(base, 0, 0x8000)
