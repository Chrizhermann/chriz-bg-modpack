"""Exercise story-phase utility XP with Lua 5.1 and LuaJIT engine doubles."""
from importlib import import_module
from pathlib import Path

import pytest

from test_utility_xp import ENGINE_DOUBLE


SOURCE = Path(__file__).resolve().parents[1] / "chriz-bg-modpack/story-utility-xp"
PURE = "cbmsxp.lua"
ADAPTER = "cbmsxrt.lua"
BOOTSTRAP = "m_cbmsxp.lua"
MENU = "cbmsxp.menu"


@pytest.fixture(params=["lua51", "luajit21"])
def lua(request):
    runtime = import_module("lupa." + request.param).LuaRuntime(
        unpack_returned_tuples=True)
    runtime.execute((SOURCE / PURE).read_text(encoding="utf-8"))
    return runtime


def phase(lua, campaign, end_bg1, in_tob):
    return lua.eval("""function(campaign, ending, tob)
        local mode, reason = CBM_StoryXP.Phase(campaign, ending, tob)
        return mode, reason
    end""")(campaign, end_bg1, in_tob)


@pytest.mark.parametrize("campaign,ending,tob,expected", [
    ("BG1", 0, 0, "bg1"), ("BG1", 1, 0, "bg1"),
    ("SOD", 0, 0, "bg1"), ("SOD", 1, 0, "bg1"),
    ("BG1", 2, 0, "bg2"), ("SOD", 2, 0, "bg2"),
    ("SOA", 2, 0, "bg2"), ("TOB", 2, 0, "bg2"),
    ("BG1", 0, 1, "bg2"), ("SOD", 1, 1, "bg2"),
    ("SOA", 0, 1, "bg2"), ("TOB", 0, 1, "bg2"),
])
def test_phase_uses_supported_campaign_and_transition_flags(
        lua, campaign, ending, tob, expected):
    assert phase(lua, campaign, ending, tob)[0] == expected


@pytest.mark.parametrize("campaign,ending", [
    ("SOA", 0), ("SOA", 1), ("TOB", 0), ("TOB", 1),
])
def test_uninitialized_later_campaign_is_pending(lua, campaign, ending):
    mode, reason = phase(lua, campaign, ending, 0)
    assert mode is None
    assert isinstance(reason, str) and reason


@pytest.mark.parametrize("campaign", ["BP1", "TUT", "UNKNOWN", "", None])
@pytest.mark.parametrize("ending,tob", [(0, 0), (2, 0), (2, 1)])
def test_unsupported_campaign_cannot_be_enabled_by_transition_flags(
        lua, campaign, ending, tob):
    mode, reason = phase(lua, campaign, ending, tob)
    assert mode is None
    assert isinstance(reason, str) and reason


@pytest.mark.parametrize("ending,tob", [
    (-1, 0), (3, 0), (0.5, 0), (None, 0), ("2", 0), (True, 0),
    (0, -1), (0, 2), (0, 0.5), (0, None), (0, "1"), (0, True),
    (3, 1),  # ToB priority does not excuse corrupt flags.
])
def test_malformed_phase_flags_are_rejected(lua, ending, tob):
    mode, reason = phase(lua, "BG1", ending, tob)
    assert mode is None
    assert isinstance(reason, str) and reason


