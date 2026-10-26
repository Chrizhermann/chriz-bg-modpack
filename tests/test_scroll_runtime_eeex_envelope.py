"""Actor envelope callbacks in both shipped Lua families; no engine writes."""
import importlib
import importlib.util
from pathlib import Path
import subprocess

import pytest

from test_scroll_runtime_native import SOURCE, compiler_environment

LOADER = Path("C:/tmp/scroll-hook-research-20261009/InfinityLoader")
EEEX = Path("C:/tmp/scroll-hook-research-20261009/EEex")


@pytest.fixture(params=["lua51", "luajit21"])
def lua(request):
    value = importlib.import_module("lupa." + request.param).LuaRuntime(unpack_returned_tuples=True)
    value.execute('''
        handlers, listeners, rejects = {}, {}, {}
        actor = {aux={}}
        health, staged, finished, exported = true, nil, false, "CBMSFX01:FAKE"
        function EEex_GetUDAux(sprite) return sprite.aux end
        function EEex_Sprite_AddMarshalHandlers(name, export, import)
            handlers[name] = {exporter=export, importer=import}
        end
        function EEex_Sprite_AddLoadedListener(f) listeners[#listeners+1]=f end
        function CBMS_NativeRejectEnvelope(reason) rejects[#rejects+1]=reason; health=false end
        function CBMS_NativeHealthy() return health end
        function CBMS_NativeStage(sprite, text) staged=text; return health, "refused" end
        function CBMS_NativeExport(sprite) return exported, "export failed" end
        function CBMS_NativeImportFinished(sprite) return finished, dropped end
        printed = {}
        function print(text) printed[#printed+1] = text end
        function CBMS_NativeActorUUID(sprite, low, high)
            uuidLow, uuidHigh=low,high; finished=true; return true
        end
        function EEex_Sprite_LuaHook_OnAfterEffectListUnmarshalled(sprite)
            assert(finished, "native association must precede earlier loaded callbacks")
            previousCalled=true
        end
    ''')
    value.execute((SOURCE / "CBMS_ScrollMarshal.lua").read_text())
    value.execute('handler=handlers.CBM_SCROLL_CONTEXT')
    return value


def test_known_envelope_waits_for_native_commit(lua):
    lua.execute('''
        envelope={schema=1,payload="CBMSFX01:123456789ABCDEF0"}
        handler.importer(actor,envelope)
        assert(actor.aux.CBMS_ScrollMarshal.raw == envelope)
        assert(staged == envelope.payload)
        listeners[1](actor)
        assert(actor.aux.CBMS_ScrollMarshal.raw == envelope)
        finished=true
        listeners[1](actor)
        assert(actor.aux.CBMS_ScrollMarshal.raw == nil)
        local out=handler.exporter(actor)
        assert(out.schema==1 and out.payload==exported and #rejects==0)
    ''')


def loaded_actor(display, strref, script, low, high):
    """Fields as a loaded listener sees them: the display name is usually still empty."""
    return ('{m_sName={m_pchData={get=function() return "%s" end}},m_baseStats={m_name=%d},'
            'm_scriptName={get=function() return "%s" end},'
            'm_pLocalVariables={find=function(_,k) assert(k=="EEEX_UUID") return {m_intValue=%d,m_dWValue=%d} end}}'
            % (display, strref, script, low, high))


@pytest.mark.parametrize("name,shown", [
    (loaded_actor("", 268, "O#XAN", 0xAC, 0), "Xan (O#XAN, UUID AC)"),  # an NPC: its creature name string
    (loaded_actor("", 0xFFFFFFFF, "None", 0x3F, 0), "actor UUID 3F"),  # a protagonist: no name string yet
    (loaded_actor("Imoen", 16453, "IMOEN2", -1, 1), "Imoen (IMOEN2, UUID 1FFFFFFFF)"),
    ('{}', "an actor"),
])
def test_outdated_envelope_drop_is_logged_and_not_saved_again(lua, name, shown):
    lua.execute('function Infinity_FetchString(strref) return ({[268]="Xan",[16453]="Imoen"})[strref] or "" end')
    lua.execute(f'for k,v in pairs({name}) do actor[k]=v end')
    lua.execute('''
        envelope={schema=1,payload="CBMSFX01:123456789ABCDEF0"}
        handler.importer(actor,envelope)
        finished, dropped = true, "saved effect record count mismatch (saved 72, loaded 83)"
        listeners[1](actor)
        assert(actor.aux.CBMS_ScrollMarshal.raw == nil and health and #rejects==0)
        exported=""
        assert(handler.exporter(actor)==nil) -- nothing stale is written again
    ''')
    assert list(lua.eval('printed').values()) == [
        f"[CBM scroll] Dropped outdated scroll data for {shown} only: saved effect record count mismatch "
        "(saved 72, loaded 83). Its effects keep their levels; spells they cast later use the normal level."]


def test_refused_import_logs_no_drop_and_keeps_envelope(lua):
    lua.execute('''
        envelope={schema=1,payload="CBMSFX01:123456789ABCDEF0"}
        handler.importer(actor,envelope)
        finished, dropped = false, nil
        listeners[1](actor)
        assert(actor.aux.CBMS_ScrollMarshal.raw == envelope and #printed==0)
    ''')


