#pragma once
#include "native_api.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef void (*CBMS_EffectCopyOriginal)(void*,void*);
typedef void (*CBMS_DestroyOriginal)(void*);
CBMS_EXPORT int CBMS_ConfigureLifecycleCarriers(CBMS_EffectCopyOriginal,CBMS_DestroyOriginal,CBMS_DestroyOriginal);
CBMS_EXPORT int CBMS_LifecycleCarriersIdle(void);
CBMS_EXPORT int CBMS_DetachLifecycleCarriers(void);
#ifdef __cplusplus
CBMS_EXPORT void CBMS_EffectCopyCarrier(void*,void*) noexcept(false);
CBMS_EXPORT void CBMS_EffectDestroyCarrier(void*) noexcept(false);
CBMS_EXPORT void CBMS_ActorDestroyCarrier(void*) noexcept(false);
#else
CBMS_EXPORT void CBMS_EffectCopyCarrier(void*,void*);
CBMS_EXPORT void CBMS_EffectDestroyCarrier(void*);
CBMS_EXPORT void CBMS_ActorDestroyCarrier(void*);
#endif
#ifdef __cplusplus
}
#endif
