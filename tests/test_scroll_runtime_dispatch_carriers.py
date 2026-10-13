"""Compiled concrete opcode/message/action producers, with native callees
substituted only in this offline fixture. No initialized-engine acceptance.
"""
import ctypes as C
import struct,subprocess
import pytest
from test_scroll_runtime_native import SOURCE,compiler_environment,configure_native_api
from test_scroll_runtime_actor_archive import allocated,runtime_fixture
APPLY=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p)
CTOR=C.CFUNCTYPE(C.c_void_p,C.c_void_p)
ADD=C.CFUNCTYPE(C.c_int16,C.c_void_p,C.c_void_p,C.c_int)
RUN=C.CFUNCTYPE(None,C.c_void_p)
DESTROY=C.CFUNCTYPE(C.c_void_p,C.c_void_p,C.c_uint32)
class Functions(C.Structure):
    _fields_=[('apply146',APPLY),('apply148',APPLY),('ctor',CTOR),('add',ADD),('run',RUN),('destroy',DESTROY),
              ('ctor_returns',C.c_size_t*2),('add_return',C.c_size_t),('run_return',C.c_size_t),
              ('effect_return',C.c_size_t),('point_return',C.c_size_t),('vtable',C.c_size_t)]
@pytest.fixture(scope='module')
def dispatch_api(tmp_path_factory):
    directory=tmp_path_factory.mktemp('scroll-dispatch');compiler,env,msvc=compiler_environment();assert msvc
    library=directory/'dispatch.dll'
    result=subprocess.run([compiler,'/nologo','/std:c++20','/EHsc','/W4','/WX','/permissive-','/DCBMS_OFFLINE_HARNESS','/LD',str(SOURCE/'native_api.cpp'),str(SOURCE/'dispatch_carrier_api.cpp'),str(SOURCE/'dispatch_hook_host.cpp'),str(SOURCE/'cast_carrier_api.cpp'),str(SOURCE/'cast_hook_host.cpp'),f'/Fe{library}'],cwd=directory,env=env,text=True,capture_output=True)
    assert result.returncode==0,result.stdout+result.stderr
    api=configure_native_api(C.CDLL(str(library)));dll=api[0]
    signatures={
        'ConfigureDispatchCarriers':([C.c_void_p,C.POINTER(Functions)],C.c_int),
        'BindDispatchModule':([C.c_size_t,C.POINTER(Functions),C.c_void_p,C.c_uint32],C.c_int),
        'DetachDispatchCarriers':([],C.c_int),'DispatchCarriersIdle':([],C.c_int),'DispatchCarrierError':([],C.c_char_p),
        'Apply146Carrier':([C.c_void_p,C.c_void_p],C.c_int),'Apply148Carrier':([C.c_void_p,C.c_void_p],C.c_int),
        'TestActionDefaultCarrier':([C.c_size_t,C.c_void_p],C.c_void_p),
        'TestAddMessageCarrier':([C.c_size_t,C.c_void_p,C.c_void_p,C.c_int],C.c_int16),
        'FireMessageRunCarrier':([C.c_void_p],None),'FireMessageDestroyCarrier':([C.c_void_p,C.c_uint32],C.c_void_p),
        'DispatchOwnerAt':([C.c_uint32,C.c_size_t,C.c_void_p,C.POINTER(C.c_uint32),C.POINTER(C.c_size_t)],C.c_int),
        'DestructObserved':([C.c_void_p,C.c_uint32,C.c_size_t],C.c_int),
    }
    for name,(args,out) in signatures.items():
        fn=getattr(dll,'CBMS_'+name);fn.argtypes=args;fn.restype=out
    return api
