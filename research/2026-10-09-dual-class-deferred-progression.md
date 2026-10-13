# Deferred advancement of the retired dual class

Current handover: the offline native adapter and manual old-class reward path
are assembled in the [default EET candidate](xp-banking-native/DEFAULT-TRIAL.md).
Its build passed; Christopher deferred gameplay acceptance by choosing to keep
the disposable trial prepared without launching it. The text below retains the investigation history and must not
be read as the current list of missing implementation. No production component
or existing-save migration is claimed.

Research date: 2026-10-09. This is a bounded, offline feasibility review and
compiled transaction-core prototype for `codex/campaign-xp-banking`. It is not a
complete native engine adapter or production acceptance result.
Read the current project guidance and mandatory compatibility policy first.
No game was launched, game/save data changed, component installed, or native hook
deployed. Only this note and `research/xp-banking-native/dual-*` research files are
owned by this task.

## Approved intent and finding

The user approved **immediate dual-classing with separate XP ownership**. In the
example, 550,000 earned before dualing at the SoD 500,000 cap means 50,000 retained
for Fighter. Subsequent 200,000 belongs to Thief. When campaign room opens, each
balance becomes usable by its own class. This review does not impose a delayed
dual, an anti-abuse lock, or transfer old-class XP into the new class.

Retaining the two balances is technically distinct from granting the retired
class its deferred levels. **The existing unmodified level-up flow cannot offer
that old-class advancement merely because an old-class balance has increased.**
Its dual branch selects the active subclass only. The XP and level-up machinery
would need a new scoped advancement context, including manual choices and the
normal transaction's commit/cancel handling.

The existing screen and reward helpers offer useful building blocks. This review
does not prove that they are sufficient without extension, and does not establish
that normal-screen integration is impossible. The concrete missing capability is
a **manual, retired-class progression transaction** with independent class XP,
complete installed class/kit rewards, and rollback. A level-byte write or a global
override of one XP getter does not supply that capability.

## Reviewed inputs and scope

Executable opened read-only:
`<BG2EE 2.6.6.0 install>/Baldur.exe`,
BG2EE 2.6.6.0, SHA-256
`fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580`.
Preferred-image addresses below use image base `0x140000000`; production hooks
would require relocated signatures and a verified ABI, not fixed addresses.

Cached official source maps and bindings:

- `C:/tmp/scroll-hook-research-20261009/EEex`, commit
  `a6d21abe44e20509f5d0259ccc6c7e7f9d12b285`.
- `C:/tmp/scroll-hook-research-20261009/InfinityLoader`, commit
  `817925caab3eb9cf600cfaf38853da8d30c28247`.
- Function map: `EEex/loader/v2.6.6.0/bg2ee/function_names.db`.
- Struct source: `Core-Shared-Files/generate_bindings/in/Baldur-v2.6.6.0.h`.

Evidence is textual disassembly in `xp-banking-native/dual-ui.txt` and
`dual-rewards.txt`, plus the preceding review's
`bg2ee-2.6.6-native-bank.txt`, `bg2ee-2.6.6-native-bank-writers.txt` and
`bg2ee-2.6.6-dual-threshold.txt`. Some engine functions have folded aliases in
the name map; the conclusions below follow actual arguments and instructions.

This additional review did not re-prove every path for 2.7.3, BGEE, Linux/macOS,
modified UI implementations or modded class/kit tables. Existing instruction
tests for opcode104 are evidence about awards, not about this level-up adapter.

## Existing storage and class selection

The previous native review establishes:

- MakeDualClass writes zero to base XP at `0x1402a87c6`. The old class has a saved
  level, but no independently retained exact XP field.
- GetXP's retired-class branch reads the retired level at `0x140153334`, then
  calls GetNextLevelXP using that same number. It reports the installed XPLEVEL
  threshold for the attained old level, not exact historical XP.
- GetNextLevel takes the active/inactive class IDs at `0x1402426c4`. For a dual,
  the branch at `0x1402426c9`–`0x1402426e3` selects the active class and jumps to
  the single GetNextLevelSubClass call at `0x140242919`. The old class is not
  offered another level by this path, regardless of an external bank value.

The specific vanilla Fighter example also needs careful wording. Clean XPLEVEL
has Fighter10 at 500,000 and Fighter11 at 750,000. Releasing 50,000 to a
Fighter10 balance makes it 550,000; it does **not** itself provide Fighter11.
The XP remains valuable owned progress, and alternative installed thresholds or
a larger bank can produce an actual deferred old-class level. The implementation
must read those installed thresholds rather than treating this example as a gate.

A global GetXP replacement would have wider consequences than displaying an old
balance: CheckStatsChange and script XP comparisons also use it for retired-class
cap accounting. Substituting exact old earned XP for the native attained-level
threshold changes those calculations. Keep the class-owned progression provider
and the chosen cap-accounting policy explicit; do not introduce that change as an
incidental side effect of making the level-up button work.

## Normal manual level-up flow: why one hook is insufficient

| Stage | Native evidence | Consequence for deferred old-class advancement |
|---|---|---|
| Offer the button | IsLevelUpButtonClickable copies current derived stats at `0x1402a84d1`–`0x1402a84dd`, calls GetNextLevel at `0x1402a84f1`, and compares level fields. | A pending old-class level needs an additional eligibility/target calculation; native active-only GetNextLevel never creates the old-level difference. |
| Enter the screen | ResetLevelUpPanel snapshots the base header and derived stats, then calls GetNextLevel on the sprite's actual derived object at `0x1402bf4c9`. | This is a mutable preview transaction, not a pure display. It must be entered with a coherent selected-class context and matching rollback. |
| Proficiency choices | ResetLevelUpPanel sets the fifth GetProficiencySlots argument to zero at `0x1402bf83e`/`0x1402bf851`, then calls it at `0x1402bf858`. | The ordinary screen requests active-class slots even if an external hook raised the old level. The helper's inactive branch must be deliberately integrated, along with the correct old-class kit caps and proficiency storage. |
| Other rewards | ResetLevelUpPanel calls GetNumLevelUpAbilities at `0x1402bf889`, GetHitPoints at `0x1402bfd68`, GetSavingThrow repeatedly and GetTHAC0 at `0x1402bfe04`; spell/skill choices have further class-dependent paths. | Raising a level field does not prove that HP, skills, spells, HLAs or kit rewards were granted correctly. Reuse installed rules rather than hardcoding Fighter rewards. |
| Preview writes | ResetLevelUpPanel writes its projected three levels back to base level bytes at `0x1402c0d04`, `0x1402c0d13`, `0x1402c0d22`. | A prematurely written old level can affect reactivation and effects during the screen. It cannot safely stand in for a committed bank release. |
| Commit | OnDoneButtonClick calls LevelUp at `0x1402b923d` on one normal route. LevelUp calls AddNewSpecialAbilities at `0x1402b6927` and AddNewSpellsPriest at `0x1402b692f`, using the saved pre-level stats. | Deferred old rewards need the correct old/new snapshots and exactly-once handling, not another ordinary active-class level-up with altered totals. |
| Cancel | CancelLevelUp takes the saved native header at `0x1402b17cb` and restores it to sprite+0x560 at `0x1402b17d2` onward. | A custom XP ledger/phase is outside this native snapshot. It must restore or remain uncommitted when the player cancels; reopening must not duplicate grants. |

