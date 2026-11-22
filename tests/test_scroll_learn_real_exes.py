"""Local-only verification of component 470 against installed Steam 2.7.3.0 executables."""
from __future__ import annotations

import os
from pathlib import Path

import pefile
import pytest

from tests.scroll_learn_runtime import BUILDS, Runtime


RUNTIMES = ("lua52", "luajit21")


def _real_pe_image(exe_path: Path) -> tuple[int, bytearray]:
    pe = pefile.PE(str(exe_path), fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    header_size = pe.OPTIONAL_HEADER.SizeOfHeaders
    max_end = header_size
    exec_secs = []
    for sec in pe.sections:
        if sec.Characteristics & 0x20000000:
            end = sec.VirtualAddress + sec.Misc_VirtualSize
            max_end = max(max_end, end)
            exec_secs.append(sec)
    raw_file = exe_path.read_bytes()
    buf = bytearray(max_end)
    buf[:header_size] = raw_file[:header_size]
    for sec in exec_secs:
        data = sec.get_data()
        n = min(len(data), sec.Misc_VirtualSize)
        buf[sec.VirtualAddress:sec.VirtualAddress + n] = data[:n]
    return ib, buf


def _local_real_exes() -> list[tuple[str, Path]]:
    pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    candidates = [
        ("bgee", pf86 / "Steam/steamapps/common/Baldur's Gate Enhanced Edition/Baldur.exe"),
        ("bg2ee", pf86 / "Steam/steamapps/common/Baldur's Gate II Enhanced Edition/Baldur.exe"),
        ("iwdee", pf86 / "Steam/steamapps/common/Icewind Dale Enhanced Edition/icewind.exe"),
    ]
    return [(g, p) for g, p in candidates if p.is_file()]


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("game,exe_path", _local_real_exes() or [("none", Path())])
def test_real_2730_executables_match_and_hook(game, exe_path, runtime):
    if game == "none":
        pytest.skip("local Steam 2.7.3.0 executables not present")
    base, buf = _real_pe_image(exe_path)
    _, _, learn_rva, _, _ = BUILDS[game]
    Runtime(buf, runtime=runtime, base=base, learn=learn_rva).run().assert_active()
