#pragma once
#include "dispatch_carrier_api.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Initialization only, after existing EEex mode0 routes. All execution/writers
 * must be excluded; module/runtime lifetime remains owned by the full host. */
CBMS_EXPORT int CBMS_InstallDispatchHooks(uintptr_t game,CBMS_Runtime*);
CBMS_EXPORT int CBMS_RemoveDispatchHooks(void);
CBMS_EXPORT const char* CBMS_DispatchHookError(void);
#ifdef CBMS_OFFLINE_HARNESS
CBMS_EXPORT int CBMS_TestInstallDispatchHooks(const CBMS_DispatchFunctions*,CBMS_Runtime*);
CBMS_EXPORT uintptr_t CBMS_TestDispatchHookAllocation(void);
CBMS_EXPORT void CBMS_TestDispatchHookFailure(int);
#endif
#ifdef __cplusplus
}
#endif
