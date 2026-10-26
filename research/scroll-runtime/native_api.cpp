#include "native_api.h"
#include "eeex_bridge.hpp"
#include "native_provider.hpp"
#include "native_binder.hpp"
#include "effect_archive_text.hpp"
#include "decode_binding.hpp"
#include "marshal_binding.hpp"
#include "lifecycle_binding.hpp"
#include "action_witness.hpp"
#include <cstring>

using namespace cbm::scroll;
static_assert(sizeof(CBMS_Stats) == 44, "callback snapshot ABI must stay fixed");
struct CBMS_Runtime {
    Registry registry;
    CBMS_Resolve resolve;
    CBMS_Report report;
    std::optional<NativeReaderProvider> native_provider;
    void* user;
    std::array<char, 256> error{};
    bool reporting{};
    std::uint64_t serial{1};
    std::unordered_map<std::uint64_t, std::shared_ptr<const Origin>> uses;
    struct Active { std::uint64_t id; Registry::Scope scope; };
    std::vector<std::unique_ptr<Active>> casts;
    std::vector<std::uint64_t> resolving;
    struct Captured { Selector selector; std::optional<Context> context; };
    std::unordered_map<std::uint64_t,Captured> captured;
    struct EffectSave { SavedEffectArchive archive; std::string text; };
    struct EffectLoad { EffectImport importer; std::optional<SavedEffectArchive> archive; std::size_t next{}; bool failed{}; };
    std::unordered_map<Address, EffectSave> effect_exports;
    std::unordered_map<Address, std::unique_ptr<EffectLoad>> effect_imports;
    ActionWitnesses witnesses;
    explicit CBMS_Runtime(CBMS_Resolve r, CBMS_Report p, void* u) : resolve(r), report(p), user(u) {}
    ~CBMS_Runtime() { while (!casts.empty()) casts.pop_back(); }
    void failure(const char* message) noexcept {
        // Every reported error disables every later override, including those
        // whose ownership was queued or captured before it.
        registry.disable();
        // A reporter may call a failing API itself. Preserve the first error
        // and never recursively report the reporter's own failures.
        if (reporting) return;
        const auto length = std::min(std::strlen(message), error.size() - 1);
        std::memcpy(error.data(), message, length); error[length] = '\0';
        if (report) {
            reporting = true;
            try { report(error.data(), user); } catch (...) { /* diagnostic only */ }
            reporting = false;
        }
    }
    Handle get(Kind kind, Address address) {
        auto value = registry.find(kind, address);
        if (!value) throw std::logic_error("native scroll object lacks construction registration");
        return *value;
    }
    Registry::Scope& cast(std::uint64_t id) {
        // frame_count performs the owner-thread check before vector access.
        registry.frame_count();
        if (casts.empty() || casts.back()->id != id) throw std::logic_error("native scroll frame is not current");
        return casts.back()->scope;
    }
    std::uint64_t token() {
        registry.frame_count();
        if (serial == UINT64_MAX) throw std::overflow_error("native scroll token exhausted");
        return serial++;
    }
    std::size_t sweep_witnesses() {
        return witnesses.sweep([&](Address key) {
            if (auto handle = registry.find(Kind::Action, key)) registry.destroyed(*handle);
        });
    }
};
static Kind kind(uint32_t value) {
    if (value > 3) throw std::invalid_argument("invalid native scroll object kind");
    return static_cast<Kind>(value);
}
// Engine-address lifetimes. CAIAction ownership is carried by value; an action
// address registration could never observe its inline end and would go stale.
static Kind address_kind(uint32_t value) {
    const auto result = kind(value);
    if (result == Kind::Action) throw std::invalid_argument("CAIAction ownership is value-carried; actions have no address lifetime");
    return result;
}
static Selector selector(uint32_t value) {
    if (value > 6) throw std::invalid_argument("invalid native scroll selector");
    return static_cast<Selector>(value);
}
static ResRef resref(const char* value) {
    if (!value) throw std::invalid_argument("null native resref");
    std::size_t size = 0;
    // Engine CResRef is exactly eight bytes and may have no terminator. Never
    // inspect value[8]. A shorter NUL-terminated caller string is also accepted.
    while (size < 8 && value[size]) ++size;
    if (!size) throw std::invalid_argument("empty native resref");
    return ResRef::from(std::string(value, size));
}
template<class F> static int guarded(CBMS_Runtime* runtime, F&& callback) noexcept {
    if (!runtime) return -1;
    // Do not race the error buffer or call an engine-thread reporter from a
    // foreign thread. LastError exposes this violation; only the process-wide
    // latch changes, and it disables every later override.
    if (!runtime->registry.on_owner_thread()) { foreign_entry.store(true); return -1; }
    try { runtime->registry.frame_count(); return callback(); }
    catch (const std::exception& error) { runtime->failure(error.what()); }
    catch (...) { runtime->failure("unknown native scroll error"); }
    return -1;
}
static int output(std::optional<unsigned> replacement, uint32_t* level) {
    if (!level) throw std::invalid_argument("null native level output");
    if (!replacement) return 0; // leave caller's native level untouched
    *level = *replacement;
    return 1;
}
int CBMS_BindDecodeModules(uintptr_t game, uintptr_t eeex, CBMS_DecodeFunctions* output, char* text, uint32_t capacity) {
    if (!output || !text || capacity < 2) return 0;
    auto diagnostic = [&](const char* value) {
        const auto n = (std::min)(std::strlen(value), static_cast<std::size_t>(capacity-1));
        std::memcpy(text, value, n); text[n] = 0;
    };
    try {
#ifdef _WIN32
        std::string message;
        const auto result = cbm::scroll::binding::bind_decode(game, eeex, message);
        *output = result; diagnostic(message.c_str()); return 1;
#else
        (void)game; (void)eeex;
        diagnostic("decoder carrier binding requires the reviewed Windows x64 ABI");
#endif
    } catch (const std::exception& error) { diagnostic(error.what()); }
    catch (...) { diagnostic("unexpected decoder carrier certification failure"); }
    return 0;
}

