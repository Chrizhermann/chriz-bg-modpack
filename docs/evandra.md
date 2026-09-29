# Evandra: class and portrait choices

These two components restore preferences from Chriz's original collection.
They are included from **v0.2.0-alpha.8** onward.
Both require Evandra to be installed first, on BG2:EE or EET. Neither requires
EEex. They are independent: retain the original class or portrait by deselecting
the corresponding option.

## 224: Sorcerer

Convert the SoA and ToB recruitment templates (`rh#eva` and `rh#ev25`) to an
unkitted Sorcerer. Preserve their stored levels and XP: the original SoA template
is level 10 / 300,000 XP, and the ToB template is level 14 / 2,500,000 XP.
Do not pre-level them to match XP; the player should choose additional spells
through the game's level-up screen. The special vampire template is not class
converted. Portrait selection is component 225, not part of this conversion.

The normal level-10 starting spellbook with Spell Revisions is:

| Spell level | Known spells |
|---|---|
| 1 | Magic Missile, Dimension Jump, Shield, Identify, Spook |
| 2 | Mirror Image, Invisibility, Detect Invisibility, Glitterdust |
| 3 | Slow, Spell Thrust, Fireball |
| 4 | Improved Invisibility, Stoneskin |
| 5 | Breach |

Without Spell Revisions, Color Spray replaces Dimension Jump. At higher levels,
the authored list also includes Blur, Haste, Spirit Armor, Vitriolic Sphere,
Spell Shield, Summon Shadow, Mislead, Protection from Magical Weapons, and
Project Image. Without SR, Greater Malison replaces Vitriolic Sphere and Animate
Dead replaces Summon Shadow. Spell resources are resolved from the installed
spell symbols, not assumed from one game's resource numbers.

Known-spell limits and casts follow installed Sorcerer tables at the stored
level. The authored list extends through the original ToB level-14 starting
book. If an earlier mod supplies a higher level or extra known-spell capacity,
the component does not invent additional high-level choices; capacity beyond
the authored list stays unfilled. Earlier mods' higher XP or different HP are
not compatibility errors.
Unrelated identity, dialogue, quest scripts, equipment, effects and personal
abilities must remain intact. Install after Evandra and spell-system changes;
do not combine with another Evandra class/respec option.

This patches recruitment templates, **not characters already created in a
save**. It is not an automatic saved-character repair. Back up before manually
editing a save, and avoid awarding the same level-ups twice.

## 225: Chriz's custom portrait

Install the owner-created image as `rh#evaL.bmp`, the standard EE portrait
resource. Set both portrait fields on Evandra's SoA/ToB templates and her vampire
variant, if present, to this image; do not alter the messenger or other NPCs.
The existing epilogue uses the same resource name. Uninstall restores the prior
image and creature portrait references through WeiDU's backups.

Saved actors already pointing at `rh#evaL` pick up the replacement image after
reload/restart; other custom saved portrait names are not edited. The load-game
screen may retain its old thumbnail until the next save. No dialogue strings
or save data are changed by this component.

Christopher created the image with ChatGPT and approved distribution on
September 29, 2026; see `THIRD_PARTY_NOTICES.md` for its exact hash. The original
Evandra mod and its artwork are not bundled.

## Delivery status

Automated fixture checks and release packaging are distinct from a full live
install/playtest. CEBG must pin a release actually containing 224 and 225, make
them default only when Evandra's core is selected, and skip both when Evandra
is skipped. Do not append these IDs to the old alpha.7 archive's catalogue.
