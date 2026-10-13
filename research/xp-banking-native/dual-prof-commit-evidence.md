# Retired proficiency allocation: bounded native evidence

This is uninstalled research. No game was launched and no live save or game
resource was read or written. The two explicitly named `Baldur.exe` files were
read as PE data. `dual_prof_commit.py` records their SHA-256 hashes.

## Findings that changed the design

The native extended proficiency range is stat 89 through 134. Its packed
allocation uses bits 0–2 for the active class and bits 3–5 for the inactive class.
The remaining bits are preserved by our allocation edits.

* `SetInactiveProficiency` reads aggregate derived stats and replaces the entire
  amount in every timed opcode233 record whose full parameter2 is the stat and
  whose timing is 9. It can copy equipment or temporary active bonuses into the
  permanent base. Its exact matcher is visible in `ModifyAllOfType`.
* Mode0 opcode233 is assignment, with the last evaluated SET winning. Independent
  permanent SET records are therefore merged from their own class allocations;
  their distinct unrelated fields and order are retained.
* Native mode1 is not a safe general carrier. On both pinned builds, Axe92 writes
  derived stats directly and can be masked by a later temporary SET. Halberd99
  adds to bonus stats and then adds through the pointer in uninitialized caller
  home space. The probe reproduces an access fault with a poisoned home pointer.
  No global native effect fix is included.
* An equipped SET is evaluated before the timed list. A timed-list SET underlay
  therefore still overrides an earlier equipped SET. A newly earned class SET
  follows that native precedence; equipment totals are never copied into its
  class base.
* Stock `CombineActiveInactiveProficiency` also uses aggregate stats. A class
  SET with active1/old3 followed by temporary SET0 is permanently rewritten to0;
  temporary SET4 instead makes the permanent allocation4. The new transaction
  therefore replaces only the owned manual-screen merge with a class-record
  merge. It does not replace global native merging.
* Giving a dormant carrier a live high-bit bonus is insufficient: a later
  ordinary `SetActiveProficiency` copies those high bits into its permanent SET.
  The carrier must remain inert until the owned reactivation preview.

## Persisted representation

The earned dormant increment is a timing9 opcode233 record with full parameter2
`0x0000FFFF` (mode0), amount=pips1–7, amount2=real stat, amount3=schema1,
sourceRes=`CBMDPRF`, and a 32-character provenance owner in scriptName.

Actual native mode0 dispatch returns1 without changing actor or effect for this
out-of-range stat. This remains true with a poisoned home pointer. No opcode
hook is necessary, and removing our handler does not turn the carrier into an
unsafe native additive effect. That proves inert fallback, not release/disable
or removal of EEex as a whole.

Full native v2 `CGameEffectList::Marshal` and `CGameEffect::CopyFromBase` preserve
these fields on both builds. Only the output allocator is substituted in that
test. The resource copying/uppercasing, memset, and security-cookie code execute.
This is an EFF codec check, not a complete saved-game roundtrip. Provenance is
not checked against the current bank owner when reading an earned carrier;
native clones and CHR copies retain the static earned allocation.

## Exact allocation bucket and transaction

Only timed-list opcode233 records with **full** parameter2 equal to the selected
stat89–134 and timing9 are the native class allocation bucket. Equipped records,
temporary records, and nonzero-mode additive records are excluded. No record
count, position, incoming level, English text, or reference-game value is a
prerequisite. Internal linked-list consistency is checked before mutation.

The native setter does not encode a stronger distinction between ordinary class
SETs and a mod's permanent SET grant in this same bucket. The primitive cannot
invent that missing provenance. It follows the bucket the native class setters
themselves own and preserves all fields except the relevant allocation bits.

`ReadOldAllocation` uses the last matching class SET's old bits plus all supported
inert carrier deltas; no SET means zero class base. `ReadActiveAllocation` uses
the last class SET's low bits. Unknown or malformed private carrier schemas are
preserved and stop dependent old-allocation work rather than being guessed away.

`ApplyPreview` requires the real `CBMDS_Query` PREPARING scope and matching actor,
owner, session, and incarnation. It merges every native class record from its
own active/old base plus earned delta, clearing the inactive bits. A missing SET
gets a normal persistent class SET with active=earned delta and an explicit
private creation marker. An obscured earlier record may saturate at the native
three-bit maximum; the effective last allocation must still represent the full
earned result. The supplied row budget and installed kit caps remain the caller's
responsibility.

