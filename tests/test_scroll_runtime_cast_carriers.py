"""Concrete native ABI wrappers and the seven preselection scalar adapters.
Native callees here are substitutes; actual bridge/native bytes have separate
emulation/unwind tests. No game executable functions are invoked.
"""
import ctypes as C
import struct
import pytest
from test_scroll_runtime_dispatch_carriers import dispatch_api,Harness
from test_scroll_runtime_actor_archive import allocated
from test_scroll_runtime_native import WITNESS_BASELINE
EFFECT=C.CFUNCTYPE(None,C.c_void_p,C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_int)
FIRE=C.CFUNCTYPE(C.c_int16,C.c_void_p,C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_void_p,C.c_int,C.c_int)
TARGET=C.CFUNCTYPE(C.c_int16,C.c_void_p,C.c_void_p)
POINT=C.CFUNCTYPE(C.c_int16,C.c_void_p)
CHILD=C.CFUNCTYPE(C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_void_p)
TYPE=C.CFUNCTYPE(C.c_int16,C.c_void_p)
class Functions(C.Structure):
    _fields_=[('effect',EFFECT),('fire',FIRE),('point',FIRE),('force',TARGET),('force_point',POINT),
              ('spell',TARGET),('spell_point',POINT),('child',CHILD),('type',TYPE),('getter',C.c_size_t),
              ('selection',C.c_size_t*7),('children',C.c_size_t*7),('extra',C.c_size_t*2)]
SIGNATURES={
    'ConfigureCastCarriers':([C.c_void_p,C.POINTER(Functions)],C.c_int),'DetachCastCarriers':([],C.c_int),
    'CastCarriersIdle':([],C.c_int),'CastCarrierError':([],C.c_char_p),
    'SelectCapturedNative':([C.c_uint32,C.POINTER(C.c_uint64)],None),
    'TestEffectFireCarrier':([C.c_size_t,*EFFECT._argtypes_],None),
    'TestFireCarrier':([C.c_uint32,C.c_size_t,*FIRE._argtypes_],C.c_int16),
    'TestSpellEffectCarrier':([C.c_size_t,*CHILD._argtypes_],C.c_void_p),
    'ForceCarrier':(TARGET._argtypes_,C.c_int16),'ForcePointCarrier':(POINT._argtypes_,C.c_int16),
    'SpellCarrier':(TARGET._argtypes_,C.c_int16),'SpellPointCarrier':(POINT._argtypes_,C.c_int16),
    'CarrierIsOwned':([C.c_void_p,C.c_uint32,C.c_size_t],C.c_int),
}
def configure_cast(native):
    """Cast-carrier signatures on top of a configured dispatch harness build."""
    for name,(args,result) in SIGNATURES.items():fn=getattr(native[0],'CBMS_'+name);fn.argtypes=args;fn.restype=result
    return native
@pytest.fixture(scope='module')
def cast_api(dispatch_api):
    return configure_cast(dispatch_api)
