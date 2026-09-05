"""Run the production Lua in both engine-compatible Lua and LuaJIT runtimes."""
from importlib import import_module
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "chriz-bg-modpack/utility-xp"


@pytest.fixture(params=["lua51", "luajit21"])
def lua(request):
    runtime = import_module("lupa." + request.param).LuaRuntime(unpack_returned_tuples=True)
    for name in ("CBMUXPC.lua", "CBMUXP.lua"):
        runtime.execute((SOURCE / name).read_text(encoding="utf-8"))
    runtime.globals().CBM_UtilityXP.Validate(runtime.globals().CBM_UtilityXP_Config)
    return runtime


@pytest.mark.parametrize("xp,lock,trap,spell1,spell9", [
    (0, 30, 10, 10, 90),
    (10000, 30, 10, 10, 90),
    (40000, 50, 100, 50, 450),
    (89000, 150, 500, 250, 2250),
    (161000, 400, 1750, 500, 4500),
    (290500, 660, 2220, 740, 6590),
    (440000, 950, 2750, 1000, 9000),
    (1320000, 1550, 3250, 1000, 9000),
    (8000000, 1550, 3250, 1000, 9000),
])
def test_balance_checkpoints(lua, xp, lock, trap, spell1, spell9):
    g = lua.globals()
    result = g.CBM_UtilityXP.Rewards(g.CBM_UtilityXP_Config, xp)
    assert (result.lock, result.trap, result.spells[1], result.spells[9]) == (
        lock, trap, spell1, spell9)


def test_interpolation_and_independent_multipliers(lua):
    lua.execute("""
        CBM_UtilityXP_Config.lockMultiplier = 2
        CBM_UtilityXP_Config.trapMultiplier = 0
        CBM_UtilityXP_Config.scribeMultiplier = 1.5
        result = CBM_UtilityXP.Rewards(CBM_UtilityXP_Config, 125000)
    """)
    result = lua.globals().result
    assert (result.lock, result.trap, result.spells[4]) == (550, 0, 2250)


@pytest.mark.parametrize("step,mode,spell1,spell5", [
    (10, "up", 740, 3670),
    (10, "nearest", 730, 3660),
    (100, "up", 800, 3700),
    (1, "nearest", 732, 3660),
    (None, None, 732, 3660),  # configs saved before rounding settings existed
])
def test_configurable_rounding_happens_after_spell_level_multiplication(
        lua, step, mode, spell1, spell5):
    g = lua.globals()
    config = g.CBM_UtilityXP_Config
    config.roundingStep, config.roundingMode = step, mode
    g.CBM_UtilityXP.Validate(config)
    result = g.CBM_UtilityXP.Rewards(config, 290500)
    assert (result.spells[1], result.spells[5]) == (spell1, spell5)


def test_upward_rounding_keeps_zero_disabled_and_changes_awards_by_less_than_step(lua):
    g = lua.globals()
    config = g.CBM_UtilityXP_Config
    config.trapMultiplier = 0
    # Known raw rewards at the tested save: 655.2867 lock, 732.0789 per spell level.
    result = g.CBM_UtilityXP.Rewards(config, 290500)
    assert result.trap == 0
    assert 655.2867 <= result.lock < 665.2867
    assert 732.0789 <= result.spells[1] < 742.0789


def test_rewards_never_drop_at_boundaries(lua):
    lua.execute("""
        for _, a in ipairs(CBM_UtilityXP_Config.anchors) do
            if a.xp > 0 then
                local before = CBM_UtilityXP.Rewards(CBM_UtilityXP_Config, a.xp - 1)
                local after = CBM_UtilityXP.Rewards(CBM_UtilityXP_Config, a.xp + 1)
                assert(before.lock <= after.lock and before.trap <= after.trap)
                for level = 1, 9 do assert(before.spells[level] <= after.spells[level]) end
            end
        end
    """)


