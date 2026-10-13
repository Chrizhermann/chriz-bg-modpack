#include "dual_transaction.h"
#include <atomic>
#include <limits>
#include <new>

namespace {
std::atomic<uint64_t> next_thread_key{1};
std::atomic<uint64_t> engine_thread_key{0};
uint64_t allocate_thread_key() {
    auto candidate = next_thread_key.load();
    while (candidate != UINT64_MAX) {
        if (next_thread_key.compare_exchange_weak(candidate, candidate + 1)) return candidate;
    }
    return 0;
}
uint64_t thread_key() {
    // OS/std::thread IDs may be reused after exit. A per-thread monotonically
    // allocated token prevents a replacement thread inheriting an old context.
    static thread_local const uint64_t key = allocate_thread_key();
    return key;
}
} // namespace

/* This library is only a transaction coordinator. There are deliberately no
 * executable addresses, EEex calls, direct stat writes, or production hooks. */
struct CBMD_Context {
    const uint64_t owner_thread = thread_key();
    CBMD_EngineV1 engine{};
    std::atomic<bool> busy{false};
    uint32_t phase = CBMD_IDLE;
    CBMD_Request request{};
    CBMD_Snapshot before{};
    CBMD_Plan plan{};
    CBMD_Receipt receipt{};
    uint64_t handle = 0, transaction = 0, reviewed_choice = 0;
    bool preview_fault = false;
};