class CastHarness(Harness):
    def __init__(self,api):
        super().__init__(api);self.path=0;self.raw_type=1;self.on_cast=lambda:None;self.on_child=lambda:None;self.entries=[];self.scalars=[]
        self.sprite=allocated(bytes(0x5000));self.sprite_address=C.addressof(self.sprite)
        self.strings.construct(self.sprite_address+0x3F8);self.holders.append(self.sprite_address+0x3F8)
        self.header=allocated(b'SPL V1  '+bytes(0x70));self.resource=allocated(bytes(0x80));self.spell=allocated(bytes(8)+b'SPELL123')
        C.c_void_p.from_buffer(self.resource,0x68).value=C.addressof(self.header);C.c_void_p.from_buffer(self.spell).value=C.addressof(self.resource)
        self.created=[]
        def invoke(path,args):self.path=path;self.entries.append((path,args));self.on_cast();return -219
        @EFFECT
        def effect(*args):invoke(0,args)
        @FIRE
        def fire(*args):return invoke(1,args)
        @FIRE
        def point(*args):return invoke(2,args)
        @TARGET
        def force(*args):return invoke(3,args)
        @POINT
        def force_point(*args):return invoke(4,args)
        @TARGET
        def spell(*args):return invoke(5,args)
        @POINT
        def spell_point(*args):return invoke(6,args)
        @CHILD
        def child(*args):
            self.entries.append(('child',args));self.on_child();value=allocated(bytes([0xA5])*0x160)
            self.created.append(value);return C.addressof(value)
        @TYPE
        def native_type(spell):return self.raw_type
        self.kept=(effect,fire,point,force,force_point,spell,spell_point,child,native_type)
        self.cast=Functions(*self.kept,800,(C.c_size_t*7)(*[1000+i*10 for i in range(7)]),(C.c_size_t*7)(*[2000+i*10 for i in range(7)]),(C.c_size_t*2)(3000,3001))
        assert self.api.CBMS_ConfigureCastCarriers(self.runtime,C.byref(self.cast))==1
    def scalar(self,path=None,pc=None,instance=None):
        path=self.path if path is None else path;saved=(C.c_uint64*40)();saved[14]=instance or C.addressof(self.spell);saved[16]=self.cast.selection[path]+5 if pc is None else pc
        local=allocated(bytes(0x100));saved[11]=C.addressof(local);saved[12]=self.sprite_address
        saved[2]=saved[3]=saved[4]=7
        C.c_uint32.from_buffer(local,0x77).value=7
        for offset in (0x58,0x6C):C.c_uint32.from_address(C.addressof(saved)+17*8+offset).value=7
        C.c_uint16.from_buffer(self.sprite,0x4C8A).value=7
        before=bytes(saved);self.api.CBMS_SelectCapturedNative(path,saved)
        if path==0:value=C.c_uint32.from_buffer(local,0x77).value
        elif path==1:value=C.c_uint32.from_address(C.addressof(saved)+17*8+0x58).value
        elif path==2:value=saved[3]
        elif path in (3,4):value=saved[2 if path==3 else 4]
        else:value=C.c_uint16.from_buffer(self.sprite,0x4C8A).value
        self.scalars.append(value);return saved,before
    def produce(self,pc=None,instance=None):
        return self.api.CBMS_TestSpellEffectCarrier(self.cast.children[self.path] if pc is None else pc,instance or C.addressof(self.spell),4,9,0x7654)
    def run_path(self,path):
        opcode=148 if path in (2,4,6) else 146;mode=2 if path==0 else 1 if path in (1,2) else 0
        root=self.effect(opcode,mode,int(path>=5));target=self.sprite_address
        if path==0:self.on_apply=lambda effect,target:self.api.CBMS_TestEffectFireCarrier(104,effect,C.addressof(self.spell)+8,target,17,10,0x555)
        elif path==2:self.on_apply=lambda effect,target:self.api.CBMS_TestFireCarrier(2,105,target,C.addressof(self.spell)+8,0x345,17,-1,0x567,19,23)
        elif path==1:
            self.on_apply=lambda effect,target:self.message()
            self.on_run=lambda message:self.api.CBMS_TestFireCarrier(1,103,target,C.addressof(self.spell)+8,0x345,17,-1,0x567,19,23)
        else:
            # Queued mode0: the witnessed message action reaches m_curAction by
            # native value copies; the entry then reads ownership from it.
            self.on_apply=lambda effect,target:self.deliver(self.insert(opcode,int(path>=5)),self.sprite)
        getattr(self.api,f'CBMS_Apply{opcode}Carrier')(C.addressof(root),target)
        if path==1:self.api.CBMS_FireMessageRunCarrier(C.addressof(self.messages[-1]))
        elif path>=3:
            args=(target,) if path in (4,6) else (target,0x345)
            return getattr(self.api,['','','','CBMS_ForceCarrier','CBMS_ForcePointCarrier','CBMS_SpellCarrier','CBMS_SpellPointCarrier'][path])(*args)
    def close(self):
        assert self.api.CBMS_DetachCastCarriers()==1
        for value in self.created:assert self.api.CBMS_DestructObserved(self.runtime,1,C.addressof(value))==1
        super().close()