@pytest.mark.parametrize("change", [
    "anchors[1].xp = 1", "anchors[2].xp = 0", "anchors[3].xp = 10.5",
    "anchors[3].trap = -1", "anchors[4].lock = 1", "scribeMultiplier = 0/0",
    "lockMultiplier = math.huge", "trapMultiplier = -1",
    "anchors[7].scribe = 2147483647",
    "roundingStep = 0", "roundingStep = -10", "roundingStep = 2.5",
    "roundingStep = math.huge", "roundingStep = 0/0", "roundingStep = '10'",
    "roundingStep = false",
    "roundingMode = 'down'", "roundingMode = false",
    "anchors[7].lock = 2147483640.5",  # only rounding overflows the engine integer
])
def test_invalid_custom_config_is_rejected(lua, change):
    lua.execute("CBM_UtilityXP_Config." + change)
    ok, _ = lua.eval("pcall(CBM_UtilityXP.Validate, CBM_UtilityXP_Config)")
    assert not ok


@pytest.mark.parametrize("class_id,levels", [
    (4, [10, 0, 0]), (9, [7, 8, 0]), (10, [6, 6, 7]), (13, [7, 8, 0]),
    (7, [7, 7, 0]), (8, [7, 7, 0]), (14, [7, 7, 0]), (15, [7, 8, 0]),
    (16, [7, 8, 0]), (17, [6, 6, 6]), (18, [7, 6, 0]),
])
def test_single_and_multi_use_total_xp_without_level_multiplication(lua, class_id, levels):
    result = lua.globals().CBM_UtilityXP.LifetimeXP(
        161000, 0x400000, class_id, lua.table_from(levels),
        lua.eval("function() error('non-dual must not consult XPLEVEL') end"))
    assert result == 161000


@pytest.mark.parametrize("class_id,flags,levels,expected_class,expected_level,threshold", [
    (13, 64, [9, 4, 0], "THIEF", 4, 5000),  # Nalia: retired thief in slot 2
    (13, 16, [7, 9, 0], "MAGE", 7, 60000),  # Mage -> thief, reversed direction
    (9, 8, [9, 10, 0], "FIGHTER", 9, 250000),
    (9, 64, [10, 7, 0], "THIEF", 7, 40000),
    (7, 8, [9, 10, 0], "FIGHTER", 9, 250000),
    (7, 16, [10, 9, 0], "MAGE", 9, 135000),
    (14, 32, [7, 8, 0], "CLERIC", 7, 55000),
    (18, 256, [9, 7, 0], "RANGER", 7, 75000),
    (16, 128, [10, 9, 0], "DRUID", 9, 90000),
    (8, 8, [7, 8, 0], "FIGHTER", 7, 64000),
    (8, 32, [8, 7, 0], "CLERIC", 7, 55000),
    (14, 16, [8, 7, 0], "MAGE", 7, 60000),
    (15, 32, [7, 8, 0], "CLERIC", 7, 55000),
    (15, 64, [8, 7, 0], "THIEF", 7, 40000),
    (16, 8, [7, 8, 0], "FIGHTER", 7, 64000),
    (18, 32, [7, 8, 0], "CLERIC", 7, 55000),
])
def test_duals_restore_only_the_original_class_contribution(
        lua, class_id, flags, levels, expected_class, expected_level, threshold):
    calls = []

    def lookup(class_name, level):
        calls.append((class_name, level))
        return threshold

    result = lua.globals().CBM_UtilityXP.LifetimeXP(
        161000, flags | 0x400000, class_id, lua.table_from(levels), lookup)
    assert result == 161000 + threshold
    assert calls == [(expected_class, expected_level)]


def test_dual_downtime_and_reactivation_share_same_progression(lua):
    g = lua.globals()
    old = lua.eval("function() return 250000 end")
    # Retired Fighter 9 contributes during new-class downtime and after reactivation.
    downtime = g.CBM_UtilityXP.LifetimeXP(10000, 8, 9, lua.table_from([9, 5, 0]), old)
    active = g.CBM_UtilityXP.LifetimeXP(160000, 8, 9, lua.table_from([9, 10, 0]), old)
    assert (downtime, active) == (260000, 410000)


def test_missing_dual_threshold_fails_instead_of_resetting_progression(lua):
    ok, error = lua.eval("""pcall(function()
        return CBM_UtilityXP.LifetimeXP(161000, 64, 13, {9, 4, 0}, function() return nil end)
    end)""")
    assert not ok and "threshold" in error