The helper supporting inactive-class proficiency calculations is encouraging;
the screen's hardcoded active selector demonstrates why directly invoking the
existing screen is insufficient. Temporarily swapping the actor's class/dual
flags would affect usability, equipment, kit identity and effect processing and
is not a proved safe shortcut. No such operation was attempted.

The reward helper inspection supplies additional concrete constraints:

- `GetHitPoints` handles retired-class HP only in the special all-previous-levels-
  zero path (`0x140240ae8`–`0x140240afe`, `0x140240b6e`–`0x140240be7`). Existing
  dual actors take the active-class path. Raising only the retired level does
  not receive its HP through this helper. Five recorded isolated control-flow
  cases confirm that routing; their underlying HP rolls were deliberately
  stubbed and are not installed-rule HP tests. A lower RollHitPoints helper
  accepts a selected subclass, but no correct retired transaction is supplied
  merely by calling it.
- `GetProficiencySlots` can select inactive class via its fifth argument at
  `0x140245ecb`. Its calculation reads the installed class PROFS row. It does not
  apply pips or establish old-kit WEAPPROF limits; the native screen passes false.
- `AddClassAbilities` gates the selected subclass through IsUsableSubClass at
  `0x140347786`, setting its usable level to zero when unavailable. This prevents
  normal positive-column CLAB grants for a dormant old class. Its all-level
  replay option does not by itself prove safe exactly-once reactivation or
  reversal of previously permanent AP_ effects.
- `AddNewSpellsPriest` checks current subclass usability and priest slots, then
  installed spell restrictions and duplicates. It is not an independent old-
  class progression API. These checks must remain data-driven with and without
  SR; they cannot be replaced with a fixture's known spell list.

## Native reactivation follows the resulting levels

The exact usability discriminator is `CAIObjectType::IsUsableSubClass`, not merely
GetActiveInactiveClasses. At `0x14011e0e5` it reads the active class level and at
`0x14011e113` the retired level. The retired subclass is usable only when
**active level > retired level**: `cmp r14d,eax` and `jbe` to false at
`0x14011e12d`–`0x14011e130`.

Therefore, if a manual deferred Fighter level raises Fighter to equal or exceed
the current Thief level, the native usability check can make Fighter unavailable
again until Thief exceeds it. That is the existing comparison reacting to changed
levels; this research proposes no additional lock.

ResetLevelUpPanel has a one-direction reactivation branch: it compares the
projected active/retired levels and the saved prior active/retired levels at
`0x1402bf59b`–`0x1402bf5a7`. On a transition from active<=old to active>old it calls
CombineAllActiveInactiveProficiencies (`0x1402bf5b0`) and marks reactivation.
LevelUp subsequently has a special ability-regrant path at `0x1402b6934`–
`0x1402b69c4`. This does not establish that raising the retired level safely undoes
previously merged proficiencies or permanently granted kit effects. Reverse
transitions are an explicit acceptance/design gap.

## Candidate ordering and minimum missing extension

On a confirmed campaign transition, make the two owned XP balances usable within
the new allowed room **without silently writing either class's level**. If the
old class has a deferred level, an explicit manual old-class step before the next
active-class step is the most coherent candidate to investigate: active-class
level-up calculations would then see the final retired level and the native
reactivation comparison would be evaluated against it. If the old class has no
new threshold, there is no old-class leveling step to invent.

This ordering is **not yet proved safe** with the stock screen. The transition
must not silently auto-level, force a character restart, debit a bank on opening
the screen, or grant old XP to Thief. If the player cancels the old-class step,
the pending entitlement and actual actor state must remain intact. How to expose
the pending choice while preserving ordinary manual leveling belongs to the lead
design; ordering is not an anti-abuse restriction.

The smallest credible extension to prove next is a selected-class context around
the existing manual level-up transaction, not a second full character system:

1. An actor-owned exact pre-dual XP snapshot and two independent XP entitlements,
   with stable class/kit identity and no new post-dual earnings assigned to Fighter.
2. A target-level provider for the selected class using its own newly usable XP
   and the installed XPLEVEL rules, extending button eligibility and screen
   calculation while leaving the other class's committed level unchanged.
3. Class-correct reward and choice routing: inactive-class proficiency/kit caps,
   HP, saves/THAC0, skills, spells and CLAB/HLA rewards, including rewards earned
   while the class is unusable and their later activation. Required original
   choices remain manual.
4. Coherent preview, commit and cancel integration with the normal native
   snapshots; idempotent reward application and no XP/level changes on cancel.
5. Correct effect/proficiency usability after both forward and reverse level
   comparisons; preserve other mods' effects rather than blanket removal/regrant.

No complete existing EEex retired-class advancement callback was identified in
the inspected source. Generic native hooks could add these behaviors, but their
availability does not prove this multi-stage adapter. The current XP observer
prototype implements none of this extension.

## Shortest meaningful proof before implementation claims

First extend the isolated native investigation to verify class selection/reward
arguments and old/new snapshot ownership for one deferred Fighter threshold,
including active>old becoming active<=old. Then build an **uninstalled** scoped
transaction prototype only if those boundaries are understood. Its acceptance
must include manual proficiency choice, HP and kit reward preservation, cancel
and reopen, repeated transition notification, no-threshold bank release, old-only
and both-class owed levels, and eventual ordinary Thief advancement/reactivation.

