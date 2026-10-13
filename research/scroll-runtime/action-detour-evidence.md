# Action lifecycle bridges: offline implementation checkpoint

October 9, 2026. `action_detours.py` emits real x64 bridges for the pinned 2.6.6.0
and 2.7.3.0 binaries in `binder-profiles.json`. Nothing patches a game process or
file. This is one lifecycle edge, not the complete scroll hook set.

The copy constructor and assignment bridges run after native copying finishes,
before `mov rbx,[rsp+30h]; mov rax,rdi`. At that point RBX is the source and RDI
the destination. The destructor bridge runs before `push rbx; sub rsp,20h`.
It removes metadata before either CString is destroyed. The native destructor
tail-jumps into the last CString destructor; it is not treated as a simple RET.
The complete native bodies and stolen boundaries must match the audited image.
Unsupported/altered bodies and unreachable rel32 bridges refuse emission.

Callbacks call the compiled `CBMS_ActionCopied` / `CBMS_ActionBeforeDestroy` ABI.
Copy construction refuses an already-live destination. Assignment replaces the
destination context, including clearing it when the source is unowned;
self-assignment preserves it. Existing unowned actions are registered upon first
observation. This still requires host teardown for actions never destroyed by
an installed hook; these three bridges alone do not cover message creation,
effect ancestry or cast entry/exit.

Every GPR except RSP, flags, and volatile XMM0–5 is saved; the Windows callback
ABI preserves XMM6–15. The callback receives aligned stack/shadow space.
Tests execute the actual pinned native action instructions plus emitted bridge
instructions in Unicorn. Only CString/object-copy helpers are replaced by
deterministic fixture operations; the bridge invokes the real compiled callback
through the test host, then deliberately clobbers permitted volatile state.
Original versus hooked action fields, helper order, registers, flags, stack,
return value, ownership, unowned assignment and self-assignment are compared.

## Native Windows unwind correction

The Windows `RtlVirtualUnwind` check initially found two real defects. A naive
chain after extra bridge allocation restored the native RBX from the wrong
establisher-frame offset. Flattened per-instruction unwind records now adjust
native SAVE_NONVOL offsets by the live bridge allocation.

The final `ff25` indirect jump was also wrong: Windows recognizes its ModRM00
form as an epilogue, although this bridge jumps **into an active native frame**.
The bridge now stores the return address in the audited native callee's unused
32-byte call-home area and branches using `jmp [rsp+0]` (ModRM01), preserving
all registers/flags. This follows Microsoft's documented
[x64 epilogue grammar](https://learn.microsoft.com/en-us/cpp/build/prolog-and-epilog).
The call-home bytes are not promised unchanged: no remaining native instruction
at these three sites reads them before another call may overwrite them.

The lead's focused run passed **24 cases**: 18 detour cases and six OS-unwind
cases, spanning both builds. OS unwinding is checked at every emitted instruction
against copied stacks, including partially completed save/restore sequences and
the final branch. It restores the native caller's RIP/RSP and all nonvolatile
GPRs. The OS reads inert private instructions and native read-only SEC_IMAGE
metadata; no game or bridge entry point is called natively.

## Actual registration

`action_loader.py` builds one private bundle containing instructions, flattened
UNWIND_INFO and sorted RUNTIME_FUNCTION entries. `RegisteredUnwind` validates
table bounds, private committed readable allocation, exact emitted bytes and
conflicting registrations, then calls
[RtlAddFunctionTable](https://learn.microsoft.com/en-us/windows/win32/api/winnt/nf-winnt-rtladdfunctiontable).
Four tests cover both builds: every registered instruction range resolves through
the real `RtlLookupFunctionEntry`, and removal uses `RtlDeleteFunctionTable`.
Corrupt, unmapped, malformed and duplicate bundles refuse registration. Test pages
remain read-only/non-executable. These operations affect only the test process.

The host must keep bundle memory alive until hooks are removed and no thread can
execute or unwind inside it. Registration does not install hooks, establish
engine-thread quiescence, or grant permission to free active code. The loader
does not modify a native module, allocate executable memory or invoke callbacks.

Focused commands (MSVC x64 and `PYTHONPATH=C:/tmp/xp-banking-analysis-deps`):

```text
python -m pytest tests/test_scroll_runtime_detours.py tests/test_scroll_runtime_unwind.py tests/test_scroll_runtime_registration.py -q
```

Unicorn on this host produces a handled first-chance access-violation diagnostic
when mapping even an empty emulator address space. The minimal reproduction
continues and exits0. This is separate from the genuine unwind assertions above;
no diagnostic suppression or test bypass was added.
