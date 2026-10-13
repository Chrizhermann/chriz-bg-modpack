#include "eeex_bridge.hpp"
#include "native_provider.hpp"
#include "native_api.h"
#include "effect_archive.hpp"
#include "effect_archive_text.hpp"
#include <cstring>
#include <functional>
#include <iostream>
#include <map>

using namespace cbm::scroll;
#define CHECK(x) do { if (!(x)) throw std::runtime_error("check failed: " #x); } while (false)
template<class F> void rejects(F&& callback) {
    bool failed = false;
    try { callback(); } catch (const std::exception&) { failed = true; }
    CHECK(failed);
}
ReaderStats stats(unsigned level, Capability arcane = Capability::Active, Capability divine = Capability::Absent) {
    return {{{level, true}}, {arcane, arcane == Capability::Active ? level : 0},
                              {divine, divine == Capability::Active ? level : 0}};
}
CastRequest request(Selector selector = Selector::Fire, Address spell = 0xD000, SpellType type = SpellType::Arcane) {
    return {selector, spell, ResRef::from("MODSPELL"), type, {101, 202, 17, 23}};
}
struct Fixture {
    Registry registry;
    Handle reader = registry.born(Kind::Actor, 0x1000);
    Handle effect = registry.born(Kind::Effect, 0x2000);
    std::shared_ptr<const Origin> origin = registry.begin_item(reader, ResRef::from("SCROLL01"), 3, ItemPolicy::OrdinaryScroll);
    Fixture() { registry.item_child(effect, origin, 7); }
};
// Gameplay fields deliberately placed in an alternate physical order. The
// adapter uses the generated engine field names, never this fixture's offsets.
struct NativeEffect {
    unsigned m_special = 0;
    std::array<unsigned char, 23> foreign{};
    int m_sourceId = 11, m_sourceTarget = 99;
    unsigned m_effectId = 146, m_casterLevel = 10, m_dWFlags = 1;
    int m_effectAmount = 777;
    ResRef m_res = ResRef::from("NESTED");
    unsigned charges_sentinel = 2, target_sentinel = 6;
};

void policy() {
    CHECK(reader_level(stats(19), SpellType::Arcane) == 19U);
    CHECK(reader_level(stats(19), SpellType::Divine) == 9U);
    CHECK(reader_level(stats(1, Capability::Absent), SpellType::Arcane) == 1U);
    CHECK(reader_level(stats(3, Capability::Absent), SpellType::Arcane) == 1U);
    CHECK(reader_level(stats(0, Capability::Absent), SpellType::Arcane) == 1U);
    auto zero = stats(0); zero.arcane.level = 1;
    CHECK(reader_level(zero, SpellType::Arcane) == 1U);
    ReaderStats multiclass{{{20, true}, {24, true}}, {Capability::Absent, 0}, {Capability::Absent, 0}};
    CHECK(reader_level(multiclass, SpellType::Arcane) == 12U);
    ReaderStats dormant{{{13, false}, {12, true}}, {Capability::Absent, 0}, {Capability::Absent, 0}};
    CHECK(reader_level(dormant, SpellType::Arcane) == 6U);
    dormant.classes[0].active = true; dormant.classes[1].level = 14;
    dormant.arcane = {Capability::Active, 13};
    CHECK(reader_level(dormant, SpellType::Arcane) == 13U);
    CHECK(reader_level(dormant, SpellType::Divine) == 7U);
    ReaderStats reduced{{{15, true}}, {Capability::Absent, 0}, {Capability::Active, 7}};
    CHECK(reader_level(reduced, SpellType::Divine) == 7U);
    reduced.divine.level = 21; // installed progression / casting bonus, not raw level
    CHECK(reader_level(reduced, SpellType::Divine) == 21U);
    rejects([&] { reader_level(reduced, SpellType::Unresolved); });
    reduced.divine.state = Capability::Unresolved;
    rejects([&] { reader_level(reduced, SpellType::Divine); });
    reduced.divine = {Capability::Active, 0};
    rejects([&] { reader_level(reduced, SpellType::Divine); });
    reduced.classes[0].active = false;
    rejects([&] { reader_level(reduced, SpellType::Arcane); });
}

