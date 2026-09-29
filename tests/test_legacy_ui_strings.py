"""Component 640: real WeiDU output and pre-provider Lua bootstrap behavior."""
from importlib import import_module
from types import SimpleNamespace
import subprocess

import pytest

from tests.test_sarah_options import (
    SyntheticSarahGame, file_tree, find_weidu,
)


BEGIN = "-- CBM_LEGACY_UI_STRINGS_BEGIN"
END = "-- CBM_LEGACY_UI_STRINGS_END"
UTIL = b"-- Existing utility functions and arbitrary non-ASCII bytes: \xc3\xa9\r\n" \
       b"function getUiString(key) return key end\r\n"


@pytest.fixture(scope="module")
def weidu():
    executable = find_weidu()
    if not executable:
        pytest.skip("Set WEIDU_BIN to run the real installer")
    return executable


def make_game(path, source=UTIL):
    game = SyntheticSarahGame(SimpleNamespace(name=str(path)), complete=False)
    if source is not None:
        (game.override / "util.lua").write_bytes(source)
    # Provider resources remain byte-for-byte untouched. The helper must be in
    # UTIL itself, before any provider calls or captures the old global.
    (game.override / "ui.menu").write_bytes(b"provider menu sentinel")
    (game.override / "m_dui.lua").write_bytes(b"provider bootstrap sentinel")
    return game


@pytest.fixture(scope="module")
def installed_guard(tmp_path_factory, weidu):
    game = make_game(tmp_path_factory.mktemp("legacy-ui-lua"))
    result = game.run(weidu, "--force-install-list", 640)
    assert result.returncode == 0, game.transcript(result)
    assert "SUCCESSFULLY INSTALLED" in game.transcript(result)
    source = (game.override / "util.lua").read_text(encoding="utf-8")
    assert source.count(BEGIN) == 1
    assert source.count(END) == 1
    return source[source.index(BEGIN):source.index(END) + len(END)]


@pytest.fixture(params=["lua51", "luajit21"])
def lua(request):
    return import_module("lupa." + request.param).LuaRuntime(
        unpack_returned_tuples=True)


@pytest.mark.parametrize("source", [
    UTIL,
    b"function t(key) return key end",  # No terminal newline.
    b"t = function(key) return key end\n",  # Assignment declaration.
])
def test_public_install_changes_only_util_and_uninstalls_exactly(
        tmp_path, weidu, source):
    game = make_game(tmp_path, source)
    baseline = file_tree(game.override)
    result = game.run(weidu, "--force-install-list", 640)
    assert result.returncode == 0, game.transcript(result)
    assert "SUCCESSFULLY INSTALLED" in game.transcript(result)
    installed = file_tree(game.override)
    assert set(installed) == set(baseline)
    assert installed["UTIL.LUA"].startswith(source)
    assert installed["UTIL.LUA"].count(BEGIN.encode()) == 1
    assert {k: v for k, v in installed.items() if k != "UTIL.LUA"} == {
        k: v for k, v in baseline.items() if k != "UTIL.LUA"}
    result = game.run(weidu, "--force-uninstall-list", 640)
    assert result.returncode == 0, game.transcript(result)
    assert file_tree(game.override) == baseline


def test_missing_util_is_reported_without_publishing_any_files(tmp_path, weidu):
    game = make_game(tmp_path, None)
    baseline = file_tree(game.override)
    result = game.run(weidu, "--force-install-list", 640)
    assert "SKIPPING" in game.transcript(result)
    assert "UTIL.LUA" in game.transcript(result)
    assert file_tree(game.override) == baseline


