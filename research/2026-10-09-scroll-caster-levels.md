# Reader-level scroll casting: feasibility and missing hook

Status: source investigation, October 9, 2026. **Component 430 has not been
replaced. Its released fixed-15 implementation is not acceptance of this task.**
This initial investigation made no runtime or item changes. A subsequent
uninstalled [native extension](scroll-runtime/README.md) now implements reader
context and native class/caster queries; it is still missing installed detours,
resource policy and save/transport integration. No recipe changes, game launches
or save changes were made. The subsequent
[offline native investigation and selector prototype](2026-10-09-scroll-native-prototype.md)
corrects the initial mode assumptions below. It establishes actual native
selection boundaries, but does not complete the runtime replacement.

## Settled behavior

Use the reader's active caster level appropriate to the installed spell type.
For a reader without that relevant active casting class, Christopher confirmed
**half the highest active class level, rounded down, minimum 1**. Do not add or
average multiclass levels; ignore a dormant dual class in this fallback.

| Reader | Arcane scroll | Divine scroll |
|---|---|---|
| Mage/specialist, Sorcerer, Bard | Relevant active arcane caster level | Half highest active class level unless an active divine casting capability exists |
| Cleric/Druid | Half highest active class level unless an active arcane casting capability exists | Relevant active divine caster level |
| Fighter 20 / Thief 24 | 12 | 12 |
| Dormant Mage 13 -> active Thief 12 | 6 | 6 |
| Reactivated Mage 13 -> Thief 14 | Mage caster level | 7 absent another divine capability |

Ranger/Paladin and mod kits require the engine's actual active spell-type
capability and caster progression, including reduced caster levels. A kit name,
UAI possession, or the query's minimum result is not proof of a casting class.
Non-thief access uses the same rule. Do not borrow an arcane caster level for a
divine spell, or classify SR spells by vanilla resource numbering. Retain normal
spell caps. The subsequent [reader-provider audit](scroll-runtime/reader-provider-evidence.md)
establishes native class/capability queries and their bounded checks. Arbitrary
casting extensions outside native class rules remain unverified; this policy
table alone does not establish compatibility.

## Source-backed early interception

Reviewed EEex v1.3.1 at
`a6d21abe44e20509f5d0259ccc6c7e7f9d12b285` and InfinityLoader at
`817925caab3eb9cf600cfaf38853da8d30c28247`. The relevant projectile API and native
caster-level label also exist in the checked EEex v1.2.0 source.