void modes_and_selectors() {
    CHECK(spell_type(1) == SpellType::Arcane);
    CHECK(spell_type(2) == SpellType::Divine);
    CHECK(spell_type(0) == SpellType::Unresolved);
    CHECK(spell_type(4) == SpellType::PreserveNative);
    CHECK(spell_type(7) == SpellType::Unresolved);
    const std::array routes{
        route(146, 0, 0), route(146, 1, 0), route(146, 2, 0),
        route(148, 0, 0), route(148, 1, 0), route(148, 2, 0),
        route(146, 0, 1), route(148, 0, 1)};
    CHECK(routes[0].selector == Selector::Force && routes[1].selector == Selector::Fire);
    CHECK(routes[2].selector == Selector::EffectFire && routes[3].selector == Selector::ForcePoint);
    CHECK(routes[4].selector == Selector::FirePoint && routes[5].selector == Selector::FirePoint);
    CHECK(routes[6].selector == Selector::Spell && routes[7].selector == Selector::SpellPoint);
    std::map<Selector, bool> exercised;
    for (const auto& path : routes) {
        Fixture f;
        auto carrier = f.effect;
        if (!path.direct) {
            carrier = f.registry.born(path.carrier, 0x5000);
            f.registry.dispatch(f.effect, carrier, path.selector);
        }
        auto scope = f.registry.enter(carrier, request(path.selector));
        CHECK(scope.select(path.selector, scope.spell(), [&](Handle reader, const CastRequest& cast) {
            CHECK(reader == f.reader); CHECK(cast.destination.native_target == 202U);
            return stats(23);
        }) == 23U);
        auto child = f.registry.born(Kind::Effect, 0x6000);
        NativeEffect native;
        native.foreign.fill(0xB7);
        auto expected = native; expected.m_casterLevel = 23;
        spell_child(scope, child, scope.spell(), native);
        CHECK(std::memcmp(&native, &expected, sizeof native) == 0U);
        CHECK(f.registry.context(child)->origin == f.origin);
        exercised[path.selector] = true;
    }
    CHECK(exercised.size() == 7U);
    rejects([] { route(147, 0, 0); });
    rejects([] { route(146, 3, 0); });
}

void two_queued_readers() {
    Fixture f;
    auto second_reader = f.registry.born(Kind::Actor, 0x1100);
    auto second_effect = f.registry.born(Kind::Effect, 0x2100);
    auto second_origin = f.registry.begin_item(second_reader, ResRef::from("SCROLL02"), 0, ItemPolicy::OrdinaryScroll);
    f.registry.item_child(second_effect, second_origin, 4);
    auto a = f.registry.born(Kind::FireMessage, 0x3000);
    auto b = f.registry.born(Kind::FireMessage, 0x3100);
    NativeEffect native;
    queued_dispatch(f.registry, f.effect, native, a);
    queued_dispatch(f.registry, second_effect, native, b);
    f.registry.destroyed(f.effect); f.registry.destroyed(second_effect);
    // Native queue order and source lifetimes are independent of origin order.
    for (auto message : {b, a}) {
        auto cast = f.registry.enter(message, request());
        auto expected = message == a ? 6U : 21U;
        CHECK(cast.select(Selector::Fire, cast.spell(), [&](Handle reader, const CastRequest&) {
            return stats(reader == f.reader ? 6U : 21U);
        }) == expected);
        f.registry.destroyed(message); // frame retains origin through Run return
    }
    CHECK(f.registry.owned_carriers() == 0U);
}

