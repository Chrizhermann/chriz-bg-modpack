#pragma once
#include "native_api.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Independent decoder subsystem, not full scroll activation. Call only during
 * loader initialization before game execution, with module lifetime retained.
 * Native entry writes are never invoked by offline tests on a game image. */
CBMS_EXPORT int CBMS_InstallDecodeHooks(uintptr_t game, uintptr_t eeex);
/* Adds the actual native Marshal wrapper in the same rollback transaction. */
CBMS_EXPORT int CBMS_InstallPersistenceHooks(uintptr_t game, uintptr_t eeex);
/* Also chains the three certified existing EEex live effect/actor callbacks.
 * This still is not full item/cast/message carrier activation. */
CBMS_EXPORT int CBMS_InstallEffectPersistenceHooks(uintptr_t game,uintptr_t eeex);
CBMS_EXPORT int CBMS_InstallEffectPersistenceHooksChained(uintptr_t game,uintptr_t eeex,CBMS_BankActorQuery,void*);
/* All participating engine threads must be quiescent. Refuses changed bytes or
 * active carrier callbacks; it never overwrites a later mod's detour. */
CBMS_EXPORT int CBMS_RemoveDecodeHooks(void);
CBMS_EXPORT const char* CBMS_DecodeHookError(void);
#ifdef CBMS_OFFLINE_HARNESS
/* Private allocated instruction fixtures only; no game/EEex module invocation. */
CBMS_EXPORT int CBMS_TestInstallDecodeHooks(uintptr_t unmarshal, uintptr_t decoder, uintptr_t previous);
CBMS_EXPORT uintptr_t CBMS_TestDecodeAllocation(void);
CBMS_EXPORT void CBMS_TestDecodeFailure(int point);
CBMS_EXPORT int CBMS_TestInstallPersistenceHooks(uintptr_t unmarshal,uintptr_t decoder,uintptr_t previous,uintptr_t marshal);
CBMS_EXPORT int CBMS_TestInstallEffectPersistenceHooks(uintptr_t unmarshal,uintptr_t decoder,uintptr_t previous,uintptr_t marshal,uintptr_t copy,uintptr_t effect_destroy,uintptr_t actor_destroy);
CBMS_EXPORT int CBMS_TestInstallEffectPersistenceHooksChained(uintptr_t unmarshal,uintptr_t decoder,uintptr_t previous,uintptr_t marshal,uintptr_t copy,uintptr_t effect_destroy,uintptr_t actor_destroy,const CBMS_BankActorChain*);
#endif
#ifdef __cplusplus
}
#endif
