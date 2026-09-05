-- Engine bootstrap; filenames loaded by the game have at most eight characters.
if not EEex_Active then
    print("[CBM utility XP] EEex is inactive; launch the game with InfinityLoader.")
    return
end
for _, name in ipairs({
    "EEex_Menu_AddAfterMainFileLoadedListener", "EEex_Menu_AddAfterMainFileReloadedListener",
    "EEex_GameState_AddInitializedListener", "EEex_GameState_AddDestroyedListener",
    "EEex_Action_AddSpriteStartedActionListener", "EEex_Resource_Load2DA",
    "EEex_GameObject_Get", "EEex_UDToPtr",
}) do
    if type(_G[name]) ~= "function" then
        print("[CBM utility XP] Required EEex API is missing: " .. name .. ". Update EEex.")
        return
    end
end
local ok, err = pcall(function()
    Infinity_DoFile("CBMUXPC")
    Infinity_DoFile("CBMUXP")
    Infinity_DoFile("CBMUXRT")
end)
if not ok then
    print("[CBM utility XP] Initialization failed: " .. tostring(err))
end
