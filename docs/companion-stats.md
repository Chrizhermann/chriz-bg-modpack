# Optional companion stat improvements

**Components 230-234** — optional, added in alpha.12.

These five independent components raise the base ability scores of companions
that are otherwise weak. Select any combination; none requires a class, kit,
spell mod, or another stat component. Collection selection is decided separately.

| ID | Label | Companion | Assigned base scores |
|---:|---|---|---|
| 230 | `cbm_rasaad_stats` | Rasaad | Dexterity 17, Constitution 16 |
| 231 | `cbm_dorn_stats` | Dorn | Constitution 16 |
| 232 | `cbm_eldoth_stats` | Eldoth | Strength 17, Intelligence 14, Wisdom 9, Constitution 16 |
| 233 | `cbm_garrick_stats` | Garrick | Dexterity 17, Intelligence 15 |
| 234 | `cbm_quayle_stats` | Quayle | Constitution 15 |

Selecting a component makes these scores authoritative, regardless of the incoming
scores, class, kit, level, XP, or current HP. Eldoth's exceptional-strength byte is
also cleared because his assigned Strength is 17. All other bytes are preserved,
including other scores, HP, class/kit, equipment, proficiencies, spellbooks, daily
casts, effects and racial/kit abilities. The implementation uses the declared
[CRE V1.0 ability fields](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/cre_v1.htm).

## Creature coverage

The explicit list covers 35 named resources across BG:EE, SoD, BG2:EE and EET.
Patch every listed file that exists, whether it is in `override` or only in the
game's BIFF archives. Log each missing file and warn that other or renamed
variants may remain unpatched. If none exists, report that no resources changed.
Missing campaign variants never block the files present; malformed CRE headers
do fail with the affected filename and roll back the component.

| Companion | BG1 recruitment | Later campaigns and other appearances |
|---|---|---|
| Rasaad | `RASAAD`, `RASAAD2`, `RASAAD4`, `RASAAD6` | SoD `RASAAD7`; BG2 `RASAAD8`, `RASAAD9`, `RASAAD10`, `RASAAD11`, `RASAAD13`; ToB `RASAAD12` |
| Dorn | `DORN`, `DORN2`, `DORN4`, `DORN6` | SoD `DORN7`; BG2 `DORN8`, `DORN9`, `DORN10`, `DORN12`; ToB `DORN14` |
| Eldoth | `ELDOTH`, `ELDOTH5` | Dormant alternate-story Eldoth `ELDOTD`, included for complete named-character coverage |
| Garrick | `GARRIC`, `GARRIC2`, `GARRIC4`, `GARRIC6` | SoD cameo `BDGARRIC`; BG2 cameo `GARRICK` |
| Quayle | `QUAYLE`, `QUAYLE4`, `QUAYLE6`; EET imports BG1 `QUAYLE` as `QUAYLE_` | BG2 normal `QUAYLE` and transformed circus Quayle `QUAYLEM` |

Resource suffixes are not assumed to equal creature levels. EET's `RASAAD_`,
`DORN_` and `GARRICK_` remappings are scripts/dialogues, not additional CRE files.
`OHB1RASD` and `OHB2DORN` are separate Black Pits II arena enemies and are outside
these companion improvements. A name scan of two EET installations found no
other creature with one of these five names.

## Ordering and class/kit compatibility

Install after companion content, EET's BG1 import, and other stat/class/kit
conversions, before the companion first appears. In a split collection install,
place these with the companion changes before continuity component 199/EET_end.
A later mod that writes these scores or replaces a CRE can overwrite this choice.
There is no runtime enforcement that would cancel ordinary buffs or progression.

The inspected Artisan Sacred Fist conversion for Rasaad preserves ability scores;
Garrick's Troubadour conversion changes only his kit field; Dorn's Blackguard pass
preserves Constitution. Rasaad's Monk Revision AC adjustment does not rewrite his
Dexterity. None of the inspected companion resources carries an embedded effect
that sets these scores. These findings support compatibility with the
collection's current choices, not every possible future conversion.

Spell Revisions and other spell overhauls are not relevant: these components do
not read or change spells. The result is the same with or without them.

Stored HP is intentionally unchanged. Setting Constitution does not by itself
establish that existing-level HP has been recalculated; normal future progression
uses the resulting character build. No saved actor is repaired. Existing saves
can already contain actors created from the old defaults, including actors reused
by EET continuity; modifying those requires separate approval.

## Validation

Validation on October 14, 2026, using WeiDU 249:

- Focused tests use disposable synthetic games. They check every listed
  resource, each component alone and all five in one run, arbitrary incoming
  builds, override and BIFF-only variants, partial and missing families, repeat
  application, malformed-header rollback, and byte-exact uninstall restoration
  of the override folder. They do not require a full collection installation.
- An extracted-release check installs and removes each component, and all five
  together, using only the built archive.
- Separate disposable installs used copies of the effective creature files from
  two read-only EET installations: 35 companion files each, plus the two arena
  lookalikes. The same bytes were also arranged under BG:EE/SoD and BG2:EE file
  names. Every component alone and all five together changed only the selected
  scores in the selected families. Each uninstall restored the copies byte for
  byte.

Live recruitment, level-up and save/reload acceptance is not claimed; no running
game or save is modified.