int CBMS_BindMarshalModule(uintptr_t game, uintptr_t* entry, char* text, uint32_t capacity) {
    if(!entry||!text||capacity<2) return 0;
    auto diagnostic=[&](const char* value) {const auto n=(std::min)(std::strlen(value),static_cast<std::size_t>(capacity-1));std::memcpy(text,value,n);text[n]=0;};
    try {
#ifdef _WIN32
        std::string message;const auto result=cbm::scroll::binding::bind_marshal(game,message);
        *entry=result;diagnostic(message.c_str());return 1;
#else
        (void)game;diagnostic("native Marshal binding requires Windows x64");
#endif
    } catch(const std::exception& error) {diagnostic(error.what());} catch(...) {diagnostic("native Marshal certification failed");}
    return 0;
}
int CBMS_BindLifecycleModules(uintptr_t game,uintptr_t eeex,CBMS_LifecycleFunctions* output,char* text,uint32_t capacity) {
    return CBMS_BindLifecycleModulesChained(game,eeex,output,nullptr,nullptr,nullptr,text,capacity);
}
int CBMS_BindLifecycleModulesChained(uintptr_t game,uintptr_t eeex,CBMS_LifecycleFunctions* output,
    CBMS_BankActorQuery query,void* user,CBMS_BankActorChain* chain,char* text,uint32_t capacity) {
    if(!output||!text||capacity<2) return 0;
    auto diagnostic=[&](const char* value) {const auto n=(std::min)(std::strlen(value),static_cast<std::size_t>(capacity-1));std::memcpy(text,value,n);text[n]=0;};
    try {
#ifdef _WIN32
        CBMS_BankActorChain accepted{};
        std::string message;const auto result=cbm::scroll::binding::bind_lifecycle(game,eeex,message,query,user,chain?&accepted:nullptr);
        if(chain)*chain=accepted;
        *output=result;diagnostic(message.c_str());return 1;
#else
        (void)game;(void)eeex;(void)query;(void)user;(void)chain;diagnostic("native lifecycle binding requires Windows x64");
#endif
    } catch(const std::exception& error) {diagnostic(error.what());} catch(...) {diagnostic("native lifecycle certification failed");}
    return 0;
}

