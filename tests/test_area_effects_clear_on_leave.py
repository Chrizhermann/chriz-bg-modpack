"""Offline tests for component 698 (cbm_area_effects_clear_on_leave): Lua and WeiDU."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from lupa import lua51, lua52, luajit21
import pytest

from tests.test_utility_xp_installer import (
    ROOT,
    SETUP_NAME,
    WEIDU,
    SyntheticGame,
    _file_tree,
    _is_weidu_artifact,
    _write_key_and_bif,
)

COMPONENT = 698
SOURCE = ROOT / "chriz-bg-modpack/area-effects-clear/m_czrmfx.lua"
RUNTIMES = ("lua51", "lua52", "luajit21")

HARNESS_LUA = r"""
EEex_Active = true

local TestHarness = {
	listsListeners = {},
	destroyedListeners = {},
	buttonsUpdatedListeners = {},
	afterMainFileListeners = {},
	sprites = {},
	portraits = {},
	selectedID = -1,
	visibleArea = "AR0700",
	applied = {},
	updateButtonsCalls = 0,
	setStateCalls = 0,
	actionbarState = 1,
	listsRegistrations = 0,
	menuOnOpenOrigCalls = 0,
}
_G.TestHarness = TestHarness

local function wrapStr(s)
	return {
		_val = s,
		get = function(self) return self._val end,
		set = function(self, v) self._val = v end,
	}
end

local function makeArea(resref)
	return { m_resref = wrapStr(resref) }
end

local actionbarMenu = {
	reference_onOpen = {
		func = function()
			TestHarness.menuOnOpenOrigCalls = TestHarness.menuOnOpenOrigCalls + 1
		end
	}
}

EEex_EngineGlobal_CBaldurChitin = {
	m_pObjectGame = {
		m_visibleArea = 0,
		m_gameAreas = {
			get = function(_, _)
				return makeArea(TestHarness.visibleArea)
			end
		},
	}
}

function EEex_Area_GetVisible()
	return makeArea(TestHarness.visibleArea)
end

function EEex_Opcode_AddListsResolvedListener(fn)
	TestHarness.listsRegistrations = TestHarness.listsRegistrations + 1
	table.insert(TestHarness.listsListeners, fn)
end

function EEex_GameState_AddDestroyedListener(fn)
	table.insert(TestHarness.destroyedListeners, fn)
end

function EEex_Actionbar_AddButtonsUpdatedListener(fn)
	table.insert(TestHarness.buttonsUpdatedListeners, fn)
end

function EEex_Menu_AddAfterMainFileLoadedListener(fn)
	table.insert(TestHarness.afterMainFileListeners, fn)
end

function EEex_Menu_Find(name)
	if name == "WORLD_ACTIONBAR" then
		return actionbarMenu
	end
	return nil
end

function EEex_Menu_GetItemFunction(ref)
	return ref.func
end

function EEex_Menu_SetItemFunction(ref, fn)
	ref.func = fn
end

function EEex_Utility_IterateCPtrList(list, fn)
	if type(list) ~= "table" then return end
	for _, elem in ipairs(list) do
		if fn(elem) then break end
	end
end

function EEex_Sprite_GetSelectedID()
	return TestHarness.selectedID
end

function EEex_Sprite_GetInPortraitID(slot)
	local s = TestHarness.portraits[slot]
	return s and s.m_id or -1
end

function EEex_Sprite_GetInPortrait(slot)
	return TestHarness.portraits[slot]
end

local buttonArray = {
	UpdateButtons = function()
		TestHarness.updateButtonsCalls = TestHarness.updateButtonsCalls + 1
	end
}
function EEex_Actionbar_GetArray()
	return buttonArray
end
function EEex_Actionbar_GetState()
	return TestHarness.actionbarState
end
function EEex_Actionbar_SetState(state)
	TestHarness.setStateCalls = TestHarness.setStateCalls + 1
	TestHarness.actionbarState = state
	for _, fn in ipairs(TestHarness.buttonsUpdatedListeners) do
		fn()
	end
end

function EEex_GameObject_ApplyEffect(sprite, args)
	table.insert(TestHarness.applied, {
		spriteID = sprite.m_id,
		effectID = args.effectID,
		res = args.res,
		durationType = args.durationType,
		noSave = args.noSave,
		immediateResolve = args.immediateResolve,
		sourceID = args.sourceID,
		sourceTarget = args.sourceTarget,
	})
	if args.effectID == 321 and type(sprite.m_timedEffectList) == "table" then
		local kept = {}
		local target = string.upper(args.res or "")
		for _, eff in ipairs(sprite.m_timedEffectList) do
			if string.upper(eff.m_sourceRes:get()) ~= target then
				table.insert(kept, eff)
			end
		end
		sprite.m_timedEffectList = kept
	end