void action_assignment_and_ticks() {
    Fixture f;
    auto embedded = f.registry.born(Kind::Action, 0x3000);
    auto queued = f.registry.born(Kind::Action, 0x4000);
    auto current = f.registry.born(Kind::Action, 0x5000);
    NativeEffect native; native.m_dWFlags = 0;
    queued_dispatch(f.registry, f.effect, native, embedded);
    f.registry.copy(embedded, queued); f.registry.copy(queued, current);
    f.registry.destroyed(embedded); f.registry.destroyed(queued); f.registry.destroyed(f.effect);
    f.registry.copy(current, current); // actual operator= can self-assign
    for (int tick = 0; tick < 3; ++tick) {
        auto cast = f.registry.enter(current, request(Selector::Force));
        CHECK(cast.select(Selector::Force, cast.spell(), [](Handle, const CastRequest&) { return stats(17); }) == 17U);
    }
    auto plain = f.registry.born(Kind::Action, 0x6000);
    f.registry.copy(plain, current);
    auto cast = f.registry.enter(current, request(Selector::Force));
    CHECK(!cast.select(Selector::Force, cast.spell(), [](Handle, const CastRequest&) -> ReaderStats { throw std::runtime_error("must not query unowned action"); }));
}

void reflection_and_linked177() {
    Fixture f;
    NativeEffect native;
    native.m_dWFlags = 2;
    native.m_sourceId = 900; native.m_sourceTarget = 900; // native reflection
    auto cast = direct_dispatch(f.registry, f.effect, native, request(Selector::EffectFire));
    CHECK(cast.select(Selector::EffectFire, cast.spell(), [&](Handle reader, const CastRequest&) { CHECK(reader == f.reader); return stats(8); }) == 8U);
    auto wrapper = f.registry.born(Kind::Effect, 0x3100);
    auto child = f.registry.born(Kind::Effect, 0x3200);
    spell_child(cast, wrapper, cast.spell(), native);
    auto expected = native;
    linked_child(f.registry, wrapper, child, native);
    CHECK(std::memcmp(&native, &expected, sizeof native) == 0U);
    CHECK(native.m_sourceId == 900 && native.m_sourceTarget == 900U);
    CHECK(f.registry.context(child)->origin->reader == f.reader);
    auto copy = f.registry.born(Kind::Effect, 0x3300);
    f.registry.copy(child, copy); f.registry.destroyed(child);
    CHECK(f.registry.context(copy)->applied_level == 8U);
}

void root177_and_ordinary_repeat() {
    Fixture f;
    NativeEffect native;
    native.m_effectId = 146;
    native.m_dWFlags = 2;
    auto child = f.registry.born(Kind::Effect, 0x3000);
    auto expected = native;
    linked_child(f.registry, f.effect, child, native);
    CHECK(std::memcmp(&native, &expected, sizeof native) == 0);
    CHECK(f.registry.context(child)->origin == f.origin);
    CHECK(!f.registry.context(child)->applied_level);
    // Repeated dispatches of the same resource are valid; there is no global
    // resref deduplication. Each receives its own level decision and frame.
    for (int index = 0; index < 2; ++index) {
        auto cast = direct_dispatch(f.registry, child, native, request(Selector::EffectFire));
        CHECK(cast.select(Selector::EffectFire, cast.spell(), [](Handle, const CastRequest&) { return stats(8); }) == 8U);
    }
}

void nested_and_unowned_masking() {
    Fixture f;
    auto outer = f.registry.enter(f.effect, request(Selector::EffectFire));
    CHECK(outer.select(Selector::EffectFire, outer.spell(), [](Handle, const CastRequest&) { return stats(12); }) == 12U);
    auto next = f.registry.born(Kind::Effect, 0x3000);
    CHECK(outer.child(next, outer.spell()) == 12U);
    {
        auto inner = f.registry.enter(next, request(Selector::FirePoint, 0xD100, SpellType::Divine));
        CHECK(inner.select(Selector::FirePoint, inner.spell(), [](Handle, const CastRequest&) { return stats(23); }) == 11U);
        rejects([&] { outer.child(next, outer.spell()); });
        {
            // Even the same CSpell pointer must not leak ownership to an
            // unrelated reentrant call. Every native entry creates a frame.
            auto unrelated = f.registry.enter({}, request(Selector::FirePoint, inner.spell()));
            CHECK(!unrelated.select(Selector::FirePoint, unrelated.spell(), [](Handle, const CastRequest&) -> ReaderStats { throw std::runtime_error("unowned query"); }));
            auto plain_child = f.registry.born(Kind::Effect, 0x4000);
            CHECK(!unrelated.child(plain_child, unrelated.spell()));
        }
        CHECK(inner.select(Selector::FirePoint, inner.spell(), [](Handle, const CastRequest&) -> ReaderStats { throw std::runtime_error("cached"); }) == 11U);
    }
    CHECK(outer.child(next, outer.spell()) == 12U);
}

