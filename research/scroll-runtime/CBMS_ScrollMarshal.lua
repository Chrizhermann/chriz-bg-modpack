-- Actor envelope adapter. The startup transaction attaches its native runtime.
-- No numbers represent UUIDs, runtime addresses or origin IDs in this format.
local handlerName, stateKey = "CBM_SCROLL_CONTEXT", "CBMS_ScrollMarshal"

local function state(sprite)
    local aux = EEex_GetUDAux(sprite)
    local value = aux[stateKey]
    if not value then value = {}; aux[stateKey] = value end
    return value, aux
end

local function reject(value, reason)
    value.error = reason
    CBMS_NativeRejectEnvelope(reason) -- native latch survives EEex TryIgnore
end

local function importer(sprite, envelope)
    local value = state(sprite)
    if not CBMS_NativeHealthy() then
        value.raw = envelope
        value.error = "scroll native bridge unavailable; retained unchanged"
        return
    end
    value.raw = envelope
    -- A missing payload or an unknown serialized format is unreadable only for
    -- this actor. The native importer stages its local drop reason and remains
    -- healthy for other actors. Extra Lua fields do not prevent reading payload.
    local payload = type(envelope) == "table" and envelope.schema == 1 and envelope.payload
    if type(payload) ~= "string" then payload = "" end
    local ok, reason = CBMS_NativeStage(sprite, payload)
    if not ok then reject(value, reason or "native scroll actor envelope rejected") end
end

local function exporter(sprite)
    local value, aux = state(sprite)
    local fallback = aux.EEex_Sprite_FallbackMarshalStorage
    if fallback and fallback[handlerName] ~= nil then
        -- EEex appends fallback storage separately. Returning it here too
        -- duplicates the handler. Late activation cannot infer decoded pairs.
        if not value.fallbackLogged then
            print("[CBM scroll] Actor scroll data loaded before its handler; retaining that actor's data until reload.")
            value.fallbackLogged = true
        end
        return nil
    end
    if value.raw ~= nil then return value.raw end
    if not CBMS_NativeHealthy() then return nil end
    local payload, reason = CBMS_NativeExport(sprite)
    if payload == nil then
        reject(value, reason or "native scroll envelope export failed")
        return nil
    end
    if payload == "" then return nil end -- ordinary actor, no owned effects
    return {schema = 1, payload = payload}
end

EEex_Sprite_AddMarshalHandlers(handlerName, exporter, importer)
-- Independent DLL route: EEex has updated both UUID local fields before this
-- function. Bind before its earlier callbacks/listeners can dispatch spells.
-- Installing after load is insufficient; reload is required for saved pairs.
local previousLoaded = EEex_Sprite_LuaHook_OnAfterEffectListUnmarshalled
if type(previousLoaded) == "function" then
    EEex_Sprite_LuaHook_OnAfterEffectListUnmarshalled = function(sprite)
        if CBMS_NativeHealthy() then
            local variable = sprite.m_pLocalVariables:find("EEEX_UUID")
            if variable then
                CBMS_NativeActorUUID(sprite, variable.m_intValue, variable.m_dWValue)
            else
                CBMS_NativeRejectEnvelope("EEex actor UUID local missing after native registration")
            end
        end
        return previousLoaded(sprite)
    end
end
-- Loaded listeners run before the engine sets an actor's display name and CRE
-- resref (both still empty in the lab), so name it by what is already loaded:
-- its creature name string, its script name and EEex's UUID.
local function describe(sprite)
    local name, details = nil, {}
    pcall(function()
        local text = sprite.m_sName.m_pchData:get()
        if text == "" then text = Infinity_FetchString(sprite.m_baseStats.m_name) end
        if type(text) == "string" and text ~= "" then name = text end
    end)
    pcall(function()
        local script = sprite.m_scriptName:get()
        if type(script) == "string" and script ~= "" and script ~= "None" then details[#details + 1] = script end
    end)
    pcall(function()
        local variable = sprite.m_pLocalVariables:find("EEEX_UUID")
        if not variable then return end
        -- 16-bit pieces, which every supported Lua formats exactly.
        local high, low = variable.m_dWValue, variable.m_intValue % 4294967296
        local digits = string.format("%04X%04X%04X%04X", math.floor(high / 65536), high % 65536,
            math.floor(low / 65536), low % 65536)
        details[#details + 1] = "UUID " .. (digits:gsub("^0+(%x)", "%1"))
    end)
    if name and #details > 0 then return name .. " (" .. table.concat(details, ", ") .. ")" end
    if name then return name end
    if #details > 0 then return "actor " .. table.concat(details, ", ") end
    return "an actor"
end

EEex_Sprite_AddLoadedListener(function(sprite)
    local value = state(sprite)
    if value.error then return end
    local finished, dropped = CBMS_NativeImportFinished(sprite)
    if not finished then return end
    value.raw = nil -- native association committed before loaded listeners
    if dropped then
        -- The envelope no longer matched this actor's records, so the next
        -- save writes only what this load owns for this actor. That does not
        -- cover actors in areas not loaded since, or envelopes kept unparsed
        -- while 430 is off: those are saved again unchanged. Nothing else is
        -- turned off.
        print("[CBM scroll] Dropped outdated scroll data for " .. describe(sprite) .. " only: " ..
            dropped .. ". Its effects keep their levels; spells they cast later use the normal level.")
    end
end)
