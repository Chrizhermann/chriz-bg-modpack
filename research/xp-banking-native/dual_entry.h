#pragma once
#include "dual_manual_session.h"
// Source-bound eligibility for the owned old-class first page. It changes only
// IsLevelUpButtonClickable's PRIVATE derived-stats copy. It does not open a
// screen or grant a level. The account owner supplies the earned target level.
struct CBMDE_Config {
 uint32_t abi;
 uintptr_t clickable,next_level,get_classes,get_class,get_level,set_level,is_usable;
 uintptr_t identity_query,identity_can_mutate;
 uintptr_t on_click,game,get_deny,eligible_lua,route_lua;
};
CBMDS_API int CBMDE_Configure(const CBMDE_Config*);
// 1 allowed, 0 native restrictions deny it, -1 invalid/stale scope.
CBMDS_API int CBMDE_Check(void* character_screen,void* actor,uint64_t incarnation,
 uint8_t old_before,uint8_t old_target);
// Replace ONLY IsLevelUpButtonClickable(sprite)'s audited GetNextLevel call.
// Unscoped calls retain the original routine and all native restrictions.
CBMDS_API void CBMDE_GetNextLevel(void* rules,void* type,void* private_stats);
CBMDS_API int CBMDE_Clickable(void* character_screen,void* actor);
CBMDS_API void CBMDE_Click(void* character_screen);
// Continue the normal button pipeline only for the currently selected actor.
CBMDS_API int CBMDE_Open(void* character_screen,void* actor,uint64_t incarnation,
 uint8_t old_before,uint8_t old_target);
