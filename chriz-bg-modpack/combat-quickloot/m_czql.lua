-- Chriz Combat Quick Loot Disabler 0.1.0.
-- Targets BG:EE, SoD, BG2:EE, EET, and IWD:EE (EEex v1.2.0 / v1.3.1, Lua 5.1 / 5.2 / LuaJIT).
-- Disables Quick Loot (WORLD_QUICKLOOT) while in combat so items must be looted from
-- the ground/containers directly, and restores Quick Loot automatically after combat.

CZCombatQuickLoot = CZCombatQuickLoot or { status = 'not initialized' }
local state = CZCombatQuickLoot
if state.queued then return end
state.queued = true

local DEAD_STATE_MASK = 0xFC0
local SIGHT_RANGE = 448
local NOTIFY_COOLDOWN_MS = 1500
local NOTIFY_COOLDOWN_TICKS = 22
local DEFAULT_MESSAGE = 'Quick Loot is disabled in combat.'

local function makeSession()
    return {
        suppressing = false,
        savedToggleBeforeCombat = nil,
        lastTickChecked = nil,
        cachedCombatTick = nil,
        cachedCombatResult = nil,
        fixMessagesRectNextTick = false,
        lastNotifyClock = nil,
        lastNotifyTick = nil,
        internalCall = false,
    }
end

state.session = state.session or makeSession()
state.wrappedObjects = state.wrappedObjects or setmetatable({}, { __mode = 'k' })

local function log(message)
    state.status = message
    if state.logged then return end
    state.logged = true
    message = tostring(message):gsub('[\r\n]+', ' ')
    if io and io.open then
        local f = io.open('chriz_combat_quickloot.log', 'a')
        if f then
            f:write('Chriz Combat Quick Loot: ' .. message .. '\n')
            f:close()
            return
        end
    end
    print('Chriz Combat Quick Loot: ' .. message)
end

local function isTruthy(value)
    if value == true then return true end
    if type(value) == 'number' then return value ~= 0 end
    return false
end

local function isMenuOnStack(name)
    if type(_G.Infinity_IsMenuOnStack) ~= 'function' then return false end
    local ok, visible = pcall(_G.Infinity_IsMenuOnStack, name)
    return ok and isTruthy(visible)
end

local function callable(value)
    if type(value) == 'function' then return true end
    if type(value) ~= 'table' and type(value) ~= 'userdata' then return false end
    local mt = (debug and debug.getmetatable or getmetatable)(value)
    return type(mt) == 'table' and mt.__call ~= nil
end

local function getWorldTick()
    if type(state._tickOverride) == 'number' then
        return state._tickOverride
    end
    local ok, ticks = pcall(function()
        return EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime.m_gameTime
    end)
    if ok and type(ticks) == 'number' then
        return ticks
    end
    return nil
end

local function getClockMs()
    if type(state._clockOverride) == 'number' then
        return state._clockOverride
    end
    if type(_G.Infinity_GetClockTicks) == 'function' then
        local ok, ms = pcall(_G.Infinity_GetClockTicks)
        if ok and type(ms) == 'number' then return ms end
    end
    return nil
end

local function loadConfig()
    if state.configEnabled ~= nil then
        return state.configEnabled
    end
    local value = 1
    if type(_G.Infinity_GetINIValue) == 'function' then
        local ok, raw = pcall(_G.Infinity_GetINIValue, 'Challenge Mode', 'NoCombatQuickLoot', 1)
        if ok and raw ~= nil and raw ~= '' then
            local num = tonumber(raw)
            if num ~= nil then
                value = (num ~= 0) and 1 or 0
            elseif raw == false then
                value = 0
            end
        end
    end
    state.configEnabled = value
    return value
end

function CZCombatQuickLoot.IsEnabled()
    if loadConfig() ~= 1 then
        return false
    end
    local chm = _G.CBRCHM
    if type(chm) == 'table' and type(chm.IsActive) == 'function' then
        local ok, active = pcall(chm.IsActive)
        if ok and not isTruthy(active) then
            return false
        end
    end
    return true
end

