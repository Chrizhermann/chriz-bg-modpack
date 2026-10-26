# Reader-level scroll casting

Current status, October 9, 2026: component **430** now has an actual WeiDU install path,
a linked independent `CBMScroll.dll`, early EEex startup, and a bundled installed-resource
policy builder. The old fixed-level-15 ITM patch is replaced. At that point nothing had
been installed into a real game. On October 23 a disposable lab game ran it for the first
time (below); no player game or save was used.

See [component430-status.md](component430-status.md) for the current package, supported
native profiles, bounded checks, and the remaining user-run acceptance check. Earlier
reports describe the milestones when written; their "remaining integration" sections
are historical, not the present delivery status.

## Implemented route

- `scroll_context.hpp`, `native_api.*`, `native_provider.hpp`, `native_binder.hpp`: original
  reader/item ownership, active native class/caster queries, lifetime generations, and
  certified native addresses. Dormant dual classes are excluded. Recognized active caster
  capability is queried natively, not inferred from known-spell counts or a kit-name list.
- `item_*`, `dispatch_*`, `cast_*`, `action_witness.hpp`: concrete item roots, 146/148
  delivery, message destruction, value-carried action ownership
  ([action-witness-evidence.md](action-witness-evidence.md)), seven pre-ability-selection
  sites, and child effects.
- `linked177_*`, `conditional_*`: linked EFF decoding and actual 326, 272, and six 232 cast
  sites, including four embedded contingency cleanup sites. Typed children retain original
  ownership through native untyped helpers and repeating edges.
- `decode_*`, `marshal_*`, `lifecycle_*`, `eeex_save_bridge.*`, `CBMS_ScrollMarshal.lua`:
  existing EEex lifecycle chaining, exact emitted native record association, actor-owned
  metadata, reader UUID binding, and already-proven per-cast scalar persistence. An
  outdated actor envelope is dropped for that actor alone
  ([persistence-edge-evidence.md](persistence-edge-evidence.md)).
- `installed_resources.py`, `policy_table.*`, `policy_resource*`: effective ITM/SPL/EFF
  classification and full-resource SHA256 validation; manual learning and explicit genuine
  protection-scroll families retain native behavior.
- `startup.*`, `startup_lua.cpp`, `CBMS_Startup.lua`: one early initialization transaction,
  reverse rollback, admission only after every group and resource hash is verified, and
  failure diagnostics in the loader log. Nothing is shown in the game unless the rollback
  itself fails: `CBMS_StartupRetained` (Lua `CBMS_NativeRetained`) then reports the kept
  runtime, and the script shows one EEex message box after its log lines, once per
  process. No hot activation or in-session unload is offered: a second load after a
  successful start turns the running overrides off through the native single-attempt
  refusal.
- `carrier_gate.hpp`: every hooked entry checks for the engine thread that installed it
  before touching carrier state; a call on another thread goes unchanged to the native
  original. That, and every reported error, latches one state that keeps every later
  selection at its native level, including casts already queued.
- `build_runtime_package.py`: builds the independent DLL outside source/game directories,
  then copies only distributable DLL/Lua files into `chriz-bg-modpack/scroll-casting`.
  End users need neither Python nor a compiler.

This implementation chains the existing EEex owner; it does not require a forked EEex.dll.
The repository contains native ABI/body evidence, actual-byte emulation, Windows unwind
checks, private hook transaction checks, and real synthetic WeiDU installation checks.
These are separate from native game acceptance. The first in-game check, in a disposable
lab on 2.7.3.0 with EEex v1.3.1, is recorded in
[action-witness-evidence.md](action-witness-evidence.md#lab-acceptance).
