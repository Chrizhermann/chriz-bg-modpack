/* Uninstalled research extension ABI. No game hooks or native reward bindings.
 * Engine callback names below are NEW requirements, not existing EEex APIs.
 * Linking/loading this library does not install anything or touch a game.
 */
#ifndef CBM_DUAL_TRANSACTION_H
#define CBM_DUAL_TRANSACTION_H
#include <stdint.h>
#include <stddef.h>
#ifdef _WIN32
#define CBMD_API __declspec(dllexport)
#else
#define CBMD_API __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif

enum { CBMD_ABI = 1 };
enum CBMD_Status {
    CBMD_OK = 0, CBMD_UNSUPPORTED, CBMD_INVALID, CBMD_BUSY, CBMD_REENTRANT,
    CBMD_STALE, CBMD_NO_LEVEL, CBMD_CHOICES_PENDING, CBMD_ADAPTER_ERROR,
    CBMD_INDETERMINATE, CBMD_ALREADY_COMMITTED, CBMD_WRONG_PHASE, CBMD_WRONG_THREAD
};
enum CBMD_Phase { CBMD_IDLE = 0, CBMD_CHOOSING, CBMD_COMMIT_UNKNOWN, CBMD_COMMITTED };
enum CBMD_Outcome { CBMD_UNKNOWN = 0, CBMD_UNCHANGED = 1, CBMD_APPLIED = 2 };
enum CBMD_Capability {
    CBMD_MANUAL_SCREEN = 1u << 0,
    CBMD_DETACHED_PREVIEW = 1u << 1,
    CBMD_INSTALLED_REWARDS = 1u << 2,
    CBMD_OLD_HP = 1u << 3,
    CBMD_OLD_PROFICIENCY_CHOICES = 1u << 4,
    CBMD_OLD_KIT_CLAB = 1u << 5,
    CBMD_SKILLS_SPELLS_HLA = 1u << 6,
    CBMD_DORMANT_REWARDS = 1u << 7,
    CBMD_ATOMIC_ACTOR_LEDGER_COMMIT = 1u << 8,
    CBMD_REVERSIBLE_OLD_USABILITY = 1u << 9,
    CBMD_NO_WORLD_CLASS_TOGGLE = 1u << 10,
    CBMD_BASE_REQUIRED = (1u << 0) | (1u << 1) | (1u << 2) | (1u << 3)
        | (1u << 4) | (1u << 5) | (1u << 6) | (1u << 7) | (1u << 8) | (1u << 10)
};

/* Owner is save-bound; incarnation distinguishes recycled native object IDs.
 * These identities must be supplied by the independently verified store/engine
 * adapter. A pointer or an object ID alone is insufficient. */
typedef struct CBMD_Actor {
    uint64_t owner_hi, owner_lo, incarnation;
    uint32_t object_id;
} CBMD_Actor;

typedef struct CBMD_Request {
    CBMD_Actor actor;
    uint64_t ledger_revision;
    uint64_t old_class_xp_target;
    uint64_t manual_action_id; /* nonzero, explicitly requested by the player */
} CBMD_Request;

/* Captured by the new adapter from committed actor+store state, never inferred
 * from levels. old_frozen_total and its baseline come from the lead's policy;
 * this core does not choose conditional/no-bank or native-discard semantics.
 * Ledger amounts do not change during this LEVEL transaction: campaign release
 * already determined old_usable_xp. There is no award or XP transfer here. */
typedef struct CBMD_Snapshot {
    CBMD_Actor actor;
    uint64_t ledger_revision, actor_revision;
    uint64_t old_frozen_total, old_usable_xp, original_old_bank;
    uint64_t active_usable_xp, active_bank;
    uint32_t native_base_xp, kit;
    uint16_t old_class, active_class, old_level_at_dual;
    uint16_t old_level, active_level;
} CBMD_Snapshot;

typedef struct CBMD_Plan {
    uint64_t old_xp_target;
    uint64_t target_threshold, next_threshold;
    uint16_t target_old_level;
    uint8_t at_table_max; /* next_threshold is not read when true */
    uint8_t reserved;
} CBMD_Plan;