namespace {
constexpr uint64_t exact_max = 9007199254740991ULL;
std::atomic<CBMD_Context *> screen_owner{nullptr};
std::atomic<uint64_t> sequence{1};

struct Guard {
    CBMD_Context *context;
    bool entered;
    int failure;
    explicit Guard(CBMD_Context *c) : context(c), entered(false), failure(CBMD_INVALID) {
        if (!c) return;
        if (thread_key() != c->owner_thread) { failure = CBMD_WRONG_THREAD; return; }
        entered = !c->busy.exchange(true);
        failure = entered ? CBMD_OK : CBMD_REENTRANT;
    }
    ~Guard() { if (entered) context->busy.store(false); }
};
bool same_actor(const CBMD_Actor &a, const CBMD_Actor &b) {
    return a.owner_hi == b.owner_hi && a.owner_lo == b.owner_lo
        && a.incarnation == b.incarnation && a.object_id == b.object_id;
}
bool valid_actor(const CBMD_Actor &a) {
    return (a.owner_hi || a.owner_lo) && a.incarnation && a.object_id != UINT32_MAX;
}
bool valid_snapshot(const CBMD_Snapshot &s) {
    return valid_actor(s.actor) && s.ledger_revision < exact_max
        && s.actor_revision < UINT64_MAX
        && s.old_frozen_total <= exact_max && s.old_usable_xp <= s.old_frozen_total
        && s.original_old_bank <= s.old_frozen_total
        && s.active_usable_xp <= exact_max && s.active_bank <= exact_max
        && s.old_class > 0 && s.old_class < 256 && s.active_class > 0 && s.active_class < 256
        && s.old_class != s.active_class && s.old_level_at_dual > 0
        && s.old_level_at_dual <= s.old_level && s.old_level < 256
        && s.active_level > 0 && s.active_level < 256;
}
bool same_snapshot(const CBMD_Snapshot &a, const CBMD_Snapshot &b) {
    return same_actor(a.actor, b.actor) && a.ledger_revision == b.ledger_revision
        && a.actor_revision == b.actor_revision && a.old_frozen_total == b.old_frozen_total
        && a.old_usable_xp == b.old_usable_xp && a.original_old_bank == b.original_old_bank
        && a.active_usable_xp == b.active_usable_xp && a.active_bank == b.active_bank
        && a.native_base_xp == b.native_base_xp && a.kit == b.kit
        && a.old_class == b.old_class && a.active_class == b.active_class
        && a.old_level_at_dual == b.old_level_at_dual && a.old_level == b.old_level
        && a.active_level == b.active_level;
}
int valid_plan(const CBMD_Context &c) {
    const auto &p = c.plan;
    if (p.old_xp_target != c.before.old_usable_xp
        || p.old_xp_target != c.request.old_class_xp_target
        || p.target_old_level < c.before.old_level || p.target_old_level >= 256
        || p.target_threshold > p.old_xp_target || p.at_table_max > 1 || p.reserved
        || (!p.at_table_max && (p.next_threshold <= p.old_xp_target
                               || p.next_threshold > exact_max))) return CBMD_INVALID;
    if (p.target_old_level == c.before.old_level) return CBMD_NO_LEVEL;
    const bool was_usable = c.before.active_level > c.before.old_level;
    const bool stays_usable = c.before.active_level > p.target_old_level;
    if (was_usable && !stays_usable
        && !(c.engine.capabilities & CBMD_REVERSIBLE_OLD_USABILITY)) return CBMD_UNSUPPORTED;
    return CBMD_OK;
}
bool valid_preview(const CBMD_Context &c, const CBMD_Preview &p) {
    auto expected = c.before;
    expected.old_level = c.plan.target_old_level;
    return p.choice_revision > 0 && same_snapshot(p.projected, expected);
}
bool valid_receipt(const CBMD_Context &c, const CBMD_Receipt &r) {
    auto expected = c.before;
    expected.old_level = c.plan.target_old_level;
    ++expected.ledger_revision;
    ++expected.actor_revision;
    return r.transaction_id == c.transaction && r.choice_revision == c.reviewed_choice
        && same_snapshot(r.after, expected);
}
void relinquish(CBMD_Context &c) {
    auto *expected = &c;
    screen_owner.compare_exchange_strong(expected, nullptr);
}
bool discard(CBMD_Context &c) {
    const auto handle = c.handle;
    c.handle = 0;
    bool good = true;
    if (handle) {
        try { c.engine.discard(c.engine.user, handle); }
        catch (...) { good = false; } // no world changes permitted in discard
    }
    return good;
}
int abandon(CBMD_Context &c, int result) {
    const bool clean = discard(c);
    c.phase = CBMD_IDLE;
    c.preview_fault = false;
    c.reviewed_choice = 0;
    relinquish(c);
    return clean ? result : CBMD_ADAPTER_ERROR;
}
int inspect(CBMD_Context &c, CBMD_Preview &preview) {
    if (c.preview_fault) return CBMD_ADAPTER_ERROR;
    try {
        if (c.engine.inspect(c.engine.user, c.handle, &preview) != 1) return CBMD_ADAPTER_ERROR;
    } catch (...) { return CBMD_ADAPTER_ERROR; }
    return valid_preview(c, preview) ? CBMD_OK : CBMD_INVALID;
}
int finish_commit(CBMD_Context &c, const CBMD_Receipt &receipt, CBMD_Receipt *out) {
    c.receipt = receipt;
    c.phase = CBMD_COMMITTED;
    const bool clean = discard(c);
    relinquish(c);
    if (out) *out = c.receipt;
    return clean ? CBMD_OK : CBMD_ADAPTER_ERROR;
}
bool callbacks_present(const CBMD_EngineV1 &e) {
    return e.capture && e.prepare && e.choose && e.inspect && e.commit && e.resolve && e.discard;
}
} // namespace

