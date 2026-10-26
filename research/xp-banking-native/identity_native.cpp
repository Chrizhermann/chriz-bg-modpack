// Actual native-call shims, not injected reason callbacks. See identity_hooks.lua
// for the concrete InfinityLoader/EEex loading and entry-detour path.
#include "identity_native.h"
#include <array>
#include <atomic>
#include <charconv>
#include <cstring>
#include <limits>
#include <thread>
#include <unordered_map>
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#pragma comment(lib, "bcrypt.lib")
#endif

namespace {
CBMI_Config config{};
bool configured = false;
std::thread::id host_thread;
struct Lifetime { CBMI_Reason birth; uint64_t incarnation; std::array<char, 33> token; bool replaced = false; };
std::unordered_map<const void*, Lifetime> actors;
uint64_t next_incarnation = 0;
// Another thread's lifetime event: every identity is unavailable from then on,
// for the rest of the process (a restart restores banking). Its address is
// recorded first, lock-free and bounded: slots fill in order and are never
// cleared, and with all of them taken every address counts as recorded. An
// event at an address leaves whatever lifetime was there unknown; one
// elsewhere proves nothing about it.
std::atomic<bool> foreign_lifetime_seen{false};
constexpr size_t foreign_slots = 64;
std::array<std::atomic<uintptr_t>, foreign_slots> foreign_addresses{};
std::atomic<bool> foreign_addresses_full{false};
void note_foreign(const void* sprite) {
    const auto address = reinterpret_cast<uintptr_t>(sprite);
    if (!address) return; // No actor there; CBMI_Lifetime never reads one.
    for (auto& slot : foreign_addresses) {
        uintptr_t seen = 0;
        if (slot.compare_exchange_strong(seen, address) || seen == address) return;
    }
    foreign_addresses_full = true;
}
bool foreign_at(const void* sprite) {
    if (foreign_addresses_full) return true;
    const auto address = reinterpret_cast<uintptr_t>(sprite);
    for (const auto& slot : foreign_addresses) {
        const auto seen = slot.load();
        if (seen == address) return true;
        if (seen == 0) return false; // Later slots fill only after this one.
    }
    return foreign_addresses_full;
}
// No allocation in scope entry/exit. RAII restores the prior scope on C++
// unwinding; a process-fatal SEH fault is not claimed to be recoverable.
struct Scope {
    CBMI_Reason reason;
    const void* serializing;
    Scope* prior;
    static thread_local Scope* top;
    Scope(CBMI_Reason r, const void* s = nullptr) : reason(r), serializing(s), prior(top) { top = this; }
    ~Scope() { top = prior; }
};
thread_local Scope* Scope::top = nullptr;
bool on_host() { return configured && std::this_thread::get_id() == host_thread; }
CBMI_Reason current() { return Scope::top ? Scope::top->reason : CBMI_WORLD; }
bool copy_reason(CBMI_Reason r) { return r == CBMI_MAGICAL_CLONE || r == CBMI_PREVIEW || r == CBMI_OTHER_COPY; }
const char* reason_name(CBMI_Reason r) {
    static const char* names[] = {"world", "save", "chr_export", "chr_import", "magical_clone", "preview", "other_copy"};
    return names[static_cast<unsigned>(r)];
}
bool token(std::array<char, 33>& out) {
#ifdef _WIN32
    unsigned char bytes[16];
    if (BCryptGenRandom(nullptr, bytes, sizeof(bytes), BCRYPT_USE_SYSTEM_PREFERRED_RNG) < 0) return false;
    constexpr char hex[] = "0123456789abcdef";
    for (size_t i = 0; i != 16; ++i) { out[2*i] = hex[bytes[i] >> 4]; out[2*i+1] = hex[bytes[i] & 15]; }
    out[32] = 0;
    return true;
#else
    (void)out;
    return false; // This is a Windows native host, not a guessed portable UUID.
#endif
}
template<class T> T original(CBMI_Slot slot) { return reinterpret_cast<T>(config.originals[slot]); }
}

