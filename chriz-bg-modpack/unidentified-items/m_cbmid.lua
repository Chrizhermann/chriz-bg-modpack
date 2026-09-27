-- Deliberately report initialization failure rather than silently leaving some
-- unidentified-item displays exposed. This script never modifies save data.
if not (CBMID_State and CBMID_State.installed) then
    Infinity_DoFile("CBMIDCFG")
    Infinity_DoFile("CBMID")
    CBMID.install(CBMID_Config)
end
