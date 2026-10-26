"""Compiled concrete opcode/message/action producers, with native callees
substituted only in this offline fixture. No initialized-engine acceptance.
Mode0 ownership travels inside the action value (action_witness.hpp);
EngineStrings stands in for the certified engine CString copies.
"""
import ctypes as C
import struct,subprocess
import pytest
from test_scroll_runtime_native import SOURCE,compiler_environment,configure_native_api,EngineStrings,WITNESS_BASELINE
from test_scroll_runtime_actor_archive import allocated,runtime_fixture
APPLY=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p)
CTOR=C.CFUNCTYPE(C.c_void_p,C.c_void_p)
ADD=C.CFUNCTYPE(C.c_int16,C.c_void_p,C.c_void_p,C.c_int)
RUN=C.CFUNCTYPE(None,C.c_void_p)
DESTROY=C.CFUNCTYPE(C.c_void_p,C.c_void_p,C.c_uint32)
INSERT=0x2468ACE0
# Queued ForceSpell/ForceSpellPoint; EEex's mode0 route swaps in SpellNoDec /
# SpellPointNoDec for special bit 0 before it calls AddMessage.
ACTION_IDS={(146,0):113,(146,1):191,(148,0):114,(148,1):192}
class Functions(C.Structure):
    _fields_=[('apply146',APPLY),('apply148',APPLY),('ctor',CTOR),('add',ADD),('run',RUN),('destroy',DESTROY),
              ('ctor_returns',C.c_size_t*2),('add_return',C.c_size_t),('run_return',C.c_size_t),
              ('effect_return',C.c_size_t),('point_return',C.c_size_t),('vtable',C.c_size_t),
              ('insert_vtable',C.c_size_t),('empty_string',C.c_size_t)]
SIGNATURES={
    'ConfigureDispatchCarriers':([C.c_void_p,C.POINTER(Functions)],C.c_int),
    'BindDispatchModule':([C.c_size_t,C.POINTER(Functions),C.c_void_p,C.c_uint32],C.c_int),
    'DetachDispatchCarriers':([],C.c_int),'DispatchCarriersIdle':([],C.c_int),'DispatchCarrierError':([],C.c_char_p),
    'Apply146Carrier':([C.c_void_p,C.c_void_p],C.c_int),'Apply148Carrier':([C.c_void_p,C.c_void_p],C.c_int),
    'TestActionDefaultCarrier':([C.c_size_t,C.c_void_p],C.c_void_p),
    'TestAddMessageCarrier':([C.c_size_t,C.c_void_p,C.c_void_p,C.c_int],C.c_int16),
    'FireMessageRunCarrier':([C.c_void_p],None),'FireMessageDestroyCarrier':([C.c_void_p,C.c_uint32],C.c_void_p),
    'DispatchOwnerAt':([C.c_uint32,C.c_size_t,C.c_void_p,C.POINTER(C.c_uint32),C.POINTER(C.c_size_t)],C.c_int),
    'TestLimitActionWitnesses':([C.c_void_p,C.c_uint32],C.c_int),
}
def configure_dispatch(library):
    """Native-API and dispatch-carrier signatures of a harness build."""
    api=configure_native_api(library)
    for name,(args,out) in SIGNATURES.items():
        fn=getattr(library,'CBMS_'+name);fn.argtypes=args;fn.restype=out
    return api
@pytest.fixture(scope='module')
def dispatch_api(tmp_path_factory):
    directory=tmp_path_factory.mktemp('scroll-dispatch');compiler,env,msvc=compiler_environment();assert msvc
    library=directory/'dispatch.dll'
    result=subprocess.run([compiler,'/nologo','/std:c++20','/EHsc','/W4','/WX','/permissive-','/DCBMS_OFFLINE_HARNESS','/LD',str(SOURCE/'native_api.cpp'),str(SOURCE/'dispatch_carrier_api.cpp'),str(SOURCE/'dispatch_hook_host.cpp'),str(SOURCE/'cast_carrier_api.cpp'),str(SOURCE/'cast_hook_host.cpp'),f'/Fe{library}'],cwd=directory,env=env,text=True,capture_output=True)
    assert result.returncode==0,result.stdout+result.stderr
    return configure_dispatch(C.CDLL(str(library)))
