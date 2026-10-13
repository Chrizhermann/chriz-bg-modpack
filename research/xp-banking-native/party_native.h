// Native tail target for one reviewed AddCharacterToParty GetNameRef callsite.
#pragma once
#include "identity_native.h"
struct CBMP_Config { uint64_t abi; uintptr_t original_get_name_ref, protected_callback; };
CBMI_API int CBMP_Configure(const CBMP_Config*);
CBMI_API uint32_t CBMP_OnPartyReady(void* sprite);
CBMI_API int CBMP_LastStatus();