def test_direct_reapplication_adds_only_one_guard(tmp_path, weidu):
    game = make_game(tmp_path)
    baseline = file_tree(game.override)
    harness = game.root / "legacy-ui-test.tp2"
    harness.write_text(
        'BACKUP ~legacy-ui-test-backup~\nAUTHOR ~fixture~\n'
        'BEGIN ~Repeated helper inclusion~\n'
        'INCLUDE ~chriz-bg-modpack/lib/cbm_legacy_ui_strings.tpa~\n'
        'REINCLUDE ~chriz-bg-modpack/lib/cbm_legacy_ui_strings.tpa~\n',
        encoding="utf-8")
    result = subprocess.run(
        [weidu, str(harness), "--no-auto-tp2", "--game", str(game.root),
         "--force-install-list", "0", "--use-lang", "en_us", "--no-exit-pause"],
        cwd=game.root, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    installed = (game.override / "util.lua").read_bytes()
    assert installed.startswith(baseline["UTIL.LUA"])
    assert installed.count(BEGIN.encode()) == 1
    assert installed.count(END.encode()) == 1


@pytest.mark.parametrize("declaration", [
    "function getUiString(...) return ... end",
    "getUiString = function(...) return ... end",
    '_G["getUiString"] = function(...) return ... end',
])
def test_modern_helper_becomes_exact_legacy_alias_without_being_called(
        lua, installed_guard, declaration):
    lua.execute(declaration)
    lua.execute(installed_guard)
    assert lua.eval("t == getUiString")
    assert lua.eval('t("localized", 7, false)') == ("localized", 7, False)
    lua.execute(installed_guard)
    assert lua.eval("t == getUiString")


@pytest.mark.parametrize("modern", ["nil", "false", "function() error('unused') end"])
@pytest.mark.parametrize("legacy", [
    "function t(...) return ... end",
    "t = function(...) return ... end",
])
def test_existing_legacy_function_and_wrappers_are_preserved(
        lua, installed_guard, modern, legacy):
    lua.execute(legacy + "\noriginal = t\ngetUiString = " + modern)
    lua.execute(installed_guard)
    assert lua.eval("t == original")
    assert lua.eval('t("older game", 4)') == ("older game", 4)


@pytest.mark.parametrize("legacy", ["nil", "false", "0", '"bad"', "{}"])
def test_non_callable_legacy_value_uses_callable_modern_helper(
        lua, installed_guard, legacy):
    lua.execute("t = " + legacy + "\ngetUiString = function(key) return key end")
    lua.execute(installed_guard)
    assert lua.eval("t == getUiString")


@pytest.mark.parametrize("source", [
    "-- function t(key) return key end\n-- function getUiString(key) return key end",
    "t = false; getUiString = {}",
    "local function t() end; local function getUiString() end",
])
def test_missing_helpers_fail_with_clear_error_even_when_comments_name_them(
        lua, installed_guard, source):
    result = lua.eval("function(source) return pcall(assert(loadstring(source))) end")(
        source + "\n" + installed_guard)
    assert result[0] is False
    assert "component 640" in result[1]
    assert "neither a callable t nor getUiString" in result[1]


def test_bootstrap_does_not_call_translation_before_catalog_is_ready(
        lua, installed_guard):
    lua.execute("""
        calls = 0
        function getUiString(key)
            calls = calls + 1
            assert(uiStrings, 'catalog not ready')
            return uiStrings[key]
        end
    """)
    lua.execute(installed_guard)
    assert lua.eval("calls") == 0
    lua.execute('uiStrings = {DONE_BUTTON = "Localized Done"}')
    assert lua.eval('t("DONE_BUTTON")') == "Localized Done"
    assert lua.eval("calls") == 1


def test_dragonspear_capture_keeps_working_before_and_after_lazy_translation(
        lua, installed_guard):
    # Model the lifecycle of pinned DragonspearUI d86bddd M_dui.lua:21-42:
    # capture t, tolerate an absent catalog, then restore t after translating it.
    lua.execute("""
        function getUiString(key)
            return uiStrings and uiStrings[key] or 'not ready'
        end
    """)
    lua.execute(installed_guard)
    lua.execute("""
        __t = t
        function t(key)
            if not uiStrings then return __t(key) end
            uiStrings.DONE_BUTTON = 'Dragonspear translated'
            t, __t = __t, nil
            return t(key)
        end
        provider_wrapper = t
    """)
    assert lua.eval("__t == getUiString")
    assert lua.eval('t("DONE_BUTTON")') == "not ready"
    # Even if a later UTIL reload reaches this block, preserve the wrapper.
    lua.execute(installed_guard)
    assert lua.eval("t == provider_wrapper")
    lua.execute('uiStrings = {DONE_BUTTON = "Default Done"}')
    assert lua.eval('t("DONE_BUTTON")') == "Dragonspear translated"
    assert lua.eval("t == getUiString and __t == nil")
    assert lua.eval('t("DONE_BUTTON")') == "Dragonspear translated"


def test_hgo_alias_remains_the_same_function(lua, installed_guard):
    lua.execute("getUiString = function(key) return key end; t = getUiString")
    lua.execute(installed_guard)
    assert lua.eval("t == getUiString")