1. [`EEex_Projectile_Patch.lua:115-158`](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Projectile_Patch.lua#L115-L158)
   recognizes native `UseItem`, `UseItemPoint`, `FireItem` and `FireItemPoint`
   calls into `CProjectile::AddEffect`. It recovers the originating actor from
   the correct native register for each call path.
2. [`EEex.cpp:5793-5855`](https://github.com/Bubb13/InfinityLoader/blob/817925caab3eb9cf600cfaf38853da8d30c28247/EEex-Core-Shared-Files/source/EEex.cpp#L5793-L5855)
   invokes the registered global mutator before adding the effect. Lua receives
   `originatingSprite`, the actual mutable `effect`, source discriminator and
   projectile. This is a real item-use interception, not merely a caster query.
3. For a projectile-carried item opcode146/148, that hook occurs before the cast
   dispatcher executes its referenced SPL. Whether changing the explicit level
   affects selection depends on the native mode: it works through the normal
   mode-0 action field and 146/2's explicit argument, but 146/1 and 148/1/2 do
   not use that parameter. The later native probe verifies the exact selector
   boundaries; no game was launched.
4. [`EEex_Sprite.lua:682-690`](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Sprite.lua#L682-L690)
   provides `EEex_Sprite_GetCasterLevelForSpell`. The native `GetCasterLevel`
   label exists in `InfinityLoader.db:321`. Query availability alone establishes
   neither correct dual-class classification nor interception of all casts.

Preserve the original effect's source/target IDs, coordinates and native
destination. The sources inspected do not prove `projectile.m_targetId` is final
at `AddEffect`; reconstructing a new cast from it would be unjustified. Retaining
the original item-use path is also necessary to preserve its charge accounting.

The June EEex 0.11 investigation's blanket missing-label conclusion is historical
and must not be reused as a claim about current EEex.

## Why this is not yet a replacement for 430

- Projectile insertion alone does not establish coverage of caster-side/direct
  item effects, linked EFFs or nested spell dispatchers. Original scroll identity
  must survive every supported wrapper; merely observing an outer177 is not
  proof of the inner cast's ownership.
- Opcode403 screening is early, but recipient-local. Native
  [`Opcode_Hook_OnCheckAdd`](https://github.com/Bubb13/InfinityLoader/blob/817925caab3eb9cf600cfaf38853da8d30c28247/EEex-Core-Shared-Files/source/EEex.cpp#L4604-L4632)
  returns immediately when the recipient has no screening effects. A globally
  named Lua function does not create a global hook. Reader-only screening cannot
  cover arbitrary other targets.
- Native opcode146 mode1 ignores its explicit level parameter and queues a
  `CMessageFireSpell`; it is not synchronous simply because it is called
  instant. Opcode148 modes1 and2 both call `FireSpellPoint` and both ignore
  that parameter. Mode146/2 instead takes the explicit-level `CGameEffect`
  path. Do not change modes to obtain a level override. The two existing
  [pre-message hooks](https://github.com/Bubb13/EEex/blob/a6d21abe44e20509f5d0259ccc6c7e7f9d12b285/EEex/copy/EEex_scripts/EEex_Opcode_Patch.lua#L108-L146)
  handle queued mode0; they do not expose 146/1's separate message. These
  distinctions supersede the initial shared assumptions about instant modes.
- Some effects independently query class level. Vanilla Mirror Image's image
  count is a documented UAI case; setting the scroll's dispatch level alone is
  not proof of complete scaling. See [opcode119 and opcode146](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op119).
- A nonzero level or `CDIA`/`CDID` name does not identify a genuine special fixed
  scroll. SCS generates ordinary IWD scrolls with those prefixes. The old
  reference installation's fourteen CL10 survivors are not a universal exception
  list. Classify installed item/spell behavior and explicit provider exceptions,
  without depending on English names, record order, or one installation's count.

## Bounded hook proposal

The required capability is an **effect-aware level override before the engine
selects a spell ability**, covering each native mode0/1/2 path. Its context
must include dispatcher, cast mode, spell, native selected level, original
scroll/ability, reader, engine-resolved caster and destination. Return only an
optional replacement level; preserve mode, reflection, targets, charges and all
other fields. Carry context per cast, not in one mutable global, so queued and
reentrant casts cannot borrow another reader's level.

A global CheckAdd listener before the current empty-recipient-list return would
solve the recipient-screening gap. It would **not** solve mode1 selection or
linked attribution. The follow-up investigation now identifies the actual
message/action copy boundaries, seven native selection paths (including EEex's
mode-0 special-bit actions), and SPL/177 child propagation points. It also
proves that reflection rewrites source IDs, requiring separately retained
original-reader identity. Establish the complete scoped ownership lifetime and
bounded, cycle-safe wrapper tracking at those boundaries. Preserve shared
SPL/EFF resources or clone/retarget private variants; do not globally rewrite
spell levels or every caster-level query.

This remains an engine-hook implementation proposal, not an implemented hook or
a request to install a partial runtime. Keep the replacement out of default
selection until these paths are established. No CEBG recipe was edited.

## Required acceptance before replacing 430

Use source/disassembly and focused synthetic callback/resource tests first:
direct/self/point casts; modes0/1/2; queued/reflected/reentrant casts; linked
SPL/EFF paths and cycles; multiple/reordered dispatchers; genuine fixed-level
exceptions; ordinary scrolls with and without CDTweaks2170; SR/non-SR; all class
families above, dormant/reactivated dual classes and legitimate non-thief kits.
Assert unrelated effects, learning, non-scroll casting and item fields remain
unchanged. An unsupported path must identify its affected resource/capability;
it must not silently fall back to CL15 or claim universal support.

After separate authorization, a short native check must demonstrate low/high
ability-header selection, charge use, self/creature/point targeting, save/load,
and independent scaling such as Mirror Image. Mocked caster queries alone cannot
establish that native engine boundary.
