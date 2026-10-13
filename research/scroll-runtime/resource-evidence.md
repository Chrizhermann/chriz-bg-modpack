# Installed resource classification and native helper preservation

October 9, 2026. The read-only parser now feeds the real component430 policy builder and
native item-use boundary. No ITM/SPL/EFF resource is changed. Effective installed bytes
are hashed in the policy and reverified through EEex Demand at startup.

Declared offsets/counts/indexes govern ITM V1, SPL V1, and linked EFF V2 traversal,
including reordered/padded blocks. The graph follows 146/148 modes0/1/2, 177, 232,
272, and 326 through globals and every ability. Native repeating edges are recorded
and each resource expanded once; later branches remain checked. Depth/node budgets,
unknown types, invalid bounds, and missing resources still produce concrete diagnostics.
Unrelated effect fields may contain binary data and are not decoded as resource names.
Vanilla SPLESEAR.EFF has zero embedded version bytes8-15; only the external signature
bytes0-7 is required. See [current status](component430-status.md) for the final inventory.

Manual learning (147) is reported per ability. A mixed learning/casting ability
is unresolved for runtime attribution; it is never silently enabled. Non-scroll
items, non-use abilities and unrelated direct effects receive no reader policy.
Installed SPL type1 is arcane, type2 divine, and resolved types0/3/4/5 retain
native behavior. Neither SPWI/SPPR resource names nor parameter1 supplies type.

Actual read-only samples come from:

- `%USERPROFILE%/CEBG-Tests/Combined-20260908/game` (SR collection).
- `<BG2EE 2.6.6.0 install>`
  (non-SR sample; this directory still contains other modifications).

Both samples cover ordinary SCRL67/SCRL75/SCRL7C, their separate learning
abilities, and protection scrolls SCRL03–09/SCRL15. Each input ITM is rehashed
after analysis. Combined SCRL67/75/7C already have casting parameter1=15, proving
that nonzero levels do not mark exceptions. Combined SCRL7C references installed
arcane SPWI521 and its type4 DW#BLHDA child; non-SR SPWI521 has linked
SPLESEAR.EFF. Both layouts classify successfully without changing records.

## Explicit special-scroll exceptions

The known native protection-scroll family is explicit: SCRL03 acid,04 cold,
05 electricity,06 fire,07 magic,08 poison,09 undead,15 petrification. It requires
an appropriate protection mechanic anywhere in the ability's linked graph and
no learning behavior. Semantic anchors are resistance27–30, spell-level
immunity102, poison protection101/173, creature protection100, and petrification
immunity101. No effect count, ordering, magnitude, English string, level or
filename prefix is required. If a known family lacks its mechanic, the report
requests provider review rather than overriding an ambiguous replacement.

These are native protection items, not ordinary learnable mage spells:

- SR's `spell_rev/components/main_component.tpa:3454` identifies the native
  protection resources, including separate SCRL73 mage petrification and SCRL15
  protection scrolls. Current source lives in the separate `chriz-spell-revisions-patch` repository.
- Installed SCS `stratagems/tactical_bg2/undeadscroll.tpa:1–27` explicitly changes
  SCRL09's creature-protection100 into a cast of DW#PROUN so selected undead can
  resist that special scroll. The classifier follows the spell to the mechanic.
- Installed SCS `stratagems/spell/spellstrike_vs_pm_scroll.tpa:9–31` moves SCRL07's
  effects into DW#PMSCR and dispatches it. This source-proven alternate graph
  keeps the same special-scroll policy even if a provider changes SPL type.

The exceptions are narrow, not a claim to identify all future mod-authored fixed
scrolls. Structurally identical typed scrolls cannot reveal author intent from
the bytes alone. Other typed casts are explicitly `typed_cast_candidate`, not a
claim that every author exception has been audited. Ordinary CDIA/CDID IWD
scrolls receive no prefix-based exception.

## Runtime helper behavior

`SpellType::PreserveNative` is now an explicit successful selection outcome.
It returns no scalar override and does not reuse a parent's applied level.
Its child effects retain the immutable scroll/reader origin, so a later typed
child can independently apply the reader's relevant active level. An unrelated
nested cast still gets an unowned frame. Unknown/unresolved types remain errors.

The native provider verifies the actual CSpell type before preserving it. Native
GetCasterType returns0 both for a genuine type0 header and for absent/empty
resources; therefore type0 also requires a nonempty actual CSpell resref and a
present V1 SPL header whose installed type is0. Both native binaries read
`CSpell.pRes`, `CResSpell.pHeader` at+0x68, and header type+0x1C at these proven
instructions: `reader-native-2.6.txt:827–850` / `reader-native-2.7.txt:461–484`.
The existing caller contract requires valid live CSpell/resource lifetimes.

Tests cover typed root → native helper → typed child, original reader identity,
unchanged native helper/child levels, repeated selection, and independent nested
casting. The provider harness checks known type4, resolved type0, missing header,
empty resref, malformed signature and type mismatch. This is offline adapter
evidence, not initialized-engine acceptance.

`python -m pytest tests/test_scroll_runtime_resources.py -q`: **30 passed**.
