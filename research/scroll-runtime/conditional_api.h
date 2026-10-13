#pragma once
#include "native_api.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef void(*CBMS_RepeatingUpdate)(void*,void*,int);
typedef void*(*CBMS_RepeatingDecode)(const void*);
typedef struct CBMS_ConditionalFunctions {CBMS_RepeatingUpdate update;CBMS_RepeatingDecode decode;uintptr_t decode_call,fire326_return,calls[10],targets[10];} CBMS_ConditionalFunctions;
int CBMS_ConfigureConditional(CBMS_Runtime*,const CBMS_ConditionalFunctions*);
int CBMS_ConditionalIdle(void);int CBMS_DetachConditional(void);
const char* CBMS_ConditionalError(void);
int CBMS_ConditionalOwnerAt(uint32_t,uintptr_t,void*,uintptr_t*);
void CBMS_ConditionalBefore(uint32_t,uintptr_t*);
#ifdef __cplusplus
void CBMS_RepeatingCarrier(void*,void*,int) noexcept(false);
void* CBMS_RepeatingDecodeCarrier(const void*) noexcept(false);
#endif
CBMS_EXPORT int CBMS_InstallConditionalHooks(uintptr_t,CBMS_Runtime*);
CBMS_EXPORT int CBMS_RemoveConditionalHooks(void);
CBMS_EXPORT const char* CBMS_ConditionalHookError(void);
CBMS_EXPORT int CBMS_BindConditional(uintptr_t,CBMS_ConditionalFunctions*,char*,uint32_t);
#ifdef __cplusplus
}
#endif
