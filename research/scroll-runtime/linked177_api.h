#pragma once
#include "native_api.h"
#ifdef __cplusplus
#define CBMS_LINKED_THROWS noexcept(false)
extern "C" {
#else
#define CBMS_LINKED_THROWS
#endif
typedef int (*CBMS_LinkedApply)(void*,void*);
typedef void* (*CBMS_LinkedDecode)(const void*);
typedef struct CBMS_LinkedFunctions { CBMS_LinkedApply apply; CBMS_LinkedDecode decode; uintptr_t call_site; } CBMS_LinkedFunctions;
CBMS_EXPORT int CBMS_ConfigureLinked177(CBMS_Runtime*,const CBMS_LinkedFunctions*);
CBMS_EXPORT int CBMS_Linked177Idle(void);
CBMS_EXPORT int CBMS_DetachLinked177(void);
CBMS_EXPORT const char* CBMS_Linked177Error(void);
CBMS_EXPORT int CBMS_Linked177Apply(void*,void*) CBMS_LINKED_THROWS;
CBMS_EXPORT void* CBMS_Linked177Decode(const void*) CBMS_LINKED_THROWS;
CBMS_EXPORT int CBMS_InstallLinked177Hooks(uintptr_t,CBMS_Runtime*);
CBMS_EXPORT int CBMS_RemoveLinked177Hooks(void);
CBMS_EXPORT int CBMS_BindLinked177(uintptr_t,CBMS_LinkedFunctions*,char*,uint32_t);
CBMS_EXPORT const char* CBMS_Linked177HookError(void);
#ifdef CBMS_OFFLINE_HARNESS
CBMS_EXPORT void* CBMS_TestLinked177Decode(uintptr_t,const void*) CBMS_LINKED_THROWS;
CBMS_EXPORT int CBMS_TestInstallLinked177Hooks(const CBMS_LinkedFunctions*,CBMS_Runtime*);
CBMS_EXPORT uintptr_t CBMS_TestLinked177Allocation(void);
CBMS_EXPORT void CBMS_TestLinked177Failure(int);
#endif
#ifdef __cplusplus
}
#endif
#undef CBMS_LINKED_THROWS