`BeginActivePreview` handles active levels still below the retired target. The
caller invokes it after native Reset skipped CombineAll, still in PREPARING.
It snapshots class records without changing the actor, merging old bits, or
consuming carriers. Active-only Complete retains existing carriers; the caller
then persists any newly selected retired rows through `PersistDormant`.

`SetActiveOwned` is restricted to the transaction's PREVIEW phase. It writes a
final class-basis value, retains unrelated fields, and tracks any new SET node
for cancellation. It enforces the initial effective active allocation as the
floor, independently of later temporary/equipment effects. The owning native UI
wrapper must perform the setter's force-recalculation branch (actor+4BA4=1,
ProcessEffectList(actor,1)) before the existing caller refreshes the panel. The
caller itself only refreshes the panel; replacing the setter would otherwise
omit the immediate recalculation.

New-record insertion is not claimed to duplicate generic AddEffect admission.
The stock new-SET branch runs CheckSevenEyes/CheckAdd, copies current derived
stats to its backup, resolves the record, appends it, and calls ProcessEffectList
with0. Our scoped class-allocation primitive owns its exact record and inserts
it directly. A plain timing9 opcode233 Resolve/Apply only writes the selected
derived proficiency and does not mark the record done. Full new-node UI/recalc
integration remains distinct from the isolated primitive checks.

After normal native Cancel, `Restore` restores the original six allocation bits
of each affected original node, preserves current unrelated fields and effects,
and removes only nodes created by this transaction. After successful native
commit, `Complete` removes the exact consumed inert carriers and preserves the
accepted active choices. `PersistDormant` handles old-only commits by creating
inert earned increments without merging class SETs; its `Complete` merely
acknowledges the receipt.

The full CancelLevelUp source restores base and derived snapshots, but does not
replace the actor's timed effect list. The focused native Cancel probe executes
its real proficiency loop (2.6 RVA2B196A–2B19CA; 2.7 RVA2B1FEA–2B204A), real
SetActiveProficiency/ModifyAllOfType, and real HandleList/ResolveEffect/opcode233.
Across 47 class SETs plus an inert carrier, temporary SET, and additive record,
all original node and effect identities survive. The additive record performs
its ordinary firstCall/amount2 bookkeeping, explicitly checked. The installed
WEAPPROF index lookup is a declared fixture mapping; ProcessEffectList routes to
its real timed HandleList only, not the whole game recalculation pipeline.
Consequently arbitrary external effect deletion/replacement still requires the
identity guard and recovery evidence; the probe does not justify removing it.

The native bridge returns1 on success,0 on a failed precondition before actor
mutation, and -1 for uncertain native mutation. The transaction remains available
for recovery evidence and cannot be automatically replayed. Snapshot export gives
node/effect identities and full before/after serialized bases; pointers are not
save identities. Durable pending-preview/recovery serialization is the enclosing
manual transaction's responsibility and is not supplied by this primitive.

## Binding and checks

The generated `dual_prof_commit_profiles.lua` contains full direct function
bodies for both pinned builds. Correct data insertion is **CObList::AddTail**:
the nearby symbol `CPtrList::AddTail` appends another list and has a different
argument meaning. The actual data-insertion, NewNode, and RemoveAt instructions
have been executed against a synthetic native free-node pool on both builds.
No opcode233 detour is installed; `original_apply` may be zero in the config.

Pinned EEex hooks `CopyFromBase` to copy EEex side data, but explicitly exempts
the actual `DecodeEffectFromBase` caller. The factory calls that real native
decoder, rather than directly calling the patched copy function on a base object.

Current focused evidence:

* 66 actual native cases per build, 132 total: SET/additive behavior, unsafe
  aggregate setter/merge counterexamples, inert fallback, v2 field roundtrip,
  linked-list data insertion/removal, and actual bonus-fold instructions.
* Two actual Cancel proficiency-loop cases, one per build, with 46 native setter
  calls and 2,300 real Resolve/Apply calls each, and exact node identity checks.
* 1,360 compiled C++ synthetic assertions: exact field preservation, real bridge
  scope contract with declared synthetic session/list/factory helpers, reordered
  class records, no-SET creation, active choice/undo, active-only preview below
  the retired target, Cancel cleanup, dormant
  accumulation, later retirement, unknown schema, failed factory, and uncertain
  insertion quarantine including object-pointer reuse with a new incarnation.
  A tracked-node removal before a later UI choice refuses the write before any
  captured effect pointer is dereferenced, retaining recovery evidence.

These do not prove complete UI behavior, live copy/save timing, arbitrary native
patch combinations, automatic preview-recovery persistence, or safe uninstall.