int CBMI_Configure(const CBMI_Config* in) {
    if (!in || in->abi != 1 || configured) return 0;
    for (auto address : in->originals) if (!address) return 0;
    if (!in->lua_tolstring || !in->lua_pushstring || !in->lua_pushboolean || !in->strip_uuid || !in->no_uuid) return 0;
    config = *in;
    host_thread = std::this_thread::get_id();
    configured = true;
    return 1;
}

void* CBMI_Copy(void* sprite, int a, int b, int c, int d) {
    const auto fn = original<void*(*)(void*, int, int, int, int)>(CBMI_COPY);
    if (!on_host()) return fn(sprite, a, b, c, d);
    // The method boundary proves this IS Copy. The flags only refine its subtype;
    // unlike IsMarshallingCopy alone, they cannot confuse a CHR export with Copy.
    const auto r = *reinterpret_cast<const bool*>(config.no_uuid) ? CBMI_PREVIEW
        : *reinterpret_cast<const bool*>(config.strip_uuid) ? CBMI_MAGICAL_CLONE : CBMI_OTHER_COPY;
    Scope scope(r);
    return fn(sprite, a, b, c, d);
}
uintptr_t CBMI_Marshal(void* sprite, void* a, void* b, void* c, unsigned char d) {
    const auto fn = original<uintptr_t(*)(void*, void*, void*, void*, unsigned char)>(CBMI_MARSHAL);
    if (!on_host()) return fn(sprite, a, b, c, d);
    const auto r = current() == CBMI_WORLD ? CBMI_SAVE : current();
    Scope scope(r, sprite);
    return fn(sprite, a, b, c, d);
}
uintptr_t CBMI_CharacterExport(void* game, int id, void* name, int quiet) {
    const auto fn = original<uintptr_t(*)(void*, int, void*, int)>(CBMI_EXPORT);
    if (!on_host()) return fn(game, id, name, quiet);
    // Nested explicit export is still subordinate to an enclosing copy. It must
    // never promote a preview/clone into an eligible owner.
    Scope scope(copy_reason(current()) ? current() : CBMI_CHR_EXPORT);
    return fn(game, id, name, quiet);
}
int CBMI_CharacterImport(void* game, void* name, void* version, unsigned char flag) {
    const auto fn = original<int(*)(void*, void*, void*, unsigned char)>(CBMI_IMPORT);
    if (!on_host()) return fn(game, name, version, flag);
    Scope scope(copy_reason(current()) ? current() : CBMI_CHR_IMPORT);
    return fn(game, name, version, flag);
}
void CBMI_Construct(void* sprite) {
    // This is invoked early by EEex's native constructor hook, before the CRE's
    // effect stream is imported; it is independent of late m_bInCopy assignment.
    if (on_host()) {
        try {
            actors.erase(sprite); // Pointer reuse cannot inherit a prior lifetime.
            if (next_incarnation != std::numeric_limits<uint64_t>::max()) {
                const auto birth = copy_reason(current()) || current() == CBMI_CHR_IMPORT ? current() : CBMI_WORLD;
                Lifetime life{birth, ++next_incarnation, {}};
                if (copy_reason(life.birth) || token(life.token)) actors.emplace(sprite, life);
            }
        } catch (...) { actors.erase(sprite); } // No guessed identity on allocation failure.
    } else { // Never race the host's registry (main-thread-audit-2.7.3.txt finds no resolved path here).
        note_foreign(sprite); foreign_lifetime_seen = true; // Both before the object changes.
    }
    original<void(*)(void*)>(CBMI_CONSTRUCT)(sprite);
}
void CBMI_Destruct(void* sprite) {
    if (on_host()) actors.erase(sprite);
    else { note_foreign(sprite); foreign_lifetime_seen = true; }
    original<void(*)(void*)>(CBMI_DESTRUCT)(sprite);
}
int CBMI_Query(const void* sprite, CBMI_View* out) {
    // After another thread's lifetime event no identity is trusted again in this
    // process: banking stays off until the game restarts.
    if (!on_host() || foreign_lifetime_seen || !sprite || !out) return 0;
    const auto it = actors.find(sprite);
    if (it == actors.end()) return 0;
    CBMI_View value{};
    value.birth = it->second.birth;
    value.current = current();
    value.incarnation = it->second.incarnation;
    std::memcpy(value.owner_token, it->second.token.data(), 33);
    for (auto* s = Scope::top; s; s = s->prior) {
        if (s->serializing == sprite) value.serializing = true;
    }
    value.eligible = !copy_reason(value.birth) && !copy_reason(value.current);
    *out = value;
    return 1;
}
int CBMI_CanMutate(const void* sprite, uint64_t incarnation) {
    CBMI_View view{};
    if (!CBMI_Query(sprite, &view) || !view.eligible || view.incarnation != incarnation) return 0;
    // Shared EEex marshal scratch means an unrelated sprite's nested marshal
    // also excludes mutation. This guard does not repair pre-existing reentry.
    for (auto* s = Scope::top; s; s = s->prior) if (s->serializing) return 0;
    return 1;
}

