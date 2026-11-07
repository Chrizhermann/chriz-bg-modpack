# Unreleased overwrite update

Selecting a component makes its documented output authoritative for the fields
and behavior it owns. Old values, wording, extra effects, missing owned effects,
component log versions and replacement counts do not approve or veto that output.
A missing optional target or a file whose structure cannot be addressed costs
that file only, with an ordinary log line. Real engine features and native memory
signatures remain requirements. Component numbers, defaults and release version
remain unchanged.

## Ownership and fallback data

NPC conversions write their named class/kit, complete proficiency allocations and
other documented fields. Stats-only options write only their named scores.
Unrelated effects, identity and inventory remain outside those conversions.
Indexed resource readers follow the header pointers and counts; independently
indexed blocks need not occupy a particular physical order.

Progressions are read by row and column label. Bundled stock EE 2.7.3 tables fill
missing labels and numeric cells; existing usable cells supply calculations.
Standard IDS symbols have stock fallbacks. Custom kits still need their actual
implementation. No missing label is interpreted as a reason to refuse a build.

Spell fixes rebuild their owned effects and retain unrelated indexed effects.
Yeslick's dispel has forty authored thresholds; Keldorn retains his installed
scaling and gets the hostile-only projectile. Script fixes replace their owned
blocks, adding them when absent. Recruitment XP selections take over recognized
competing XP writes while preserving other story actions. Degrodel's missing
hand-in is supplied by an owned dialogue path.

The bundled descriptions contain the complete English output of the previous
patches on their intended installed resources, including item descriptions.
They do not depend on incoming text. Other game languages retain their current
text with a log line until translations are supplied. Neutral artwork for missing
630 donors and baseline progression/XP tables are bundled fallback data.

## Expected byte differences

Canonical spell blocks can have new indexes, offsets and packing; unused gaps
are not retained. Unrelated indexed effects and trailing data are retained.
Owned script and dialogue blocks can be decompiled and recompiled. Equivalent existing blocks
can therefore change serialization, and competing XP providers are intentionally
replaced. Full English descriptions can add TLK entries even when visible wording
is unchanged; WeiDU uninstall preserves the original strings but may leave new
unused strings. Private XP tables, fallback artwork and helper scripts are new
payload files. The 430 native DLL and policy builder were rebuilt after removing
resource fingerprints and the 64-link ancestry limit. 650's native hooks, DLLs,
memory signatures and callback return paths are unchanged. Its threshold reader
now uses bundled stock XP data for missing installed cells. Its error handler
must never return zero to the game.

## Remaining review and coverage limits

- A Marek with every backpack, quick-item and spare weapon slot occupied needs a
  placement decision. WeiDU's ADD_CRE_ITEM can displace an existing item when no
  listed slot is empty. The closest current result places the dagger; preserving
  every displaced item requires a separate behavior decision. See the
  [WeiDU ADD_CRE_ITEM reference](https://weidu.org/~thebigg/beta/README-WeiDU.html#ADD_CRE_ITEM).
- Extremely large effect lists replicated across forty dispel abilities can
  exceed the SPL format's 16-bit effect indexes. Splitting unrelated effects into
  helper resources would need an ownership decision; that case is not covered.
- Continuity identity collisions and hand-edited, unrecognizable death variables
  need review. The current implementation retains known identity mappings; it
  does not invent an identity for an unknown actor.
- 430 now isolates invalid saved metadata to its actor. Unknown extra Lua fields
  do not prevent reading a supported payload. An unloaded original reader keeps
  that cast at its native level and can bind later. These changed paths have no
  native-game acceptance yet; pointer/lifetime and hook checks remain in place.

- 650 still needs reconciliation rules for contradictory class flags, invalid
  campaign/chapter progress and inconsistent saved XP ownership or balances.
  Those checks are recorded as open, not classified as native-signature checks.
  The existing actor-local native fallback and saved evidence remain intact.

- Damaged-resource fixtures exercise headers, bounds and selected script framing.
  Arbitrarily corrupted BCS/DLG interiors and every possible custom runtime XP
  writer have not been covered. This is not a claim about all mod setups.

Current commands and final counts are recorded in the uncommitted
`WE-OVERWRITE-LEDGER.md`. No game, lab, saved character, full collection install,
release, tag or version update is part of this work. Historical playtest results
in component guides apply to those earlier packages only.
