# Native item-use carrier and hook host

October 9, 2026. This extends the uninstalled native scroll runtime. It does not
replace component430, install into a game, or claim initialized-engine testing.

`item_carrier_api.cpp` wraps the real x64 signatures of `CGameSprite::UseItem`,
`UseItemPoint`, `CGameAIBase::FireItem`, `FireItemPoint`, and
`CItem::GetAbilityEffect`. All four use/fire entries return a 16-bit action
result. The native bodies, including their charge updates and target routing,
remain the original callees. Every completed nonnull root retains the actual
eight-byte item resource, ability/effect indexes and original reader.

An item invocation owns its own origin scopes. The two exact native Use→Fire
extra-target calls share their parent use; other nested calls are independent.
The four exact native calls to GetAbilityEffect establish root eligibility.
Unrelated calls cannot borrow an outer item's context. Generic FireItem readers
must already have an observed sprite lifetime; the code never treats the target
or an arbitrary AI object as the original sprite. Native UseItem paths establish
their own typed sprite observation.

`generate_item_profiles.py` reads the pinned executables and emits full-body
SHA256 profiles for these five methods plus `CItem::GetItemType`. It disassembles
and verifies all six call edges, checks the previously tested entry prefixes,
and rejects signatures spanning ASLR relocations. `item_binding.hpp` certifies
these bodies after the existing reader ABI/PE checks and binds relocated entry
and return-PC addresses. A changed body, including another installed detour,
refuses. This is deliberately an audited ABI boundary, not an old gameplay-value
fingerprint or a promise that arbitrary future detours are compatible.

The actual native type query reads the demanded ITM category. Only category11
enters the verified policy table. Manual learning, native-only abilities and
source-backed fixed exceptions preserve native behavior; absent and unresolved
scroll entries report distinct failures. The table's complete dependency hashes
must match effective installed resources before any hooks are written.
`policy_resource.lua` and its compiled CNG binding provide the actual EEex
full-resource digest route; the full runtime initializer connecting this route
to all carrier groups remains unfinished.

`item_hook_host.cpp` installs all five entries in one initialization-only
transaction. It rechecks exact prefixes, allocates a near relay page, writes
trampolines, changes that page to RX, flushes the cache and registers five real
Windows unwind records before entry writes. Partial failures restore original
bytes/protections and deregister. Failed rollback retains reachable code and
registrations. Removal requires the idle owner thread and checks every entry
before changing any. It never overwrites a later hook owner. The caller must
exclude execution and other writers during initialization/removal; this is not
a stop-the-world implementation.

Trampoline bytes are shared with `item_detours.py`'s offline-tested recipes.
Active-frame continuations use the audited native call-home space and ModRM01
indirect jump, following the Windows
[epilogue grammar](https://learn.microsoft.com/en-us/cpp/build/prolog-and-epilog).
Leaf partial prologues use an ordinary absolute jump. The 10 actual-instruction
tests cover both executables and every emitted instruction's OS unwinding.

The first integrated item run passed **45 checks**: 15 compiled carrier cases,
18 relocated-image binding cases, 11 private hook transaction cases, and the
independent DLL link. No game function was invoked. Two additional compiled
exception cases passed after finding and fixing a real `/EHsc` issue: carrier
exports with C linkage need explicit `noexcept(false)` so MSVC emits the scope
cleanup across calls into native C++ code. Both an exception before a root is
returned and one after root attribution now release the use token and restore
the invocation stack while preserving the original exception. These are our own
original-call fixtures, not exceptions induced in an initialized engine.
The subsequent item/core/DLL regression run passed **58 checks**, recorded in
`C:/tmp/scroll-item-regression.log`.

Commands, with `PYTHONPATH=C:/tmp/xp-banking-analysis-deps`:

```text
python -m pytest tests/test_scroll_runtime_item_carriers.py tests/test_scroll_runtime_item_binding.py tests/test_scroll_runtime_item_host.py tests/test_scroll_runtime_independent_dll.py -q
python -m pytest tests/test_scroll_runtime_item_detours.py -q
```

Latched ownership errors preserve the original native return/effect rather than
manufacturing a cast or refund. The full initializer still must connect those
diagnostics to the visible failure path. New item ownership is disabled after a
latched item fault; existing owned carriers retain their metadata. This local
subsystem is not advertised as a usable player-facing candidate by itself.
