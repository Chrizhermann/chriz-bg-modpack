#pragma once
#include "action_carrier_api.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Explicit inert-host entry points; no automatic registration. Initialization
 * must exclude native execution and code writers; retain module/runtime until
 * quiescent removal. Install before dispatch's default-constructor observer. */
CBMS_EXPORT int CBMS_InstallActionHooks(uintptr_t game,CBMS_Runtime*);
CBMS_EXPORT int CBMS_ActionHooksReadyRemove(void);
CBMS_EXPORT int CBMS_RemoveActionHooks(void);
CBMS_EXPORT const char* CBMS_ActionHookError(void);
#ifdef CBMS_OFFLINE_HARNESS
CBMS_EXPORT int CBMS_TestInstallActionHooks(const CBMS_ActionFunctions*,CBMS_Runtime*);
CBMS_EXPORT uintptr_t CBMS_TestActionHookAllocation(void);
CBMS_EXPORT void CBMS_TestActionHookFailure(int);
#endif
#ifdef __cplusplus
}
#endif
