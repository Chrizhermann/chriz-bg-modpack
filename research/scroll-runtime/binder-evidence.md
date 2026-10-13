# Read-only native provider binding

October 9, 2026. Implemented in `native_binder.hpp`, exposed by
`CBMS_BindModule` and `CBMS_BindCurrent` in the compiled native callback library.
This closes the offline function-table certification step. It does **not**
install hooks or establish a working in-game scroll implementation.

## Concrete behavior

`CBMS_BindCurrent` inspects the process's existing main module through
`GetModuleHandleW(nullptr)`. It never calls LoadLibrary, starts a process,
initializes the game, or executes the returned functions. `CBMS_BindModule`
performs the same certification on an explicitly supplied mapped image base.

Before publishing any pointer, the binder verifies:

- Page-aligned base; Windows `MEM_IMAGE` allocation ownership and bounded
  ranges. Every read uses `ReadProcessMemory` after `VirtualQuery`, avoiding a
  raw dereference of an untrusted PE header or unreadable page.
- DOS and PE signatures, bounded PE-header location, AMD64 executable machine
  type, PE32+ optional header, section count, table bounds, section/image
  alignment, image extent and nonoverlapping section extents.
- Supported timestamp, image size and entry RVA select one audited profile.
  These are selectors, **not sufficient proof of ABI identity**.
- Every audited span belongs to an executable/readable code section and has
  committed readable/executable pages inside this allocation.
- SHA-256 of every complete audited instruction span, including internal jump
  tables and padding. No first-instruction-only or wildcard match is accepted.

Only after all checks pass are the eight typed function pointers calculated as
`actual module base + audited RVA`. Bind success returns 1. Refusal returns 0,
preserves the caller's entire output table, and supplies a diagnostic naming the
layout obstacle or altered native function. The host must then leave native
behavior enabled and report that reader-level scroll integration was not enabled.
It must not suppress a failed bind and later invoke an old/partial table.

The caller must provide a writable diagnostic buffer (512 bytes is used in the
tests), retain the module lifetime, and exclude concurrent unload or code
mutation throughout certification and subsequent use. `ReadProcessMemory`
contains inaccessible-read failure; it is not a synchronization primitive.
There is no process-wide patch lock, loader implementation, ongoing code monitor,
or attempt to repair another mod's hook.

After successful binding, the existing `CBMS_CreateNative(&functions, ...)`
constructs the actual provider using this certified table. No generic mock API
was added. The current-process entry point correctly refuses the Python test
host, whose main executable is not a supported game image.

## Supported instruction profiles

[`binder-profiles.json`](binder-profiles.json) records the exact source hashes,
RVA/length/hash of every span and image metadata. [`binder_profiles.hpp`](binder_profiles.hpp)
is the generated C++ equivalent. The offline generator reads the pinned
executables and matching pinned EEex symbol databases; an unexpected source hash
or base-relocation entry intersecting a signature span stops generation.

| Source build | Audited spans | Bytes hashed | Source executable SHA-256 |
|---|---:|---:|---|
| BG2EE Windows x64 2.6.6.0 | 19 | 4,224 | `fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580` |
| BG2EE Windows x64 2.7.3.0 | 19 | 4,384 | `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57` |

The eight callable entries are GetDeny, GetActiveInactiveClasses, GetLevel,
GetMaximumLevel, CanCastMageSpells, CanCastPriestSpells, GetCasterType and
GetCasterLevel. Additional signatures cover IsUsableSubClass, GetLevelField,
GetKitMask, the folded current-class getter, PriestLevelCast, WizardLevelCast,
CSpell::GetLevel, GetMinCasterLevel, GetAverageLevel, max and sscanf. Names, calling
contracts and body boundaries are grounded in the preceding
[native reader audit](reader-provider-evidence.md); the folded getter's symbol
name does not change the proven five-byte class-read semantics.

These spans contain no base-dependent PE relocation slots. Their RIP-relative
calls and embedded RVA jump tables therefore compare unchanged at different
mapped bases. This does not claim that an otherwise uninitialized full game
image can safely run at any arbitrary address.

The binder deliberately does not compare every executable byte or mutable
native class/kit/rule-table data. Unrelated EEex hooks and loaded gameplay data
are outside this provider ABI gate. The pinned EEex/InfinityLoader source audit
found no direct modifications of these queried methods or signature-span hook
matches; derived-stat hooks affect construct/reload/copy/add/GetAtOffset instead.
This is source evidence about the pinned versions, not a universal claim about
installed third-party detours. A changed audited body gives a named refusal and
requires a separate ABI audit; its bytes are never restored or bypassed.

This is a bounded provider ABI certification, not a transitive integrity audit
of the whole engine. Native resource demand/virtual dispatch, CRT internals,
initialized globals and installed rule data remain native host contracts. The
provider still needs a valid original actor/CSpell and the existing lifetime
checks. Binder success cannot certify arbitrary custom casting systems.

## Executed evidence

The combined focused run passed **106 tests**: 27 context/provider ABI tests and
79 mapped-image binder tests, compiled with MSVC x64 C++20 and `/W4 /WX`.

```powershell
python -m pytest tests/test_scroll_runtime_native.py tests/test_scroll_runtime_binding.py -q
```

Binder checks use read-only file handles and `SEC_IMAGE` memory-map views at
`0x200000000` and `0x300000000`, both different from the preferred `0x140000000`.
No LoadLibrary, executable entry point, game function pointer, or game process
is invoked. The OS supplies image-shaped test mappings only; imports, globals
and runtime startup are not initialized as a game.

Coverage:

- Both profiles at both nonpreferred bases; all eight resolved addresses equal
  that mapping's base plus the independently recorded function RVA.
- Every one of 19 native/dependency spans rejects a changed byte, including the
  last span byte, proving certification is not restricted to entry prefixes.
- Wrong/truncated PE-header declarations, architecture/magic, section counts,
  oversized/misaligned/overlapping sections, unreadable headers/code,
  nonexecutable code, unsupported metadata and invalid addresses refuse.
- Private allocated buffers are refused even if readable: they are not mapped
  PE images. The unrelated current Python executable is also refused.
- Refusal leaves all eight output pointers unchanged. Successful reads preserve
  all observed headers and instruction spans.
- Unrelated entry-point-code and writable-data changes still certify, avoiding
  an arbitrary pristine-whole-install requirement.

Deliberate mutations use private copy-on-write pages in the test process. The
on-disk executable hashes are checked again after every mapping is released and
remain identical. No executable or game installation was copied. Tests explicitly
skip when the unbundled pinned executables are absent; such a skip is not native
certification evidence.

Remaining acceptance: call the binder from an authorized initialized engine,
confirm its actual loaded instruction profile, install/review the separately
required lifecycle/selection detours, and validate resources, transport and
save behavior. None of that occurred in these tests.
