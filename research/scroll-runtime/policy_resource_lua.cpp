// Uses the actual generated CRes::Demand return type, UnmappedUserType. The
// explicit size is CRes.nSize, not a guessed ITM/SPL header/effect extent.
#include "infinity_loader_common_api.h"
#include "lua_bindings_core_api.h"
#include "policy_resource_hash.h"
#include <cmath>

namespace {
int resource_hash(lua_State* L) {
    const auto size = lua_tonumber(L, 2);
    const auto* data = tolua_tousertype_dynamic(L, 1, nullptr, "UnmappedUserType");
    char digest[65]{};
    if (data && lua_type(L, 2) == LUA_TNUMBER && std::isfinite(size) && size > 0 &&
        size <= 4294967295.0 && size == std::floor(size) &&
        CBMS_PolicyHashBytes(data, static_cast<std::size_t>(size), digest)) {
        lua_pushstring(L, digest); return 1;
    }
    lua_pushnil(L);
    lua_pushstring(L, "Cannot hash the complete demanded resource buffer");
    return 2;
}
}
void CBMS_OpenResourceHash(lua_State* L) {
    lua_pushcclosure(L, resource_hash, 0); lua_setglobal(L, "CBMS_NativeResourceSHA256");
}
