// Per-emitted-record ownership for native V1 effect marshal/decode integration.
// No save/file I/O. Actor marshal metadata owns SavedEffectArchive by value.
#pragma once
#include "scroll_context.hpp"
#include <span>
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>

namespace cbm::scroll {
using EffectWire = std::array<std::byte, 0x108>;
struct SavedEffectContext {
    std::uint64_t origin_key{}, reader_uuid{};
    ResRef item;
    unsigned ability{}, root_effect{}, depth{};
    std::optional<unsigned> applied_level;
    bool operator==(const SavedEffectContext&) const = default;
};
struct SavedEffectRow {
    EffectWire wire;
    std::optional<SavedEffectContext> context;
};
struct SavedEffectArchive {
    unsigned schema{1};
    // Includes unowned emitted rows so insertions/filtering cannot shift owned
    // ordinals silently. Nothing in this representation is a machine pointer.
    std::vector<SavedEffectRow> rows;
};
class EffectExport {
    Registry& registry_;
    Address output_;
    SavedEffectArchive saved_;
public:
    EffectExport(Registry& registry, Address output) : registry_(registry), output_(output) {
        if (!output) throw std::invalid_argument("null native effect marshal buffer");
    }
    void emitted(Handle effect, Address destination, std::span<const std::byte> wire) {
        registry_.frame_count();
        if (effect.kind != Kind::Effect || wire.size() != 0x108 || destination < output_ ||
            destination - output_ != saved_.rows.size() * 0x108)
            throw std::invalid_argument("native effect marshal record ordinal/size mismatch");
        SavedEffectRow row{};
        std::copy(wire.begin(), wire.end(), row.wire.begin());
        if (auto context = registry_.context(effect)) {
            if (!context->origin->reader_uuid) throw std::logic_error("cannot save owned effect without original-reader UUID");
            if (context->pending_selector) throw std::logic_error("effect archive cannot serialize a queued action/message selector");
            row.context = SavedEffectContext{context->origin->use, context->origin->reader_uuid,
                context->origin->item, context->origin->ability, context->root_effect, context->depth, context->applied_level};
            if (context->applied_level) {
                std::uint32_t native_level{};
                std::memcpy(&native_level, wire.data() + 0xC0, sizeof native_level);
                if (native_level != *context->applied_level)
                    throw std::logic_error("saved native caster level differs from proven effect level");
            }
        }
        saved_.rows.push_back(std::move(row));
    }
    SavedEffectArchive finish(std::span<const std::byte> actual_native_wire) const {
        if (actual_native_wire.size() != saved_.rows.size() * 0x108)
            throw std::logic_error("native effect marshal count changed");
        for (std::size_t i = 0; i < saved_.rows.size(); ++i)
            if (!std::equal(saved_.rows[i].wire.begin(), saved_.rows[i].wire.end(), actual_native_wire.begin() + i * 0x108))
                throw std::logic_error("native effect marshal bytes changed after attribution");
        return saved_;
    }
};

class EffectImport {
    struct Decoded { Handle effect; EffectWire wire; };
    Registry& registry_;
    std::vector<Decoded> decoded_;
    bool committed_{};
public:
    explicit EffectImport(Registry& registry) : registry_(registry) {}
    // Called at the actual DecodeEffectFromBase return, with the saved raw
    // record. Not inferred from effect-list order or mutable decoded fields.
    void decoded(std::size_t ordinal, Handle effect, std::span<const std::byte> wire) {
        if (committed_ || effect.kind != Kind::Effect || ordinal != decoded_.size() || wire.size() != 0x108)
            throw std::logic_error("effect decode ordinal/size/lifetime mismatch");
        if (registry_.context(effect)) throw std::logic_error("decoded effect already has live ancestry");
        Decoded row{effect, {}};
        std::copy(wire.begin(), wire.end(), row.wire.begin());
        decoded_.push_back(std::move(row));
    }
    // Returns nothing once ownership is restored. A well-formed envelope that
    // no longer describes these decoded records (count or bytes) is stale: the
    // records changed after it was written, as when a process with overrides
    // off kept it unparsed and saved it again. Then nothing is restored and the
    // reason is returned; only this actor loses that saved ancestry, its
    // records keep their saved levels. Anything else that cannot be trusted
    // (schema, ancestry, scalars, origins, lifetimes) throws, as before.
    std::optional<std::string> restore(const SavedEffectArchive& saved) {
        if (committed_) throw std::logic_error("effect archive imported twice");
        // Caller keeps unknown schemas in actor-owned storage; this refuses
        // without destroying, normalizing or silently dropping that envelope.
        if (saved.schema != 1) throw std::logic_error("unsupported effect archive schema; retain actor metadata");
        // Checked on its own first: malformed or internally inconsistent data
        // refuses here. A well-formed mismatch below is outdated, damaged or not.
        std::map<std::uint64_t, SavedEffectContext> definitions;
        for (const auto& row : saved.rows) {
            if (!row.context) continue;
            const auto& value = *row.context;
            if (!value.origin_key || !value.reader_uuid || !value.item.bytes[0] || value.depth > 64 ||
                (value.applied_level && (!*value.applied_level || *value.applied_level > 32767)))
                throw std::logic_error("invalid saved effect ancestry");
            if (value.applied_level) {
                std::uint32_t native_level{};
                std::memcpy(&native_level, row.wire.data() + 0xC0, sizeof native_level);
                if (native_level != *value.applied_level) throw std::logic_error("saved effect scalar mismatch");
            }
            auto [it, inserted] = definitions.emplace(value.origin_key, value);
            if (!inserted && (it->second.reader_uuid != value.reader_uuid || it->second.item != value.item ||
                               it->second.ability != value.ability))
                throw std::logic_error("conflicting saved scroll origin definitions");
        }
        for (const auto& row : decoded_)
            if (registry_.context(row.effect)) throw std::logic_error("decoded effect acquired ancestry before import");
        if (saved.rows.size() != decoded_.size())
            return "saved effect record count mismatch (saved " + std::to_string(saved.rows.size()) +
                   ", loaded " + std::to_string(decoded_.size()) + ")";
        for (std::size_t i = 0; i < saved.rows.size(); ++i) {
            const auto& wire = saved.rows[i].wire;
            const auto first = std::mismatch(wire.begin(), wire.end(), decoded_[i].wire.begin()).first;
            if (first == wire.end()) continue;
            char where[96];
            std::snprintf(where, sizeof where, " (record %zu of %zu, byte 0x%zX)", i + 1, saved.rows.size(),
                          static_cast<std::size_t>(first - wire.begin()));
            return std::string("saved effect record identity mismatch") + where;
        }
        std::map<std::uint64_t, std::shared_ptr<const Origin>> origins;
        for (const auto& [key, value] : definitions)
            origins.emplace(key, registry_.restored_origin(value.reader_uuid, value.item, value.ability));
        std::vector<std::pair<Handle, Context>> staged;
        for (std::size_t i = 0; i < saved.rows.size(); ++i) {
            if (auto& saved_context = saved.rows[i].context) {
                const auto& value = *saved_context;
                staged.emplace_back(decoded_[i].effect, Context{origins.at(value.origin_key), value.root_effect,
                    value.depth, value.applied_level, {}});
            }
        }
        // All identity/format checks and allocations finish before ownership
        // changes. No provider callbacks occur during this commit.
        for (auto& [effect, context] : staged) registry_.restore_effect(effect, std::move(context));
        committed_ = true;
        return std::nullopt;
    }
};
} // namespace cbm::scroll
