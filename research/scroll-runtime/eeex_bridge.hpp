// Typed bridge for the pinned InfinityLoader CGameEffect / CItem definitions.
// This file installs NO hook. The callback sites and lifecycle producers must
// all be wired before using it in a game. See README.md.
#pragma once
#include "scroll_context.hpp"
#include <utility>

namespace cbm::scroll {
struct Route { Selector selector; Kind carrier; bool direct; };
inline SpellType spell_type(unsigned native_caster_type) noexcept {
    return native_caster_type == 1 ? SpellType::Arcane :
           native_caster_type == 2 ? SpellType::Divine :
           native_caster_type >= 3 && native_caster_type <= 5 ? SpellType::PreserveNative : SpellType::Unresolved;
}
inline Route route(unsigned opcode, unsigned mode, unsigned special) {
    if (mode > 2 || (opcode != 146 && opcode != 148))
        throw std::invalid_argument("unsupported scroll dispatcher opcode/mode");
    if (!mode) {
        return {opcode == 146 ? ((special & 1) ? Selector::Spell : Selector::Force)
                             : ((special & 1) ? Selector::SpellPoint : Selector::ForcePoint), Kind::Action, false};
    }
    if (opcode == 148) return {Selector::FirePoint, Kind::Effect, true};
    return mode == 1 ? Route{Selector::Fire, Kind::FireMessage, false}
                     : Route{Selector::EffectFire, Kind::Effect, true};
}

// Read-only named-field access uses the actual generated bindings' spelling.
// It does not assume layout/order of the source effect's gameplay fields.
template<class NativeEffect>
Route route(const NativeEffect& effect) {
    return route(effect.m_effectId, effect.m_dWFlags, effect.m_special);
}
template<class NativeEffect>
void queued_dispatch(Registry& registry, Handle source, const NativeEffect& effect, Handle destination) {
    const auto selected = route(effect);
    if (selected.direct || destination.kind != selected.carrier)
        throw std::invalid_argument("wrong queued-scroll boundary");
    registry.dispatch(source, destination, selected.selector);
}
template<class NativeEffect>
Registry::Scope direct_dispatch(Registry& registry, Handle source, const NativeEffect& effect, CastRequest request) {
    const auto selected = route(effect);
    if (!selected.direct || selected.selector != request.selector)
        throw std::invalid_argument("wrong direct-scroll boundary");
    return registry.enter(source, request);
}

// Only this native field is owned. No source/target, parameter, mode, flags,
// resource, timing, charge or equipment field is changed by this adapter.
template<class NativeEffect>
void spell_child(Registry::Scope& cast, Handle child, Address spell, NativeEffect& effect) {
    if (auto level = cast.child(child, spell)) effect.m_casterLevel = *level;
}
template<class NativeEffect>
void linked_child(Registry& registry, Handle parent, Handle child, NativeEffect& effect) {
    registry.linked177(parent, child);
    if (auto value = registry.context(child); value && value->applied_level)
        effect.m_casterLevel = *value->applied_level;
}

// A native trampoline must not let C++ exceptions cross the engine ABI. Its
// caller must inspect false and abort/report the unsupported operation; false
// is NOT permission to report a successful native-level fallback. The supplied
// reporter must itself be noexcept and must not allocate/enter the engine.
template<class Callback, class Report>
bool boundary(Callback&& callback, Report&& report) noexcept {
    static_assert(noexcept(report(static_cast<const char*>(nullptr))));
    try { std::forward<Callback>(callback)(); return true; }
    catch (const std::exception& error) { report(error.what()); }
    catch (...) { report("unknown native scroll extension error"); }
    return false;
}
} // namespace cbm::scroll