@pytest.mark.parametrize('path',range(7))
def test_seven_real_call_boundary_adapters_stamp_only_level_and_keep_native_arguments(cast_api,path):
    h=CastHarness(cast_api)
    try:
        h.on_cast=lambda:(h.scalar(),h.produce());result=h.run_path(path)
        assert h.scalars==[12] and all(call[0]==0x1000 for call in h.calls)
        value=bytes(h.created[0]);assert value[:0xC8]==bytes([0xA5])*0xC8 and value[0xCC:]==bytes([0xA5])*(0x160-0xCC)
        assert struct.unpack_from('<I',value,0xC8)[0]==12 and h.api.CBMS_CastCarrierError()==b''
        if path>=3:assert result==-219
        if path in (1,2):assert h.entries[0][1][3:]==(17,-1,0x567,19,23)
        if path==0:assert h.entries[0][1][3:]==(17,10,0x555)
        assert h.api.CBMS_CastCarriersIdle()==1
    finally:h.close()

@pytest.mark.parametrize('raw_type',[0,3,4,5,9,-1])
def test_installed_native_helpers_preserve_level_and_unknown_type_refuses(cast_api,raw_type):
    h=CastHarness(cast_api)
    try:
        h.raw_type=raw_type;C.c_uint16.from_buffer(h.header,0x1C).value=max(0,raw_type)
        h.on_cast=lambda:(h.scalar(),h.produce());h.run_path(0)
        assert h.scalars==[7] and C.c_uint32.from_buffer(h.created[0],0xC8).value==0xA5A5A5A5
        assert bool(h.api.CBMS_CastCarrierError())==(raw_type not in (0,3,4,5))
        # Valid native-only children still have original-reader ancestry.
        if raw_type in (0,3,4,5):assert h.api.CBMS_CarrierIsOwned(h.runtime,1,C.addressof(h.created[0]))==1
    finally:h.close()

@pytest.mark.parametrize('case',['wrong_pc','repeated_selection','wrong_child_pc','other_cspell','action_reassigned'])
def test_strict_site_identity_and_entry_snapshot(cast_api,case):
    h=CastHarness(cast_api)
    try:
        def run():
            if case=='action_reassigned':
                other=h.action(caller=999);h.strings.assign_action(h.sprite_address+0x3F8,C.addressof(other))
            h.scalar(pc=777 if case=='wrong_pc' else None)
            if case=='repeated_selection':h.scalar()
            h.produce(pc=777 if case=='wrong_child_pc' else None,instance=C.addressof(h.header) if case=='other_cspell' else None)
        h.on_cast=run;h.run_path(5)
        if case=='action_reassigned':assert h.scalars==[12] and C.c_uint32.from_buffer(h.created[0],0xC8).value==12
        if case in ('wrong_child_pc','other_cspell'):assert C.c_uint32.from_buffer(h.created[0],0xC8).value==0xA5A5A5A5
        assert bool(h.api.CBMS_CastCarrierError())==(case in ('wrong_pc','repeated_selection'))
    finally:h.close()

@pytest.mark.parametrize('path,pc',[(1,3000),(2,3001),(1,777)])
def test_only_exact_native_extra_target_continuations_inherit_and_nested_cast_masks(cast_api,path,pc):
    h=CastHarness(cast_api);depth=0
    try:
        def run():
            nonlocal depth
            h.scalar();h.produce()
            if depth:return
            depth=1
            h.api.CBMS_TestFireCarrier(path,pc,h.sprite_address,C.addressof(h.spell)+8,0x777,0,-1,None,1,0)
            depth=0
        h.on_cast=run;h.run_path(5 if path==1 else 6)
        assert h.scalars==[12,12 if pc!=777 else 7]
        assert C.c_uint32.from_buffer(h.created[1],0xC8).value==(12 if pc!=777 else 0xA5A5A5A5)
        assert C.c_uint16.from_buffer(h.sprite,0x4C8A).value==12
        assert h.api.CBMS_CastCarrierError()==b''
    finally:h.close()

