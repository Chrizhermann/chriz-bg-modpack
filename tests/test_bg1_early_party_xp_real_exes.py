"""Local-only verification of component 695 against installed Steam 2.7.3.0 / ref 2.6.6.0 executables."""
from __future__ import annotations

import os
from pathlib import Path
import struct

import pytest

from tests.bg1_early_party_xp_runtime import BUILDS, Runtime


RUNTIMES = ("lua52", "luajit21")


def _real_pe_image(exe_path: Path) -> tuple[int, bytearray]:
    raw = exe_path.read_bytes()
    pe = struct.unpack_from("<I", raw, 0x3C)[0]
    nsec, optsz = struct.unpack_from("<HH", raw, pe + 6)[0], struct.unpack_from("<H", raw, pe + 20)[0]
    ib = struct.unpack_from("<Q", raw, pe + 24 + 24)[0]
    hdr_sz = struct.unpack_from("<I", raw, pe + 24 + 60)[0]
    sec_off = pe + 24 + optsz
    max_end = hdr_sz
    exec_secs = []
    for i in range(nsec):
        s = sec_off + i * 40
        vsz, srva, rawsz, rawptr = struct.unpack_from("<IIII", raw, s + 8)
        chars = struct.unpack_from("<I", raw, s + 36)[0]
        if chars & 0x20000000:
            max_end = max(max_end, srva + vsz)
            exec_secs.append((vsz, srva, rawsz, rawptr))
    buf = bytearray(max_end)
    buf[:hdr_sz] = raw[:hdr_sz]
    for vsz, srva, rawsz, rawptr in exec_secs:
        n = min(vsz, rawsz)
        buf[srva:srva + n] = raw[rawptr:rawptr + n]
    return ib, buf


def _local_real_exes() -> list[tuple[str, Path]]:
    pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    candidates = [
        ("bgee", pf86 / "Steam/steamapps/common/Baldur's Gate Enhanced Edition/Baldur.exe"),
        ("bg2ee", pf86 / "Steam/steamapps/common/Baldur's Gate II Enhanced Edition/Baldur.exe"),
        ("bg2ee_266", Path(r"C:\Games\Baldur's Gate II Enhanced Edition modded\Baldur.exe")),
    ]
    return [(g, p) for g, p in candidates if p.is_file()]


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("game,exe_path", _local_real_exes() or [("none", Path())])
def test_real_bg_executables_match_and_hook(game, exe_path, runtime):
    if game == "none":
        pytest.skip("local BG executables not present")
    base, buf = _real_pe_image(exe_path)
    _, _, fn_rva = BUILDS[game]
    Runtime(buf, runtime=runtime, base=base, fn=fn_rva).run().assert_active()


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_real_iwdee_executable_is_rejected(runtime):
    pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    iwd_exe = pf86 / "Steam/steamapps/common/Icewind Dale Enhanced Edition/icewind.exe"
    if not iwd_exe.is_file():
        pytest.skip("local IWD:EE executable not present")
    base, buf = _real_pe_image(iwd_exe)
    Runtime(buf, runtime=runtime, base=base).run().assert_inactive("unsupported engine build")
