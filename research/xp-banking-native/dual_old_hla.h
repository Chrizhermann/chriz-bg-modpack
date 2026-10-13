// Research-only native old-class HLA provider. No registration on load.
#pragma once
#include <cstdint>
#include <cstddef>
#ifdef _WIN32
#define CBMDHLA_API extern "C" __declspec(dllexport)
#else
#define CBMDHLA_API extern "C"
#endif
struct CBMDHLA_Config {
    uint64_t abi;
    uintptr_t rules,is_engine_thread,num_abilities,set_level,class_string,get_at,scan,cstring_destroy;
    uintptr_t first_level,rate,change_level,new_rate;
    uintptr_t get_abilities,complete_abilities;
    uintptr_t ability_construct,cstring_construct_chars,cstring_assign_chars,resref_construct_cstring;
    uintptr_t check_enabled,get_ai_type;
};
struct CBMDHLA_View {
    uint64_t handle;
    uint32_t points,native_capped_points,row_count;
    uint8_t eligibility_flags;
};
// Strings are borrowed until Close. The Lua adapter must detach all fields.
// Snapshot-local row index is not a durable selection identity.
struct CBMDHLA_Row {
    char icon[9];
    uint32_t name_strref;
    int32_t min_level,max_level,max_rank;
    const char* effect;
    const char* prerequisite;
    const char* excluded_by;
    const char* alignment;
};
CBMDHLA_API int CBMDHLA_Configure(const CBMDHLA_Config*);
// Read-only, before native Reset. Uses real actor AI metadata only as borrowed
// input to a detached old-class/old-kit sprite view; never changes real class.
CBMDHLA_API int CBMDHLA_Open(const void* actor,uint8_t old_class,uint32_t old_kit,
    uint8_t before_level,uint8_t after_level,CBMDHLA_View*);
CBMDHLA_API int CBMDHLA_ReadRow(uint64_t handle,uint32_t index,CBMDHLA_Row*);
// Returns1 allowed,0 native constraints, -1 invalid/incomplete query. Selected
// rows are this open catalog's ordered IDs. Previously earned dormant receipts
// are marker-equivalent context, never fired by this read-only query.
CBMDHLA_API int CBMDHLA_CanChoose(uint64_t handle,const void* actor,uint32_t row,
    const uint32_t* selected,uint32_t selected_count,
    const CBMDHLA_Row* deferred,uint32_t deferred_count);
CBMDHLA_API int CBMDHLA_Close(uint64_t handle);
CBMDHLA_API int CBMDHLA_LastStatus();
struct CBMDHLA_LuaConfig {uint64_t abi;uintptr_t to_string,push_string;};
CBMDHLA_API int CBMDHLA_ConfigureLua(const CBMDHLA_LuaConfig*);
CBMDHLA_API int CBMDHLA_LuaOpen(void*);
CBMDHLA_API int CBMDHLA_LuaRow(void*);
CBMDHLA_API int CBMDHLA_LuaChoose(void*);
CBMDHLA_API int CBMDHLA_LuaClose(void*);
struct CBMDHLA_DeliveryConfig {
 uint64_t abi;
 uintptr_t session_query,is_engine_thread,is_dormant,allocate,array_construct,array_grow,
  list_vtable,ability_construct,cstring_assign_chars,cstring_destroy,release,complete_abilities;
};
struct CBMDHLA_DeliveryResult {uint32_t completed,uncertain;};
CBMDHLA_API int CBMDHLA_ConfigureDelivery(const CBMDHLA_DeliveryConfig*);
// Only actual COMMITTING, exact owner and native old-class usability. Caller
// first persists the complete pending delivery receipt. 1=complete,0=no actor
// mutation,-1=uncertain. Never replay a started transaction automatically.
CBMDHLA_API int CBMDHLA_Deliver(void* actor,uint8_t old_class,const char* owner,
 const CBMDHLA_Row*,uint32_t count,CBMDHLA_DeliveryResult*);
CBMDHLA_API int CBMDHLA_LuaDeliver(void*);
struct CBMDHLA_ProjectionConfig {uint64_t abi;uintptr_t session_query;};
CBMDHLA_API int CBMDHLA_ConfigureProjection(const CBMDHLA_ProjectionConfig*);
CBMDHLA_API int CBMDHLA_PrepareManual(void* actor,const char* owner,const CBMDHLA_Row*,uint32_t count,uint64_t* token);
CBMDHLA_API int CBMDHLA_ClearManual(uint64_t token);
CBMDHLA_API int CBMDHLA_CheckAbilityEnabled(void* screen,void* actor,void* candidate);
CBMDHLA_API int CBMDHLA_LuaPrepareManual(void*);
CBMDHLA_API int CBMDHLA_LuaClearManual(void*);
