// Research-only observation extension. No actor/ledger/reward mutation API.
#pragma once
#include <cstdint>
#ifdef _WIN32
#define CBMDH_API extern "C" __declspec(dllexport)
#else
#define CBMDH_API extern "C"
#endif
struct CBMDH_Config {
    uint32_t abi;
    // Audited CRuleTables::GetHitPoints; replaced ONLY at ResetLevelUpPanel's
    // call site. It is NOT the global function entry (also used by opcodes).
    uintptr_t get_hit_points;
};
struct CBMDH_Sample { uint32_t level; int32_t rolled_hp; };
struct CBMDH_Batch {
    uint32_t abi,serial,count,status; // status:1=complete,2=uncertain/incomplete
    uintptr_t actor;
    int32_t native_total;
    uint16_t before_levels[3],after_levels[3];
    CBMDH_Sample samples[255]; // Native dual level bytes bound the active span.
};
CBMDH_API int CBMDH_Configure(const CBMDH_Config*);
CBMDH_API int32_t CBMDH_Capture(void* rules,void* type,void* before,void* after,
    unsigned char constitution,void* actor);
// Exact mid-instruction observer: R15D=level,EAX=already-rolled contribution.
CBMDH_API void CBMDH_Record(uint32_t level,int32_t rolled_hp) noexcept;
CBMDH_API int CBMDH_Peek(CBMDH_Batch*);
// Acknowledges read only; no committing HP or class ownership is implied.
CBMDH_API int CBMDH_Acknowledge(uint32_t serial);
CBMDH_API int CBMDH_SetSink(uintptr_t sink); // actual CBMDS_OnHP; engine thread only
