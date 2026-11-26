-- Clear lingering area/room-pulsed effects immediately upon leaving the room
-- or area (component 698: cbm_area_effects_clear_on_leave).
-- Compatible with BG:EE, SoD, BG2:EE, EET on EEex v1.2.0 and v1.3.1
-- (Lua 5.1, Lua 5.2, LuaJIT 2.1).

if not EEex_Active then
	return
end

local existing = rawget(_G, "CZRMFX")
if type(existing) == "table" and existing._registered then
	return
end

local CZRMFX = existing or {}
_G.CZRMFX = CZRMFX

-- Room-pulsed hazard resrefs only; creature combat rays/spells such as SPIN550B,
-- SPIN992B, SPIN689D, SPIN779, SPCL132, SPWM128, and hub permanent OHBANTIM are
-- intentionally excluded so legitimate combat debuffs are never stripped.
local function isInsideWatchersKeepIceRoom(sprite)
	if not sprite then
		return true
	end
	local ok, x, y = pcall(function()
		local pos = sprite.m_pos
		if not pos then
			return nil, nil
		end
		return pos.x, pos.y
	end)
	if not ok or x == nil or y == nil then
		return true
	end
	return x >= 1775 and x <= 2375 and y >= 2400
end

local ROOM_EFFECTS = {
	["SPIN646"] = {
		-- Dead Magic Area (14s pulse): AR3004/AR3008 Watcher's Keep Maze, BD0063 SoD canyon.
		areas = { AR3004 = true, AR3008 = true, BD0063 = true },
		refreshesToolbar = true,
	},
	["SPIN645"] = {
		-- Wild Magic Area (14s pulse): AR3005/AR3009 WK Maze, OH6000/OH6100/OH6200 Neera.
		areas = { AR3005 = true, AR3009 = true, OH6000 = true, OH6100 = true, OH6200 = true },
	},
	["SPIN778"] = {
		-- Wild Magic Zone variant: bound dynamically to whichever area applied it.
		areas = nil,
	},
	["OHNWILDX"] = {
		-- Vicross anti-wild-magic field (7s pulse): OH6400.
		areas = { OH6400 = true },
		refreshesToolbar = true,
	},
	["SPIN628"] = {
		-- Slow Freeze (3s pulse): Watcher's Keep Level 2 Ice Library inside AR3016.
		areas = { AR3016 = true },
		subroomCheck = isInsideWatchersKeepIceRoom,
	},
	["SPIN628A"] = {
		-- Spell Revisions / chriz-bg-magic subspell for SPIN628.
		areas = { AR3016 = true },
		subroomCheck = isInsideWatchersKeepIceRoom,
	},
}

CZRMFX.ROOM_EFFECTS = ROOM_EFFECTS
CZRMFX._spriteState = CZRMFX._spriteState or {}
CZRMFX._lastVisibleArea = nil
CZRMFX._refreshingToolbar = false
CZRMFX._menuHooked = false

local function getAreaResref(sprite)
	if not sprite then
		return nil
	end
	local ok, areaRes = pcall(function()
		local area = sprite.m_pArea
		if not area then
			return nil
		end
		local resrefObj = area.m_resref
		if not resrefObj then
			return nil
		end
		if type(resrefObj) == "string" then
			return resrefObj
		end
		if type(resrefObj.get) == "function" then
			return resrefObj:get()
		end
		return nil
	end)
	if not ok or type(areaRes) ~= "string" or areaRes == "" then
		return nil
	end
	return string.upper(areaRes)
end

local function getVisibleAreaResref()
	local ok, areaRes = pcall(function()
		local chitin = EEex_EngineGlobal_CBaldurChitin
		if not chitin or not chitin.m_pObjectGame then
			return nil
		end
		local game = chitin.m_pObjectGame
		if type(EEex_Area_GetVisible) == "function" then
			local area = EEex_Area_GetVisible()
			if area and area.m_resref then
				local r = area.m_resref
				return type(r) == "string" and r or r:get()
			end
		end
		if game.m_gameAreas and game.m_visibleArea ~= nil then
			local area = game.m_gameAreas:get(game.m_visibleArea)
			if area and area.m_resref then
				local r = area.m_resref
				return type(r) == "string" and r or r:get()
			end
		end
		return nil
	end)
	if not ok or type(areaRes) ~= "string" or areaRes == "" then
		return nil
	end
	return string.upper(areaRes)
