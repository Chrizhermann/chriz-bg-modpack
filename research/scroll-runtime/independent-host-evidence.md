# Independent native persistence host — October 9, 2026

Historical persistence-host milestone. The subsequent complete startup and component430
install path are documented in [component430-status.md](component430-status.md).
Since alpha.11 this DLL, `CBMScroll.dll`, is what component 430 installs; the
[scroll casting guide](../../docs/scroll-casting.md) records its in-game checks by DLL SHA-256.
`CBMS_EEexConfigureCurrent()` intentionally refuses bypassing the verified early startup
transaction; `CBMS_StartCurrent` is the implemented entry point. No EEex.dll fork is needed.

## Concrete route now implemented

`dll_entry.cpp` implements the actual loader `InitBindings(SharedState)` and
`OpenBindings()` contract. `build_independent_dll.py` links our source against
import libraries generated from the pinned shipped loader DLL exports. Both
Lua52 and LuaJIT providers satisfy its actual imports. It imports no EEex.dll
symbols and contains no offline-only attach/install APIs in a normal build.
The linked product was inspected as a PE file, never loaded or called.

`CBMS_InstallPersistenceHooks(gameBase, eeexBase)` first binds the reviewed
native functions and then installs three entry detours in one rollback
transaction. `CBMS_InstallEffectPersistenceHooks` adds three actual shipped EEex
lifecycle entries to that same transaction:

1. `CGameEffectList::Unmarshal` chains the **existing certified EEex override**,
   with unchanged list/data/size/actor/version arguments. The wrapper scopes
   every call, including V0 and null-actor calls that mask an enclosing V1 scope.
2. `CGameEffect::DecodeEffectFromBase` calls a concrete native trampoline and
   observes its exact original wire-record argument and returned effect. Only
   aligned normal V1 records belonging to that active buffer are associated;
   `X-BIV1.0` metadata and unrelated nested decodes are excluded.
3. `CGameEffectList::Marshal` retains the actual list, output-pointer address,
   version, permanent-only and skip-equipped arguments. The existing EEex
   exporter supplies its actual sprite and claims the scope only when that
   sprite's native timed-effect member is the active list. This is a pairing
   check, not an actor pointer inferred from arbitrary list memory. Nested
   serializers have separate stack scopes. After the native writer returns,
   the exact emitted normal-record prefix is checked against the captured
   archive. Other native serializers without an actor exporter remain unchanged.

4. EEex's live-effect copy callback remains chained; afterward the destination
   receives the source's owned context, or clears stale ownership when the
   source is unowned. EEex's raw-record DecodeEffectFromBase exclusion still
   applies, so save imports and opcode177 need their separate associations.
5. EEex's effect destructor remains chained after observed scroll lifetime
   cleanup. Unobserved effects are legal and do not invent ownership.
6. EEex's actor destructor remains chained after scroll actor cleanup. The
   actual destructor ends that actor's pending IO lifetime; it does not imply
   that an old save slot was restored. Metadata maintenance continues after a
   policy/schema fault so pointer reuse cannot redirect old ownership.

The Lua adapter retains the actor envelope before parsing it. After EEex updates
its UUID local, the exact low/high 32-bit fields bind the loaded actor before the
earlier loaded callbacks run. The full uint64 identity never passes through a
Lua floating-point number. Unknown envelope data remains retained. This does
not by itself create a completed gameplay load barrier or cancel a failed save.

## What the binding certifies

The decoder binder includes the prior 19 reviewed native provider/dependency
spans; the whole native decoder; the original Unmarshal tail; the shipped EEex
override's complete hot/cold body and registration; its initialized decoder
pointer; and the exact existing native jump destination. Both pinned 2.6.6.0
and 2.7.3.0 profiles are rebased from their actual mapped image base. It rejects
uninitialized, changed, inaccessible or wrong-architecture modules without
changing its output structure.

The Marshal binder separately certifies the native prologue, filter/count and
writer/return instruction spans. It preserves the two stock EEex hook sites at
native Marshal `+0x2A4` (six-byte JLE replaced by E9/NOP) and `+0x2AD` (five-byte
allocation CALL replaced by E9). Both must lead to readable executable memory
outside that native function. **Those two dynamically generated cave bodies
are not fully certified by this binder.** Their existing EEex source semantics
and lifetime remain host-owned; this check must not be described as proof about
an arbitrary third-party cave. No site is bypassed or recreated by our wrapper.
The immutable normal writer/filter spans and post-return byte validation remain
required. The two hook shapes were checked against `EEex_Assembly_x86-64.lua`
and `EEex_Sprite_Patch.lua`, not inferred from a development game's file layout.

