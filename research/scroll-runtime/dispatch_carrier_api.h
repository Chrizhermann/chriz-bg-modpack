#pragma once
#include "native_api.h"
#ifdef __cplusplus
#define CBMS_DISPATCH_THROWS noexcept(false)
extern "C" {
#else
#define CBMS_DISPATCH_THROWS
#endif
typedef int (*CBMS_ApplyOriginal)(void*,void*);
typedef void* (*CBMS_ActionDefaultOriginal)(void*);
typedef int16_t (*CBMS_AddMessageOriginal)(void*,void*,int);
typedef void (*CBMS_MessageRunOriginal)(void*);
/* Actual deleting destructor consumes flags in EDX and returns this in RAX.
 * The generated base CMessage vtable declaration omits those ABI details. */
typedef void* (*CBMS_MessageDestroyOriginal)(void*,uint32_t);
typedef struct CBMS_DispatchFunctions {
    CBMS_ApplyOriginal apply146,apply148;
    CBMS_ActionDefaultOriginal action_default;
    CBMS_AddMessageOriginal add_message;
    CBMS_MessageRunOriginal fire_run;
    CBMS_MessageDestroyOriginal fire_destroy;
    uintptr_t action_default_returns[2],fire_add_return,fire_run_return;
    uintptr_t effect_fire_return,point_fire_return,fire_vtable;
    /* CMessageInsertAction vtable and the engine global holding the shared
     * empty CString, both certified with the producer bodies. */
    uintptr_t insert_vtable,empty_string;
} CBMS_DispatchFunctions;
CBMS_EXPORT int CBMS_BindDispatchModule(uintptr_t game,CBMS_DispatchFunctions*,char* diagnostic,uint32_t capacity);
CBMS_EXPORT int CBMS_ConfigureDispatchCarriers(CBMS_Runtime*,const CBMS_DispatchFunctions*);
CBMS_EXPORT int CBMS_DispatchCarriersIdle(void);
CBMS_EXPORT int CBMS_DetachDispatchCarriers(void);
CBMS_EXPORT const char* CBMS_DispatchCarrierError(void);
CBMS_EXPORT int CBMS_Apply146Carrier(void*,void*) CBMS_DISPATCH_THROWS;
CBMS_EXPORT int CBMS_Apply148Carrier(void*,void*) CBMS_DISPATCH_THROWS;
CBMS_EXPORT void* CBMS_ActionDefaultCarrier(void*) CBMS_DISPATCH_THROWS;
CBMS_EXPORT int16_t CBMS_AddMessageCarrier(void*,void*,int) CBMS_DISPATCH_THROWS;
CBMS_EXPORT void CBMS_FireMessageRunCarrier(void*) CBMS_DISPATCH_THROWS;
CBMS_EXPORT void* CBMS_FireMessageDestroyCarrier(void*,uint32_t) CBMS_DISPATCH_THROWS;
/* Native cast-entry units only: strict audited producer/run return PC and
 * receiver match; 0 leaves an independent/masking cast, 1 supplies ownership.
 * Selectors0/1/2 only. Action casts (3-6) read the witness carried by the
 * receiver's current action itself (action_witness.hpp), never this stack. */
CBMS_EXPORT int CBMS_DispatchOwnerAt(uint32_t selector,uintptr_t caller,void* receiver,uint32_t* kind,uintptr_t* carrier);
#ifdef CBMS_OFFLINE_HARNESS
CBMS_EXPORT void* CBMS_TestActionDefaultCarrier(uintptr_t,void*) CBMS_DISPATCH_THROWS;
CBMS_EXPORT int16_t CBMS_TestAddMessageCarrier(uintptr_t,void*,void*,int) CBMS_DISPATCH_THROWS;
#endif
#ifdef __cplusplus
}
#endif
#undef CBMS_DISPATCH_THROWS
