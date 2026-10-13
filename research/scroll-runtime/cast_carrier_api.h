#pragma once
#include "native_api.h"
typedef int (*CBMS_AdditionalCastOwner)(uint32_t,uintptr_t,void*,uintptr_t*);
#ifdef __cplusplus
#define CBMS_CAST_THROWS noexcept(false)
extern "C" {
void CBMS_SetAdditionalCastOwner(CBMS_AdditionalCastOwner);
#else
#define CBMS_CAST_THROWS
#endif
/* Actual x64 ABI: EffectFire has no return; AI Fire/Point and action methods
 * return a native short. The six/eight stack arguments are forwarded intact. */
typedef void (*CBMS_EffectFireOriginal)(void*,void*,void*,int,int,int);
typedef int16_t (*CBMS_FireOriginal)(void*,void*,void*,int,int,void*,int,int);
typedef int16_t (*CBMS_CastTargetOriginal)(void*,void*);
typedef int16_t (*CBMS_CastPointOriginal)(void*);
typedef void* (*CBMS_SpellEffectOriginal)(void*,int,int,void*);
typedef struct CBMS_CastFunctions {
    CBMS_EffectFireOriginal effect_fire;
    CBMS_FireOriginal fire,fire_point;
    CBMS_CastTargetOriginal force;
    CBMS_CastPointOriginal force_point;
    CBMS_CastTargetOriginal spell;
    CBMS_CastPointOriginal spell_point;
    CBMS_SpellEffectOriginal child;
    short (*caster_type)(void*);
    uintptr_t count_getter,selection_calls[7],child_returns[7],extra_returns[2];
} CBMS_CastFunctions;
CBMS_EXPORT int CBMS_ConfigureCastCarriers(CBMS_Runtime*,const CBMS_CastFunctions*);
CBMS_EXPORT int CBMS_CastCarriersIdle(void);
CBMS_EXPORT int CBMS_DetachCastCarriers(void);
CBMS_EXPORT const char* CBMS_CastCarrierError(void);
CBMS_EXPORT void CBMS_EffectFireCarrier(void*,void*,void*,int,int,int) CBMS_CAST_THROWS;
CBMS_EXPORT int16_t CBMS_FireCarrier(void*,void*,void*,int,int,void*,int,int) CBMS_CAST_THROWS;
CBMS_EXPORT int16_t CBMS_FirePointCarrier(void*,void*,void*,int,int,void*,int,int) CBMS_CAST_THROWS;
CBMS_EXPORT int16_t CBMS_ForceCarrier(void*,void*) CBMS_CAST_THROWS;
CBMS_EXPORT int16_t CBMS_ForcePointCarrier(void*) CBMS_CAST_THROWS;
CBMS_EXPORT int16_t CBMS_SpellCarrier(void*,void*) CBMS_CAST_THROWS;
CBMS_EXPORT int16_t CBMS_SpellPointCarrier(void*) CBMS_CAST_THROWS;
CBMS_EXPORT void* CBMS_SpellEffectCarrier(void*,int,int,void*) CBMS_CAST_THROWS;
/* Called only by the emitted GetAbilityCount call bridge. Snapshot layout is
 * flags,r15,r14,r13,r12,r11,r10,r9,r8,rdi,rsi,rbp,rbx,rdx,rcx,rax,returnPC.
 * Native pre-CALL RSP is immediately after that final returnPC. */
CBMS_EXPORT void CBMS_SelectCapturedNative(uint32_t selector,uint64_t* snapshot);
#ifdef CBMS_OFFLINE_HARNESS
CBMS_EXPORT void CBMS_TestEffectFireCarrier(uintptr_t,void*,void*,void*,int,int,int) CBMS_CAST_THROWS;
CBMS_EXPORT int16_t CBMS_TestFireCarrier(uint32_t,uintptr_t,void*,void*,void*,int,int,void*,int,int) CBMS_CAST_THROWS;
CBMS_EXPORT void* CBMS_TestSpellEffectCarrier(uintptr_t,void*,int,int,void*) CBMS_CAST_THROWS;
#endif
#ifdef __cplusplus
}
#endif
#undef CBMS_CAST_THROWS