@pytest.mark.parametrize('case',['plain_action','replaced_before_entry','corrupted_witness'])
def test_action_entries_take_ownership_only_from_the_current_action_value(cast_api,case):
    h=CastHarness(cast_api);current=h.sprite_address+0x3F8
    try:
        h.on_cast=lambda:(h.scalar(),h.produce())
        root=h.effect(146,0,1)
        if case!='plain_action':
            h.on_apply=lambda effect,target:h.deliver(h.insert(146,1),h.sprite)
            h.api.CBMS_Apply146Carrier(C.addressof(root),h.sprite_address)
        if case=='replaced_before_entry':
            other=h.action(caller=999);h.strings.assign_action(current,C.addressof(other))
        witness=C.c_size_t.from_address(current+0x80).value
        if case=='corrupted_witness':C.c_int32.from_address(witness-8).value=3
        assert h.api.CBMS_SpellCarrier(h.sprite_address,0x345)==-219
        assert h.scalars==[7] and C.c_uint32.from_buffer(h.created[0],0xC8).value==0xA5A5A5A5 and not h.calls
        assert bool(h.api.CBMS_CastCarrierError())==(case=='corrupted_witness')
        if case=='corrupted_witness':C.c_int32.from_address(witness-8).value=0
    finally:h.close()

@pytest.mark.parametrize('fault',['field_changed','exhausted','retired_damaged'])
def test_queued_override_casts_natively_after_a_later_witness_fault(cast_api,fault):
    """Queue A, fail B, report it, then A casts at its native level: the one
    latched disabled state also covers ownership queued before the fault."""
    h=CastHarness(cast_api);current=h.sprite_address+0x3F8;repair=lambda:None
    try:
        if fault=='retired_damaged':
            # C: an earlier scroll cast whose witness is already retired.
            other=h.new_sprite();h.on_apply=lambda effect,target:h.deliver(h.insert(146,1),other)
            h.api.CBMS_Apply146Carrier(C.addressof(h.effect(146,0,1)),C.addressof(other))
            retired=C.c_size_t.from_address(C.addressof(other)+0x3F8+0x80).value
            fresh=h.action(caller=999)
            for holder in (C.addressof(other)+0x3F8,C.addressof(h.scratch)):h.strings.assign_action(holder,C.addressof(fresh))
            assert h.api.CBMS_SweepActionWitnesses(h.runtime)==0 and h.strings.refs(retired)==WITNESS_BASELINE
        # A: an owned mode0 cast queued into the reader's current action.
        h.on_apply=lambda effect,target:h.deliver(h.insert(146,1),h.sprite)
        h.api.CBMS_Apply146Carrier(C.addressof(h.effect(146,0,1)),h.sprite_address)
        assert h.witness(current)[0]==1 and h.api.CBMS_DispatchCarrierError()==b''
        # B: a later owned mode0 whose witness fails.
        edit=None
        if fault=='exhausted':assert h.api.CBMS_TestLimitActionWitnesses(h.runtime,len(h.witnesses))==1
        if fault=='field_changed':
            script=h.strings.block(1,b'SCRIPT')
            def edit(action):h.strings.put(action+0x80,script)
        if fault=='retired_damaged':
            C.c_int32.from_address(retired-12).value+=1  # an engine holder nobody counted
            def repair():C.c_int32.from_address(retired-12).value=WITNESS_BASELINE
        h.on_apply=lambda effect,target:h.insert(146,1,edit=edit)
        assert h.api.CBMS_Apply146Carrier(C.addressof(h.effect(146,0,1)),0x9999)==-71  # native call kept
        # Reported: the carrier diagnostic, the runtime reporter and the latch.
        assert h.api.CBMS_DispatchCarrierError() and h.errors and h.api.CBMS_OverridesDisabled(h.runtime)==1
        # A casts at its native level; its reader is never queried.
        h.on_cast=lambda:(h.scalar(),h.produce())
        assert h.api.CBMS_SpellCarrier(h.sprite_address,0x345)==-219
        assert h.scalars==[7] and C.c_uint32.from_buffer(h.created[0],0xC8).value==0xA5A5A5A5 and not h.calls
        assert h.api.CBMS_CastCarrierError()==b''
    finally:
        repair();h.close()
