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


def test_package_matches_canonical_sources_and_six_reviewed_binaries():
    manifest = package.check()
    assert manifest["status"] == "experimental-unreleased"
    native = {Path(name).name for name in manifest["files"] if name.startswith("native/")}
    assert native == package.NATIVE
    assert "cbmbank_identity_only.dll" not in native
    for path in SOURCE.rglob("*.lua"):
        assert "cbm-bank-trial" not in path.read_text(), path
    assert all(len(Path(name).stem) <= 8 for name in PUBLICATIONS)
    tp2 = (ROOT / SETUP_NAME).read_text()
    for number in (650, 651):
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
@pytest.mark.parametrize("config,policy", [("cbmbkcfg.lua", "bg1_sod"), ("cbmbksoa.lua", "bg1_sod_soa")])
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
