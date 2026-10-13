-- Private trial entry. Load once from EEex_Modules.lua, before initialization.
-- No in-session hot activation. Files live in the trial game's CBMScroll/.
local function announce(reason)
    local text="[CBM scroll trial] "..tostring(reason)
    print(text)
    if type(EEex_MessageBox)=="function" then EEex_MessageBox(text) end
end
if CBMS_BootstrapLoaded then announce("Duplicate startup refused; restart this process."); return end
CBMS_BootstrapLoaded=true
if EEex_GameState_Private_AlreadyInitialized then
    announce("Late activation refused. Start a fresh process before loading a game."); return
end
for _,name in ipairs({"EEex_OpenLuaBindings","EEex_GameState_AddInitializedListener",
    "EEex_Sprite_AddMarshalHandlers","EEex_Sprite_AddLoadedListener","EEex_GetUDAux",
    "EEex_Sprite_LuaHook_OnAfterEffectListUnmarshalled","EEex_Resource_Fetch",
    "EEex_AIBase_AddScriptingObjectUpdatedListener"}) do
    if type(_G[name])~="function" then announce("Required EEex API missing: "..name); return end
end
local ok,why=pcall(function()
    EEex_OpenLuaBindings("CBMScroll")
    assert(type(CBMS_NativeStart)=="function" and type(CBMS_NativeStatus)=="function",
        "Native scroll startup bindings are unavailable")
    local verifier=dofile("CBMScroll/policy_resource.lua")
    local file=assert(io.open("CBMScroll/CBMSPOL1.bin","rb"))
    local bytes=file:read("*a");file:close()
    assert(type(bytes)=="string" and #bytes>0,"Installed scroll policy is empty")
    -- Register before actors can load. The native bridge stays inert until all
    -- carrier groups have installed and effective dependency hashes agree.
    dofile("CBMScroll/CBMS_ScrollMarshal.lua")
    EEex_GameState_AddInitializedListener(function()
        -- Banking installs its actor lifetime hook first; only that owner's
        -- authenticated offer may be chained at this site. The bank needs the game
        -- object, which exists only from initialization on, and its own listener
        -- comes after this one, so start it here (it runs once).
        local startBank=rawget(_G,"CBMBank_Start")
        if type(startBank)=="function" then startBank() end
        local bank=rawget(_G,"CBMBank_Identity")
        local offer=type(bank)=="table" and bank.ActorDestroyChain or nil
        local started,reason=CBMS_NativeStart(bytes,verifier.Digest,offer)
        bytes=nil
        if not started then announce(reason or "Native startup refused");return end
        print("[CBM scroll trial] Native carrier groups and installed resources verified.")
        local reported=false
        EEex_AIBase_AddScriptingObjectUpdatedListener(function()
            if reported then return end
            local healthy,detail=CBMS_NativeStatus()
            if not healthy then
                reported=true
                announce((detail or "Native scroll failure").."\nNew scroll overrides are disabled. Stop this disposable trial; do not keep its saves.")
            end
        end)
    end)
end)
if not ok then announce(why) end
