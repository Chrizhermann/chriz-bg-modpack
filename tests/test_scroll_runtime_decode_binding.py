"""Certify independent decoder routing in relocated, uninitialized SEC_IMAGE
views. The simulated existing jump/pointer writes are private copy-on-write;
neither mapped image is invoked and the source files are verified unchanged.
"""
import ctypes as C
import json
import struct

import pytest

from test_scroll_runtime_native import SOURCE, native_scroll_build
from test_scroll_runtime_binding import MappedImage, windows  # noqa: F401

PROFILES = json.loads((SOURCE / "decode-profiles.json").read_text())


def eeex_jump(form, previous, entry_address, original):
    """Bytes EEex leaves at the native Unmarshal entry, restoring originals after them.

    "aligned" is the form captured live from 2.7.3.0 with EEex 1.2 (16 bytes:
    FF 25 02 00 00 00, two padding bytes, the 8-byte target).
    """
    if form == "rel32":
        code = b"\xe9"+struct.pack("<i", previous-(entry_address+5))
    else:
        padding = {"aligned": 2, "absolute": 0, "padding7": 7, "padding8": 8}[form]
        code = b"\xff\x25"+struct.pack("<I", padding)+b"\0"*padding+struct.pack("<Q", previous)
    return code+original[len(code):]


class DecodeFunctions(C.Structure):
    _fields_ = [("addresses", C.c_size_t * 3)]


@pytest.fixture(scope="module")
def api(native_scroll_build):
    value = C.CDLL(str(native_scroll_build[1]))
    value.CBMS_BindDecodeModules.argtypes = [C.c_size_t, C.c_size_t, C.POINTER(DecodeFunctions), C.c_void_p, C.c_uint32]
    value.CBMS_BindDecodeModules.restype = C.c_int
    return value


@pytest.fixture(params=PROFILES, ids=lambda p: p["version"]+"-EEex"+p.get("eeex_version","1.3.1"))
def images(windows, request):
    p = request.param
    game = MappedImage(windows, p, 0x400000000)
    dll = None
    try:
        # Game SizeOfImage is ~53MiB: the second mapping must not overlap it.
        dll = MappedImage(windows, {"source":p["eeex_source"], "sha256":p["eeex_sha256"], "preferred_base":0x180000000}, 0x410000000)
        previous = dll.base + p["eeex_override"]["rva"]
        decoder = game.base + p["decoder"]["rva"]
        entry = p["unmarshal_tail"]["rva"]-14
        # This is what EEex initialization establishes in the running process.
        game.write(entry, eeex_jump("aligned", previous, game.base+entry, bytes.fromhex(p["unmarshal_original"])))
        dll.write(p["decode_pointer_rva"], struct.pack("<Q", decoder))
        yield game, dll, p
    finally:
        if dll: dll.close()
        game.close()


def bind(api, game, dll):
    output = DecodeFunctions((C.c_size_t*3)(11,22,33))
    original = bytes(output)
    text = C.create_string_buffer(512)
    result = api.CBMS_BindDecodeModules(game.base, dll.base, C.byref(output), text, len(text))
    return result, output, original, text.value.decode()


@pytest.mark.parametrize("jump", ["aligned", "absolute", "rel32", "padding7"])
def test_binds_existing_eeex_route_without_invocation(api, images, jump):
    game, dll, p = images
    entry = p["unmarshal_tail"]["rva"]-14
    previous = dll.base + p["eeex_override"]["rva"]
    game.write(entry, eeex_jump(jump, previous, game.base+entry, bytes.fromhex(p["unmarshal_original"])))
    before = game.read(entry,22), dll.read(p["eeex_override"]["rva"],p["eeex_override"]["size"])
    ok, output, _, reason = bind(api, game, dll)
    assert ok == 1, reason
    assert list(output.addresses) == [game.base+entry, previous, game.base+p["decoder"]["rva"]]
    assert before == (game.read(entry,22),dll.read(p["eeex_override"]["rva"],p["eeex_override"]["size"]))


@pytest.mark.parametrize("damage", ["native", "eeex_hot", "eeex_cold", "registration", "tail", "after_jump", "rel32_head", "jump", "padding8", "wrong_target", "uninitialized", "pointer", "architecture", "dll_flag", "image_size"])
def test_refuses_changed_or_uninitialized_chain_without_output(api, images, damage):
    game, dll, p = images
    entry = p["unmarshal_tail"]["rva"]-14
    previous = dll.base + p["eeex_override"]["rva"]
    original = bytes.fromhex(p["unmarshal_original"])
    where = {
        "native":(game,p["decoder"]["rva"]), "eeex_hot":(dll,p["eeex_override"]["rva"]),
        "eeex_cold":(dll,p["eeex_override"]["rva"]+0x206), "registration":(dll,p["eeex_registration"]["rva"]),
        # Past every accepted jump form, and the first byte after EEex's 16-byte jump.
        "tail":(game,entry+22), "after_jump":(game,entry+16),
        "jump":(game,entry),
    }
    if damage in where:
        image, rva = where[damage]; image.write(rva, bytes([image.read(rva,1)[0]^1]))
    if damage == "rel32_head":
        # A short jump leaves the rest of the native head in place; it must be original.
        code = bytearray(eeex_jump("rel32", previous, game.base+entry, original)); code[6] ^= 1
        game.write(entry, bytes(code))
    if damage == "padding8":
        game.write(entry, eeex_jump("padding8", previous, game.base+entry, original))
    if damage == "wrong_target":
        # The aligned form keeps its target at entry+8.
        game.write(entry+8,struct.pack("<Q",dll.base+p["eeex_override"]["rva"]+p["eeex_override"]["size"]))
    if damage in ("uninitialized", "pointer"):
        dll.write(p["decode_pointer_rva"],struct.pack("<Q",0 if damage=="uninitialized" else game.base+p["decoder"]["rva"]+1))
    if damage == "architecture": dll.write(dll.nt+4,struct.pack("<H",0x14C))
    if damage == "dll_flag": dll.write(dll.nt+22,struct.pack("<H",dll.u16(dll.nt+22)&~0x2000))
    if damage == "image_size": dll.write(dll.optional+56,struct.pack("<I",0x1000))
    ok, output, original, reason = bind(api, game, dll)
    assert ok == 0 and bytes(output)==original and reason


def test_dll_cannot_select_a_profile_for_another_engine_pair(api,images):
    game,dll,p=images
    # The mapped game is unchanged. Substituting a DLL timestamp from an
    # otherwise supported different engine pairing must never select its ABI.
    other=next(q for q in PROFILES if q['version']!=p['version'])
    dll.write(dll.nt+8,struct.pack('<I',other['eeex_timestamp']))
    ok,output,original,reason=bind(api,game,dll)
    assert ok==0 and bytes(output)==original and 'pair' in reason
