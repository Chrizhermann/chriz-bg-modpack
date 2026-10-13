# Campaign XP banking: persistence audit

Date: 2026-10-09. Scope: source audit and uninstalled native/serializer prototype;
not an engine acceptance result. The concrete milestone below supersedes the
initial audit's unresolved copy-reason implementation question.

EEex provides an actor-owned serialization path suitable for a bank, but the
current APIs alone do **not** prove lossless banking across every required
lifecycle. In particular, copy/export discrimination, coherent native-XP/bank
commits, actor replacement, and release-and-disable remain acceptance gates.
Do not expose a working banking component on the strength of this audit.

No game or saves were opened or modified. No game was launched. No new game copy
was made. Explicitly named executable files were read as PE research inputs.
Implementation remains under `research/`; no TP2, M_ loader or production
registration is supplied.

## Source identity

The complete collection brief and the mandatory compatibility policy were read.
The modpack worktree began at `d22427a`; no production implementation was changed.

| Source | Pinned revision / local evidence |
| --- | --- |
| EEex | [`a6d21abe44e20509f5d0259ccc6c7e7f9d12b285`](https://github.com/Bubb13/EEex/tree/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285), installer version **1.3.1**; `C:/tmp/scroll-hook-research-20261009/EEex` |
| InfinityLoader | [`817925caab3eb9cf600cfaf38853da8d30c28247`](https://github.com/Bubb13/InfinityLoader/tree/817925caab3eb9cf600cfaf38853da8d30c28247); `C:/tmp/scroll-hook-research-20261009/InfinityLoader` |
| EET | [`74e91d72bca5d073fa11c1d088b90d7ff0c7105d`](https://github.com/Gibberlings3/EET/tree/74e91d72bca5d073fa11c1d088b90d7ff0c7105d); collection archive SHA256 `9834a53322b7fe9d8923bfde36c0e6bc8bef54d730d32ac29286b80d6f08287e` |

The two Git source checkouts were clean during inspection. These pins identify
the audited implementation; they do not establish the minimum supported version
or prove that an installed native DLL matches it. Capability and native-build
checks must precede activation.

## What the carrier actually does

- `EEex_GetUDAux` indexes by the userdata's light pointer. It creates a Lua table;
  it does not persist arbitrary auxiliary fields automatically. The game-object
  deletion hook removes that table before ordinary object-array deletion.
  [Assembly:1288–1319](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Assembly.lua#L1288-L1319),
  [deletion hook:13–38](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_GameObject_Patch.lua#L13-L38),
  [cleanup:487–510](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_GameObject.lua#L487-L510).
- Marshal registration selects exporter/importer by handler name. The sprite
  effect-list hooks append/read `X-BIV1.0` data in the creature serialization.
  This is an actor carrier, independent of portrait order and the party list.
  [registration:997–1004](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Sprite.lua#L997-L1004),
  [native-hook installation:184–309](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Sprite_Patch.lua#L184-L309).
- The native reader recognizes the extra data inside the effect stream; it is
  not an ordinary executable gameplay effect. A decoding failure emits a warning
  that the game may crash. This is no proof of safe loading without EEex.
  [native reader:4958–5033](https://github.com/Bubb13/InfinityLoader/blob/817925caab3eb9cf600cfaf38853da8d30c28247/EEex-Core-Shared-Files/source/EEex.cpp#L4958-L5033).

Recommendation: keep the durable ledger only in this actor-owned carrier, with
save-owned policy metadata. Runtime indexes may assist lookup, but must never
become an authoritative balance or campaign high-water mark. Clear transient
indexes when the session is destroyed; the public listener explicitly covers
loading another save.
[session lifecycle:175–224](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_GameState.lua#L175-L224).

## Copies are not one category

`EEex.IsMarshallingCopy()` returns **only** `bStripUUID`. The inspected patches
set it around both `CGameEffectCopySelf::ApplyEffect` calling `CGameSprite::Copy`
and `CInfGame::CharacterExport` calling `CGameSprite::Marshal`. Item comparison
uses the separate `bNoUUID` flag. Neither flag is a nesting counter.
[native definition:393–395](https://github.com/Bubb13/InfinityLoader/blob/817925caab3eb9cf600cfaf38853da8d30c28247/EEex-Core-Shared-Files/source/EEex.cpp#L393-L395),
[three context hooks:711–753](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Sprite_Patch.lua#L711-L753).

| Operation | Source-supported conclusion | Banking consequence |
| --- | --- | --- |
| Ordinary save / actor serialization | Registered handlers run at the sprite effect-list marshal call. No inspected patch sets `bStripUUID` for an ordinary save. | Export a read-only snapshot of the bank. Do not suppress it because of an unverified “save preview” interpretation. |
| Magical CopySelf clone | `bStripUUID` is set around the copy operation. | Exclude transfer of an eligible bank into this new actor. Never debit or alter the owner in its exporter. |
| Character export | The same `bStripUUID` flag is set. | A blanket `if IsMarshallingCopy() then return nil end` also omits the bank from CHR exports. It cannot satisfy lossless export/import. |
| Item-comparison preview | `bNoUUID` is set; `IsMarshallingCopy()` does not expose it. | No exporter may award/release XP, allocate ledger identities, or change persistent policy. A stronger context check remains necessary. |
| Direct mod call to `sprite:createCopy()` | The Lua wrapper calls native `Copy` directly; it does not set either flag itself. | A CopySelf-only guard is not proof that arbitrary mod-created copies are safe. |

Direct-copy wrapper:
[Sprite:248–258](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Sprite.lua#L248-L258).

The skill's claims that `IsMarshallingCopy` specifically means quicksave previews,
autosave thumbnails or area transitions are not supported by these current call
sites. Native disassembly now resolves the `m_bInCopy` timing: on 2.7, Copy calls
the sprite constructor at `0x140351310` and only then sets `m_bInCopy` at
`0x14035131D`. The constructor can already read the extra-effect carrier. That
field is too late for importer classification; see `identity-paths-2.7.txt`.

The extension below now exposes scoped marshal/copy reasons at those actual
entry boundaries. It preserves CHR data separately from activation of a new
run's policy/phase; live acceptance remains outstanding.

## Concrete uninstalled identity/reset milestone

`xp-banking-native/identity_native.{h,cpp}` replaces six reviewed native entry
boundaries: Copy, the raw CRE Marshal overload, CharacterExport, CharacterImport,
and EEex's native sprite constructor/destructor callbacks. The Copy scope spans
both internal serialization passes and construction, rather than ending after
the first Marshal. EEex's flags refine an already-proven Copy operation into
magical clone or item preview; an unflagged direct `createCopy` remains other
copy. CHR export has its own native scope. C++ RAII restores nested provenance
after normal or exceptional returns.

The lifetime registry binds a pointer to a new monotonically increasing runtime
incarnation at **both** constructors and erases it on destruction. It is never
the save identity. Eligible fresh actors receive a random 128-bit candidate
owner token using BCryptGenRandom; a loaded carrier retains its own durable
owner. Runtime metadata checks incarnation before using cached UDAux data.
Copies receive no candidate token. A wire-valid unknown copy payload is retained
inside a permanent excluded carrier so a later ordinary save/load cannot turn
it into an eligible bank merely because the in-memory copy scope ended.

The concrete loader uses existing EEex/InfinityLoader APIs:
`EEex_LoadLibrary`, `EEex_GetProcAddressInternal`, `EEex_ExposeToLua`,
`EEex_JITNearAsLuaFunction`, and `EEex_HookReplaceFunctionMaintainOriginal`.
Lua API addresses use the active-provider `Hardcoded_lua_*` labels, including
LuaJIT overrides. Query receives the exact actor pointer as a hexadecimal string
made from two 32-bit halves (stock Lua `%x` is unsafe for a whole 64-bit number).

Actual-source bridge review found a concrete defect in the pinned
`EEex_GenLuaCall` final pcall block: it writes `ctx`/`k` to outgoing stack offsets
0/8, inside Win64's register home area. The ordinary six-argument LuaProvider52
prototype requires outgoing offsets 32/40 (callee-entry offsets 40/48). Other
generator branches already use those correct slots. A zero-initialized test
stack can hide this defect; acceptance must poison the real argument slots and
permit callees to overwrite all 32 home bytes.

The private `callback_abi.lua` adapter now puts both continuation arguments in
their actual outgoing slots immediately before each generated pcallk call,
inside its existing alignment scope. The generator reserves the extra 16 bytes.
Reset, preview, party, award, writer, cap and manual callbacks receive this
dependency explicitly. Already-correct generators remain valid; redundant zero
stores do not change their arguments. No upstream EEex file or global generator
is replaced. Returned assembly is detached, and commented-out calls cannot
become executable calls. Nine Lua5.1/5.2/LuaJIT isolation checks cover these
adapter properties; only the separate actual-source compiled bridge probe can
establish the resulting native ABI behavior.

`CBMBank_Identity.Query(sprite)` returns `birthReason`, current `reason`, decimal
string `incarnation`, optional candidate `ownerToken`, `serializing`, `eligible`
and `canMutate`. No caller-supplied verified flag creates this authority. Missing
observed lifetime, wrong thread, or poisoned cross-thread lifetime tracking
returns no identity. Any active marshal scope blocks mutation; that guard does
not claim to make EEex's shared serializer scratch reentrant.

`reset_native.{h,cpp}` wraps both ScreenCharacter and CreateChar MakeDualClass,
with native signature `void(screen, sprite, uint8 newClass)`. The CreateChar
route prepares before the caller's RemoveAbilities call, then retains the same
actor/screen/class/lifetime context through the following MakeDualClass call.
A direct CreateChar reset cannot invent a receipt after abilities were removed.
The earlier OnDualClassButtonClick-to-StartEditing callsite captures clean state
before mode 0x18 starts preview choices. Its native GetDeny lookup establishes
the actor; `PreviewQuery` exists only inside that capturing callback. Root runtime
requires this owner/incarnation/revision/base/class/level-bound clean receipt;
the later aggregate cannot be mislabelled as exclusively old-class allocation.
Root publishes a detached `pendingDual` journal before native removal/reset.
CompleteDual runs only after ordinary return; exception or
failed postconditions retain an uncertain journal rather than inventing a
rollback. The native query reports preparing/native/completing/uncertain and
the observed incarnation, preBase, newClass and character/create path. An XP
change between ability removal and reset leaves an uncertain journal instead
of discarding the unaccounted difference. Its NativeCap method invokes
the real GetXPCap through the current Chitin/game/rule-table pointer and this
actor's start AI, rather than a cached or caller-asserted ceiling.

The tiny party native bridge preserves GetNameRef's return and calls protected
OnLoaded after that one reviewed AddCharacterToParty call. It does not replace
the getter globally. The parent-owned party probe establishes the call's position
after membership writes and before later recruitment awards.

`bank_bootstrap.lua` joins the actual identity, reset, party, award, writer,
compatibility, runtime, receipt, store and cap modules. Merely loading it does
nothing. Explicit research Install
requires EEex's real one-time early-startup flag to still be false; it refuses
hot initialization after actors could load. It checks profiles before native
writes, defines the two exact reviewed cap labels, installs boundaries before
registering the actor handlers, and preserves unrelated listeners. On failure it
restores captured bytes and removes only its own registrations. Native Configure
is one-shot: a failed attempt requires restart even after successful rollback.
It explicitly reports `experimental=true, usable=false`; it is not a finished
banking component. `bank_build.ps1` builds an inert bundle only, with no installer
or automatic startup hook.

### Bounded checks recorded for this milestone

- Windows compiled identity shim: **251 assertions**, including nested copies,
  five-argument forwarding, both serialization passes, CHR provenance, pointer
  reuse, thread refusal and exception scope cleanup.
- Compiled reset/party shim: **191 assertions**, including exact callback order,
  reentry refusal, dynamic native-cap routing, partial-native exception journals,
  getter result preservation, failed party notification, pre-preview scope,
  both reset routes, partial ability removal and mismatched continuation refusal.
- Real PE entry relocation: **60 identity comparisons** across pinned 2.6 and
  2.7 game/EEex binaries. Reset adds **20 relocation comparisons** and **24 real
  native instruction-window cases** proving XP is unchanged until MakeDualClass's
  first zero store at entry+0xA6. Another **12 caller comparisons** execute actual
  argument production and E8 calls, before/after near-JMP substitution, for
  preview and ability removal. Called helpers are explicit offline stubs.
- Actual EEex size/write/read serializer source, with offline memory and actors:
  **53 tests** (Lua5.2/LuaJIT plus inert/address Lua5.1 checks). They cover known
  and opaque carriers, save/CHR provenance, excluded copies, failed identity
  queries, old UDAux reuse, the actual runtime's partial-dual receipt/journal,
  overflow completion, saved uncertain-award/writer recovery and explicit
  unsupported percentage-with-overflow preserving the original carrier.
- Actual loader/bootstrap Lua with explicit native-host API doubles: **66 tests**
  across Lua5.1/Lua5.2/LuaJIT. They check real module wiring, partial native patch
  and registration failure, byte restoration, unrelated listener preservation,
  active-provider labels and refusal of late/modified/conflicting hosts. These
  doubles do **not** execute JIT assembly or prove an installed game starts.

The native cancel/back-navigation path still requires specific reward-ownership
verification. Returning from dual proficiency mode 0x19 calls
ResetProficienciesPanel and can move back to mode 0x18; it is not the ordinary
CancelLevelUp path. These hooks do not assert that every cancelled preview
restores old high bits/effects correctly, nor do they claim all dual rewards
are already accounted for.

### Native stat44 writer boundary

`writer_native.cpp` interposes only SetAtOffset's 30-byte XP branch, before the
common ProcessEffectList tail. A real CALL enters a typed DLL function with
compiler-owned unwind metadata, then the original actor is restored to RCX and
the native common tail continues. All other stat branches are untouched. Root
planning owns SET/loss/ADD meaning; the native bridge performs one planned base
store and completes its journal before effect recalculation can reenter.

The two installed compatibility entrypoints call the real SetAtOffset under a
native scoped origin. That origin is consumed by the first exact actor/lifetime/
target SET; writes nested during recalculation do not inherit it. **473 compiled
assertions** execute both actual extracted native SetAtOffset bodies on synthetic
actors, including unrelated stats, unsigned passthrough, single-use planning,
completion failure, nested recalc and Windows C++ unwind through the copied
native frame with its original unwind recipe. Recalculation is an explicit
test stub; this is not installed-engine execution.

### Positive permanent award overflow boundary

`award_native.cpp` now replaces actual `CGameEffectXP::ApplyEffect`, typed
`int(effect, sprite)`, at RVA `0x1CB160` (2.6) / `0x1CB370` (2.7). Its entire
224-byte body is identical in the pinned builds, SHA256
`b82b9164057049bbca1f2f7cbe5c98e3edf3595bc09aa1ab53ace0912e626c86`.
Disassembly verifies no calls, external branches or RIP-relative dependencies.
For mode 0, permanent timing 1 and signed amount 1..INT32_MAX, it adds the
per-recipient amount to base XP at sprite+0x570, sets effect done+0x114 and
forceRepass+0x118 to 1, and returns 1. Derived XP and bonus XP are untouched.
This point is already after native party splitting; the bridge never divides
the amount again.

The native wrapper captures exact effect/actor pointers and the observed actor
incarnation. BeforeAward(sprite,effect) returns disposition 1 for tracked,
2 for proven unowned/excluded passthrough, or 0 on refusal. Root runtime attempts
real adoption of eligible party actors before an award and stores pendingAward
before the original. Only a wrapping positive amount is temporarily reduced to
`UINT32_MAX - preBase`; the exact remainder is a pending overflow entitlement.
RAII restores the original effect amount before CompleteAward and on C++ unwind.
Completion checks actual return, native post-base, done/repass and lifetime; only
then does root commit the remainder into metadata. Failure retains a journal,
returns the original native result and prevents replay. Unobserved identities
are errors, not invented unowned actors. Same actor/effect reentry is rejected.

Permanent SET, percentage, signed loss and zero now enter the writer journal
through `CBMW_EffectWrite`. Its source is explicitly opcode104, with the exact
raw original amount and native effect mode; a stat44 modifier of 2 remains an
ordinary native SET and cannot be mistaken for a percentage. The native leaf
temporarily receives a permanent SET of root's planned target; RAII restores
both effect parameters before completion or exception reporting. The original
leaf still owns its done/repass stores and return value. Successful completion
requires those exact outputs and the observed planned base XP.

Root's percentage policy preserves the actual unsigned native result
`floor(((rawAmount * baseXP) modulo 2^32) / 100)` when no overflow exists. It
explicitly refuses a percentage of an overflowed account without mutating or
erasing that account. Nonpermanent and unknown effect modes remain byte-exact
native passthrough. Native prepare refusal returns 0 before native writes.
Whether every upstream caller retries or reports that failure is **not proven**;
it is not described as guaranteed lossless recovery. Ordinary successful awards
still have one authoritative native XP total, plus only a true overflow carrier.

`award_probe.py` checks the complete body on both pinned PEs and runs **48**
independent Unicorn cases. `award_native_test.cpp` also executes the actual
extracted leaf as read-only executable code on Windows, using synthetic actor
and effect buffers. The compiled wrapper tests overflow, saturation, repeated
awards, original-byte-preserving passthrough, copied/unowned actors,
permanent effect writer routing and restored parameters, reentry, exception
and completion-failure handling: **671 compiled assertions**. This is actual native leaf
execution; it is still not a launched game or an executed EEex Lua/JIT bridge.

The compiler uses `/EHs`, deliberately not `/EHsc`: an exported C ABI entry can
forward a throwing C++ engine method. A focused regression caught stale Copy
scope when the compiler assumed extern-C calls could not throw. The build scripts
now preserve the required C++ cleanup. Access violations/SEH do not become a
claimed recoverable native transaction.

Actual serializer tests also found and corrected three data-loss paths in the
parent runtime: re-exporting an excluded future-schema carrier, failed identity
export, and failed identity import. Empty export tables mean absent banking state.
No model defaults replace an unknown bank. Real CHR import still requires explicit
new-run reconciliation before its prior campaign phase can become active.

Remaining boundaries are concrete: engine execution of the generated bridges;
coverage of additional native XP writers outside these audited methods;
dual reward ownership/application and cancelled-preview restoration;
unloaded-owner release completeness; multiplayer Copy transport; and real
save/load/area/death/CHR acceptance. Generic Copy is deliberately excluded until
network transport semantics are proven. A constructor that aborts before normal
destruction is not asserted to be a valid eligible actor. No live result or
safe raw uninstall follows from these offline checks.

## Identity and actor lifecycle

| Case | What can be relied on / what remains unproved |
| --- | --- |
| Party reorder | Actor auxiliary state is not keyed by party slot. No bank movement is needed. |
| Object-ID reuse | Ordinary object-array deletion clears UDAux. Never key durable balances by `m_id`, or assume a fresh actor is the old character because its ID matches. |
| Pointer reuse | The same cleanup protects ordinary deleted game objects. Destruction of temporary copies outside the object array is not proved to use that path; avoid initializing banking state from exporters/previews. |
| Dismissal, unload, death/resurrection | If the same actor remains in memory or its serialized CRE is retained and unmarshalled, the carrier follows it. The hook location supports this path, but does not prove every native save/unload/death branch. Test each rather than assuming that all non-party actors are serialized identically. |
| Actual actor destruction/recreation | A new resource-created CRE has no automatic relationship with a discarded actor's auxiliary bank. Death variable, name, portrait and CRE resref are insufficient authority for transferring balances. |
| Old/new saves, independent runs | Import only that save's carrier. A process-wide cache must not restore data from a later save. UUIDs are save-scoped identity aids, not cross-run ledger identities. |

EEex stores UUIDs in actor locals, reloads its next-UUID counter from game globals,
and removes native UUID associations on sprite destruction.
[UUID counter:3914–3952](https://github.com/Bubb13/InfinityLoader/blob/817925caab3eb9cf600cfaf38853da8d30c28247/EEex-Core-Shared-Files/source/EEex.cpp#L3914-L3952),
[actor lifetime:4766–4839](https://github.com/Bubb13/InfinityLoader/blob/817925caab3eb9cf600cfaf38853da8d30c28247/EEex-Core-Shared-Files/source/EEex.cpp#L4766-L4839).

EET distinguishes continuing actors from fresh campaign actors. Its NPC helper
uses `MoveGlobal` for the existing SoA companion when summoned into continuing
ToB, and `CreateCreature` for a direct-start default. It also injects conditional
`DestroySelf` cleanup for actors outside their retained campaign membership.
Therefore campaign support cannot assume every old NPC CRE survives or that a
fresh same-name NPC should inherit its bank.
[EET existing/new ToB paths:529–569](https://github.com/Gibberlings3/EET/blob/74e91d72bca5d073fa11c1d088b90d7ff0c7105d/EET/other/EET_functions.tph#L529-L569),
[cleanup templates:228–259](https://github.com/Gibberlings3/EET/blob/74e91d72bca5d073fa11c1d088b90d7ff0c7105d/EET/other/EET_functions.tph#L228-L259).

For the initial scope, continued-actor transport is the plausible supported path;
any destroy/recreate continuity requires an explicit, separately validated
transfer contract. The separate campaign audit owns exact transition detection.

## Unknown schemas, handler errors and the wire boundary

Importer/exporter failures are caught by `EEex_Utility_TryIgnore`. Import failure
does **not** enter missing-handler fallback; export failure does **not** reserve
the old handler record. Fallback is used only when the handler is absent and is
exported independently of registered handlers.
[handler dispatch and fallback:1284–1345, 1447–1454](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Sprite.lua#L1284-L1454),
[error handling:172–189](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Utility.lua#L172-L189).

Required design consequences:

1. Retain an imported, wire-valid payload before interpreting its schema. For an
   unknown/newer schema, preserve it opaquely, stop mechanical writes for that
   actor and report the issue. Returning defaults or throwing away its balance
   is not recovery.
2. Keep a last-known wire-safe snapshot for export. A registered exporter must
   not signal a validation problem by throwing or returning nil when it already
   owns a nonempty bank. Unknown data must not be replaced by a v1 empty record.
3. Register once before actor load, with collision detection. Hot-registering
   after fallback load can serialize both an active and fallback entry under the
   same name; the reader will dispatch both. There is no automatic adoption or
   deduplication. Fallback also bypasses the mod's clone/export guard.
4. The current wire format supports booleans, integer-tagged numbers, strings
   and nested tables. Validate finite exact integer domains and forbid embedded
   NUL strings, cycles and unsupported key/value types before publication.
   Bound depth/size without silently deleting a bank. Do not trust arbitrary Lua
   numbers as an unlimited exact XP ledger; use a deliberately bounded domain or
   validated chunk/string encoding if a larger total is required.
5. Preserve unknown fields in a supported envelope unless migration explicitly
   owns them. Unknown *wire tags* are a lower-level EEex decoder problem; the mod
   importer cannot repair a payload it never receives.

The serializer chooses integer writers by numeric range, writes NUL-terminated
strings and traverses nested tables without a cycle detector. It retains exporter
table references for a later write pass rather than taking a deep snapshot.
[wire implementation:1082–1282](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Sprite.lua#L1082-L1282).

## Atomicity is not supplied by the marshal API

The serializer has shared current-sprite scratch state and a size pass followed
by a write pass. The patch likewise stores one current sprite pointer and one
original effect-list size. No transaction API connects these with a native XP
credit, and these snippets establish no nested-save safety.
[marshal patch:181–301](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Sprite_Patch.lua#L181-L301).

Publish an immutable committed ledger snapshot; exporters/importers must never
perform XP accounting or trigger nested engine work. A candidate native award
hook still has to demonstrate that successful native credit and bank debit commit
together before a save can observe them, including reentrancy/error paths. A
Lua `busy` flag or synchronous-looking callback is not that proof. An exporter
cannot repair the discrepancy by editing XP while a CRE is being marshalled.

If the selected native hook cannot provide that boundary, return the exact missing
hook/commit context. Do not implement a polling repair or claim that a journal
alone is sufficient without proving how it distinguishes committed native credit.

## Disable and recovery

Removing only a mod handler while EEex remains present has a source-supported
fallback carrier. It does not release XP, guard copied records, or validate a
schema. Removing EEex is a different operation: the native extra-data parser is
then absent. Neither operation is a lossless release-and-disable procedure.

A recovery mode must leave the reader and save-bound disabled/migrating policy
installed while it transfers each actor's bank into native XP through the proven
commit path. Debit only observed successful credit; keep any native-cap remainder.
It must also cover dismissed, dead and unloaded bank owners. Iterating the six
party slots cannot establish that all banks in a save have been recovered.

Consequently there is currently **no proven safe raw-uninstall route with a
nonempty bank**. A supported migration needs a completeness criterion for bank
owners and a durable record of incomplete recovery. Do not clear an unknown
schema, erase a bank to make uninstall possible, or silently reactivate a stricter
policy after a runtime setting change.

## Smallest remaining native acceptance work

Prepare these checks for a separately approved disposable EEex/EET test run;
none were executed here:

1. Instrument marshal reason/fields without mutation. Compare ordinary save,
   quicksave, area unload, CHR export/import, CopySelf clones, item comparison and
   direct `createCopy`. Verify the owner unchanged and only intended carriers
   eligible for subsequent awards/releases.
2. Save actor A with a small distinct bank, then a larger bank, then load the
   older save and an independent run. Verify serialized and loaded payloads;
   include party reorder, dismiss/rejoin, death/resurrection and object-ID reuse.
3. Exercise one continuing actor across each actual campaign transport, plus a
   direct-start fresh actor. Record whether native identity/serialized CRE was
   retained. Test a known destruction/recreation path separately.
4. Force repeated/nested award and release callbacks and save at the supported
   native boundaries. Verify native credit plus bank conservation, not just the
   Lua callback result.
5. Load wire-valid unknown/newer schema and remove only the banking handler while
   EEex remains. Save/reload and verify opaque preservation, then restore through
   a clean load. Also prove exporter errors cannot create a successful save that
   silently loses a nonempty bank.
6. Run release-and-disable with an unloaded/dismissed owner and with a retained
   native XP ceiling. Require exact successful credit and preserved remainder;
   no blanket uninstall acceptance until all required owners are covered.

Arithmetic and mocked lifecycle tests are valuable before these checks. They do
not substitute for the native copy, award/save, actor-transport or recovery gates.
