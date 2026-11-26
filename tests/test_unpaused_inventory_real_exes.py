"""Local-only verification of components 699/700 against installed 2.7.3.0 executables."""
from __future__ import annotations

import os
from pathlib import Path
import struct

import pefile
import pytest

from tests.unpaused_inventory_runtime import PAT_ACT, PAT_ASY, PAT_TOG, Runtime


RUNTIMES = ("lua52", "luajit21")


def _real_pe_image(exe_path: Path) -> tuple[int, bytearray, int, int, int, int]:
    pe = pefile.PE(str(exe_path), fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    header_size = pe.OPTIONAL_HEADER.SizeOfHeaders
    max_end = header_size
    exec_secs = []
    text_sec = None
    for sec in pe.sections:
        if sec.Characteristics & 0x20000000:
            end = sec.VirtualAddress + sec.Misc_VirtualSize
            max_end = max(max_end, end)
            exec_secs.append(sec)
            if sec.Name.rstrip(b"\0") == b".text":
                text_sec = sec
    raw_file = exe_path.read_bytes()
    buf = bytearray(max_end)
    buf[:header_size] = raw_file[:header_size]
    for sec in exec_secs:
        data = sec.get_data()
        n = min(len(data), sec.Misc_VirtualSize)
        buf[sec.VirtualAddress:sec.VirtualAddress + n] = data[:n]

    assert text_sec is not None
    tdata = text_sec.get_data()
    tva = text_sec.VirtualAddress
    ha = tdata.index(PAT_ACT)
    ht = tdata.index(PAT_TOG)
    hs = tdata.index(PAT_ASY)
    act_rva = tva + ha - 0x29
    tog_rva = tva + ht - 0x47
    asy_rva = tva + hs - 0x2D
    p_chitin_rva = act_rva + 0x29 + struct.unpack_from("<i", tdata, (ha - 0x29) + 0x25)[0]
    return ib, buf, act_rva, tog_rva, asy_rva, p_chitin_rva


def _local_real_exes() -> list[tuple[str, Path]]:
    pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    cebg = Path.home() / "CEBG-Tests"
    candidates = [
        ("bgee", pf86 / "Steam/steamapps/common/Baldur's Gate Enhanced Edition/Baldur.exe"),
        ("bgee_lab", cebg / "Magic-Lab-20261104/eet/bg1/Baldur.exe"),
        ("bg2ee", pf86 / "Steam/steamapps/common/Baldur's Gate II Enhanced Edition/Baldur.exe"),
        ("bg2ee_lab", cebg / "Magic-Lab-20261104/bg2ee/Baldur.exe"),
        ("iwdee", pf86 / "Steam/steamapps/common/Icewind Dale Enhanced Edition/icewind.exe"),
    ]
    return [(g, p) for g, p in candidates if p.is_file()]


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("game,exe_path", _local_real_exes() or [("none", Path())])
def test_real_2730_executables_match_and_hook(game, exe_path, runtime):
    if game == "none":
        pytest.skip("local 2.7.3.0 executables not present")
    base, buf, act_rva, tog_rva, asy_rva, p_chitin_rva = _real_pe_image(exe_path)
    Runtime(
        buf,
        runtime=runtime,
        base=base,
        act_rva=act_rva,
        tog_rva=tog_rva,
        asy_rva=asy_rva,
        p_chitin_rva=p_chitin_rva,
    ).run().assert_active()
