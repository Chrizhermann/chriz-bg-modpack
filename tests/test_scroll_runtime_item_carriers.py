"""Concrete compiled item-entry callbacks. Native callees are controlled fixtures;
the two real executable bodies/call PCs are certified in the separate binding tests.
"""
import ctypes as C
import hashlib
import importlib.util
import struct
import subprocess

import pytest
from test_scroll_runtime_native import SOURCE,compiler_environment,configure_native_api
from test_scroll_runtime_actor_archive import allocated,runtime_fixture

USE=C.CFUNCTYPE(C.c_uint16,C.c_void_p,C.c_void_p)
POINT=C.CFUNCTYPE(C.c_uint16,C.c_void_p)
FIRE=C.CFUNCTYPE(C.c_uint16,C.c_void_p,C.c_void_p,C.c_int,C.c_void_p)
ROOT=C.CFUNCTYPE(C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_void_p)
TYPE=C.CFUNCTYPE(C.c_uint16,C.c_void_p)
DIGEST=C.CFUNCTYPE(C.c_int,C.c_char_p,C.c_char_p,C.c_void_p,C.c_void_p)
class Functions(C.Structure):
    _fields_=[('use',USE),('point',POINT),('fire',FIRE),('fire_point',FIRE),('effect',ROOT),('item_type',TYPE),('roots',C.c_size_t*4),('continuations',C.c_size_t*2)]

SIGNATURES={
    'ConfigureItemCarriers':([C.c_void_p,C.POINTER(Functions),C.c_void_p,C.c_uint32,DIGEST,C.c_void_p],C.c_int),
    'ItemCarriersIdle':([],C.c_int),'DetachItemCarriers':([],C.c_int),'ItemCarrierError':([],C.c_char_p),
    'UseItemCarrier':([C.c_void_p,C.c_void_p],C.c_uint16),'UsePointCarrier':([C.c_void_p],C.c_uint16),
    'TestFireItemCarrier':([C.c_size_t,C.c_int,C.c_void_p,C.c_void_p,C.c_int,C.c_void_p],C.c_uint16),
    'TestItemEffectCarrier':([C.c_size_t,C.c_void_p,C.c_int,C.c_int,C.c_void_p],C.c_void_p),
    'DestructObserved':([C.c_void_p,C.c_uint32,C.c_size_t],C.c_int),
    'BindItemModule':([C.c_size_t,C.POINTER(Functions),C.c_void_p,C.c_uint32],C.c_int),
    'ActorIsObserved':([C.c_void_p,C.c_size_t],C.c_int),
}
def configure_items(library):
    """Native-API and item-carrier signatures of a harness build."""
    native=configure_native_api(library)
    for name,(args,out) in SIGNATURES.items():
        fn=getattr(library,'CBMS_'+name);fn.argtypes=args;fn.restype=out
    return native
@pytest.fixture(scope='module')
def item_api(tmp_path_factory):
    directory=tmp_path_factory.mktemp('scroll-item-carrier');compiler,env,msvc=compiler_environment();assert msvc
    dll=directory/'item.dll'
    result=subprocess.run([compiler,'/nologo','/std:c++20','/EHsc','/W4','/WX','/permissive-','/DCBMS_OFFLINE_HARNESS','/LD',str(SOURCE/'native_api.cpp'),str(SOURCE/'item_carrier_api.cpp'),str(SOURCE/'item_hook_host.cpp'),f'/Fe{dll}'],cwd=directory,env=env,text=True,capture_output=True)
    assert result.returncode==0,result.stdout+result.stderr
    return configure_items(C.CDLL(str(dll)))

