"""Read-only Marshal ABI binding; existing routes simulated on private image COW pages."""
import ctypes as C
import json
import struct

import pytest
from test_scroll_runtime_native import SOURCE,native_scroll_build
from test_scroll_runtime_binding import mapped,windows

PROFILES=json.loads((SOURCE/"marshal-profiles.json").read_text())


@pytest.fixture(scope="module")
def api(native_scroll_build):
    dll=C.CDLL(str(native_scroll_build[1]))
    dll.CBMS_BindMarshalModule.argtypes=[C.c_size_t,C.POINTER(C.c_size_t),C.c_void_p,C.c_uint32]
    dll.CBMS_BindMarshalModule.restype=C.c_int
    return dll


def call(api,image):
    output=C.c_size_t(0xcafed00d);reason=C.create_string_buffer(512)
    result=api.CBMS_BindMarshalModule(image.base,C.byref(output),reason,len(reason))
    return result,output.value,reason.value


@pytest.mark.parametrize("damage",[None,"filter","writer","prefix","no_routes","bad_padding","inside","not_code"])
def test_bind_marshal_preserves_eeex_sites_and_refuses_changed_native_abi(api,mapped,damage):
    p=next(p for p in PROFILES if p['version']==mapped.profile['version'])
    # Jump targets only need code-page validation here. They are NOT invoked or
    # claimed to be initialized EEex JIT functions in these read-only fixtures.
    target=mapped.base+p['rva']+0x1000
    for rva,size in [(p['branch_rva'],6),(p['call_rva'],5)]:
        mapped.write(rva,b'\xe9'+struct.pack('<i',target-(mapped.base+rva+5))+b'\x90'*(size-5))
    if damage in ('filter','writer','prefix'):
        rva=p['rva']+{'prefix':0,'filter':0x260,'writer':0x300}[damage]
        mapped.write(rva,bytes([mapped.read(rva,1)[0]^1]))
    if damage=='no_routes':mapped.write(p['branch_rva'],bytes.fromhex(p['branch']))
    if damage=='bad_padding':mapped.write(p['branch_rva']+5,b'\xcc')
    if damage in ('inside','not_code'):
        to=mapped.base+p['rva']+0x200 if damage=='inside' else mapped.base+0x100
        mapped.write(p['branch_rva'],b'\xe9'+struct.pack('<i',to-(mapped.base+p['branch_rva']+5))+b'\x90')
    before=mapped.read(p['rva'],0x3a0)
    result,output,reason=call(api,mapped)
    assert mapped.read(p['rva'],0x3a0)==before
    if damage:
        assert result==0 and output==0xcafed00d and reason
    else:
        assert result==1 and output==mapped.base+p['rva']
        assert b'host-owned' in reason