def test_uuid_uses_two_exact_local_fields_before_existing_callbacks(lua):
    lua.execute('''
        actor.m_pLocalVariables={find=function(self,name)
            assert(name=="EEEX_UUID")
            return {m_intValue=-1,m_dWValue=4294967295}
        end}
        EEex_Sprite_LuaHook_OnAfterEffectListUnmarshalled(actor)
        assert(uuidLow==-1 and uuidHigh==4294967295 and previousCalled)
    ''')


@pytest.mark.parametrize("definition", [
    '{schema=99,payload="future",unknown={x=1}}',
    '{schema=1,payload="future",unknown={x=1}}',
    '{schema=1,payload=17}',
])
def test_unknown_envelope_kept_by_reference(lua, definition):
    lua.execute(f'envelope={definition}')
    lua.execute('''
        handler.importer(actor,envelope)
        finished=true
        listeners[1](actor)
        assert(handler.exporter(actor)==envelope)
        assert(staged==nil and #rejects==1 and not health)
    ''')


def test_disabled_bridge_keeps_known_envelope_without_numeric_identity(lua):
    lua.execute('''
        health=false
        envelope={schema=1,payload="CBMSFX01:FEDCBA9876543210"}
        handler.importer(actor,envelope)
        assert(staged==nil and handler.exporter(actor)==envelope)
        assert(actor.aux.CBMS_ScrollMarshal.error and #rejects==0)
    ''')


def test_fallback_is_not_exported_twice_or_adopted_after_decode(lua):
    lua.execute('''
        envelope={schema=99,payload="future"}
        actor.aux.EEex_Sprite_FallbackMarshalStorage={CBM_SCROLL_CONTEXT=envelope}
        assert(handler.exporter(actor)==nil)
        assert(actor.aux.EEex_Sprite_FallbackMarshalStorage.CBM_SCROLL_CONTEXT==envelope)
        assert(#rejects==1 and not health)
    ''')


def test_exporter_failure_and_duplicate_import_are_latched(lua):
    lua.execute('''
        exported=nil
        assert(handler.exporter(actor)==nil and #rejects==1)
        health=true
        one={schema=1,payload="one"}; two={schema=1,payload="two"}
        handler.importer(actor,one); handler.importer(actor,two)
        local v=actor.aux.CBMS_ScrollMarshal
        assert(v.raw==one and v.conflicts[1]==one and v.conflicts[2]==two)
        assert(#rejects==2 and not health)
    ''')


def test_source_overlay_exact_pinned_edges_and_nonmutation(tmp_path):
    spec = importlib.util.spec_from_file_location("scroll_eeex_overlay", SOURCE / "eeex_source_overlay.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    changes = module.render(LOADER, EEEX)
    source = changes["InfinityLoader/EEex-Core-Shared-Files/source/EEex.cpp"]
    assert source.index("CBMS_EEexAfterActorUUID") < source.index('lua_getglobal(L, "EEex_Sprite_LuaHook_OnAfterEffectListUnmarshalled")')
    assert 'DecodeEffectFromBase(pEffectBase);\n\t\t\t\tif (pSprite != nullptr && version == 1) CBMS_EEexEffectDecoded' in source
    script = changes["EEex/EEex/copy/EEex_scripts/EEex_Sprite_Patch.lua"]
    assert script.index("call #L(CBMS_EEexBeforeEffectMarshal)") < script.index('EEex_GenLuaCall("EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize"')
    assert "mov r8, r13" in script and "mov rdx, rdi" in script
    assert "call #L(CBMS_EEexAfterEffectMarshal)" in script
    # Lua parser only: no hook execution, machine code or game process.
    parser = importlib.import_module("lupa.lua51").LuaRuntime()
    assert parser.eval("function(s) return assert(loadstring(s)) ~= nil end")(script)
    original = (LOADER / "EEex-Core-Shared-Files/source/EEex.cpp").read_text()
    assert "CBMS_EEexEffectDecoded" not in original
    with pytest.raises(ValueError, match="anchor"):
        module.once("ambiguous ambiguous", "ambiguous", "x")


def test_lua_binding_object_compiles_against_actual_infinityloader_sdk(tmp_path):
    compiler, env, msvc = compiler_environment()
    assert msvc, "actual reviewed SDK is Windows x64"
    includes = [LOADER / "InfinityLoaderCommon/headers/common", LOADER / "LuaBindingsCore/headers/common"]
    for unit in ("eeex_lua_bindings", "dll_entry"):
        args = [compiler, "/nologo", "/std:c++20", "/EHsc", "/W4", "/WX", "/permissive-", "/c",
                str(SOURCE / (unit + ".cpp")), f"/Fo{tmp_path / (unit + '.obj')}"]
        args += [f"/I{path}" for path in includes]
        result = subprocess.run(args, cwd=tmp_path, env=env, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (tmp_path / (unit + ".obj")).stat().st_size > 0