Relevant variants include installed altered thresholds, an old kit with CLAB
grants, and an old caster/skill class if support is promised. The same mechanics
must not depend on a particular UI or SR installation. If that broader adapter
cannot be proven, report the exact unsupported class/reward path rather than
silently raising only level/stat fields.

## Compiled uninstalled transaction extension

The continued implementation request is addressed by actual compiled source,
not an invented claim that the engine already exposes the missing callbacks:

- `xp-banking-native/dual_transaction.h`: versioned C ABI, snapshots, immutable
  class-XP plan, preview/receipt types and required **new** engine callback vtable.
- `xp-banking-native/dual_transaction.cpp`: transaction coordinator with no game
  addresses, class toggles, bare level/stat writes or automatic hook registration.
- `xp-banking-native/dual_transaction_test.cpp`: explicitly fake detached backend
  exercising the coordinator; it does not model native rewards as proven.
- `xp-banking-native/dual_check.ps1` and `dual-check-results.json`: repeatable
  Windows DLL/test build, C export verification and optional GCC sanitizer run.

The coordinator accepts a player-initiated request with save-owner identity,
native incarnation, expected ledger revision and explicit old-class XP target.
The adapter's captured committed snapshot must confirm that target and its frozen
old entitlement. Baseline/no-bank semantics belong to the lead's policy; this
core does **not** decide whether to preserve or discard surplus at an ordinary
unbanked dual. It supports either supplied account without converting new-class
earnings into old-class XP.

Its implemented state machine is:

```text
idle -> capture + prepare detached plan -> choosing
choosing -> inspect/choose/review -> choosing
choosing -> cancel -> idle (no actor/ledger writes)
choosing -> checked atomic adapter commit -> committed
commit throws / outcome unknown / bad receipt -> commit_unknown
commit_unknown -> authoritative resolve(applied) -> committed
commit_unknown -> authoritative resolve(unchanged) -> idle
```

Only one manual screen transaction may be active in the process. Reentrant calls
are rejected. The final review also corrected a real thread-confinement defect:
the original busy flag prevented overlap, but did not reject a later call from a
different thread. The first successful Create now pins the library to that
thread for its lifetime. Every subsequent Create and context operation, including
Destroy, rejects a different thread before invoking callbacks or changing screen
ownership. Per-thread monotonically assigned identities avoid inheriting ownership
through a recycled OS thread ID. There is no migration or automatic rebinding.

The future engine binding must call the first Create from a verified native main-
thread initialization boundary: this core does not independently discover the
game's main thread. Context pointer lifetime remains the caller's obligation;
thread checks cannot make using a freed pointer or racing destruction safe.

The core checks identity and revisions again before commit, checks
that the last presented choice revision is still current, and rejects incomplete
choices. The adapter must still perform an atomic compare-and-swap when publishing
the native actor plus its progression receipt; the preflight read alone is not
claimed to close a race.

The projected and committed snapshots must preserve active class and level, kit,
native base XP, all owned XP amounts, frozen entitlement and original dual level.
Only the selected old level and the successful transaction's revisions may
change. This transaction consumes **no XP award**: campaign policy has already
made the selected old XP usable. It grants the manual progression attached to
that entitlement, without re-crediting either bank.

An already committed transaction returns its original receipt without invoking
commit again. An uncertain native outcome cannot be retried, cancelled, reset or
destroyed until `resolve` proves applied or unchanged; there is no guessed
rollback of a possibly completed class reward. The resolver must be idempotent
and read-only. This is a tested protocol, not a claim that an unimplemented
callback can provide atomic native persistence merely by promising it.

### Explicit engine capability gap

Creation rejects a missing ABI/callback or a missing required capability before
capture. The callback table is **not populated for the real engine**. The Windows
DLL exports ten coordinator functions and contains no startup loader or game
binding. A self-declared capability bit is not proof of native correctness; the
fake test backend supplies bits solely to exercise protocol branches.

| New required callback | Concrete binding work still missing |
|---|---|
| `capture` | Read verified saved ownership, exact frozen old account and actor state in one consistent transaction view. Root's policy/store are separate modules; this C ABI is not wired to them. |
| `prepare`, `choose`, `inspect` | Add selected-retired-class routing to normal manual choices, with detached complete reward preview. Stock ResetLevelUpPanel operates on the real sprite and its backups. IsUsableSubClass resolves the actual actor through its native object ID; merely passing a shadow stats pointer does not isolate that lookup. No safe all-path binding was established. |
| `commit` | Apply the full HP/proficiency/skill/spell/CLAB/HLA result and actor-owned progression receipt atomically, preserving installed rules and unrelated changes. The stock HP and active-only proficiency/level routing identified above must actually be extended. |
| `resolve` | Prove applied versus unchanged after an interrupted/erroring commit using a stable saved transaction receipt. The coordinator never invents that fact from a level comparison. |
| `discard` | Release only detached preview state. It must not silently undo or repeat live native rewards. |

If the projected old level changes native usability from active>old to
active<=old, Begin additionally requires `CBMD_REVERSIBLE_OLD_USABILITY`.
Without it, that case returns unsupported **before live mutation**. This records
the real missing adapter; it is not an alternative gameplay lock or delayed-dual
policy. The required implementation must reconcile previously merged active/old
proficiencies and permanent CLAB effects by class ownership, including later
reactivation, without deleting unrelated mod effects or double-granting AP_/GA_.
No such reversible native reward binding has been proved or supplied here.

### Initial next target (completed by the continuation below)

The following target description records the initial investigation. The later
implementation section supersedes its pending-wrapper and pending-2.7 statements.

The bounded next target is the **existing**
`CRuleTables::GetProficiencySlots` routine, 2.6.6 RVA `0x245e70`, with its inactive-
class selector set true. This is an actual engine function, not a new capability
callback used as a substitute for engine behavior. Its observed Windows x64
arguments are RCX=rule tables, RDX=CAIObjectType, R8=before CDerivedStats,
R9=projected CDerivedStats, and a fifth byte at entry RSP+0x28 selecting inactive
class. Its count returns in EAX.

