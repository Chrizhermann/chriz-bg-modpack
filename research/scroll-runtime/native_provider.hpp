// Read-only target-reader adapter. The host supplies audited native function
// pointers after version/signature validation; no detours are installed here.
#pragma once
#include "eeex_bridge.hpp"
#include <cstring>

namespace cbm::scroll {
struct NativeReaderFunctions {
    using Lookup = std::uint8_t (*)(std::int32_t, void**);
    using Classes = void (*)(void*, std::uint8_t*, std::uint8_t*);
    using Level = std::uint8_t (*)(void*, std::uint8_t, std::uint8_t);
    using Maximum = std::uint8_t (*)(void*, std::uint8_t);
    using CanCast = int (*)(void*, void*);
    using CasterType = short (*)(void*);
    using CasterLevel = short (*)(void*, void*, int);
    Lookup lookup{};
    Classes active_inactive{};
    Level class_level{};
    Maximum maximum_level{};
    CanCast mage{}, priest{};
    CasterType caster_type{};
    CasterLevel caster_level{};
};
struct NativeReaderLayout {
    // Pinned BG2EE x64 layout; certification for each version is required in
    // the host. Named offsets correspond to actual generated/source fields.
    std::size_t current_ai = 0x30;
    std::size_t start_ai = 0x4B68;
    std::size_t ai_class = 0xB;
    std::size_t ai_instance = 0xC;
    std::size_t derived = 0x1120;
    std::size_t temporary = 0x1DC8;
    std::size_t use_derived = 0x4EA4;
};
struct NativeReaderSnapshot {
    ReaderStats stats;
    std::uint8_t current_class{}, start_class{}, new_class{}, old_class{};
    bool dual{};
};
class NativeReaderProvider {
    NativeReaderFunctions functions_;
    NativeReaderLayout layout_;
    template<class T> static T read(const std::byte* pointer) {
        T out;
        std::memcpy(&out, pointer, sizeof out);
        return out;
    }
public:
    explicit NativeReaderProvider(NativeReaderFunctions functions, NativeReaderLayout layout = {})
        : functions_(functions), layout_(layout) {
        static_assert(sizeof(void*) == 8, "audited reader ABI is x64 only");
        if (!functions.lookup || !functions.active_inactive || !functions.class_level ||
            !functions.maximum_level || !functions.mage || !functions.priest ||
            !functions.caster_type || !functions.caster_level)
            throw std::invalid_argument("native reader provider missing audited function");
    }
    NativeReaderSnapshot resolve(void* reader, void* spell, SpellType expected) const {
        if (!reader || !spell) throw std::invalid_argument("null native reader or CSpell");
        // Registry generation/lifetime is checked by Scope::select before and
        // after this callback. Lookup also verifies the engine identity used
        // internally by GetActiveInactiveClasses, whose failed lookup otherwise
        // looks exactly like the nondual case.
        auto* bytes = static_cast<std::byte*>(reader);
        auto* start = bytes + layout_.start_ai;
        const auto instance = read<std::int32_t>(start + layout_.ai_instance);
        void* resolved = nullptr;
        if (instance == -1 || functions_.lookup(instance, &resolved) != 0 || resolved != reader)
            throw std::logic_error("native start-AI instance does not resolve to original reader");
        const auto raw_type = static_cast<unsigned>(functions_.caster_type(spell));
        auto actual = spell_type(raw_type);
        if (raw_type == 0 && expected == SpellType::PreserveNative) {
            // GetCasterType also returns0 for missing/empty resources. Only a
            // present V1 SPL header with actual type0 resolves that ambiguity.
            // Pinned native GetCasterType reads CSpell::pRes + CResSpell::pHeader
            // at these same offsets after Demand (reader-native-2.6/2.7.txt).
            auto* spell_bytes = static_cast<std::byte*>(spell);
            auto* resource = read<std::byte*>(spell_bytes);
            auto* header = resource ? read<std::byte*>(resource + 0x68) : nullptr;
            if (read<std::uint8_t>(spell_bytes + 8) != 0 && header &&
                std::memcmp(header, "SPL V1  ", 8) == 0 && read<std::uint16_t>(header + 0x1C) == 0)
                actual = SpellType::PreserveNative;
        }
        if (actual == SpellType::Unresolved || actual != expected)
            throw std::logic_error("installed native spell type unresolved or changed");
        NativeReaderSnapshot out;
        if (actual == SpellType::PreserveNative) return out;
        out.current_class = read<std::uint8_t>(bytes + layout_.current_ai + layout_.ai_class);
        out.start_class = read<std::uint8_t>(start + layout_.ai_class);
        functions_.active_inactive(start, &out.new_class, &out.old_class);
        out.dual = out.new_class != out.old_class;
        auto* stats = bytes + (read<std::uint32_t>(bytes + layout_.use_derived) ? layout_.derived : layout_.temporary);
        // In a dual class the new class is always the highest ACTIVE class:
        // until new>old, old is dormant; afterwards new is already higher.
        // Nondual/multiclass slot mapping is delegated to the native helper.
        const auto highest = out.dual ? functions_.class_level(stats, out.start_class, out.new_class)
                                      : functions_.maximum_level(stats, out.start_class);
        out.stats.classes.push_back({highest, true});
        // Native screen-method bodies do not use their this pointer or selected
        // UI actor. RDX is this original reader. They apply native active-class,
        // kit-mask and fallen-class mechanics without a mod-kit name whitelist.
        const bool capable = (actual == SpellType::Arcane ? functions_.mage : functions_.priest)(nullptr, reader) != 0;
        auto& capability = actual == SpellType::Arcane ? out.stats.arcane : out.stats.divine;
        capability.state = capable ? Capability::Active : Capability::Absent;
        if (capable) {
            // This native method intentionally uses currentAI while capability
            // uses startAI. Preserve both semantics and expose their provenance;
            // do not assume the two class bytes must equal under every mod.
            const short level = functions_.caster_level(reader, spell, 1);
            if (level <= 0) throw std::logic_error("native active caster level invalid");
            capability.level = static_cast<unsigned>(level);
        }
        (void)reader_level(out.stats, actual); // validate the completed snapshot
        return out;
    }
};
} // namespace cbm::scroll