void CBMI_NoteReplaced(const void* sprite) {
    if (!on_host()) return; // The registry is the main thread's.
    const auto it = actors.find(sprite);
    if (it != actors.end()) it->second.replaced = true;
}
int CBMI_Lifetime(const void* sprite, uint64_t incarnation) {
    if (!on_host() || !sprite) return 0;
    // Only this thread changes the registry, and only in Construct and Destruct:
    // an entry gone or newer proves that lifetime ended. Another thread's event
    // at this address may have ended it too, unseen, so then only the proof
    // counts; one at another address proves nothing about this one. An event
    // racing this very read is one on an object the game itself is using here.
    const auto it = actors.find(sprite);
    if (it == actors.end() || it->second.incarnation != incarnation) return -1;
    return foreign_at(sprite) ? 0 : 1;
}

namespace {
using ToString = const char*(*)(void*, int, size_t*);
bool lua_unsigned(void* L, int index, int base, uint64_t* out) {
    size_t count = 0;
    const char* text = reinterpret_cast<ToString>(config.lua_tolstring)(L, index, &count);
    if (!text || count == 0 || count > 20) return false;
    const auto parsed = std::from_chars(text, text + count, *out, base);
    return parsed.ec == std::errc{} && parsed.ptr == text + count;
}
}
int CBMI_LuaQuery(void* L) {
    using PushString = const char*(*)(void*, const char*);
    using PushBool = void(*)(void*, int);
    if (!on_host()) return 0;
    auto read = reinterpret_cast<ToString>(config.lua_tolstring);
    auto push = reinterpret_cast<PushString>(config.lua_pushstring);
    auto boolean = reinterpret_cast<PushBool>(config.lua_pushboolean);
    size_t count = 0;
    const char* text = read(L, 1, &count);
    uintptr_t address = 0;
    if (!text || count == 0 || count > sizeof(uintptr_t)*2) return 0;
    const auto parsed = std::from_chars(text, text + count, address, 16);
    if (parsed.ec != std::errc{} || parsed.ptr != text + count) return 0;
    CBMI_View view{};
    if (!CBMI_Query(reinterpret_cast<const void*>(address), &view)) return 0;
    char generation[32];
    auto result = std::to_chars(generation, generation + sizeof(generation)-1, view.incarnation);
    *result.ptr = 0;
    push(L, reason_name(view.birth)); push(L, reason_name(view.current));
    push(L, generation); push(L, view.owner_token);
    boolean(L, view.serializing); boolean(L, view.eligible);
    boolean(L, CBMI_CanMutate(reinterpret_cast<const void*>(address), view.incarnation));
    boolean(L, actors.at(reinterpret_cast<const void*>(address)).replaced);
    return 8;
}
int CBMI_LuaAckReplaced(void* L) {
    if (!on_host() || foreign_lifetime_seen) return 0;
    uint64_t address = 0, incarnation = 0;
    if (!lua_unsigned(L, 1, 16, &address) || !lua_unsigned(L, 2, 10, &incarnation)) return 0;
    const auto it = actors.find(reinterpret_cast<const void*>(static_cast<uintptr_t>(address)));
    const bool cleared = it != actors.end() && it->second.incarnation == incarnation;
    if (cleared) it->second.replaced = false;
    reinterpret_cast<void(*)(void*, int)>(config.lua_pushboolean)(L, cleared);
    return 1;
}
