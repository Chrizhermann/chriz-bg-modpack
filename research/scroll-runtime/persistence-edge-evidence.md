# Effect persistence: implemented association and remaining native integration

October 9, 2026. Action copy/assignment/destruction is now a concrete emitted,
emulated and OS-unwound bridge. That preserves queued ownership within a session;
it does not turn pointer-keyed metadata into saved context.

The pinned current InfinityLoader source is commit
`817925caab3eb9cf600cfaf38853da8d30c28247`. Its
[CGameEffectList::Override_Unmarshal](https://github.com/Bubb13/InfinityLoader/blob/817925caab3eb9cf600cfaf38853da8d30c28247/EEex-Core-Shared-Files/source/EEex.cpp#L4961)
iterates serialized effects. It recognizes X-BIV1.0 records as actor-level Lua
marshal data, otherwise calls `DecodeEffectFromBase` and `AddTail`. No call at
that normal decode edge restores custom per-effect ancestry. Version0 also
calls virtual_OnLoad per effect, which is not the version1 path. Thus a Lua
sprite importer alone cannot identify a particular pending dispatch effect.

The same source's
[post-unmarshal UUID hook](https://github.com/Bubb13/InfinityLoader/blob/817925caab3eb9cf600cfaf38853da8d30c28247/EEex-Core-Shared-Files/source/EEex.cpp#L4809)
restores actor identity and calls the Lua loaded listeners. Actor UUID is useful
for original-reader rebinding, but it does not identify a message, embedded
CAIAction or particular effect among duplicate records. Copying an actor's
metadata table does not prove a live queued action survived native save/load.

The audited 2.7 CMessageFireSpell MarshalMessage at0x14020BDE0 writes source
remote-ID pair, spell string length/string, and target remote-ID pair. Its
UnmarshalMessage at0x14021B8B0 resolves remote IDs and reconstructs those native
fields. There is no original item/ability/reader/use token. These are transport
functions, not evidence of saved action queues. See the full existing disassembly
in `../scroll-native/bg2ee-2.7.3.0-extra-paths.txt`.

This association is now implemented in `effect_archive.hpp` and the compiled
native API. Both actual V1 Marshal bodies were emulated through completion:
32 cases prove native list order, timing2/9 filters, empty lists, duplicate effect
bytes with different pointer identities, actual emitted bytes and stack return.
See `effect_marshal_native.py`, `persistence-native-2.6.txt` and
`persistence-native-2.7.txt`. The API prepares the same ordered native records
before EEex calls exporters, then checks every actual emitted record afterwards.
It refuses a changed list/payload rather than assigning an ambiguous index.

Decode import consumes the actual `DecodeEffectFromBase(rawRecord)` argument
and returned effect pair. The native actor-envelope importer stages the saved
mapping; ownership commits only after all decoded rows pass byte/ordinal checks.
Identical rows remain distinct by their proven emitted ordinal. All allocation
and validation precede ownership commit. No native padding or gameplay fields
store metadata.

The `CBMSFX01:` ASCII codec preserves uint64 reader/origin identities without
passing them through Lua numbers. `CBMS_ScrollMarshal.lua` retains the original
actor table before parsing, keeps unknown schema/fields unchanged, and avoids
duplicating EEex's separately exported fallback storage. Rejected imports remain
pending until their owner actually cancels the native operation; a failed stage
cannot be turned into successful Finish by ignoring its return value.

Restored effects retain a pending original-reader UUID until that same actor
lifetime registers. The recipient is never substituted. A previously resolved
effect level is also preserved and checked against native wire offset+C0;
opcode177 can inherit that already-proven scalar while the reader is absent.
A later differently typed spell still requires its own reader-level selection.

`eeex_save_bridge.cpp` implements the concrete native actor save/decode events.
`eeex_source_overlay.py` renders a reference integration at the actual pinned
EEex boundaries in memory. `eeex_lua_bindings.cpp` and `dll_entry.cpp` compile
against actual InfinityLoader headers. The latter provides independent
InitBindings(SharedState)/OpenBindings() entry points supported by the loader;
no replacement of EEex.dll is required. The independent decoder carrier wraps
the certified existing EEex Unmarshal target and native DecodeEffectFromBase,
scoping nested/V0/unrelated decodes rather than scanning a later effect list.

Normal native UUID binding happens before existing Lua loaded callbacks, by
reading EEex's `EEEX_UUID` local low32/high32 fields after its own registration.
The full-width archive cannot compensate for an upstream UUID implementation
changing an identity; its binding follows EEex's actual registered identity.

Queued actions/projectiles need their own proven save disposition first: if the
native engine cancels a queued action, metadata must be cancelled too, not
replayed to manufacture a cast. If it preserves one, the reconstructed carrier
needs explicit association. For remote FireSpell transport, adding bytes would
change the protocol; both endpoints and the message size/decode path need a
versioned extension. None is silently enabled by this checkpoint.

## Actual cancellation boundary

The newly captured `save-transaction-2.7.txt` shows why throwing from an EEex
exporter is insufficient. EEex's Lua exporter/importer calls are wrapped in
TryIgnore; the native V1 decode override returns void and continues after a Lua
failure. In the native overwrite flow, CScreenSave::SaveGame calls
DeleteSaveGame at0x1402DDD3C before inner SaveGame at0x1402DDDFB. Inner SaveGame
removes temporary files at0x140289E76, writes GAM at0x140289EFB, then marshals
areas at0x140289F4E. An inner failure return does not restore an overwritten slot.
Any preflight cancellation must precede the outer deletion. No filesystem
rollback is implemented or claimed.

LoadGame destroys the current world at0x1402806B2 when one is active. It checks
CInfGame::Unmarshal's success at0x140280F4B; its false branch reaches cleanup and
returns false, but that does not restore the previous world. The loaded-callback
wrapper orders UUID association before callbacks; a complete dispatch barrier
and supported failure/visible-error behavior still need native integration.

Current ConfigureCurrent refuses activation with these concrete missing edges;
it is not a usable installed candidate. The focused compiled archive, bridge,
native context, actual-header and two-Lua-family suite passes **63 tests**.
The separate actual-native Marshal probe passes32. These are different claims
from a game launch, real save/load, area transition, or install/uninstall result.