@pytest.mark.parametrize("mode,locks,traps,multiplier", [
    ("bg1", [25, 40, 95, 155], [10, 17, 27, 32], 10),
    ("bg2", [250, 400, 950, 1550], [1000, 1750, 2750, 3250], 1000),
])
def test_native_reward_brackets_and_scribe_level_limit(
        lua, mode, locks, traps, multiplier):
    for level in (1, 5, 6, 9, 10, 11, 15, 16, 40, 50, 80):
        bracket = min((level - 1) // 5, 3)
        result = lua.globals().CBM_StoryXP.Rewards(mode, level)
        assert (result.lock, result.trap, result.scribe) == (
            locks[bracket], traps[bracket],
            multiplier * level if level <= 9 else 0)


STORY_DOUBLE = """
campaign = 'BG1'
storyGlobals = { EndOfBG1 = 0, InToB = 0, Chapter = 7 }
globalReads = {}
game.m_sCurrentCampaign = {
    m_pchData = {get = function() return campaign end}
}
EEex_GameState_GetGlobalInt = function(name)
    globalReads[#globalReads + 1] = name
    local labels = {ENDOFBG1 = 'EndOfBG1', INTOB = 'InToB'}
    assert(labels[name], 'unexpected story input: ' .. name)
    return storyGlobals[labels[name]]
end
baselineLoads = 0
baselineReads = {}
baselineFault = nil
local baselineRows = { PICK_LOCK = 700, DISARM_TRAP = 800, LEARN_SPELL = 900 }
function baselineValue(column, row)
    assert(type(column) == 'string' and tonumber(column), 'column-label order')
    assert(baselineRows[row], 'row-label order')
    return tostring(baselineRows[row] + tonumber(column))
end
EEex_Resource_Load2DA = function(name)
    assert(name == 'XPBONUS', 'must not consult protagonist XP or class tables')
    baselineLoads = baselineLoads + 1
    return {getAtLabels = function(self, column, row)
        baselineReads[#baselineReads + 1] = column .. ':' .. row
        if baselineFault and column == baselineFault.column and row == baselineFault.row then
            return baselineFault.value
        end
        return baselineValue(column, row)
    end}
end
EEex_GameObject_Get = function() error('story rewards do not inspect actor XP or class') end
game.m_characters.get = function() error('story rewards do not inspect party members') end
"""


def start_adapter(lua, campaign="BG1", ending=0, tob=0):
    lua.execute(ENGINE_DOUBLE)
    lua.execute(STORY_DOUBLE)
    set_phase(lua, campaign, ending, tob)
    lua.execute((SOURCE / ADAPTER).read_text(encoding="utf-8"))
    return lua.globals()


def set_phase(lua, campaign, ending, tob):
    g = lua.globals()
    g.campaign = campaign
    g.storyGlobals.EndOfBG1 = ending
    g.storyGlobals.InToB = tob


def values(table):
    return [table.cells[index].value
            for index in range(table.m_nSizeX * table.m_nSizeY)]


def expected_rewards(before, width, levels, mode, rows=(0, 1, 2)):
    expected = list(before)
    locks, traps, multiplier = (
        ([25, 40, 95, 155], [10, 17, 27, 32], 10) if mode == "bg1" else
        ([250, 400, 950, 1550], [1000, 1750, 2750, 3250], 1000))
    for column in range(levels):
        bracket = min(column // 5, 3)
        for row, value in zip(rows, (
                locks[bracket], traps[bracket],
                (column + 1) * multiplier if column < 9 else 0)):
            expected[row * width + column] = str(value)
    return expected


@pytest.mark.parametrize("width,levels", [(40, 40), (50, 50), (53, 50), (80, 80)])
@pytest.mark.parametrize("mode", ["bg1", "bg2"])
def test_adapter_changes_only_three_named_rows_and_preserves_padding(
        lua, width, levels, mode):
    g = start_adapter(lua, "BG1", 2 if mode == "bg2" else 0)
    lua.execute(f"game.m_ruleTables.m_tXPBonus = makeTable({width}, 6789, {levels})")
    table = g.game.m_ruleTables.m_tXPBonus
    before = values(table)
    assert g.CBM_StoryXP_Runtime.Refresh() is False
    assert values(table) == expected_rewards(before, width, levels, mode)
    assert table.writes == 3 * levels
    assert g.CBM_StoryXP_Runtime.lastError is None


def test_row_labels_are_resolved_instead_of_assuming_physical_order(lua):
    g = start_adapter(lua)
    lua.execute("""
        game.m_ruleTables.m_tXPBonus.findRowLabel = function(self, name)
            return ({ PICK_LOCK = 2, DISARM_TRAP = 0, LEARN_SPELL = 1 })[name] or -1
        end
    """)
    table = g.game.m_ruleTables.m_tXPBonus
    before = values(table)
    g.CBM_StoryXP_Runtime.Refresh()
    assert values(table) == expected_rewards(before, 50, 50, "bg1", rows=(2, 0, 1))


def test_story_progression_and_overlapping_chapter_numbers(lua):
    g = start_adapter(lua)
    table = g.game.m_ruleTables.m_tXPBonus
    before = values(table)
    for campaign, ending, tob, chapter, mode in (
        ("BG1", 0, 0, 7, "bg1"), ("SOD", 1, 0, 13, "bg1"),
        ("SOA", 2, 0, 13, "bg2"), ("TOB", 2, 1, 20, "bg2"),
    ):
        set_phase(lua, campaign, ending, tob)
        g.storyGlobals.Chapter = chapter
        g.CBM_StoryXP_Runtime.Refresh()
        assert values(table) == expected_rewards(before, 50, 50, mode)


@pytest.mark.parametrize("campaign", ["SOA", "TOB"])
def test_direct_later_campaign_waits_then_rechecks_initialized_flags(lua, campaign):
    g = start_adapter(lua, campaign)
    table = g.game.m_ruleTables.m_tXPBonus
    before = values(table)
    g.CBM_StoryXP_Runtime.Refresh()
    assert table.writes == 0 and values(table) == before
    set_phase(lua, campaign, 2 if campaign == "SOA" else 0, int(campaign == "TOB"))
    g.CBM_StoryXP_Runtime.Refresh()
    assert values(table) == expected_rewards(before, 50, 50, "bg2")


@pytest.mark.parametrize("campaign,ending,tob", [
    ("BP2", 2, 1), ("TUT", 0, 0), ("UNKNOWN", 2, 0), ("BG1", 3, 0),
])
def test_initial_unsupported_or_invalid_phase_does_not_touch_table(
        lua, campaign, ending, tob):
    g = start_adapter(lua, campaign, ending, tob)
    table = g.game.m_ruleTables.m_tXPBonus
    before = values(table)
    g.CBM_StoryXP_Runtime.Refresh()
    assert table.writes == 0 and values(table) == before


def test_repeated_frame_action_refreshes_never_add_xp_or_rewrite_cells(lua):
    g = start_adapter(lua)
    for _ in range(5):
        g.CBM_StoryXP_Runtime.Refresh()
        g.listeners.action()
    assert g.game.m_ruleTables.m_tXPBonus.writes == 150
    assert g.hero.m_baseStats.m_xp == 161000
    assert g.other.m_baseStats.m_xp == 8000000
    g.game.m_nCharacters = 6
    g.hero.m_baseStats.m_xp = 8000000
    g.hero.m_typeAI.m_Class = 13
    g.storyGlobals.Chapter = 13
    g.CBM_StoryXP_Runtime.Refresh()
    assert g.game.m_ruleTables.m_tXPBonus.writes == 150


def test_loading_bg1_after_bg2_replaces_rates_even_when_pointer_is_reused(lua):
    g = start_adapter(lua, "SOA", 2)
    table = g.game.m_ruleTables.m_tXPBonus
    before = values(table)
    g.CBM_StoryXP_Runtime.Refresh()
    g.listeners.destroy()
    set_phase(lua, "BG1", 0, 0)
    g.listeners.init()
    g.CBM_StoryXP_Runtime.Refresh()
    assert values(table) == expected_rewards(before, 50, 50, "bg1")


@pytest.mark.parametrize("reset,new_pointer,width,levels", [
    (True, 1234, 50, 50), (False, 9876, 50, 50), (False, 1234, 53, 50),
])
def test_new_table_or_reset_refreshes_layout_and_cached_phase(
        lua, reset, new_pointer, width, levels):
    g = start_adapter(lua)
    g.CBM_StoryXP_Runtime.Refresh()
    if reset:
        g.CBM_StoryXP_Runtime.Reset()
    lua.execute(f"game.m_ruleTables.m_tXPBonus = makeTable({width}, {new_pointer}, {levels})")
    table = g.game.m_ruleTables.m_tXPBonus
    before = values(table)
    g.CBM_StoryXP_Runtime.Refresh()
    assert values(table) == expected_rewards(before, width, levels, "bg1")


@pytest.mark.parametrize("reset", [False, True])
@pytest.mark.parametrize("campaign,ending,tob", [
    ("BP2", 2, 1), ("TUT", 0, 0), ("BG1", 3, 0), ("SOA", 0, 0),
])
def test_leaving_a_supported_phase_restores_resource_baseline_not_modified_memory(
        lua, reset, campaign, ending, tob):
    g = start_adapter(lua, "SOA", 2)
    lua.execute("game.m_ruleTables.m_tXPBonus = makeTable(53, 1234, 50)")
    table = g.game.m_ruleTables.m_tXPBonus
    expected = values(table)
    g.CBM_StoryXP_Runtime.Refresh()
    if reset:
        g.listeners.destroy()
    set_phase(lua, campaign, ending, tob)
    g.CBM_StoryXP_Runtime.Refresh()
    for row, offset in enumerate((700, 800, 900)):
        for column in range(50):
            expected[row * 53 + column] = str(offset + column + 1)
    assert values(table) == expected
    writes = table.writes
    g.CBM_StoryXP_Runtime.Refresh()
    assert table.writes == writes


@pytest.mark.parametrize("mutation", [
    "t.getColumnLabel = function(self, index) return index == 24 and '' or tostring(index + 1) end",
    "t.getColumnLabel = function(self, index) return index == 24 and '27' or tostring(index + 1) end",
    "t.findRowLabel = function(self, name) return name == 'LEARN_SPELL' and -1 or 0 end",
    "t.findRowLabel = function() return 4 end",
    "t.m_nSizeX = 8",
])
def test_malformed_table_is_rejected_before_any_partial_write(lua, mutation):
    g = start_adapter(lua)
    table = g.game.m_ruleTables.m_tXPBonus
    before = values(table)
    lua.execute("local t = game.m_ruleTables.m_tXPBonus; " + mutation)
    g.CBM_StoryXP_Runtime.Refresh()
    g.CBM_StoryXP_Runtime.Refresh()
    assert table.writes == 0
    assert [table.cells[index].value for index in range(200)] == before
    assert g.CBM_StoryXP_Runtime.lastError
    assert len(g.logs) == 1


def test_invalid_baseline_is_validated_before_restore_writes(lua):
    g = start_adapter(lua, "SOA", 2)
    g.CBM_StoryXP_Runtime.Refresh()
    table = g.game.m_ruleTables.m_tXPBonus
    before = values(table)
    lua.execute("baselineFault = { column = '50', row = 'LEARN_SPELL', value = 'BAD' }")
    g.CBM_StoryXP_Runtime.Reset()
    set_phase(lua, "BP2", 2, 1)
    writes = table.writes
    g.CBM_StoryXP_Runtime.Refresh()
    assert table.writes == writes and values(table) == before
    assert g.CBM_StoryXP_Runtime.lastError


def test_hidden_menu_callback_refreshes_without_world_ticks(lua):
    g = start_adapter(lua)
    g.listeners.menu()
    g.listeners.init()
    g.listeners.reload()
    assert g.loadedMenu == "CBMSXP"
    assert g.pushedMenu == "CBM_StoryXP_Tick"
    menu = (SOURCE / MENU).read_text(encoding="utf-8")
    callback = menu.split('enabled "', 1)[1].split('"', 1)[0]
    assert lua.eval(callback) is False
    set_phase(lua, "SOA", 2, 0)
    assert lua.eval(callback) is False
    assert g.game.m_ruleTables.m_tXPBonus.cells[100].value == "1000"


@pytest.mark.parametrize("missing", [
    "inactive", "EEex_GameState_GetGlobalInt", "EEex_Resource_Load2DA",
    "EEex_Menu_AddAfterMainFileLoadedListener", "EEex_UDToPtr",
])
def test_bootstrap_missing_eeex_or_api_is_reported_without_publishing(lua, missing):
    lua.execute(ENGINE_DOUBLE)
    lua.execute(STORY_DOUBLE)
    g = lua.globals()
    g.EEex_Active = missing != "inactive"
    if missing != "inactive":
        g[missing] = None

    def include(name):
        lua.execute((SOURCE / (name.lower() + ".lua")).read_text(encoding="utf-8"))

    g.Infinity_DoFile = include
    lua.execute((SOURCE / BOOTSTRAP).read_text(encoding="utf-8"))
    assert len(g.logs) == 1
    assert g.game.m_ruleTables.m_tXPBonus.writes == 0
    assert g.listeners.menu is None
