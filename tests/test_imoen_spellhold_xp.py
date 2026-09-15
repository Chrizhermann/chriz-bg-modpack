"""Exercise the shipped Imoen XP helper in Lua 5.1 and LuaJIT."""
from importlib import import_module
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "chriz-bg-modpack/imoen-xp/m_cbmixp.lua"


@pytest.fixture(params=["lua51", "luajit21"])
def lua(request):
    runtime = import_module("lupa." + request.param).LuaRuntime(unpack_returned_tuples=True)
    runtime.execute("""
        EEex_Active = true
        messages, actions, party = {}, {}, {}
        function print(text) table.insert(messages, text) end
        function makeSprite(id, xp, area)
            return {
                m_id = id, m_baseStats = { m_xp = xp, m_level1 = 11, m_level2 = 7 },
                locals = {},
                m_pArea = { m_resref = { get = function() return area or 'AR1512' end } },
            }
        end
        imoen = makeSprite(42, 1250000)
        party = { makeSprite(1, 1500000), imoen, makeSprite(2, 2500000) }
        function EEex_Sprite_GetInPortrait(index) return party[index + 1] end
        function EEex_Sprite_GetNumCharacters() return #party end
        function EEex_Sprite_GetLocalInt(sprite, key) return sprite.locals[key] or 0 end
        function EEex_Sprite_SetLocalInt(sprite, key, value) sprite.locals[key] = value end
        function EEex_Action_ExecuteResponseStringOnAIBaseInstantly(text, sprite)
            local xp = assert(text:match('^ChangeStat%(Myself,XP,(%d+),SET%)$'), text)
            table.insert(actions, { sprite = sprite.m_id, xp = tonumber(xp) })
            sprite.m_baseStats.m_xp = tonumber(xp)
        end
    """)
    runtime.execute(SOURCE.read_text(encoding="utf-8"))
    return runtime


@pytest.mark.parametrize("party_xp,expected", [
    ([2000000], 2000000),
    ([1500000, 2500000], 2000000),
    ([2000000, 2000001, 2000001], 2000000),
    ([2999999, 3000000], 2999999),
    ([3000000, 3000000], 3000000),
    ([2000000, 4000000, 8000000], 3000000),
    ([0, 0], 0),
    ([1000000] * 5, 1000000),
])
def test_exact_average_excludes_imoen_and_caps_mage_xp(lua, party_xp, expected):
    g = lua.globals()
    for index, xp in enumerate(party_xp, 1):
        g.party[index] = g.makeSprite(index, xp)
    g.party[len(party_xp) + 1] = g.imoen
    for index in range(len(party_xp) + 2, 7):
        g.party[index] = None
    assert g.CBM_ImoenXP_Apply(g.imoen) is None
    assert g.imoen.m_baseStats.m_xp == expected
    assert g.imoen.locals.BD_JOINXP == 2
    assert g.imoen.locals.CBM_ImoenSpellholdXP == 1
    assert (g.imoen.m_baseStats.m_level1, g.imoen.m_baseStats.m_level2) == (11, 7)
    assert len(g.actions) == 1
    for index, xp in enumerate(party_xp, 1):
        assert g.party[index].m_baseStats.m_xp == xp


def test_native_multiclass_and_dual_xp_and_dead_party_members(lua):
    lua.execute("""
        party[1].m_typeAI = { m_Class = 7 } -- fighter/mage, pooled 1.5M
        party[1].m_baseStats.m_level1 = 10
        party[1].m_baseStats.m_level2 = 11
        party[3].m_typeAI = { m_Class = 13 } -- thief -> mage, active 2.5M
        party[3].m_baseStats.m_flags = 64
        party[3].m_baseStats.m_generalState = 2048 -- dead, still in party
        imoen.locals.BD_JOINXP = 1 -- EET's deduction is pending
        CBM_ImoenXP_Apply(imoen)
        assert(imoen.m_baseStats.m_xp == 2000000)
        assert(imoen.locals.BD_JOINXP == 2)
    """)


def test_engine_identity_and_portrait_reordering(lua):
    lua.execute("""
        party = { party[3], party[1], makeSprite(42, 1250000) }
        assert(party[3] ~= imoen) -- different wrappers for the same engine ID
        CBM_ImoenXP_Apply(imoen)
        assert(imoen.m_baseStats.m_xp == 2000000)
    """)


def test_once_only_after_xp_gain_rejoin_and_lua_reload(lua):
    g = lua.globals()
    g.CBM_ImoenXP_Apply(g.imoen)
    lua.execute("""
        imoen.m_baseStats.m_xp = 2100000 -- normal play after the initial award
        party[1].m_baseStats.m_xp = 8000000
        party[3].m_baseStats.m_xp = 8000000
    """)
    g.CBM_ImoenXP_Apply(g.imoen)
    lua.execute(SOURCE.read_text(encoding="utf-8"))  # creature locals survive reload
    g.CBM_ImoenXP_Apply(g.imoen)
    assert g.imoen.m_baseStats.m_xp == 2100000
    assert len(g.actions) == 1


@pytest.mark.parametrize("area", ["AR1512", "ar1513", "AR1514"])
def test_all_maze_areas(lua, area):
    lua.globals().areaName = area
    lua.execute("imoen.m_pArea.m_resref.get = function() return areaName end")
    lua.globals().CBM_ImoenXP_Apply(lua.globals().imoen)
    assert lua.globals().imoen.m_baseStats.m_xp == 2000000


@pytest.mark.parametrize("setup", [
    "imoen.m_pArea.m_resref.get = function() return 'AR0602' end",  # starting dungeon
    "imoen.m_pArea.m_resref.get = function() return 'AR4500' end",  # ToB
    "imoen.m_pArea = nil",
    "party[2] = makeSprite(99, 8000000)",  # Imoen is not in the party
    "imoen = nil",
])
def test_out_of_scope_calls_do_nothing(lua, setup):
    lua.execute(setup)
    lua.globals().CBM_ImoenXP_Apply(lua.globals().imoen)
    assert len(lua.globals().actions) == 0
    assert len(lua.globals().messages) == 0


def test_incomplete_party_fails_before_award_and_can_retry(lua):
    lua.execute("""
        EEex_Sprite_GetNumCharacters = function() return 4 end
        CBM_ImoenXP_Apply(imoen)
        CBM_ImoenXP_Apply(imoen)
        assert(#messages == 1)
        assert(#actions == 0)
        assert(imoen.locals.CBM_ImoenSpellholdXP == nil)
        assert(imoen.locals.BD_JOINXP == nil)
        party[4] = makeSprite(3, 2000000)
        CBM_ImoenXP_Apply(imoen)
        assert(imoen.m_baseStats.m_xp == 2000000)
        assert(imoen.locals.CBM_ImoenSpellholdXP == 1)
    """)


def test_failed_native_action_does_not_consume_once_marker(lua):
    lua.execute("""
        EEex_Action_ExecuteResponseStringOnAIBaseInstantly = function()
            error('synthetic native failure')
        end
        CBM_ImoenXP_Apply(imoen)
        assert(#messages == 1)
        assert(imoen.locals.CBM_ImoenSpellholdXP == nil)
        assert(imoen.locals.BD_JOINXP == nil)
        assert(imoen.m_baseStats.m_xp == 1250000)
    """)
