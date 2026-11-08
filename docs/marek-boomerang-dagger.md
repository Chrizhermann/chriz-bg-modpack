# Marek carries the Boomerang Dagger +2

Alpha.16 input-handling changes are described in [the overwrite review](we-overwrite.md).
Dated checks below describe earlier builds and do not establish live acceptance
for this revision.

Component **670**, label `cbm_marek_boomerang_dagger`, is an optional change
for the BG1 campaign. It supports BG:EE (with SoD) and EET and needs Marek's
creature files `MAREK.CRE` and `MAREK1.CRE` and the dagger `DAGG11.ITM`. EEex
and SCS are not required.

## Why

The Boomerang Dagger +2 (`DAGG11`) is a BG2 item. In BG1 and SoD it has only
one source: BG1 NPC Project's Kivan quest, whose reward at Shipwreck's Coast
includes it. Without that quest, BG1 has no Boomerang Dagger at all.

## What the component changes

Marek is the Iron Throne assassin who poisons the party in chapter 5. The game
has two creature files for him, and both now carry one Boomerang Dagger +2 in
the backpack:

- `MAREK.CRE`: the first meeting, when Marek and Lothander accost the party in
  the north-east district of Baldur's Gate.
- `MAREK1.CRE`: the antidote fight at the Blushing Mermaid (upper floor) in
  Lothander's side quest. The game creates this Marek only when Lothander hands
  over his half of the antidote; if Marek dies at the first meeting, or the
  party turns Lothander down, he never appears.

So only one Marek can die, and he drops the dagger. It is unidentified, not
equipped and droppable. He keeps fighting with his bow, spells and the Heart
of the Golem +2, which stays in his hand.

Only the two creature files change: one item is added to each file's first
free backpack slot. Their other items, scripts, spells and effects keep their
values, including those other mods such as SCS added. The dagger is an
ordinary inventory entry, so mods that read or swap creature items, such as
the Item Randomiser, see it like his other items.

## One dagger per target

Selecting 670 writes one unidentified, droppable dagger to each present Marek
file, even when another quest also offers it. Existing copies are normalized to
one entry. A full backpack uses an available quick-item or spare weapon slot.
The all-slots-occupied case remains an unresolved placement decision; see the
[overwrite review](we-overwrite.md).

## Installation and compatibility

Install after mods that change Marek's creature files, such as SCS, and before
mods that read creature items, such as the Item Randomiser. A mod installed
later that replaces a Marek file removes the dagger again; one that only adds
to it keeps it. Uninstalling restores the previous files byte for byte.

The dagger reaches every game in which that Marek has not yet appeared: the
game reads `MAREK.CRE` when the party first enters the north-east district and
`MAREK1.CRE` when it creates him at the Blushing Mermaid.

- Without one of the two files, the other still gets the dagger, and the
  installer names the missing one.
- Without both files (for example BG2:EE alone) or without `DAGG11.ITM`, the
  component is skipped.
- A damaged item table or slot index costs only the affected creature, with a
  log line. Other present Marek files are still patched. The area and quest
  scripts are not inspected to decide whether to place the dagger.

Letting Marek throw the dagger is left for later.

## Testing status

Synthetic WeiDU tests cover BG:EE resources in BIFF archives and EET resources
in override; vanilla and SCS-shaped Marek files (more items, a gap in the
backpack, other scripts, version 2 effects, other block orders); with and
without the Kivan quest's Shipwreck's Coast block, also with SCS-shaped files,
with Windows line endings and with a differently named area script; a BG1 NPC
Project `WeiDU.log` line without the block and dagger mentions that give
nothing; one file already carrying the dagger; one file missing; the skip and
abort cases; reinstalling and byte-exact uninstalling.

The installer also ran on copies of the original BG:EE files (dagger added to
both), of BG:EE files with BG1 NPC Project (no change) and of an EET game's
files with SCS and BG1 NPC Project (no change; with the Shipwreck's Coast
script left out, the dagger was added to both SCS-changed files).

Not tested in a game: the two fights and the drop.