class Harness:
    def __init__(self,native):
        self.api,self.runtime,self.resolve,self.report,self.calls,self.errors=runtime_fixture(native)
        self.strings=EngineStrings()
        self.effects=[];self.actions=[];self.messages=[];self.inserts=[];self.events=[];self.witnesses=set()
        self.scratch=allocated(bytes(0x88));self.strings.construct(C.addressof(self.scratch))  # GetNextAction's static action
        self.holders=[C.addressof(self.scratch)]
        self.on_apply=lambda effect,target:None;self.on_run=lambda message:None;self.on_add=lambda message:None
        for reader in (0x1000,0x2000):assert self.api.CBMS_ActorObserved(self.runtime,reader,reader+1)==1
        @APPLY
        def apply(effect,target):self.events.append(('apply',effect,target));self.on_apply(effect,target);return -71
        @CTOR
        def ctor(action):return self.strings.construct(action)
        @ADD
        def add(handler,message,force):self.events.append(('add',handler,message,force));self.on_add(message);return -13
        @RUN
        def run(message):self.events.append(('run',message));self.on_run(message)
        @DESTROY
        def destroy(message,flags):self.events.append(('destroy',message,flags));return message
        self.keep=(apply,ctor,add,run,destroy)
        self.functions=Functions(apply,apply,ctor,add,run,destroy,(C.c_size_t*2)(100,101),102,103,104,105,0x12345678,
            INSERT,C.addressof(self.strings.empty_global))
        assert self.api.CBMS_ConfigureDispatchCarriers(self.runtime,C.byref(self.functions))==1
    def effect(self,opcode,mode,special=0,reader=0x1000,owned=True):
        raw=bytearray(0x160);struct.pack_into('<I',raw,0x10,opcode);struct.pack_into('<I',raw,0x20,mode);struct.pack_into('<I',raw,0x48,special)
        value=allocated(bytes(raw));self.effects.append(value);address=C.addressof(value)
        if owned:
            assert self.api.CBMS_Construct(self.runtime,1,address)==1
            token=C.c_uint64();assert self.api.CBMS_ItemBegin(self.runtime,reader,b'SCROLL',0,0,C.byref(token))==1
            assert self.api.CBMS_ItemChild(self.runtime,token,address,0)==1;assert self.api.CBMS_ItemEnd(self.runtime,token)==1
        return value
    def action(self,point=False,caller=None,into=None):
        # Any other action the hooked default constructor builds (stack
        # temporaries, parameter constructors, engine members, reused memory).
        action=into if into is not None else allocated(bytes([0xA5])*0x88)
        if into is None:self.actions.append(action)
        assert self.api.CBMS_TestActionDefaultCarrier(100+int(point) if caller is None else caller,C.addressof(action))==C.addressof(action)
        return action
    def insert(self,opcode=146,special=0,caller=None,vtable=INSERT,edit=None):
        """ApplyEffect mode0: a CMessageInsertAction whose action (+10h) the
        audited constructor call builds; its fields are copied from the stack
        action, then EEex's cave swaps the ID and calls AddMessage."""
        message=allocated(bytes(0x98));self.inserts.append(message);base=C.addressof(message)
        C.c_size_t.from_buffer(message,0).value=vtable
        pc=(100 if opcode==146 else 101) if caller is None else caller
        assert self.api.CBMS_TestActionDefaultCarrier(pc,base+0x10)==base+0x10
        C.c_uint16.from_buffer(message,0x10).value=ACTION_IDS[(opcode,special&1)]
        if edit:edit(base+0x10)
        before=bytes(message)
        assert self.api.CBMS_TestAddMessageCarrier(0xEEE0,0x3000,base,0)==-13
        after=bytes(message);assert after[:0x90]==before[:0x90]  # only the witness field may change
        value=C.c_size_t.from_buffer(message,0x90).value
        if value!=self.strings.empty:self.witnesses.add(value)
        return message
    def new_sprite(self):
        sprite=allocated(bytes(0x500));self.actions.append(sprite);self.strings.construct(C.addressof(sprite)+0x3F8)
        self.holders.append(C.addressof(sprite)+0x3F8);return sprite
    def deliver(self,message,sprite):
        """Run -> InsertAction copy -> message deleted -> GetNextAction's
        scratch assignment -> SetCurrAction assignment -> queue node deleted.
        Every step is a native value copy; none is observed."""
        action,current=C.addressof(message)+0x10,C.addressof(sprite)+0x3F8
        node=allocated(bytes(0x88));self.actions.append(node);queued=C.addressof(node)
        self.strings.copy_action(queued,action);self.strings.destroy_action(action)
        self.strings.assign_action(C.addressof(self.scratch),queued)
        self.strings.assign_action(current,C.addressof(self.scratch));self.strings.destroy_action(queued)
        return node
    def witness(self,action):
        out=C.c_size_t(0xBAD)
        result=self.api.CBMS_ActionWitnessCarrier(self.runtime,C.c_size_t.from_address(action+0x80).value,C.byref(out))
        return result,out.value
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
        for kind,values in ((1,self.effects),(2,self.messages)):
            for value in values:assert self.api.CBMS_DestructObserved(self.runtime,kind,C.addressof(value))==1
        # The engine's own holders end the way the engine ends them.
        for action in [*self.holders,*(C.addressof(message)+0x10 for message in self.inserts)]:self.strings.destroy_action(action)
        assert self.api.CBMS_SweepActionWitnesses(self.runtime)==0
        assert not self.witnesses&set(self.strings.freed)  # the engine never frees a witness
        assert self.api.CBMS_Destroy(self.runtime)==1