# A row-major C2DArray double with native zero-based indexing and bounds checks.
# It models CString ownership; the production adapter must use SetFromChars.
ENGINE_DOUBLE = """
logs = {}
print = function(message) logs[#logs + 1] = message end
listeners = {}
EEex_Menu_AddAfterMainFileLoadedListener = function(f) listeners.menu = f end
EEex_GameState_AddInitializedListener = function(f) listeners.init = f end
EEex_Menu_AddAfterMainFileReloadedListener = function(f) listeners.reload = f end
EEex_GameState_AddDestroyedListener = function(f) listeners.destroy = f end
EEex_Action_AddSpriteStartedActionListener = function(f) listeners.action = f end
EEex_Menu_LoadFile = function(name) loadedMenu = name end
Infinity_PushMenu = function(name) pushedMenu = name end
EEex_UDToPtr = function(array) return array.pointer end

function makeTable(width, pointer, levelColumns)
    levelColumns = levelColumns or width
    local labels = { 'PICK_LOCK', 'DISARM_TRAP', 'LEARN_SPELL', 'FOREIGN_ROW' }
    local t = { m_nSizeX = width, m_nSizeY = 4, writes = 0, cells = {} }
    t.m_pArray = { pointer = pointer }
    for i = 0, width * 4 - 1 do
        local cell = { value = i % width < levelColumns and tostring(100000 + i) or '' }
        cell.m_pchData = { get = function() return cell.value end }
        function cell:SetFromChars(text)
            t.writes = t.writes + 1
            self.value = text
        end
        t.cells[i] = cell
    end
    function t.m_pArray:getReference(index)
        assert(index >= 0 and index < width * 4, 'out of bounds native write')
        return t.cells[index]
    end
    function t:findRowLabel(name)
        for i, label in ipairs(labels) do if label == name then return i - 1 end end
        return -1
    end
    function t:getColumnLabel(index)
        assert(index >= 0 and index < width, 'out of bounds native column label')
        return index < levelColumns and tostring(index + 1) or ''
    end
    return t
end

xpLoads = 0
EEex_Resource_Load2DA = function(name)
    assert(name == 'XPLEVEL')
    xpLoads = xpLoads + 1
    return { getAtLabels = function(self, column, row)
        assert(column == '4' and row == 'THIEF')
        return '5000'
    end }
end
hero = { m_baseStats = {m_xp = 161000, m_flags = 0, m_level1 = 10,
    m_level2 = 0, m_level3 = 0}, m_typeAI = {m_Class = 4} }
other = { m_baseStats = {m_xp = 8000000}, m_typeAI = {m_Class = 13} }
EEex_GameObject_Get = function(id)
    if id == 42 then return hero elseif id == 99 then return other end
end
game = { m_nCharacters = 2,
    m_characters = {get = function(self, index) assert(index == 0) return 42 end},
    m_charactersPortrait = {get = function(self, index) return 99 end},
    m_ruleTables = { m_tXPBonus = makeTable(50, 1234) } }
EngineGlobals = { g_pBaldurChitin = {m_pObjectGame = game} }
"""


def start_adapter(lua):
    lua.execute(ENGINE_DOUBLE)
    lua.execute((SOURCE / "CBMUXRT.lua").read_text(encoding="utf-8"))
    return lua.globals()


@pytest.mark.parametrize("width", [40, 50, 80])
def test_adapter_writes_all_existing_levels_and_preserves_other_cells(lua, width):
    g = start_adapter(lua)
    lua.execute(f"game.m_ruleTables.m_tXPBonus = makeTable({width}, 6789)")
    assert g.CBM_UtilityXP_Runtime.Refresh() is False
    table = g.game.m_ruleTables.m_tXPBonus
    for col in range(width):
        assert table.cells[col].value == "400"
        assert table.cells[width + col].value == "1750"
        if col < 9:
            assert table.cells[2 * width + col].value == str(500 * (col + 1))
        else:
            assert table.cells[2 * width + col].value == str(100000 + 2 * width + col)
        assert table.cells[3 * width + col].value == str(100000 + 3 * width + col)
    assert g.xpLoads == 0  # pure/multi protagonists need no XPLEVEL load


