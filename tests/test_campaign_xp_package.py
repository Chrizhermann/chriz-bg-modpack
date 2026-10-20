"""Source/package parity, real WeiDU synthetic installs, inert startup routing."""
from importlib import import_module
import json
import os
from pathlib import Path
import struct
import subprocess

import pytest

from tools import sync_campaign_xp as package
from tests.test_utility_xp_installer import (
    ROOT, SETUP_NAME, WEIDU, SyntheticGame, _file_tree, _is_weidu_artifact,
)

SOURCE = ROOT / package.PACKAGE
PUBLICATIONS = {"m_cbmbnk.lua", "cbmbkcfg.lua", "cbmdold.menu"}
NATIVE_HOST = ("baldur.exe", "eeex.dll", "luabindings.dll", "luaprovider.dll", "infinityloaderdll.dll")


@pytest.mark.skipif(os.name != "nt" or WEIDU is None,
                   reason="Combined installer needs Windows to run the shipped scroll policy EXE and WeiDU")
def test_scroll_and_banking_publications_coexist_and_uninstall(tmp_path):
    from tests.test_scroll_runtime_installer import fixture

    game = fixture(tmp_path, kind="eet")
    native_headers(game)
    before = game_files(game)
    result, log = run_component(game, 430)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    scroll_only = game_files(game)
    for component in (650, 651):
        result, log = run_component(game, component)
        assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    combined = game_files(game)
    for name, data in scroll_only.items():
        assert combined[name] == data, name
    for name in PUBLICATIONS:
        assert "OVERRIDE/" + name.upper() in combined
    for component in (651, 650):
        result, log = run_component(game, component, uninstall=True)
        assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == scroll_only
    result, log = run_component(game, 430, uninstall=True)
    assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == before


def native_headers(game):
    header = bytearray(0x200)
    struct.pack_into("<H", header, 0, 0x5A4D)
    struct.pack_into("<I", header, 0x3C, 0x80)
    struct.pack_into("<IH", header, 0x80, 0x4550, 0x8664)
    struct.pack_into("<H", header, 0x98, 0x20B)
    for name in NATIVE_HOST:
        (game.root / name).write_bytes(header)
    (game.root / "infinityloader.db").write_text("; unrelated loader data\n", encoding="ascii")


def run_component(game, component, *, uninstall=False):
    result = subprocess.run([str(WEIDU), SETUP_NAME, "--game", str(game.root),
        "--force-uninstall-list" if uninstall else "--force-install-list", str(component),
        "--language", "0", "--use-lang", "en_us", "--no-exit-pause", "--noautoupdate", "--quick-log"],
        cwd=game.root, capture_output=True, text=True, timeout=60)
    return result, result.stdout + result.stderr


def game_files(game):
    return {name: data for name, data in _file_tree(game.root).items() if not _is_weidu_artifact(name)}


# 652 fixtures, shared with the release ZIP acceptance tests.
CHAPTER_GATE = 'GlobalGT("Chapter","GLOBAL",4)'
BAINVI_IDS = {
    "trigger": "0x4010 GlobalGT(S:Name*,S:Area*,I:Value*)\n",
    "action": "120 StartCutScene(S:CutScene*)\n121 StartCutSceneMode()\n122 ClearAllActions()\n",
}
BAINVI_VANILLA = (
    'IF\n'
    '  XPGT(Player1,10000)\n'
    '  Global("BA_START_SCENE","MYAREA",0)\n'
    'THEN\n'
    '  RESPONSE #100\n'
    '    SetGlobal("BA_START_SCENE","MYAREA",1)\n'
    '    ClearAllActions()\n'
    '    StartCutSceneMode()\n'
    '    StartCutScene("CUTBA01")\n'
    'END\n'
)
# Another mod's Baeloth scene: no BA_START_SCENE or CUTBA01 for 652 to recognise.
BAINVI_REPLACED_SCENE = (
    'IF\n'
    '  Global("OtherModBaelothScene","GLOBAL",0)\n'
    'THEN\n'
    '  RESPONSE #100\n'
    '    SetGlobal("OtherModBaelothScene","GLOBAL",1)\n'
    '    StartCutScene("OMBA01")\n'
    'END\n'
)
BAINVI_NOT_COMPILED = b"not a compiled script\n"
NO_GATE_WARNING = "without Baeloth's Chapter 5+ gate"
NO_GATE_REASONS = {
    "replaced_scene": "has no block that starts his Larswood entrance",
    "not_compiled": "not a valid compiled script",
}
UNRECOGNISED_BAINVI = {"replaced_scene": BAINVI_REPLACED_SCENE, "not_compiled": BAINVI_NOT_COMPILED}