end

local function getSourceResref(effect)
	if not effect then
		return nil
	end
	local res = effect.m_sourceRes
	if not res then
		return nil
	end
	local raw = type(res) == "string" and res or (type(res.get) == "function" and res:get() or nil)
	if type(raw) ~= "string" or raw == "" then
		return nil
	end
	return string.upper(raw)
end

local function iterateTimedEffects(sprite, callback)
	local ok, list = pcall(function()
		return sprite.m_timedEffectList
	end)
	if not ok or not list then
		return
	end
	if type(EEex_Utility_IterateCPtrList) == "function" then
		EEex_Utility_IterateCPtrList(list, callback)
		return
	end
	if type(list) == "table" then
		for _, eff in ipairs(list) do
			if callback(eff) then
				break
			end
		end
	end
end

local function isSelectedOrInParty(spriteID)
	local okSelected, selectedID = pcall(function()
		if type(EEex_Sprite_GetSelectedID) == "function" then
			return EEex_Sprite_GetSelectedID()
		end
		return nil
	end)
	if okSelected and selectedID == spriteID then
		return true
	end
	if type(EEex_Sprite_GetInPortraitID) == "function" then
		for slot = 0, 5 do
			local okSlot, slotID = pcall(EEex_Sprite_GetInPortraitID, slot)
			if okSlot and slotID == spriteID then
				return true
			end
		end
	end
	return false
end

function CZRMFX.refreshToolbar()
	if CZRMFX._refreshingToolbar then
		return false
	end
	CZRMFX._refreshingToolbar = true
	local ok = pcall(function()
		local array = type(EEex_Actionbar_GetArray) == "function" and EEex_Actionbar_GetArray() or nil
		if array and type(array.UpdateButtons) == "function" then
			array:UpdateButtons()
			return
		end
		if type(EEex_Actionbar_GetState) == "function" and type(EEex_Actionbar_SetState) == "function" then
			local state = EEex_Actionbar_GetState()
			if type(state) == "number" and state >= 0 then
				EEex_Actionbar_SetState(state)
			end
		end
	end)
	CZRMFX._refreshingToolbar = false
	return ok
end

local function stripEffectRes(sprite, spriteID, resref)
	if type(EEex_GameObject_ApplyEffect) ~= "function" then
		return false
	end
	local ok = pcall(EEex_GameObject_ApplyEffect, sprite, {
		["effectID"] = 321,
		["res"] = resref,
		["durationType"] = 1,
		["noSave"] = 1,
		["immediateResolve"] = 1,
		["sourceID"] = spriteID,
		["sourceTarget"] = spriteID,
	})
	return ok
end

