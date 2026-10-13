/* Uninstalled native callback ABI. It does not install engine detours. */
#pragma once
#include <stdint.h>
#ifdef _WIN32
#define CBMS_EXPORT __declspec(dllexport)
#else
#define CBMS_EXPORT __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif
typedef struct CBMS_Runtime CBMS_Runtime;
typedef struct CBMS_Stats {
    uint32_t count;
    uint32_t level[3];
    uint32_t active[3];
    /* 0 absent, 1 active, 2 unresolved; native CL>=1 is NOT capability. */
    uint32_t arcane_state, arcane_level, divine_state, divine_level;
} CBMS_Stats;
/* Return 1 only for a fully resolved snapshot of this original reader. */
typedef int (*CBMS_Resolve)(uintptr_t reader, uint64_t generation, uintptr_t spell_instance, uint32_t spell_type, CBMS_Stats* output, void* user);
typedef void (*CBMS_Report)(const char* error, void* user);
typedef struct CBMS_NativeFunctions {
    uint8_t (*lookup)(int32_t, void**);
    void (*active_inactive)(void*, uint8_t*, uint8_t*);
    uint8_t (*class_level)(void*, uint8_t, uint8_t);
    uint8_t (*maximum_level)(void*, uint8_t);
    int (*mage)(void*, void*);
    int (*priest)(void*, void*);
    short (*caster_type)(void*);
    short (*caster_level)(void*, void*, int);
} CBMS_NativeFunctions;
typedef struct CBMS_DecodeFunctions {
    uintptr_t native_unmarshal_entry, previous_eeex_unmarshal, native_decoder_entry;
} CBMS_DecodeFunctions;
/* Certifies the actual installed EEex jump chain and shipped override bodies.
 * Read-only: does not install a hook, initialize or invoke either module. */
CBMS_EXPORT int CBMS_BindDecodeModules(uintptr_t game, uintptr_t eeex, CBMS_DecodeFunctions*, char* diagnostic, uint32_t capacity);
CBMS_EXPORT int CBMS_BindMarshalModule(uintptr_t game, uintptr_t* entry, char* diagnostic, uint32_t capacity);
typedef struct CBMS_LifecycleFunctions { uintptr_t copy,effect_destroy,actor_destroy; } CBMS_LifecycleFunctions;
CBMS_EXPORT int CBMS_BindLifecycleModules(uintptr_t game,uintptr_t eeex,CBMS_LifecycleFunctions*,char* diagnostic,uint32_t capacity);
/* Sole supported co-owner: banking installs its actor destructor first. */
typedef struct CBMS_BankActorChain {
    uint32_t schema;
    uintptr_t entry,handler;
    unsigned char original[7],replacement[7];
} CBMS_BankActorChain;
typedef int (*CBMS_BankActorQuery)(uintptr_t expected_entry,CBMS_BankActorChain*,void* user);
CBMS_EXPORT int CBMS_BindLifecycleModulesChained(uintptr_t game,uintptr_t eeex,CBMS_LifecycleFunctions*,
    CBMS_BankActorQuery,void*,CBMS_BankActorChain*,char* diagnostic,uint32_t capacity);

/* Read-only Windows mapped-image certification. Returns 1 and fills functions
 * only on a reviewed ABI, otherwise 0 with an actionable diagnostic. Refusal
 * leaves functions unchanged: keep native behavior and do not enable hooks.
 * Does not load a module or install hooks. Module/code lifetime is host-owned.
 */
CBMS_EXPORT int CBMS_BindModule(uintptr_t module, CBMS_NativeFunctions* functions, char* diagnostic, uint32_t capacity);
CBMS_EXPORT int CBMS_BindCurrent(CBMS_NativeFunctions* functions, char* diagnostic, uint32_t capacity);

