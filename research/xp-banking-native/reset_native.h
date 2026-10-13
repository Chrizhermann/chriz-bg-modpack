// Uninstalled MakeDualClass bridge; paired with concrete reset_hooks.lua loader.
#pragma once
#include "identity_native.h"
enum CBMR_Stage : unsigned { CBMR_PREPARING=1, CBMR_NATIVE, CBMR_COMPLETING, CBMR_UNCERTAIN };
struct CBMR_Config {
    uint64_t abi;
    uintptr_t original, prepare, complete, uncertain;
    uintptr_t get_xp_cap, chitin_global;
    uintptr_t lua_tolstring, lua_pushstring;
    uintptr_t original_create, original_remove, original_start, get_deny, capture_preview;
};
struct CBMR_View { uint64_t incarnation; uint32_t pre_base; unsigned new_class; CBMR_Stage stage; unsigned path; };
struct CBMR_PreviewView { uint64_t incarnation; uint32_t pre_base; };
CBMI_API int CBMR_Configure(const CBMR_Config*);
CBMI_API void CBMR_MakeDualClass(void* screen, void* sprite, unsigned char new_class);
CBMI_API void CBMR_CreateMakeDualClass(void* screen, void* sprite, unsigned char new_class);
CBMI_API void CBMR_RemoveAbilities(void* screen, void* sprite, unsigned new_class, int remove);
CBMI_API void CBMR_StartEditing(void* screen, int actor_id, int mode);
CBMI_API int CBMR_PreviewQuery(const void* sprite, CBMR_PreviewView* out);
CBMI_API int CBMR_LuaPreviewQuery(void* L);
CBMI_API int CBMR_Query(const void* sprite, CBMR_View* out);
CBMI_API int CBMR_NativeCap(const void* sprite, uint32_t* out);
CBMI_API int CBMR_LuaQuery(void* L);
CBMI_API int CBMR_LuaNativeCap(void* L);
