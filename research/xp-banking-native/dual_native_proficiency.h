#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef _WIN32
#define CBMDP_API extern "C" __declspec(dllexport)
#else
#define CBMDP_API extern "C"
#endif

/* Uninstalled native reward binding; NOT the complete old-class adapter.
 * Call Bind initially at a verified engine-main-thread boundary. Pointers must
 * be valid native objects / detached stats snapshots throughout each call.
 * No actor, XP, level, proficiency, or table field is written. The native helper
 * allocates temporary CString objects using the engine's allocator.
 * A bound CAIObjectType must identify the actual actor: native class selection
 * reads that actor's dual flags through its object ID. No class flag swapping.
 */
enum CBMDP_Status { CBMDP_OK, CBMDP_INVALID, CBMDP_UNSUPPORTED_IMAGE,
    CBMDP_WRONG_THREAD, CBMDP_NOT_EXPECTED_DUAL, CBMDP_INVALID_PROFS,
    CBMDP_INVALID_PROJECTION, CBMDP_NATIVE_MISMATCH };
struct CBMDP_Binding;
struct CBMDP_Result {
    uint32_t picks, first_level, rate;
    uint8_t active_class, old_class, old_before, old_after;
};
struct CBMDP_ChoiceCap {
    int32_t weapon_kit_limit, level_limit;
    uint32_t effective_limit;
};
struct CBMDP_SkillBudget { uint32_t per_level, levels_gained, points; };
struct CBMDP_OldTarget { uint32_t usable_xp; uint8_t before, target, active_class, old_class; };
// Actual installed XPLEVEL progression, queried as the retired single class in a
// private scalar projection. Never changes the actor's class flags or XP. The
// native byte-level loop is preflighted through its first terminal cell so a
// malformed/nonterminating table cannot wrap forever inside the engine.
CBMDP_API int CBMDP_GetOldTarget(CBMDP_Binding*,void* rules,const void* actor_type,
 const void* before_stats,uint8_t expected_active,uint8_t expected_old,
 uint32_t old_usable_xp,CBMDP_OldTarget*);
struct CBMDP_OldPlan {CBMDP_OldTarget levels;uint32_t prof_points,skill_points;};
CBMDP_API int CBMDP_GetOldPlan(CBMDP_Binding*,void*,const void*,const void*,uint8_t,uint8_t,
 uint32_t old_usable_xp,uint32_t old_kit,CBMDP_OldPlan*);
CBMDP_API int CBMDP_GetOldCap(CBMDP_Binding*,void*,const void*,const void*,uint8_t,uint8_t,
 uint32_t old_usable_xp,uint32_t old_kit,uint32_t stat,CBMDP_ChoiceCap*);
struct CBMDP_HPSample { uint32_t level; int32_t contribution; };
struct CBMDP_HPRolls {
    uint32_t count;
    int32_t total, native_con_bonus, native_minimum_roll;
    CBMDP_HPSample samples[255];
};
CBMDP_API int CBMDP_Bind(const void *loaded_image, size_t image_size,
                       CBMDP_Binding **output);
CBMDP_API int CBMDP_Destroy(CBMDP_Binding *binding);
CBMDP_API int CBMDP_IsEngineThread();
CBMDP_API int CBMDP_GetSlots(CBMDP_Binding *binding, void *rules,
    const void *actor_type, const void *before_stats, const void *after_stats,
    uint8_t expected_active, uint8_t expected_old, CBMDP_Result *output);
/* Read the old class/kit's OWN limits, not the native merged active/old cap.
 * old_kit must come from the captured old-class identity. Calling the native
 * pure rules helper with explicit selected-class arguments changes no actor.
 * This neither makes a choice nor writes pips; later UI must retain that choice.
 */
CBMDP_API int CBMDP_GetChoiceCap(CBMDP_Binding *binding, void *rules,
    const void *actor_type, const void *projected_stats, uint8_t expected_active,
    uint8_t expected_old, uint32_t old_kit, uint32_t proficiency_stat,
    CBMDP_ChoiceCap *output);
CBMDP_API int CBMDP_GetSkillBudget(CBMDP_Binding *binding, void *rules,
    const void *actor_type, const void *before_stats, const void *after_stats,
    uint8_t expected_active, uint8_t expected_old, uint32_t old_kit,
    CBMDP_SkillBudget *output);
/* Stateful native RNG query: call once per owned manual preview and cache it.
 * Uses the retired class's captured kit and installed HPCLASS/HP tables, native
 * maximum-HP option and native rolling/minimum rules. Detached projections only;
 * never changes world class, levels, HP or XP. Returns BASE roll contributions;
 * CON-derived HP remains the native engine's responsibility, not an extra grant.
 * On native failure propagate it: RNG may already be consumed, never retry as
 * though nothing happened. This function is not a complete reward transaction.
 */
CBMDP_API int CBMDP_RollOldHP(CBMDP_Binding *binding, void *rules,
    const void *actor_type, const void *before_stats, const void *after_stats,
    uint8_t expected_active, uint8_t expected_old, uint32_t old_kit,
    uint8_t constitution, CBMDP_HPRolls *output);
CBMDP_API int CBMDP_RollOldPlan(CBMDP_Binding*,void* rules,const void* type,const void* before,
 uint8_t active,uint8_t old,uint32_t xp,uint32_t kit,uint8_t constitution,CBMDP_HPRolls*);
struct CBMDP_SkillChoices { uint8_t before[7], selected[7]; };
/* Concrete low-level mutation primitive for the future combined commit. It is
 * NOT installed or wired to a UI. Caller must own the native manual transaction
 * and its journal; these expected bytes are a concurrency check, not a fixture.
 * Requires actual actor/type correspondence and old class still unusable. Uses
 * native SetSkillValue, touching only accepted base skill fields. All validation
 * precedes writes. Returns unused budget for the owning class receipt.
 */
CBMDP_API int CBMDP_ApplyOldSkills(CBMDP_Binding *binding,void *rules,void *actor,
    const void *before_stats,const void *after_stats,uint8_t expected_active,
    uint8_t expected_old,uint32_t old_kit,const CBMDP_SkillChoices *choices,
    uint32_t *unused_points);
CBMDP_API int CBMDP_ApplyOldPlanSkills(CBMDP_Binding*,void* rules,void* actor,
 uint8_t active,uint8_t old,uint32_t xp,uint32_t kit,const CBMDP_SkillChoices*,uint32_t* unused);
