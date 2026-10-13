// NUL-free ASCII envelope for EEex actor marshal strings. UUIDs never pass
// through a Lua floating-point number. Unknown schemas remain caller-owned.
#pragma once
#include "effect_archive.hpp"
#include <string_view>

namespace cbm::scroll {
inline std::string archive_text(const SavedEffectArchive& saved) {
    if (saved.schema != 1 || saved.rows.size() > UINT32_MAX) throw std::invalid_argument("unsupported effect archive schema/size");
    std::vector<std::byte> bytes;
    const auto integer = [&](std::uint64_t value, unsigned width) {
        for (unsigned i = 0; i < width; ++i) bytes.push_back(static_cast<std::byte>((value >> (i * 8)) & 255));
    };
    integer(saved.rows.size(), 4);
    for (const auto& row : saved.rows) {
        bytes.insert(bytes.end(), row.wire.begin(), row.wire.end());
        integer(row.context.has_value() ? 1 : 0, 1);
        if (!row.context) continue;
        const auto& value = *row.context;
        integer(value.origin_key, 8); integer(value.reader_uuid, 8);
        for (char c : value.item.bytes) integer(static_cast<unsigned char>(c), 1);
        integer(value.ability, 4); integer(value.root_effect, 4); integer(value.depth, 4);
        integer(value.applied_level.has_value() ? 1 : 0, 1); integer(value.applied_level.value_or(0), 4);
    }
    std::string result = "CBMSFX01:";
    constexpr char hex[] = "0123456789ABCDEF";
    result.reserve(result.size() + bytes.size() * 2);
    for (auto byte : bytes) {
        const auto value = std::to_integer<unsigned>(byte);
        result.push_back(hex[value >> 4]); result.push_back(hex[value & 15]);
    }
    return result;
}

inline SavedEffectArchive read_archive_text(std::string_view text) {
    if (!text.starts_with("CBMSFX01:") || (text.size() - 9) % 2)
        throw std::invalid_argument("unknown/malformed effect envelope; retain original actor data");
    std::vector<std::byte> bytes;
    bytes.reserve((text.size() - 9) / 2);
    const auto digit = [](char c) -> unsigned {
        if (c >= '0' && c <= '9') return static_cast<unsigned>(c - '0');
        if (c >= 'A' && c <= 'F') return static_cast<unsigned>(c - 'A' + 10);
        if (c >= 'a' && c <= 'f') return static_cast<unsigned>(c - 'a' + 10);
        throw std::invalid_argument("invalid effect envelope hex");
    };
    for (std::size_t i = 9; i < text.size(); i += 2)
        bytes.push_back(static_cast<std::byte>((digit(text[i]) << 4) | digit(text[i + 1])));
    std::size_t cursor = 0;
    const auto integer = [&](unsigned width) {
        if (cursor > bytes.size() || width > bytes.size() - cursor) throw std::invalid_argument("truncated effect envelope");
        std::uint64_t value = 0;
        for (unsigned i = 0; i < width; ++i) value |= std::to_integer<std::uint64_t>(bytes[cursor++]) << (i * 8);
        return value;
    };
    const auto count = integer(4);
    if (count > (bytes.size() - cursor) / 265) throw std::invalid_argument("effect envelope count exceeds its bytes");
    SavedEffectArchive out;
    out.rows.reserve(static_cast<std::size_t>(count));
    for (std::uint64_t i = 0; i < count; ++i) {
        SavedEffectRow row{};
        for (auto& byte : row.wire) byte = static_cast<std::byte>(integer(1));
        const auto owned = integer(1);
        if (owned > 1) throw std::invalid_argument("invalid saved effect ownership marker");
        if (owned) {
            SavedEffectContext value;
            value.origin_key = integer(8); value.reader_uuid = integer(8);
            for (auto& c : value.item.bytes) c = static_cast<char>(integer(1));
            value.ability = static_cast<unsigned>(integer(4)); value.root_effect = static_cast<unsigned>(integer(4));
            value.depth = static_cast<unsigned>(integer(4));
            const auto has_level = integer(1), level = integer(4);
            if (has_level > 1 || (!has_level && level)) throw std::invalid_argument("invalid saved effect scalar marker");
            if (has_level) value.applied_level = static_cast<unsigned>(level);
            row.context = value;
        }
        out.rows.push_back(std::move(row));
    }
    if (cursor != bytes.size()) throw std::invalid_argument("trailing bytes in effect envelope");
    return out;
}
} // namespace cbm::scroll
