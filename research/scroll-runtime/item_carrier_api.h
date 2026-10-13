#pragma once
#include "native_api.h"
#ifdef __cplusplus
#define CBMS_ITEM_MAY_THROW noexcept(false)
extern "C" {
#else
#define CBMS_ITEM_MAY_THROW
#endif
typedef uint16_t (*CBMS_UseItemOriginal)(void*,void*);
typedef uint16_t (*CBMS_UsePointOriginal)(void*);
typedef uint16_t (*CBMS_FireItemOriginal)(void*,void*,int,void*);
typedef void* (*CBMS_ItemEffectOriginal)(void*,int,int,void*);
typedef uint16_t (*CBMS_ItemTypeOriginal)(void*);
typedef int (*CBMS_PolicyDigest)(const char* name,const char* extension,unsigned char digest[32],void* user);
typedef struct CBMS_ItemFunctions {
    CBMS_UseItemOriginal use;
    CBMS_UsePointOriginal use_point;
    CBMS_FireItemOriginal fire,fire_point;
    CBMS_ItemEffectOriginal effect;
    CBMS_ItemTypeOriginal item_type;
    /* Actual native return PCs, relocated with the audited loaded module. */
    uintptr_t root_returns[4],continuation_returns[2];
} CBMS_ItemFunctions;
/* Certify the five bodies, item-type query and their six exact call edges.
 * Read only. Returned entries are originals, not initialized trampolines. */
CBMS_EXPORT int CBMS_BindItemModule(uintptr_t module,CBMS_ItemFunctions*,char* diagnostic,uint32_t capacity);
/* Originals must be the installed host's trampolines, after certification.
 * The policy is copied and verified against the effective resource reader.
 * No engine hook or native object is changed by this configuration. */
CBMS_EXPORT int CBMS_ConfigureItemCarriers(CBMS_Runtime*,const CBMS_ItemFunctions*,const void* policy,uint32_t size,CBMS_PolicyDigest,void* user);
CBMS_EXPORT int CBMS_ItemCarriersIdle(void);
CBMS_EXPORT int CBMS_DetachItemCarriers(void);
CBMS_EXPORT const char* CBMS_ItemCarrierError(void);
/* Host health gate for NEW root ownership; existing carriers keep cleanup. */
void CBMS_ItemAdmission(int (*allowed)(void));
/* Native C++ exceptions must unwind our scopes under MSVC /EHsc; an extern-C
 * declaration without explicit noexcept(false) is assumed not to throw. */
CBMS_EXPORT uint16_t CBMS_UseItemCarrier(void*,void*) CBMS_ITEM_MAY_THROW;
CBMS_EXPORT uint16_t CBMS_UsePointCarrier(void*) CBMS_ITEM_MAY_THROW;
CBMS_EXPORT uint16_t CBMS_FireItemCarrier(void*,void*,int,void*) CBMS_ITEM_MAY_THROW;
CBMS_EXPORT uint16_t CBMS_FireItemPointCarrier(void*,void*,int,void*) CBMS_ITEM_MAY_THROW;
CBMS_EXPORT void* CBMS_ItemEffectCarrier(void*,int,int,void*) CBMS_ITEM_MAY_THROW;
#ifdef CBMS_OFFLINE_HARNESS
/* The ordinary exports capture the real native return PC intrinsically.
 * These explicit-PC entrances exist only in the compiled offline harness. */
CBMS_EXPORT uint16_t CBMS_TestFireItemCarrier(uintptr_t,int,void*,void*,int,void*) CBMS_ITEM_MAY_THROW;
CBMS_EXPORT void* CBMS_TestItemEffectCarrier(uintptr_t,void*,int,int,void*) CBMS_ITEM_MAY_THROW;
#endif
#ifdef __cplusplus
}
#endif
#undef CBMS_ITEM_MAY_THROW
