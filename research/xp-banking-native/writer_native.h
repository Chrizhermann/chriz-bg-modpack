// Uninstalled scoped stat44 branch bridge. Other stats never enter this function.
#pragma once
#include "identity_native.h"
enum CBMW_Stage:unsigned{CBMW_PREPARING=1,CBMW_WRITING,CBMW_COMPLETING,CBMW_UNCERTAIN};
struct CBMW_Config{uint64_t abi;uintptr_t setter,before,complete,uncertain,lua_tolstring,lua_pushstring,lua_pushboolean;};
struct CBMW_View{uint64_t incarnation;uint32_t raw_value,mode,pre_base,post_base,planned_base,origin;CBMW_Stage stage;bool planned;
    uint32_t source,effect_mode;int native_result;const void* effect;};
CBMI_API int CBMW_Configure(const CBMW_Config*);
// RDX is the native switch destination, deliberately unused. RCX/R8/R9 carry
// actor/value/mode. Return original actor so native continuation restores RCX.
CBMI_API void* CBMW_Write(void* sprite,uintptr_t unused,uint32_t value,uint32_t mode);
// Actual permanent opcode104 leaf caller only; no effect or XP writes for a
// rejected plan. Positive additions use the separate award overflow bridge.
CBMI_API int CBMW_EffectWrite(void* effect,void* sprite,uintptr_t original_leaf);
CBMI_API int CBMW_Query(const void*,CBMW_View*);
CBMI_API int CBMW_Plan(const void*,uint32_t target);
CBMI_API int CBMW_ApplyOwnedSet(void*,uint32_t target,uint32_t origin,uint16_t* native_result);
CBMI_API int CBMW_LuaQuery(void*);
CBMI_API int CBMW_LuaPlan(void*);
CBMI_API int CBMW_LuaApplyOwnedSet(void*);
CBMI_API int CBMW_LastStatus();
