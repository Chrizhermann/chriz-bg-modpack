#pragma once
#include "native_api.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Audited Windows x64 signature: RCX=list, RDX=output**, R8B=version,
 * R9D=permanentOnly, fifth stack argument=skipEquipped. */
typedef uint32_t (*CBMS_NativeMarshalTrampoline)(void*,void**,uint8_t,int,int);
CBMS_EXPORT int CBMS_ConfigureMarshalCarrier(CBMS_NativeMarshalTrampoline original);
CBMS_EXPORT int CBMS_DetachMarshalCarrier(void);
CBMS_EXPORT int CBMS_MarshalCarrierIdle(void);
/* Called only by the existing EEex actor exporter. No sprite is guessed from
 * a list address. 0 means no native marshal scope, -1 means a mismatched scope. */
CBMS_EXPORT int CBMS_ClaimMarshalActor(void* actor);
#ifdef __cplusplus
CBMS_EXPORT uint32_t CBMS_MarshalCarrier(void*,void**,uint8_t,int,int) noexcept(false);
#else
CBMS_EXPORT uint32_t CBMS_MarshalCarrier(void*,void**,uint8_t,int,int);
#endif
#ifdef __cplusplus
}
#endif
