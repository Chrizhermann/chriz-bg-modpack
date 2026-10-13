// Concrete native screen scope. No old-class reward writes or fabricated engine
// capabilities; calls actual audited originals and the implemented Lua journal.
#pragma once
#include "dual_hp_observer.h"
#include "dual_choice_observer.h"
#include "identity_native.h"
#ifdef _WIN32
#define CBMDS_API extern "C" __declspec(dllexport)
#else
#define CBMDS_API extern "C"
#endif
enum CBMDS_Phase:uint32_t {CBMDS_PREPARING=1,CBMDS_PREVIEW,CBMDS_COMMITTING,CBMDS_CANCELING,CBMDS_UNCERTAIN};
// Begin alone is a protected Lua Number callback; invalid/error results reject.
enum CBMDS_BeginResult:int64_t {CBMDS_BEGIN_OWNED=1,CBMDS_BEGIN_PASSTHROUGH=2};
struct CBMDS_Config {
 uint32_t abi;
 uintptr_t reset,commit,cancel,identity_query,identity_can_mutate;
 uintptr_t begin_lua,prepare_commit_lua,complete_lua,cancel_lua,uncertain_lua;
};
struct CBMDS_View {
 uint64_t session,incarnation;
 uintptr_t screen,sprite;
 uint32_t phase,hp_status,hp_cached,choice_count;
 char owner[33];
};
CBMDS_API int CBMDS_Configure(const CBMDS_Config*);
CBMDS_API int CBMDS_IsEngineThread();
CBMDS_API void CBMDS_Reset(void* screen,void* sprite);
CBMDS_API void CBMDS_Commit(void* screen,void* sprite);
CBMDS_API void CBMDS_Cancel(void* screen);
CBMDS_API int CBMDS_Query(const void* sprite,CBMDS_View*);
CBMDS_API int CBMDS_BindOwner(const void* sprite,const char* saved_owner);
CBMDS_API int CBMDS_GetHP(const void* sprite,CBMDH_Batch*);
CBMDS_API int CBMDS_GetChoice(const void* sprite,uint32_t index,CBMDC_Event*);
CBMDS_API int CBMDS_OnHP(const CBMDH_Batch*);
CBMDS_API int CBMDS_OnChoice(const CBMDC_Event*);
