// Independent-DLL carrier: wrap the certified pre-existing EEex unmarshal
// target, and the native DecodeEffectFromBase entry. Does not install detours.
#pragma once
#include "eeex_save_bridge.h"
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <vector>

namespace cbm::scroll {
class DecodeCarrier {
public:
    using Unmarshal = void (*)(void*, unsigned char*, unsigned, void*, unsigned char);
    using Decode = void* (*)(const void*);
private:
    struct Scope { const unsigned char* data; std::size_t size; void* actor; unsigned char version; };
    Unmarshal previous_;
    Decode native_;
    std::vector<Scope> scopes_;
    unsigned calls_{};
    struct Busy { unsigned& count; explicit Busy(unsigned& value) : count(value) { ++count; } ~Busy() { --count; } };
public:
    DecodeCarrier(Unmarshal previous, Decode native) : previous_(previous), native_(native) {
        if (!previous || !native) throw std::invalid_argument("decode carrier needs certified EEex target and native trampoline");
    }
    void unmarshal(void* list, unsigned char* data, unsigned size, void* actor, unsigned char version) {
        Busy busy(calls_);
        // Scope EVERY call, including V0/null actor, to mask an outer V1 load.
        // The compiled C++ wrapper has normal Windows x64 unwind metadata.
        scopes_.push_back({data, size, actor, version});
        struct Pop { std::vector<Scope>& values; ~Pop() { values.pop_back(); } } pop{scopes_};
        if (actor && version == 1) CBMS_EEexBeginEffectUnmarshal(actor, version);
        previous_(list, data, size, actor, version);
    }
    void* decode(const void* raw) {
        Busy busy(calls_);
        // Preserve the exact native decoder return, including null. A different
        // actor/load nested inside this call has its own scope and restores ours.
        auto* effect = native_(raw);
        if (scopes_.empty()) return effect;
        const auto& scope = scopes_.back();
        if (!scope.actor || scope.version != 1 || !scope.data || !raw) return effect;
        const auto base = reinterpret_cast<uintptr_t>(scope.data);
        const auto address = reinterpret_cast<uintptr_t>(raw);
        // Association is the ACTUAL native decoder argument/return pair in this
        // source buffer. Not an effect-list position or a resref fingerprint.
        if (address < base || scope.size < 0x108 || address - base > scope.size - 0x108 ||
            (address - base) % 0x108 != 0) return effect;
        if (std::memcmp(raw, "X-BIV1.0", 8) == 0) {
            CBMS_EEexRejectEnvelope("EEex metadata reached native effect decoder unexpectedly");
            return effect;
        }
        CBMS_EEexEffectDecoded(scope.actor, effect, raw);
        return effect;
    }
    bool idle() const noexcept { return calls_ == 0 && scopes_.empty(); }
};
} // namespace cbm::scroll
