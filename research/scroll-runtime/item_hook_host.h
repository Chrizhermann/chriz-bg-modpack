#pragma once
#include "item_carrier_api.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Five native entries, one initialization-only rollback transaction. This is
 * not full feature activation: other dispatch/lifetime/barrier groups remain
 * required. Caller owns module/runtime lifetime and excludes all execution
 * and other patch writers until this returns. No stop-the-world assumption. */
CBMS_EXPORT int CBMS_InstallItemHooks(uintptr_t game,CBMS_Runtime*,const void* policy,uint32_t size,CBMS_PolicyDigest,void* user);
CBMS_EXPORT int CBMS_RemoveItemHooks(void);
CBMS_EXPORT const char* CBMS_ItemHookError(void);
#ifdef CBMS_OFFLINE_HARNESS
CBMS_EXPORT int CBMS_TestInstallItemHooks(const CBMS_ItemFunctions*,CBMS_Runtime*,const void*,uint32_t,CBMS_PolicyDigest,void*);
CBMS_EXPORT uintptr_t CBMS_TestItemHookAllocation(void);
CBMS_EXPORT void CBMS_TestItemHookFailure(int);
#endif
#ifdef __cplusplus
}
#endif
