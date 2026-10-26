-- Entry of component 430. Load once from EEex_Modules.lua, before initialization.
-- No in-session hot activation. Files live in the game's CBMScroll/.
-- Every notice goes to the loader log. Only a failed start that had to keep its
-- hooks also shows one box, because that process must not load or save a game.
local function log(text) print("[CBM scroll] "..tostring(text)) end
-- Each fallback leaves 430 off for this process, so scrolls keep their normal
-- level. The technical cause follows on the next line.
local function fallback(cause)
    log("Scrolls at the reader's level (Modpack 430) are turned off for this session, so scrolls cast at their normal level. Your saves stay usable.")
    log("Cause: "..tostring(cause))
end
-- The native start says whether its rollback kept hooks; the cause text is
-- never matched. The box comes after both log lines, before the main menu, and
-- at most once per process.
local function retainedNotice()
    if CBMS_RetainedNoticeShown or not CBMS_NativeRetained() then return end
    CBMS_RetainedNoticeShown=true
    if type(EEex_MessageBox)=="function" then
        pcall(EEex_MessageBox,"chriz-bg-modpack: scrolls at the reader's level could not start cleanly. Please quit and restart the game before you load or save a game.")
    end
end
if CBMS_BootstrapLoaded then
    -- A started runtime must not keep running beside a refused second load. The
    -- native start refuses every later attempt before it reads its arguments
    -- and turns that runtime off; its binding forwards only a string and a
    -- function. The first load's health poll then logs the fallback.
    if type(CBMS_NativeStatus)=="function" and type(CBMS_NativeStart)=="function" and CBMS_NativeStatus() then
        CBMS_NativeStart("",function()end)
    end
    log("Duplicate startup refused; restart this process."); return
end
CBMS_BootstrapLoaded=true
if EEex_GameState_Private_AlreadyInitialized then
    fallback("Late activation refused. Start a fresh process before loading a game."); return
end
for _,name in ipairs({"EEex_OpenLuaBindings","EEex_GameState_AddInitializedListener",
    "EEex_Sprite_AddMarshalHandlers","EEex_Sprite_AddLoadedListener","EEex_GetUDAux",
    "EEex_Sprite_LuaHook_OnAfterEffectListUnmarshalled","EEex_Resource_Fetch",
    "EEex_AIBase_AddScriptingObjectUpdatedListener",
    "EEex_Action_AddSpriteStartedActionListener"}) do
    if type(_G[name])~="function" then fallback("Required EEex API missing: "..name); return end
end
local ok,why=pcall(function()
    EEex_OpenLuaBindings("CBMScroll")
    assert(type(CBMS_NativeStart)=="function" and type(CBMS_NativeStatus)=="function"
        and type(CBMS_NativeRetained)=="function","Native scroll startup bindings are unavailable")
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
        if not started then fallback(reason or "Native startup refused");retainedNotice();return end
        log("Native carrier groups and installed resources verified.")
        -- A scripting-object update alone can be minutes away in a quiet scene, so
        -- every creature's action start polls too. CBMS_NativeStatus only reads
        -- latched flags; after the one log entry, or a failed check, a poll is
        -- a single flag test. Nothing a poll raises reaches the engine event.
        local reported=false
        local function check()
            local healthy,detail=CBMS_NativeStatus()
            if healthy then return end
            reported=true
            fallback(detail or "Native scroll failure")
        end
        local function poll()
            if reported then return end
            local fine,problem=pcall(check)
            if not fine then
                reported=true
                pcall(function() log("Health check failed: "..tostring(problem)) end)
            end
        end
        EEex_AIBase_AddScriptingObjectUpdatedListener(poll)
        EEex_Action_AddSpriteStartedActionListener(poll)
    end)
end)
if not ok then fallback(why) end