def chapter_game(tmp_path, bainvi=None):
    """EET fixture for 650/652: native host stubs, EEex marker, BAINVI.BCS.

    ``bainvi`` is BAF source compiled to override/bainvi.bcs, raw bytes written
    there unchanged, or None for a game without the script.
    """
    from tests.test_recruitment_xp import make_game, compile_script
    game = make_game(tmp_path, game_type="eet")
    native_headers(game)
    (game.override / "m___eeex.lua").write_text("-- fixture\n")
    for name, rows in BAINVI_IDS.items():
        with (game.override / f"{name}.ids").open("a", encoding="ascii") as stream:
            stream.write(rows)
    if isinstance(bainvi, bytes):
        (game.override / "bainvi.bcs").write_bytes(bainvi)
    elif bainvi is not None:
        compile_script(game, "BAINVI", bainvi)
        (game.root / "bainvi.baf").unlink()
    return game


def test_package_matches_canonical_sources_and_six_reviewed_binaries():
    manifest = package.check()
    assert manifest["status"] == "experimental-unreleased"
    native = {Path(name).name for name in manifest["files"] if name.startswith("native/")}
    assert native == package.NATIVE
    assert "cbmbank_identity_only.dll" not in native
    for path in SOURCE.rglob("*.lua"):
        assert "cbm-bank-trial" not in path.read_text(), path
    assert all(len(Path(name).stem) <= 8 for name in PUBLICATIONS | {"cbmbkchp.lua", "cbmbksoa.lua"})
    tp2 = (ROOT / SETUP_NAME).read_text()
    for number in (650, 651, 652):
        block = tp2.split(f"BEGIN @{number} DESIGNATED {number}", 1)[1].split("BEGIN @", 1)[0]
        assert "INSTALL_BY_DEFAULT" not in block
    assert "REQUIRE_COMPONENT ~setup-chriz-bg-modpack.tp2~ ~650~" in tp2


def test_sync_rejects_changed_binary_before_writing_package(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    selected = {}
    for name in package.NATIVE:
        (bundle / name).write_bytes(b"native fixture")
        selected[name] = package.digest(b"native fixture")
    changed = next(iter(package.NATIVE))
    (bundle / changed).write_bytes(b"changed")
    (bundle / "research-build.json").write_text(json.dumps({"researchOnly": True, "files": selected}))
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(AssertionError, match="checksum mismatch"):
        package.sync(bundle, root)
    assert not (root / package.PACKAGE).exists()


def test_sync_writes_its_manifest_with_repository_line_endings(tmp_path):
    bundle, root = tmp_path / "bundle", tmp_path / "repo"
    bundle.mkdir()
    selected = {}
    for name in package.NATIVE:
        (bundle / name).write_bytes(b"native fixture")
        selected[name] = package.digest(b"native fixture")
    for name in ("bank_notice.lua", "bank_record.lua"):
        selected[f"xp-banking-native/{name}"] = "source"
        source = root / "research/xp-banking-native" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"-- fixture\r\nreturn true\n")
    (root / "research/xp-banking-native/bank_recruitment_patch.tpa").write_bytes(b"// fixture\n")
    (bundle / "research-build.json").write_text(json.dumps({"researchOnly": True, "files": selected}))
    package.sync(bundle, root)
    written = (root / package.PACKAGE / "package-manifest.json").read_bytes()
    assert b"\r\n" not in written and written.endswith(b"}\n")
    assert b"\r\n" not in (root / package.PACKAGE / "runtime/xp-banking-native/bank_notice.lua").read_bytes()


def test_text_mirrors_use_stable_repository_line_endings(tmp_path):
    source = tmp_path / "source.lua"
    source.write_bytes(b"line one\r\nline two\n")
    assert package.source_bytes(source) == b"line one\nline two\n"
    manifest = package.check()
    for name, record in manifest["files"].items():
        if "source" in record:
            assert b"\r\n" not in (SOURCE / name).read_bytes(), name


