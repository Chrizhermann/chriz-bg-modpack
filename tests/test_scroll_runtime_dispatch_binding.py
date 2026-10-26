"""Actual pinned image spans plus private simulation of initialized route and
vtable relocations. No game function or dynamically generated cave is invoked.
"""
import ctypes as C
import json,struct
import pytest
from test_scroll_runtime_native import SOURCE
from test_scroll_runtime_binding import mapped,windows
from test_scroll_runtime_dispatch_carriers import dispatch_api,Functions
PROFILES=json.loads((SOURCE/'dispatch-profiles.json').read_text())
STRINGS=['string_copy','string_assign','string_destroy','string_assign_copy','string_copy_before_write','string_get_buffer','string_concat']
@pytest.mark.parametrize('damage',[None,'apply146','apply148','constructor','add','run','destroy','ctor_pc','type_vtable','unrelocated_vtable',
    'insert_vtable','unrelocated_insert_vtable','no_eeex','inside_body','inside_route','not_executable',*STRINGS])
def test_dispatch_binder_actual_bodies_and_preserved_eeex_routes(dispatch_api,mapped,damage):
    p=next(value for value in PROFILES if value['version']==mapped.profile['version'])
    # A raw SEC_IMAGE view does not initialize the module. Install only these
    # audited pointer relocations on private COW pages, as an initialized loader
    # would; imports/globals and the rest of the image remain uninitialized.
    pointers=[mapped.base+rva for rva in p['vtable_slots']]
    if damage=='unrelocated_vtable':pointers=[mapped.profile['preferred_base']+rva for rva in p['vtable_slots']]
    if damage=='type_vtable':pointers[6]+=1
    mapped.write(p['fire_vtable'],struct.pack('<7Q',*pointers))
    inserts=[mapped.base+rva for rva in p['insert_slots']]
    if damage=='unrelocated_insert_vtable':inserts=[mapped.profile['preferred_base']+rva for rva in p['insert_slots']]
    if damage=='insert_vtable':inserts[6]=mapped.base+p['vtable_slots'][6]  # FireSpell Run in the InsertAction table
    mapped.write(p['insert_vtable'],struct.pack('<7Q',*inserts))
    for route in p['eeex_routes']:
        target=mapped.base+0x280000
        if damage=='inside_body':target=mapped.base+p['entries'][0]+0x50
        if damage=='inside_route':target=mapped.base+route['rva']
        if damage=='not_executable':target=mapped.base+0x100
        patched=b'\xE9'+struct.pack('<i',target-(mapped.base+route['rva']+5))
        mapped.write(route['rva'],bytes.fromhex(route['original']) if damage=='no_eeex' else patched)
    labels=['apply146','apply148','constructor','add','run','destroy']
    if damage in labels or damage=='ctor_pc':
        rva=p['entries'][labels.index(damage)] if damage in labels else p['ctor_returns'][0]-5
        mapped.write(rva,bytes([mapped.read(rva,1)[0]^1]))
    if damage in STRINGS:
        # The witness relies on each certified CString body, not only its entry.
        span=p['strings'][STRINGS.index(damage)];rva=span['rva']+span['size']//2
        mapped.write(rva,bytes([mapped.read(rva,1)[0]^1]))
    before=[mapped.read(s['rva'],s['size']) for s in p['spans']]
    output=Functions();C.memset(C.byref(output),0xCA,C.sizeof(output));old=bytes(output);reason=C.create_string_buffer(512)
    result=dispatch_api[0].CBMS_BindDispatchModule(mapped.base,C.byref(output),reason,len(reason))
    assert [mapped.read(s['rva'],s['size']) for s in p['spans']]==before
    if damage:assert result==0 and bytes(output)==old and reason.value
    else:
        assert result==1,reason.value
        expected=p['entries']+p['ctor_returns']+[p[key] for key in ('fire_add_return','fire_run_return','effect_fire_return','point_fire_return','fire_vtable','insert_vtable','empty_string')]
        assert list(struct.unpack('<15Q',bytes(output)))==[mapped.base+rva for rva in expected]
        assert b'host-owned' in reason.value
