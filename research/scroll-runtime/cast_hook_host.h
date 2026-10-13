#pragma once
#include "cast_carrier_api.h"
#ifdef __cplusplus
extern "C" {
#endif
CBMS_EXPORT int CBMS_BindCastModule(uintptr_t,CBMS_CastFunctions*,char*,uint32_t);
CBMS_EXPORT int CBMS_InstallCastHooks(uintptr_t,CBMS_Runtime*);
CBMS_EXPORT int CBMS_RemoveCastHooks(void);
CBMS_EXPORT const char* CBMS_CastHookError(void);
#ifdef CBMS_OFFLINE_HARNESS
CBMS_EXPORT int CBMS_TestInstallCastHooks(const CBMS_CastFunctions*,CBMS_Runtime*);
CBMS_EXPORT uintptr_t CBMS_TestCastHookAllocation(uint32_t selection);
CBMS_EXPORT void CBMS_TestCastHookFailure(uint32_t selection,int point);
#endif
#ifdef __cplusplus
}
#endif
