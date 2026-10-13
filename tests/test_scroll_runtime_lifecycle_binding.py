"""Certify actual shipped callback registrations without executing either mapped image."""
import ctypes as C
import json
import pytest
from test_scroll_runtime_decode_binding import images
from test_scroll_runtime_native import SOURCE,native_scroll_build
from test_scroll_runtime_binding import windows


@pytest.fixture(scope='module')
def api(native_scroll_build):
    value=C.CDLL(str(native_scroll_build[1]))
    value.CBMS_BindLifecycleModules.argtypes=[C.c_size_t,C.c_size_t,C.c_void_p,C.c_void_p,C.c_uint32]
    value.CBMS_BindLifecycleModules.restype=C.c_int
    return value


@pytest.mark.parametrize('damage',[None,'body0','body1','body2','registration0','registration1','registration2'])
def test_callback_body_and_actual_registration_binding(api,images,damage):
    game,dll,decode=images
    profiles=json.loads((SOURCE/'lifecycle-profiles.json').read_text())
    profile=next(p for p in profiles if p['timestamp']==decode['eeex_timestamp'])
    if damage:
        field,index=damage[:-1],int(damage[-1])
        # Registration damage is the actual function-pointer LEA, including1.2.
        at=profile['entries'][index][field]['rva']+(0x11 if field=='registration' else 0)
        dll.write(at,bytes([dll.read(at,1)[0]^1]))
    output=(C.c_size_t*3)(11,22,33);before=bytes(output);reason=C.create_string_buffer(512)
    status=api.CBMS_BindLifecycleModules(game.base,dll.base,output,reason,len(reason))
    if damage:assert status==0 and bytes(output)==before and reason.value
    else:assert status==1 and list(output)==[dll.base+e['body']['rva'] for e in profile['entries']]