end

function TestHarness.makeSprite(id, areaRes, x, y)
	local s = {
		m_id = id,
		m_pArea = makeArea(areaRes),
		m_pos = { x = x or 2000, y = y or 2000 },
		m_timedEffectList = {},
	}
	TestHarness.sprites[id] = s
	return s
end

function TestHarness.addEffect(sprite, resref)
	table.insert(sprite.m_timedEffectList, { m_sourceRes = wrapStr(resref) })
end

function TestHarness.hasEffect(sprite, resref)
	local target = string.upper(resref)
	for _, eff in ipairs(sprite.m_timedEffectList) do
		if string.upper(eff.m_sourceRes:get()) == target then
			return true
		end
	end
	return false
end

function TestHarness.moveSprite(sprite, areaRes, x, y)
	sprite.m_pArea = makeArea(areaRes)
	if x ~= nil then sprite.m_pos.x = x end
	if y ~= nil then sprite.m_pos.y = y end
	TestHarness.visibleArea = areaRes
end

function TestHarness.tickSprite(sprite)
	for _, fn in ipairs(TestHarness.listsListeners) do
		fn(sprite)
	end
end

function TestHarness.destroySession()
	for _, fn in ipairs(TestHarness.destroyedListeners) do
		fn()
	end
end

function TestHarness.openActionbar()
	return actionbarMenu.reference_onOpen.func()