@pytest.mark.parametrize('opcode,special,selector',[(146,0,3),(146,1,5),(148,0,4),(148,1,6)])
def test_mode0_witness_travels_by_value_into_the_current_action(dispatch_api,opcode,special,selector):
    h=Harness(dispatch_api)
    try:
        effect=h.effect(opcode,0,special);before=bytes(effect);sprite=h.new_sprite()
        h.on_apply=lambda effect,target:h.insert(opcode,special)
        assert getattr(h.api,f'CBMS_Apply{opcode}Carrier')(C.addressof(effect),0x9876)==-71
        assert bytes(effect)==before and h.api.CBMS_DispatchCarrierError()==b''
        message=h.inserts[0];witness=C.c_size_t.from_buffer(message,0x90).value
        assert witness!=h.strings.empty and h.strings.refs(witness)==WITNESS_BASELINE+1
        h.deliver(message,sprite)
        current=C.addressof(sprite)+0x3F8
        assert h.witness(current)==(1,witness) and h.strings.refs(witness)==WITNESS_BASELINE+2  # scratch + m_curAction
        for _ in range(2):h.select(3,witness,selector,1)  # action ticks retain ownership
        assert all(call[0]==0x1000 for call in h.calls)
        # The next action replaces m_curAction and the scratch copy; the
        # released witness can no longer resolve and the sweep reclaims it.
        fresh=h.action(caller=999);h.strings.assign_action(current,C.addressof(fresh))
        assert h.witness(current)==(0,0xBAD) and h.api.CBMS_SweepActionWitnesses(h.runtime)==1
        h.strings.assign_action(C.addressof(h.scratch),C.addressof(fresh))
        assert h.api.CBMS_SweepActionWitnesses(h.runtime)==0 and h.witness(current)==(0,0xBAD)
        assert h.api.CBMS_DispatchCarrierError()==b''
    finally:h.close()

@pytest.mark.parametrize('case',['temporary_action','unowned_dispatcher','reused_memory','container_click','other_constructor_pc'])
def test_non_scroll_actions_never_inherit_a_scroll_use(dispatch_api,case):
    h=Harness(dispatch_api)
    try:
        sprite=h.new_sprite();current=C.addressof(sprite)+0x3F8
        effect=h.effect(146,0,owned=case!='unowned_dispatcher')
        def apply(effect,target):
            if case=='temporary_action':h.action(caller=999)  # CAIAction() stack temporary before the message
            h.insert(caller=777 if case=='other_constructor_pc' else None)
        h.on_apply=apply;h.api.CBMS_Apply146Carrier(C.addressof(effect),0x9999)
        owned=case not in ('unowned_dispatcher','other_constructor_pc')
        assert (C.c_size_t.from_buffer(h.inserts[0],0x90).value!=h.strings.empty)==owned
        node=h.deliver(h.inserts[0],sprite)
        if case=='temporary_action':assert h.witness(C.addressof(h.actions[-2]))==(0,0xBAD)
        if case=='reused_memory':
            # The scroll's queue node memory is reused by an ordinary action;
            # no address was ever registered, so nothing stale can attach.
            for _ in range(3):h.action(into=node)
            assert h.witness(C.addressof(node))==(0,0xBAD)
        if case=='container_click':
            # Container use builds, copies and inline-destroys plain actions
            # (CGameContainer::OnActionButton) outside any dispatcher. The old
            # address registry failed here on reused stack addresses.
            stack=allocated(bytes(0x88))
            for _ in range(5):
                h.action(into=stack);h.strings.copy_action(C.addressof(node),C.addressof(stack));h.strings.destroy_action(C.addressof(node))
            h.strings.assign_action(current,C.addressof(stack))
        result,key=h.witness(current)
        if owned and case!='container_click':assert result==1;h.select(3,key,3,1)
        else:assert (result,key)==(0,0xBAD)
        assert h.api.CBMS_DispatchCarrierError()==b''
    finally:h.close()