The inactive branch at `0x140245ecb`–`0x140245ef4` reads the old class's before/
after levels. It selects that class's installed PROFS row and returns the
first-level allowance for 0->1, otherwise
`floor(afterLevel/RATE) - floor(beforeLevel/RATE)` at `0x140246101`–
`0x140246125`. These are native instruction findings, not placeholder test results.
No actor/stat write was identified in this helper; its own string/table work
still requires valid native objects and engine-thread execution.

A concrete next wrapper can therefore resolve and signature-check this routine
for the supported executable, validate the native struct ABI and the selected
installed PROFS row (particularly nonzero positive RATE, since native DIV has no
zero guard), and pass detached before/projected stats plus the true selector.
Offline instruction execution can check selected-class routing and the installed
table result for alternate rates and class-level layouts, with byte preservation
checks on the input snapshots. The 2.7.3 routine/signature and dependent ABI still
need their own verification before claiming that version.

That wrapper would supply only the old-class **number of new proficiency picks**.
It must not mark the full `CBMD_OLD_PROFICIENCY_CHOICES` or reward adapter capability
complete: manual weapon/style selection, old-kit limits, storing choices in the
right active/inactive allocation and later merging/reversal remain distinct work.
It also does not resolve the stock HP omission or permanent CLAB reward ownership.
No native invocation or new reward binding was installed during this review.

### Checks actually completed

MSVC x64 built the uninstalled DLL and executable with C++17, `/W4 /WX`; its ten
C ABI exports were verified. **64 scenarios / 645 assertions passed** on Windows.
GCC C++17 with warnings-as-errors plus AddressSanitizer/UndefinedBehaviorSanitizer
passed the same **64 scenarios / 645 assertions**. These are two compiler runs of
one suite, not 128 independent gameplay scenarios.

Coverage includes missing ABI/capabilities, no changes during preview/cancel,
manual choices and stale choice revision, 16 preservation-field alterations,
object-ID incarnation and ledger/actor revision races, repeated commit,
reentrancy, single-screen ownership, prepare/choice failures, unknown and thrown
commit results, invalid receipts, read-only outcome resolution, no-bank policy
neutrality, table maximum and missing reverse-usability capability. Thread tests
attempt Create, Begin, Choose, GetPreview, Commit, Cancel, Resolve, GetPhase,
Reset and Destroy from a worker while the context is idle, choosing, committed
and commit-unknown. Every call is rejected without an adapter callback; the phase
and handle stay unchanged, a competitor cannot steal the screen, and owner-thread
commit/cancel/resolution still works afterward. The fake
backend uses deterministic placeholder HP/proficiency outcomes only to test
transaction publication; they are not native reward tests.

Reproduce from the worktree in PowerShell:

```powershell
& research/xp-banking-native/dual_check.ps1 -WithWsl
```

MSVC binaries, objects and logs remain under
`C:/tmp/campaign-xp-banking-20261009/native-dual`; the Linux test executable is
`/tmp/cbm-dual-transaction-test`. No binary is packaged in the repository.
Source hashes and the exact check counts are in `dual-check-results.json`.

No game or save was touched. No real manual screen, reward callback, save/reload,
reactivation or SR/UI/kit compatibility acceptance was run. A complete safe
engine binding is not established by this core; the component remains
**uninstalled and not native-ready**. The parent owns final integration and
gameplay semantics.

## Continued native binding and ownership-capture implementation

This continuation implements actual rule calls and observation thunks. It does
not populate the complete retired-class transaction vtable or expose a component.
No game process, game directory, or save was modified. Tests execute private
compiled test processes and emulate read-only executable instruction bytes.

### Native installed-rule queries: implemented and checked

`dual_native_proficiency.h/.cpp` and `dual_native_proficiency_builds.inc` provide
five C exports: Bind, Destroy, GetSlots, GetChoiceCap and GetSkillBudget. Bind
pins one native thread and checks the executable image size and every audited
function span for both supported builds. Each query rechecks signatures before
calling an address. Wrong-thread calls are rejected before native code. No game
loader or automatic hook is present.

GetSlots calls actual GetActiveInactiveClasses, GetLevel, GetClassString,
C2DArray::GetAt and GetProficiencySlots(inactive=true). It checks the installed
PROFS FIRST_LEVEL/RATE cell needed by the native division. It follows native
row/default lookup rather than requiring the reference row order or values.
GetChoiceCap calls native kit-column resolution and class/level proficiency
limits against installed WEAPPROF, KITLIST and MAXPROFS. It accepts zero/negative
disabled limits and returns max(0,min(weaponKitLimit,levelLimit)). GetSkillBudget
explicitly selects the captured old kit/class row in installed THIEFSKL and
returns LEVEL_POINTS times gained old levels; it does not pretend the stock
active-only thief helper selects a retired class.

`dual_native_check.ps1` builds the wrapper with MSVC warnings-as-errors and runs
its compiled code plus the native calculation/class/table instructions in
Unicorn. **1,878 checked queries passed across both builds**: 1,430 slot queries
(including setup checks), 288 cap queries and160 skill-budget queries. Coverage
includes16 dual orientations, rates1/3/4/7/255, custom first-level counts,
reordered/extra/default table cells, malformed divisors, custom kit columns2/7/31,
disabled/positive caps and skill rates0/15/20/25/37. Actor, AI type, rule tables,
and before/projected stats remain unchanged. Dynamic allocations, object lookup,
CString/CRT and thread-token boundaries are substituted and identified in
`dual-proficiency-check-results.json`; this is not a live reward test.

### Before-reset receipt: implemented, detached, wire-checked

`dual_reward_receipts.lua` exposes CaptureBeforeDual(sprite,context), where
context contains ownerKey, native incarnation string, exact ledger revision,
oldClass and newClass. It checks the actual reset bridge's preparing stage and
matches incarnation, class and pre-reset XP before reading anything as a receipt.
The parent calls it before MakeDualClass's first original instruction. It never
writes the actor, publishes a ledger or changes XP policy.

The receipt captures class/kit/levels, base maximum HP and skill fields, all15
legacy proficiency bytes, the46 packed proficiency stats89–134, and all op233
records in native timed/equipped lists. EEex_Sprite_GetActiveStats selects derived
versus temporary stats exactly as native GetActiveProficiency does. Duplicates
and order survive; unrelated effects are not recast as class ownership. The
receipt explicitly labels its initial evidence `unpartitioned_native_baseline`.
An aggregate observed pip value, a list ordinal or shared source resref does not
prove a temporary/item effect belongs to a class.