int CBMS_BindModule(uintptr_t module, CBMS_NativeFunctions* functions, char* diagnostic, uint32_t capacity) {
    auto message = [&](const char* value) {
        if (diagnostic && capacity) {
            const auto count = (std::min)(std::strlen(value), static_cast<std::size_t>(capacity - 1));
            std::memcpy(diagnostic, value, count); diagnostic[count] = '\0';
        }
    };
    if (!functions || !diagnostic || capacity < 2) { message("binding requires function output and diagnostic buffer"); return 0; }
    try {
#ifdef _WIN32
        std::string detail;
        const auto result = cbm::scroll::binding::bind(module, detail);
        *functions = result; message(detail.c_str()); return 1;
#else
        (void)module;
        message("mapped native provider binding requires reviewed Windows x64 ABI"); return 0;
#endif
    } catch (const std::exception& error) { message(error.what()); }
    catch (...) { message("unexpected native provider certification failure"); }
    return 0;
}
int CBMS_BindCurrent(CBMS_NativeFunctions* functions, char* diagnostic, uint32_t capacity) {
#ifdef _WIN32
    return CBMS_BindModule(reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr)), functions, diagnostic, capacity);
#else
    return CBMS_BindModule(0, functions, diagnostic, capacity);
#endif
}

CBMS_Runtime* CBMS_Create(CBMS_Resolve resolve, CBMS_Report report, void* user) {
    if (!resolve) return nullptr;
    try { return new CBMS_Runtime(resolve, report, user); } catch (...) { return nullptr; }
}
CBMS_Runtime* CBMS_CreateNative(const CBMS_NativeFunctions* functions, CBMS_Report report, void* user) {
    if (!functions) return nullptr;
    try {
        auto runtime = std::make_unique<CBMS_Runtime>(nullptr, report, user);
        runtime->native_provider.emplace(NativeReaderFunctions{
            functions->lookup, functions->active_inactive, functions->class_level,
            functions->maximum_level, functions->mage, functions->priest,
            functions->caster_type, functions->caster_level});
        return runtime.release();
    } catch (...) { return nullptr; }
}
int CBMS_Destroy(CBMS_Runtime* runtime) {
    const auto result = guarded(runtime, [&] {
        if (runtime->reporting)
            throw std::logic_error("cannot destroy native scroll runtime inside its reporter");
        if (!runtime->uses.empty() || !runtime->casts.empty() || !runtime->captured.empty() || runtime->sweep_witnesses() ||
            runtime->registry.owned_carriers() || !runtime->effect_exports.empty() || !runtime->effect_imports.empty())
            throw std::logic_error("cannot destroy native scroll runtime with pending contexts");
        runtime->witnesses.audit(); // every retired block, not one batch
        return 1;
    });
    if (result == 1) delete runtime;
    return result;
}
const char* CBMS_LastError(CBMS_Runtime* runtime) {
    if (!runtime) return "null runtime";
    if (!runtime->registry.on_owner_thread()) return "native scroll callback on another thread";
    return runtime->error.data();
}
int CBMS_Construct(CBMS_Runtime* runtime, uint32_t type, uintptr_t object) {
    return guarded(runtime, [&] { runtime->registry.born(address_kind(type), object); return 1; });
}
int CBMS_Destruct(CBMS_Runtime* runtime, uint32_t type, uintptr_t object) {
    return guarded(runtime, [&] { runtime->registry.destroyed(runtime->get(address_kind(type), object)); return 1; });
}
int CBMS_ActorUUID(CBMS_Runtime* runtime, uintptr_t reader, uint64_t uuid) {
    return guarded(runtime, [&] { runtime->registry.actor_uuid(runtime->get(Kind::Actor, reader), uuid); return 1; });
}
int CBMS_ActorObserved(CBMS_Runtime* runtime, uintptr_t actor, uint64_t uuid) {
    return guarded(runtime, [&] {
        auto handle = runtime->registry.find(Kind::Actor, actor);
        if (!handle) handle = runtime->registry.born(Kind::Actor, actor);
        if (uuid) runtime->registry.actor_uuid(*handle, uuid);
        return 1;
    });
}
int CBMS_ActorIsObserved(CBMS_Runtime* runtime,uintptr_t actor) {
    return guarded(runtime,[&] {return runtime->registry.find(Kind::Actor,actor)?1:0;});
}
int CBMS_CarrierIsOwned(CBMS_Runtime* runtime,uint32_t type,uintptr_t object) {
    return guarded(runtime,[&] {
        const auto found=runtime->registry.find(kind(type),object);
        return found&&runtime->registry.context(*found)?1:0;
    });
}
int CBMS_PrepareEffectExport(CBMS_Runtime* runtime, uintptr_t actor, uintptr_t list, uint32_t version, uint32_t permanent, uint32_t skip_equipped) {
    return guarded(runtime, [&] {
        runtime->get(Kind::Actor, actor);
        if (!list || version != 1 || permanent > 1 || skip_equipped > 1 || runtime->effect_exports.contains(actor))
            throw std::logic_error("unsupported/nested native effect export");
        // Pinned CTypedPtrList layout, proven by both native Marshal bodies:
        // head+8, count+18h, CNode.next+0 / data+10h. Host supplies live objects.
        auto read_ptr = [](Address at) { Address value{}; std::memcpy(&value, reinterpret_cast<const void*>(at), sizeof value); return value; };
        std::uint32_t count{}; std::memcpy(&count, reinterpret_cast<const void*>(list + 0x18), sizeof count);
        Address node = read_ptr(list + 8);
        EffectExport capture(runtime->registry, 1);
        std::vector<std::byte> wire;
        std::unordered_map<Address, bool> seen;
        for (std::uint32_t i = 0; i < count; ++i) {
            if (!node || !seen.emplace(node, true).second) throw std::logic_error("effect export list count/cycle mismatch");
            const auto effect = read_ptr(node + 0x10);
            if (!effect) throw std::logic_error("null native effect in export list");
            std::uint32_t timing{}; std::memcpy(&timing, reinterpret_cast<const void*>(effect + 0x24), sizeof timing);
            if ((!permanent || timing == 9) && (!skip_equipped || timing != 2)) {
                auto handle = runtime->registry.find(Kind::Effect, effect);
                if (!handle) handle = runtime->registry.born(Kind::Effect, effect);
                const auto record = std::span(reinterpret_cast<const std::byte*>(effect + 8), std::size_t{0x108});
                capture.emitted(*handle, 1 + wire.size(), record);
                wire.insert(wire.end(), record.begin(), record.end());
            }
            node = read_ptr(node);
        }
        if (node) throw std::logic_error("effect export list exceeds declared count");
        auto saved = capture.finish(wire);
        std::string text;
        if (std::any_of(saved.rows.begin(), saved.rows.end(), [](const auto& row) { return row.context.has_value(); }))
            text = archive_text(saved);
        runtime->effect_exports.emplace(actor, CBMS_Runtime::EffectSave{std::move(saved), std::move(text)});
        return 1;
    });
}
const char* CBMS_EffectExportText(CBMS_Runtime* runtime, uintptr_t actor) {
    const char* text = nullptr;
    guarded(runtime, [&] { text = runtime->effect_exports.at(actor).text.c_str(); return 1; });
    return text;
}
int CBMS_ValidateEffectExport(CBMS_Runtime* runtime, uintptr_t actor, const void* bytes, uint32_t size) {
    return guarded(runtime, [&] {
        const auto& saved = runtime->effect_exports.at(actor).archive;
        const auto length = saved.rows.size() * 0x108;
        if (length > size || (size && !bytes)) throw std::logic_error("native saved effect prefix truncated");
        const auto* data = static_cast<const std::byte*>(bytes);
        for (std::size_t i = 0; i < saved.rows.size(); ++i)
            if (std::memcmp(saved.rows[i].wire.data(), data + i * 0x108, 0x108) != 0)
                throw std::logic_error("native saved effect prefix differs from prepared ownership envelope");
        runtime->effect_exports.erase(actor);
        return 1;
    });
}
int CBMS_BeginEffectImport(CBMS_Runtime* runtime, uintptr_t actor) {
    return guarded(runtime, [&] {
        runtime->get(Kind::Actor, actor);
        if (runtime->effect_imports.contains(actor)) throw std::logic_error("nested native effect import");
        runtime->effect_imports.emplace(actor, std::make_unique<CBMS_Runtime::EffectLoad>(CBMS_Runtime::EffectLoad{EffectImport(runtime->registry), {}, 0}));
        return 1;
    });
}
int CBMS_ObserveEffectDecoded(CBMS_Runtime* runtime, uintptr_t actor, uintptr_t effect, const void* raw) {
    return guarded(runtime, [&] {
        if (!effect || !raw) throw std::logic_error("null decoded effect/record");
        auto& load = *runtime->effect_imports.at(actor);
        if (load.failed) throw std::logic_error("effect import is failed; cancel operation before rollback");
        load.failed = true;
        auto handle = runtime->registry.find(Kind::Effect, effect);
        if (!handle) handle = runtime->registry.born(Kind::Effect, effect);
        load.importer.decoded(load.next, *handle, std::span(static_cast<const std::byte*>(raw), std::size_t{0x108}));
        ++load.next;
        load.failed = false;
        return 1;
    });
}
int CBMS_StageEffectImportText(CBMS_Runtime* runtime, uintptr_t actor, const char* text, uint32_t length) {
    return guarded(runtime, [&] {
        if (!text) throw std::logic_error("null effect envelope");
        auto& load = *runtime->effect_imports.at(actor);
        if (load.failed) throw std::logic_error("effect import is failed; retain envelope and cancel operation");
        load.failed = true;
        if (load.archive) throw std::logic_error("duplicate actor effect envelope");
        load.archive = read_archive_text(std::string_view(text, length));
        load.failed = false;
        return 1;
    });
}
int CBMS_FinishEffectImport(CBMS_Runtime* runtime, uintptr_t actor, char* dropped, uint32_t capacity) {
    return guarded(runtime, [&] {
        if (!dropped || capacity < 2) throw std::invalid_argument("effect import needs a drop reason buffer");
        auto& load = *runtime->effect_imports.at(actor);
        if (load.failed) throw std::logic_error("cannot finish rejected actor effect envelope");
        // A refused restore is final: only cancellation follows, never a retry
        // that could read differently once overrides are off.
        load.failed = true;
        std::optional<std::string> stale;
        if (load.archive) stale = load.importer.restore(*load.archive);
        runtime->effect_imports.erase(actor);
        dropped[0] = '\0';
        if (!stale) return 1;
        // Only this actor's outdated envelope goes; nothing is disabled.
        const auto n = (std::min)(stale->size(), static_cast<std::size_t>(capacity - 1));
        std::memcpy(dropped, stale->data(), n); dropped[n] = '\0';
        return 2;
    });
}
int CBMS_AbortEffectExport(CBMS_Runtime* runtime, uintptr_t actor) {
    return guarded(runtime, [&] {
        if (!runtime->effect_exports.erase(actor)) throw std::logic_error("no effect export to abort");
        return 1;
    });
}
int CBMS_AbortEffectImport(CBMS_Runtime* runtime, uintptr_t actor) {
    return guarded(runtime, [&] {
        if (!runtime->effect_imports.erase(actor)) throw std::logic_error("no effect import to abort");
        return 1;
    });
}
int CBMS_ItemBegin(CBMS_Runtime* runtime, uintptr_t reader, const char* item, uint32_t ability, uint32_t policy, uint64_t* use) {
    return guarded(runtime, [&] {
        if (!use || policy > 2) throw std::invalid_argument("invalid item policy/output");
        auto origin = runtime->registry.begin_item(runtime->get(Kind::Actor, reader), resref(item), ability, static_cast<ItemPolicy>(policy));
        auto id = runtime->token(); runtime->uses.emplace(id, std::move(origin)); *use = id; return 1;
    });
}
int CBMS_ItemChild(CBMS_Runtime* runtime, uint64_t use, uintptr_t effect, uint32_t index) {
    return guarded(runtime, [&] { runtime->registry.item_child(runtime->get(Kind::Effect, effect), runtime->uses.at(use), index); return 1; });
}
int CBMS_ItemRootObserved(CBMS_Runtime* runtime,uint64_t use,uintptr_t effect,uint32_t index) {
    return guarded(runtime,[&] {
        auto found=runtime->registry.find(Kind::Effect,effect);
        if(found && runtime->registry.context(*found)) throw std::logic_error("decoded item root already has owned ancestry");
        const auto& origin=runtime->uses.at(use);
        if(!found) found=runtime->registry.born(Kind::Effect,effect);
        runtime->registry.item_child(*found,origin,index);
        return 1;
    });
}
int CBMS_ItemEnd(CBMS_Runtime* runtime, uint64_t use) {
    return guarded(runtime, [&] { if (!runtime->uses.erase(use)) throw std::logic_error("unknown item-use scope"); return 1; });
}
int CBMS_Copy(CBMS_Runtime* runtime, uint32_t type, uintptr_t source, uintptr_t destination) {
    return guarded(runtime, [&] { runtime->registry.copy(runtime->get(address_kind(type), source), runtime->get(address_kind(type), destination)); return 1; });
}
int CBMS_StampActionWitness(CBMS_Runtime* runtime, uintptr_t effect, uint32_t opcode, uint32_t mode, uint32_t special, uintptr_t field, uintptr_t empty) {
    return guarded(runtime, [&] {
        if (runtime->registry.disabled()) return 0; // the field keeps the native sentinel
        const auto path = route(opcode, mode, special);
        if (path.direct || path.carrier != Kind::Action) throw std::invalid_argument("action witness needs a queued action route");
        const auto source = runtime->get(Kind::Effect, effect);
        if (!runtime->registry.context(source)) throw std::logic_error("unowned dispatcher cannot stamp an action witness");
        runtime->sweep_witnesses();
        runtime->witnesses.stamp(field, empty, [&](Address key) {
            const auto carrier = runtime->registry.born(Kind::Action, key);
            try { runtime->registry.dispatch(source, carrier, path.selector); }
            catch (...) { runtime->registry.destroyed(carrier); throw; }
        });
        return 1;
    });
}
int CBMS_ActionWitnessCarrier(CBMS_Runtime* runtime, uintptr_t value, uintptr_t* carrier) {
    return guarded(runtime, [&] {
        if (!carrier) throw std::invalid_argument("null action witness output");
        if (!runtime->witnesses.contains(value)) return 0;
        const auto found = runtime->registry.find(Kind::Action, value);
        if (!found || !runtime->registry.context(*found)) return 0;
        *carrier = value;
        return 1;
    });
}
int CBMS_SweepActionWitnesses(CBMS_Runtime* runtime) {
    return guarded(runtime, [&] { return static_cast<int>(runtime->sweep_witnesses()); });
}
int CBMS_EffectCopied(CBMS_Runtime* runtime,uintptr_t source,uintptr_t destination) {
    return guarded(runtime,[&] {
        if(!source||!destination) throw std::invalid_argument("null native live-effect copy");
        auto from=runtime->registry.find(Kind::Effect,source),to=runtime->registry.find(Kind::Effect,destination);
        if(!from) from=runtime->registry.born(Kind::Effect,source);
        if(!to) to=source==destination?from:std::optional<Handle>(runtime->registry.born(Kind::Effect,destination));
        runtime->registry.copy(*from,*to);return 1;
    });
}
int CBMS_DestructObserved(CBMS_Runtime* runtime,uint32_t type,uintptr_t object) {
    return guarded(runtime,[&] {
        if(!object) throw std::invalid_argument("null native destruction event");
        if(auto handle=runtime->registry.find(address_kind(type),object)) runtime->registry.destroyed(*handle);
        return 1;
    });
}
int CBMS_Dispatch(CBMS_Runtime* runtime, uintptr_t effect, uint32_t opcode, uint32_t mode, uint32_t special, uint32_t carrier_kind, uintptr_t carrier) {
    return guarded(runtime, [&] {
        auto path = route(opcode, mode, special);
        if (path.direct || path.carrier != address_kind(carrier_kind)) throw std::invalid_argument("queued route mismatch");
        runtime->registry.dispatch(runtime->get(Kind::Effect, effect), runtime->get(address_kind(carrier_kind), carrier), path.selector);
        return 1;
    });
}
int CBMS_BeginCast(CBMS_Runtime* runtime, uint32_t carrier_kind, uintptr_t carrier, uint32_t path, uintptr_t spell_instance, const char* spell, uint32_t type, int source, int target, int x, int y, uint64_t* frame) {
    return guarded(runtime, [&] {
        if (!frame || type > 3) throw std::invalid_argument("invalid spell type/frame output");
        std::optional<Handle> owner;
        if (carrier) owner = runtime->get(kind(carrier_kind), carrier);
        const auto id = runtime->token();
        auto scope = runtime->registry.enter(owner, {selector(path), spell_instance, resref(spell), static_cast<SpellType>(type), {source, target, x, y}});
        auto active = std::make_unique<CBMS_Runtime::Active>(CBMS_Runtime::Active{id, std::move(scope)});
        runtime->casts.push_back(std::move(active)); *frame = id; return 1;
    });
}
int CBMS_CaptureCastOwner(CBMS_Runtime* runtime,uint32_t carrier_kind,uintptr_t carrier,uint32_t path,uint64_t* capture) {
    return guarded(runtime,[&]{
        if(!capture)throw std::invalid_argument("null cast capture output");
        const auto route=selector(path);std::optional<Handle> owner;
        if(carrier)owner=runtime->get(kind(carrier_kind),carrier);
        auto value=runtime->registry.capture(owner,route);const auto id=runtime->token();const bool owned=value.has_value();
        runtime->captured.emplace(id,CBMS_Runtime::Captured{route,std::move(value)});*capture=id;return owned?1:0;
    });
}
int CBMS_ContinueCastOwner(CBMS_Runtime* runtime,uint64_t parent,uint32_t path,uint64_t* capture) {
    return guarded(runtime,[&]{
        if(!capture)throw std::invalid_argument("null cast continuation output");
        const auto found=runtime->captured.find(parent);const auto route=selector(path);
        if(found==runtime->captured.end()||!((found->second.selector==Selector::Spell&&route==Selector::Fire)||
            (found->second.selector==Selector::SpellPoint&&route==Selector::FirePoint)))
            throw std::logic_error("unsupported native extra-target cast continuation");
        auto value=runtime->registry.disabled()?std::nullopt:found->second.context;
        if(value)value->pending_selector.reset();const auto id=runtime->token();const bool owned=value.has_value();
        runtime->captured.emplace(id,CBMS_Runtime::Captured{route,std::move(value)});*capture=id;return owned?1:0;
    });
}
int CBMS_BeginCapturedCast(CBMS_Runtime* runtime,uint64_t capture,uintptr_t spell_instance,const char* spell,uint32_t type,uint64_t* frame) {
    return guarded(runtime,[&]{
        if(!frame||type>3)throw std::invalid_argument("invalid captured spell/frame output");
        const auto found=runtime->captured.find(capture);if(found==runtime->captured.end())throw std::logic_error("unknown native cast capture");
        const auto id=runtime->token();auto scope=runtime->registry.enter_captured(found->second.context,
            {found->second.selector,spell_instance,resref(spell),static_cast<SpellType>(type),{}});
        auto active=std::make_unique<CBMS_Runtime::Active>(CBMS_Runtime::Active{id,std::move(scope)});
        runtime->casts.push_back(std::move(active));*frame=id;return 1;
    });
}
int CBMS_ReleaseCastOwner(CBMS_Runtime* runtime,uint64_t capture) {
    return guarded(runtime,[&]{if(runtime->captured.erase(capture)!=1)throw std::logic_error("unknown cast capture release");return 1;});
}
int CBMS_SpellChildObserved(CBMS_Runtime* runtime,uint64_t frame,uintptr_t spell,uintptr_t child,uint32_t* level) {
    return guarded(runtime,[&]{
        if(!level||!child)throw std::invalid_argument("null observed spell child/output");
        auto target=runtime->registry.find(Kind::Effect,child);
        if(!target)target=runtime->registry.born(Kind::Effect,child);
        else if(runtime->registry.context(*target))throw std::logic_error("native spell child already owns a context");
        return output(runtime->cast(frame).child(*target,spell),level);
    });
}
int CBMS_Select(CBMS_Runtime* runtime, uint64_t frame, uint32_t path, uintptr_t spell_instance, uint32_t* level) {
    return guarded(runtime, [&] {
        if (!level) throw std::invalid_argument("null native level output");
        if (std::find(runtime->resolving.begin(), runtime->resolving.end(), frame) != runtime->resolving.end())
            throw std::logic_error("recursive selection on the same native scroll frame");
        runtime->resolving.push_back(frame);
        struct Selecting {
            CBMS_Runtime* runtime;
            ~Selecting() { runtime->resolving.pop_back(); }
        } selecting{runtime};
        auto replacement = runtime->cast(frame).select(selector(path), spell_instance, [&](Handle reader, const CastRequest& cast) {
            if (runtime->native_provider)
                return runtime->native_provider->resolve(reinterpret_cast<void*>(reader.address),
                    reinterpret_cast<void*>(cast.spell_instance), cast.type).stats;
            CBMS_Stats raw{};
            if (runtime->resolve(reader.address, reader.generation, cast.spell_instance, static_cast<uint32_t>(cast.type), &raw, runtime->user) != 1)
                throw std::logic_error("active reader capability provider could not resolve this cast");
            // The provider must validate the actual installed helper, but no
            // active-class snapshot is needed when its level stays native.
            if (cast.type == SpellType::PreserveNative) return ReaderStats{};
            if (raw.count == 0 || raw.count > 3 || raw.arcane_state > 2 || raw.divine_state > 2)
                throw std::invalid_argument("invalid reader capability snapshot");
            ReaderStats value;
            for (unsigned i = 0; i < raw.count; ++i) {
                if (raw.active[i] > 1) throw std::invalid_argument("invalid active-class marker");
                value.classes.push_back({raw.level[i], raw.active[i] == 1});
            }
            value.arcane = {static_cast<Capability>(raw.arcane_state), raw.arcane_level};
            value.divine = {static_cast<Capability>(raw.divine_state), raw.divine_level};
            return value;
        });
        return output(replacement, level);
    });
}
int CBMS_SpellChild(CBMS_Runtime* runtime, uint64_t frame, uintptr_t spell_instance, uintptr_t child, uint32_t* level) {
    return guarded(runtime, [&] {
        if (!level) throw std::invalid_argument("null child level output");
        return output(runtime->cast(frame).child(runtime->get(Kind::Effect, child), spell_instance), level);
    });
}
int CBMS_Linked177(CBMS_Runtime* runtime, uintptr_t parent, uintptr_t child, uint32_t* level) {
    return guarded(runtime, [&] {
        if (!level) throw std::invalid_argument("null linked child level output");
        auto destination = runtime->get(Kind::Effect, child);
        runtime->registry.linked177(runtime->get(Kind::Effect, parent), destination);
        auto value = runtime->registry.context(destination);
        return output(value ? value->applied_level : std::nullopt, level);
    });
}
int CBMS_Linked177Observed(CBMS_Runtime* runtime,uintptr_t parent,uintptr_t child,uint32_t* level) {
    return guarded(runtime,[&]{
        if(!child||!level)throw std::invalid_argument("null linked effect/output");
        auto destination=runtime->registry.find(Kind::Effect,child);
        if(!destination)destination=runtime->registry.born(Kind::Effect,child);
        else if(runtime->registry.context(*destination))throw std::logic_error("decoded linked effect already owns context");
        runtime->registry.linked177(runtime->get(Kind::Effect,parent),*destination);
        const auto value=runtime->registry.context(*destination);return output(value?value->applied_level:std::nullopt,level);
    });
}
int CBMS_EndCast(CBMS_Runtime* runtime, uint64_t frame) {
    return guarded(runtime, [&] {
        if (std::find(runtime->resolving.begin(), runtime->resolving.end(), frame) != runtime->resolving.end())
            throw std::logic_error("cannot end a native scroll frame inside its level provider");
        runtime->cast(frame); runtime->casts.pop_back(); return 1;
    });
}
int CBMS_Quiescent(CBMS_Runtime* runtime) {
    return guarded(runtime, [&] { return runtime->uses.empty() && runtime->casts.empty() && runtime->captured.empty() &&
        !runtime->sweep_witnesses() && !runtime->registry.owned_carriers() && runtime->effect_exports.empty() &&
        runtime->effect_imports.empty() ? 1 : 0; });
}
void CBMS_DisableOverrides(CBMS_Runtime* runtime) { if (runtime) runtime->registry.disable(); }
int CBMS_OverridesDisabled(CBMS_Runtime* runtime) { return !runtime || runtime->registry.disabled() ? 1 : 0; }
void CBMS_ForeignEntry() { foreign_entry.store(true); }
int CBMS_ForeignEntrySeen() { return foreign_entry.load() ? 1 : 0; }
#ifdef CBMS_OFFLINE_HARNESS
int CBMS_TestLimitActionWitnesses(CBMS_Runtime* runtime, uint32_t total) {
    return guarded(runtime, [&] { runtime->witnesses.limit(total); return 1; });
}
#endif