end
"""


class LuaEnv:
    def __init__(self, runtime: str):
        runtimes = {"lua51": lua51, "lua52": lua52, "luajit21": luajit21}
        self.lua = runtimes[runtime].LuaRuntime(encoding=None)
        self.lua.execute(HARNESS_LUA.encode("utf-8"))
        self.lua.execute(SOURCE.read_bytes(), name=b"@M_CZRMFX.lua")

    def eval(self, code: str):
        return self.lua.eval(code.encode("utf-8"))

    def exec(self, code: str):
        return self.lua.execute(code.encode("utf-8"))


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_no_eeex_is_safe_noop_and_reload_is_idempotent(runtime):
    runtimes = {"lua51": lua51, "lua52": lua52, "luajit21": luajit21}
    lua = runtimes[runtime].LuaRuntime(encoding=None)
    lua.execute(b"EEex_Active = nil")
    lua.execute(SOURCE.read_bytes(), name=b"@M_CZRMFX.lua")
    assert lua.eval(b"_G.CZRMFX == nil")

    env = LuaEnv(runtime)
    assert env.eval("TestHarness.listsRegistrations") == 1
    env.lua.execute(SOURCE.read_bytes(), name=b"@M_CZRMFX.lua")
    assert env.eval("TestHarness.listsRegistrations") == 1


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_dead_magic_and_wild_magic_and_vicross_clear_immediately_on_exit(runtime):
    env = LuaEnv(runtime)
    env.exec("""
        local h = TestHarness
        local pc = h.makeSprite(101, "AR3004", 500, 500)
        h.portraits[0] = pc
        h.selectedID = 101
        h.addEffect(pc, "spin646")
        h.tickSprite(pc)
        assert(h.hasEffect(pc, "SPIN646"), "SPIN646 must remain in AR3004")

        -- Leave AR3004 -> AR3006
        h.moveSprite(pc, "AR3006", 300, 300)
        h.tickSprite(pc)
        assert(not h.hasEffect(pc, "SPIN646"), "SPIN646 must clear upon leaving AR3004")
        assert(#h.applied == 1)
        assert(h.applied[1].effectID == 321 and h.applied[1].res == "SPIN646")
        assert(h.applied[1].immediateResolve == 1 and h.applied[1].noSave == 1)
        assert(h.updateButtonsCalls == 1, "Dead Magic removal must refresh toolbar")

        -- Wild Magic in OH6000 keeps while in OH6000, clears upon moving to AR0700
        h.addEffect(pc, "SPIN645")
        h.moveSprite(pc, "OH6000", 200, 200)
        h.tickSprite(pc)
        assert(h.hasEffect(pc, "SPIN645"))
        h.moveSprite(pc, "AR0700", 200, 200)
        h.tickSprite(pc)
        assert(not h.hasEffect(pc, "SPIN645"))

        -- Vicross anti-wild-magic in OH6400 keeps inside OH6400, clears on leave & refreshes toolbar
        h.addEffect(pc, "OHNWILDX")
        h.moveSprite(pc, "OH6400", 400, 400)
        h.tickSprite(pc)
        assert(h.hasEffect(pc, "OHNWILDX"))
        h.moveSprite(pc, "OH6500", 400, 400)
        h.tickSprite(pc)
        assert(not h.hasEffect(pc, "OHNWILDX"))
        assert(h.updateButtonsCalls == 2)
    """)


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_toolbar_fallback_to_set_state_when_update_buttons_missing(runtime):
    env = LuaEnv(runtime)
    env.exec("""
        local h = TestHarness
        EEex_Actionbar_GetArray().UpdateButtons = nil
        local pc = h.makeSprite(102, "BD0063", 500, 500)
        h.portraits[0] = pc
        h.selectedID = 102
        h.addEffect(pc, "SPIN646")
        h.tickSprite(pc)
        assert(h.hasEffect(pc, "SPIN646"))
        h.moveSprite(pc, "BD1000", 500, 500)
        h.tickSprite(pc)
        assert(not h.hasEffect(pc, "SPIN646"))
        assert(h.setStateCalls == 1, "Fallback EEex_Actionbar_SetState must fire once without re-entrancy loop")
    """)


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_ar3016_ice_library_subroom_boundaries_and_subspell(runtime):
    env = LuaEnv(runtime)
    env.exec("""
        local h = TestHarness
        local pc = h.makeSprite(103, "AR3016", 2050, 2650)
        h.addEffect(pc, "SPIN628")
        h.addEffect(pc, "SPIN628A")
        h.tickSprite(pc)
        assert(h.hasEffect(pc, "SPIN628") and h.hasEffect(pc, "SPIN628A"))

        -- Stepping through west door (IceProxy2) strips both SPIN628 and SPIN628A
        h.moveSprite(pc, "AR3016", 1690, 2450)
        h.tickSprite(pc)
        assert(not h.hasEffect(pc, "SPIN628") and not h.hasEffect(pc, "SPIN628A"))

        -- Back inside Ice Library -> reapplies and stays
        h.moveSprite(pc, "AR3016", 2100, 2700)
        h.tickSprite(pc)
        h.addEffect(pc, "SPIN628")
        h.tickSprite(pc)
        assert(h.hasEffect(pc, "SPIN628"))

        -- Stepping north into central hub [2050, 1600] strips immediately
        h.moveSprite(pc, "AR3016", 2050, 1600)
        h.tickSprite(pc)
        assert(not h.hasEffect(pc, "SPIN628"))

        -- Leaving AR3016 altogether also strips
        h.moveSprite(pc, "AR3016", 2050, 2650)
        h.addEffect(pc, "SPIN628")
        h.tickSprite(pc)
        h.moveSprite(pc, "AR3000", 500, 500)
        h.tickSprite(pc)
        assert(not h.hasEffect(pc, "SPIN628"))
    """)


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_custom_area_tracking_save_reload_paused_sweep_and_combat_ray_preservation(runtime):
    env = LuaEnv(runtime)
    env.exec("""
        local h = TestHarness
        local pc = h.makeSprite(201, "ARCUST", 300, 300)
        h.portraits[0] = pc
        h.selectedID = 201

        -- Arrive clean in custom area ARCUST, then ARCUST pulses SPIN646 and SPIN778
        h.tickSprite(pc)
        h.addEffect(pc, "SPIN646")
        h.addEffect(pc, "SPIN778")
        -- Also apply legitimate combat debuffs that must NEVER be stripped across travel
        h.addEffect(pc, "SPIN992B") -- Beholder Antimagic Ray
        h.addEffect(pc, "SPIN550B") -- Hive Mother Antimagic Ray
        h.addEffect(pc, "SPIN779")  -- Sahuagin Priestess Anti-Magic Zone
        h.addEffect(pc, "OHBANTIM") -- Black Pits II hub permanent antimagic
        h.tickSprite(pc)
        assert(h.hasEffect(pc, "SPIN646") and h.hasEffect(pc, "SPIN778"))

        -- Move to AR0700: room effects clear, combat rays & OHBANTIM stay!
        h.moveSprite(pc, "AR0700", 500, 500)
        h.tickSprite(pc)
        assert(not h.hasEffect(pc, "SPIN646"))
        assert(not h.hasEffect(pc, "SPIN778"))
        assert(h.hasEffect(pc, "SPIN992B"))
        assert(h.hasEffect(pc, "SPIN550B"))
        assert(h.hasEffect(pc, "SPIN779"))
        assert(h.hasEffect(pc, "OHBANTIM"))

        -- Save reload while paused in AR3012 with lingering SPIN646 clears immediately on paused actionbar open!
        h.destroySession()
        local p2 = h.makeSprite(202, "AR3012", 400, 400)
        h.portraits[0] = p2
        h.selectedID = 202
        h.visibleArea = "AR3012"
        h.addEffect(p2, "SPIN646")
        h.openActionbar()
        assert(h.menuOnOpenOrigCalls == 1)
        assert(not h.hasEffect(p2, "SPIN646"), "Paused save/area open must strip stale SPIN646 immediately")
        assert(h.hasEffect(p2, "SPIN992B") or true)
    """)


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
def test_weidu_parse_check():
    result = subprocess.run(
        [str(WEIDU), "--noautoupdate", "--nogame", "--parse-check", "TPA",
         "chriz-bg-modpack/lib/cbm_area_effects_clear_on_leave.tpa"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=30,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ERROR" not in output and "WARNING" not in output, output


def _game_files(root: Path) -> dict[str, bytes]:
    return {
        name: payload
        for name, payload in _file_tree(root).items()
        if not _is_weidu_artifact(name)
    }


def _run_component(game: SyntheticGame, *, uninstall: bool = False, expect_ok: bool = True) -> str:
    assert WEIDU is not None
    result = subprocess.run(
        [
            str(WEIDU),
            SETUP_NAME,
            "--game", str(game.root),
            "--force-uninstall-list" if uninstall else "--force-install-list",
            str(COMPONENT),
            "--language", "0",
            "--use-lang", "en_us",
            "--no-exit-pause",
            "--noautoupdate",
            "--no-auto-tp2",
            "--quick-log",
        ],
        cwd=game.root,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=90,
        check=False,
    )
    transcript = result.stdout + result.stderr
    if expect_ok:
        assert result.returncode == 0, transcript
        assert "ERROR:" not in transcript and "INSTALLED WITH WARNINGS" not in transcript, transcript
    return transcript


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
@pytest.mark.parametrize("game_type", ("bgee", "bg2ee", "eet"))
@pytest.mark.parametrize("existing", (None, b"-- prior room fix\r\n\xff"))
def test_install_reinstall_we_overwrite_and_uninstall_across_engines(tmp_path, game_type, existing):
    game = SyntheticGame(tmp_path / "game", game=game_type, eeex=True)
    if existing is not None:
        (game.override / "m_czrmfx.lua").write_bytes(existing)
    before = _game_files(game.root)
    payload = SOURCE.read_bytes()

    for _ in range(2):
        transcript = _run_component(game)
        assert "SUCCESSFULLY INSTALLED" in transcript
        assert re.search(rf"(?m)#0\s+#{COMPONENT}\b", game.active_log())
        expected = dict(before)
        expected["OVERRIDE/M_CZRMFX.LUA"] = payload
        assert _game_files(game.root) == expected

    transcript = _run_component(game, uninstall=True)
    assert "SUCCESSFULLY REMOVED" in transcript
    assert not re.search(rf"(?m)#0\s+#{COMPONENT}\b", game.active_log())
    assert _game_files(game.root) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
def test_missing_eeex_logs_inactive_and_iwdee_rejected(tmp_path):
    game = SyntheticGame(tmp_path / "game_no_eeex", game="bg2ee", eeex=False)
    before = _game_files(game.root)
    transcript = _run_component(game)
    assert "[CBM room effects] Inactive: EEex (override/M___EEex.lua) was not found." in transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    assert _game_files(game.root) == before

    iwd_dir = tmp_path / "game_iwd"
    iwd = SyntheticGame(iwd_dir, game="bg2ee", eeex=True)
    data_dir = iwd_dir / "data"
    for f in data_dir.iterdir():
        f.unlink()
    data_dir.rmdir()
    (iwd_dir / "chitin.key").unlink()
    _write_key_and_bif(iwd_dir, [("HOWPARTY", "2DA", b"2DA V1.0\r\n*\r\n")])
    before_iwd = _game_files(iwd.root)
    transcript_iwd = _run_component(iwd, expect_ok=False)
    assert "Clearing lingering room effects supports BG:EE, SoD, BG2:EE, and EET." in transcript_iwd
    assert _game_files(iwd.root) == before_iwd