The native decoder trampoline copies seven bytes without changing RSP or any
nonvolatile register, then continues its original prologue. The Marshal
trampoline copies all six pushes and the 0x188 stack allocation. It returns into
the active native frame with a ModRM01 memory jump via native call-home space;
an FF25 jump there would be misclassified as an epilogue. Its separate unwind
record represents exactly those executed pushes/allocation, with no copied
native language-handler address. See the Windows
[prologue/epilogue grammar](https://learn.microsoft.com/en-us/cpp/build/prolog-and-epilog).

The three shipped EEex wrappers are proven by actual UTF16 label export
registration: copy RVA `0xE620`, effect destruction `0xE670`, actor destruction
`0xE8C0`, with registrations at `0x30096`, `0x300C1`, `0x301C3` in both audited
DLLs. Their seven-byte prefixes write only volatile arguments to caller home
space, leaving RSP and nonvolatiles unchanged. The independent host chains each
original callback through its trampoline and allocates a second near page for
the EEex DLL. Both unwind tables remain registered until all six entries are
safely restored. This does not certify the implementation of EEex's shared
stutter-logging executor; its original callback behavior is preserved.

The host allocates near relay pages, emits the trampolines, changes them to
read/execute, flushes the instruction cache, and registers the real
`RUNTIME_FUNCTION` records before changing native entry bytes. Partial failure
restores exact entry bytes and the original page protection. Failed restoration
retains the code allocation and registration rather than freeing reachable code.
Removal requires the owner thread with idle native carriers and validates every
entry before restoring any. A later mod's changed entry causes refusal. This
requires caller-enforced initialization/quiescence; it is not stop-the-world
thread synchronization or permission to detach a running game.

## Focused evidence and its limits

The subsequent lifecycle run passed **69 checks**, exit0 in44.88s, recorded in
`C:/tmp/scroll-lifecycle-final.log`: six actual shipped wrapper/trampoline and
OS-unwind cases, 14 relocated lifecycle binder cases, seven compiled save and
lifecycle callback cases, 12 private hook-host transaction cases, one linked
independent DLL, and the 29 core callback tests. Six-entry failure injection
exercised exact rollback of both registered allocations. This expansion caught
and fixed a real installer indexing defect: Marshal's patch must use its third
entry, not the final entry after lifecycle sites are appended. Replacement
extents now must match their certified sites before a write.

- **33 passed:** `test_scroll_runtime_marshal_binding.py`,
  `test_scroll_runtime_decode_host.py`, `test_scroll_runtime_independent_dll.py`,
  `test_scroll_runtime_save_bridge.py`. This includes both relocated images,
  changed filters/writers/prologues and bad routes, exact three-entry rollback,
  retained external ownership, foreign-thread/active-callback detach refusal,
  nested compiled wrappers, real OS registration lookup/removal, and linking
  against both supported Lua provider imports. Log:
  `C:/tmp/scroll-persistence-host.log`.
- **4 passed:** `test_scroll_runtime_marshal_detours.py`. Actual native Marshal
  executes in the offline emulator through original versus trampoline paths;
  filtered bytes, allocation/return results, stack and nonvolatiles match.
  Real Windows `RtlVirtualUnwind` recovers the caller at every emitted instruction
  on both binaries. This was part of the earlier 19-case focused run recorded in
  `C:/tmp/scroll-marshal-host.log`.
- The earlier **28 decoder binding** and **5 decoder trampoline/unwind** checks
  remain separate evidence. The original unchanged 336 selector cases were not
  rerun to inflate these counts.

Private hook-host tests patch only our own allocated inert instruction fixtures;
they never execute those fixture bytes. Native DLL wrapper tests invoke only
our compiled code and our callbacks. SEC_IMAGE checks do not run image entry
points or initialize imports/globals. Native instruction execution is emulated,
with allocation/empty construction/cookie helpers substituted. No game, save,
installed DLL or game resource was written or launched.

## Historical integration work at this milestone (now superseded)

The persistent effect carrier now has concrete native entry installation,
decoder association, actor-envelope transport and exact removal. The host
now also has concrete [item entry registration](item-host-evidence.md), verified
policy-table consumption, and [opcode/message producer registration](dispatch-host-evidence.md).
Completion still needs cast entry/selector and action-copy/destruction host
registration, full initializer policy-resource connection, and ordinary
save/load/dispatch lifecycle handling.
Native actor marshal alone does not establish which queued actions/messages or
projectiles survive GAM/ARE saves. An unknown-schema fault latch does not cancel
native execution. If save preflight is used, it must precede the outer save
screen's `DeleteSaveGame`, not pretend that inner SaveGame failure restores the
old slot. Native acceptance is separately absent by instruction.
