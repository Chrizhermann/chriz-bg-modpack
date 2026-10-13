// Uninstalled opcode104 entry bridge: positive permanent awards here, other
// supported permanent writes in writer_native. No quest/party redivision.
#pragma once
#include "identity_native.h"
enum CBMA_Stage : unsigned { CBMA_PREPARING=1,CBMA_NATIVE,CBMA_COMPLETING,CBMA_UNCERTAIN };
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
CBMI_API int CBMA_ApplyEffect(void* effect,void* sprite);
CBMI_API int CBMA_Query(const void* sprite,const void* effect,CBMA_View* out);
CBMI_API int CBMA_LuaQuery(void* L);
CBMI_API int CBMA_LastStatus();
