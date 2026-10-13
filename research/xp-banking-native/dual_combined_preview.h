#pragma once
#include "dual_native_proficiency.h"
#include "dual_manual_session.h"
// Uninstalled extension of the ACTUAL normal manual-screen scope. No UI route
// installs this yet. The addresses are the source-audited native functions,
// not reward callbacks. Configure once from the same engine thread as CBMDS.
struct CBMDL_Config {
 uint32_t abi;
 uintptr_t next_level,get_hp,get_classes,get_class,get_level,set_level,is_usable;
 uintptr_t stats_construct,stats_copy,stats_destruct;
 uintptr_t combine_all,prof_apply,prof_restore,prof_complete,prof_persist_dormant;
 uintptr_t get_active,get_inactive,set_active,prof_read_active,prof_read_old,prof_set_active,set_inactive,process_effects;
 uintptr_t prof_begin_active,add_special,apply_old_skills;
};
CBMDP_API int CBMDL_Configure(const CBMDL_Config*);
// The retired choices were selected in the detached first page. Bind this ONLY
// in the real manual Begin callback after saved-owner binding and before Reset.
// Target entitlement/budgets are checked by the owning policy/UI transaction.
CBMDP_API int CBMDL_Select(void* actor,uint64_t session,uint64_t incarnation,
 uint8_t active,uint8_t old,uint8_t before,uint8_t target,const CBMDP_HPRolls*);
struct CBMDL_ProfChoice {uint32_t stat,delta;};
// Ordered new choices; existing inert carriers are interpreted by the concrete
// prof implementation. Bind before native Reset reaches its merge boundary.
CBMDP_API int CBMDL_SelectProficiencies(void* actor,uint64_t session,uint64_t incarnation,
 const CBMDL_ProfChoice*,uint32_t count);
CBMDP_API int CBMDL_SelectSkills(void* actor,uint64_t session,uint64_t incarnation,
 uint32_t old_xp,uint32_t old_kit,const CBMDP_SkillChoices*);
// Exactly ResetLevelUpPanel -> CombineAllActiveInactiveProficiencies, never a
// global stat-generation hook. Native stock merge remains for unowned sessions.
CBMDP_API void CBMDL_CombineAll(void* actor);
CBMDP_API int CBMDL_AfterCancel(void* actor);
CBMDP_API int CBMDL_AfterCommit(void* actor);
CBMDP_API int CBMDL_AfterReset(void* actor);
// First LevelUp call only; the stock reactivation replay remains untouched.
CBMDP_API void CBMDL_AddSpecial(void* actor,const void* before);
// Only the twelve audited native UI callsites and the existing manual setter
// observer use these projections. Other sprite getters retain all effects.
CBMDP_API int32_t CBMDL_GetActive(void* actor,uint32_t stat);
CBMDP_API int32_t CBMDL_GetInactive(void* actor,uint32_t stat);
CBMDP_API void CBMDL_SetActive(void* actor,uint32_t stat,int32_t pips,int immediate);
CBMDP_API void CBMDL_SetInactive(void* actor,uint32_t stat,int32_t pips,int immediate);
CBMDP_API int CBMDL_ReadOld(const void* actor,uint32_t stat,uint32_t* value);
CBMDP_API int CBMDL_IsDormant(const void* actor,uint8_t old);
// Replace only ResetLevelUpPanel's two reviewed GetNextLevel callsites.
CBMDP_API void CBMDL_GetNextLevel(void* rules,void* type,void* stats);
// Feed this to CBMDH's original target once configured. Its only caller is the
// source-bound manual callsite observer, retaining exact per-level HP evidence.
CBMDP_API int32_t CBMDL_GetHitPoints(void* rules,void* type,void* before,void* after,uint8_t constitution);
