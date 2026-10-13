// Uninstalled native extension core. No game addresses, hooks, or disk I/O.
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <limits>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

namespace cbm::scroll {
using Address = std::uintptr_t;
enum class Kind { Actor, Effect, FireMessage, Action };
enum class Selector { EffectFire, Fire, FirePoint, Force, ForcePoint, Spell, SpellPoint };
enum class SpellType { Arcane, Divine, Unresolved, PreserveNative };
enum class Capability { Absent, Active, Unresolved };
enum class ItemPolicy { OrdinaryScroll, PreserveNative, Unresolved };

struct Handle {
    Kind kind{};
    Address address{};
    std::uint64_t generation{};
    bool operator==(const Handle&) const = default;
};
struct ResRef {
    std::array<char, 8> bytes{};
    static ResRef from(const std::string& value) {
        if (value.empty() || value.size() > 8) throw std::invalid_argument("invalid resref");
        ResRef out;
        std::copy(value.begin(), value.end(), out.bytes.begin());
        return out;
    }
    bool operator==(const ResRef&) const = default;
};
struct ClassLevel { unsigned level{}; bool active{}; };
struct CastingCapability { Capability state{Capability::Unresolved}; unsigned level{}; };
struct ReaderStats {
    std::vector<ClassLevel> classes;
    CastingCapability arcane, divine;
};

// Deliberately accepts resolved active capabilities, never infers them from a
// nonzero native query (which is also 1 for a non-caster), kit names, or books.
inline unsigned reader_level(const ReaderStats& stats, SpellType type) {
    if (type != SpellType::Arcane && type != SpellType::Divine)
        throw std::invalid_argument("spell type does not request a reader level");
    unsigned highest = 0;
    bool has_active = false;
    for (const auto& entry : stats.classes) {
        if (entry.active) { highest = std::max(highest, entry.level); has_active = true; }
    }
    if (!has_active) throw std::invalid_argument("no resolved active class entry");
    const auto& capability = type == SpellType::Arcane ? stats.arcane : stats.divine;
    if (capability.state == Capability::Unresolved) throw std::invalid_argument("unresolved active casting capability");
    if (capability.state == Capability::Active) {
        if (!capability.level || capability.level > 32767)
            throw std::invalid_argument("active caster level outside native signed-word range");
        return capability.level;
    }
    const auto fallback = std::max(1U, highest / 2U);
    if (fallback > 32767) throw std::invalid_argument("fallback exceeds native signed-word range");
    return fallback;
}

struct Origin {
    std::uint64_t use{};
    ResRef item;
    unsigned ability{};
    Handle reader;
    std::uint64_t reader_uuid{}; // save identity; never a raw pointer/object ID
};
struct Context {
    std::shared_ptr<const Origin> origin;
    unsigned root_effect{};
    unsigned depth{};
    std::optional<unsigned> applied_level;
    std::optional<Selector> pending_selector;
};
struct Destination { int native_source{}, native_target{}; int x{}, y{}; };
struct CastRequest {
    Selector selector{};
    Address spell_instance{};
    ResRef spell;
    SpellType type{SpellType::Unresolved};
    Destination destination; // observed only; never a replacement target
};

class Registry {
    struct Key {
        Kind kind; Address address;
        bool operator==(const Key&) const = default;
    };
    struct Hash {
        std::size_t operator()(const Key& key) const noexcept {
            return std::hash<Address>{}(key.address) ^ (static_cast<std::size_t>(key.kind) << 1);
        }
    };
    struct Entry { std::uint64_t generation; std::optional<Context> context; std::uint64_t actor_uuid{}; };
    struct Frame {
        std::uint64_t token;
        CastRequest request;
        std::optional<Context> context;
        std::optional<unsigned> level;
        bool selected{};
    };
    std::unordered_map<Key, Entry, Hash> entries_;
    std::vector<Frame> frames_;
    const std::thread::id owner_{std::this_thread::get_id()};
    std::uint64_t next_{1}; // never reset on load; old handles cannot become live
    static constexpr unsigned max_depth = 64;