Signed native int32 fields are normalized to unsigned32 bit patterns, with
`signedInt32Encoding=uint32_twos_complement`, avoiding the current serializer's
negative-width defect. `op233_words_v1` packs each effect as one ASCII-hex string:
ordinal, the module's ordered unsigned words, ordered signed words as unsigned
bits, then four length-prefixed resrefs. DecodeEffect reconstructs named fields.
This is evidence, not a replayable complete CGameEffect or an effect identity.
The ledger revision accepts all exact Lua integers through2^53-1.

`dual_receipts_check.py` passes **47 scenarios in each of Lua5.1 and LuaJIT2.1**.
One scenario sends203 relevant op233 records through the real
`cbmbank_store.WireSnapshot`, verifies every packed value/order and retains every
record. Other checks cover signed-width edge values, reordered/unrelated/duplicate
effects, source detachment, cyclic-list rejection, both active-stats branches,
bad/late/reset-lifetime contexts and exact53-bit revisions. These are public-field
protocol fixtures, not in-engine ABI or save/load acceptance. The store's finite
overall payload ceiling still exists; this module does not bypass it.

### Actual manual-choice and per-level HP observation extension

`dual_choice_observer.*`, `dual_hp_observer.*`, and their MASM thunks compile into
an uninstalled private test DLL. They implement the specific audited native
observations, not generic promises that reward callbacks exist:

- Four calls from OnProficiencyPlusMinusButtonClick invoke native active/inactive
  proficiency setters. The choice thunks forward all four original arguments
  and the actual screen held in RDI. The wrapper records requested/before/after
  pips and screen routing, and invokes the original setter exactly once. It does
  not globally intercept item, opcode, CLAB, respec or other mod setter calls.
- ResetLevelUpPanel has one GetHitPoints call. Its thunk preserves the five native
  arguments and passes the borrowed sprite in R14 as observation context. Inside
  RollHitPoints, the contribution thunk reads R15D=level and EAX=the exact rolled
  contribution **after** native division/minimum handling, before accumulation.
  It restores flags, all volatile integer/XMM registers, then replays
  `add r13d,eax; inc r15d`. It does not call rand or reroll an existing result.
- HP batches retain before/after native level slots, the returned aggregate and
  exact per-level samples. A mismatched sum, invalid sequence, unread prior batch,
  overflow or native exception remains incomplete/uncertain. Native exceptions
  propagate; no reward rollback or successful receipt is invented. Manual-call
  assembly includes native unwind metadata. The noexcept contribution observer
  has no external callbacks or allocations.

Exact2.6 locations: manual HP call RVA0x2bfd68; per-level accumulation0x24adb1;
manual proficiency calls0x2bdcbb/0x2bdcc9/0x2bdd67/0x2bdd6e. The2.7 equivalents and
original instruction bytes are generated from their full disassembled functions
in `dual-hp-check-results.json`. Function names alone are not used as proof.

`dual_hp_check.ps1` builds both observer protocol tests and both assembly thunks
with MSVC/MASM. **68 instruction checks passed across2.6 and2.7**. Unicorn runs
the compiled thunks, verifies original argument forwarding/alignment and compares
all registers/flags against the actual displaced native instructions after a
deliberately clobbering observation call. The separate C++ tests exercise event
ordering, thread-constrained reads/acks, no unacknowledged overwrite, exceptions
and fault reporting against simulated originals. Those simulated results are
not native HP, proficiency, randomness or class-reward acceptance.

These are not installed hooks: no game code patcher/loader is supplied here.
The generated source-bound profiles establish candidate sites; a future installer
must validate them and their surrounding native ABI, use reachable call relays,
retain unwind correctness and roll back partial installation. An observation
entry invoked off-thread/reentrantly preserves the original native call instead
of changing ordinary gameplay, and cannot supply a valid ownership receipt.
The observation buffers contain borrowed native pointers, not durable identities.

### Concrete remaining integration and correctness gates

1. Attach the actual observer events to the verified native actor lifetime and
   saved owner **at capture**, then bind a native manual-screen begin/commit/cancel
   journal. Raw pointer reuse must not transfer an old event. The current C++
   Peek/Acknowledge APIs only expose observations; acknowledging is not committing
   a reward. The parent may already persist the pre-reset receipt separately.
2. Capture initial new-class allocations and automatic class grants as distinct
   owned events, then accumulate accepted active-class choice deltas. Do not
   reconstruct either class's allocation from the later max(active,inactive).
   Native CombineActiveInactiveProficiency clears inactive bits, broadly modifies
   op233 matches and writes that max:2.6 RVA0x38f9de–0x38fa29.
3. Preserve native HP-cache samples across screen refresh/cancel semantics. At
   ResetLevelUpPanel0x2bfd12–0x2bfd4d, matching proposed levels reuse
   sprite.m_nLastLevelUpHPRoll without calling GetHitPoints. Observing just new
   rolls is insufficient if a later commit reuses a cached roll with no receipt.
   No aggregate HP polling or threshold reconstruction can recover those samples.
4. Bind detached manual old-class choices, actual HP/skill/spell/CLAB/HLA rewards,
   and an atomic commit/recovery receipt. The implemented budgets and observations
   do not make these mutation callbacks real. Stock GetHitPoints's dual path
   rewards only active levels beyond the old level; native old-level increment
   alone still omits rewards and bypasses player choices.
5. Reversible class usability remains the hard reward-ownership obstacle. Native
   RemoveClassAbilities removes AP_ effects from both lists by shared source
   resource and GA_ abilities by resource, not by class grant instance. Arbitrary
   AP_ spells can also cause permanent/instant changes which cannot be undone by
   deleting a remaining effect. Calling that routine blindly can delete unrelated
   mod grants or fail to undo old rewards. An exact class-grant capture/application
   adapter is still required; no such complete binding has been established.

Old-class native reactivation continues to follow actual levels. Nothing here
introduces a reactivation lock, delays dual-classing, auto-levels the old class,
changes the settled separate-bank policy or chooses how unbanked between-level XP
should be allocated. The HP overlap policy is not silently selected either:
the observation code preserves the actual samples needed to discuss/apply it.
The prototype remains **uninstalled and not native-ready**.

### 2026-10-09 continuation: manual scope, native old HP and combined flow

