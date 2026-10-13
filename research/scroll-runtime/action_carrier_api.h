#pragma once
#include "native_api.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Profile index and exact three addresses, in copy/assignment/destruction order.
 * Only the mapped-image binder supplies this in a real host. */
typedef struct CBMS_ActionFunctions {uint32_t profile; uintptr_t sites[3];} CBMS_ActionFunctions;
CBMS_EXPORT int CBMS_BindActionModule(uintptr_t,CBMS_ActionFunctions*,char*,uint32_t);
CBMS_EXPORT int CBMS_ConfigureActionCarriers(CBMS_Runtime*);
CBMS_EXPORT int CBMS_ActionCarriersIdle(void);
CBMS_EXPORT int CBMS_DetachActionCarriers(void);
CBMS_EXPORT const char* CBMS_ActionCarrierError(void);
/* Proven bridge argument order. These callbacks change only runtime metadata.
 * A failure is reported/latches diagnostics; native register state is restored.
 * The host must report a diagnostic, never call a failure successful fallback. */
CBMS_EXPORT int CBMS_ActionCopiedCarrier(CBMS_Runtime*,uintptr_t,uintptr_t,uint32_t);
CBMS_EXPORT int CBMS_ActionDestroyCarrier(CBMS_Runtime*,uintptr_t);
#ifdef __cplusplus
}
#endif