class Harness:
    def __init__(self,native):
        self.api,self.runtime,self.resolve,self.report,self.calls,self.errors=runtime_fixture(native)
        self.effects=[];self.actions=[];self.messages=[];self.events=[]
        self.on_apply=lambda effect,target:None;self.on_run=lambda message:None;self.on_add=lambda message:None
        for reader in (0x1000,0x2000):assert self.api.CBMS_ActorObserved(self.runtime,reader,reader+1)==1
        @APPLY
        def apply(effect,target):self.events.append(('apply',effect,target));self.on_apply(effect,target);return -71
        @CTOR
        def ctor(action):C.memset(action,0,0x88);return action
        @ADD
        def add(handler,message,force):self.events.append(('add',handler,message,force));self.on_add(message);return -13
        @RUN
        def run(message):self.events.append(('run',message));self.on_run(message)
        @DESTROY
        def destroy(message,flags):self.events.append(('destroy',message,flags));return message
        self.keep=(apply,ctor,add,run,destroy)
        self.functions=Functions(apply,apply,ctor,add,run,destroy,(C.c_size_t*2)(100,101),102,103,104,105,0x12345678)
        assert self.api.CBMS_ConfigureDispatchCarriers(self.runtime,C.byref(self.functions))==1
    def effect(self,opcode,mode,special=0,reader=0x1000,owned=True):
        raw=bytearray(0x160);struct.pack_into('<I',raw,0x10,opcode);struct.pack_into('<I',raw,0x20,mode);struct.pack_into('<I',raw,0x48,special)
        value=allocated(bytes(raw));self.effects.append(value);address=C.addressof(value)
        if owned:
            assert self.api.CBMS_Construct(self.runtime,1,address)==1
            token=C.c_uint64();assert self.api.CBMS_ItemBegin(self.runtime,reader,b'SCROLL',0,0,C.byref(token))==1
            assert self.api.CBMS_ItemChild(self.runtime,token,address,0)==1;assert self.api.CBMS_ItemEnd(self.runtime,token)==1
        return value
    def action(self,point=False,caller=None):
        action=allocated(bytes([0xA5])*0x88);self.actions.append(action)
        assert self.api.CBMS_TestActionDefaultCarrier(100+int(point) if caller is None else caller,C.addressof(action))==C.addressof(action)
        return action
    def message(self,caller=102,vtable=0x12345678,submit=True):
        message=allocated(struct.pack('<Q',vtable)+bytes(range(24)));self.messages.append(message)
        if submit:assert self.api.CBMS_TestAddMessageCarrier(caller,0x3000,C.addressof(message),-7)==-13
        return message
    def owner(self,selector,caller,receiver):
        kind,carrier=C.c_uint32(99),C.c_size_t(0xBAD)
        result=self.api.CBMS_DispatchOwnerAt(selector,caller,receiver,C.byref(kind),C.byref(carrier))
        return result,kind.value,carrier.value
    def select(self,kind,carrier,selector,expected):
        frame=C.c_uint64();level=C.c_uint32(77)
        assert self.api.CBMS_BeginCast(self.runtime,kind,carrier,selector,0xD000,b'SPELL',0,6,7,8,9,C.byref(frame))==1
        assert self.api.CBMS_Select(self.runtime,frame,selector,0xD000,C.byref(level))==expected
        assert level.value==(12 if expected else 77)
        assert self.api.CBMS_EndCast(self.runtime,frame)==1
    def close(self):
        assert self.api.CBMS_DetachDispatchCarriers()==1
        for kind,values in ((1,self.effects),(2,self.messages),(3,self.actions)):
            for value in values:assert self.api.CBMS_DestructObserved(self.runtime,kind,C.addressof(value))==1
        assert self.api.CBMS_Destroy(self.runtime)==1

@pytest.mark.parametrize('opcode,special,selector',[(146,0,3),(146,1,5),(148,0,4),(148,1,6)])
def test_mode0_attaches_at_embedded_default_constructor_before_eeex_action_rewrite(dispatch_api,opcode,special,selector):
    h=Harness(dispatch_api)
    try:
        effect=h.effect(opcode,0,special);before=bytes(effect)
        h.on_apply=lambda effect,target:h.action(opcode==148)
        assert getattr(h.api,f'CBMS_Apply{opcode}Carrier')(C.addressof(effect),0x9876)==-71
        assert bytes(effect)==before and bytes(h.actions[0])==bytes(0x88)
        for _ in range(2):h.select(3,C.addressof(h.actions[0]),selector,1) # action ticks retain ownership
        assert all(call[0]==0x1000 for call in h.calls)
        assert h.api.CBMS_DispatchCarrierError()==b''
    finally:h.close()

