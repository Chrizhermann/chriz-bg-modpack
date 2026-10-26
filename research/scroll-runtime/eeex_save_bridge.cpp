#include "eeex_save_bridge.h"
#include "marshal_carrier_api.h"
#include "carrier_gate.hpp"
#include <array>
#include <atomic>
#include <cstring>
#include <exception>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>

namespace {
std::atomic<CBMS_Runtime*> runtime{};
cbm::scroll::CarrierGate gate; // the attaching engine thread
std::array<char, 256> fault{};
struct Saving { void** output; };
std::unordered_map<void*, Saving> saving;
std::unordered_set<void*> loading, finished;
// Why an actor's outdated envelope was dropped in its latest finished load.
std::unordered_map<void*, std::array<char, 256>> dropped;
// Inert before attachment. On another thread (Lua run elsewhere, or a carrier
// reached that way) nothing but the process-wide foreign latch is touched.
bool attached() noexcept {
    if (!runtime) return false;
    if (gate.owner()) return true;
    CBMS_ForeignEntry();
    return false;
}
void fail(const char* text) noexcept {
    CBMS_DisableOverrides(runtime);
    if (fault[0]) return; // First diagnostic describes the original failure.
    if (!text) text = "unknown scroll marshal bridge failure";
    auto n = std::strlen(text);
    if (n >= fault.size()) n = fault.size() - 1;
    std::memcpy(fault.data(), text, n); fault[n] = 0;
}
bool check(int result) noexcept {
    if (result == 1) return true;
    fail(CBMS_LastError(runtime)); return false;
}
template<class F> void safely(F body) noexcept {
    // Disabled bridge does not register or mutate native objects.
    if (!attached() || fault[0]) return;
    try { body(); }
    catch (const std::exception& error) { fail(error.what()); }
    catch (...) { fail("unexpected native actor marshal bridge error"); }
}
}
int CBMS_EEexConfigureCurrent() {
    // Before attachment there is no owner thread yet; attaching clears this.
    if (!runtime || attached())
        fail("scroll runtime disabled: use the early startup transaction with a verified installed resource policy");
    return 0;
}
const char* CBMS_EEexBridgeError() { return fault.data(); }
// Disabled overrides also stop envelope exchange: CBMS_ScrollMarshal.lua then
// keeps every loaded envelope unchanged instead of consuming it.
int CBMS_EEexBridgeHealthy() { return attached() && !fault[0] && !CBMS_OverridesDisabled(runtime) ? 1 : 0; }
int CBMS_EEexAttachRuntime(CBMS_Runtime* value) {
    if (!value || runtime || !saving.empty() || !loading.empty()) return 0;
    gate.configure(); runtime = value; fault.fill(0); finished.clear(); dropped.clear(); return 1;
}
#ifdef CBMS_OFFLINE_HARNESS
int CBMS_EEexAttachForTest(CBMS_Runtime* value) {return CBMS_EEexAttachRuntime(value);}
#endif
void CBMS_EEexBeforeEffectMarshal(void* actor, void* list, void** output, uint32_t flags) {
    safely([&] {
        if (!actor || !list || !output || flags > 3 || saving.contains(actor))
            throw std::logic_error("invalid/reentrant native actor marshal event");
        const auto key = reinterpret_cast<uintptr_t>(actor);
        if (!check(CBMS_ActorObserved(runtime, key, 0))) return;
        // Reserve host cleanup state before the core can create a pending export.
        saving.emplace(actor, Saving{output});
        if (!check(CBMS_PrepareEffectExport(runtime, key, reinterpret_cast<uintptr_t>(list),
                                           1, flags & 1, (flags >> 1) & 1))) saving.erase(actor);
    });
}
void CBMS_EEexAfterEffectMarshal(void* actor, uint32_t size) {
    safely([&] {
        const auto state = saving.at(actor);
        if (check(CBMS_ValidateEffectExport(runtime, reinterpret_cast<uintptr_t>(actor), *state.output, size)))
            saving.erase(actor);
    });
}
void CBMS_EEexBeginEffectUnmarshal(void* actor, uint32_t version) {
    safely([&] {
        if (!actor || version != 1 || loading.contains(actor))
            throw std::logic_error("unsupported/reentrant native actor effect decode");
        const auto key = reinterpret_cast<uintptr_t>(actor);
        if (!check(CBMS_ActorObserved(runtime, key, 0))) return;
        loading.insert(actor); finished.erase(actor); dropped.erase(actor);
        if (!check(CBMS_BeginEffectImport(runtime, key))) loading.erase(actor);
    });
}
void CBMS_EEexEffectDecoded(void* actor, void* effect, const void* raw) {
    safely([&] {
        if (!loading.contains(actor)) throw std::logic_error("decode outside actor import");
        check(CBMS_ObserveEffectDecoded(runtime, reinterpret_cast<uintptr_t>(actor),
                                       reinterpret_cast<uintptr_t>(effect), raw));
    });
}
void CBMS_EEexAfterActorUUID(void* actor, uint64_t uuid) {
    safely([&] {
        const auto key = reinterpret_cast<uintptr_t>(actor);
        if (!check(CBMS_ActorObserved(runtime, key, uuid))) return;
        if (!loading.contains(actor)) return; // also binds a later original reader
        // Reserve before commit; allocation failure cannot follow restored ownership.
        finished.insert(actor);
        auto& reason = dropped[actor];
        const auto result = CBMS_FinishEffectImport(runtime, key, reason.data(), static_cast<uint32_t>(reason.size()));
        if (result == 1 || result == 2) loading.erase(actor);
        else { finished.erase(actor); fail(CBMS_LastError(runtime)); }
        // 2: this actor's envelope no longer matched its records and was
        // dropped for it alone. Its loaded effects carry no saved ancestry.
        if (result != 2) dropped.erase(actor);
    });
}
int CBMS_EEexCancelledActorIO(void* actor) {
    if (!attached()) return 0;
    const auto key = reinterpret_cast<uintptr_t>(actor);
    if (saving.contains(actor)) {
        if (CBMS_AbortEffectExport(runtime, key) != 1) return 0;
        saving.erase(actor);
    }
    if (loading.contains(actor)) {
        if (CBMS_AbortEffectImport(runtime, key) != 1) return 0;
        loading.erase(actor);
    }
    // Fault stays latched; unknown actor envelope stays in UDAux.
    return 1;
}
int CBMS_EEexDetachQuiescent() {
    if (!attached() || !saving.empty() || !loading.empty() || CBMS_Quiescent(runtime) != 1) return 0;
    runtime = nullptr; finished.clear(); dropped.clear(); return 1;
}
const char* CBMS_EEexExportText(void* actor) {
    if (!attached() || fault[0]) return nullptr;
    if (CBMS_ClaimMarshalActor(actor) < 0) return nullptr;
    const auto* text = CBMS_EffectExportText(runtime, reinterpret_cast<uintptr_t>(actor));
    if (!text) fail(CBMS_LastError(runtime));
    return text;
}
int CBMS_EEexStageText(void* actor, const char* text, uint32_t length) {
    if (!attached() || fault[0]) return 0;
    return check(CBMS_StageEffectImportText(runtime, reinterpret_cast<uintptr_t>(actor), text, length)) ? 1 : 0;
}
// Once overrides are disabled the Lua adapter keeps the loaded envelope too.
int CBMS_EEexImportFinished(void* actor) {
    return attached() && !fault[0] && !CBMS_OverridesDisabled(runtime) && finished.contains(actor) ? 1 : 0;
}
const char* CBMS_EEexImportDropped(void* actor) {
    if (!CBMS_EEexImportFinished(actor)) return nullptr;
    const auto found = dropped.find(actor);
    return found == dropped.end() ? nullptr : found->second.data();
}
// Before attachment a rejection has nothing to disable; attaching clears it.
void CBMS_EEexRejectEnvelope(const char* reason) { if (attached()) fail(reason); }
void CBMS_EEexLiveEffectCopied(void* source,void* destination) {
    // Existing owned carriers still need maintenance after a policy fault;
    // suppressing copy/destruction would leave stale pointers on address reuse.
    if(attached()) check(CBMS_EffectCopied(runtime,reinterpret_cast<uintptr_t>(source),reinterpret_cast<uintptr_t>(destination)));
}
void CBMS_EEexEffectDestroyed(void* effect) {
    if(attached()) check(CBMS_DestructObserved(runtime,1,reinterpret_cast<uintptr_t>(effect)));
}
void CBMS_EEexActorDestroyed(void* actor) {
    if(!attached()) return;
    // The actual owning destructor proves this actor's pending native IO will
    // not finish. This is cleanup on destruction, not invented save rollback.
    if(!CBMS_EEexCancelledActorIO(actor)) fail("cannot discard destroyed actor's pending IO state");
    finished.erase(actor); dropped.erase(actor);
    check(CBMS_DestructObserved(runtime,0,reinterpret_cast<uintptr_t>(actor)));
}
