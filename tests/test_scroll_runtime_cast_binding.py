"""Actual pinned images, private COW EEex-site simulation; read-only binder."""
import ctypes as C
import json,struct
import pytest
from test_scroll_runtime_native import SOURCE
from test_scroll_runtime_binding import mapped,windows
from test_scroll_runtime_cast_carriers import cast_api,dispatch_api,Functions
PROFILES=json.loads((SOURCE/'cast-profiles.json').read_text())
@pytest.mark.parametrize('damage',[None,*range(8),'selection','child','missing_fix','bad_fix_tail','inside_body','not_executable'])
def test_cast_body_call_sites_and_existing_eeex_fixes(cast_api,mapped,damage):
    p=next(value for value in PROFILES if value['version']==mapped.profile['version'])
    for fix in p['eeex_fixes']:
        target=mapped.base+(p['entries'][0]+0x50 if damage=='inside_body' else 0x100 if damage=='not_executable' else 0x280000)
        patch=b'\xE9'+struct.pack('<i',target-mapped.base-fix['rva']-5)+b'\x90'*(fix['size']-5)
        if damage=='bad_fix_tail' and fix['size']>5:patch=patch[:-1]+b'\xCC'
        mapped.write(fix['rva'],bytes.fromhex(fix['original']) if damage=='missing_fix' else patch)
    if isinstance(damage,int) or damage in ('selection','child'):
        at=p['entries'][damage] if isinstance(damage,int) else p['selection'][0] if damage=='selection' else p['children'][6]-5
        mapped.write(at,bytes([mapped.read(at,1)[0]^1]))
    fn=cast_api[0].CBMS_BindCastModule;fn.argtypes=[C.c_size_t,C.POINTER(Functions),C.c_void_p,C.c_uint32];fn.restype=C.c_int
    out=Functions();C.memset(C.byref(out),0xCA,C.sizeof(out));original=bytes(out);reason=C.create_string_buffer(512)
    before=[mapped.read(s['rva'],s['size']) for s in p['spans']];result=fn(mapped.base,C.byref(out),reason,len(reason))
    assert before==[mapped.read(s['rva'],s['size']) for s in p['spans']]
    if damage is not None:assert result==0 and bytes(out)==original and reason.value
    else:
        assert result==1,reason.value
        words=struct.unpack('<26Q',bytes(out));assert list(words[:8])==[mapped.base+r for r in p['entries']]
        assert words[8] and list(words[9:])==[mapped.base+r for r in [p['getter'],*p['selection'],*p['children'],*p['extras']]]