@pytest.mark.parametrize('case',['unowned_nested','owned_nested'])
def test_nested_dispatcher_scope_prevents_outer_ancestry_leak(dispatch_api,case):
    h=Harness(dispatch_api)
    try:
        outer=h.effect(146,0);inner=h.effect(146,0,reader=0x2000,owned=case=='owned_nested');depth=0
        def apply(effect,target):
            nonlocal depth
            if depth:h.insert();return
            depth=1;h.api.CBMS_Apply146Carrier(C.addressof(inner),target);depth=0;h.insert()
        h.on_apply=apply;h.api.CBMS_Apply146Carrier(C.addressof(outer),0x9999)
        inner_message,outer_message=h.inserts
        assert (C.c_size_t.from_buffer(inner_message,0x90).value!=h.strings.empty)==(case=='owned_nested')
        for message in (inner_message,outer_message):
            sprite=h.new_sprite();h.deliver(message,sprite);result,key=h.witness(C.addressof(sprite)+0x3F8)
            if result:h.select(3,key,3,1)
        assert [call[0] for call in h.calls]==([0x2000,0x1000] if case=='owned_nested' else [0x1000])
    finally:h.close()

def test_sequential_queued_casts_up_to_the_lifetime_allowance_then_native(dispatch_api):
    """Stamp, cast, release and retire one queued scroll cast after another; the
    stamp past the allowance is refused and reported, and that cast and every
    later one keep their native level. The real allowance runs in runtime_tests."""
    h=Harness(dispatch_api)
    try:
        allowance=5
        assert h.api.CBMS_TestLimitActionWitnesses(h.runtime,allowance)==1
        sprite=h.new_sprite();current=C.addressof(sprite)+0x3F8
        h.on_apply=lambda effect,target:h.insert(146,0)
        for n in range(allowance+2):
            assert h.api.CBMS_Apply146Carrier(C.addressof(h.effect(146,0)),0x9876)==-71  # native call kept
            message=h.inserts[-1];witness=C.c_size_t.from_buffer(message,0x90).value
            h.deliver(message,sprite)
            if n<allowance:
                assert witness!=h.strings.empty and h.witness(current)==(1,witness)
                h.select(3,witness,3,1)
                assert h.api.CBMS_DispatchCarrierError()==b''
            else:
                assert witness==h.strings.empty and h.witness(current)==(0,0xBAD)
                assert b'exhausted' in h.api.CBMS_DispatchCarrierError()
                assert h.api.CBMS_OverridesDisabled(h.runtime)==1 and h.errors
            # The engine replaces the action; the next sweep retires the witness.
            fresh=h.action(caller=999)
            for holder in (current,C.addressof(h.scratch)):h.strings.assign_action(holder,C.addressof(fresh))
            assert h.api.CBMS_SweepActionWitnesses(h.runtime)==0
        assert len(h.witnesses)==allowance and len(h.calls)==allowance
    finally:h.close()

@pytest.mark.parametrize('case',['wrong_message_class','field_changed'])
def test_owned_mode0_malformed_message_latches_error_and_keeps_native_call(dispatch_api,case):
    h=Harness(dispatch_api)
    try:
        effect=h.effect(146,0);other=h.strings.block(1,b'SCRIPT')
        def edit(action):h.strings.put(action+0x80,other)
        h.on_apply=lambda effect,target:h.insert(vtable=0xDEADBEEF if case=='wrong_message_class' else INSERT,
                                                 edit=edit if case=='field_changed' else None)
        assert h.api.CBMS_Apply146Carrier(C.addressof(effect),0x8888)==-71
        assert any(event[0]=='add' for event in h.events)
        expected=other if case=='field_changed' else h.strings.empty
        assert C.c_size_t.from_buffer(h.inserts[0],0x90).value==expected and h.api.CBMS_DispatchCarrierError()
    finally:h.close()

@pytest.mark.parametrize('case',['allocation_failed','another_message'])
def test_owned_mode0_without_its_constructed_message_attaches_nothing(dispatch_api,case):
    h=Harness(dispatch_api)
    try:
        effect=h.effect(146,0)
        def apply(effect,target):
            if case=='allocation_failed':assert h.api.CBMS_TestAddMessageCarrier(0xEEE0,0x3000,None,0)==-13
            else:h.message(caller=0xEEE0)
        h.on_apply=apply;h.api.CBMS_Apply146Carrier(C.addressof(effect),0x8888)
        assert h.api.CBMS_SweepActionWitnesses(h.runtime)==0 and h.api.CBMS_DispatchCarrierError()==b''
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
