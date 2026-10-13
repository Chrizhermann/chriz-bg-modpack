# Deferred retired-class HLA provider (uninstalled research)

This is a native query, preview-context, and delivery primitive. It is not a
released component and has not been exercised in a running game. Source inputs
are the pinned EEex/InfinityLoader function maps and read-only BG2EE executables
used by the other banking native probes. No saves or installed resources were
read or modified by these tests.

## Native rules and exact ownership boundary

`CRuleTables::GetNumLevelUpAbilities` (2.6 RVA `242c10`) selects only the active
class of a dual. Therefore asking it about a real dual's old-level change returns
zero when the active level did not change. The provider instead supplies a
private single-old-class AI view (`m_Instance=-1`) and private before/after
derived-stat level fields populated by native `SetLevel`. No real class, kit,
level, XP, effect list, or ability count is rewritten for this query.

The count table is installed `LUNUMAB`; the native class row uses kit `0x4000`.
Columns are `FIRST_LEVEL`, `RATE`, `CHANGE_LEVEL`, `NEW_RATE`. Native single
precision multiplication and truncation apply to each interval term, followed
by a final cap of 24. Summing one-level results would be wrong for fractional
rates. For example, a rate of 0.5 can award one point for two levels together and
zero for each separate one-level interval. The provider preserves this native
interval arithmetic, calculates the uncapped result, and checks that its capped
result agrees with the actual native return. It exposes all points: a synthetic
51-point interval remains 51, with later delivery split into 24/24/3.

`GetLevelUpAbilities` (2.6 `241690`) reads the private old class and the actual
saved old kit. Native `GetClassString` and installed `LUABBR` select the `LU...`
catalog. There is no kit-name whitelist. An interval with zero points does not
load a catalog. Positive points with no catalog remain visible as an empty
choice set; the provider never invents fallback abilities.

## Native predicate, including its asymmetric spell matching

`CheckAbilityEnabled` (2.6 `2b1cf0`) is called with the actual native flags output
from the single-class count query. Min/max fields compare numerically against
this byte; they are not masks and must not be replaced by the target level.
`ALL_GOOD` and `ALL_EVIL` alignment entries exclude those respective alignments.

The current selection prefix is compared using the full effect string with
case-sensitive `_mbscmp`. Previously earned opcode313 markers compare the
resource suffix (effect string after its first three characters) through the
case-insensitive native `CResRef` comparison. Consequently selected `GA_X` and
`AP_X` differ, but an existing marker for `X` counts for either. The provider
preserves both rules. Pending dormant selections become marker-equivalent nodes
in a private borrowed effect-list view; no marker is added to the actor.

The detached picker may hold more than24 choices. Its native predicate receives
at most one prerequisite and one exclusion representative, while the candidate
rank allowance is reduced by its complete full-string selection count. This
preserves the native predicate without overflowing its 24-byte selected array.

The actual active picker receives the same marker-equivalent context through
only two callsites: ResetLevelUpPanel and UpdateHighLevelAbilitiesPanel
(`2bf8ee`/`2c53e9` on2.6; `2bff6e`/`2c5a69` on2.7). The wrapper requires the
actual CBMDS owner/session/incarnation/screen in PREPARING or PREVIEW. Unowned
actors, unrelated screens, and other phases delegate the original unchanged.
Clear uses a token, so an old cleanup cannot erase a later session's context.

## Persistence contract and native delivery

Each detached selection contains `{id, descriptor}`. `id` is a zero-based
snapshot-local UI index, never sufficient for replay. Descriptor schema1 is:

```
icon, nameStrref, minLevel, maxLevel, maxRank,
effect, prerequisite, excludedBy, alignment
```

The four numeric fields are persisted as unsigned32 bits; min/max/rank decode
to signed32 before native hydration. This avoids EEex serializer signed-width
gaps without losing native values. Strings retain their original case. No
native pointer, object ID, catalog handle, or callback is persisted.

`CompleteCharacterHighLevelAbilities` (2.6 `2b2cb0`) clones selected descriptors,
dispatches `GA` to AddSpecialAbility or `AP` to a self-targeted FireSpell, adds
opcode313 resource markers, and frees the input catalog. It does **not** test
class usability. Our delivery therefore requires real CBMDS COMMITTING, exact
saved owner/lifetime, and actual `CBMDL_IsDormant(oldClass)==0` before firing.
The parent queue retains dormant selections until reactivation.

The helper constructs real CAbilityData/CGameAbilityList objects using native
allocation, CString, array, and destructor functions. Every batch is allocated
before actor delivery begins. It invokes the actual completion function in
ordered batches of at most24. Reentry/exception after delivery starts yields
uncertain status and is not automatically replayed. The parent must persist its
full pending receipt before calling and retain it on uncertainty. A native
same-session guard prevents a second attempt; it is not a cross-save receipt.

Lua APIs: `Open(sprite,account,target[,priorDeferred])`, `Pending(sprite)`,
`PrepareManual(sprite,account,target,choices[,priorDeferred]) -> token`,
`ClearManual(token)`, and
`Deliver(sprite,oldClass,owner,entries) -> status,completedBatchCount,uncertain`.
Install accepts real runtime `PendingHLAs` / `ManualHLAs` readers and native
identity/manual modules. Merely loading any source file registers nothing.

Catalog Close consumes its handle before native cleanup; a cleanup exception
cannot cause a second free on retry. Its failure status remains visible. A
zero-selection native cleanup branch never touches the actor.

## Focused evidence and limits

* Actual PE count probe:62 cases per build, including dual omission, installed
  fractional-rate variations, and raw51/native24. Catalog selection reaches the
  real resource request for a synthetic custom old kit on both builds.
* Actual PE predicate probe:43 cases per build, including all native alignment
  outcomes, GA/AP and case distinctions, prior markers, and selected-prefix
  representative equivalence.
* Actual PE delivery probe:8 total cases across both builds, including ordered
  mixed GA/AP, descriptor cloning, exact self-target arguments, resource codec,
  marker creation,24 selections, and empty cleanup with null actor.
* Compiled C++ interface tests cover detached actor preservation, no-catalog
  zero intervals, one-shot uncertain cleanup, Lua string transport, actual
  scoped-context contracts, dormant rejection,51-choice delivery, duplicate
  attempt rejection, and partial delivery uncertainty.
* Lua5.1/LuaJIT tests cover schema/transport, lifetime changes, pending marker
  acquisition, one-shot cleanup, and exact hook preflight/rollback paths.

The PE probes declare heap, CString/array adapters and final gameplay sinks.
They do not execute HLA spells or prove all installed spell side effects. The
catalog-selection probe reaches the real resource request but uses synthetic
table rows; it is not a game-resource catalog test. Compiled and Lua tests use
synthetic native/provider interfaces. Parent account/serializer tests separately
own durable queue conservation, recovery, and cancellation. Live native UI,
actual AP/GA effects, actor unload/reload, and running-game acceptance remain
unverified. An interrupted native delivery is deliberately not advertised as
rolled back or safely replayable.