The earlier statement that no observation loader/manual lifetime binding exists
is superseded. `dual_manual_session.*`, `dual_manual_lua.cpp`,
`dual_manual_hooks.lua`, and `dual_manual_receipts.lua` now provide concrete
ResetLevelUpPanel/LevelUp/CancelLevelUp wrappers and actual Lua exports. They pin
engine thread, saved owner and native incarnation; observe accepted choices;
retain per-level HP rolls across native cached cancel/reopen; and write a
serializer-checked pending journal before preview and commit. Native exceptions
remain uncertain. The loader verifies both source-derived profiles, prepares
reachable relays, and restores original bytes after partial patch failure.
It remains inert until explicitly installed. No installation was performed.

Checks:68 compiled-thunk instruction comparisons across the two engines;
13 journal scenarios per Lua5.1/LuaJIT2.1;20 loader/profile/rollback scenarios.
The C++ screen tests use simulated originals and are protocol tests, not native
HP/proficiency/CLAB outcomes. A save/reload cannot reconstruct native screen
backups from the pending journal alone; recovery and serialization exclusion
must be completed before deployment.

The clean pre-dual receipt now comes from `CaptureBeforePreview` at the actual
StartEditing(DUALCLASS_CLASS) boundary. It has captureBoundary
`before_dual_preview` and intentionally no newClass until that choice exists.
The later CaptureBeforeDual snapshot is labeled `before_native_reset`: accepted
new-class preview choices may already have changed inactive proficiency bits.
Neither aggregate effect list is described as exclusively player/class owned.
51 receipt scenarios per Lua runtime pass, including203 op233 records through
actual WireSnapshot. Root/reset worker owns installation of the earlier hook.

`CBMDP_RollOldHP` is a concrete native binding, not a mocked capability. With
explicit captured old kit and private scalar level projections it calls native
GetHPCONBonus and the higher RollHitPoints overload with old class for both class
arguments, divisor1 and useKit1. The native helper resolves installed HPCLASS,
loads its HP table, applies the native maximum-HP option, dice/minimum rules and
RNG. Each selected old level has its exact base-roll contribution returned.
The actual actor's class/XP/level/stats are unchanged. This consumes real native
RNG if called in an engine; the future manual adapter must cache the result and
must not retry after an uncertain native failure. CON-derived HP is not added a
second time. Offline256 cases execute compiled binding plus real HP instructions
across16 dual orientations and both builds, with custom kit mappings, reordered
HP columns/rows, varied dice/fixed gains/minimum rolls and max-HP modes. Resource
I/O, CString/CRT environment and deterministic RNG are explicit emulator stubs.
The native query suite including setup/regression checks totals2390 at this
milestone; subsequent result JSON is authoritative for extensions.

Approved overlap policy is implemented in `dual_hp_replacement.lua`: replace each
already-owned active-class contribution with that level's old contribution;
never add both or keep the larger. A missing overlapping exact sample rejects
that reconciliation, rather than reconstructing it from aggregate HP. Negative
HP deltas are persisted as uint32 bits with an explicit signed schema.25 checks
per Lua runtime include actual WireSnapshot. Native positive leveling adds the
same gain to base maxHP and currentHP (2.6ResetLevelUpPanel0x2bfdeb/0x2bfdf6).
CurrentAfter preserves this missing-HP relation; a living result is bounded to
1..resulting native maximum, and nonpositive/dead currentHP is preserved. This
is a detached plan/calculation, not an installed actor HP mutation.

The supported combined manual design has been refined with the lead: process
all pending old-class choices before active-class choices in one level-up
transaction, analogous to a multiclass manual action. Outside that manual action,
only actual selected levels affect usability. There is no entitlement-level
IsUsable override and no extra reactivation lock. The lead's chronological shared
cap allocation leaves active usableXP zero while the old bank remains; adopted
existing duals have no deferred old entitlement. Consequently old class is still
inactive when this supported combined flow begins. Validate that semantic
invariant, retaining and explaining an externally inconsistent actor rather than
attempting to reverse arbitrary previously granted AP effects. This avoids the
otherwise real shared-resref/permanent-AP reversal problem in supported flow.

Source still requires a concrete combined retired-choice routing extension:
stock ResetLevelUpPanel calls GetNextLevel for active class only, obtains active
proficiency budget, and stock CancelLevelUp restores active proficiency setters
only. Mode0x19 is DUALCLASS_PROFICIENCIES and eventually invokes MakeDualClass;
it must never be reused as a retired-level screen. Deferred inactive choices
must stay detached until the combined transaction owns their rollback/commit.
Stock LevelUp grants new specials and priest spells, then uses its reactivation
flag to replay old specials; retaining that native path after old-first projection
is preferable to independently firing old AP/GA resources. Current session code
captures the normal active screen; it is not yet that full combined extension.

No game was launched, no game or save was modified, and no production component
or complete native-ready deferred-level adapter is claimed.

### Installed target and old-only entry continuation

`CBMDP_GetOldTarget` now calls the actual `GetNextLevelSubClass` against a private
single-class scalar projection containing the owned old usable XP. It reads the
old class row through native `GetClassString`, and preflights each decimal level
column using the installed XPLEVEL table and its default. It does not assume
level 40, table ordering, a vanilla XP threshold, or a fixed terminal column.
The guard prevents malformed/nonterminating byte-level wrap; it does not require
a fixture's progression. Actual engine instructions and compiled binding pass
288 target cases across both builds and 16 dual orientations, including levels
beyond 40, level 255, reordered columns, terminal defaults and malformed input.
The full query/mutation-primitive regression now passes **3,414 checks**; the
result JSON distinguishes target/HP/skill cases from their setup slot checks.
No actor or rules field is changed by the target query.

The earlier skill milestone is also concrete: `CBMDP_ApplyOldSkills` invokes the
real seven-field `SetSkillValue` only after installed THIEFSKL budget, monotonic
selection, exact current base-skill concurrency and inactive-class validation.
224 mutation/rejection cases across both builds preserve every unrelated actor
byte. This is not yet attached to combined Begin/Cancel/Commit. In particular,
it must execute after native backups exist and before an active projection makes
the old class usable; calling it before the backup would defeat Cancel.

