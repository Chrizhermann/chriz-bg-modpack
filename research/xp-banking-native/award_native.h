// Uninstalled opcode104 entry bridge: positive permanent awards here, other
// supported permanent writes in writer_native. No quest/party redivision.
#pragma once
#include "identity_native.h"
// WITHDRAWING: the uncertain callback is asked to withdraw the journal of a
// preparation that no store followed; it returns true only when it did.
enum CBMA_Stage : unsigned { CBMA_PREPARING=1,CBMA_NATIVE,CBMA_COMPLETING,CBMA_UNCERTAIN,CBMA_WITHDRAWING };
struct CBMA_Config {
    uint64_t abi;
    uintptr_t original,before,complete,uncertain,lua_tolstring,lua_pushstring;
};
struct CBMA_View {
    uint64_t incarnation;
    uint32_t pre_base,amount,applied,remainder,post_base;
    int native_result;
    CBMA_Stage stage;
};
// before(sprite,effect): 1=tracked,2=unowned passthrough,0=refused.
// complete/uncertain(sprite,effect) use protected Lua callbacks.
CBMI_API int CBMA_Configure(const CBMA_Config*);
// Returns 0 only when a committed award's original leaf did. Every path that
// does not commit returns 1: native (original award, unbanked), defer (neither
// done nor repass: resolved again next pass) or complete (done without XP).
CBMI_API int CBMA_ApplyEffect(void* effect,void* sprite);
CBMI_API int CBMA_Query(const void* sprite,const void* effect,CBMA_View* out);
CBMI_API int CBMA_LuaQuery(void* L);
CBMI_API int CBMA_LastStatus();
// Native fallbacks: awards that ran the original because banking could not
// (not unowned passthroughs). last_status may be null.
CBMI_API uint64_t CBMA_Fallbacks(int* last_status);
// Lua: total fallbacks (award+writer), last award and writer status, changes
// whose lifetime ended while prepared (11), the setter writes kept unwritten
// (12) and their list (CBMW_Kept). Six values.
CBMI_API int CBMA_LuaFallbacks(void* L);
// Same-DLL coordination, not exported; bits as CBMW_Holds.
int CBMA_Holds(const void* sprite,uint64_t incarnation);