local function isSpriteDead(sprite)
    local ok, generalState = pcall(function()
        return sprite.m_baseStats.m_generalState
    end)
    if not ok or type(generalState) ~= 'number' then
        return false
    end
    if type(_G.EEex_BAnd) == 'function' then
        return _G.EEex_BAnd(generalState, DEAD_STATE_MASK) ~= 0
    end
    return (math.floor(generalState / 64) % 64) ~= 0
end

function CZCombatQuickLoot.IsInCombat(forceFresh)
    if type(state._inCombatOverride) == 'boolean' then
        return state._inCombatOverride
    end
    local okGame, gameObj = pcall(function()
        return EngineGlobals.g_pBaldurChitin.m_pObjectGame
    end)
    if okGame and gameObj ~= nil then
        local okFlags, loaded, inLoadGame, inLoadArea = pcall(function()
            return gameObj.m_bGameLoaded, gameObj.m_bInLoadGame, gameObj.m_bInLoadArea
        end)
        if okFlags then
            if loaded == 0 or (type(inLoadGame) == 'number' and inLoadGame ~= 0)
                or (type(inLoadArea) == 'number' and inLoadArea ~= 0) then
                return false
            end
        end
        local okCtr, ctr = pcall(function()
            return gameObj.m_nCombatCounter
        end)
        if okCtr and type(ctr) == 'number' and ctr > 0 then
            return true
        end
    end

    local worldTick = getWorldTick()
    if not forceFresh and worldTick ~= nil and state.session.cachedCombatTick == worldTick
        and state.session.cachedCombatResult ~= nil then
        return state.session.cachedCombatResult
    end

    local inCombat = false
    if type(_G.EEex_Sprite_GetInPortrait) == 'function' then
        local evalTrigger = _G.EEex_Trigger_EvalConditionalStringAsAIBase
        local forEachInRange = _G.EEex_Sprite_ForAllOfTypeStringInRange
        for slot = 0, 5 do
            local okSprite, sprite = pcall(_G.EEex_Sprite_GetInPortrait, slot)
            if okSprite and sprite ~= nil and not isSpriteDead(sprite) then
                local okAreaCtr, areaCtr = pcall(function()
                    return sprite.m_pArea and sprite.m_pArea.m_combatCounter
                end)
                if okAreaCtr and type(areaCtr) == 'number' and areaCtr > 0 then
                    inCombat = true
                    break
                end
                if type(forEachInRange) == 'function' then
                    pcall(forEachInRange, sprite, '[ENEMY]', SIGHT_RANGE, function(enemy)
                        if enemy ~= nil and not isSpriteDead(enemy) then
                            inCombat = true
                        end
                    end)
                    if inCombat then break end
                end
                if type(evalTrigger) == 'function' then
                    local okSee, seesEnemy = pcall(evalTrigger, 'See([EVILCUTOFF])', sprite)
                    if okSee and isTruthy(seesEnemy) then
                        inCombat = true
                        break
                    end
                    local okCombat, combatActive = pcall(evalTrigger, 'CombatCounterGT(0)', sprite)
                    if okCombat and isTruthy(combatActive) then
                        inCombat = true
                        break
                    end
                end
            end
        end
    end

    if worldTick ~= nil then
        state.session.cachedCombatTick = worldTick
        state.session.cachedCombatResult = inCombat
    end
    return inCombat
end

local function isBlocked(forceFresh)
    return CZCombatQuickLoot.IsEnabled() and CZCombatQuickLoot.IsInCombat(forceFresh)
end

local function notifyBlocked()
    if type(_G.Infinity_DisplayString) ~= 'function' then return end
    local nowMs = getClockMs()
    local nowTick = getWorldTick()
    local s = state.session
    if nowMs ~= nil and s.lastNotifyClock ~= nil then
        local delta = nowMs - s.lastNotifyClock
        if delta >= 0 and delta < NOTIFY_COOLDOWN_MS then
            return
        end
    elseif nowTick ~= nil and s.lastNotifyTick ~= nil then
        local delta = nowTick - s.lastNotifyTick
        if delta >= 0 and delta < NOTIFY_COOLDOWN_TICKS then
            return
        end
    end
    s.lastNotifyClock = nowMs
    s.lastNotifyTick = nowTick
    pcall(_G.Infinity_DisplayString, DEFAULT_MESSAGE)
end

