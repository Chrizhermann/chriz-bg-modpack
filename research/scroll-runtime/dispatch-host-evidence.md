# Native spell-dispatch producers and queued-message lifetime

October 9, 2026. Compiled uninstalled code; no game or save was changed or
launched. This is the next concrete group after the [item host](item-host-evidence.md),
not full scroll activation or initialized-engine acceptance.

`dispatch_native_audit.py` resolves the actual native bodies, constructor call
sites, FireSpell message vtable, destructor and unwind metadata in both pinned
executables. `dispatch-audit-2.6.6.0.json` and `dispatch-audit-2.7.3.0.json` retain
the evidence. The FireSpell deleting destructor is identified through the
vtable whose independently named subtype and Run slots match; no nearest folded
symbol name is treated as its identity.

The native deleting destructor consumes EDX flags, conditionally frees on bit0,
and returns this in RAX. The generated base CMessage vtable declaration omits
these details. Our exact two-argument, pointer-return signature follows both
actual bodies. AddMessage returns a signed short, ApplyEffect returns int, the
default action constructor returns its destination, and FireSpell::Run is void.

## Attribution before the native queue

Mode0 AddMessage call sites are already redirected by EEex. Their return PCs
therefore cannot be assumed to be the original native call-end addresses. The
new code preserves those sites and EEex's special-bit SpellNoDec/SpellPointNoDec
behavior. Instead, it attaches action ancestry immediately after the exact
default constructor of the message's inline CAIAction. The temporary stack
action has a distinct constructor call and is not attributed.

October 23: that constructor call now only identifies the message's action.
Ownership is attached when EEex's route queues the message, as a witness that
the action carries by value ([action-witness-evidence.md](action-witness-evidence.md)).
No action lifetime is registered.

Pinned 2.7.3.0 native return PCs:

| Boundary | Return PC |
|---|---|
| 146 message's inline action constructor | `0x1401A876B` |
| 148 message's inline action constructor | `0x1401A89C7` |
| 146/1 untouched AddMessage | `0x1401A85A3` |
| FireSpell message Run→FireSpell | `0x140212E89` |
| 146/2 direct Effect::FireSpell | `0x1401A85C5` |
| 148/1 and /2 direct FireSpellPoint | `0x1401A890E` |

`dispatch_carrier_api.cpp` establishes a scope for every 146/148 ApplyEffect,
including unowned reentrant calls, so unrelated effects mask an outer origin.
Mode0 constructor callbacks carry the selected Force/Spell route without
rewriting native fields. Mode1 attaches a retained origin to the actual
FireSpell message before its untouched AddMessage. The actual deleting
destructor handles queued cancellation as well as eventual processing. A Run
scope and its precise FireSpell call edge recover the correct message; nested
unowned Run calls mask their parent. Native source/target IDs and message data
remain unchanged. A native AddMessage return does not itself prove deletion, so
the implementation does not erase ownership based on that return value.

The direct 146/2 and 148/1/2 handoffs require the current effect, exact return PC
and native receiver to agree. These handoff queries are for the concrete cast
entry unit; they do not replace the still-required pre-selection hooks.

## Binding and real entry installation

`generate_dispatch_profiles.py` and `dispatch_binding.hpp` certify eight body
spans covering all six entries and attribution calls. Only the two known EEex
mode0 call sites are excluded. Those must have the installed E9 route to
readable executable memory outside the native bodies and route sites. As with
the existing Marshal binder, these checks do not certify every dynamically
generated EEex cave instruction; its established semantics and lifetime remain
host-owned. The FireSpell vtable's seven relocated entries must match the
audited class. Unknown code changes refuse before patching.

`dispatch_hook_host.cpp` uses the internal `entry_hook_group.hpp` transaction to
install the six certified entries, near relays and actual Windows unwind
records. It preserves page protections, checks all entries before removal,
refuses later-owner changes, rolls back partial writes, and keeps reachable code
registered if cleanup cannot finish. Initialization/removal requires the
quiescent owner thread and exclusion of other execution/writers. The shared
internal transaction is not an exported arbitrary-hook API.

Focused results:

- **12 passed:** actual copied prologues versus trampolines in both executables,
  including registers/flags/stack and real RtlVirtualUnwind at every emitted
  instruction. A fixture lookup initially used a list index for a dictionary;
  correcting that lookup allowed all native checks to execute and pass.
- **55 passed:** 28 read-only relocated-image binding checks, 15 compiled
  producer/message cases, 11 private entry transaction cases and one complete
  independent DLL link. Log `C:/tmp/scroll-dispatch-host.log`.

Read-only SEC_IMAGE tests explicitly provide only the inspected vtable
relocations and simulated external route pointers on private COW pages. They do
not initialize imports/globals or call game/cave functions. Host transaction
tests patch only our own inert private instruction fixtures. Compiled callbacks
use controlled native-callee substitutes; that does not make them engine tests.

```text
python -m pytest tests/test_scroll_runtime_dispatch_detours.py -q
python -m pytest tests/test_scroll_runtime_dispatch_host.py tests/test_scroll_runtime_dispatch_binding.py tests/test_scroll_runtime_dispatch_carriers.py tests/test_scroll_runtime_independent_dll.py -q
```

The default-constructor hook was planned with an action-copy/destruction host
covering its observed lifetimes. That host shipped in alpha.11 to alpha.13 and
was removed on October 23: the engine destroys most actions inline, where no
hook observes them ([action-witness-evidence.md](action-witness-evidence.md)).
Seven native cast entries and their selector/
child hooks, linked177, the complete loader initializer and dispatch/load/save
barriers remain integration work. No callback group is installed automatically
by DLL binding initialization.