function CZRMFX.checkSprite(sprite)
	if not sprite then
		return false, false
	end
	local okId, spriteID = pcall(function()
		return sprite.m_id
	end)
	if not okId or spriteID == nil then
		return false, false
	end

	local areaRes = getAreaResref(sprite)
	if not areaRes then
		return false, false
	end

	local state = CZRMFX._spriteState[spriteID]
	if not state then
		state = {
			lastArea = nil,
			dynamicAreaByRes = {},
			hadResLastCheck = {},
		}
		CZRMFX._spriteState[spriteID] = state
	end

	local presentRes = {}
	local anyTracked = false
	iterateTimedEffects(sprite, function(effect)
		local sourceRes = getSourceResref(effect)
		if sourceRes and ROOM_EFFECTS[sourceRes] then
			presentRes[sourceRes] = true
			anyTracked = true
		end
	end)

	local strippedAny = false
	local refreshToolbar = false

	if anyTracked then
		local prevArea = state.lastArea
		local prevHad = state.hadResLastCheck
		local dyn = state.dynamicAreaByRes

		for resref, _ in pairs(presentRes) do
			local cfg = ROOM_EFFECTS[resref]
			local validHere = false
			if cfg.areas and cfg.areas[areaRes] then
				if not cfg.subroomCheck or cfg.subroomCheck(sprite) then
					validHere = true
					dyn[resref] = areaRes
				end
			else
				if dyn[resref] == areaRes and (not cfg.subroomCheck or cfg.subroomCheck(sprite)) then
					validHere = true
				elseif prevArea == areaRes and not prevHad[resref] then
					-- Newly applied while already standing inside a non-canonical/modded area.
					validHere = true
					dyn[resref] = areaRes
				end
			end

			if not validHere then
				if stripEffectRes(sprite, spriteID, resref) then
					strippedAny = true
					if cfg.refreshesToolbar then
						refreshToolbar = true
					end
				end
				presentRes[resref] = nil
				dyn[resref] = nil
			end
		end
	end

	-- Clear recorded dynamic areas for effects that already expired normally.
	for resref, _ in pairs(state.dynamicAreaByRes) do
		if not presentRes[resref] then
			state.dynamicAreaByRes[resref] = nil
		end
	end

	state.lastArea = areaRes
	state.hadResLastCheck = presentRes

	if refreshToolbar and isSelectedOrInParty(spriteID) then
		CZRMFX.refreshToolbar()
	end

	return strippedAny, refreshToolbar
end

function CZRMFX.sweepParty(force)
	local visibleArea = getVisibleAreaResref()
	if not force and visibleArea and visibleArea == CZRMFX._lastVisibleArea then
		return false
	end
	if visibleArea then
		CZRMFX._lastVisibleArea = visibleArea
	end

	if type(EEex_Sprite_GetInPortrait) ~= "function" then
		return false
	end
	local anyStripped = false
	for slot = 0, 5 do
		local okSprite, sprite = pcall(EEex_Sprite_GetInPortrait, slot)
		if okSprite and sprite then
			local stripped = CZRMFX.checkSprite(sprite)
			if stripped then
				anyStripped = true
			end
		end
	end
	return anyStripped
end

function CZRMFX.reset()
	CZRMFX._spriteState = {}
	CZRMFX._lastVisibleArea = nil
end

local function hookActionbarMenu()
	if CZRMFX._menuHooked then
		return
	end
	if type(EEex_Menu_Find) ~= "function" or type(EEex_Menu_GetItemFunction) ~= "function" or type(EEex_Menu_SetItemFunction) ~= "function" then
		return
	end
	pcall(function()
		local actionbarMenu = EEex_Menu_Find("WORLD_ACTIONBAR")
		if not actionbarMenu or not actionbarMenu.reference_onOpen then
			return
		end
		local prevOnOpen = EEex_Menu_GetItemFunction(actionbarMenu.reference_onOpen)
		EEex_Menu_SetItemFunction(actionbarMenu.reference_onOpen, function(...)
			CZRMFX.sweepParty(false)
			if prevOnOpen then
				return prevOnOpen(...)
			end
		end)
		CZRMFX._menuHooked = true
	end)
end

local function register()
	if CZRMFX._registered then
		return
	end
	if type(EEex_Opcode_AddListsResolvedListener) ~= "function" then
		return
	end
	EEex_Opcode_AddListsResolvedListener(function(sprite)
		CZRMFX.checkSprite(sprite)
	end)
	if type(EEex_GameState_AddDestroyedListener) == "function" then
		EEex_GameState_AddDestroyedListener(function()
			CZRMFX.reset()
		end)
	end
	if type(EEex_Actionbar_AddButtonsUpdatedListener) == "function" then
		EEex_Actionbar_AddButtonsUpdatedListener(function()
			CZRMFX.sweepParty(false)
		end)
	end
	if type(EEex_Menu_AddAfterMainFileLoadedListener) == "function" then
		EEex_Menu_AddAfterMainFileLoadedListener(function()
			CZRMFX._menuHooked = false
			hookActionbarMenu()
		end)
	end
	hookActionbarMenu()
	CZRMFX._registered = true
end

register()