local function syncInfinityUIMessagesRect(quickLootOpen)
    if type(_G.Infinity_SetArea) ~= 'function' then return end
    if not isMenuOnStack('WORLD_ACTIONBAR') then return end
    if _G.RgIsModernHud == 1 then
        pcall(_G.Infinity_SetArea, 'messagesRect', nil, nil, nil, quickLootOpen and -10 or 50)
    elseif _G.RgMessageboxUnlocked == 1 then
        pcall(_G.Infinity_SetArea, 'messagesRect', nil, nil, nil, quickLootOpen and -65 or -5)
    end
end

local function closeQuickLootUI()
    local s = state.session
    local needAction = (_G.groundItemsButtonToggle == 1)
        or isMenuOnStack('WORLD_QUICKLOOT')
        or s.fixMessagesRectNextTick

    _G.groundItemsButtonToggle = 0
    _G.mouseOverQuicklootContainer = nil
    if type(_G.loot) == 'table' and type(_G.loot.groundItems) == 'table' then
        _G.loot.groundItems = {}
    end

    if not needAction then return end

    if _G.worldScreen ~= nil and type(state.origStopGroundItems) == 'function' then
        s.internalCall = true
        pcall(state.origStopGroundItems, _G.worldScreen)
        s.internalCall = false
    elseif _G.worldScreen ~= nil and _G.worldScreen.StopGroundItems ~= nil and not s.internalCall then
        s.internalCall = true
        pcall(function() _G.worldScreen:StopGroundItems() end)
        s.internalCall = false
    end

    if type(_G.Infinity_PopMenu) == 'function' and isMenuOnStack('WORLD_QUICKLOOT') then
        pcall(_G.Infinity_PopMenu, 'WORLD_QUICKLOOT')
    end
    syncInfinityUIMessagesRect(false)
    s.fixMessagesRectNextTick = false
end

local function restoreQuickLootUI()
    local s = state.session
    _G.groundItemsButtonToggle = 1
    if not isMenuOnStack('WORLD_ACTIONBAR') then return end
    if isMenuOnStack('WORLD_CONTAINER') or isMenuOnStack('WORLD_DIALOG') then return end
    if _G.e ~= nil and _G.worldScreen ~= nil then
        local okEng, active = pcall(function() return _G.e:GetActiveEngine() end)
        if okEng and active ~= nil and not rawequal(active, _G.worldScreen) then
            return
        end
    end
    if _G.worldScreen ~= nil and type(state.origStartGroundItems) == 'function' then
        s.internalCall = true
        pcall(state.origStartGroundItems, _G.worldScreen)
        s.internalCall = false
    elseif _G.worldScreen ~= nil and _G.worldScreen.StartGroundItems ~= nil then
        s.internalCall = true
        pcall(function() _G.worldScreen:StartGroundItems() end)
        s.internalCall = false
    end
    syncInfinityUIMessagesRect(true)
    if _G.RgIsModernHud == 1 and type(_G.Infinity_PushMenu) == 'function'
        and not isMenuOnStack('WORLD_QUICKLOOT') then
        pcall(_G.Infinity_PushMenu, 'WORLD_QUICKLOOT')
    end
end

function CZCombatQuickLoot.Sync(forceFresh, notifyIfBlocked)
    local s = state.session
    if isBlocked(forceFresh) then
        if not s.suppressing then
            local wasOn = (_G.groundItemsButtonToggle == 1) or isMenuOnStack('WORLD_QUICKLOOT')
            s.savedToggleBeforeCombat = wasOn and 1 or 0
            s.suppressing = true
        end
        closeQuickLootUI()
        if notifyIfBlocked then
            notifyBlocked()
        end
        return true
    end

    if s.suppressing then
        local shouldRestore = (s.savedToggleBeforeCombat == 1)
        s.suppressing = false
        s.savedToggleBeforeCombat = nil
        s.fixMessagesRectNextTick = false
        if shouldRestore then
            restoreQuickLootUI()
        end
    end
    return false
end

