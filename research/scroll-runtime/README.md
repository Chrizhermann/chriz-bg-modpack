# Reader-level scroll casting

Current status, October 9, 2026: component **430** now has an actual WeiDU install path,
a linked independent `CBMScroll.dll`, early EEex startup, and a bundled installed-resource
policy builder. The old fixed-level-15 ITM patch is replaced. Nothing has been installed
into a real game; no game or save has been launched or written.

See [component430-status.md](component430-status.md) for the current package, supported
native profiles, bounded checks, and the remaining user-run acceptance check. Earlier
reports describe the milestones when written; their "remaining integration" sections
are historical, not the present delivery status.

## Implemented route

- `scroll_context.hpp`, `native_api.*`, `native_provider.hpp`, `native_binder.hpp`: original
  reader/item ownership, active native class/caster queries, lifetime generations, and
  certified native addresses. Dormant dual classes are excluded. Recognized active caster
  capability is queried natively, not inferred from known-spell counts or a kit-name list.
- `item_*`, `dispatch_*`, `cast_*`, `action_*`: concrete item roots, 146/148 delivery,
  action/message copy and destruction, seven pre-ability-selection sites, and child effects.
- `linked177_*`, `conditional_*`: linked EFF decoding and actual 326, 272, and six 232 cast
  sites, including four embedded contingency cleanup sites. Typed children retain original
  ownership through native untyped helpers and repeating edges.
- `decode_*`, `marshal_*`, `lifecycle_*`, `eeex_save_bridge.*`, `CBMS_ScrollMarshal.lua`:
  existing EEex lifecycle chaining, exact emitted native record association, actor-owned
  metadata, reader UUID binding, and already-proven per-cast scalar persistence.
- `installed_resources.py`, `policy_table.*`, `policy_resource*`: effective ITM/SPL/EFF
  classification and full-resource SHA256 validation; manual learning and explicit genuine
  protection-scroll families retain native behavior.
- `startup.*`, `startup_lua.cpp`, `CBMS_Startup.lua`: one early initialization transaction,
  reverse rollback, admission only after every group and resource hash is verified, and
  visible failure diagnostics. No hot activation or in-session unload is offered.
- `build_runtime_package.py`: builds the independent DLL outside source/game directories,
  then copies only distributable DLL/Lua files into `chriz-bg-modpack/scroll-casting`.
  End users need neither Python nor a compiler.

This implementation chains the existing EEex owner; it does not require a forked EEex.dll.
The repository contains native ABI/body evidence, actual-byte emulation, Windows unwind
checks, private hook transaction checks, and real synthetic WeiDU installation checks.
These are separate from native game acceptance, which remains unperformed.