extern "C" {
int CBMD_Create(const CBMD_EngineV1 *engine, CBMD_Context **out) {
    if (!out) return CBMD_INVALID;
    *out = nullptr;
    if (!engine || engine->abi != CBMD_ABI || engine->struct_size != sizeof(CBMD_EngineV1)
        || !callbacks_present(*engine)) return CBMD_UNSUPPORTED;
    if ((engine->capabilities & CBMD_BASE_REQUIRED) != CBMD_BASE_REQUIRED) return CBMD_UNSUPPORTED;
    const auto caller = thread_key();
    if (!caller) return CBMD_UNSUPPORTED;
    auto owner = engine_thread_key.load();
    if (owner && owner != caller) return CBMD_WRONG_THREAD;
    auto *c = new (std::nothrow) CBMD_Context;
    if (!c) return CBMD_ADAPTER_ERROR;
    uint64_t unbound = 0;
    if (!engine_thread_key.compare_exchange_strong(unbound, caller) && unbound != caller) {
        delete c;
        return CBMD_WRONG_THREAD;
    }
    c->engine = *engine;
    *out = c;
    return CBMD_OK;
}

int CBMD_Destroy(CBMD_Context *c) {
    if (!c) return CBMD_INVALID;
    if (thread_key() != c->owner_thread) return CBMD_WRONG_THREAD;
    if (c->busy.exchange(true)) return CBMD_REENTRANT;
    if (c->phase != CBMD_IDLE && c->phase != CBMD_COMMITTED) {
        c->busy.store(false);
        return c->phase == CBMD_COMMIT_UNKNOWN ? CBMD_INDETERMINATE : CBMD_BUSY;
    }
    // Caller must not race object destruction with a new API invocation.
    delete c;
    return CBMD_OK;
}

int CBMD_Begin(CBMD_Context *c, const CBMD_Request *request) {
    if (!c || !request) return CBMD_INVALID;
    Guard guard(c);
    if (!guard.entered) return guard.failure;
    if (c->phase != CBMD_IDLE) return CBMD_WRONG_PHASE;
    if (!valid_actor(request->actor) || !request->manual_action_id
        || request->ledger_revision >= exact_max || request->old_class_xp_target > exact_max)
        return CBMD_INVALID;
    CBMD_Context *empty = nullptr;
    if (!screen_owner.compare_exchange_strong(empty, c)) return CBMD_BUSY;
    c->request = *request;
    c->before = {};
    c->plan = {};
    c->reviewed_choice = 0;
    c->preview_fault = false;
    c->transaction = sequence.fetch_add(1);
    // A saturated identity space cannot safely issue another receipt.
    if (!c->transaction || c->transaction == UINT64_MAX) {
        sequence.store(UINT64_MAX);
        return abandon(*c, CBMD_UNSUPPORTED);
    }
    try {
        if (c->engine.capture(c->engine.user, &request->actor, &c->before) != 1)
            return abandon(*c, CBMD_ADAPTER_ERROR);
        if (!valid_snapshot(c->before)) return abandon(*c, CBMD_INVALID);
        if (!same_actor(c->before.actor, request->actor)
            || c->before.ledger_revision != request->ledger_revision
            || c->before.old_usable_xp != request->old_class_xp_target)
            return abandon(*c, CBMD_STALE);
        if (c->engine.prepare(c->engine.user, &c->request, &c->before, c->transaction,
                              &c->handle, &c->plan) != 1)
            return abandon(*c, CBMD_ADAPTER_ERROR);
        if (!c->handle) return abandon(*c, CBMD_INVALID);
        const auto status = valid_plan(*c);
        if (status != CBMD_OK) return abandon(*c, status);
        c->phase = CBMD_CHOOSING;
        CBMD_Preview preview{};
        const auto checked = inspect(*c, preview);
        if (checked != CBMD_OK) return abandon(*c, checked);
        return CBMD_OK;
    } catch (...) {
        // capture/prepare/inspect are contractually detached and read-only.
        return abandon(*c, CBMD_ADAPTER_ERROR);
    }
}

int CBMD_Choose(CBMD_Context *c, const void *choice, size_t bytes) {
    if (!c || (!choice && bytes)) return CBMD_INVALID;
    Guard guard(c);
    if (!guard.entered) return guard.failure;
    if (c->phase != CBMD_CHOOSING) return CBMD_WRONG_PHASE;
    if (c->preview_fault) return CBMD_ADAPTER_ERROR;
    c->reviewed_choice = 0;
    try {
        if (c->engine.choose(c->engine.user, c->handle, choice, bytes) == 1) {
            CBMD_Preview preview{};
            const auto checked = inspect(*c, preview);
            if (checked == CBMD_OK) return CBMD_OK;
        }
    } catch (...) {}
    c->preview_fault = true; // require cancel, not a potentially partial choice
    return CBMD_ADAPTER_ERROR;
}

int CBMD_GetPreview(CBMD_Context *c, CBMD_Preview *out) {
    if (!c || !out) return CBMD_INVALID;
    Guard guard(c);
    if (!guard.entered) return guard.failure;
    if (c->phase != CBMD_CHOOSING) return CBMD_WRONG_PHASE;
    CBMD_Preview preview{};
    const auto status = inspect(*c, preview);
    if (status == CBMD_OK) {
        *out = preview;
        c->reviewed_choice = preview.choice_revision;
    }
    return status;
}

int CBMD_Commit(CBMD_Context *c, uint64_t choice_revision, CBMD_Receipt *out) {
    if (!c || !out) return CBMD_INVALID;
    Guard guard(c);
    if (!guard.entered) return guard.failure;
    if (c->phase == CBMD_COMMITTED) { *out = c->receipt; return CBMD_ALREADY_COMMITTED; }
    if (c->phase == CBMD_COMMIT_UNKNOWN) return CBMD_INDETERMINATE;
    if (c->phase != CBMD_CHOOSING) return CBMD_WRONG_PHASE;
    CBMD_Preview preview{};
    const auto checked = inspect(*c, preview);
    if (checked != CBMD_OK) return checked;
    if (preview.pending_choices) return CBMD_CHOICES_PENDING;
    if (!choice_revision || choice_revision != c->reviewed_choice
        || choice_revision != preview.choice_revision) return CBMD_STALE;
    CBMD_Snapshot now{};
    try {
        if (c->engine.capture(c->engine.user, &c->request.actor, &now) != 1)
            return CBMD_ADAPTER_ERROR;
    } catch (...) { return CBMD_ADAPTER_ERROR; }
    if (!same_snapshot(now, c->before)) return CBMD_STALE;
    CBMD_Receipt receipt{};
    // Set this BEFORE entering commit. Reentrant calls cannot retry it, and any
    // thrown/unknown failure remains pending until an authoritative resolution.
    c->phase = CBMD_COMMIT_UNKNOWN;
    int result = CBMD_UNKNOWN;
    try {
        result = c->engine.commit(c->engine.user, c->handle, c->transaction,
                                  &c->before, &c->plan, choice_revision, &receipt);
    } catch (...) { return CBMD_INDETERMINATE; }
    if (result == CBMD_UNCHANGED) { c->phase = CBMD_CHOOSING; return CBMD_ADAPTER_ERROR; }
    if (result != CBMD_APPLIED || !valid_receipt(*c, receipt)) return CBMD_INDETERMINATE;
    return finish_commit(*c, receipt, out);
}

int CBMD_Cancel(CBMD_Context *c) {
    if (!c) return CBMD_INVALID;
    Guard guard(c);
    if (!guard.entered) return guard.failure;
    if (c->phase == CBMD_COMMIT_UNKNOWN) return CBMD_INDETERMINATE;
    if (c->phase != CBMD_CHOOSING) return CBMD_WRONG_PHASE;
    return abandon(*c, CBMD_OK);
}

int CBMD_Resolve(CBMD_Context *c, CBMD_Receipt *out) {
    if (!c || !out) return CBMD_INVALID;
    Guard guard(c);
    if (!guard.entered) return guard.failure;
    if (c->phase == CBMD_COMMITTED) { *out = c->receipt; return CBMD_ALREADY_COMMITTED; }
    if (c->phase != CBMD_COMMIT_UNKNOWN) return CBMD_WRONG_PHASE;
    CBMD_Receipt receipt{};
    int result = CBMD_UNKNOWN;
    try { result = c->engine.resolve(c->engine.user, c->handle, c->transaction, &receipt); }
    catch (...) { return CBMD_INDETERMINATE; }
    if (result == CBMD_UNCHANGED) {
        // Resolution cancels this attempt. A retry needs a fresh manual request.
        return abandon(*c, CBMD_OK);
    }
    if (result != CBMD_APPLIED || !valid_receipt(*c, receipt)) return CBMD_INDETERMINATE;
    return finish_commit(*c, receipt, out);
}

int CBMD_GetPhase(CBMD_Context *c, uint32_t *out) {
    if (!c || !out) return CBMD_INVALID;
    Guard guard(c);
    if (!guard.entered) return guard.failure;
    *out = c->phase;
    return CBMD_OK;
}

int CBMD_Reset(CBMD_Context *c) {
    if (!c) return CBMD_INVALID;
    Guard guard(c);
    if (!guard.entered) return guard.failure;
    if (c->phase != CBMD_COMMITTED && c->phase != CBMD_IDLE)
        return c->phase == CBMD_COMMIT_UNKNOWN ? CBMD_INDETERMINATE : CBMD_BUSY;
    c->phase = CBMD_IDLE;
    c->request = {};
    c->before = {};
    c->plan = {};
    c->receipt = {};
    c->reviewed_choice = 0;
    return CBMD_OK;
}
} // extern C
