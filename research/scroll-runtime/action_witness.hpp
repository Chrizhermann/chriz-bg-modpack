// Value-carried CAIAction ownership. No hook, engine address or engine allocator.
//
// 2.7.3.0 inlines most CAIAction constructions, copies and destructions, so no
// set of function hooks observes every action lifetime (action-witness-
// evidence.md). Instead an owned action carries a private empty CString block
// in its m_source CString (+80h). The engine touches that field only through
// CString members: CAIAction::Read stores a compiled script's source text there,
// and copies, assignments and destructions share or release it. The action an
// opcode 146/148 ApplyEffect queues holds the shared empty sentinel there.
// Every native copy of the action, inline or not, shares the witness through
// the engine's reference count, and every replacement or destruction releases
// it. Ownership therefore follows the action's value through the message, the
// action queue, GetNextAction's scratch copy and m_curAction without any
// lifetime callback, and a fresh or unrelated action can never carry it: native
// construction writes the shared empty sentinel, and only a copy of a witnessed
// action holds a witness. Readers of m_source see an empty string either way.
//
// Engine CString block ABI, certified per build by the dispatch binder:
// data-0Ch refs, data-8 length, data-4 capacity. A copy shares a block whose
// refs >= 0 (lock inc). Assignment over it and destruction lock-decrement it
// and free only at zero. Every reviewed writer (AssignCopy, CopyBeforeWrite,
// GetBuffer, ConcatInPlace) first copies a block whose refs > 1. The private
// baseline keeps refs > 1, so the engine never writes into or frees a witness.
//
// A witness no engine string references any more is retired: its ownership
// ends, but its block is never freed or reused, not even when the table is
// destroyed. Sweeps audit the retired blocks round robin, a bounded batch per
// stamp, so a holder the evidence missed (a bitwise copy or a double release)
// is reported instead of touching freed memory, and a stale value can never
// resolve to a later scroll use. Since every block ever issued stays allocated,
// a process issues at most `total_capacity` witnesses; the next stamp then
// fails like any other witness fault (action-witness-evidence.md).
#pragma once
#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace cbm::scroll {
class ActionWitnesses {
public:
    using Address = std::uintptr_t;
    // Our own reference. Far above any count of real engine holders, so the
    // engine's count never reaches zero or one while we keep the block.
    static constexpr std::int32_t baseline = 0x40000000;
    // Live witnesses are bounded by scroll actions still referenced by engine
    // strings. More than this means references are retained without bound.
    static constexpr std::size_t live_capacity = 4096;
    // Witnesses one process may issue; each owned queued scroll cast takes one.
    // 16 MiB of blocks at the cap, allocated only as they are used.
    static constexpr std::size_t total_capacity = std::size_t{1} << 20;
    // Retired blocks audited per sweep. Every retired block is audited again
    // after at most ceil(issued / audit_batch) sweeps.
    static constexpr std::size_t audit_batch = 64;

    ActionWitnesses() = default;
    ActionWitnesses(const ActionWitnesses&) = delete;
    ActionWitnesses& operator=(const ActionWitnesses&) = delete;
    // An engine string the evidence missed may still name any issued block, so
    // even a destroyed table hands its blocks to the process instead of freeing
    // them. At most total_capacity blocks, and production destroys a runtime
    // only in a failed startup, before any witness exists.
    ~ActionWitnesses() { for (auto& slab : slabs_) static_cast<void>(slab.release()); }
    // Lowers the lifetime cap, for tests. Never below the blocks already issued.
    void limit(std::size_t total) {
        if (!total || total > total_capacity || total < issued_) throw std::invalid_argument("invalid action witness limit");
        total_ = total;
    }

