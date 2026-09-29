if not EEex_Active then
    print("[CBM story utility XP] EEex is inactive; launch with InfinityLoader.")
    return
end
for _, name in ipairs({
    "EEex_Menu_AddAfterMainFileLoadedListener", "EEex_Menu_AddAfterMainFileReloadedListener",
    "EEex_GameState_AddInitializedListener", "EEex_GameState_AddDestroyedListener",
    "EEex_Action_AddSpriteStartedActionListener", "EEex_GameState_GetGlobalInt",
    "EEex_Resource_Load2DA", "EEex_UDToPtr",
}) do
    if type(_G[name]) ~= "function" then
        print("[CBM story utility XP] Required EEex API is missing: " .. name)
        return
    end
end
local ok, err = pcall(function()
    Infinity_DoFile("CBMSXP")
    Infinity_DoFile("CBMSXRT")
end)
if not ok then print("[CBM story utility XP] Initialization failed: " .. tostring(err)) end
