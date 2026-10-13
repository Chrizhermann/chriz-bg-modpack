#include "eeex_save_bridge.h"
#include "marshal_carrier_api.h"
#include <array>
#include <cstring>
#include <exception>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>

namespace {
CBMS_Runtime* runtime{};
std::array<char, 256> fault{};
struct Saving { void** output; };
std::unordered_map<void*, Saving> saving;
std::unordered_set<void*> loading, finished;
void fail(const char* text) noexcept {
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
    if (!runtime || fault[0]) return;
    try { body(); }
    catch (const std::exception& error) { fail(error.what()); }
    catch (...) { fail("unexpected native actor marshal bridge error"); }
}
}
int CBMS_EEexConfigureCurrent() {
    fail("scroll runtime disabled: use the early startup transaction with a verified installed resource policy");
    return 0;
}
const char* CBMS_EEexBridgeError() { return fault.data(); }
int CBMS_EEexBridgeHealthy() { return runtime && !fault[0] ? 1 : 0; }
int CBMS_EEexAttachRuntime(CBMS_Runtime* value) {
    if (!value || runtime || !saving.empty() || !loading.empty()) return 0;
    runtime = value; fault.fill(0); finished.clear(); return 1;
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
        loading.insert(actor); finished.erase(actor);
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
        if (check(CBMS_FinishEffectImport(runtime, key))) loading.erase(actor);
        else finished.erase(actor);
    });
}
int CBMS_EEexCancelledActorIO(void* actor) {
    if (!runtime) return 0;
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
    if (!runtime || !saving.empty() || !loading.empty() || CBMS_Quiescent(runtime) != 1) return 0;
    runtime = nullptr; finished.clear(); return 1;
}
const char* CBMS_EEexExportText(void* actor) {
    if (!runtime || fault[0]) return nullptr;
    if (CBMS_ClaimMarshalActor(actor) < 0) return nullptr;
    const auto* text = CBMS_EffectExportText(runtime, reinterpret_cast<uintptr_t>(actor));
    if (!text) fail(CBMS_LastError(runtime));
    return text;
}
int CBMS_EEexStageText(void* actor, const char* text, uint32_t length) {
    if (!runtime || fault[0]) return 0;
    return check(CBMS_StageEffectImportText(runtime, reinterpret_cast<uintptr_t>(actor), text, length)) ? 1 : 0;
}
int CBMS_EEexImportFinished(void* actor) { return runtime && !fault[0] && finished.contains(actor) ? 1 : 0; }
void CBMS_EEexRejectEnvelope(const char* reason) { fail(reason); }
void CBMS_EEexLiveEffectCopied(void* source,void* destination) {
    // Existing owned carriers still need maintenance after a policy fault;
    // suppressing copy/destruction would leave stale pointers on address reuse.
    if(runtime) check(CBMS_EffectCopied(runtime,reinterpret_cast<uintptr_t>(source),reinterpret_cast<uintptr_t>(destination)));
}
void CBMS_EEexEffectDestroyed(void* effect) {
    if(runtime) check(CBMS_DestructObserved(runtime,1,reinterpret_cast<uintptr_t>(effect)));
}
void CBMS_EEexActorDestroyed(void* actor) {
    if(!runtime) return;
    // The actual owning destructor proves this actor's pending native IO will
    // not finish. This is cleanup on destruction, not invented save rollback.
    if(!CBMS_EEexCancelledActorIO(actor)) fail("cannot discard destroyed actor's pending IO state");
    finished.erase(actor);
    check(CBMS_DestructObserved(runtime,0,reinterpret_cast<uintptr_t>(actor)));
}
