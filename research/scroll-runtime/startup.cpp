#include "startup.h"
#include "cast_hook_host.h"
#include "decode_hook_host.h"
#include "dispatch_hook_host.h"
#include "item_hook_host.h"
#include "linked177_api.h"
#include "conditional_api.h"
#include "eeex_save_bridge.h"
#include "carrier_gate.hpp"
#include <algorithm>
#include <array>
#include <atomic>
#include <cstring>
#include <stdexcept>
#define NOMINMAX
#include <windows.h>
extern "C" {
int CBMS_ItemHooksPresent(); int CBMS_CastHooksPresent(); int CBMS_DispatchHooksPresent();
int CBMS_DecodeHooksPresent(); int CBMS_Linked177HooksPresent();
int CBMS_ConditionalHooksPresent();
}
namespace {
CBMS_Runtime* runtime{};
// The engine thread that ran the transaction owns everything below.
cbm::scroll::CarrierGate gate;
std::atomic<bool> attempted{};
bool ready{},retained{};
std::array<char,512> error{};
void fail(const char* message) noexcept {
    // A refusal after a successful start, too, keeps every later selection native.
    CBMS_DisableOverrides(runtime);
    if(error[0])return;
    if(!message||!*message)message="scroll startup failed without a diagnostic";
    const auto n=(std::min)(std::strlen(message),error.size()-1);
    std::memcpy(error.data(),message,n);error[n]=0;
}
void report(const char* message,void*){fail(message);}
void require(int status,const char* reason){if(status!=1)throw std::runtime_error(reason&&*reason?reason:"scroll carrier installation failed");}
bool rollback() noexcept {
    // Include the failed group if it retained executable memory or a partial
    // patch. Stop on a failed rollback: earlier dependencies must remain alive.
    struct Removal{int(*present)();int(*remove)();};
    for(const auto& group:{Removal{CBMS_ItemHooksPresent,CBMS_RemoveItemHooks},
        Removal{CBMS_CastHooksPresent,CBMS_RemoveCastHooks},Removal{CBMS_DispatchHooksPresent,CBMS_RemoveDispatchHooks},
        Removal{CBMS_DecodeHooksPresent,CBMS_RemoveDecodeHooks},
        Removal{CBMS_ConditionalHooksPresent,CBMS_RemoveConditionalHooks},
        Removal{CBMS_Linked177HooksPresent,CBMS_RemoveLinked177Hooks}}) {
        if(group.present()&&group.remove()!=1)return false;
    }
    CBMS_ItemAdmission(nullptr);
    if(runtime&&CBMS_Destroy(runtime)!=1)return false;
    runtime=nullptr;return true;
}
}
static int start(uintptr_t game,uintptr_t eeex,const void* policy,uint32_t size,CBMS_PolicyDigest digest,void* user,CBMS_BankActorQuery bank=nullptr,void* bank_user=nullptr) {
    if(attempted.exchange(true)){
        // Another thread must not even write the diagnostic.
        if(gate.owner())fail("scroll startup is single-attempt; restart the process after refusal");
        else CBMS_ForeignEntry();
        return 0;
    }
    gate.configure();
    try {
        if(!policy||!size||!digest)throw std::invalid_argument("scroll startup needs a generated policy and effective-resource verifier");
        if(!game||!eeex)throw std::runtime_error("scroll startup requires the already loaded game and EEex modules");
        CBMS_NativeFunctions functions{};std::array<char,512> diagnostic{};
        require(CBMS_BindModule(game,&functions,diagnostic.data(),static_cast<uint32_t>(diagnostic.size())),diagnostic.data());
        runtime=CBMS_CreateNative(&functions,report,nullptr);
        if(!runtime)throw std::runtime_error("cannot create native scroll reader runtime");
        CBMS_ItemAdmission(CBMS_StartupHealthy);
        // 177 certifies the original decoder before the persistence wrapper.
        // Queued actions carry ownership by value, so no action lifetime hook
        // precedes dispatch. Item roots become reachable last.
        require(CBMS_InstallLinked177Hooks(game,runtime),CBMS_Linked177HookError());
        require(CBMS_InstallConditionalHooks(game,runtime),CBMS_ConditionalHookError());
        require(bank?CBMS_InstallEffectPersistenceHooksChained(game,eeex,bank,bank_user):CBMS_InstallEffectPersistenceHooks(game,eeex),CBMS_DecodeHookError());
        require(CBMS_InstallDispatchHooks(game,runtime),CBMS_DispatchHookError());
        require(CBMS_InstallCastHooks(game,runtime),CBMS_CastHookError());
        require(CBMS_InstallItemHooks(game,runtime,policy,size,digest,user),CBMS_ItemHookError());
        require(CBMS_EEexAttachRuntime(runtime),"cannot attach actor envelope bridge after carrier installation");
        ready=true;return 1;
    }catch(const std::exception& problem){fail(problem.what());}catch(...){fail("unexpected scroll startup failure");}
    retained=!rollback();return 0;
}
int CBMS_StartCurrent(const void* policy,uint32_t size,CBMS_PolicyDigest digest,void* user) {
    return start(reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr)),reinterpret_cast<uintptr_t>(GetModuleHandleW(L"EEex.dll")),policy,size,digest,user);
}
int CBMS_StartCurrentWithBank(const void* policy,uint32_t size,CBMS_PolicyDigest digest,void* user,CBMS_BankActorQuery bank,void* bank_user) {
    return start(reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr)),reinterpret_cast<uintptr_t>(GetModuleHandleW(L"EEex.dll")),policy,size,digest,user,bank,bank_user);
}
#ifdef CBMS_OFFLINE_HARNESS
extern "C" CBMS_EXPORT int CBMS_TestStart(uintptr_t game,uintptr_t eeex,const void* policy,uint32_t size,CBMS_PolicyDigest digest,void* user){return start(game,eeex,policy,size,digest,user);}
#endif
int CBMS_StartupHealthy() {
    if(!gate.owner()){if(attempted)CBMS_ForeignEntry();return 0;}
    if(!ready||error[0])return 0;
    for(const char* detail:{CBMS_EEexBridgeError(),CBMS_ItemCarrierError(),CBMS_CastCarrierError(),
        CBMS_DispatchCarrierError(),CBMS_Linked177Error(),CBMS_ConditionalError()})if(detail&&*detail){fail(detail);return 0;}
    // Neither latch writes a carrier diagnostic of its own.
    if(CBMS_ForeignEntrySeen()){fail("a scroll carrier was entered on a thread other than the engine thread that installed it");return 0;}
    if(CBMS_OverridesDisabled(runtime)){fail("scroll overrides were disabled after an earlier native fault");return 0;}
    return CBMS_EEexBridgeHealthy();
}
const char* CBMS_StartupError() {
    (void)CBMS_StartupHealthy();
    if(retained)return "Scroll startup rollback could not safely remove every hook. Exit this process; do not load or save a game. The native runtime was retained to avoid dangling code.";
    return error.data();
}
int CBMS_StartupRetained() {
    // The flag belongs to the transaction's thread, like the health check.
    if(!gate.owner()){if(attempted)CBMS_ForeignEntry();return 0;}
    return retained?1:0;
}