void pointer_reuse_and_reader_loss() {
    Fixture f;
    auto message = f.registry.born(Kind::FireMessage, 0x3000);
    f.registry.dispatch(f.effect, message, Selector::Fire);
    f.registry.destroyed(f.reader);
    auto replacement = f.registry.born(Kind::Actor, f.reader.address);
    CHECK(replacement.generation != f.reader.generation);
    {
        auto cast = f.registry.enter(message, request());
        rejects([&] { cast.select(Selector::Fire, cast.spell(), [](Handle, const CastRequest&) { return stats(99); }); });
    }
    f.registry.destroyed(message);
    auto recycled = f.registry.born(Kind::FireMessage, message.address);
    rejects([&] { f.registry.destroyed(message); });
    CHECK(!f.registry.context(recycled));
}

void failure_unwind_and_reentrant_provider() {
    Fixture f;
    try {
        auto cast = f.registry.enter(f.effect, request(Selector::EffectFire));
        cast.select(Selector::EffectFire, cast.spell(), [&](Handle, const CastRequest&) -> ReaderStats {
            auto mask = f.registry.enter({}, request(Selector::Fire, 0xF000));
            throw std::runtime_error("provider failure");
        });
    } catch (const std::runtime_error&) {}
    CHECK(f.registry.frame_count() == 0U);
    auto cast = f.registry.enter(f.effect, request(Selector::EffectFire));
    CHECK(cast.select(Selector::EffectFire, cast.spell(), [&](Handle, const CastRequest&) {
        auto mask = f.registry.enter({}, request(Selector::Fire, 0xF000));
        return stats(15);
    }) == 15U);
    unsigned reports = 0;
    CHECK(!boundary([] { throw std::runtime_error("typed bridge failure"); }, [&](const char* text) noexcept { if (text && *text) ++reports; }));
    CHECK(reports == 1U);
}

void guards_and_unowned_preservation() {
    Fixture f;
    auto plain = f.registry.born(Kind::Effect, 0x3000);
    f.registry.copy(plain, f.effect);
    CHECK(!f.registry.context(f.effect));
    NativeEffect native;
    auto expected = native;
    auto cast = f.registry.enter(f.effect, request(Selector::EffectFire));
    spell_child(cast, plain, cast.spell(), native);
    CHECK(std::memcmp(&native, &expected, sizeof native) == 0U);
    rejects([&] { cast.child(plain, 0xBAD); });
    rejects([&] { cast.select(Selector::Spell, cast.spell(), [](Handle, const CastRequest&) { return stats(9); }); });
    rejects([&] { f.registry.clear_session(); });
    rejects([&] { f.registry.begin_item(f.reader, ResRef::from("SCROLL"), 1, ItemPolicy::Unresolved); });
    CHECK(!f.registry.begin_item(f.reader, ResRef::from("SCROLL"), 1, ItemPolicy::PreserveNative));
    rejects([&] { f.registry.born(Kind::Effect, plain.address); });
}