/* Kind: 0 actor, 1 effect, 2 FireSpell message, 3 action.
 * Selector: 0 EffectFire, 1 Fire, 2 FirePoint, 3 Force, 4 ForcePoint,
 *           5 Spell, 6 SpellPoint. Spell type: 0 arcane, 1 divine, 2 unresolved,
 *           3 resolved installed native-only helper (retain ancestry).
 * All callbacks belong to one engine thread. Errors return -1 and latch a
 * diagnostic; the host must not silently treat that as successful fallback.
 * Selector/child callbacks return 0 leave native level or 1 replacement in
 * output. A root177 may inherit ancestry but return0 before any level selection.
 * Other successful callbacks return 1. The native provider reads audited
 * engine fields and calls the supplied query functions; it does not write
 * engine fields. Other callbacks use engine addresses only as lifetime keys.
 * Item/spell text arguments are copied as at most eight readable bytes,
 * stopping earlier at NUL. An eight-byte engine CResRef needs no terminator.
 */
CBMS_EXPORT CBMS_Runtime* CBMS_Create(CBMS_Resolve resolve, CBMS_Report report, void* user);
/* Uses the implemented native reader provider. Function pointers must be
 * resolved against the reviewed x64 engine by the host; no address guessing. */
CBMS_EXPORT CBMS_Runtime* CBMS_CreateNative(const CBMS_NativeFunctions* functions, CBMS_Report report, void* user);
/* Refuses destruction while contexts remain; no silent loss of pending casts. */
CBMS_EXPORT int CBMS_Destroy(CBMS_Runtime* runtime);
CBMS_EXPORT const char* CBMS_LastError(CBMS_Runtime* runtime);
CBMS_EXPORT int CBMS_Construct(CBMS_Runtime*, uint32_t kind, uintptr_t object);
CBMS_EXPORT int CBMS_Destruct(CBMS_Runtime*, uint32_t kind, uintptr_t object);
/* Called with the actual EEex actor UUID after load/registration. Never an
 * engine object ID. Also resolves pending saved origins with this same UUID. */
CBMS_EXPORT int CBMS_ActorUUID(CBMS_Runtime*, uintptr_t reader, uint64_t uuid);
/* Observation at native load/save boundary. UUID0 means no identity is bound
 * yet (e.g. serializing a temporary copy); it never replaces a known UUID. */
CBMS_EXPORT int CBMS_ActorObserved(CBMS_Runtime*, uintptr_t actor, uint64_t uuid);
/* Query only. A generic CGameAIBase is not automatically a sprite. */
CBMS_EXPORT int CBMS_ActorIsObserved(CBMS_Runtime*,uintptr_t actor);
/* Nonmutating ownership query for concrete native dispatch boundaries. */
CBMS_EXPORT int CBMS_CarrierIsOwned(CBMS_Runtime*,uint32_t kind,uintptr_t object);
/* Native V1 effect-list save integration. Prepare runs before EEex exporter
 * callbacks; Validate runs after the native list writer returns. Decoder events
 * refer to actual raw record/returned effect pairs, not a later list scan. */
CBMS_EXPORT int CBMS_PrepareEffectExport(CBMS_Runtime*, uintptr_t actor, uintptr_t list, uint32_t version, uint32_t permanent_only, uint32_t skip_equipped);
CBMS_EXPORT const char* CBMS_EffectExportText(CBMS_Runtime*, uintptr_t actor);
CBMS_EXPORT int CBMS_ValidateEffectExport(CBMS_Runtime*, uintptr_t actor, const void* bytes, uint32_t size);
CBMS_EXPORT int CBMS_BeginEffectImport(CBMS_Runtime*, uintptr_t actor);
CBMS_EXPORT int CBMS_ObserveEffectDecoded(CBMS_Runtime*, uintptr_t actor, uintptr_t effect, const void* raw_record);
CBMS_EXPORT int CBMS_StageEffectImportText(CBMS_Runtime*, uintptr_t actor, const char* text, uint32_t length);
CBMS_EXPORT int CBMS_FinishEffectImport(CBMS_Runtime*, uintptr_t actor);
/* Rollback only after the host has cancelled that native save/load operation.
 * Import abort never clears already-restored ownership. Unknown/raw actor
 * envelope storage remains host-owned and must be retained separately. */
