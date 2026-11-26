"""Offline tests for component 696 (cbm_no_combat_quickloot): Lua 5.1/5.2/LuaJIT and WeiDU."""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess

from lupa import lua51, lua52, luajit21
import pytest

from tests.test_utility_xp_installer import (
    MOD_NAME,
    SETUP_NAME,
    WEIDU,
    SyntheticGame,
    _file_tree,
    _is_weidu_artifact,
    _write_key_and_bif,
    ONE_EMPTY_STRING_TLK,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "chriz-bg-modpack/combat-quickloot/m_czql.lua"
COMPONENT = 696
RUNTIMES = ("lua51", "lua52", "luajit21")

LUA_HARNESS = r"""
Meter = {
    initListeners = {},
    menuLoadedListeners = {},
    menuReloadedListeners = {},
    tickListeners = {},
    keyPressedListeners = {},
    keyReleasedListeners = {},
    destroyedListeners = {},
    startGroundCalls = 0,
    stopGroundCalls = 0,
    groundButtonClicks = {},
    groundScrollCalls = 0,
    containerButtonClicks = 0,
    takeAllCalls = 0,
    popMenuCalls = {},
    pushMenuCalls = {},
    displayStrings = {},
    prints = {},
    setAreaCalls = {},
    iniWrites = {},
    logWrites = {},
    triggerEvalCalls = 0,
}

if io and io.open then
    local origOpen = io.open
    io.open = function(path, mode)
        if path == 'chriz_combat_quickloot.log' then
            return {
                write = function(self, text)
                    Meter.logWrites[#Meter.logWrites + 1] = text
                end,
                close = function(self) end,
            }
        end
        return origOpen(path, mode)
    end
end

MenusOnStack = { WORLD_ACTIONBAR = true }
IniValues = {}
Portraits = {}
SeeEnemySlots = {}
CombatTriggerSlots = {}
GameState = {
    m_bGameLoaded = 1,
    m_bInLoadGame = 0,
    m_bInLoadArea = 0,
    m_nCombatCounter = 0,
    m_worldTime = { m_gameTime = 100 },
}
EngineGlobals = {
    g_pBaldurChitin = {
        m_pObjectGame = GameState,
    },
}

ClockMs = 1000
EEex_Active = true
groundItemsButtonToggle = 0
mouseOverQuicklootContainer = nil
loot = { groundItems = {} }
RgIsModernHud = 0
RgMessageboxUnlocked = 0
MessagesRectArea = { x = 0, y = 0, w = 400, h = 50 }

print = function(...)
    local parts = {}
    for i = 1, select('#', ...) do
        parts[i] = tostring(select(i, ...))
    end
    Meter.prints[#Meter.prints + 1] = table.concat(parts, '\t')
end

EEex_GameState_AddInitializedListener = function(fn)
    Meter.initListeners[#Meter.initListeners + 1] = fn
end
EEex_Menu_AddAfterMainFileLoadedListener = function(fn)
    Meter.menuLoadedListeners[#Meter.menuLoadedListeners + 1] = fn
end
EEex_Menu_AddAfterMainFileReloadedListener = function(fn)
    Meter.menuReloadedListeners[#Meter.menuReloadedListeners + 1] = fn
end
EEex_Opcode_AddDeferredListsResolvedListener = function(fn)
    Meter.tickListeners[#Meter.tickListeners + 1] = fn
end
EEex_Key_AddPressedListener = function(fn)
    Meter.keyPressedListeners[#Meter.keyPressedListeners + 1] = fn
end
EEex_Key_AddReleasedListener = function(fn)
    Meter.keyReleasedListeners[#Meter.keyReleasedListeners + 1] = fn
end
EEex_GameState_AddDestroyedListener = function(fn)
    Meter.destroyedListeners[#Meter.destroyedListeners + 1] = fn
end

EEex_BAnd = function(a, b)
    local res, bitval = 0, 1
    while a > 0 and b > 0 do
        if a % 2 == 1 and b % 2 == 1 then res = res + bitval end
        a = math.floor(a / 2)
        b = math.floor(b / 2)
        bitval = bitval * 2
    end
    return res
end

EEex_Sprite_GetInPortrait = function(slot)
    return Portraits[slot]
end

EEex_Trigger_EvalConditionalStringAsAIBase = function(cond, sprite)
    Meter.triggerEvalCalls = Meter.triggerEvalCalls + 1
    local slot = sprite and sprite._slot
    if cond == 'See([EVILCUTOFF])' then
        return slot ~= nil and (SeeEnemySlots[slot] == true)
    elseif cond == 'CombatCounterGT(0)' then
        return slot ~= nil and (CombatTriggerSlots[slot] == true)
    end
    return false
end

Infinity_GetClockTicks = function() return ClockMs end
Infinity_IsMenuOnStack = function(name) return MenusOnStack[name] == true end
Infinity_PopMenu = function(name)
    Meter.popMenuCalls[#Meter.popMenuCalls + 1] = name
    MenusOnStack[name] = nil
end
Infinity_PushMenu = function(name)
    Meter.pushMenuCalls[#Meter.pushMenuCalls + 1] = name
    MenusOnStack[name] = true
end
Infinity_DisplayString = function(text)
    Meter.displayStrings[#Meter.displayStrings + 1] = text
end
Infinity_GetINIValue = function(sec, key, def)
    local s = IniValues[sec]
    if s and s[key] ~= nil then return s[key] end
    return def
end
Infinity_SetINIValue = function(sec, key, val)
    IniValues[sec] = IniValues[sec] or {}
    IniValues[sec][key] = val
    Meter.iniWrites[#Meter.iniWrites + 1] = { sec = sec, key = key, val = val }
end
Infinity_GetArea = function(name)
    if name == 'messagesRect' then
        return MessagesRectArea.x, MessagesRectArea.y, MessagesRectArea.w, MessagesRectArea.h
    end
end
Infinity_SetArea = function(name, x, y, w, h)
    Meter.setAreaCalls[#Meter.setAreaCalls + 1] = { name = name, h = h }
    if name == 'messagesRect' then
        if x ~= nil then MessagesRectArea.x = x end
        if y ~= nil then MessagesRectArea.y = y end
        if w ~= nil then MessagesRectArea.w = w end
        if h ~= nil then MessagesRectArea.h = h end
    end
end

local worldScreenMethods = {
    StartGroundItems = function(self)
        Meter.startGroundCalls = Meter.startGroundCalls + 1
        MenusOnStack.WORLD_QUICKLOOT = true
    end,
    StopGroundItems = function(self)
        Meter.stopGroundCalls = Meter.stopGroundCalls + 1
        MenusOnStack.WORLD_QUICKLOOT = nil
    end,
    OnGroundButtonClick = function(self, slotId, containerId, res)
        Meter.groundButtonClicks[#Meter.groundButtonClicks + 1] = { slotId, containerId, res }
    end,
    OnGroundScroll = function(self, delta)
        Meter.groundScrollCalls = Meter.groundScrollCalls + 1
    end,
    GroundScrollEnabled = function(self, delta)
        return true
    end,
    GetTopGroundItem = function(self)
        return 0
    end,
    OnContainerButtonClick = function(self, slotId)
        Meter.containerButtonClicks = Meter.containerButtonClicks + 1
    end,
    TakeAllFromContainer = function(self)
        Meter.takeAllCalls = Meter.takeAllCalls + 1
    end,
}
worldScreen = setmetatable({}, { __index = worldScreenMethods })

local buttonArrayMethods = {
    GetButtonEnabled = function(self, idx) return true end,
}
buttonArray = setmetatable({}, { __index = buttonArrayMethods })

ActiveEngine = worldScreen
e = {
    GetActiveEngine = function(self) return ActiveEngine end,
}

function registerMenuGlobals()
    getSlotContainerId = function(idx)
        local slot = loot.groundItems[idx + worldScreen:GetTopGroundItem()]
        return slot and slot.containerId or nil
    end
    getGroundItemProperty = function(idx, prop)
        local slot = loot.groundItems[idx + worldScreen:GetTopGroundItem()]
        if not slot or not slot.item then return nil end
        return slot.item[prop]
    end
    groundItemClick = function(slotId)
        local slot = loot.groundItems[slotId + worldScreen:GetTopGroundItem()]
        if slot and slot.item then
            worldScreen:OnGroundButtonClick(slot.slotId, slot.containerId, slot.item.res)
        end
    end
    showGroundItemDescription = function(slotId)
        return 'desc:' .. tostring(slotId)
    end
end
registerMenuGlobals()

function FireInit()
    for _, fn in ipairs(Meter.initListeners) do fn() end
end
function FireMenuLoaded()
    registerMenuGlobals()
    for _, fn in ipairs(Meter.menuLoadedListeners) do fn() end
end
function FireMenuReloaded()
    registerMenuGlobals()
    for _, fn in ipairs(Meter.menuReloadedListeners) do fn() end
end
function FireTick(newGameTime)
    if newGameTime ~= nil then GameState.m_worldTime.m_gameTime = newGameTime end
    for _, fn in ipairs(Meter.tickListeners) do fn() end
end
function FireKeyPress()
    for _, fn in ipairs(Meter.keyPressedListeners) do fn(0x70) end
end
function FireKeyRelease()
    for _, fn in ipairs(Meter.keyReleasedListeners) do fn(0x70) end
end
function FireGameDestroyed()
    for _, fn in ipairs(Meter.destroyedListeners) do fn() end
end
"""


class CombatQuickLootHarness:
    def __init__(self, runtime: str = "lua52"):
        runtimes = {"lua51": lua51, "lua52": lua52, "luajit21": luajit21}
        self.lua = runtimes[runtime].LuaRuntime(encoding=None)
        self.lua.execute(LUA_HARNESS.encode("utf-8"))

    def load_mod(self, extra: bytes = b"", initialize: bool = True) -> "CombatQuickLootHarness":
        if extra:
            self.lua.execute(extra)
        self.lua.execute(SOURCE.read_bytes(), name=b"@M_CZQL.lua")
        if initialize:
            self.lua.execute(b"FireInit()")
        return self

    def exec(self, code: str):
        self.lua.execute(code.encode("utf-8"))

    def eval(self, expr: str):
        return self.lua.eval(expr.encode("utf-8"))


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("logging_mode", ("normal", "no_io", "io_fail"))
def test_missing_eeex_is_clean_noop(runtime, logging_mode):
    h = CombatQuickLootHarness(runtime)
    extra = b"EEex_Active = nil;"
    if logging_mode == "no_io":
        extra += b"io = nil;"
    elif logging_mode == "io_fail":
        extra += b"io = { open = function() return nil end };"
    h.load_mod(extra=extra, initialize=False)
    assert not h.eval("CZCombatQuickLoot.installed")
    assert b"EEex is required" in h.eval("CZCombatQuickLoot.status")
    assert h.eval("#Meter.initListeners") == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("missing_api", (
    "EEex_GameState_AddInitializedListener",
    "EEex_Menu_AddAfterMainFileLoadedListener",
    "EEex_Opcode_AddDeferredListsResolvedListener",
))
def test_missing_required_eeex_api_is_clean_noop(runtime, missing_api):
    h = CombatQuickLootHarness(runtime)
    extra = f"{missing_api} = nil;"
    if missing_api == "EEex_Menu_AddAfterMainFileLoadedListener":
        extra += "EEex_Menu_AddMainFileLoadedListener = nil;"
    if missing_api == "EEex_Opcode_AddDeferredListsResolvedListener":
        extra += "EEex_Opcode_AddListsResolvedListener = nil;"
    h.load_mod(extra=extra.encode("ascii"), initialize=False)
    assert not h.eval("CZCombatQuickLoot.installed")
    assert b"missing EEex API" in h.eval("CZCombatQuickLoot.status")


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_idempotent_reload_and_rehook_on_menu_reload(runtime):
    h = CombatQuickLootHarness(runtime).load_mod()
    # Reloading script and firing menu load/reload must not duplicate listeners or double-wrap.
    h.lua.execute(SOURCE.read_bytes(), name=b"@M_CZQL.lua")
    h.exec("FireInit(); FireMenuLoaded(); FireMenuReloaded(); FireMenuReloaded()")
    assert h.eval("#Meter.initListeners") == 1
    assert h.eval("#Meter.menuLoadedListeners") == 1
    assert h.eval("#Meter.menuReloadedListeners") == 1
    assert h.eval("#Meter.tickListeners") == 1
    # Wrapped global still delegates once out of combat.
    h.exec("""
        loot.groundItems[0] = { slotId = 0, containerId = 7, item = { res = 'SW1H01', name = 'Long Sword' } }
        groundItemClick(0)
    """)
    assert h.eval("#Meter.groundButtonClicks") == 1


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_combat_detection_signals_and_tick_cache(runtime):
    h = CombatQuickLootHarness(runtime).load_mod()
    h.exec("""
        Portraits[0] = { _slot = 0, m_baseStats = { m_generalState = 0 } }
        Portraits[1] = { _slot = 1, m_baseStats = { m_generalState = 0x800 } } -- dead
    """)
    assert h.eval("CZCombatQuickLoot.IsInCombat(true)") is False

    # Dead companion seeing an enemy does NOT trigger combat.
    h.exec("SeeEnemySlots[1] = true")
    assert h.eval("CZCombatQuickLoot.IsInCombat(true)") is False

    # Living companion seeing an enemy triggers combat immediately on tick 100.
    h.exec("SeeEnemySlots[0] = true")
    assert h.eval("CZCombatQuickLoot.IsInCombat(true)") is True

    # Cached within same m_gameTime tick for non-forced checks.
    calls_before = h.eval("Meter.triggerEvalCalls")
    assert h.eval("CZCombatQuickLoot.IsInCombat(false)") is True
    assert h.eval("Meter.triggerEvalCalls") == calls_before

    # Advancing m_gameTime refreshes cache.
    h.exec("SeeEnemySlots[0] = false; GameState.m_worldTime.m_gameTime = 101")
    assert h.eval("CZCombatQuickLoot.IsInCombat(false)") is False

    # m_nCombatCounter > 0 short-circuits to true without sprite trigger calls.
    calls_before = h.eval("Meter.triggerEvalCalls")
    h.exec("GameState.m_nCombatCounter = 1")
    assert h.eval("CZCombatQuickLoot.IsInCombat(true)") is True
    assert h.eval("Meter.triggerEvalCalls") == calls_before

    # Unloaded / mid-load game never falsely reports combat.
    h.exec("GameState.m_bGameLoaded = 0")
    assert h.eval("CZCombatQuickLoot.IsInCombat(true)") is False
    h.exec("GameState.m_bGameLoaded = 1; GameState.m_bInLoadArea = 1")
    assert h.eval("CZCombatQuickLoot.IsInCombat(true)") is False


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_area_combat_counter_and_nearby_enemy_range_check(runtime):
    h = CombatQuickLootHarness(runtime).load_mod()
    h.exec("""
        Portraits[0] = {
            _slot = 0,
            m_baseStats = { m_generalState = 0 },
            m_pArea = { m_combatCounter = -45 },
        }
        NearbyEnemies = {}
        EEex_Sprite_ForAllOfTypeStringInRange = function(sprite, tag, range, cb)
            assert(tag == '[ENEMY]' and range == 448)
            for _, enemy in ipairs(NearbyEnemies) do
                cb(enemy)
            end
        end
    """)
    assert h.eval("CZCombatQuickLoot.IsInCombat(true)") is False

    # Dead [ENEMY] corpse in range (0x800 STATE_DEAD) must not block Quick Loot.
    h.exec("NearbyEnemies = { { m_baseStats = { m_generalState = 0x800 } } }")
    assert h.eval("CZCombatQuickLoot.IsInCombat(true)") is False

    # Living nearby enemy in sight range triggers combat on frame 1.
    h.exec("NearbyEnemies = { { m_baseStats = { m_generalState = 0 } } }")
    assert h.eval("CZCombatQuickLoot.IsInCombat(true)") is True

    # Area m_combatCounter > 0 short-circuits without calling trigger evaluation.
    h.exec("NearbyEnemies = {}; Portraits[0].m_pArea.m_combatCounter = 120")
    calls_before = h.eval("Meter.triggerEvalCalls")
    assert h.eval("CZCombatQuickLoot.IsInCombat(true)") is True
    assert h.eval("Meter.triggerEvalCalls") == calls_before

    # Cooldown settled back to <= 0 unlocks Quick Loot.
    h.exec("Portraits[0].m_pArea.m_combatCounter = -45")
    assert h.eval("CZCombatQuickLoot.IsInCombat(true)") is False


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_preopen_quickloot_closes_on_combat_and_restores_after_combat(runtime):
    h = CombatQuickLootHarness(runtime).load_mod()
    h.exec("""
        groundItemsButtonToggle = 1
        MenusOnStack.WORLD_QUICKLOOT = true
        mouseOverQuicklootContainer = 42
        loot.groundItems = { [0] = { slotId = 0, containerId = 42, item = { res = 'POTN08', name = 'Healing' } } }
        -- Combat starts via combat counter
        GameState.m_nCombatCounter = 1
        FireTick(101)
    """)
    assert h.eval("groundItemsButtonToggle") == 0
    assert h.eval("Infinity_IsMenuOnStack('WORLD_QUICKLOOT')") is False
    assert h.eval("mouseOverQuicklootContainer") is None
    assert h.eval("loot.groundItems[0]") is None
    assert h.eval("Meter.stopGroundCalls") == 1

    # Combat ends -> automatically restores because it was ON before combat.
    h.exec("GameState.m_nCombatCounter = 0; FireTick(102)")
    assert h.eval("groundItemsButtonToggle") == 1
    assert h.eval("Infinity_IsMenuOnStack('WORLD_QUICKLOOT')") is True
    assert h.eval("Meter.startGroundCalls") == 1


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_off_quickloot_stays_off_after_combat(runtime):
    h = CombatQuickLootHarness(runtime).load_mod()
    h.exec("""
        groundItemsButtonToggle = 0
        MenusOnStack.WORLD_QUICKLOOT = nil
        GameState.m_nCombatCounter = 1
        FireTick(101)
        GameState.m_nCombatCounter = 0
        FireTick(102)
    """)
    assert h.eval("groundItemsButtonToggle") == 0
    assert h.eval("Infinity_IsMenuOnStack('WORLD_QUICKLOOT')") is False
    assert h.eval("Meter.startGroundCalls") == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("ui_mode", ("vanilla", "infinityui_modern", "infinityui_unlocked_msg"))
def test_incombat_button_click_blocked_and_messages_rect_never_drifts(runtime, ui_mode):
    h = CombatQuickLootHarness(runtime).load_mod()
    if ui_mode == "infinityui_modern":
        h.exec("RgIsModernHud = 1; MessagesRectArea.h = 50")
    elif ui_mode == "infinityui_unlocked_msg":
        h.exec("RgMessageboxUnlocked = 1; MessagesRectArea.h = -5")

    h.exec("GameState.m_nCombatCounter = 1; FireTick(101)")

    # Simulate 5 clicks on Quick Loot button during combat (including InfinityUI++'s h - 60 tail).
    h.exec("""
        for i = 1, 5 do
            ClockMs = ClockMs + (i == 1 and 0 or 500)
            groundItemsButtonToggle = 1
            if RgIsModernHud == 1 then
                local _, _, _, h = Infinity_GetArea('messagesRect')
                worldScreen:StartGroundItems()
                Infinity_SetArea('messagesRect', nil, nil, nil, h - 60)
            else
                worldScreen:StartGroundItems()
            end
            buttonArray:GetButtonEnabled(0)
        end
    """)
    assert h.eval("Meter.startGroundCalls") == 0
    assert h.eval("groundItemsButtonToggle") == 0
    assert h.eval("Infinity_IsMenuOnStack('WORLD_QUICKLOOT')") is False
    # Rate-limited: 5 clicks within 2s should only emit 2 notices (at 1000ms and 2500ms).
    assert h.eval("#Meter.displayStrings") == 2
    assert h.eval("Meter.displayStrings[1]") == b"Quick Loot is disabled in combat."

    if ui_mode == "infinityui_modern":
        assert h.eval("MessagesRectArea.h") == 50
    elif ui_mode == "infinityui_unlocked_msg":
        assert h.eval("MessagesRectArea.h") == -5

    # After combat ends, because Quick Loot was OFF before combat, it stays OFF.
    h.exec("GameState.m_nCombatCounter = 0; FireTick(102)")
    assert h.eval("groundItemsButtonToggle") == 0
    assert h.eval("Meter.startGroundCalls") == 0


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_native_hotkey_and_slot_actions_blocked_while_ground_containers_work(runtime):
    h = CombatQuickLootHarness(runtime).load_mod()
    h.exec("""
        loot.groundItems = { [0] = { slotId = 0, containerId = 99, item = { res = 'AROW01', name = 'Arrow' } } }
        GameState.m_nCombatCounter = 1
        FireTick(101)

        -- Simulate C++ CScreenWorld::OnKeyDown directly pushing WORLD_QUICKLOOT + toggle=1.
        MenusOnStack.WORLD_QUICKLOOT = true
        groundItemsButtonToggle = 1
        FireKeyPress()
        FireKeyRelease()
    """)
    assert h.eval("Infinity_IsMenuOnStack('WORLD_QUICKLOOT')") is False
    assert h.eval("groundItemsButtonToggle") == 0
    assert h.eval("#Meter.displayStrings") == 1

    # Even if WORLD_QUICKLOOT is forced open while paused, UI getters/clicks/scrolls all block and pop it.
    h.exec("""
        MenusOnStack.WORLD_QUICKLOOT = true
        groundItemsButtonToggle = 1
        loot.groundItems = { [0] = { slotId = 0, containerId = 99, item = { res = 'AROW01', name = 'Arrow' } } }
        BlockedProp = getGroundItemProperty(0, 'name')
        BlockedCont = getSlotContainerId(0)
        BlockedDesc = showGroundItemDescription(0)
        groundItemClick(0)
        worldScreen:OnGroundButtonClick(0, 99, 'AROW01')
        worldScreen:OnGroundScroll(1)
        ScrollOk = worldScreen:GroundScrollEnabled(1)

        -- Ground container looting remains completely functional in combat!
        worldScreen:OnContainerButtonClick(0)
        worldScreen:TakeAllFromContainer()
    """)
    assert h.eval("BlockedProp") is None
    assert h.eval("BlockedCont") is None
    assert h.eval("BlockedDesc") is None
    assert h.eval("ScrollOk") is False
    assert h.eval("#Meter.groundButtonClicks") == 0
    assert h.eval("Meter.groundScrollCalls") == 0
    assert h.eval("Infinity_IsMenuOnStack('WORLD_QUICKLOOT')") is False
    assert h.eval("Meter.containerButtonClicks") == 1
    assert h.eval("Meter.takeAllCalls") == 1


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_deferred_restore_when_combat_ends_inside_container_or_dialog(runtime):
    h = CombatQuickLootHarness(runtime).load_mod()
    h.exec("""
        groundItemsButtonToggle = 1
        MenusOnStack.WORLD_QUICKLOOT = true
        GameState.m_nCombatCounter = 1
        FireTick(101)
        -- Player opens a corpse/container on the ground, closing WORLD_ACTIONBAR.
        MenusOnStack.WORLD_ACTIONBAR = nil
        MenusOnStack.WORLD_CONTAINER = true
        GameState.m_nCombatCounter = 0
        FireTick(102)
    """)
    # Toggle flag is restored to 1 so WORLD_ACTIONBAR onOpen will open it, but StartGroundItems
    # is NOT called while WORLD_CONTAINER covers the bar.
    assert h.eval("groundItemsButtonToggle") == 1
    assert h.eval("Meter.startGroundCalls") == 0

    # Player closes container -> WORLD_ACTIONBAR onOpen runs out of combat and starts Quick Loot.
    h.exec("""
        MenusOnStack.WORLD_CONTAINER = nil
        MenusOnStack.WORLD_ACTIONBAR = true
        if groundItemsButtonToggle == 1 then worldScreen:StartGroundItems() end
    """)
    assert h.eval("Meter.startGroundCalls") == 1
    assert h.eval("Infinity_IsMenuOnStack('WORLD_QUICKLOOT')") is True


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_ini_and_cbrchm_live_toggle_and_save_reload_reset(runtime):
    h = CombatQuickLootHarness(runtime).load_mod()
    h.exec("""
        groundItemsButtonToggle = 1
        MenusOnStack.WORLD_QUICKLOOT = true
        GameState.m_nCombatCounter = 1
        FireTick(101)
    """)
    assert h.eval("groundItemsButtonToggle") == 0

    # Live Challenge Mode (CBRCHM) toggle OFF mid-combat restores Quick Loot immediately on next tick.
    h.exec("""
        CBRCHM = { IsActive = function() return false end }
        FireTick(102)
    """)
    assert h.eval("groundItemsButtonToggle") == 1
    assert h.eval("Infinity_IsMenuOnStack('WORLD_QUICKLOOT')") is True

    # Toggle CBRCHM back ON -> suppresses again; then SetEnabled(0) disables via INI.
    h.exec("""
        CBRCHM = { IsActive = function() return true end }
        FireTick(103)
    """)
    assert h.eval("groundItemsButtonToggle") == 0
    h.exec("CZCombatQuickLoot.SetEnabled(0)")
    assert h.eval("IniValues['Challenge Mode'].NoCombatQuickLoot") == 0
    assert h.eval("groundItemsButtonToggle") == 1

    # Save reload mid-combat resets suppression session cleanly.
    h.exec("""
        CZCombatQuickLoot.SetEnabled(1)
        FireTick(104)
        assert(CZCombatQuickLoot.session.suppressing == true)
        GameState.m_nCombatCounter = 0
        groundItemsButtonToggle = 0
        MenusOnStack.WORLD_QUICKLOOT = nil
        FireGameDestroyed()
    """)
    assert h.eval("CZCombatQuickLoot.session.suppressing") is False
    assert h.eval("CZCombatQuickLoot.session.savedToggleBeforeCombat") is None


def _game_files(root: Path) -> dict[str, bytes]:
    return {
        name: payload
        for name, payload in _file_tree(root).items()
        if not _is_weidu_artifact(name)
    }


def _make_iwdee_game(root: Path, *, eeex: bool = True) -> Path:
    root.mkdir()
    override = root / "override"
    override.mkdir()
    shutil.copy2(ROOT / SETUP_NAME, root / SETUP_NAME)
    shutil.copytree(ROOT / MOD_NAME, root / MOD_NAME)
    _write_key_and_bif(root, [("AR2100", "ARE", b"synthetic IWD:EE marker")])
    lang_tlk = root / "lang" / "en_us" / "dialog.tlk"
    lang_tlk.parent.mkdir(parents=True)
    lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
    (root / "dialog.tlk").write_bytes(ONE_EMPTY_STRING_TLK)
    (root / "Baldur.lua").write_bytes(b"-- IWD:EE settings\r\n")
    if eeex:
        (override / "m___eeex.lua").write_bytes(b"-- synthetic EEex marker\r\n")
    return root


def _run_component(game_root: Path, *, uninstall: bool = False) -> str:
    assert WEIDU is not None
    result = subprocess.run(
        [
            str(WEIDU),
            SETUP_NAME,
            "--game", str(game_root),
            "--force-uninstall-list" if uninstall else "--force-install-list",
            str(COMPONENT),
            "--language", "0",
            "--use-lang", "en_us",
            "--no-exit-pause",
            "--noautoupdate",
            "--no-auto-tp2",
            "--quick-log",
        ],
        cwd=game_root,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=90,
        check=False,
    )
    transcript = result.stdout + result.stderr
    assert result.returncode == 0, transcript
    assert "ERROR:" not in transcript and "INSTALLED WITH WARNINGS" not in transcript, transcript
    return transcript


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
def test_weidu_parse_check():
    result = subprocess.run(
        [str(WEIDU), "--noautoupdate", "--nogame", "--parse-check", "TPA",
         "chriz-bg-modpack/lib/cbm_no_combat_quickloot.tpa"],
        cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=30,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ERROR" not in output and "WARNING" not in output, output


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
@pytest.mark.parametrize("game_type", ("bgee", "bg2ee", "eet", "iwdee"))
@pytest.mark.parametrize("existing", (None, b"-- prior quickloot script\n", b"hand-edited\0\xff"))
def test_install_reinstall_uninstall_across_engines(tmp_path, game_type, existing):
    if game_type == "iwdee":
        game_root = _make_iwdee_game(tmp_path / "game", eeex=True)
    else:
        game_root = SyntheticGame(tmp_path / "game", game=game_type, eeex=True).root
    if existing is not None:
        (game_root / "override" / "m_czql.lua").write_bytes(existing)
    before = _game_files(game_root)
    payload = SOURCE.read_bytes()

    for _ in range(2):
        transcript = _run_component(game_root)
        assert "SUCCESSFULLY INSTALLED" in transcript
        active_log = "\n".join(
            line for line in (game_root / "weidu.log").read_text(encoding="utf-8", errors="replace").splitlines()
            if not line.lstrip().startswith("//")
        )
        assert re.search(rf"(?m)#0\s+#{COMPONENT}\b", active_log)
        expected = dict(before)
        expected["OVERRIDE/M_CZQL.LUA"] = payload
        assert _game_files(game_root) == expected

    transcript = _run_component(game_root, uninstall=True)
    assert "SUCCESSFULLY REMOVED" in transcript
    active_log = "\n".join(
        line for line in (game_root / "weidu.log").read_text(encoding="utf-8", errors="replace").splitlines()
        if not line.lstrip().startswith("//")
    )
    assert not re.search(rf"(?m)#0\s+#{COMPONENT}\b", active_log)
    assert _game_files(game_root) == before


@pytest.mark.skipif(WEIDU is None, reason="WeiDU unavailable; set WEIDU")
def test_missing_eeex_logs_inactive_and_enables_on_reinstall(tmp_path):
    game = SyntheticGame(tmp_path / "game", game="bg2ee", eeex=False)
    before = _game_files(game.root)

    transcript = _run_component(game.root)
    assert "[CBM combat quick loot] Inactive: EEex (override/M___EEex.lua) was not found." in transcript
    assert "SUCCESSFULLY INSTALLED" in transcript
    assert _game_files(game.root) == before

    (game.override / "m___eeex.lua").write_bytes(b"-- EEex installed later\n")
    transcript = _run_component(game.root)
    assert "SUCCESSFULLY INSTALLED" in transcript
    assert _game_files(game.root)["OVERRIDE/M_CZQL.LUA"] == SOURCE.read_bytes()

    transcript = _run_component(game.root, uninstall=True)
    assert "SUCCESSFULLY REMOVED" in transcript
    after_uninstall = _game_files(game.root)
    assert "OVERRIDE/M_CZQL.LUA" not in after_uninstall
    assert after_uninstall["OVERRIDE/M___EEEX.LUA"] == b"-- EEex installed later\n"