function CZCombatQuickLoot.SetEnabled(enabled)
    local clean = (enabled == true or tonumber(enabled) == 1) and 1 or 0
    state.configEnabled = clean
    state.session.cachedCombatTick = nil
    state.session.cachedCombatResult = nil
    if type(_G.Infinity_SetINIValue) == 'function' then
        pcall(_G.Infinity_SetINIValue, 'Challenge Mode', 'NoCombatQuickLoot', clean)
    end
    CZCombatQuickLoot.Sync(true, false)
end

local function wrapMethod(target, fieldOrigName, methodKey, buildWrapper)
    if target == nil then return end
    local mt = (debug and debug.getmetatable or getmetatable)(target)
    if type(mt) ~= 'table' then return end
    local index = rawget(mt, '__index')
    local methods = (type(index) == 'table' and index[methodKey] ~= nil) and index or mt
    pcall(function()
        local current = methods[methodKey]
        if not callable(current) then return end
        if state.wrappedObjects[current] then return end
        state[fieldOrigName] = current
        local wrapped = buildWrapper(current)
        methods[methodKey] = wrapped
        state.wrappedObjects[wrapped] = true
    end)
end

local function wrapWorldScreen()
    local ws = _G.worldScreen
    if ws == nil then return end

    wrapMethod(ws, 'origStartGroundItems', 'StartGroundItems', function(original)
        return function(self, ...)
            if state.session.internalCall or not rawequal(self, _G.worldScreen) then
                return original(self, ...)
            end
            if isBlocked(true) then
                local s = state.session
                if not s.suppressing then
                    -- WORLD_QUICKLOOT is only already on stack if Quick Loot was genuinely open
                    -- prior to combat; an in-combat toggle click flipped the UI var just before call.
                    s.savedToggleBeforeCombat = isMenuOnStack('WORLD_QUICKLOOT') and 1 or 0
                    s.suppressing = true
                end
                closeQuickLootUI()
                -- Set after closeQuickLootUI because InfinityUI++ rgActionbarGoldernButton12
                -- calls Infinity_SetArea('messagesRect', ..., h - 60) after StartGroundItems returns.
                s.fixMessagesRectNextTick = true
                notifyBlocked()
                return
            end
            state.session.suppressing = false
            state.session.savedToggleBeforeCombat = nil
            state.session.fixMessagesRectNextTick = false
            return original(self, ...)
        end
    end)

    wrapMethod(ws, 'origStopGroundItems', 'StopGroundItems', function(original)
        return function(self, ...)
            if state.session.internalCall or not rawequal(self, _G.worldScreen) then
                return original(self, ...)
            end
            if not isBlocked(false) then
                state.session.suppressing = false
                state.session.savedToggleBeforeCombat = nil
                state.session.fixMessagesRectNextTick = false
            end
            return original(self, ...)
        end
    end)

    wrapMethod(ws, 'origOnGroundButtonClick', 'OnGroundButtonClick', function(original)
        return function(self, ...)
            if rawequal(self, _G.worldScreen) and isBlocked(true) then
                CZCombatQuickLoot.Sync(true, true)
                return
            end
            return original(self, ...)
        end
    end)

    wrapMethod(ws, 'origOnGroundScroll', 'OnGroundScroll', function(original)
        return function(self, ...)
            if rawequal(self, _G.worldScreen) and isBlocked(false) then
                CZCombatQuickLoot.Sync(false, false)
                return
            end
            return original(self, ...)
        end
    end)

    wrapMethod(ws, 'origGroundScrollEnabled', 'GroundScrollEnabled', function(original)
        return function(self, ...)
            if rawequal(self, _G.worldScreen) and isBlocked(false) then
                return false
            end
            return original(self, ...)
        end
    end)
end

local function wrapButtonArray()
    local ba = _G.buttonArray
    if ba == nil then return end
    wrapMethod(ba, 'origGetButtonEnabled', 'GetButtonEnabled', function(original)
        return function(self, ...)
            if rawequal(self, _G.buttonArray) then
                local s = state.session
                if s.fixMessagesRectNextTick
                    or (s.suppressing and _G.groundItemsButtonToggle == 1)
                    or isMenuOnStack('WORLD_QUICKLOOT')
                    or s.suppressing then
                    pcall(CZCombatQuickLoot.Sync, false, false)
                end
            end
            return original(self, ...)
        end
    end)
end