The stock button's eligibility defect for old-only levels is proven. In 2.6,
`IsLevelUpButtonClickable(sprite)` calls `GetNextLevel` at RVA `0x2a84f1` on its
private stack stats copy, using actor type at `+0x4b50`. It compares all three
level fields, then applies actor-state `0x800` and opcode 216 restrictions. The
native routine also retains local/multiplayer ownership checks. The ordinary
button calls `StartEditing(0x1c)` at RVA `0x2aabeb`, after its stop-actions message.
The two corresponding 2.7 callsites are derived from actual instructions in
`dual_entry_profiles.lua`, not guessed by address delta. Evidence is retained in
`dual-owned-entry-26.txt`, `dual-owned-eligibility-26.txt` and the profile report.

`dual_entry.*` implements a scoped `CBMDE_Check`: only during this read-only
check, its callsite replacement adds the selected old target to the PRIVATE
eligibility projection. Outside that scope the original query runs unchanged.
It validates native identity/incarnation, serialization exclusion, engine thread
and the supported old-inactive entry invariant. It cannot grant a level or open
a screen. A native pending-spell-pick branch cannot bypass denied control because
the private old query must actually have run. **32 actual native eligibility
instruction cases** cover both builds, both old slots, old-only eligibility,
ownership, network ownership, incapacitation, level drain and pending spell picks.
Derived-copy/environment/effect-presence/progression-query boundaries are declared
stubs in this particular check; native progression has the separate proof above.

`dual_rules_lua.cpp` and `dual_rules_bridge.lua` expose the real target resolver
through the active Lua provider, using current EEex actor/rules pointers. They
perform no detours. `dual_entry_hooks.lua` binds the concrete entry query and
patches only the audited eligibility call; its Lua check uses the actual
`m_pEngineCharacter`. Both loaders are inert until explicit research installation.
The source-bound DLL signatures/exports, dependency ordering and partial-byte
rollback pass **20 loader scenarios** across Lua 5.1/LuaJIT 2.1 and both builds.
The C++ Lua bridge protocol test confirms wrong-thread calls invoke no Lua
provider callbacks. These tests do not prove a rendered menu or live installation.

The parent now supplies `R.OldProgression(sprite)` with save owner, exact revision,
incarnation, old/active class, captured old kit, current old level, old/active
usable XP and clean-history availability. `dual_retired_controller.lua` connects
that concrete provider to the native target and entry queries, and revalidates
before a pending journal could be published. Sixteen protocol scenarios per Lua
runtime cover stale owner/lifetime/revision/entitlement and preserve ordinary
equipment changes; there is no aggregate HP/proficiency equality fingerprint.

The combined native preview wrapper now compiles: it projects the selected old
level only inside the real native manual scope, and computes active HP using a
private before-copy whose old level already equals the selected target, then
adds the exact cached old samples. This avoids native GetHitPoints skipping the
active gains when old levels change. Its current tests are **protocol tests with
simulated native originals**, not final reward acceptance; no loader currently
installs the combined projection and no retired choice popup is shipped.

The concrete remaining integration obstacle is proficiency preview rollback.
Stock Reset merges inactive/active pips BEFORE displaying the active page, but
stock Cancel restores active setters only. Deferring merge until Done would let
the player allocate against unmerged values and could discard choices. The
parallel `dual_prof_commit.*` work owns exact record transforms and the no-SET
private carrier; combined integration must apply them in PREPARING after backups,
capture native merge/materialization changes, and restore the old side precisely
on Cancel. Merely retaining an aggregate receipt is not that restoration proof.
The UI/skill/HP/CLAB commit path remains uninstalled until this transaction can
be completed coherently. No game process or save was touched.

### Integration milestone: real normal-button and owned allocation routes

The following supersedes the earlier unbound-entry/merge status. The private
`dual_combined_hooks.lua` now configures the actual allocation DLL and native
combined wrapper through `dual_manual_hooks.Install`'s explicit `combined`
option. It patches the two audited Reset GetNextLevel calls, the one CombineAll
call, twelve native proficiency UI getters, and the FIRST LevelUp
AddNewSpecialAbilities call. Together with the existing nine manual boundaries
this is 25 source-bound patches. None has been installed into a game here.

The required EEex stats constructor/copy/destructor hooks are preserved. The
profile validates all original body bytes except the exact five-byte EEex
after-call sites, where it verifies the known label, jump and relay's original
first native callee. Requiring a completely pristine body would wrongly reject
EEex itself. ProcessEffectList is bound by complete untouched entry instructions;
its deeper EEex hooks are not replaced.

The owned UI getters read native permanent class-record allocation, not temporary
SET/additive/equipment aggregates. The exact source getter sites and native
argument setup are in the parent's `dual-active-ui-evidence.md`. Owned active
choices call the sibling's `SetActiveOwned` and retain native force-reload:
actor+0x4ba4=1, ProcessEffectList(actor,1). All four actual plus/minus callsites
pass immediate=1. The original setter's class-bit copy is not called a second
time. The native UI still computes budget/cap and refreshes its page. Outside
the owned scope, all calls use the original native functions. Old choices are
accepted only on the detached first page, never through mode0x19.

At actual reactivation the exact class-record merge uses the sibling's
ApplyPreview/Restore/Complete transaction. If active levels remain below the
newly selected old level, `AfterReset` instead opens BeginActivePreview without
merging the inactive bits. Both preserve exact class allocation on Cancel. The
old-only path persists new old pips as inert timing9 carriers after native
commit; later actual reactivation consumes those carriers once. These records
are earned allocations that copy with the actor, not a current-bank-owner
restriction. Unknown externally removed/replaced tracked nodes are a recovery
condition, never a reason to dereference stale effect pointers.

The parent reproduced and proved the CLAB double-grant path in 320 native
routing cases. `CBMDL_AddSpecial` now gives only the FIRST native call a private
before-copy with old level=selected target. This suppresses a duplicate old
interval in that first pass while preserving the active interval; the stock
reactivation replay delivers old1..target once. Dormant old rewards remain
suppressed by the native usability check. This does not claim that arbitrary
post-dual rekit/respec maps the captured old kit to a different current CLAB.

Old selected base skills use the real installed-budget/native-SetSkillValue
binding at the FIRST Reset GetNextLevel boundary: backups already exist and
the original active projection has not yet made the old class usable. The
second GetNextLevel call does not apply them again. Native Cancel restores its
base backup. Row availability and bonus-adjusted limits are provided separately
by the parent's concrete skill binding; the flow must not invent an all-skills
allowance merely because THIEFSKL grants points.

