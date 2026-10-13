"""Actual pinned EEex fallback preservation, not a safe-uninstall claim.

No game/save access. The marshal handler's absence makes deferred rewards
inaccessible; preserving its bytes is not equivalent to releasing those rewards.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


CHECK = Path(__file__).resolve().parents[1] / "research/xp-banking-native/identity_serializer_test.py"
_spec = spec_from_file_location("cbm_actual_serializer_fixture", CHECK)
_fixture = module_from_spec(_spec)
_spec.loader.exec_module(_fixture)
wire = _fixture.wire


def test_actual_eeex_preserves_absent_banking_handler_then_restores_its_payload(wire):
    lua, _memory = wire
    lua.execute('''
        local payload={schema=2,policy='bg1_sod',phase='SOD',revision=13,
            ownerKey=string.rep('a',32),floor=500000,overflow=123456789,kind='dual',
            old={class=2,newClass=4,levelAtDual=10,total=550000,usable=500000,
                preUsable=500000,preBank=50000},
            futureField={note='opaque data must survive',flag=true}}
        local function import(actor,data) actor.received=data end
        register('CBMBank',function() return payload end,import)
        local original={aux={}}
        local firstSize=EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize(original)
        EEex_Sprite_Hook_WriteExtraEffectListMarshal(4096)
        -- Removing this component's handler must use EEex's real fallback,
        -- rather than our exporter or a newly invented preservation callback.
        EEex_Sprite_Private_MarshalHandlers.CBMBank=nil
        local absent={aux={}}
        EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal(absent,4096)
        local fallback=absent.aux.EEex_Sprite_FallbackMarshalStorage.CBMBank
        assert(fallback.old.total==550000 and fallback.old.usable==500000)
        assert(fallback.overflow==123456789 and fallback.ownerKey==payload.ownerKey)
        assert(fallback.futureField.note==payload.futureField.note and fallback.futureField.flag)
        -- Subsequent saves with EEex present must export the unknown handler
        -- again. Repeated load/save must not turn preservation into XP release.
        for i=1,2 do
            local size=EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize(absent)
            assert(size==firstSize)
            EEex_Sprite_Hook_WriteExtraEffectListMarshal(4096)
            absent={aux={}}
            EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal(absent,4096)
            local data=absent.aux.EEex_Sprite_FallbackMarshalStorage.CBMBank
            assert(data.revision==13 and data.old.preBank==50000 and data.old.usable==500000)
        end
        -- Normal startup re-registers before loading actors. The saved carrier
        -- returns through the real importer without adopting a replacement.
        register('CBMBank',function() error('export should not run here') end,import)
        local restored={aux={}}
        EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal(restored,4096)
        assert(restored.received.schema==2 and restored.received.old.total==550000)
        assert(restored.received.overflow==123456789 and restored.received.revision==13)
        assert(restored.received.futureField.flag and #failures==0)
    ''')
