// Uninstalled scoped stat44 branch bridge. Other stats never enter this function.
#pragma once
#include "identity_native.h"
enum CBMW_Stage:unsigned{CBMW_PREPARING=1,CBMW_WRITING,CBMW_COMPLETING,CBMW_UNCERTAIN,CBMW_WITHDRAWING}; // As CBMA_Stage.
struct CBMW_Config{uint64_t abi;uintptr_t setter,before,complete,uncertain,lua_tolstring,lua_pushstring,lua_pushboolean;};
struct CBMW_View{uint64_t incarnation;uint32_t raw_value,mode,pre_base,post_base,planned_base,origin;CBMW_Stage stage;bool planned;
    uint32_t source,effect_mode;int native_result;const void* effect;};
CBMI_API int CBMW_Configure(const CBMW_Config*);
// RDX is the native switch destination, deliberately unused. RCX/R8/R9 carry
// actor/value/mode. Return original actor so native continuation restores RCX.
// Every refusal still performs the write: the original store (counted), or,
// while a change of that actor is in flight, the same store as it closes. Only
// where another thread's lifetime event at that address leaves its actor
// unknown is the write kept instead, never written (12, CBMW_Kept).
CBMI_API void* CBMW_Write(void* sprite,uintptr_t unused,uint32_t value,uint32_t mode);
// Actual permanent opcode104 leaf caller only. A refused plan writes no XP
// itself: it runs the original leaf (native), defers or completes, and never
// returns 0. Positive additions use the separate award overflow bridge.
CBMI_API int CBMW_EffectWrite(void* effect,void* sprite,uintptr_t original_leaf);
CBMI_API int CBMW_Query(const void*,CBMW_View*);
CBMI_API int CBMW_Plan(const void*,uint32_t target);
CBMI_API int CBMW_ApplyOwnedSet(void*,uint32_t target,uint32_t origin,uint16_t* native_result);
CBMI_API int CBMW_LuaQuery(void*);
CBMI_API int CBMW_LuaPlan(void*);
CBMI_API int CBMW_LuaApplyOwnedSet(void*);
CBMI_API int CBMW_LastStatus();
// Writes the bank could not take that ran the game's own code instead: the
// original opcode-104 leaf, or the original stat44 store (mode 1 adds, any
// other sets). A setter write is never dropped. last_status may be null.
CBMI_API uint64_t CBMW_Fallbacks(int* last_status);
// The setter writes kept unwritten (12): their actor became unknown at its
// address (CBMI_Lifetime 0), so nothing was stored into what may now be another
// actor. Not fallbacks. Process-wide, never cleared; text lists them ("add 1000,
// set 54321"), truncated to size with ", ..." while the count stays exact.
// Same-DLL, host thread only.
uint64_t CBMW_Kept(char* text,size_t size);
// Same-DLL coordination with the award bridge, not exported. Holds: bit 1 a
// change of this actor in flight (any lifetime), bit 2 an uncertain record of
// this lifetime. Settle lands the setter writes deferred behind a change of
// that actor once no change of it is in flight; every change window ends with it.
int CBMW_Holds(const void* sprite,uint64_t incarnation);
void CBMW_Settle(void* sprite);
struct CBMW_SettleOnExit{void* sprite;~CBMW_SettleOnExit(){CBMW_Settle(sprite);}};
// The retry table of both bridges: true for the first change of this effect in
// this lifetime (it defers once), false for its second or when the table is
// full of live entries (the original runs). A scope drops the effect's entry
// as it resolves, unless kept by a defer. Host thread only.
bool CBMW_FirstChange(const void* effect,const void* sprite,uint64_t incarnation);
struct CBMW_RetryScope{const void* effect;bool kept=false;~CBMW_RetryScope();};
// Whether the original opcode-104 leaf, about to run this effect on this actor
// as the effect now reads, replaces the XP word (a permanent SET, percentage,
// or addition past either end): the bank then takes the stored word. Either
// bridge's fallback classifies the operation it actually executes with it.
bool CBMW_LeafReplaces(const void* effect,const void* sprite);
// Changes whose actor lifetime provably ended while the bank prepared them
// (status 11; CBMI_Lifetime -1); nothing was written into another lifetime.
// An identity merely unknown is no such proof. Both bridges, process-wide.
void CBMW_CountEnded();
uint64_t CBMW_Ended();