@pytest.mark.parametrize("padding_columns", [1, 3])
def test_adapter_uses_allocated_row_stride_but_preserves_trailing_blank_columns(
        lua, padding_columns):
    g = start_adapter(lua)
    width = 50 + padding_columns
    lua.execute(f"game.m_ruleTables.m_tXPBonus = makeTable({width}, 6789, 50)")
    table = g.game.m_ruleTables.m_tXPBonus
    expected = [table.cells[index].value for index in range(width * 4)]
    # Only named levels are rewards. The extra native allocation remains blank
    # in every row; spell levels above 9 and the foreign row remain byte-exact.
    for column in range(50):
        expected[column] = "400"
        expected[width + column] = "1750"
        if column < 9:
            expected[2 * width + column] = str(500 * (column + 1))

    assert g.CBM_UtilityXP_Runtime.Refresh() is False

    assert g.CBM_UtilityXP_Runtime.lastError is None
    assert table.writes == 109
    assert [table.cells[index].value for index in range(width * 4)] == expected


@pytest.mark.parametrize("column,label", [(0, ""), (8, ""), (24, ""), (24, "27")])
def test_adapter_rejects_interior_blank_or_gapped_columns_before_any_write(
        lua, column, label):
    g = start_adapter(lua)
    lua.execute("""
        game.m_ruleTables.m_tXPBonus = makeTable(53, 6789, 50)
        originalColumnLabel = game.m_ruleTables.m_tXPBonus.getColumnLabel
    """)
    lua.execute(f"""
        game.m_ruleTables.m_tXPBonus.getColumnLabel = function(self, index)
            if index == {column} then return '{label}' end
            return originalColumnLabel(self, index)
        end
    """)
    table = g.game.m_ruleTables.m_tXPBonus
    before = [table.cells[index].value for index in range(53 * 4)]

    g.CBM_UtilityXP_Runtime.Refresh()

    assert table.writes == 0
    assert [table.cells[index].value for index in range(53 * 4)] == before
    assert len(g.logs) == 1
    assert "columns" in g.CBM_UtilityXP_Runtime.lastError


def test_frame_and_action_refreshes_do_not_accumulate_awards_or_writes(lua):
    g = start_adapter(lua)
    for _ in range(5):
        g.CBM_UtilityXP_Runtime.Refresh()
        g.listeners.action()
    assert g.game.m_ruleTables.m_tXPBonus.writes == 109
    assert g.hero.m_baseStats.m_xp == 161000


def test_paused_inventory_callback_refreshes_scribing_after_xp_changes(lua):
    g = start_adapter(lua)
    g.CBM_UtilityXP_Runtime.Refresh()
    g.hero.m_baseStats.m_xp = 440000
    # The actual .menu enabled callback is independent of world/AI ticks.
    menu = (SOURCE / "CBMUXP.menu").read_text(encoding="utf-8")
    callback = menu.split('enabled "', 1)[1].split('"', 1)[0]
    assert lua.eval(callback) is False
    assert g.game.m_ruleTables.m_tXPBonus.cells[108].value == "9000"


@pytest.mark.parametrize("new_caster_class", [1, 5])  # Mage and Bard
def test_new_caster_catchup_uses_bg2_rates_for_low_level_spells(lua, new_caster_class):
    g = start_adapter(lua)
    g.hero.m_baseStats.m_xp = 440000
    g.other.m_baseStats.m_xp = 0
    g.other.m_typeAI.m_Class = new_caster_class
    g.CBM_UtilityXP_Runtime.Refresh()
    cells = g.game.m_ruleTables.m_tXPBonus.cells
    low_level_rewards = [int(cells[100 + level].value) for level in range(5)]
    assert low_level_rewards == [1000, 2000, 3000, 4000, 5000]
    # Illustrative catch-up library: ten spells at each of levels 1-5.
    assert sum(low_level_rewards) * 10 == 150000