void depth_and_session_invalidation() {
    Fixture f;
    auto current = f.effect;
    for (unsigned depth = 0; depth < 64; ++depth) {
        auto child = f.registry.born(Kind::Effect, 0x3000 + depth * 0x100);
        f.registry.linked177(current, child);
        current = child;
    }
    auto overflow = f.registry.born(Kind::Effect, 0x9000);
    rejects([&] { f.registry.linked177(current, overflow); });
    CHECK(!f.registry.context(overflow));
    f.registry.clear_session();
    auto new_reader = f.registry.born(Kind::Actor, f.reader.address);
    CHECK(new_reader.generation != f.reader.generation);
    rejects([&] { f.registry.context(current); });
}

void route_and_child_order_guards() {
    Fixture f;
    auto message = f.registry.born(Kind::FireMessage, 0x3000);
    auto action = f.registry.born(Kind::Action, 0x4000);
    NativeEffect effect;
    rejects([&] { queued_dispatch(f.registry, f.effect, effect, action); });
    queued_dispatch(f.registry, f.effect, effect, message);
    rejects([&] { f.registry.enter(message, request(Selector::EffectFire)); });
    auto cast = f.registry.enter(message, request());
    auto child = f.registry.born(Kind::Effect, 0x5000);
    rejects([&] { cast.child(child, cast.spell()); });
    CHECK(!f.registry.context(child));
    rejects([&] { direct_dispatch(f.registry, f.effect, effect, request(Selector::Fire)); });
}

void thread_guard() {
    Fixture f;
    bool rejected = false;
    std::thread worker([&] {
        try { f.registry.find(Kind::Actor, f.reader.address); }
        catch (const std::logic_error&) { rejected = true; }
    });
    worker.join();
    CHECK(rejected);
}

struct ProviderDouble {
    std::array<std::byte, 0x5000> actor{};
    std::uint8_t new_class{1}, old_class{1}, new_level{12}, maximum{24};
    bool arcane{true}, divine{false}, lookup_ok{true}, same_reader{true};
    short type{1}, casting_level{19};
    unsigned level_calls{}, maximum_calls{}, caster_calls{};
    void* observed_stats{};
    static inline ProviderDouble* current{};
    ProviderDouble() {
        current = this;
        put<std::uint8_t>(0x3B, 19); // transformed/current class may differ
        put<std::uint8_t>(0x4B73, 1);
        put<std::int32_t>(0x4B74, 77);
    }
    template<class T> void put(std::size_t at, T value) { std::memcpy(actor.data() + at, &value, sizeof value); }
    static std::uint8_t lookup(std::int32_t id, void** out) {
        CHECK(id == 77);
        *out = current->same_reader ? current->actor.data() : nullptr;
        return current->lookup_ok ? 0 : 2;
    }
    static void classes(void* ai, std::uint8_t* next, std::uint8_t* old) {
        CHECK(ai == current->actor.data() + 0x4B68);
        *next = current->new_class; *old = current->old_class;
    }
    static std::uint8_t level(void* stats, std::uint8_t composite, std::uint8_t constituent) {
        CHECK(composite == 1 && constituent == current->new_class);
        ++current->level_calls; current->observed_stats = stats; return current->new_level;
    }
    static std::uint8_t maxlevel(void* stats, std::uint8_t composite) {
        CHECK(composite == 1);
        ++current->maximum_calls; current->observed_stats = stats; return current->maximum;
    }
    static int mage(void* screen, void* reader) { CHECK(!screen && reader == current->actor.data()); return current->arcane; }
    static int priest(void* screen, void* reader) { CHECK(!screen && reader == current->actor.data()); return current->divine; }
    static short castertype(void* spell) { CHECK(spell == reinterpret_cast<void*>(0xD000)); return current->type; }
    static short casterlevel(void* reader, void* spell, int wild) {
        CHECK(reader == current->actor.data() && spell == reinterpret_cast<void*>(0xD000) && wild == 1);
        ++current->caster_calls; return current->casting_level;
    }
    NativeReaderFunctions functions() { return {lookup, classes, level, maxlevel, mage, priest, castertype, casterlevel}; }
};

