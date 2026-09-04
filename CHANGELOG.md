# Changelog

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