@pytest.mark.parametrize('case',['temporary_action','unowned_nested','owned_nested'])
def test_ctor_pc_and_nested_dispatcher_scope_prevent_outer_ancestry_leak(dispatch_api,case):
    h=Harness(dispatch_api)
    try:
        outer=h.effect(146,0);inner=h.effect(146,0,reader=0x2000,owned=case=='owned_nested');depth=0
        def apply(effect,target):
            nonlocal depth
            if depth:h.action();return
            if case=='temporary_action':h.action(caller=999);return
            depth=1;h.api.CBMS_Apply146Carrier(C.addressof(inner),target);depth=0;h.action()
        h.on_apply=apply;h.api.CBMS_Apply146Carrier(C.addressof(outer),0x9999)
        h.select(3,C.addressof(h.actions[0]),3,1 if case=='owned_nested' else 0)
        if case!='temporary_action':h.select(3,C.addressof(h.actions[1]),3,1)
        if case=='owned_nested':assert [call[0] for call in h.calls]==[0x2000,0x1000]
    finally:h.close()

def test_two_queued_readers_message_run_copy_cancellation_and_native_bytes(dispatch_api):
    h=Harness(dispatch_api)
    try:
        roots=[h.effect(146,1,reader=reader) for reader in (0x1000,0x2000)]
        h.on_apply=lambda effect,target:h.message()
        for root in roots:h.api.CBMS_Apply146Carrier(C.addressof(root),0x9999)
        originals=[bytes(message) for message in h.messages]
        def run(message):
            result,kind,carrier=h.owner(1,103,0x8888)
            assert (result,kind,carrier)==(1,2,message)
            h.select(kind,carrier,1,1)
            assert h.owner(1,999,0x8888)==(0,99,0xBAD)
        h.on_run=run
        for message in reversed(h.messages):h.api.CBMS_FireMessageRunCarrier(C.addressof(message))
        assert [call[0] for call in h.calls]==[0x2000,0x1000]
        assert [bytes(message) for message in h.messages]==originals
        message=C.addressof(h.messages[0]);assert h.api.CBMS_FireMessageDestroyCarrier(message,0x80000001)==message
        assert h.events[-1]==('destroy',message,0x80000001)
        h.on_run=lambda message:None
        assert h.api.CBMS_DispatchCarriersIdle()==1
    finally:h.close()

@pytest.mark.parametrize('opcode,mode,selector,pc',[(146,2,0,104),(148,1,2,105),(148,2,2,105)])
def test_direct_native_call_identity_and_receiver_check(dispatch_api,opcode,mode,selector,pc):
    h=Harness(dispatch_api)
    try:
        effect=h.effect(opcode,mode);results=[]
        def apply(effect,target):
            receiver=effect if opcode==146 else target
            results.append(h.owner(selector,pc,receiver))
            results.append(h.owner(selector,999,receiver));results.append(h.owner(selector,pc,0xBAD))
        h.on_apply=apply;getattr(h.api,f'CBMS_Apply{opcode}Carrier')(C.addressof(effect),0x2222)
        assert results==[(1,1,C.addressof(effect)),(0,99,0xBAD),(0,99,0xBAD)]
        assert h.owner(selector,pc,C.addressof(effect))==(0,99,0xBAD)
    finally:h.close()

def test_nested_unowned_fire_message_run_masks_owned_parent(dispatch_api):
    h=Harness(dispatch_api)
    try:
        effect=h.effect(146,1);h.on_apply=lambda effect,target:h.message();h.api.CBMS_Apply146Carrier(C.addressof(effect),0)
        outer=C.addressof(h.messages[0]);inner=C.addressof(h.message(submit=False));results=[]
        def run(message):
            results.append(h.owner(1,103,0x1000))
            if message==outer:
                h.api.CBMS_FireMessageRunCarrier(inner);results.append(h.owner(1,103,0x1000))
        h.on_run=run;h.api.CBMS_FireMessageRunCarrier(outer)
        assert results==[(1,2,outer),(0,99,0xBAD),(1,2,outer)]
    finally:h.close()

@pytest.mark.parametrize('case',['wrong_message_class','unsupported_mode','wrong_opcode_class'])
def test_owned_malformed_native_path_latches_error_and_preserves_original_call(dispatch_api,case):
    h=Harness(dispatch_api)
    try:
        effect=h.effect(148 if case=='wrong_opcode_class' else 146,9 if case=='unsupported_mode' else 1)
        if case=='wrong_message_class':h.on_apply=lambda effect,target:h.message(vtable=0xDEADBEEF)
        before=bytes(effect);assert h.api.CBMS_Apply146Carrier(C.addressof(effect),0x8888)==-71
        assert before==bytes(effect) and h.api.CBMS_DispatchCarrierError()
    finally:h.close()