void native_provider_queries() {
    ProviderDouble fake;
    NativeReaderProvider provider(fake.functions());
    auto get = [&] { return provider.resolve(fake.actor.data(), reinterpret_cast<void*>(0xD000), SpellType::Arcane); };
    auto native = get();
    CHECK(reader_level(native.stats, SpellType::Arcane) == 19U);
    CHECK(native.current_class == 19 && native.start_class == 1 && !native.dual);
    CHECK(fake.maximum_calls == 1U && fake.level_calls == 0U);
    CHECK(fake.observed_stats == fake.actor.data() + 0x1DC8);
    fake.new_class = 4; fake.old_class = 1; fake.arcane = false;
    fake.put<std::uint32_t>(0x4EA4, 1);
    native = get();
    CHECK(native.dual && reader_level(native.stats, SpellType::Arcane) == 6U);
    CHECK(fake.level_calls == 1U && fake.caster_calls == 1U);
    CHECK(fake.observed_stats == fake.actor.data() + 0x1120);
    fake.new_level = 14; fake.arcane = true; fake.casting_level = 13;
    native = get();
    CHECK(reader_level(native.stats, SpellType::Arcane) == 13U);
    fake.type = 2; fake.divine = true; fake.casting_level = 7;
    native = provider.resolve(fake.actor.data(), reinterpret_cast<void*>(0xD000), SpellType::Divine);
    CHECK(reader_level(native.stats, SpellType::Divine) == 7U);
    rejects(get); // installed spell type changed, not a vanilla-ID assumption
    fake.type = 1; fake.lookup_ok = false; rejects(get);
    fake.lookup_ok = true; fake.same_reader = false; rejects(get);
    fake.same_reader = true; fake.new_level = 0; fake.arcane = false;
    CHECK(reader_level(get().stats, SpellType::Arcane) == 1U);
    fake.arcane = true;
    fake.new_level = 14; fake.casting_level = 0; rejects(get);
    fake.type = 4;
    const auto calls = fake.caster_calls;
    CHECK(provider.resolve(fake.actor.data(), reinterpret_cast<void*>(0xD000), SpellType::PreserveNative).stats.classes.empty());
    CHECK(fake.caster_calls == calls);
    rejects(get);
    // A native type0 result also signals missing resources. Resolve only a
    // present valid SPL header, never the bare zero return.
    std::array<std::byte, 16> spell{};
    std::array<std::byte, 0x70> resource{};
    std::array<std::byte, 0x72> header{};
    auto* resource_ptr = resource.data();
    auto* header_ptr = header.data();
    std::memcpy(spell.data(), &resource_ptr, sizeof resource_ptr);
    std::memcpy(resource.data() + 0x68, &header_ptr, sizeof header_ptr);
    std::memcpy(spell.data() + 8, "HELPER", 6);
    std::memcpy(header.data(), "SPL V1  ", 8);
    auto zero_functions = fake.functions();
    zero_functions.caster_type = +[](void*) -> short { return 0; };
    NativeReaderProvider zero_provider(zero_functions);
    auto zero = [&] { return zero_provider.resolve(fake.actor.data(), spell.data(), SpellType::PreserveNative); };
    CHECK(zero().stats.classes.empty());
    header[0] = std::byte{0}; rejects(zero); header[0] = std::byte{'S'};
    header[0x1C] = std::byte{1}; rejects(zero); header[0x1C] = std::byte{0};
    spell[8] = std::byte{0}; rejects(zero); spell[8] = std::byte{'H'};
    std::fill(resource.begin(), resource.end(), std::byte{0}); rejects(zero);
    auto functions = fake.functions(); functions.mage = nullptr;
    rejects([&] { NativeReaderProvider missing(functions); });
}