class Harness:
    def __init__(self,native,classification='typed_cast_candidate',item_type=11,verify=True,observe=True):
        self.api,self.runtime,self.resolve,self.report,self.calls,self.errors=runtime_fixture(native)
        self.effects=[];self.arguments=[];self.on_use=lambda reader,target:None;self.on_fire=lambda reader,item,ability,target:None
        self.null=False;self.category=item_type
        self.item=allocated(bytes(0x10)+b'SCROLL12') # full eight bytes, no NUL
        self.item_address=C.addressof(self.item)
        if observe:assert self.api.CBMS_ActorObserved(self.runtime,0x1000,0xFEDCBA9876543210)==1
        assert self.api.CBMS_ActorObserved(self.runtime,0x2000,17)==1
        @USE
        def use(reader,target):
            self.arguments.append(('use',reader,target));self.on_use(reader,target);return 0xFEDC
        @POINT
        def point(reader):
            self.arguments.append(('point',reader));self.on_use(reader,0x9876);return 0xEDCB
        @FIRE
        def fire(reader,item,ability,target):
            self.arguments.append(('fire',reader,item,ability,target));self.on_fire(reader,item,ability,target);return 0xDCBA
        @ROOT
        def effect(item,ability,index,reader):
            self.arguments.append(('root',item,ability,index,reader))
            if self.null:return None
            data=bytearray(0x110);data[8:16]=b'EFF V2.0';struct.pack_into('<I',data,0xC8,10)
            value=allocated(bytes(data));self.effects.append(value);return C.addressof(value)
        @TYPE
        def category(item):return self.category
        @DIGEST
        def digest(name,extension,out,user):
            if not verify:return 0
            C.memmove(out,hashlib.sha256(b'actual fixture bytes').digest(),32);return 1
        self.keep=(use,point,fire,effect,category,digest)
        self.functions=Functions(use,point,fire,fire,effect,category,(C.c_size_t*4)(100,101,102,103),(C.c_size_t*2)(200,201))
        spec=importlib.util.spec_from_file_location('item_policy_table',SOURCE/'policy_table.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        binary,_=module.build([dict(item='SCROLL12',ability=2,classification=classification,resources={'SCROLL12.ITM':hashlib.sha256(b'actual fixture bytes').hexdigest()})])
        self.table=allocated(binary)
        self.configured=self.api.CBMS_ConfigureItemCarriers(self.runtime,C.byref(self.functions),self.table,len(self.table),digest,None)
    def root(self,kind=0,reader=0x1000,index=0,ability=2,caller=None):
        return self.api.CBMS_TestItemEffectCarrier(100+kind if caller is None else caller,self.item_address,ability,index,reader)
    def fire(self,reader=0x1000,point=0,caller=200,ability=2):
        return self.api.CBMS_TestFireItemCarrier(caller,point,reader,self.item_address,ability,0xAABBCCDD)
    def archive(self):
        nodes=[allocated(bytes(0x18)) for _ in self.effects];linked=allocated(bytes(0x20))
        for i,(node,effect) in enumerate(zip(nodes,self.effects)):
            C.c_uint64.from_buffer(node,0).value=C.addressof(nodes[i+1]) if i+1<len(nodes) else 0
            C.c_uint64.from_buffer(node,0x10).value=C.addressof(effect)
        C.c_uint64.from_buffer(linked,8).value=C.addressof(nodes[0]) if nodes else 0
        C.c_uint32.from_buffer(linked,0x18).value=len(nodes)
        assert self.api.CBMS_PrepareEffectExport(self.runtime,0x2000,C.addressof(linked),1,0,0)==1
        text=self.api.CBMS_EffectExportText(self.runtime,0x2000)
        wire=allocated(b''.join(bytes(effect)[8:] for effect in self.effects))
        assert self.api.CBMS_ValidateEffectExport(self.runtime,0x2000,wire,len(wire))==1
        if not text:return [None]*len(nodes)
        data=bytes.fromhex(text[9:].decode());offset=4;rows=[]
        for _ in nodes:
            offset+=264;owned=data[offset];offset+=1
            if not owned:rows.append(None);continue
            origin,reader,item,ability,root,depth,has_level,level=struct.unpack_from('<QQ8sIIIBI',data,offset)
            rows.append(dict(origin=origin,reader=reader,item=item,ability=ability,root=root));offset+=41
        assert offset==len(data)
        return rows
    def close(self):
        if self.configured:assert self.api.CBMS_DetachItemCarriers()==1
        for effect in self.effects:assert self.api.CBMS_DestructObserved(self.runtime,1,C.addressof(effect))==1
        assert self.api.CBMS_Destroy(self.runtime)==1

@pytest.mark.parametrize('point',[False,True])
def test_real_family_signatures_exact_args_multi_target_shared_origin(item_api,point):
    h=Harness(item_api)
    try:
        assert h.configured==1
        def use(reader,target):
            assert h.api.CBMS_ItemCarriersIdle()==0
            h.root(int(point),reader,0)
            assert h.fire(reader,int(point),200+int(point))==0xDCBA
            h.root(int(point),reader,2)
        h.on_use=use;h.on_fire=lambda reader,item,ability,target:h.root(2+int(point),reader,1)
        result=h.api.CBMS_UsePointCarrier(0x1000) if point else h.api.CBMS_UseItemCarrier(0x1000,0x12345678)
        assert result==(0xEDCB if point else 0xFEDC)
        rows=h.archive();assert len({row['origin'] for row in rows})==1
        assert [row['root'] for row in rows]==[0,1,2]
        assert all(row['reader']==0xFEDCBA9876543210 and row['item']==b'SCROLL12' and row['ability']==2 for row in rows)
        assert h.arguments[2]==('fire',0x1000,h.item_address,2,0xAABBCCDD)
        assert all(C.c_uint32.from_buffer(effect,0xC8).value==10 for effect in h.effects)
        assert h.api.CBMS_ItemCarrierError()==b''
    finally:h.close()

@pytest.mark.parametrize('nested',['unrelated_fire','other_reader_use','same_reader_use'])
def test_nested_item_invocations_cannot_borrow_outer_origin(item_api,nested):
    h=Harness(item_api)
    try:
        depth=0
        def use(reader,target):
            nonlocal depth
            h.root(0,reader)
            if depth:return
            depth=1
            if nested=='unrelated_fire':h.fire(caller=999)
            else:h.api.CBMS_UseItemCarrier(0x2000 if nested=='other_reader_use' else reader,target)
            depth=0;h.root(0,reader,2)
        h.on_use=use;h.on_fire=lambda reader,item,ability,target:h.root(2,reader,1)
        h.api.CBMS_UseItemCarrier(0x1000,7)
        rows=h.archive();assert rows[0]['origin']==rows[2]['origin']!=rows[1]['origin']
        assert rows[1]['reader']==(17 if nested=='other_reader_use' else rows[0]['reader'])
    finally:h.close()

@pytest.mark.parametrize('case',['unrelated_root','manual_learning','fixed_native','review_native','non_scroll','null_return'])
def test_unowned_operations_leave_native_return_and_effect_bytes(item_api,case):
    h=Harness(item_api,classification={'manual_learning':'learning','fixed_native':'native_exception','review_native':'unresolved'}.get(case,'typed_cast_candidate'),item_type=1 if case=='non_scroll' else 11)
    try:
        if case=='null_return':h.null=True
        h.on_use=lambda reader,target:h.root(caller=999 if case=='unrelated_root' else None)
        assert h.api.CBMS_UseItemCarrier(0x1000,0x7788)==0xFEDC
        assert all(row is None for row in h.archive())
        assert h.api.CBMS_ItemCarrierError()==b''
    finally:h.close()

@pytest.mark.parametrize('case',['missing_ability','unobserved_ai','bad_resource_digest'])
def test_visible_refusal_without_replacing_native_result_or_stranding_use(item_api,case):
    h=Harness(item_api,classification='unresolved' if case=='unresolved' else 'typed_cast_candidate',verify=case!='bad_resource_digest',observe=case!='unobserved_ai')
    try:
        if case=='bad_resource_digest':assert h.configured==0
        elif case=='unobserved_ai':
            h.on_fire=lambda reader,item,ability,target:h.root(2,reader)
            assert h.fire(caller=999)==0xDCBA
        else:
            h.on_use=lambda reader,target:h.root(ability=3 if case=='missing_ability' else 2)
            assert h.api.CBMS_UseItemCarrier(0x1000,0)==0xFEDC
        assert h.api.CBMS_ItemCarrierError()
        assert all(row is None for row in h.archive())
    finally:h.close()

def test_root_origin_survives_return_for_later_typed_selection(item_api):
    h=Harness(item_api)
    try:
        h.on_use=lambda reader,target:h.root()
        h.api.CBMS_UseItemCarrier(0x1000,0x2000)
        frame=C.c_uint64();level=C.c_uint32(10)
        assert h.api.CBMS_BeginCast(h.runtime,1,C.addressof(h.effects[0]),0,0xD000,b'SPELL',0,2,3,4,5,C.byref(frame))==1
        assert h.api.CBMS_Select(h.runtime,frame,0,0xD000,C.byref(level))==1 and level.value==12
        assert h.calls[0][0]==0x1000
        assert h.api.CBMS_EndCast(h.runtime,frame)==1
    finally:h.close()

@pytest.fixture(scope='module')
def exception_probe(tmp_path_factory):
    directory=tmp_path_factory.mktemp('scroll-item-exception');compiler,env,msvc=compiler_environment();assert msvc
    binary=directory/'probe.exe'
    result=subprocess.run([compiler,'/nologo','/std:c++20','/EHsc','/W4','/WX','/permissive-','/DCBMS_OFFLINE_HARNESS',str(SOURCE/'native_api.cpp'),str(SOURCE/'item_carrier_api.cpp'),str(SOURCE/'item_exception_probe.cpp'),f'/Fe{binary}'],cwd=directory,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    return binary

@pytest.mark.parametrize('mode',['root','use'])
def test_actual_cpp_original_exceptions_release_scope_and_use_token(exception_probe,mode):
    result=subprocess.run([str(exception_probe),mode],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    assert result.stdout.strip()==f'PASS original {mode} exception cleanup'
