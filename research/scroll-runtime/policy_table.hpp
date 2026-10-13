#pragma once
#include "scroll_context.hpp"
#include <algorithm>
#include <array>
#include <cstdint>
#include <functional>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace cbm::scroll {
// Immutable indexed policy. SHA verification deliberately uses the host's
// effective resource reader, not only override files or a reference install.
class PolicyTable {
public:
    using Digest = std::array<std::uint8_t, 32>;
    using VerifyResource = std::function<std::optional<Digest>(std::string_view, std::string_view)>;
    enum class Reason : std::uint8_t { TypedCast, Learning, NativeOnly, NativeException, MixedLearning, Unresolved };
    struct Result { ItemPolicy policy; Reason reason; };
    struct Dependency { std::array<char, 8> name; std::array<char, 4> extension; Digest digest; };
private:
    struct Entry { std::array<char, 8> item; std::uint32_t ability; Result result; };
    std::vector<Entry> entries_;
    std::vector<Dependency> dependencies_;
    bool verified_ = false;
    static std::uint32_t u32(std::span<const std::uint8_t> bytes, std::size_t offset) {
        return std::uint32_t(bytes[offset]) | std::uint32_t(bytes[offset + 1]) << 8 |
            std::uint32_t(bytes[offset + 2]) << 16 | std::uint32_t(bytes[offset + 3]) << 24;
    }
    static std::array<char, 8> name(std::span<const std::uint8_t> bytes, bool canonical) {
        if (bytes.empty() || bytes.size() > 8) throw std::invalid_argument("invalid policy resource reference length");
        std::array<char, 8> out{};
        bool ended = false;
        for (std::size_t i = 0; i < bytes.size(); ++i) {
            auto c = bytes[i];
            if (!c) { ended = true; continue; }
            if (ended || c < 33 || c > 126 || c == '/' || c == '\\' || c == ':')
                throw std::invalid_argument("invalid policy resource reference");
            if (c >= 'a' && c <= 'z') {
                if (canonical) throw std::invalid_argument("noncanonical policy resource reference");
                c = static_cast<std::uint8_t>(c - 'a' + 'A');
            }
            out[i] = static_cast<char>(c);
        }
        if (!out[0]) throw std::invalid_argument("empty policy resource reference");
        return out;
    }
    template<std::size_t N> static std::string_view text(const std::array<char, N>& value) {
        return {value.data(), static_cast<std::size_t>(std::find(value.begin(), value.end(), '\0') - value.begin())};
    }
public:
    static constexpr std::size_t max_entries = 131072, max_resources = 262144;
    explicit PolicyTable(std::span<const std::uint8_t> bytes) {
        constexpr std::array<std::uint8_t, 8> magic{'C','B','M','S','P','O','L','1'};
        if (bytes.size() < 16 || !std::equal(magic.begin(), magic.end(), bytes.begin()))
            throw std::invalid_argument("unsupported scroll policy table");
        const auto count = u32(bytes, 8), resources = u32(bytes, 12);
        if (count > max_entries || resources > max_resources ||
            bytes.size() != 16 + std::size_t(count) * 16 + std::size_t(resources) * 44)
            throw std::invalid_argument("scroll policy table bounds/count mismatch");
        entries_.reserve(count); dependencies_.reserve(resources);
        for (std::uint32_t i = 0; i < count; ++i) {
            const auto offset = 16 + std::size_t(i) * 16;
            const auto item = name(bytes.subspan(offset, 8), true);
            const auto ability = u32(bytes, offset + 8);
            const auto policy = bytes[offset + 12], reason = bytes[offset + 13];
            constexpr std::array<std::uint8_t, 6> expected{0, 1, 1, 1, 2, 2};
            if (ability >= 65535 || reason >= expected.size() || policy != expected[reason] ||
                bytes[offset + 14] || bytes[offset + 15])
                throw std::invalid_argument("invalid scroll policy entry");
            if (!entries_.empty() && (entries_.back().item > item ||
                (entries_.back().item == item && entries_.back().ability >= ability)))
                throw std::invalid_argument("unsorted/duplicate scroll policy entry");
            entries_.push_back({item, ability, {static_cast<ItemPolicy>(policy), static_cast<Reason>(reason)}});
        }
        for (std::uint32_t i = 0; i < resources; ++i) {
            const auto offset = 16 + std::size_t(count) * 16 + std::size_t(i) * 44;
            Dependency dep{};
            dep.name = name(bytes.subspan(offset, 8), true);
            std::copy_n(bytes.begin() + offset + 8, 4, dep.extension.begin());
            const auto ext = text(dep.extension);
            if (dep.extension[3] || (ext != "ITM" && ext != "SPL" && ext != "EFF"))
                throw std::invalid_argument("invalid scroll policy dependency type");
            std::copy_n(bytes.begin() + offset + 12, 32, dep.digest.begin());
            if (!dependencies_.empty() && (dependencies_.back().name > dep.name ||
                (dependencies_.back().name == dep.name && dependencies_.back().extension >= dep.extension)))
                throw std::invalid_argument("unsorted/duplicate policy dependency");
            dependencies_.push_back(dep);
        }
        for (const auto& entry : entries_) {
            const auto it = std::lower_bound(dependencies_.begin(), dependencies_.end(), entry.item,
                [](const Dependency& dep, const auto& item) { return dep.name < item; });
            auto scan = it;
            while (scan != dependencies_.end() && scan->name == entry.item && text(scan->extension) != "ITM") ++scan;
            if (scan == dependencies_.end() || scan->name != entry.item)
                throw std::invalid_argument("policy entry is missing its item dependency");
        }
    }
    // A failed refresh invalidates the whole old table before invoking host
    // code. It can never leave a partly refreshed policy usable.
    void verify(const VerifyResource& read_digest) {
        verified_ = false;
        if (!read_digest) throw std::invalid_argument("scroll policy requires effective resource verification");
        for (const auto& dep : dependencies_) {
            const auto actual = read_digest(text(dep.name), text(dep.extension));
            if (!actual || *actual != dep.digest)
                throw std::runtime_error("scroll policy inventory changed: " + std::string(text(dep.name)) + "." + std::string(text(dep.extension)));
        }
        verified_ = true;
    }
    void invalidate() noexcept { verified_ = false; }
    bool verified() const noexcept { return verified_; }
    const std::vector<Dependency>& dependencies() const noexcept { return dependencies_; }
    std::optional<Result> lookup(std::span<const std::uint8_t> item, std::uint32_t ability) const {
        if (!verified_) throw std::logic_error("scroll policy inventory has not been verified");
        const auto key = name(item, false);
        const auto found = std::lower_bound(entries_.begin(), entries_.end(), std::pair{key, ability},
            [](const Entry& entry, const auto& value) { return entry.item < value.first ||
                (entry.item == value.first && entry.ability < value.second); });
        if (found == entries_.end() || found->item != key || found->ability != ability) return {};
        return found->result;
    }
};
} // namespace cbm::scroll