struct ReportingDouble {
    CBMS_Runtime* runtime{};
    unsigned calls{};
    bool same_message{}, nested_rejected{}, destruction_rejected{};
    static int resolve(uintptr_t, uint64_t, uintptr_t, uint32_t, CBMS_Stats*, void*) { return 0; }
    static void report(const char* message, void* user) {
        auto& state = *static_cast<ReportingDouble*>(user);
        ++state.calls;
        state.nested_rejected = CBMS_Construct(state.runtime, 99, 0x1000) == -1;
        state.destruction_rejected = CBMS_Destroy(state.runtime) == -1;
        state.same_message = std::strcmp(message, "invalid native scroll object kind") == 0 &&
            std::strcmp(CBMS_LastError(state.runtime), message) == 0;
        throw std::runtime_error("reporter failure must not cross callback boundary");
    }
};
void reporter_failure_is_contained() {
    ReportingDouble state;
    state.runtime = CBMS_Create(ReportingDouble::resolve, ReportingDouble::report, &state);
    CHECK(state.runtime);
    CHECK(CBMS_Construct(state.runtime, 99, 0x1000) == -1);
    CHECK(state.calls == 1U && state.nested_rejected && state.destruction_rejected && state.same_message);
    CHECK(std::strcmp(CBMS_LastError(state.runtime), "invalid native scroll object kind") == 0);
    CHECK(CBMS_Construct(state.runtime, 0, 0x1000) == 1);
    CHECK(CBMS_Destroy(state.runtime) == 1);
}

