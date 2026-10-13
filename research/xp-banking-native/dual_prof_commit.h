// Inert research-only owned proficiency primitive. No registration on load.
#pragma once
#include <cstdint>
#include <cstddef>
#ifdef _WIN32
#define CBMDPC_API extern "C" __declspec(dllexport)
#else
#define CBMDPC_API extern "C"
#endif
struct CBMDPC_Config {
    uint64_t abi;
    uintptr_t original_apply;
    uintptr_t session_query,is_engine_thread,base_construct,decode_base,add_tail,remove_at;
};
// A record plan stores the entire serialized base before/after, excluding the
// native vtable and transient CGameEffect tail. Offsets are pinned Win64 ABI.
struct CBMDPC_RecordPlan {
    uintptr_t effect;
    unsigned char before[0x108],after[0x108];
};
struct CBMDPC_Choice {uint32_t stat,delta;};
struct CBMDPC_PreviewRecord {CBMDPC_RecordPlan record;uintptr_t node;uint32_t created,carrier,start_active;};
CBMDPC_API int CBMDPC_Configure(const CBMDPC_Config*);
CBMDPC_API int CBMDPC_ApplyEffect(void* effect,void* sprite);
// Recognizes only the inert, schema1 private carrier. Provenance copies with
// the effect; it is not a current-bank-owner gate on earned allocations.
CBMDPC_API int CBMDPC_ReadCarrier(const void* effect,uint32_t* stat,uint32_t* pips);
CBMDPC_API int CBMDPC_ReadOldAllocation(const void* actor,uint32_t stat,uint32_t* value,uint32_t* pending);
CBMDPC_API int CBMDPC_ReadActiveAllocation(const void* actor,uint32_t stat,uint32_t* value);
// Only a live PREVIEW transaction. Requested is a class-basis
// final value, not aggregate pips. Caller owns budget/cap and native refresh.
CBMDPC_API int CBMDPC_SetActiveOwned(void* actor,uint64_t session,uint64_t incarnation,
    const char* owner,uint32_t stat,uint32_t requested);
// Fills a detached native CGameEffectBase after its real default constructor.
// The caller owns allocation/lifecycle and must use DecodeEffectFromBase.
CBMDPC_API int CBMDPC_MakeCarrierBase(void* base,uint32_t stat,uint32_t pips,const char* provenance);
// Plans only; DOES NOT write the supplied effect. delta is a chosen increment.
// Saturation of an obscured earlier SET at the native three-bit limit is
// explicit in return2. Caller must validate the effective owned choice/cap.
CBMDPC_API int CBMDPC_PlanSet(const void* effect,uint32_t stat,uint32_t delta,CBMDPC_RecordPlan*);
// Concrete engine-list mutation, ONLY inside the actual CBMDS PREPARING scope.
// Caller owns choice-budget validation and persistent pending-preview journal.
// Results: 1=success,0=no actor mutation,-1=uncertain native mutation. On -1,
// retain transaction and journal; no automatic replay/rollback is authorized.
// Every native class SET is merged from its own class bits; no aggregate stat
// is read. Inert carriers contribute once and survive until Complete.
CBMDPC_API int CBMDPC_ApplyPreview(void* actor,uint64_t session,uint64_t incarnation,
    const char* owner,const CBMDPC_Choice* rows,uint32_t count,uint64_t* transaction);
// For active levels that do not reactivate the retired class: begin AFTER
// native Reset has skipped CombineAll, while still PREPARING. No actor write,
// old-bit merge or carrier consumption occurs. Returns1/0. After Complete,
// caller persists newly earned retired rows with PersistDormant separately.
CBMDPC_API int CBMDPC_BeginActivePreview(void* actor,uint64_t session,uint64_t incarnation,
    const char* owner,uint64_t* transaction);
CBMDPC_API int CBMDPC_GetRecordPlan(uint64_t transaction,uint32_t index,CBMDPC_PreviewRecord*);
// Restore after normal native Cancel. Restore owns the six class-allocation
// bits changed by reactivation; current unrelated fields/effects stay intact.
CBMDPC_API int CBMDPC_Restore(void* actor,uint64_t session,uint64_t incarnation,uint64_t transaction);
CBMDPC_API int CBMDPC_Complete(void* actor,uint64_t session,uint64_t incarnation,uint64_t transaction);
// Old-only accepted rows remain native no-op carriers; no class SET is changed.
// Same1/0/-1 results and recovery handle. Complete acknowledges this receipt
// without deleting its earned carriers. Caller verifies old-only projection.
CBMDPC_API int CBMDPC_PersistDormant(void* actor,uint64_t session,uint64_t incarnation,
    const char* owner,const CBMDPC_Choice* rows,uint32_t count,uint64_t* transaction);
CBMDPC_API int CBMDPC_LastStatus();
