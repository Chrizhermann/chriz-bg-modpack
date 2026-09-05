# Changelog

## v0.2.0-alpha.5 - 2026-09-06

### Fixed

- Component `170` resolves Xan's source Enchanter kit through the canonical
  `MAGESCHOOL_ENCHANTER` symbol in installed `KIT.IDS`. The Eldritch Knight
  conversion and CRE kit encoding are unchanged.
- Component `192` accepts a stale count on Viconia's final populated priest
  memorization row when the declared ranges form an unambiguous contiguous
  prefix. It corrects that row and following empty indices to the actual table
  length, preserving every existing memorized spell and flag. Ambiguous ranges
  still fail; class, skill, proficiency, ability and spell-slot policy is unchanged.
- Authored regressions cover both observed stale-range shapes, invalid metadata,
  canonical kit symbols, install scope and byte-exact uninstall restoration.

## v0.2.0-alpha.4 - 2026-09-05

### Added

- Optional Yoshimo Swashbuckler (`220`), plus mutually exclusive Hexxat
  Shadowdancer (`221`), Fighter/Thief (`222`) and Assassin (`223`) choices.
- Installed-table thief-skill allocation and kit resolution support vanilla kits
  or Artisan revisions. Old class abilities are removed selectively; Hexxat's
  vampire powers, equipment and quest state are preserved, and Clara is untouched.
- Fighter/Thief rebuilds levels, HP, THAC0, saves, lore and proficiencies while
  retaining total XP and recruitment level-up opportunities. Extra Domination
  uses retain their original total-XP milestones.
- The public companion guide and focused installer/package acceptance tests.

### Compatibility and verification

- New choices use `220`-`223` to preserve all existing public component IDs.
  The earlier unpublished `190`-`193` draft numbers must not be used for these
  choices. No existing component was renumbered.
- Install after kit/progression changes and before the companion first appears
  in the saved world. EEex and Artisan's Kitpack are optional for these choices.
- Focused synthetic tests cover BG2EE/EET, altered kit rules, wrong/missing data,
  script scope, option exclusion, rollback and byte-exact uninstall. All four
  options also passed disposable installs against copied pristine and modded
  resources. Live recruitment remains untested; a broad live test pass is not
  a release blocker after source review.

## v0.2.0-alpha.3 - 2026-09-05

### Added

- Component `610`, progressive XP for lockpicking, trap disarming and spell
  learning in BG2EE/EET. It keeps early rewards small and approaches native BG2
  rewards using the protagonist's total XP plus a retired dual class's level
  threshold. Multiclass, triple-class and both dual directions share that scale.
- Scribing reaches 1,000 XP per spell level at 440,000 progression XP, including
  low-level catch-up spells learned by newly recruited mages and bards.
- Editable anchors, category multipliers and rounding in `CBMUXPC.lua`; settings
  apply to existing saves after a restart. Final party awards round up to 10 XP
  by default (the tested 732 XP scribing example becomes 740).
- Lua 5.1/LuaJIT regression tests and real WeiDU synthetic install/uninstall
  checks, plus component 610 acceptance from the extracted release package.

### Compatibility and verification

- Component 610 requires EEex. Install after other utility-XP tweaks and launch
  through InfinityLoader. Native XP sharing and caps remain in force.
- In a disposable EET installation, startup, load/save and an actual scribing
  award passed. The maintainer confirmed the test worked. The later rounding
  adjustment is covered by automated tests; live lock/trap awards and the full
  class matrix were not exhaustively tested.
- The native adapter preserves trailing unnamed XPBONUS padding columns and
  rejects interior gaps before writing. The included `docs/utility-xp.md` explains
  the curve, settings, sources and validation limits.
- Source filenames support Linux WeiDU, and the installer test harness supports
  Windows temporary paths containing `~`. The alpha.2 tag failed the latter
  build check and was not published as a release.

## v0.2.0-alpha.1 - 2026-09-04

First public alpha.

### Added

- NPC and collection fixes: Fade Fighter/Thief (`110`), BG1NPC Kivan quest/SCS
  guard (`130`), Mazzy proficiencies (`140`), Skie thief skills (`160`), and EET
  Xan Eldritch Knight reconciliation (`170`).
- Optional Sarah Archer conversion (`190`) with Long Bow 3, Long Sword 1, Short
  Bow 2, Two-Handed Weapon Style 0, and Two-Weapon Style 2. Omitting it leaves a
  normally installed Sarah unchanged.
- Collection-oriented NPC defaults: permanent Viconia Cleric/Thief (`192`),
  Shar-Teel Wizard Slayer (`193`), Kagain Dwarven Defender (`194`), atomic Skie
  Swashbuckler plus skill correction (`195`), Faldorn Avenger (`196`), Dynaheir
  Haste (`197`), and Kivan Archer (`198`).
- Spell and compatibility fixes: Branwen Spiritual Hammer (`400`), Yeslick and
  Keldorn Dispel Magic (`410`), Use Any Item scroll caster level (`430`),
  Ascension/EE Fixpack Slayer transformation (`440`), and SCS/EE Fixpack
  shapechange (`450`).
- Deterministic, allowlisted release packaging with an official pinned WeiDU
  249.00 AMD64 executable, recorded checksums, license text, and package contents.
- Generated-fixture and synthetic-game coverage for component behavior,
  fail-closed guards, idempotence, installer paths, and uninstall restoration.

### Compatibility and collection notes

- Xan component `170` requires Artisan's Kitpack `20000` and Artisan's NPC
  component `20002` first.
- Garrick remains an external collection selection through Artisan's component
  `99001`; no duplicate component is provided here.
- Kagain component `194` should follow Artisan's Kitpack `v1.3.1` when that mod is
  present, preserving the corrected Dwarven Defender Shield Bash grant.
- Components `440` and `450` are independently expressed compatibility patches
  intended to run after their relevant Ascension, SCS, and EE Fixpack components.

### Not included

- Component `191` and the owner's custom Sarah portrait are private/unavailable
  publicly and are not bundled.
- Components `199` and `600` are reserved or deferred and are absent rather than
  exposed as installer-time failure stubs.
- Live-game acceptance has not yet been performed; this alpha's current evidence
  is automated fixture and synthetic-game testing.