def test_loading_low_xp_save_replaces_high_rewards_even_with_reused_pointer(lua):
    g = start_adapter(lua)
    g.hero.m_baseStats.m_xp = 8000000
    g.CBM_UtilityXP_Runtime.Refresh()
    g.listeners.destroy()
    g.hero.m_baseStats.m_xp = 0
    g.CBM_UtilityXP_Runtime.Refresh()
    assert g.game.m_ruleTables.m_tXPBonus.cells[0].value == "30"
    assert g.game.m_ruleTables.m_tXPBonus.cells[108].value == "90"


def test_loading_same_xp_save_reapplies_after_table_reinitialized(lua):
    g = start_adapter(lua)
    g.CBM_UtilityXP_Runtime.Refresh()
    g.listeners.destroy()
    lua.execute("game.m_ruleTables.m_tXPBonus = makeTable(50, 1234)")
    g.CBM_UtilityXP_Runtime.Refresh()
    assert g.game.m_ruleTables.m_tXPBonus.cells[0].value == "400"


def test_new_table_storage_reapplies_even_without_session_reset(lua):
    g = start_adapter(lua)
    g.CBM_UtilityXP_Runtime.Refresh()
    lua.execute("game.m_ruleTables.m_tXPBonus = makeTable(50, 9876)")
    g.CBM_UtilityXP_Runtime.Refresh()
    assert g.game.m_ruleTables.m_tXPBonus.cells[0].value == "400"


def test_native_dual_fields_and_installed_xplevel_lookup(lua):
    g = start_adapter(lua)
    lua.execute("""
        hero.m_baseStats.m_flags = 64
        hero.m_baseStats.m_level1 = 9
        hero.m_baseStats.m_level2 = 4
        hero.m_typeAI.m_Class = 13
    """)
    g.CBM_UtilityXP_Runtime.Refresh()
    assert g.CBM_UtilityXP_Runtime.lastXP == 166000
    assert g.xpLoads == 1
    g.listeners.destroy()
    g.CBM_UtilityXP_Runtime.Refresh()
    assert g.xpLoads == 2


def test_no_party_or_unavailable_player1_leaves_table_alone(lua):
    g = start_adapter(lua)
    g.game.m_nCharacters = 0
    g.CBM_UtilityXP_Runtime.Refresh()
    g.game.m_nCharacters = 1
    lua.execute("hero = nil")
    g.CBM_UtilityXP_Runtime.Refresh()
    assert g.game.m_ruleTables.m_tXPBonus.writes == 0


def test_bad_table_is_rejected_before_any_write_and_reported_once(lua):
    g = start_adapter(lua)
    lua.execute("game.m_ruleTables.m_tXPBonus.getColumnLabel = function() return 'BAD' end")
    g.CBM_UtilityXP_Runtime.Refresh()
    g.CBM_UtilityXP_Runtime.Refresh()
    assert g.game.m_ruleTables.m_tXPBonus.writes == 0
    assert len(g.logs) == 1
    assert "columns" in g.CBM_UtilityXP_Runtime.lastError


def test_menu_load_and_reload_use_namespaced_hidden_menu(lua):
    g = start_adapter(lua)
    g.listeners.menu()
    g.listeners.init()
    g.listeners.reload()
    assert g.loadedMenu == "CBMUXP"
    assert g.pushedMenu == "CBM_UtilityXP_Tick"


@pytest.mark.parametrize("mode", ["inactive", "old_api", "invalid_config"])
def test_bootstrap_reports_unavailable_runtime_or_bad_config_without_publishing(lua, mode):
    lua.execute(ENGINE_DOUBLE)
    g = lua.globals()
    g.EEex_Active = mode != "inactive"
    if mode == "old_api":
        g.EEex_Menu_AddAfterMainFileLoadedListener = None

    def include(name):
        lua.execute((SOURCE / (name + ".lua")).read_text(encoding="utf-8"))
        if mode == "invalid_config" and name == "CBMUXPC":
            lua.execute("CBM_UtilityXP_Config.trapMultiplier = -1")

    g.Infinity_DoFile = include
    lua.execute((SOURCE / "M_CBMUXP.lua").read_text(encoding="utf-8"))
    assert len(g.logs) == 1
    assert g.game.m_ruleTables.m_tXPBonus.writes == 0
    assert g.listeners.menu is None