CBMS_EXPORT int CBMS_AbortEffectExport(CBMS_Runtime*, uintptr_t actor);
CBMS_EXPORT int CBMS_AbortEffectImport(CBMS_Runtime*, uintptr_t actor);
CBMS_EXPORT int CBMS_ItemBegin(CBMS_Runtime*, uintptr_t reader, const char* item, uint32_t ability, uint32_t policy, uint64_t* use);
CBMS_EXPORT int CBMS_ItemChild(CBMS_Runtime*, uint64_t use, uintptr_t effect, uint32_t index);
/* Actual completed CItem::GetAbilityEffect root; observes a newly decoded
 * effect if no earlier callback observed it. Never overwrites owned context. */
CBMS_EXPORT int CBMS_ItemRootObserved(CBMS_Runtime*,uint64_t use,uintptr_t effect,uint32_t index);
CBMS_EXPORT int CBMS_ItemEnd(CBMS_Runtime*, uint64_t use);
CBMS_EXPORT int CBMS_Copy(CBMS_Runtime*, uint32_t kind, uintptr_t source, uintptr_t destination);
/* Concrete CAIAction lifecycle edges: completed native copy/assignment and
 * destructor entry. Existing unowned actions may be observed on first use;
 * a copied construction must not silently replace a registered lifetime. */
CBMS_EXPORT int CBMS_ActionCopied(CBMS_Runtime*, uintptr_t source, uintptr_t destination, uint32_t construction);
CBMS_EXPORT int CBMS_ActionBeforeDestroy(CBMS_Runtime*, uintptr_t action);
CBMS_EXPORT int CBMS_EffectCopied(CBMS_Runtime*,uintptr_t source,uintptr_t destination);
CBMS_EXPORT int CBMS_DestructObserved(CBMS_Runtime*,uint32_t kind,uintptr_t object);
CBMS_EXPORT int CBMS_Dispatch(CBMS_Runtime*, uintptr_t effect, uint32_t opcode, uint32_t mode, uint32_t special, uint32_t carrier_kind, uintptr_t carrier);
CBMS_EXPORT int CBMS_BeginCast(CBMS_Runtime*, uint32_t carrier_kind, uintptr_t carrier, uint32_t selector, uintptr_t spell_instance, const char* spell, uint32_t type, int native_source, int native_target, int x, int y, uint64_t* frame);
/* Typed cast-entry host: snapshot ownership before native callbacks may replace
 * the reusable current action. A capture owns no native actor and has no CSpell
 * until the actual preselection CALL. Capture/Continue return1 owned,0 unowned,
 * -1 error; both successful outcomes produce a token. Release every token. */
CBMS_EXPORT int CBMS_CaptureCastOwner(CBMS_Runtime*,uint32_t kind,uintptr_t carrier,uint32_t selector,uint64_t* capture);
CBMS_EXPORT int CBMS_ContinueCastOwner(CBMS_Runtime*,uint64_t parent,uint32_t selector,uint64_t* capture);
CBMS_EXPORT int CBMS_BeginCapturedCast(CBMS_Runtime*,uint64_t capture,uintptr_t spell_instance,const char* spell,uint32_t type,uint64_t* frame);
CBMS_EXPORT int CBMS_ReleaseCastOwner(CBMS_Runtime*,uint64_t capture);
CBMS_EXPORT int CBMS_SpellChildObserved(CBMS_Runtime*,uint64_t frame,uintptr_t spell_instance,uintptr_t child,uint32_t* level);
CBMS_EXPORT int CBMS_Select(CBMS_Runtime*, uint64_t frame, uint32_t selector, uintptr_t spell_instance, uint32_t* level);
CBMS_EXPORT int CBMS_SpellChild(CBMS_Runtime*, uint64_t frame, uintptr_t spell_instance, uintptr_t child, uint32_t* level);
CBMS_EXPORT int CBMS_Linked177(CBMS_Runtime*, uintptr_t parent, uintptr_t child, uint32_t* level);
CBMS_EXPORT int CBMS_Linked177Observed(CBMS_Runtime*,uintptr_t parent,uintptr_t child,uint32_t* level);
CBMS_EXPORT int CBMS_EndCast(CBMS_Runtime*, uint64_t frame);
/* Local lifetime check only; does NOT prove safe uninstall/save persistence. */
CBMS_EXPORT int CBMS_Quiescent(CBMS_Runtime*);
#ifdef __cplusplus
}
#endif