void effect_archive_identity_and_pending_reader() {
    Registry source;
    auto reader = source.born(Kind::Actor, 0x1000);
    source.actor_uuid(reader, 0x123456789ABCDEF0ULL);
    auto root = source.born(Kind::Effect, 0x2000);
    auto first = source.born(Kind::Effect, 0x2100);
    auto second = source.born(Kind::Effect, 0x2200);
    auto plain = source.born(Kind::Effect, 0x2300);
    auto origin = source.begin_item(reader, ResRef::from("SCROLL"), 3, ItemPolicy::OrdinaryScroll);
    source.item_child(root, origin, 7);
    {
        auto cast = source.enter(root, request());
        auto summoned = source.born(Kind::Actor, 0x1800);
        source.actor_uuid(summoned, 777); // unrelated creature load during cast
        source.actor_uuid(reader, 0x123456789ABCDEF0ULL); // stable binding is safe
        source.destroyed(summoned);
        CHECK(cast.select(Selector::Fire, 0xD000, [](Handle, const CastRequest&) { return stats(12); }) == 12U);
        CHECK(cast.child(first, 0xD000) == 12U);
    }
    source.item_child(root, origin, 8);
    {
        auto cast = source.enter(root, request());
        CHECK(cast.select(Selector::Fire, 0xD000, [](Handle, const CastRequest&) { return stats(12); }) == 12U);
        CHECK(cast.child(second, 0xD000) == 12U);
    }
    EffectWire wire{};
    const std::uint32_t level = 12;
    std::memcpy(wire.data() + 0xC0, &level, sizeof level);
    std::vector<std::byte> native_bytes;
    for (unsigned i = 0; i < 3; ++i) native_bytes.insert(native_bytes.end(), wire.begin(), wire.end());
    EffectExport exported(source, 0x9000);
    exported.emitted(first, 0x9000, wire);
    exported.emitted(plain, 0x9108, wire);
    exported.emitted(second, 0x9210, wire);
    auto saved = exported.finish(native_bytes);
    const auto encoded = archive_text(saved);
    CHECK(encoded.find('\0') == std::string::npos);
    auto roundtrip = read_archive_text(encoded);
    CHECK(roundtrip.rows[0].context == saved.rows[0].context && roundtrip.rows[2].wire == wire);
    CHECK(roundtrip.rows[0].context->reader_uuid == 0x123456789ABCDEF0ULL);
    for (auto invalid : {encoded.substr(0, encoded.size() - 2), encoded + "00", std::string("CBMSFX02:") + encoded.substr(9),
                         std::string("CBMSFX01:FFFFFFFF")})
        rejects([&] { read_archive_text(invalid); });
    CHECK(saved.rows[0].context->root_effect == 7 && saved.rows[2].context->root_effect == 8);
    CHECK(!saved.rows[1].context);
    CHECK(saved.rows[0].wire == saved.rows[2].wire); // identity is ordinal, not fingerprint
    native_bytes[0] = std::byte{1}; rejects([&] { exported.finish(native_bytes); }); native_bytes[0] = std::byte{0};

    Registry restored;
    auto a = restored.born(Kind::Effect, 0x3100), b = restored.born(Kind::Effect, 0x3200), c = restored.born(Kind::Effect, 0x3300);
    EffectImport imported(restored);
    imported.decoded(0, a, wire); imported.decoded(1, b, wire); imported.decoded(2, c, wire);
    auto altered = saved;
    altered.rows[2].wire[1] = std::byte{1};
    rejects([&] { imported.restore(altered); });
    CHECK(!restored.context(a) && !restored.context(c)); // atomic refusal
    altered = saved; altered.schema = 99;
    rejects([&] { imported.restore(altered); });
    CHECK(altered.schema == 99 && altered.rows.size() == 3); // caller retains unknown envelope
    imported.restore(saved);
    CHECK(restored.context(a)->origin == restored.context(c)->origin);
    CHECK(restored.context(a)->applied_level == 12U && !restored.context(b));
    CHECK(restored.context(a)->origin->reader.address == 0);
    auto linked = restored.born(Kind::Effect, 0x3400);
    restored.linked177(a, linked);
    CHECK(restored.context(linked)->applied_level == 12U);
    {
        auto pending = restored.enter(a, request());
        rejects([&] { pending.select(Selector::Fire, 0xD000, [](Handle, const CastRequest&) { return stats(99); }); });
    }
    auto original = restored.born(Kind::Actor, 0xABC0);
    restored.actor_uuid(original, 0x123456789ABCDEF0ULL);
    CHECK(restored.context(a)->origin->reader == original);
    CHECK(restored.context(linked)->origin->reader == original);
    {
        auto future = restored.enter(a, request(Selector::Fire, 0xD100, SpellType::Divine));
        CHECK(future.select(Selector::Fire, 0xD100, [&](Handle actual, const CastRequest&) {
            CHECK(actual == original); return stats(18, Capability::Absent, Capability::Active);
        }) == 18U); // next typed spell does not borrow the saved parent level12
    }
    auto impostor = restored.born(Kind::Actor, 0x1000); // old process pointer is not identity
    rejects([&] { restored.actor_uuid(impostor, 0x123456789ABCDEF0ULL); });
    restored.destroyed(original);
    restored.actor_uuid(impostor, 0x123456789ABCDEF0ULL);
    CHECK(restored.context(a)->origin->reader == impostor); // same UUID, new validated lifetime
    rejects([&] { imported.restore(saved); });
}

int main(int argc, char** argv) {
    const std::map<std::string, std::function<void()>> cases{
        {"policy", policy}, {"modes", modes_and_selectors},
        {"queued_readers", two_queued_readers}, {"actions", action_assignment_and_ticks},
        {"reflection_177", reflection_and_linked177}, {"root177", root177_and_ordinary_repeat}, {"nested", nested_and_unowned_masking},
        {"reuse", pointer_reuse_and_reader_loss}, {"unwind", failure_unwind_and_reentrant_provider},
        {"guards", guards_and_unowned_preservation}, {"depth_reset", depth_and_session_invalidation},
        {"route_guards", route_and_child_order_guards}, {"thread", thread_guard},
        {"native_provider", native_provider_queries}, {"reporter", reporter_failure_is_contained},
        {"effect_archive", effect_archive_identity_and_pending_reader}};
    try {
        if (argc != 2 || !cases.contains(argv[1])) throw std::runtime_error("unknown test case");
        cases.at(argv[1])();
        std::cout << "PASS " << argv[1] << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << (argc > 1 ? argv[1] : "") << ": " << error.what() << '\n';
        return 1;
    }
}