    void thread_check() const {
        if (owner_ != std::this_thread::get_id()) throw std::logic_error("scroll callback on another thread");
    }
    std::uint64_t next_token() {
        if (next_ == std::numeric_limits<std::uint64_t>::max()) throw std::overflow_error("scroll token exhausted");
        return next_++;
    }
    Entry& entry(Handle handle) {
        thread_check();
        auto found = entries_.find({handle.kind, handle.address});
        if (found == entries_.end() || found->second.generation != handle.generation)
            throw std::logic_error("stale scroll carrier/reader handle");
        return found->second;
    }
    void set(Handle destination, std::optional<Context> value) { entry(destination).context = std::move(value); }
    Frame& frame(std::uint64_t token, Address spell) {
        thread_check();
        if (frames_.empty() || frames_.back().token != token || frames_.back().request.spell_instance != spell)
            throw std::logic_error("scroll frame or CSpell instance mismatch");
        return frames_.back();
    }
public:
    Registry() = default;
    Registry(const Registry&) = delete;
    Registry& operator=(const Registry&) = delete;
    bool on_owner_thread() const noexcept { return owner_ == std::this_thread::get_id(); }
    Handle born(Kind kind, Address address) {
        thread_check();
        if (!address) throw std::invalid_argument("null scroll carrier");
        Key key{kind, address};
        if (entries_.contains(key)) throw std::logic_error("scroll carrier born twice without destruction");
        const auto generation = next_token();
        entries_.emplace(key, Entry{generation, std::nullopt});
        return {kind, address, generation};
    }
    std::optional<Handle> find(Kind kind, Address address) {
        thread_check();
        auto found = entries_.find({kind, address});
        if (found == entries_.end()) return std::nullopt;
        return Handle{kind, address, found->second.generation};
    }
    void destroyed(Handle handle) {
        entry(handle);
        entries_.erase({handle.kind, handle.address});
    }
    std::optional<Context> context(Handle handle) { return entry(handle).context; }
    void actor_uuid(Handle reader, std::uint64_t uuid) {
        if (reader.kind != Kind::Actor || !uuid) throw std::invalid_argument("invalid original-reader UUID");
        auto& actor = entry(reader);
        if (actor.actor_uuid && actor.actor_uuid != uuid) throw std::logic_error("reader lifetime changed UUID");
        for (const auto& [key, value] : entries_)
            if (key.kind == Kind::Actor && key.address != reader.address && value.actor_uuid == uuid)
                throw std::logic_error("original-reader UUID resolves to multiple live actors");
        auto needs_rebind = [&](const auto& origin) {
            const auto prior = entries_.find({Kind::Actor, origin->reader.address});
            const bool prior_live = prior != entries_.end() && prior->second.generation == origin->reader.generation;
            return (origin->reader == reader && !origin->reader_uuid) ||
                (origin->reader_uuid == uuid && !prior_live);
        };
        // A cast may load an unrelated creature (e.g. a summoned actor). That
        // actor can acquire its UUID; only changing the origin of an active
        // frame would split its immutable ancestry and must be deferred.
        for (const auto& active : frames_)
            if (active.context && needs_rebind(active.context->origin))
                throw std::logic_error("cannot rebind an active cast's original-reader UUID");
        std::unordered_map<const Origin*, std::shared_ptr<const Origin>> replacements;
        for (const auto& [key, value] : entries_) {
            (void)key;
            if (!value.context) continue;
            const auto& origin = value.context->origin;
            if (needs_rebind(origin)) {
                if (!replacements.contains(origin.get())) {
                    auto updated = std::make_shared<Origin>(*origin);
                    updated->reader = reader; updated->reader_uuid = uuid;
                    replacements.emplace(origin.get(), std::move(updated));
                }
            }
        }
        // Allocation/validation completed before changing the live metadata.
        actor.actor_uuid = uuid;
        for (auto& [key, value] : entries_) {
            (void)key;
            if (value.context) {
                auto found = replacements.find(value.context->origin.get());
                if (found != replacements.end()) value.context->origin = found->second;
            }
        }
    }
    std::shared_ptr<const Origin> restored_origin(std::uint64_t uuid, ResRef item, unsigned ability) {
        thread_check();
        if (!uuid) throw std::invalid_argument("saved scroll has no original-reader UUID");
        Handle reader{Kind::Actor, 0, 0};
        for (const auto& [key, value] : entries_)
            if (key.kind == Kind::Actor && value.actor_uuid == uuid) reader = {Kind::Actor, key.address, value.generation};
        return std::make_shared<const Origin>(Origin{next_token(), item, ability, reader, uuid});
    }
    void restore_effect(Handle effect, Context value) {
        if (effect.kind != Kind::Effect || !value.origin || !value.origin->reader_uuid || value.depth > max_depth)
            throw std::invalid_argument("invalid saved effect context");
        set(effect, std::move(value));
    }
    std::shared_ptr<const Origin> begin_item(Handle reader, ResRef item, unsigned ability, ItemPolicy policy) {
        if (reader.kind != Kind::Actor) throw std::invalid_argument("scroll reader is not an actor");
        entry(reader);
        if (policy == ItemPolicy::Unresolved) throw std::invalid_argument("unresolved scroll ability policy");
        if (policy == ItemPolicy::PreserveNative) return {};
        return std::make_shared<const Origin>(Origin{next_token(), item, ability, reader, entry(reader).actor_uuid});
    }
    void item_child(Handle effect, const std::shared_ptr<const Origin>& origin, unsigned index) {
        if (effect.kind != Kind::Effect) throw std::invalid_argument("item child is not an effect");
        if (origin) entry(origin->reader);
        set(effect, origin ? std::optional<Context>{{origin, index, 0, {}, {}}} : std::nullopt);
    }
    // Both assignment and copy-construction must call this. Copying an unowned
    // action/effect clears the destination, including reusable current actions.
    void copy(Handle source, Handle destination) {
        if (source.kind != destination.kind || source.kind == Kind::Actor)
            throw std::invalid_argument("incompatible scroll carrier copy");
        auto value = context(source); // capture first: self-assignment is safe
        set(destination, std::move(value));
    }
    void dispatch(Handle effect, Handle carrier, Selector selector) {
        if (effect.kind != Kind::Effect || (carrier.kind != Kind::FireMessage && carrier.kind != Kind::Action))
            throw std::invalid_argument("invalid scroll dispatcher transfer");
        if ((carrier.kind == Kind::FireMessage && selector != Selector::Fire) ||
            (carrier.kind == Kind::Action && selector != Selector::Force && selector != Selector::ForcePoint &&
             selector != Selector::Spell && selector != Selector::SpellPoint))
            throw std::invalid_argument("native scroll route/carrier mismatch");
        auto value = context(effect);
        if (value) value->pending_selector = selector;
        set(carrier, std::move(value));
    }
    void linked177(Handle parent, Handle child) {
        if (parent.kind != Kind::Effect || child.kind != Kind::Effect)
            throw std::invalid_argument("invalid linked-effect transfer");
        auto value = context(parent);
        if (value) {
            if (value->depth >= max_depth) throw std::overflow_error("scroll linked-effect depth exceeded");
            ++value->depth;
            value->pending_selector.reset();
        }
        set(child, std::move(value));
    }