/* Each preview preserves identity, active class/XP and exact ledger amounts.
 * The only projected progression change described here is old_level.
 * The callback also owns a detached complete reward/choice object addressed by
 * handle. The core cannot validate its HP/effects; capabilities alone are not
 * proof of a working native adapter. */
typedef struct CBMD_Preview {
    CBMD_Snapshot projected;
    uint32_t pending_choices;
    uint64_t choice_revision;
} CBMD_Preview;

typedef struct CBMD_Receipt {
    CBMD_Snapshot after;
    uint64_t transaction_id, choice_revision;
} CBMD_Receipt;

/* All callbacks below are missing native-extension requirements.
 * capture, prepare, choose and inspect return 1 on success, 0 on failure.
 * capture, prepare, choose, inspect and discard MUST NOT modify the live actor,
 * effects, XP, ledger, inventory or class flags. The manual UI edits detached
 * state until commit. prepare returns a nonzero handle on success.
 *
 * commit performs ONE atomic compare-and-swap across actor revision, identity,
 * ledger revision AND the complete reward/choice transaction. APPLIED means
 * actor and its progression receipt are saved coherently. UNCHANGED means
 * absolutely no native/persistent change. A thrown exception, false statement
 * or UNKNOWN is never interpreted as safe retry: resolve must supply proof.
 *
 * resolve is read-only and idempotent. It confirms APPLIED with the same receipt,
 * UNCHANGED with no side effects, or UNKNOWN. No core rollback guesses occur.
 * discard releases detached adapter state only; it never rolls back live data.
 * The core does not supply this callback vtable for the actual engine.
 */
typedef struct CBMD_EngineV1 {
    uint32_t abi, struct_size, capabilities;
    void *user;
    int (*capture)(void *, const CBMD_Actor *, CBMD_Snapshot *);
    int (*prepare)(void *, const CBMD_Request *, const CBMD_Snapshot *,
                   uint64_t transaction_id, uint64_t *handle, CBMD_Plan *);
    int (*choose)(void *, uint64_t handle, const void *choice, size_t bytes);
    int (*inspect)(void *, uint64_t handle, CBMD_Preview *);
    int (*commit)(void *, uint64_t handle, uint64_t transaction_id,
                  const CBMD_Snapshot *, const CBMD_Plan *, uint64_t choice_revision,
                  CBMD_Receipt *);
    int (*resolve)(void *, uint64_t handle, uint64_t transaction_id, CBMD_Receipt *);
    void (*discard)(void *, uint64_t handle);
} CBMD_EngineV1;

typedef struct CBMD_Context CBMD_Context;
/* First successful Create pins the library to its calling thread for the whole
 * library lifetime. The real adapter MUST invoke it from a verified native
 * engine/main-thread initialization boundary. This core does not discover that
 * boundary. All later Create and context operations, including Destroy, reject
 * other threads before callbacks or ownership mutation. No thread migration or
 * automatic rebinding after the owner exits is supported. The caller remains
 * responsible for pointer lifetime: never race destruction/use a freed context. */
CBMD_API int CBMD_Create(const CBMD_EngineV1 *, CBMD_Context **);
/* Destruction refuses an outstanding transaction, including unknown commit. */
CBMD_API int CBMD_Destroy(CBMD_Context *);
CBMD_API int CBMD_Begin(CBMD_Context *, const CBMD_Request *);
CBMD_API int CBMD_Choose(CBMD_Context *, const void *, size_t);
CBMD_API int CBMD_GetPreview(CBMD_Context *, CBMD_Preview *);
/* Review/commit require the exact choice revision last presented to the user. */
CBMD_API int CBMD_Commit(CBMD_Context *, uint64_t choice_revision, CBMD_Receipt *);
CBMD_API int CBMD_Cancel(CBMD_Context *);
CBMD_API int CBMD_Resolve(CBMD_Context *, CBMD_Receipt *);
CBMD_API int CBMD_GetPhase(CBMD_Context *, uint32_t *);
/* Explicit reset for a different manual request after a completed transaction.
 * Last committed transaction stays idempotent until this reset. */
CBMD_API int CBMD_Reset(CBMD_Context *);

#ifdef __cplusplus
}
#endif
#endif
