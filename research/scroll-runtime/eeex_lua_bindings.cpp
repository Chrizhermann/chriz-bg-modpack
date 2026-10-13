/* Compile as an EEex-Core source file against the real InfinityLoader headers.
 * No invented EEex_Call, DLL-loading API or numeric actor pointer conversion. */
#include "infinity_loader_common_api.h"
#include "lua_bindings_core_api.h"
#include "eeex_save_bridge.h"
#include <limits>
#include <cmath>

namespace {
void* actor(lua_State* L) {
    return tolua_tousertype_dynamic(L, 1, nullptr, "CGameSprite");
}
int export_text(lua_State* L) {
    auto* sprite = actor(L);
    const char* text = sprite ? CBMS_EEexExportText(sprite) : nullptr;
    if (text) { lua_pushstring(L, text); return 1; }
    lua_pushnil(L); lua_pushstring(L, CBMS_EEexBridgeError()); return 2;
}
int stage_text(lua_State* L) {
    auto* sprite = actor(L);
    size_t length{};
    const char* text = lua_type(L, 2) == LUA_TSTRING ? lua_tolstring(L, 2, &length) : nullptr;
    const bool valid = sprite && text && length <= (std::numeric_limits<uint32_t>::max)();
    const int status = valid ? CBMS_EEexStageText(sprite, text, static_cast<uint32_t>(length)) : 0;
    if (!valid) CBMS_EEexRejectEnvelope("actor envelope binding requires CGameSprite and bounded string");
    lua_pushboolean(L, status); lua_pushstring(L, CBMS_EEexBridgeError()); return 2;
}
int finished(lua_State* L) { lua_pushboolean(L, CBMS_EEexImportFinished(actor(L))); return 1; }
int healthy(lua_State* L) { lua_pushboolean(L, CBMS_EEexBridgeHealthy()); return 1; }
int actor_uuid(lua_State* L) {
    auto* sprite = actor(L);
    const double low = lua_tonumber(L, 2), high = lua_tonumber(L, 3);
    if (!sprite || lua_type(L, 2) != LUA_TNUMBER || lua_type(L, 3) != LUA_TNUMBER ||
        !std::isfinite(low) || !std::isfinite(high) || std::floor(low) != low || std::floor(high) != high ||
        low < -2147483648.0 || low > 4294967295.0 || high < 0.0 || high > 4294967295.0) {
        CBMS_EEexRejectEnvelope("EEex UUID binding requires exact 32-bit local fields");
        lua_pushboolean(L, 0); return 1;
    }
    const auto uuid = (static_cast<uint64_t>(high) << 32) | static_cast<uint32_t>(static_cast<int64_t>(low));
    if (!uuid) CBMS_EEexRejectEnvelope("EEex actor UUID is absent after native registration");
    else CBMS_EEexAfterActorUUID(sprite, uuid);
    lua_pushboolean(L, CBMS_EEexBridgeHealthy()); return 1;
}
int reject(lua_State* L) {
    const char* reason = lua_type(L, 1) == LUA_TSTRING ? lua_tolstring(L, 1, nullptr) : nullptr;
    CBMS_EEexRejectEnvelope(reason ? reason : "invalid actor envelope"); return 0;
}
}
void CBMS_EEexOpenLua(lua_State* L) {
    struct Binding { const char* name; lua_CFunction function; };
    for (const auto& binding : {
        Binding{"CBMS_NativeExport", export_text}, Binding{"CBMS_NativeStage", stage_text},
        Binding{"CBMS_NativeImportFinished", finished}, Binding{"CBMS_NativeHealthy", healthy},
        Binding{"CBMS_NativeActorUUID", actor_uuid},
        Binding{"CBMS_NativeRejectEnvelope", reject}}) {
        lua_pushcclosure(L, binding.function, 0); lua_setglobal(L, binding.name);
    }
}