    class Scope {
        Registry* registry_;
        std::uint64_t token_;
        Address spell_;
        friend class Registry;
        Scope(Registry& registry, std::uint64_t token, Address spell) : registry_(&registry), token_(token), spell_(spell) {}
    public:
        Scope(const Scope&) = delete;
        Scope& operator=(const Scope&) = delete;
        Scope(Scope&& other) noexcept : registry_(other.registry_), token_(other.token_), spell_(other.spell_) { other.registry_ = nullptr; }
        ~Scope() noexcept {
            if (registry_) {
                // Broken LIFO unwinding cannot be repaired by borrowing another
                // frame. This is a programmer contract, exercised by the harness.
                if (registry_->owner_ != std::this_thread::get_id() || registry_->frames_.empty() || registry_->frames_.back().token != token_)
                    std::terminate();
                registry_->frames_.pop_back();
            }
        }
        template<class Resolve>
        std::optional<unsigned> select(Selector selector, Address spell, Resolve&& resolve) {
            auto& current = registry_->frame(token_, spell);
            if (current.request.selector != selector) throw std::logic_error("wrong native scroll selector");
            if (!current.context) return {};
            if (!current.selected) {
                if (!current.context->origin->reader.address)
                    throw std::logic_error("original scroll reader UUID is pending load binding");
                registry_->entry(current.context->origin->reader);
                // Resolve only this original reader, never the reflected native
                // source. Calls are synchronous; refs are reacquired afterwards
                // because a provider may enter another, properly masked cast.
                const auto request = current.request;
                const auto origin = current.context->origin;
                auto stats = resolve(origin->reader, request);
                const auto level = request.type == SpellType::PreserveNative ? std::nullopt
                    : std::optional<unsigned>(reader_level(stats, request.type));
                auto& after = registry_->frame(token_, spell);
                registry_->entry(origin->reader);
                after.level = level;
                after.selected = true;
            }
            return registry_->frame(token_, spell).level;
        }
        // Called only after CSpell::GetAbilityEffect in this matching CSpell
        // invocation. Return the sole native field the adapter may change.
        std::optional<unsigned> child(Handle effect, Address spell) {
            if (effect.kind != Kind::Effect) throw std::invalid_argument("spell child is not an effect");
            auto& current = registry_->frame(token_, spell);
            auto value = current.context;
            if (value) {
                if (!current.selected) throw std::logic_error("scroll child before ability selection");
                if (value->depth >= max_depth) throw std::overflow_error("scroll spell depth exceeded");
                ++value->depth;
                value->applied_level = current.level;
                value->pending_selector.reset();
            }
            const auto level = value ? value->applied_level : std::nullopt;
            registry_->set(effect, std::move(value));
            return level;
        }
        Address spell() const noexcept { return spell_; }
    };
    std::optional<Context> capture(std::optional<Handle> carrier, Selector selector) {
        thread_check();
        std::optional<Context> value;
        if (carrier) {
            if (carrier->kind == Kind::Actor) throw std::invalid_argument("actor is not a scroll cast carrier");
            value = context(*carrier);
            if (value && carrier->kind != Kind::Effect && value->pending_selector != selector)
                throw std::logic_error("queued scroll selector does not match its dispatcher");
        }
        return value;
    }
    Scope enter_captured(std::optional<Context> value, CastRequest request) {
        thread_check();
        if (!request.spell_instance) throw std::invalid_argument("null CSpell instance");
        const auto token = next_token();
        frames_.push_back({token, request, std::move(value), {}});
        return Scope(*this, token, request.spell_instance);
    }
    Scope enter(std::optional<Handle> carrier, CastRequest request) {
        return enter_captured(capture(carrier, request.selector), request);
    }
    // For a loading callback only. This INVALIDATES session metadata and old
    // handles. It is not serialization and cannot recover a pending scroll cast.
    void clear_session() {
        thread_check();
        if (!frames_.empty()) throw std::logic_error("cannot reset inside a scroll cast");
        entries_.clear();
    }
    std::size_t owned_carriers() const {
        thread_check();
        return static_cast<std::size_t>(std::count_if(entries_.begin(), entries_.end(), [](const auto& pair) { return pair.second.context.has_value(); }));
    }
    std::size_t frame_count() const { thread_check(); return frames_.size(); }
};
} // namespace cbm::scroll
