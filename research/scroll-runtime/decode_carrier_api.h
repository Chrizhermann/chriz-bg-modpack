#pragma once
#include "native_api.h"
#ifdef __cplusplus
#define CBMS_NATIVE_MAY_THROW noexcept(false)
extern "C" {
#else
#define CBMS_NATIVE_MAY_THROW
#endif
typedef void (*CBMS_PreviousUnmarshal)(void* list, unsigned char* data, unsigned size, void* actor, unsigned char version);
typedef void* (*CBMS_NativeDecoderTrampoline)(const void* raw);
/* Setup only after BindDecodeModules and trampoline/unwind certification.
 * Installs no hooks. Detach only after restoring entry bytes and quiescence. */
CBMS_EXPORT int CBMS_ConfigureDecodeCarrier(CBMS_PreviousUnmarshal, CBMS_NativeDecoderTrampoline);
CBMS_EXPORT int CBMS_DetachDecodeCarrier(void);
CBMS_EXPORT int CBMS_DecodeCarrierIdle(void);
/* Native C++ routines can throw. These wrappers preserve ordinary C++ unwind
 * rather than pretending a native allocation failure completed the load. */
CBMS_EXPORT void CBMS_UnmarshalCarrier(void*, unsigned char*, unsigned, void*, unsigned char) CBMS_NATIVE_MAY_THROW;
CBMS_EXPORT void* CBMS_DecodeCarrier(const void*) CBMS_NATIVE_MAY_THROW;
#ifdef __cplusplus
}
#endif
#undef CBMS_NATIVE_MAY_THROW