`dual_entry_hooks.lua` now optionally detours the two native record-screen
methods, without requiring a modification of an arbitrary main .menu layout.
Clickable consults the scoped old eligibility query and retains normal native
restrictions. Click resolves the selected party actor through the same screen
virtual selection method, party table and GetDeny as the original. Protected
Lua routing has explicit pass/handled/reject states. Continue revalidates the
selected actor and invokes the original OnLevelUpButtonClick under the scoped
read projection, preserving its stop-actions and normal StartEditing(0x1c).

`dual_retired_flow.lua` connects the actual parent OldProgression provider,
native installed target/choice rules, detached picker, native screen and actual
WireSnapshot journal. Accepted account/choices/base-skill evidence/old HP samples
are saved in `pendingManualProgression.retired` before original Reset runs. An
`oldManualHPPreview` claim is saved before native RNG; successful samples survive
Cancel/reopen without rerolling. An uncertain roll keeps its claim and journal.
The cache is keyed by the owed class/level interval, not Constitution changes;
it keeps the original roll's Constitution as evidence. The actual row provider
rechecks skill availability, unchanged base allocation and current bonus-adjusted
cap before closing the picker and again before publishing the manual journal.
Failed picker preparation closes its native catalog; a failed menu-close clears
the pending launch so no later screen can consume stale choices.
Ordinary active-only progression with a clean, still-dormant old class binds
target==before and zero new old choices, retaining the later reactivation path.

Focused offline evidence at this milestone: 40 entry/rules loader scenarios,
48 combined-loader scenarios, 20 default-manual-loader regressions, 26 actual
journal/store scenarios, and 16 flow/controller/picker/store handoff scenarios
across Lua5.1/LuaJIT2.1. The loader tests use actual modules/profiles/DLL exports
against explicit synthetic host memory; they do not execute AsmJit or render
the native menu. Compiled C++ protocol checks cover context, owner/thread,
selection parsing, native-call argument order, cancel/commit routing and scoped
CLAB before-copy. Their helper doubles are not evidence of native HP/pip rewards.
The separate actual engine instruction probes remain the native-rule evidence.
The current native-rule run passed 3,478 cases, including the real composite
old-target-to-HP-roll and old-target-to-skill-application wrappers. The main
observer DLL was rebuilt, with 68 compiled observation-thunk checks passing.

Private bootstrap order (integration owned by the parent): root identity/account
and cap/reset bindings; rules bridge Install; construct receipt adapter and
flow; install manual scope with adapter=flow and the combined/proficiency/rules
DLL dependencies; install concrete skill/HLA data bindings; install the owned
popup; finally install entry hooks with router=flow and the private callback ABI
helper. Everything is configured on the engine thread before gameplay resumes.
Any later startup failure requires the parent's aggregate patch rollback, not
continuing with a half-configured button route. The rules helper and main manual
DLLs are built by dual_native_check.ps1 and dual_hp_check.ps1 under
`C:/tmp/campaign-xp-banking-20261009/native-dual`; the sibling's allocation DLL is
under `.../native-prof-commit`. The parent has supplied installed row assembly
and the concrete skill helper under `.../native-skill-rows`; HLA catalog and
durable dormant delivery remain coordinated parent/sibling work. This is not a complete,
deployed, or live-accepted component. No game or saves were touched.

### Final integration corrections and compact history

The normal Reset entry now consumes an explicit tri-state protected Begin result:
1 binds an owned journal, 2 passes through to native Reset only before any owner
binding/native mutation, and every other result retains an uncertain owned scope.
Identity eligibility alone did not prove campaign/account ownership. The real
root `ManualOwnership` query supplies that distinction. Numeric Begin/error ABI
is included in the parent's actual EEex/AsmJit poisoned-stack verification.
Compiled tests cover unowned pass-through, invalid/error results and an attempted
pass-through after owner binding; that last case is correctly rejected.

The menu loader is registered through the pinned AfterMainFileLoaded listener,
covering initial menus and F5 reload. There is no early bootstrap uiLoadMenu call.
Reload closes only a detached picker and its native catalog. Uninstall removes
only the exact owned listener from the public array. The native manual session
has separate journal/Cancel semantics and is not silently dismissed by reload.

The flow now prepares the real scoped active-HLA marker context after its owner
binds, including later active-only sessions with pending old choices. It stages
the parent's durable queue before native Commit and runs that queue's actual
reactivation-only delivery afterward. Commit/Cancel/Uncertain clear the detached
native predicate context once. The sibling owns the HLA native delivery and exact
predicate hooks; their independent native evidence remains separate from this
flow protocol test.

`dual_manual_ledger.lua` replaces unbounded completed full snapshots with compact
semantic records and one latest diagnostic AFTER snapshot. Each record preserves
exact per-level HP, initial/final native proficiency intent per class/stat bucket,
base-skill before/preview/after observations, explicitly selected old prof/skill
deltas, installed class/level/kit and session/revision provenance, old HLA choices
and their durable queue stage reference. Arbitrary base-skill changes and adopted
aggregate pips are labeled observations, never reclassified as class-owned.
Historical owners use an immutable dictionary reference, so a legitimate CHR
reassociation changes the ledger's current owner without rewriting earned history.
Repeated +/- clicks collapse to their first basis and final accepted allocation;
they are not multiple earned rewards. The old clean pre-dual baseline is untouched.

The latest diagnostic is superseded when a new pending BEFORE is captured. Pending
BEFORE retains full effect evidence; PREVIEW keeps only reward-relevant base and
proficiency observations. Exact native node rollback remains owned by the C++
transaction. No semantic reward record is trimmed to satisfy serializer bounds.
The test initially caught a byte-budget overflow after duplicating each historical
owner string; dictionary references fixed it without reducing coverage.

Current focused results: 30 real receipt/store scenarios, including 508 successive
protocol commits with 203 op233 records and all saved histories decoded; 22 flow
scenarios; 48 entry/rules loader cases (configuration buffers freed on success,
native rejection and exception); 48 combined and 20 ordinary manual loader cases.
The compiled manual protocol and 68 actual observation-thunk cases pass. The
3,478 native-rule cases include actual composite old-target/HP and old-target/skill
wrappers. These are offline evidence, not rendered-menu or live-engine acceptance.
