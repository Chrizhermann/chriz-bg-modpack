#pragma once
#include "item_carrier_api.h"
#ifdef __cplusplus
extern "C" {
#endif
/* One engine-initialization thread, before native gameplay/actor loading. No
 * LoadLibrary, late hot activation or game writes. Failed rollback retains the
 * module/runtime; the process must exit before another attempt. */
CBMS_EXPORT int CBMS_StartCurrent(const void*,uint32_t,CBMS_PolicyDigest,void*);
CBMS_EXPORT int CBMS_StartCurrentWithBank(const void*,uint32_t,CBMS_PolicyDigest,void*,CBMS_BankActorQuery,void*);
CBMS_EXPORT int CBMS_StartupHealthy(void);
CBMS_EXPORT const char* CBMS_StartupError(void);
/* 1 once a failed start could not remove every hook and kept its runtime, so the
 * player must restart before loading or saving a game. Engine thread only. */
CBMS_EXPORT int CBMS_StartupRetained(void);
#ifdef __cplusplus
}
struct lua_State;
void CBMS_OpenStartup(lua_State*);
#endif
