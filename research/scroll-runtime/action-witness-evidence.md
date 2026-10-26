# Value-carried CAIAction ownership (action witness)

October 20-23, 2026. Read-only analysis of both pinned executables, the actual
engine bodies executed in Unicorn on private memory, compiled native tests and
one disposable lab game (see [Lab acceptance](#lab-acceptance)). This replaces
the action copy/destruction host of alpha.11 to alpha.13 (`action_hook_host.cpp`,
`action-detour-evidence.md`), which is removed together with its tests.

## Why address lifetimes failed

Alpha.11 to alpha.13 ship the same `CBMScroll.dll` (SHA-256 `dad1b982...`). It
tracked every CAIAction by its address: the dispatch default-constructor hook
registered each construction, and the action host hooked the copy constructor,
the assignment and the out-of-line destructor `~CAIAction` (2.7.3.0 RVA
`0x120680`). That destructor has three direct callers, all in
`CAIScriptFile::ParseAction`. Everywhere else the engine destroys actions
inline, by calling the destructors of their CString and CAIObjectType members
directly, and frees heap actions with its own sized delete. Such a registration
outlives its action. The next action built at the same address, a recycled heap
block or the same stack slot, then fails with "scroll carrier born twice without
destruction" (default constructor) or "copied action construction overlaps an
existing lifetime" (copy constructor). The runtime then disables new scroll
overrides for the rest of the process and shows its EEex message box.

The left click on a container is one such path. `CGameContainer::OnActionButton`
(2.7.3.0 `0x140193A20`) builds its actions with the default constructor
`0x140116D10` and the copy constructor `0x140116930`, hands them to
`CAIGroup::GroupAction`, and destroys them through inline `CString::~CString`
calls, never through `~CAIAction`. Each container click leaves registrations
that the next click at the same stack depth collides with.

On October 20 that DLL failed this way in a lab on 2.7.3.0 with EEex v1.3.1,
without any save from another installation: right after loading a save (a
debugger showed the script parser's `new CAIAction(copy)` landing on a recycled
block), during a new game, and when an NPC joined. Letting both constructors end
an unobserved lifetime avoided the box there, but such a patch cannot tell a
stale registration from a live one, so no address-keyed design was pursued
further.

## Design

An owned action carries a private empty CString block in its `m_source` CString
(+80h). `action_witness.hpp` documents the ABI it relies on; the binder
certifies it per build. The engine itself carries ownership:

| Step | Code | What happens |
|---|---|---|
| Identify | `dispatch_carrier_api.cpp` `action_default` | At the audited message-constructor return PCs (2.7.3.0 `0x1401A876B` for 146, `0x1401A89C7` for 148), an owned mode0 ApplyEffect records the action it builds at message+10h. Nothing is registered. |
| Stamp | `add_message` | When EEex's mode0 route queues exactly that message, the CMessageInsertAction vtable is checked and `CBMS_StampActionWitness` replaces the native empty sentinel in message+90h with a new witness whose key carries the scroll's ownership. |
| Travel | engine only | Message, action queue, GetNextAction's scratch copy, `m_curAction`: each copy shares the block (refs + 1), each replacement or destruction releases it (refs - 1), inline or not. |
| Read | `cast_carrier_api.cpp` | The four action cast entries (Force, ForcePoint, Spell, SpellPoint) read `m_curAction.m_source` (sprite+3F8h+80h). Only a live witness with current ownership names a scroll reader; any other value is never dereferenced. |
| Retire | `ActionWitnesses::sweep` | Each stamp sweeps first. A witness held only by our own reference ends its ownership and is retired (below), and the next 64 retired blocks are audited. |

Our own reference is `0x40000000`, so the engine's count never reaches one or
zero while we keep a block: the engine never frees a witness, and its writers
copy a shared block before writing. Native construction stores the shared
empty sentinel, so a fresh or unrelated action can never carry a witness; only a
copy of a witnessed action holds one. Readers of `m_source` see an empty string
either way. At most 4,096 witnesses may be referenced at once; more is reported
as unbounded retention.

### Retired witnesses are never freed

A retired witness has no counted engine holder. Freeing it would turn a holder
the evidence missed (a bitwise copy, a double release) into a use-after-free
inside the engine's CString code, and the allocator could hand the same address
to a later witness, so a stale value would name another scroll use. Retired
blocks therefore stay allocated and unused for the rest of the process, even
when the runtime is destroyed: its witness table hands its blocks to the process
instead of freeing them. Blocks are issued in order from 4 KiB slabs of 256 and
never reused.

The audit is incremental. Each sweep, that is each owned queued scroll cast,
checks the next 64 retired blocks round robin: still at exactly our reference
and untouched. Any difference is reported and disables every override (below);
a failing block keeps the cursor, so it is reported again. Every retired block
is checked again within `ceil(issued / 64)` scroll casts, and `CBMS_Destroy`
audits all of them. The cost per scroll cast is the live witnesses (normally a
handful, at most 4,096) plus 64 block checks, however long the process runs.

Since no block is ever freed, a process issues at most 1,048,576 witnesses
(`ActionWitnesses::total_capacity`), 16 bytes each: 16 MiB at the cap,
allocated only as used. Each owned queued scroll cast takes one witness: an
ordinary scroll use queues one cast, and a scroll spell whose own effects queue
casts (opcode 146/148 mode 0) takes one more per queued cast, for example per
target. A long session of heavy scroll use is some hundreds of scroll uses,
reloads included; even at ten queued casts each that is a few thousand
witnesses, and one queued scroll cast every second for 24 hours would be 86,400.
The cap is more than 200 times the first and 12 times the second, and a new
game process starts again from zero. Once it is reached, the stamp is refused
like any other witness fault: the field keeps the native sentinel, that cast and
every later one keep their native level, the fault is reported (the runtime
reporter, the dispatch carrier diagnostic and the startup health check, which
`CBMS_Startup.lua` logs once), and nothing already issued is freed.

### Faults disable every override

Every reported error, in the runtime, a carrier group, the save bridge or the
startup transaction, latches one disabled state (`Registry::disable`,
`CBMS_DisableOverrides`). Afterwards no
carrier reads as owned, no context is stored or propagated (item roots, linked
and copied effects, queued messages and actions, restored saves), and every
selection and spell child keeps its native level, including frames entered,
casts captured and actions queued before the fault. The one exception is a
selection already in progress when the state latches, which needs the latch to
come from a call on another thread at that moment: that one cast can still get
its override ([Limits](#limits)). Witness stamps leave the native sentinel.
Lifetimes, frames, captures, witness sweeps and their audits, and the cleanup of
contexts stored earlier keep working, so the runtime still releases what it
holds. A scroll queued before a fault therefore casts at its native level after
it (`test_queued_override_casts_natively_after_a_later_witness_fault`).

A fault shows only in the loader log; nothing appears in the game (Christopher's
decision of October 23, confirmed October 25). The one exception, decided on
October 25, is a failed start whose rollback could not remove every hook:
`startup.cpp` then keeps the runtime, `CBMS_StartupRetained` (Lua
`CBMS_NativeRetained`) reports that on the startup thread, and the script shows
one EEex message box after its two log lines, once per process and before any
game can be loaded, asking the player to quit and restart. `CBMS_Startup.lua` polls the
health check from two EEex listeners, scripting-object updates and sprite action
starts (`EEex_Action_AddSpriteStartedActionListener`), and logs the first
failure once per process: one line saying that 430 is off for this session,
then its cause. A poll reads latched flags; after that report it is a single
flag test, and an error inside it only prints
`[CBM scroll] Health check failed: ...` to the loader log, never reaching
the engine event. With the scripting-object listener alone the notice, then a
message box, came about 15 minutes after a fault in an idle lab scene: that
listener runs when a trigger updates a scripting object (a `Shout` or `Help`),
not for scroll casts, spell hits or a reflection. With both, it came with the
next event after the fault ([lab acceptance](#lab-acceptance)). The levels do
not wait for it.

A second load of `CBMS_Startup.lua` after a successful start calls the native
start once more. The start is single-attempt: it refuses before reading its
arguments and runs `CBMS_DisableOverrides`, so the started runtime keeps every
later selection native, and the first load's poll logs the fallback. A second
load before initialization only refuses and leaves the first load's start
alone.

### Threading

Every carrier group, the save bridge and the startup transaction record the
engine thread that configured them (`carrier_gate.hpp`). Each hooked entry
compares the current thread with it before it reads any carrier state. A call
on another thread touches no carrier state: it forwards its arguments unchanged
to the native original and returns its result, and it latches the process-wide
foreign state, which disables every override in every runtime and makes the
startup health check report it. Group removal (only in the startup rollback)
refuses while such a call is in flight, and the rollback then keeps every hook
and the runtime alive. See [Review questions](#review-questions) for what this
does not cover.

## Native evidence

`dispatch_native_audit.py` reads both pinned executables with pefile and
capstone and never runs them; `dispatch-audit-2.6.6.0.json` and
`dispatch-audit-2.7.3.0.json` keep the results. The script asserts each fact, so
a changed body fails the audit instead of being recorded.

- Native default construction stores the one empty sentinel global (2.7.3.0
  `0x65CB10`, 2.6.6.0 `0x65BB10`) into +60h, +68h and +80h. In both producers
  the only native write to message+90h before AddMessage is one
  `CString::operator=` from the stack action.
- CString block ABI: refs at data-0Ch. The copy constructor shares a block with
  refs >= 0 (`lock inc`); `operator=` and `~CString` lock-decrement, return
  early for the shared sentinel and free only at zero; AssignCopy,
  CopyBeforeWrite, GetBuffer and ConcatInPlace copy a block with refs > 1 before
  writing. These seven bodies are hash-certified in `dispatch_profiles.hpp`, as
  is the CMessageInsertAction vtable.
- CString is never inlined. Across about 5.5 MB of reachable code, every locked
  operation on a block header lies in a CString member; only the copy
  constructor and `operator=` add a holder. Other locked operations belong to
  unrelated code (C runtime, SDL, the network library).
- Every action value in every `.pdata` body (78 in 48 bodies in each build,
  recognised by their CString and CAIObjectType members or by inline
  construction) reaches `m_source` only through those bodies: the copy
  constructor (4 sites as destination, 3 as source), `operator=` (48 and 32) and
  `~CString` (39). Apart from 19 inline-construction stores of the empty
  sentinel, no code reads or writes the pointer directly. Each of the 126
  addresses of `m_source` those bodies form is the `this` or argument of the
  next member call; none is kept as an alias.
- The six bulk copies in bodies that handle actions were reviewed one by one:
  the multiplayer message marshal copies string text (three), QuickLoad copies
  the CRE header into the base stats (one), and ProcessEffectList copies
  derived stats (two). None copies an action or a CString pointer.
- Among save and load functions, only the multiplayer response marshal and
  unmarshal and QuickLoad's reset of `m_curAction` touch action members: queued
  and current actions are not part of a save.

EEex copies, assigns and destroys actions through the engine's own functions
(v1.2.0 and v1.3.1 `EEex_Action_ExecuteScriptFileResponseAsAIBaseInstantly`,
`EEex_MemoryManagerStructDefinitions.CAIAction`), so a witness there is shared,
not copied bitwise. While EEex runs an instant action in `m_curAction`, a cast
entry sees that unowned action. Neither version hooks the CAIAction
constructors, assignment or destructor, or `CGameContainer::OnActionButton`;
its only container hook is `CGameContainer::Render` (B3EmptyContainer).
EEex.dll's own code is not part of this audit: a bitwise copy there would be
reported by the sweep audits, not followed.

## Tests

- `test_scroll_runtime_action_witness_native.py`, both builds: the actual
  CString and CAIAction copy, assignment and destruction bodies run in Unicorn
  against a witness laid out as `action_witness.hpp` issues it. Copies share it,
  replacement by the empty or an ordinary string and destruction release it,
  the shared sentinel is never released, and each reviewed writer first gives a
  field holding the witness its own block. The witness bytes stay untouched.
  A third test checks the audit facts above, and a fourth reruns the audit over
  the pinned executables and requires exactly the committed evidence.
- `runtime_tests.cpp` (through `test_scroll_runtime_native.py`): stamping,
  sweep and retirement, a later use getting a different block, audit failures
  for an uncounted holder (refs one lower or one higher, a written byte), the
  4,096 bound, destruction refusal, 8,199 sequential stamp, release and retire
  cycles with at most 64 audits per stamp and a damaged old block found within
  one audit round, the lifetime allowance at its real size and its refusal, the
  disabled state, and the foreign-thread latch.
- `test_scroll_runtime_dispatch_carriers.py`: the compiled carriers with
  controlled native-callee substitutes. A mode0 witness travels by value into
  `m_curAction`; non-scroll actions never inherit a scroll use; a malformed or
  foreign message latches an error and keeps the native call; a dispatcher
  without its constructed message attaches nothing; nested scopes mask outer
  ancestry; queued casts up to a lowered allowance, then the refused stamp and
  native casts.
- `test_scroll_runtime_cast_carriers.py`: queue A, fail B (a changed message
  field, exhausted storage, a damaged retired witness), the fault is reported,
  then A casts at its native level without querying its reader.
- `test_scroll_runtime_foreign_thread.py`: every hooked entry of every group,
  the save bridge's Lua entries and the native API, called on another thread:
  originals get unchanged arguments and their results back, no carrier state
  changes, the latch disables every override, and removal waits for the call.
- `test_scroll_runtime_startup.py`: the startup health check reports a latched
  disabled state, a foreign entry and a health query from another thread;
  `CBMS_StartupRetained` is 1 only after a failed removal and reads 0 on
  another thread. The real `CBMS_Startup.lua`, under Lua 5.1 and LuaJIT, logs
  each fallback and its cause, never calls `Infinity_DisplayString`, and calls
  `EEex_MessageBox` exactly once, after both lines, only when the native start
  reports kept hooks: not for any other fallback or a second load, and not
  again in the same process. With the real `startup.cpp` and runtime, a second
  load after a successful start turns the overrides off, and a scroll cast
  queued earlier with a witness then casts at its native level without querying
  its reader (`test_duplicate_bootstrap_turns_the_started_runtime_off`); a
  forced failed removal shows the box and a clean rollback does not
  (`test_only_a_start_that_kept_its_hooks_shows_the_box`).
- `test_scroll_runtime_independent_dll.py`: the linked DLL rebuilds byte for
  byte in another build folder (`/Brepro` replaces link times with content
  hashes). The sources must stay in the same folder: MSVC derives
  anonymous-namespace names from their path.

The removed tests covered only the removed action detours, their bridge
registration, their unwind and the action host. The shared Windows unwinder
checks every remaining bridge family, including the dispatch entry trampolines.

## Review questions

The October 23 review of this design left three questions open.

**Is the audit complete?** No proof covers every body. The scanner recognises
an action value by its member pattern (CString and CAIObjectType members at
action offsets, inline construction) or by a direct call to an action function.
A body that handles an action only through raw offsets, a scalar copy of the
pointer, or an action pointer passed on to a helper without such a pattern is
outside the proof; none was found. Two points the review raised are addressed:
the scanner now follows every address of `m_source` formed in the recognised
bodies and requires it to be consumed by the next member call (126 per build,
no alias), and a test reruns the scanner over the pinned executables instead of
checking only the committed JSON. What remains is a bitwise holder the audit
missed. It cannot reach freed memory (below), a release or write by it shows in
the sweep audits, and it never makes a retired witness name a reader again,
because a retired key never regains ownership and its block is never reissued.
It could attribute a scroll use to another action only by copying the pointer
into that action while the scroll's cast is still queued, outside the CString
members; the bulk-copy review found no such copy.

**Does destruction free a block a missed holder still reaches?** Not any more.
Destroying the runtime ends its witness table without freeing a block, so an
untouched, uncounted holder that passes the baseline audit still reads a valid
empty string. `CBMS_Destroy` has one production caller, the rollback of the
single startup attempt in `startup.cpp`. It runs inside `CBMS_NativeStart` in
EEex's game-initialized listener, before any game is started or loaded (later
activation is refused), and only after every hook group was removed on its owner thread while
idle. Nothing destroys the runtime at process exit. Destruction still refuses
while a witness is referenced or any context is pending, and it audits every
retired block.

**What establishes owner-thread execution?** `CBMS_NativeStart` installs and
configures every group synchronously on the thread that runs that listener, the
engine thread that runs EEex's Lua. The runtime no longer assumes the engine
keeps every hooked entry on that thread: each entry checks the thread before it
touches carrier state and forwards a foreign call unchanged to the original
(above), and a health query or save bridge call from another thread reports
unhealthy or is refused. Outside two startup windows, a foreign call therefore
neither crashes nor changes a level. Both windows lie in that one listener
call, before any game is started or loaded, and remain open:

- Installation writes each entry patch with `memcpy` after `VirtualProtect`,
  without suspending other threads. A thread running a site while its bytes
  change could execute a torn instruction. EEex patches its own sites the same
  way at startup.
- A rollback removal frees the group's relays after restoring its sites. A
  thread that entered a relay before the restore but had not yet counted itself
  as `Outside` (a few instructions) is not seen by the idle check, and neither
  is one that counted itself out again after its handler returned but still runs
  the relay's last instructions. Either could then run freed code.

Neither is guarded against: both would need the hooked entries to run on
another thread during the startup transaction. The source review of October 25
confirmed both, and this release does not fix them
([known limitations](../../docs/scroll-casting.md#known-limitations)).

## Lab acceptance

October 23, on a disposable copy of the collection install (Steam 2.7.3.0, EET
with Spell Revisions, EEex v1.3.1), with `CBMScroll.dll` SHA-256
`9671cf3f2838ebdbc487c4cf1882a7d937b6cc673568e35358f691c954901b3c`, installed
with WeiDU as component 430 and removed again afterwards. Two game processes,
muted and windowed. The runtime stayed healthy at every check:

- main menus, loads of saves made under the alpha.13 runtime and earlier, a new
  SoA game with Imoen joining through her dialog, Xan created and joined (the
  alpha.12/13 failure point), container clicks through the engine's own
  `CGameContainer::OnActionButton` (one container opened), and an area change;
- levels as documented: active cleric 12 reading divine: 12; the same cleric
  reading arcane: 6; mage 8/thief 7: 8; mage 8 with a dormant thief 10 reading
  divine: 4; dormant mage 13 dualed to thief 10, then 12: 5, then 6; pure
  fighter 12: 6; fighter 2/mage 9: 9; a level-1 cleric: 1. Haste (an area
  spell) reached both party members at 6; the 148 point route (Summon Shadow)
  summoned three shadows at 6 where a plain level-13 cast summons two wraiths;
- a plain cast right after a scroll use kept its native level (1 and 13), and
  six consecutive uses each consumed one scroll at level 8;
- learning through the inventory's Write Magic button learned the spell and
  consumed the scroll;
- saves with continuing scroll effects reloaded with the same levels; a save
  made while a scroll cast was queued reloaded without the cast and with the
  scroll back, and using it again cast at the scroll level.

Later that day the review-fix build
(`41fed66c93f86a138afa853d203835ad755f0176ac627d8d42d42f4b63adb11b`) went
through the same lab in two more processes, after loading a save made under the
first build. A cleric 12 read arcane scrolls (level 6; natively 1 for this
reader), and the runtime stayed healthy until the forced fault:

- linked and conditional chains: Sleep at 6 on three creatures, including the
  232 effect that casts `SPWI116D` (damage fired it and woke the creature);
  Invisibility at 6 (its conditional 326 helper did not trigger); Improved
  Haste at 6 on both party members, including its three 326 children;
- repeating helpers keep their native mechanics (installed type 0,
  `PreserveNative`): Combust's 326 helper `SPWI230B` got 12 on the reader
  (cleric 12) whether its parent was cast at 6 under 430 or at 1 with the
  overrides off, and 1 on a level-1 creature from a plain native cast; Acid
  Storm's 146 mode 1 helper `SPWI709Z` went from 1 to 12 under 430 and in a
  plain native cast alike;
- reflection: Melf's Acid Arrow from a scroll, turned by opcode 200 on its
  target, landed on the reader with the five effects of its level-6 ability at
  6 (natively the three of its level-1 ability at 1); unturned it hit the
  target at 6;
- fixed protection scrolls (`SCRL06`, `SCRL09`) at their native 10, SCS's
  `DW#PROUN` at 12, the same with the overrides on and off;
- one forced witness fault: Improved Haste was queued at Imoen, and once its
  witness was the current ForceSpellPoint's `m_source`, the lab wrote 1 into
  the block's capacity field. That queued cast landed at native level 1 on both
  party members, the health check reported "engine wrote into an action
  witness", and every later scroll cast kept its native level. The box came
  only with the next scripting-object update, about 15 minutes later
  ([above](#faults-disable-every-override)).

That evening the same DLL with the late-box `CBMS_Startup.lua` (SHA-256
`063d74a8504c495adf89351c7118cdbadd6df91b720603b37d1a34711fec7aeb`) went
through five more processes. Levels stayed as documented throughout (cleric 12
reading arcane 6 and divine 12, fighter 2/mage 2 at 2, mage 8/thief 7 at 8):

- containers, the symptom reported for alpha.11: a scroll use, then a container
  opened through `CGameContainer::OnActionButton`, four times in a save made by
  an earlier installation (alpha.12, no envelope of this component) and three
  times in a new BG1 game, once more after reloading it. Two more clicks
  replaced a scroll cast still in progress, one of them a `ForceSpellPoint`
  checked to carry a witness; neither cast landed. Healthy throughout;
- the October 20 failure paths: that earlier save loaded first and Xan joined;
  a save made in the lab loaded first and Sarah joined; a new SoA game, healthy
  at every poll through its start, and Imoen joined through her dialog; also an
  area change and a scroll learned through Write Magic;
- opcode 272: Spell Shield (`SCRL8X`) put its parent effects including the 272
  at 6 and its untyped repeating children at their native 12. A save during the
  272 carried both actors' envelopes, each byte-identical to the actor's own
  effect records, and reloaded with the same levels, the 272 and its children
  still present 14 seconds later, in the same process and in a fresh one;
- the late box, twice: after a forced witness fault the health check turned
  unhealthy at once, the box waited while nothing happened (13 seconds without
  an action start or a scripting-object update) and came once with the next
  event, in one process the next action start, in the other a scripting-object
  update. Later action starts, walking orders and a shout showed nothing more;
- saves around a fault: a save made after the fault holds no envelope, and in a
  fresh process it loaded healthy, with old effects at their saved levels and a
  new scroll at the reader's level. A save loaded while overrides were off keeps
  its envelopes unparsed, and the next save writes them again unchanged; once
  the actors' effects had changed, loading that save in a fresh process turned
  every override off ("saved effect record count mismatch"), and saving there
  kept the same stale envelopes. With 430 uninstalled, EEex kept them the same
  way ([limits](#limits)).

On October 24 the per-actor drop (`CBMScroll.dll` SHA-256
`88ce92e2ae3af6b07a67693eef97d88dd8c2061667bacda9196cb7b4d9b68e11`, with
`CBMS_ScrollMarshal.lua`
`99936511f13f8a1338aacc15298831256041d76b2b4019fadfe2a1d6b85655bc`) went
through four more processes, after a first one with the same DLL whose log
line could not name the actor yet (the display name and CRE resref are still
empty when EEex's loaded listeners run). Healthy throughout apart from two
forced witness faults, and no box otherwise:

- the three outdated saves above, then the first again, in one fresh process:
  each load logged one line per actor, such as "Dropped outdated scroll data
  for Xan (O#XAN, UUID AC) only: saved effect record count mismatch (saved 41,
  loaded 52)", and the protagonist, who has no name string at that point, as
  "actor UUID 3F". Both tables were dropped, the effects kept their saved
  levels, and new scrolls used the reader's level (cleric 12 reading arcane 6,
  fighter 2/mage 2 at 2). A save made there held only matching envelopes,
  owning only the new casts, and loaded in a fresh process without a drop
  line, also right after an outdated save in the same process;
- a kept envelope is outdated as soon as the game writes its actor again: the
  actor's op187 local-variable records carry the current game time, and in
  this install another mod rewrites its own effects after a load. A save made
  while overrides were off held outdated envelopes for Player1, Xan and a cow
  in the current area; the next load dropped all three, the cow by name;
- an actor the faulted process never writes keeps a current envelope: with the
  party moved to another area before the fault, the cow's BG2900 records
  stayed byte-identical in the save made while overrides were off. Loading it
  in a fresh process dropped the two party envelopes and, after the area
  change, restored the cow's without a line. The next save wrote its 35 rows
  again with the same reader, scroll, depth and level 12 (origin keys are
  process-local), and it loaded in a fresh process without a drop line.

On October 25 the same DLL with the log-only `CBMS_Startup.lua`
(`6899144fe12e9ef8381559022221c0f421b3feb12b851839bca894e043d192a8`) went
through five more processes. The probe was Haste from a scroll: its delayed
op146 casts the fatigue `SPWI305D` on every hasted creature 60 to 72 seconds
later, a child spell long after the scroll use (Player1 cleric 1, Imoen mage
8/thief 7, a new SoA game):

- healthy throughout two area changes during the effect, Imoen leaving and
  rejoining the party, Imoen dismissed (her object stays, in no area) while
  the party traveled to another area, a save with continuing Haste reloaded in
  the same and in a fresh process, and one made while Imoen was away reloaded
  in the same process. While Imoen was in no area, the engine cast no fatigue
  at all, before and after a reload. The fatigue's level shows nothing about
  430: with the overrides off the engine gave the same levels, the hasting
  reader's 8 in live play and each creature's own after a reload (Player1 1,
  Imoen 8), and `SPWI305D` has one ability with fixed values;
- a reader outside the party that is not loaded when the restored effect's
  child comes due: a lab-created cow read Haste at Player1, and the game was
  saved after the cow was removed with `DestroySelf` or after the party had
  moved to another area without it. Loading such a save, in the same and in a
  fresh process, was healthy until the fatigue came due; then every override
  turned off ("original scroll reader UUID is pending load binding"). A
  restored frame consults its reader before the policy applies
  (`scroll_context.hpp`), and the reader stays pending while it is not loaded.
  With the party back in the cow's area before the fatigue, the same save
  stayed healthy. Without a reload nothing turned off: the fatigue was not cast
  while the cow's object was gone, and Sleep's on-damage op232 child ran
  without consulting its removed reader;
- the loader-log notice: each of these faults and a second load of
  `CBMS_Startup.lua` from the remote console wrote exactly the two fallback
  lines at the next action start; a recorder in place of `EEex_MessageBox` and
  a wrapper around `Infinity_DisplayString` saw nothing, and the quiet runner
  found no window. After the second load, Imoen's divine Free Action scroll got
  level 1 where it got 4 with the runtime healthy.

On October 26 the build with the kept-hooks box (`CBMScroll.dll`
`74ea73d879c906d57497eb7f3d3ec6dc4b890da5a066961ec46e596b2a29aa54`,
`CBMS_Startup.lua`
`8f1cef80bc362a02a63801567b29e99ca7fa8f3b9f08a8380917a62cde15e3bb`) went
through one process, started through the slot tool with no OBS running. The
normal start logged its verified line and reached the main menu; the quiet
runner saw only the game's own windows on its desktop, no dialog at any time.
The in-game `CBMS_NativeRetained` returned false. In the save with continuing
Haste, Imoen's Free Action scroll got level 4; a second load of
`CBMS_Startup.lua` from the console then wrote the refusal and, at the next
action start, exactly the two fallback lines, with no box and no in-game
message, and her next Free Action scroll got level 1. The kept-hooks start
itself cannot be produced in a game without changing the runtime; the startup
tests force it.

Not exercised in game: EEex 1.2.0, 2.6.6.0, a child spell cast after a reload
by a restored effect where the engine's own level differs from the reader's,
multiplayer and an ongoing playthrough.

## Limits

- Multiplayer: the response marshal sends string text, so a remote machine
  builds the action without the witness and uses the native level there.
- Recognition of action values in the audit is by member pattern. A body that
  touched an action only through raw offsets would not be recognised; the
  emulation, the lab and the sweep audits are separate evidence.
- A process issues at most 1,048,576 witnesses; later scroll casts keep their
  native level and the fault is reported.
- The two startup threading windows above are not guarded, and this release
  does not fix them.
- A selection already in progress when the disabled state latches, from a call
  on another thread at that moment, can still write its override: that one
  cast can get the reader's level, every later one keeps its native level. This
  release does not fix it.
- The loader-log notice of a fault is written with the next action start or
  scripting-object update after the fault, not at the fault itself. Nothing is
  shown in the game.
- A restored effect whose reader is not loaded when it next casts a child spell
  turns every override off: the pending reader is checked before the policy
  applies. The lab produced it with readers outside the party that were
  destroyed before the save or left in an area the party had left; party
  readers were bound after every load, and returning to the reader's area first
  kept the overrides on ([lab acceptance](#lab-acceptance)). This release does
  not fix it.
- An envelope kept unparsed, because it was loaded while overrides were off or
  while 430 was not installed (EEex's fallback storage), is saved again
  unchanged. Once the game writes that actor again, which in the lab changed
  its records every time, a later load drops it for that actor alone and logs
  it ([persistence](persistence-edge-evidence.md)): its effects keep their
  saved levels, but spells they cast later use their native level. Malformed or
  internally inconsistent, unknown, duplicate or conflicting envelope data still
  turns every override off for that process; damage that keeps an envelope well
  formed looks outdated and is dropped the same way.
- Only the audited 2.6.6.0 and 2.7.3.0 builds bind; any other body refuses.

```text
python research/scroll-runtime/dispatch_native_audit.py
python -m pytest tests/test_scroll_runtime_action_witness_native.py tests/test_scroll_runtime_dispatch_carriers.py tests/test_scroll_runtime_dispatch_binding.py tests/test_scroll_runtime_native.py tests/test_scroll_runtime_independent_dll.py -q
python research/scroll-runtime/build_runtime_package.py --build-dir <new empty folder>
```

Set `BG2EE_266_ROOT` and `BG2EE_273_ROOT` to folders holding the pinned
executables first (`local_paths.py`).
