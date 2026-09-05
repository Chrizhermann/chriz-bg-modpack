# chriz-bg-modpack

`chriz-bg-modpack` is a small WeiDU collection of first-party NPC, spell, and
compatibility fixes for Baldur's Gate II: Enhanced Edition and EET.

**Release:** `v0.2.0-alpha.3`

This is a public alpha. Its installer and focused behavior are tested against
generated fixtures and synthetic BG2EE/EET-shaped games. Component 610 also passed
startup, load/save and scribing checks in a disposable EET install. A complete
live-game acceptance pass across all components has not yet been performed.

## Installation

1. Close the game and any mod manager using the game directory.
2. Extract the release ZIP into the game directory that contains `chitin.key`.
3. Run `setup-chriz-bg-modpack.exe` and select only components whose upstream
   content is installed.

Install this mod after the NPC, kit, spell, and tactical mods whose resources it
patches. Each component validates its expected resources and source shape before
writing; missing prerequisites are reported by the installer.

## Public alpha components

| ID | Label | Purpose |
|---:|---|---|
| 110 | `cbm_fade_ft_fix` | Complete Fade's Fighter/Thief conversion, authored build, and amulet usability |
| 130 | `cbm_kivan_quest_fix` | Protect the BG1NPC Kivan sea-elf dialogue phase from SCS combat AI |
| 140 | `cbm_mazzy_prof_fix` | Move Mazzy's illegal fifth Short Bow pip to Short Sword |
| 160 | `cbm_skie_skill_fix` | After a Swashbuckler conversion, move unusable Move Silently points to Open Locks |
| 170 | `cbm_xan_ek_fix` | Extend Artisan's Eldritch Knight conversion to EET Xan resources |
| 190 | `cbm_sarah_archer` | Optionally convert Sarah to Archer with the selected proficiency build |
| 192 | `cbm_viconia_cleric_thief` | Permanently convert Viconia to a true-class Cleric/Thief |
| 193 | `cbm_sharteel_wizard_slayer` | Give joinable Shar-Teel variants the Wizard Slayer kit |
| 194 | `cbm_kagain_dwarven_defender` | Give Kagain the Dwarven Defender kit |
| 195 | `cbm_skie_swashbuckler` | Atomically give Skie the Swashbuckler kit and compatible thief skills |
| 196 | `cbm_faldorn_avenger` | Give Faldorn the Avenger kit |
| 197 | `cbm_dynaheir_haste` | Add the effective installed Haste spell to Dynaheir once |
| 198 | `cbm_kivan_archer` | Give joinable Kivan variants the Archer kit |
| 400 | `cbm_branwen_hammer_fix` | Correct Spiritual Hammer's Create Weapon quantity |
| 410 | `cbm_yeslick_keldorn_dispel_fix` | Make Yeslick/Keldorn dispels hostile-only and correctly scaled |
| 430 | `cbm_uai_caster_level` | Give non-caster Use Any Item scroll use a fair fixed caster level |
| 440 | `cbm_ascension_slayer_eefp_fix` | Repair Ascension/EE Fixpack upgraded-Slayer subspell links |
| 450 | `cbm_scs_shapechange_eefp_fix` | Repair the SCS/EE Fixpack arcane shapechange interaction |
| 610 | `cbm_utility_xp` | Scale lock, trap and spell-learning XP with party progression; requires EEex |

Components `191`, `199`, and `600` are reserved or deferred and are not exposed
by this release. There are no placeholder components that fail at install time.

## Collection choices

A normal Sarah installation remains unchanged unless component `190` is selected.
The collection recommends `190` by default, but it is optional. It converts both
Sarah ToB v8 CREs to Archer and assigns exactly:

- Long Bow: 3
- Long Sword: 1
- Short Bow: 2
- Two-Handed Weapon Style: 0
- Two-Weapon Style: 2

The owner's custom Sarah portrait preference is maintained separately in private
collection configuration. Component `191` is reserved for that preference, but no
portrait component or portrait artwork is included in this public repository or
release.

The collection also recommends components `192` through `198` where their NPCs and
prerequisites are present. Garrick needs no component here: the collection selects
Artisan's Kitpack component `99001` directly.

## Dependencies and ordering

- Install Fade before `110`, the BG1NPC Kivan quest before `130`, and Sarah ToB v8
  before `190`. Install `130` after SCS and `190` after other kit/proficiency edits.
- `160`, `170`, and `192`-`198` target EET resources. Component `160` requires Skie
  to already be a Swashbuckler; `195` performs that conversion and applies the skill
  correction atomically.
- `170` requires Artisan's Kitpack component `20000` and Artisan's NPC component
  `20002` to be installed first.
- When the collection uses Artisan's Kitpack with `194`, install Artisan's corrected
  `v1.3.1` release before this component so the Dwarven Defender Shield Bash grant is
  present.
- Install `400`, `410`, and `430` after the spell/item systems they refine. In
  particular, `430` belongs after the relevant Use Any Item scroll-caster-level
  changes.
- Install `440` after Ascension's Improved Slayer Transformation and EE Fixpack.
  Install `450` after the SCS shapechange-spell tweak and EE Fixpack.
- Install `610` after EEex, EET finalization and other utility-XP tweaks, then
  launch through `InfinityLoader.exe`. It uses the protagonist's total XP plus
  the retired class's level threshold for dual classes, giving all thieves and
  spell learners the same progression scale. Scribing reaches native BG2 rates
  at 440,000 progression XP, including low-level spells learned by new companions.
  Rewards round up to 10 XP by default. Edit `override/CBMUXPC.lua` and restart
  to adjust the anchors, multipliers or rounding. See the included
  [utility-XP guide](docs/utility-xp.md) for values, class coverage and limits.

## Testing status

The automated suite covers guarded transformation behavior, malformed-input
rejection, idempotence, public installer paths, and byte-exact uninstall restoration
on generated fixtures and synthetic games. That evidence does not substitute for
live play: recruitment, combat and spell visuals remain to be accepted across the
collection. Component 610's native smoke test covered startup, load/save and one
paused-inventory scribing award; the maintainer confirmed the throwaway test
worked. The final rounding adjustment is covered by automated tests. Live
lock/trap awards and the full class matrix were not exhaustively tested.

## License

First-party source and documentation are licensed under the MIT License; see
`LICENSE`. The bundled WeiDU executable remains under the GNU GPL v2 and ships with
its own `WEIDU-COPYING.txt`. See `THIRD_PARTY_NOTICES.md` for source and checksum
details.