local function wrapGlobalUiFn(name, forceFresh, notifyOnBlock)
    local fn = _G[name]
    if type(fn) ~= 'function' or state.wrappedObjects[fn] then return end
    local wrapped = function(...)
        if isBlocked(forceFresh) then
            CZCombatQuickLoot.Sync(forceFresh, notifyOnBlock)
            return nil
        end
        return fn(...)
    end
    _G[name] = wrapped
    state.wrappedObjects[wrapped] = true
end

local function wrapMenuGlobals()
    wrapWorldScreen()
    wrapButtonArray()
    wrapGlobalUiFn('getGroundItemProperty', false, false)
    wrapGlobalUiFn('getSlotContainerId', false, false)
    wrapGlobalUiFn('groundItemClick', true, true)
    wrapGlobalUiFn('showGroundItemDescription', true, true)
end

local function onTick()
    local tick = getWorldTick()
    if tick ~= nil then
        if state.session.lastTickChecked == tick then return end
        state.session.lastTickChecked = tick
    end
    CZCombatQuickLoot.Sync(false, false)
end

local function onKeyEvent()
    local s = state.session
    if isMenuOnStack('WORLD_QUICKLOOT') or _G.groundItemsButtonToggle == 1 or s.suppressing then
        local hadMenuOrToggle = isMenuOnStack('WORLD_QUICKLOOT') or (_G.groundItemsButtonToggle == 1)
        if isBlocked(true) then
            CZCombatQuickLoot.Sync(true, hadMenuOrToggle)
        else
            CZCombatQuickLoot.Sync(false, false)
        end
    end
end

local function onGameDestroyed()
    state.session = makeSession()
    wrapMenuGlobals()
end

local function onInitialized()
    wrapMenuGlobals()
    if not state.listenersInstalled then
        local addMenuLoaded = _G.EEex_Menu_AddAfterMainFileLoadedListener
            or _G.EEex_Menu_AddMainFileLoadedListener
        if type(addMenuLoaded) == 'function' then
            addMenuLoaded(function() pcall(wrapMenuGlobals) end)
        end
        if type(_G.EEex_Menu_AddAfterMainFileReloadedListener) == 'function' then
            _G.EEex_Menu_AddAfterMainFileReloadedListener(function() pcall(wrapMenuGlobals) end)
        end
        local addTick = _G.EEex_Opcode_AddDeferredListsResolvedListener
            or _G.EEex_Opcode_AddListsResolvedListener
        if type(addTick) == 'function' then
            addTick(function() pcall(onTick) end)
        end
        if type(_G.EEex_Key_AddPressedListener) == 'function' then
            _G.EEex_Key_AddPressedListener(function() pcall(onKeyEvent) end)
        end
        if type(_G.EEex_Key_AddReleasedListener) == 'function' then
            _G.EEex_Key_AddReleasedListener(function() pcall(onKeyEvent) end)
        end
        if type(_G.EEex_GameState_AddDestroyedListener) == 'function' then
            _G.EEex_GameState_AddDestroyedListener(function() pcall(onGameDestroyed) end)
        end
        state.listenersInstalled = true
    end
    state.installed = true
    log('active (combat Quick Loot suppression installed)')
    CZCombatQuickLoot.Sync(false, false)
end

if not _G.EEex_Active then
    log('inactive: EEex is required')
    return
end

local addInit = _G.EEex_GameState_AddInitializedListener
local addMenu = _G.EEex_Menu_AddAfterMainFileLoadedListener or _G.EEex_Menu_AddMainFileLoadedListener
local addTick = _G.EEex_Opcode_AddDeferredListsResolvedListener or _G.EEex_Opcode_AddListsResolvedListener

if type(addInit) ~= 'function' then
    log('inactive: missing EEex API EEex_GameState_AddInitializedListener')
    return
end
if type(addMenu) ~= 'function' then
    log('inactive: missing EEex API EEex_Menu_AddAfterMainFileLoadedListener')
    return
end
if type(addTick) ~= 'function' then
    log('inactive: missing EEex API EEex_Opcode_AddDeferredListsResolvedListener')
    return
end

addInit(function()
    local ok, err = pcall(onInitialized)
    if not ok then
        log('inactive: ' .. tostring(err))
    end
end)
