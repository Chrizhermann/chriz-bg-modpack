"""Relocated read-only actual image certification, never invoking game code."""
import ctypes as C
import json
import pytest
from test_scroll_runtime_native import SOURCE
from test_scroll_runtime_binding import mapped,windows
from test_scroll_runtime_item_carriers import item_api,Functions
PROFILES=json.loads((SOURCE/'item-profiles.json').read_text())
@pytest.mark.parametrize('damage',[None,'use','point','fire','fire_point','root','type','root_call','continuation_call'])
def test_item_binder_six_bodies_and_exact_call_sites(item_api,mapped,damage):
    p=next(value for value in PROFILES if value['version']==mapped.profile['version'])
    if damage:
        if damage=='root_call':rva=p['root_returns'][0]-5
        elif damage=='continuation_call':rva=p['continuation_returns'][0]-5
        else:rva=p['spans'][['use','point','fire','fire_point','root','type'].index(damage)]['rva']
        mapped.write(rva,bytes([mapped.read(rva,1)[0]^1]))
    out=Functions();C.memset(C.byref(out),0xCA,C.sizeof(out));before=bytes(out);reason=C.create_string_buffer(512)
    result=item_api[0].CBMS_BindItemModule(mapped.base,C.byref(out),reason,len(reason))
    if damage:assert result==0 and bytes(out)==before and reason.value
    else:
        assert result==1,reason.value
        actual=struct_unpack_addresses(out)
        assert actual[:6]==[mapped.base+s['rva'] for s in p['spans']]
        assert actual[6:10]==[mapped.base+rva for rva in p['root_returns']]
        assert actual[10:]==[mapped.base+rva for rva in p['continuation_returns']]
def struct_unpack_addresses(value):
    import struct
    return list(struct.unpack('<12Q',bytes(value)))