@pytest.mark.parametrize("name", ["../outside", "C:/outside", "x/../../outside", "x\\outside"])
def test_manifest_paths_remain_inside_package(name):
    with pytest.raises(ValueError, match="Unsafe"):
        package.relative(name)


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
@pytest.mark.parametrize(
    "config,policy",
    [("cbmbkcfg.lua", "bg1_sod"), ("cbmbksoa.lua", "bg1_sod_soa"), ("cbmbkchp.lua", "chapter_caps")],
)
def test_startup_uses_normal_package_and_selected_policy_once(flavor, config, policy):
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.globals().config = (SOURCE / config).read_text()
    lua.globals().expected = policy
    lua.execute('''
        EEex_Active=true; calls=0
        gameReady=false;initListeners={}
        function EEex_GameState_AddInitializedListener(f) initListeners[#initListeners+1]=f end
        function initialize() gameReady=true;for _,f in ipairs(initListeners) do f() end;initListeners={} end
        function Infinity_DoFile(name) assert(name=='CBMBKCFG');assert(loadstring(config))() end
        function dofile(path)
            assert(path=='chriz-bg-modpack/campaign-xp/runtime/xp-banking-native/bank_bootstrap.lua')
            return {Install=function(o)
                assert(gameReady,'bank must start only once the game object exists')
                calls=calls+1;assert(o.policy==expected and o.researchOnly)
                assert(o.dllPath=='chriz-bg-modpack/campaign-xp/native/cbmbank_identity.dll')
                assert(o.progressionDLLDirectory=='chriz-bg-modpack/campaign-xp/native')
                assert(o.researchDir=='chriz-bg-modpack/campaign-xp/runtime')
                return true
            end}
        end
        function print()end
    ''')
    loader = (SOURCE / "m_cbmbnk.lua").read_text()
    lua.execute(loader)
    lua.execute(loader)
    # Loading the file only registers the start; the game object does not exist yet.
    assert lua.globals().calls == 0
    lua.execute("initialize()")
    assert lua.globals().calls == 1
    lua.execute(loader)
    assert lua.globals().calls == 1


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
def test_scroll_casting_starts_the_bank_first_and_it_runs_once(flavor):
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        EEex_Active=true; calls=0
        gameReady=false;initListeners={}
        function EEex_GameState_AddInitializedListener(f) initListeners[#initListeners+1]=f end
        function Infinity_DoFile(name) CBMBank_Config={schema=1,policy='bg1_sod'} end
        function dofile() return {Install=function()
            assert(gameReady,'bank must start only once the game object exists')
            calls=calls+1;CBMBank_Identity={ActorDestroyChain=function() end};return true end} end
        function print() end
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    # Scroll casting's earlier listener runs first and starts the bank; the bank's own
    # listener then finds it started.
    lua.execute('''
        gameReady=true
        CBMBank_Start();assert(calls==1 and CBMBank_Identity)
        for _,f in ipairs(initListeners) do f() end
        assert(calls==1)
    ''')
    # A running bank owns the rerouted names; the loader defines no fallback.
    lua.execute("assert(CBMBank_ActiveXP==nil and CBMBank_ImoenXPSet==nil and CBMBank_Catchup==nil)")


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
def test_without_eeex_startup_reports_at_load_and_keeps_pre_650_behavior(flavor):
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        printed={}
        function print(s) printed[#printed+1]=s end
        function dofile() error('nothing may load without EEex') end
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    lua.execute('''
        assert(#printed==1 and printed[1]:find('EEex is unavailable',1,true))
        assert(type(CBMBank_ActiveXP)=='function' and type(CBMBank_ImoenXPSet)=='function')
        assert(type(CBMBank_Catchup)=='function')
    ''')


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
def test_failed_startup_falls_back_only_for_names_nothing_owns(flavor):
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        EEex_Active=true
        gameReady=false;initListeners={}
        function EEex_GameState_AddInitializedListener(f) initListeners[#initListeners+1]=f end
        function initialize() gameReady=true;for _,f in ipairs(initListeners) do f() end;initListeners={} end
        function Infinity_DoFile(name) CBMBank_Config={schema=1,policy='bg1_sod'} end
        function dofile() return {Install=function() error('injected startup failure') end} end
        function print() end
        owned=function() end;CBMBank_ImoenXPSet=owned
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    lua.execute("assert(CBMBank_ActiveXP==nil and CBMBank_Catchup==nil);initialize()")
    lua.execute('''
        assert(CBMBank_ImoenXPSet==owned)
        assert(type(CBMBank_ActiveXP)=='function' and type(CBMBank_Catchup)=='function')
    ''')


WARNING_HARNESS = '''
    EEex_Active=true
    gameReady=false;initListeners={};actionListeners={};destroyedListeners={};shown={};printed={}
    function EEex_GameState_AddInitializedListener(f) initListeners[#initListeners+1]=f end
    function EEex_Action_AddSpriteStartedActionListener(f) actionListeners[#actionListeners+1]=f end
    function EEex_GameState_AddDestroyedListener(f) destroyedListeners[#destroyedListeners+1]=f end
    function initialize() gameReady=true;for _,f in ipairs(initListeners) do f() end;initListeners={} end
    function act(n) for i=1,n do for _,f in ipairs(actionListeners) do assert(f({},{})==nil) end end end
    function destroy() for _,f in ipairs(destroyedListeners) do f() end end
    function Infinity_DisplayString(s) shown[#shown+1]=s end
    function Infinity_DoFile(name) CBMBank_Config={schema=1,policy='bg1_sod'} end
    function print(s) printed[#printed+1]=s end
'''


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
def test_failed_startup_warns_in_game_once_per_loaded_game(flavor):
    # The live failure of 2026-10-13: the log line was the only trace, so XP went
    # past the BG1 cap unnoticed. The player now sees it in the message log.
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute(WARNING_HARNESS + '''
        function dofile() return {Install=function() error(
            '...ign-xp/runtime/xp-banking-native/dual_combined_hooks.lua:36: '..
            'EEex stats relay does not preserve native first call',0) end} end
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    lua.execute('''
        assert(#actionListeners==0 and CBMBank_Status==nil);initialize()
        assert(printed[1]:find('Startup failed',1,true))
        assert(#actionListeners==1 and #destroyedListeners==1 and #shown==0)
        act(3)
        assert(#shown==1)
        assert(shown[1]:find('did not start, so XP is not capped or banked',1,true))
        assert(shown[1]:find('Reason: dual_combined_hooks.lua:36: EEex stats relay does not '..
            'preserve native first call',1,true))
        assert(not shown[1]:find('runtime/',1,true))
        -- Loading another game shows it once more, at its first action.
        destroy();assert(#shown==1);act(2);assert(#shown==2 and shown[2]==shown[1])
        assert(CBMBank_Status()==shown[1] and #shown==3)
    ''')


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
def test_started_bank_adds_no_failure_warning(flavor):
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute(WARNING_HARNESS + '''
        function dofile() return {Install=function() assert(gameReady);return true end} end
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    lua.execute('''
        initialize();act(2)
        assert(#actionListeners==0 and #destroyedListeners==0 and #shown==0)
        assert(CBMBank_Status==nil and printed[1]:find('initialized',1,true))
    ''')


@pytest.mark.parametrize("flavor", ["lua51", "luajit21"])
def test_failure_warning_leaves_an_owned_status_command_and_works_without_eeex(flavor):
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute(WARNING_HARNESS + '''
        function dofile() return {Install=function() error('injected startup failure',0) end} end
        owned=function() return 'owned' end;CBMBank_Status=owned
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    lua.execute('''
        initialize();assert(CBMBank_Status==owned)
        act(1);assert(#shown==1 and shown[1]:find('Reason: injected startup failure',1,true))
    ''')
    # Without EEex nothing can be listened to; the status command still explains.
    lua = import_module("lupa." + flavor).LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        shown={}
        function print() end
        function Infinity_DisplayString(s) shown[#shown+1]=s end
        function dofile() error('nothing may load without EEex') end
    ''')
    lua.execute((SOURCE / "m_cbmbnk.lua").read_text())
    lua.execute('''
        assert(#shown==0)
        local text=CBMBank_Status()
        assert(text:find('did not start',1,true) and text:find('EEex is unavailable; launch using InfinityLoader',1,true))
        assert(#shown==1 and shown[1]==text)
    ''')


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU or WEIDU_BIN")
@pytest.mark.parametrize("prior", [False, True])
def test_base_soa_dependency_and_exact_uninstall(tmp_path, prior):
    game = SyntheticGame(tmp_path / "game", game="eet")
    native_headers(game)
    if prior:
        for name in PUBLICATIONS:
            (game.override / name).write_bytes(b"foreign prior bytes\x00\xff\r\n")
    before = game_files(game)
    result, log = run_component(game, 651)
    assert result.returncode == 0 and "SKIPPING:" in log, log
    assert game_files(game) == before
    result, log = run_component(game, 650)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    base = game_files(game)
    expected = dict(before)
    for name in PUBLICATIONS:
        expected["OVERRIDE/" + name.upper()] = (SOURCE / name).read_bytes()
    assert base == expected
    result, log = run_component(game, 651)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    expected["OVERRIDE/CBMBKCFG.LUA"] = (SOURCE / "cbmbksoa.lua").read_bytes()
    assert game_files(game) == expected
    result, log = run_component(game, 651, uninstall=True)
    assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == base
    result, log = run_component(game, 650, uninstall=True)
    assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU or WEIDU_BIN")
@pytest.mark.parametrize("problem", ["non-eet", "no-eeex", "missing-native", "x86", "truncated", "bad-offset"])
def test_real_prerequisites_and_pe_failures_publish_nothing(tmp_path, problem):
    game = SyntheticGame(tmp_path / "game", game="bg2ee" if problem == "non-eet" else "eet",
                         eeex=problem != "no-eeex")
    native_headers(game)
    host = game.root / "eeex.dll"
    if problem == "missing-native":
        host.unlink()
    elif problem == "truncated":
        host.write_bytes(b"MZ")
    elif problem in ("x86", "bad-offset"):
        data = bytearray(host.read_bytes())
        struct.pack_into("<H" if problem == "x86" else "<I", data,
                         0x84 if problem == "x86" else 0x3C, 0x14C if problem == "x86" else 0xFFFFFFF0)
        host.write_bytes(data)
    before = game_files(game)
    result, log = run_component(game, 650)
    assert "SUCCESSFULLY INSTALLED" not in log, log
    if problem in ("non-eet", "no-eeex", "missing-native"):
        assert result.returncode == 0 and "SKIPPING:" in log, log
    else:
        assert result.returncode != 0 and "ERROR" in log, log
    assert game_files(game) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU or WEIDU_BIN")
@pytest.mark.parametrize("sr", [False, True])
def test_component_routes_owned_recruitment_without_changing_authored_xp(tmp_path, sr):
    from tests.test_recruitment_xp import make_game, install, decompile_script, compile_script
    game = make_game(tmp_path, game_type="eet", sr=sr, converted=sr, reversed_blocks=sr)
    native_headers(game)
    (game.override / "m___eeex.lua").write_text("-- fixture\n")
    with (game.override / "action.ids").open("a") as stream:
        stream.write('472 EEex_LuaAction(S:Code*)\n')
    for component in (237, 238):
        result, log = install(game, component)
        assert result.returncode == 0, log
    for script in ("CBMFXP", "CBMEXP"):
        source = decompile_script(game, script)
        compile_script(game, script, source + 'IF\n Global("ForeignXP","LOCALS",0)\nTHEN\n RESPONSE #100\n ChangeStat(Myself,XP,555000,SET)\nEND\n')
    (game.override / "m_cbmixp.lua").write_bytes((ROOT / "chriz-bg-modpack/imoen-xp/m_cbmixp.lua").read_bytes())
    before = game_files(game)
    result, log = run_component(game, 650)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    for script in ("CBMFXP", "CBMEXP"):
        source = decompile_script(game, script)
        assert source.count("CBMBank_Catchup(") == 6
        assert 'ChangeStat(Myself,XP,555000,SET)' in source
    imoen = (game.override / "m_cbmixp.lua").read_text()
    assert "CBMBank_ActiveXP(member)" in imoen and "CBMBank_ImoenXPSet(sprite, target)" in imoen
    assert "math.min(3000000, math.floor(total / count))" in imoen
    result, log = run_component(game, 650, uninstall=True)
    assert result.returncode == 0, log
    assert game_files(game) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU or WEIDU_BIN")
def test_chapter_caps_dependency_mutual_exclusion_and_exact_uninstall(tmp_path):
    game = SyntheticGame(tmp_path / "game", game="eet")
    native_headers(game)
    before = game_files(game)
    # 652 requires 650
    result, log = run_component(game, 652)
    assert result.returncode == 0 and "SKIPPING:" in log, log
    assert game_files(game) == before
    # Install 650 then 652
    result, log = run_component(game, 650)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    base = game_files(game)
    result, log = run_component(game, 652)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    expected = dict(base)
    expected["OVERRIDE/CBMBKCFG.LUA"] = (SOURCE / "cbmbkchp.lua").read_bytes()
    assert game_files(game) == expected
    # 651 is mutually exclusive while 652 is installed
    result, log = run_component(game, 651)
    assert result.returncode == 0 and "SKIPPING:" in log, log
    assert game_files(game) == expected
    # Uninstall 652 restores 650's CBMBKCFG.lua; 651 can then install and blocks 652
    result, log = run_component(game, 652, uninstall=True)
    assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == base
    result, log = run_component(game, 651)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    result, log = run_component(game, 652)
    assert result.returncode == 0 and "SKIPPING:" in log, log
    for component in (651, 650):
        result, log = run_component(game, component, uninstall=True)
        assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU or WEIDU_BIN")
@pytest.mark.parametrize("layout", ["vanilla", "modded_triggers_and_extra_block", "already_gated"])
def test_chapter_caps_gates_bainvi_bcs_and_preserves_unrelated_blocks(tmp_path, layout):
    from tests.test_recruitment_xp import decompile_script
    bainvi_baf = {
        "vanilla": BAINVI_VANILLA,
        "modded_triggers_and_extra_block": (
            'IF\n'
            '  Global("OtherModPrep","LOCALS",0)\n'
            'THEN\n'
            '  RESPONSE #100\n'
            '    SetGlobal("OtherModPrep","LOCALS",1)\n'
            '    Continue()\n'
            'END\n'
            'IF\n'
            '  Global("BA_START_SCENE","MYAREA",0)\n'
            '  XPGT(Player1,25000)\n'
            'THEN\n'
            '  RESPONSE #100\n'
            '    SetGlobal("BA_START_SCENE","MYAREA",1)\n'
            '    StartCutScene("CUTBA01")\n'
            'END\n'
        ),
        "already_gated": (
            'IF\n'
            '  GlobalGT("Chapter","GLOBAL",4)\n'
            '  Global("BA_START_SCENE","MYAREA",0)\n'
            'THEN\n'
            '  RESPONSE #100\n'
            '    SetGlobal("BA_START_SCENE","MYAREA",1)\n'
            '    StartCutScene("CUTBA01")\n'
            'END\n'
        ),
    }[layout]
    game = chapter_game(tmp_path, bainvi_baf)
    before = game_files(game)
    for component in (650, 652):
        result, log = run_component(game, component)
        assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    patched = decompile_script(game, "BAINVI")
    assert patched.count(CHAPTER_GATE) == 1
    assert 'StartCutScene("CUTBA01")' in patched
    if layout == "modded_triggers_and_extra_block":
        assert 'Global("OtherModPrep","LOCALS",0)' in patched
        assert 'XPGT(Player1,25000)' in patched
    for component in (652, 650):
        result, log = run_component(game, component, uninstall=True)
        assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU or WEIDU_BIN")
@pytest.mark.parametrize("layout", sorted(UNRECOGNISED_BAINVI))
def test_chapter_caps_install_and_warn_when_bainvi_has_no_known_entrance(tmp_path, layout):
    # The caps do not depend on the Baeloth gate: an unrecognised BAINVI.BCS stays
    # byte-identical, the installer warns, and the chapter caps still install.
    game = chapter_game(tmp_path, UNRECOGNISED_BAINVI[layout])
    original = (game.override / "bainvi.bcs").read_bytes()
    before = game_files(game)
    result, log = run_component(game, 650)
    assert result.returncode == 0 and "SUCCESSFULLY INSTALLED" in log, log
    base = game_files(game)
    result, log = run_component(game, 652)
    # WeiDU exits with 3 after a component installed with warnings.
    assert result.returncode == 3 and "INSTALLED WITH WARNINGS" in log, log
    assert NO_GATE_WARNING in log, log
    assert NO_GATE_REASONS[layout] in log, log
    assert (game.override / "bainvi.bcs").read_bytes() == original
    expected = dict(base)
    expected["OVERRIDE/CBMBKCFG.LUA"] = (SOURCE / "cbmbkchp.lua").read_bytes()
    assert game_files(game) == expected
    for component in (652, 650):
        result, log = run_component(game, component, uninstall=True)
        assert result.returncode == 0 and "SUCCESSFULLY REMOVED" in log, log
    assert game_files(game) == before
