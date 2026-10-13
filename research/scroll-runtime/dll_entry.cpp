// Independent InfinityLoader binding DLL entry points. OpenLuaBindings is a
// supported loader API; no replacement of EEex.dll / global owner is required.
// No hooks are installed by either entry point.
#include "infinity_loader_common_api.h"
#include "lua_bindings_core_api.h"
#include "eeex_save_bridge.h"
#include "startup.h"

SharedState sharedState;
void CBMS_OpenResourceHash(lua_State*);
extern "C" CBMS_EXPORT void __stdcall InitBindings(SharedState value) {
    sharedState() = value;
}
extern "C" CBMS_EXPORT void __stdcall OpenBindings() {
    InitLuaBindingsCommon(sharedState());
    CBMS_EEexOpenLua(luaState());
    CBMS_OpenResourceHash(luaState());
    CBMS_OpenStartup(luaState());
}
