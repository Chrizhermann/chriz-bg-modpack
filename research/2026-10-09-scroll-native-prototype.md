# Reader-level scroll casting: native selector prototype

October 9, 2026. This report preserves the initial offline native investigation,
following [the behavior brief](2026-10-09-scroll-caster-levels.md). The subsequent
implementation now replaces component430's fixed-level patch through a real installer
and independent native DLL. See the [current delivery status](scroll-runtime/component430-status.md).
No real game installation or native acceptance has been performed.

The new result is stronger than a mocked caster-level callback: seven actual
native ability-selection loops were executed in an emulator against two local
executables, with 168 passing cases per executable. The investigation also
establishes concrete item, message, action, effect-copy and linked-EFF boundaries
needed by an effect-aware implementation. That initial investigation did not
establish complete native context persistence, active-kit classification or live
acceptance. The continuation below resolves native class/capability querying;
extension-defined casting systems and installed kit tables remain outside its
offline acceptance coverage.

Implementation continuation: the subsequent
[uninstalled native context extension](scroll-runtime/README.md) now provides
compiled C++ origin/lifetime handling, all seven selector adapters, SPL/177 child
propagation, an exported callback ABI, a native reader-provider adapter and
27 passing focused context/provider tests. Its subsequent
[mapped-module binder](scroll-runtime/binder-evidence.md) adds 79 checks against
relocated pinned images and invalid layouts, for 106 passing tests in the
combined run. No resolved game function is called from those views. The additional
[reader audit](scroll-runtime/reader-provider-evidence.md) executes 875 native
class/capability calls per binary. The later concrete detours, startup, persistence, and component430 package are
documented in the current delivery status. Initialized-engine acceptance remains pending.

No game was launched, no game or save was written, and no full installation was
copied. The executable files were read into analysis-process memory only.

## Evidence and reproduction

Source pins:

- [EEex](https://github.com/Bubb13/EEex/tree/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285),
  v1.3.1 source snapshot.
- [InfinityLoader](https://github.com/Bubb13/InfinityLoader/tree/817925caab3eb9cf600cfaf38853da8d30c28247).

The version-specific EEex `function_names.db` files supply symbol addresses;
branch behavior below was checked against actual PE instructions. A nearest
symbol name alone is insufficient evidence, especially for folded functions.
Linear disassembly also prints embedded jump tables as instructions; those
regions must be read as data.

| Local executable | SHA-256 |
|---|---|
| BG2EE 2.6.6.0, development clean install | `fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580` |
| BG2EE 2.7.3.0, Combined-20260908 captured install | `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57` |

[`scroll-native/selection_probe.py`](scroll-native/selection_probe.py) uses
Capstone 5.0.9, pefile 2024.8.26 and Unicorn 2.1.4. It verifies the executable
hash, loads the PE into emulator memory, and executes the bounded selection
instructions without changing those instructions. Only native CSpell resource
getters and the integer `max` helper are replaced with fixture providers.

The input is the replacement level at the identified pre-selection boundary.
The observed result is the actual selected native header pointer. Cases use
header minimums `(1, 6, 12, 20)` and `(1, 5, 10, 15, 25)`, at levels
`1, 3, 5, 6, 7, 10, 12, 15, 19, 20, 25, 30`. All selected the expected highest
eligible header. All emulator writes stayed within the temporary stack; the
fixture actor/resource region remained identical. That preservation assertion
applies to the **selection windows only**, not to complete casting/charge use.

Results, including exact instruction-window hashes:

- [2.6.6.0: 168/168](scroll-native/selection-2.6.6.0.json).
- [2.7.3.0: 168/168](scroll-native/selection-2.7.3.0.json).

Example, run from this worktree with the dependencies on `PYTHONPATH`:

```powershell
python research/scroll-native/selection_probe.py `
  "%USERPROFILE%/CEBG-Tests/Combined-20260908/game/Baldur.exe" `
  C:/tmp/scroll-hook-research-20261009/EEex/EEex/loader/v2.7.3.0/bg2ee/function_names.db `
  --out research/scroll-native/selection-2.7.3.0.json
```

## The mode distinction is material

The following native addresses are for the pinned **2.7.3.0** executable.
[Dispatch evidence](scroll-native/bg2ee-2.7.3.0-dispatch.txt),
[fire/action evidence](scroll-native/bg2ee-2.7.3.0-fire.txt), and the
[2.6.6.0 corresponding trace](scroll-native/bg2ee-2.6.6.0-trace.txt) are retained.
These are address observations for reviewed binaries, not hardcoded universal
engine constants.

| Dispatcher | Actual route | Explicit parameter 1 |
|---|---|---|
| 146, mode 0 | Creates `CMessageInsertAction`; later runs `ForceSpell` | Copied into action `m_specificID`; zero asks native caster level |
| 146, mode 1 | Creates **`CMessageFireSpell`**; its later `Run` invokes `CGameAIBase::FireSpell` | Not read on this branch |
| 146, mode 2 | Calls `CGameEffect::FireSpell` directly | Passed as explicit selection level |
| 148, mode 0 | Creates `CMessageInsertAction`; later runs `ForceSpellPoint` | Copied into action `m_specificID`; zero asks native caster level |
| 148, modes 1 and 2 | Both take the same `CGameAIBase::FireSpellPoint` branch | Neither reads parameter 1 |

In particular, the mode name **instant** does not mean synchronous same-stack
execution. For 146/1, `0x1401A84B0` allocates a 0x20-byte message, assigns source
and target IDs and the spell string, then submits it at `0x1401A859E`.
`CMessageFireSpell::Run` resolves those IDs and calls `FireSpell` at
`0x140212E84`. There is no explicit caster-level member in that path. For 148,
every nonzero mode reaches the same call at `0x1401A8909`.

The existing [EEex opcode hooks](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Opcode_Patch.lua#L108-L146)
attach to the **mode-0** message call sites. They do not expose the 146/1
message. They also change mode-0 actions to `SpellNoDec`/`SpellPointNoDec` when
`special & 1` is set. That feature must be preserved.

The pinned 2.7 action switch maps action 191 through table byte index 24 to
`0x140396B43`, which calls `CGameSprite::Spell`; action 192 maps through index 43
to `0x140397238`, which calls `CGameSprite::SpellPoint`. The table RVAs are
`0x398990` (byte index) and `0x3987AC` (branch RVAs).
[Action dispatch](scroll-native/bg2ee-2.7.3.0-action-dispatch.txt) and
[the two additional selection paths](scroll-native/bg2ee-2.7.3.0-extra-paths.txt)
are retained. The prototype includes these two selection loops too.

## Verified pre-selection boundaries

All these loops compare the SPL ability's minimum caster level at header +0x10
before selecting the ability. The native ability list, ordering and caps remain
in control. A replacement after this comparison is too late.

| Native function / covered path | Selector input boundary | Working level | Comparison / selected-header boundary |
|---|---|---|---|
| `CGameEffect::FireSpell`, 146/2 | `0x1401E466D` | Explicit stack argument `[rbp+0x77]`, read at `0x1401E4690` | Compare `0x1401E46A2`; R13 is selected header at `0x1401E46D8` |
| `CGameAIBase::FireSpell`, 146/1 | `0x14016AD21` | R8W, then stack local | Compare `0x14016AD6E`; RAX header at `0x14016ADA1` |
| `CGameAIBase::FireSpellPoint`, 148/1/2 | `0x14016BB02` | R8W, then R13D | Compare `0x14016BB4E`; RAX header at `0x14016BB7B` |
| `CGameAIBase::ForceSpell`, 146/0 | `0x14016C84B` | R14D | Compare `0x14016C870`; RAX header at `0x14016C8A4` |
| `CGameAIBase::ForceSpellPoint`, 148/0 | `0x14016D84A` | R12W, then R14D | Compare `0x14016D872`; RAX header at `0x14016D89B` |
| `CGameSprite::Spell`, special-bit action | `0x1403B4DED` | Working caster-level word `[sprite+0x4C8A]` | Compare `0x1403B4E19`; R13 header at `0x1403B4E40` |
| `CGameSprite::SpellPoint`, special-bit action | `0x1403B6A9B` | Same working caster-level word | Compare `0x1403B6AD7`; R13 header at `0x1403B6AFE` |

These are probe boundaries, not a tested hook installation recipe. Several
native functions make further caster-level queries after selecting the header.
The hook must retain the chosen level for the particular cast, without changing
unrelated spellcasting or globally replacing every `GetCasterLevel` result.

## Where the origin must be attached and transferred

### Root: before native item targeting splits

`CItem::GetAbilityEffect` receives `item`, ability index, effect index and reader
in RCX/EDX/R8D/R9. Its effect result is available before the caller routes it.
At `0x1401FB4B8` it decodes the item effect; it then sets native source type 2,
source item resref and source flags, and **caster level 10** at effect +0xC8.
The returned effect is available at `0x1401FB563`.
[Evidence](scroll-native/bg2ee-2.7.3.0-level-item.txt).

This is a concrete root for a separately owned origin token: actual installed
item, ability/effect identity, original reader and one use-instance token. Item
classification still belongs to the approved ordinary-scroll policy; names,
prefixes, parameter 1 and a current equipment slot are not sufficient.

All four item-use families reach this root. The captured caller paths split
after it into self-target effect messages, direct/party processing and projectile
effect lists. For example, `UseItem` calls this root at `0x1403BBAB4`, queues a
self-effect message at `0x1403BBB7D`, adds projectile effects at `0x1403BBBDA` /
`0x1403BBBFF`, or invokes party effect processing at `0x1403BBC17`. Its later
charge decrement reaches `SetUsageCount` at `0x1403BBF29`.
`UseItemPoint`, `FireItem` and `FireItemPoint` call the same root at
`0x1403BC637`, `0x14016A55C` and `0x14016A92C` respectively.
[Caller evidence](scroll-native/bg2ee-2.7.3.0-use-item.txt).

Therefore an AddEffect projectile mutator alone misses supported native item
paths. The root hook must leave the native routing and charge code intact.
Learning/non-casting abilities need explicit classification coverage before a
runtime can claim they are unaffected.

### Copies, reflection, SPL children and opcode 177

1. **Live effect copy:** current EEex already copies `exEffectInfoMap` metadata
   through `Opcode_Hook_OnCopy` and erases it through `OnDestruct`.
   [Native handlers](https://github.com/Bubb13/InfinityLoader/blob/817925caab3eb9cf600cfaf38853da8d30c28247/EEex-Core-Shared-Files/source/EEex.cpp#L4666-L4680),
   [copy/destruction hooks](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Opcode_Patch.lua#L5-L44).
   The inspected 146 `Copy` calls `CopyFromBase` at `0x1401CFAFE`.
   Extending this owned native metadata carrier is preferable to effect-pointer
   Lua entries with no established destruction lifetime.
2. **Reflection:** `CBounceList::Add` writes the reflector's native ID into
   effect source ID (+0x110) and source-target ID (+0x150), and replaces the
   source point at `0x14014C971`–`0x14014C986`. It then gives the **same effect**
   to the reflected projectile at `0x14014C9EB` or `0x14014CA3E`.
   [Evidence](scroll-native/bg2ee-2.7.3.0-context-copy.txt).
   Thus source ID later in the chain is not proof of the original reader.
   Keep origin separately; do not undo native source/target changes.
3. **SPL children:** all five basic cast routes call `CSpell::GetAbilityEffect`.
   That function sets source type/resref to the SPL, then independently calls
   `GetCasterLevel` at `0x14024EF83` and writes effect +0xC8 at `0x14024EF8B`.
   [Evidence](scroll-native/bg2ee-2.7.3.0-spell-child.txt).
   A selector-only override leaves this child level dependent on the native
   caster. Attach ancestry and the cast's resolved level to the returned child
   within the explicitly attributed native cast, before target dispatch.
4. **Linked EFF via opcode 177:** the parent reaches
   `DecodeEffectFromBase` at `0x1401A6D25`, then copies source IDs/points, timing
   and selected flags into the returned child. It **does not** propagate native
   source type, source resref or caster level. The child is checked/applied at
   `0x1401A6E16` / `0x1401A6E3B`.
   [Evidence](scroll-native/bg2ee-2.7.3.0-eff-class.txt).
   A specific parent-to-child transfer is required just after that decode:
   RBX is the live parent and RAX the child. EEex deliberately excludes the raw
   `DecodeEffectFromBase` caller from its generic live-effect copy hook, so the
   existing copy hook does not solve this edge.

### Queued messages and actions

- **146/1:** attach a retained origin to the actual newly created
  `CMessageFireSpell` before its AddMessage call. Enter the corresponding cast
  context around that message's `Run` call to `FireSpell`; release the message's
  context on both processing and cancellation/destruction. A single “last scroll
  reader” variable cannot cover two queued readers or a reflected cast.
- **146/0 and 148/0:** attach origin to the message's embedded action (+0x10).
  `CMessageInsertAction::Run` passes that action to `InsertAction` at
  `0x1402130A1`. `InsertAction` makes a new action using `CAIAction::operator=`
  at `0x140162869`; `SetCurrAction` again uses the operator at `0x140163948` to
  write the reusable current-action object (+0x3F8).
  [Evidence](scroll-native/bg2ee-2.7.3.0-context-copy.txt).
  The operator is an exact copy-propagation boundary. It must copy owned context
  when present and clear stale destination context when absent. The action
  destructor and every actual copy/assignment constructor need lifecycle
  coverage. Do not consume the context on the first action tick: native casting
  can continue over later ticks.
- **146/2 and 148/1/2:** enter a bounded call frame directly from the live
  dispatcher effect around the native fire call. Do not substitute another mode
  or manufacture a new cast.

The source fields and action parameters are native gameplay data, not spare
storage. Do not encode a token in `m_specificID2/3`, strings or effect padding
without a separate proof that the engine and installed mods do not use it.

## Minimum native extension contract

This describes the native integration contract. Its context/callback portion is
now implemented in [scroll-runtime](scroll-runtime/README.md); the engine detours
are not wired and it is **not an upstream EEex API**. No broad post-selection
`GetCasterLevel` replacement is sufficient.

1. Own an immutable origin object with an independent use-instance token,
   installed item/ability identity and original reader identity. Associate it
   with live effects, the 146/1 message and copied mode-0 actions at the exact
   producer/copy/destruction boundaries above. Use lifecycle-aware handles;
   object IDs or pointer keys alone must not survive object reuse unchecked.
2. Enter a cast frame from an explicit effect/message/current-action carrier.
   The frame owns the installed CSpell instance, mode, engine-resolved caster,
   original origin and resolved replacement level. A nested cast without such
   a carrier creates an empty/masking frame instead of borrowing the outer
   frame. Scope by native call and CSpell instance, not solely by resource name.
3. At each applicable selector boundary, request an optional level using that
   frame. The callback sees original reader, actual dispatcher, installed SPL,
   native level and native destination. It may replace **only the level**.
   An ordinary unowned cast must retain its native level and effects.
4. At the verified `CSpell::GetAbilityEffect` returns within that attributed
   cast, pass ancestry to each native child and stamp the resolved child caster
   level consistently. Inherit through 177's specific decode and live effect
   copies. Re-evaluate the relevant installed spell type for nested typed SPLs;
   do not assume a wrapper's resource prefix supplies the final casting type.
5. Clean up on every normal, early-return and cancellation path. Copy metadata
   by value/shared immutable origin into messages/actions before the producing
   stack frame ends. Reflection keeps the origin while native routing fields
   change. An unrelated reentrant cast masks the outer context.
6. Establish native serialization behavior before supporting pending casts
   across save/load. An in-memory map is not persistence. The inspected
   `CMessageFireSpell::MarshalMessage`/`UnmarshalMessage` encode the native
   source, spell and target, with no origin token or level field
   ([evidence](scroll-native/bg2ee-2.7.3.0-extra-paths.txt)). These are message
   transport functions; their names do **not** prove save persistence. Native
   effect/projectile/action save handling and remote-message transport require
   separate context support, or a precisely documented unsupported boundary.

An ancestry path/depth bound and a visited-resource set are needed for analysis
of linked SPL/EFF graphs. At runtime, repeated resource names in separate casts
are legitimate; a global “already visited resref” set would suppress valid work.
Do not make all shared SPL/EFF users scroll casts merely because one scroll
references that resource.

## Reader-level calculation: initial gap and subsequent proof

The initial findings below explained why a level-query shortcut was insufficient.
The subsequent [reader audit](scroll-runtime/reader-provider-evidence.md) located
and exercised the native active-class/capability methods, and
`scroll-runtime/native_provider.hpp` now implements that adapter. Its loaded
engine integration and nonnative casting systems retain the stated limits.

Keep the agreed rule: relevant **active** caster level; otherwise
`max(1, floor(highest_active_class_level / 2))`. Native ability selection then
preserves each spell's ordinary header cap.

The disassembly establishes why a shortcut is unsafe:

- `GetCasterLevel` selects `GetWizardLevelCast` / `GetPriestLevelCast` using
  `CSpell::GetCasterType`, but these derived-stat queries return 1 for a
  non-casting class. A positive result is not a casting-capability test.
- The priest query contains the Paladin/Ranger reduced-progression branches;
  reading a raw character level instead would miss those rules.
- `GetMaximumLevel` takes maxima of physical class level fields. No dormant-dual
  exclusion was found in that function itself. `GetLevelField` and
  `GetClassLevel` do not supply a proven active-class capability classifier.

Evidence: [caster/level queries](scroll-native/bg2ee-2.7.3.0-dispatch.txt),
[casting progression](scroll-native/bg2ee-2.7.3.0-level-item.txt),
[level-field/max helpers](scroll-native/bg2ee-2.7.3.0-eff-class.txt),
[class-level helper](scroll-native/bg2ee-2.7.3.0-class-level.txt).
Native class capability can now be resolved without a kit-name whitelist through
the audited methods. Arbitrary casting outside native class mechanics and
untyped/mixed wrapper classification remain unresolved integrations. Those must
be resolved from installed mechanics, not English names, UAI, empty/nonempty
spellbooks or vanilla resource IDs.

## Honest completion boundary

**Proved offline:** concrete dispatch differences for 146/148; pre-header
selection points; 336 passing native selection cases across two executables;
item-root ordering before target splitting; 146/1 queue lifetime; mode-0 action
copy boundaries; reflection's source-ID rewrite; SPL/177 ancestry gaps.

**Not proved or shipped:** installed hook ABI/lifetime integration, arbitrary
nonnative kit casting integration, origin serialization/recovery, all other linked
dispatch opcodes, genuine fixed-level exception classification, SR/non-SR
installed-resource matrix, independent Mirror Image scaling, native charges,
targeting/reflection outcomes and live save/load. No synthetic selector result
is being presented as coverage of those paths.

The scoped native origin/cast extension and focused ownership tests now exist
in [scroll-runtime](scroll-runtime/README.md). Engine lifecycle wiring, resource
integration and native acceptance remain. A Lua-only projectile rewrite or
fixed-15 fallback would not meet the settled behavior.