    // Replaces the engine's shared empty sentinel in `field` with a new witness.
    // `bind(key)` registers ownership for the witness key and may throw; nothing
    // is written to engine memory unless it succeeds.
    template<class Bind>
    Address stamp(Address field, Address empty, Bind&& bind) {
        if (!field || !empty) throw std::invalid_argument("null action witness field or empty sentinel");
        if (load_pointer(field) != empty)
            throw std::logic_error("message action witness field no longer holds the native empty string");
        // A locked (refs < 0) empty block owns no reference, so replacing it
        // can neither leak nor release anything.
        if (refs_at(empty) >= 0 || length_at(empty) != 0 || *reinterpret_cast<const char*>(empty) != 0)
            throw std::logic_error("native empty CString sentinel has an unexpected shape");
        if (live_.size() >= live_capacity) throw std::overflow_error("too many live action witnesses are still referenced");
        if (issued_ >= total_)
            throw std::overflow_error("action witness storage is exhausted: this process has issued its lifetime allowance of queued scroll casts");
        if (issued_ / slab_size == slabs_.size()) slabs_.push_back(std::make_unique<Slab>());
        auto& block = issued_block(issued_);
        const auto key = reinterpret_cast<Address>(block.data);
        auto [placed, inserted] = live_.emplace(key, &block);
        if (!inserted) throw std::logic_error("new action witness reuses a live witness address");
        // Until bind succeeds the block was never visible, so a refusal keeps
        // it for the next stamp.
        try { bind(key); }
        catch (...) { live_.erase(placed); throw; }
        ++issued_;
        std::atomic_ref<std::int32_t>(block.refs).fetch_add(1); // the engine field's reference
        std::memcpy(reinterpret_cast<void*>(field), &key, sizeof key);
        return key;
    }
    // True only for a live witness this table issued. `value` is never
    // dereferenced unless it is one of our own blocks.
    bool contains(Address value) const {
        const auto found = live_.find(value);
        if (found == live_.end()) return false;
        check(*found->second, true);
        return true;
    }
    // Retires witnesses no engine string references any more; `erase(key)` ends
    // their ownership first. Audits the next audit_batch retired blocks. Returns
    // the number of witnesses still referenced.
    template<class Erase>
    std::size_t sweep(Erase&& erase) {
        audit_next(audit_batch);
        for (auto it = live_.begin(); it != live_.end();) {
            check(*it->second, false);
            if (std::atomic_ref<std::int32_t>(it->second->refs).load() == baseline) {
                erase(it->first);
                it = live_.erase(it); // retired: stays allocated, audited round robin
            } else ++it;
        }
        return live_.size();
    }
    // Audits every retired block, before the table is discarded.
    void audit() { audit_next(issued_); }
    std::size_t size() const noexcept { return live_.size(); }
    std::size_t retired() const noexcept { return issued_ - live_.size(); }
    std::size_t issued() const noexcept { return issued_; }
    std::size_t audits() const noexcept { return audits_; } // retired-block audits so far
    // Refs of a live or retired witness, for diagnostics and tests only.
    std::int32_t references(Address value) const {
        if (const auto found = live_.find(value); found != live_.end())
            return std::atomic_ref<std::int32_t>(found->second->refs).load();
        for (std::size_t slab = 0; slab < slabs_.size(); ++slab) {
            const auto first = reinterpret_cast<Address>(slabs_[slab]->blocks[0].data);
            if (value < first || (value - first) % sizeof(Block)) continue;
            const auto index = slab * slab_size + (value - first) / sizeof(Block);
            if ((value - first) / sizeof(Block) < slab_size && index < issued_)
                return std::atomic_ref<std::int32_t>(slabs_[slab]->blocks[index % slab_size].refs).load();
        }
        throw std::invalid_argument("not an action witness");
    }

private:
    struct alignas(16) Block {
        std::int32_t refs{baseline};
        std::int32_t length{};
        std::int32_t allocated{};
        char data[4]{};
    };
    static_assert(offsetof(Block, data) == 12, "engine CString data follows a 12-byte header");
    static_assert(sizeof(Block) == 16, "one witness block is 16 bytes");
    // Blocks are issued in order and never reused, so an index names each one.
    static constexpr std::size_t slab_size = 256;
    struct Slab { std::array<Block, slab_size> blocks{}; };
    std::vector<std::unique_ptr<Slab>> slabs_;
    std::size_t issued_{}, total_{total_capacity}, cursor_{}, audits_{};
    std::unordered_map<Address, Block*> live_;

    Block& issued_block(std::size_t index) { return slabs_[index / slab_size]->blocks[index % slab_size]; }
    // Round robin over every issued block; live ones are checked by sweep. A
    // failed audit leaves the cursor on its block, so it is reported again.
    void audit_next(std::size_t count) {
        count = (std::min)(count, issued_);
        for (std::size_t n = 0; n < count; ++n) {
            if (cursor_ >= issued_) cursor_ = 0;
            auto& block = issued_block(cursor_);
            if (!live_.contains(reinterpret_cast<Address>(block.data))) { audit_retired(block); ++audits_; }
            ++cursor_;
        }
    }

    static Address load_pointer(Address at) { Address value; std::memcpy(&value, reinterpret_cast<const void*>(at), sizeof value); return value; }
    static std::int32_t refs_at(Address data) { std::int32_t value; std::memcpy(&value, reinterpret_cast<const void*>(data - 12), sizeof value); return value; }
    static std::int32_t length_at(Address data) { std::int32_t value; std::memcpy(&value, reinterpret_cast<const void*>(data - 8), sizeof value); return value; }
    static void untouched(Block& block) {
        if (block.length || block.allocated || block.data[0])
            throw std::logic_error("engine wrote into an action witness");
    }
    static void check(Block& block, bool held) {
        const auto refs = std::atomic_ref<std::int32_t>(block.refs).load();
        // Fewer references than engine holders: a holder was copied bitwise or
        // released twice. The block may still be referenced; never free it.
        if (refs < baseline || (held && refs == baseline))
            throw std::logic_error("action witness reference count fell below its engine holders");
        untouched(block);
    }
    static void audit_retired(Block& block) {
        // Retired at exactly our own reference: any later change is an engine
        // holder that was never counted.
        if (std::atomic_ref<std::int32_t>(block.refs).load() != baseline)
            throw std::logic_error("an engine string still referenced a retired action witness");
        untouched(block);
    }
};
} // namespace cbm::scroll
