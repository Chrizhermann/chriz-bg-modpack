# Baeloth: standard sorcerer spells known

**Component 235** — `cbm_baeloth_spellbook` — **major rebalance, unreleased**.

This independent option reduces Baeloth's unusually large starting spellbook to
the installed Sorcerer spells-known allowance. It is intended for the collection's
planned **Challenge Mode**, not an unconditional collection default. Selecting
it does not require any other companion conversion, stat adjustment or rebalance.

## Starting selections

| Recruitment template | Existing known spells, levels 1 / 2 / 3 | Normalized selection |
|---|---|---|
| `BAELOTH`, stored character level 6 | 7 / 5 / 4 | **4 / 2 / 1** |
| `BAELOT7`, stored character level 7 | 8 / 6 / 5 | **5 / 3 / 2** |

At level six, with or without Spell Revisions:

| Spell level | Known spells in priority order |
|---|---|
| 1 | Magic Missile, Shield, Spook, Chromatic Orb |
| 2 | Mirror Image, Web |
| 3 | Fireball |

The fresh level-seven recruitment template additionally knows:

| Spell level | Without Spell Revisions | With Spell Revisions |
|---|---|---|
| 1 | Blindness | Identify |
| 2 | Melf's Acid Arrow | Melf's Acid Arrow |
| 3 | Haste | Haste |

The installer resolves the current `SPELL.IDS` identities and validates each
selected SPL's actual wizard type and level. It does not treat a vanilla resource
number as a spell's identity. In the inspected SR installation, `SPWI106` is
Obscuring Mist although `WIZARD_BLINDNESS` still points at it. SR's installation
markers/component select the Identify branch instead. Hidden or removed choices
are rejected when the installed `HIDESPL.2DA` marks them as such.

Limits come from the **stored CRE level's row in installed `SPLSRCKN.2DA`**,
not from a hardcoded allowance or the creature's XP. With altered levels/tables,
the agreed priority lists are capped at that allowance. Additional capacity
beyond the authored five/three/two selections stays unfilled; the component does
not invent higher-level selections. A missing rule row or an incompatible moved
spell gets a specific diagnostic rather than silently substituting another build.

## Exact scope

Both named templates are used unchanged in BG:EE/SoD and EET. BG1 recruits
`BAELOTH`; a **fresh** SoD recruit uses `BAELOT7`. A carried or rejoined actor keeps
his existing spellbook. Black Pits resources such as `BPBAELOT` and `OHBBAEL`,
debug duplicates and merely similar names are outside the target list.

Each present template is patched independently. Missing variants are logged with
a warning that other/renamed variants may remain unpatched. If neither exists,
the component reports no changes and does not load unused class or spell rules.
An actual non-Sorcerer conversion is rejected: this option owns the Sorcerer book,
not class or kit. Different HP, XP or valid stored levels are not incompatibility
fingerprints.

Rejected wizard spells are removed from **both known spells and their castable
memorized records**. Keeping the latter could leave rejected spells available.
Every memorization group's base/maximum daily-slot fields remains byte-identical,
including original `BAELOTH`'s unusual empty fourth-level group with 0/3 slots.
Selected spells retain their raw prepared/spent records; no rest or recharge is
performed. The normal original CREs already contain all selected spells, leaving
37 memorized wizard copies at level six and 56 at level seven.

If another mod removed a selected spell's prepared records, replacement copies
use the smallest original per-spell copy count, capped by the group's existing
maximum, and the smallest ready count. Empty or missing groups gain no casts.
This conservative fallback does not refresh a spent pool. Duplicate known-spell
entries are normalized without deleting nonwizard/innate entries.

No stats, level, XP, kit, equipment, effects, racial traits, innate abilities,
priest spells, dialogue or scripts are changed. No spell/progression table is
edited. In particular, this component does not change component 430 or scroll
caster levels.

## Installation order and future progression

Install **after NPC and spell-system mods, EET finalization when applicable, and
all NPC spellbook writers, including Spell Revisions component 60 if selected**.
SR 60 remains optional. Its inspected arcane pass removes unsuitable spells;
there is no evidence that it caused Baeloth's original excessive allocation.
The late placement ensures this chosen starting book is the final authored one.

The inspected recruitment, personal, dialogue, camp and transition paths contain
no ordinary spellbook grants needing a script patch. SoD catch-up changes XP,
leaving normal level-up selections to the player. There is no recurring
normalizer, rest hook or rejoin reset. The fresh level-seven template's authored
choices do not override choices made by a player leveling a carried level-six
Baeloth.

This edits **recruitment resources only**. Existing actors/saves are not repaired.
No running installation or save is part of this work. Use normal WeiDU uninstall
to restore the original resource bytes.

## Collection integration and validation

Keep 235 independently selectable within the planned Challenge Mode and identify
it as a major companion rebalance. Do not make it mandatory, couple it to other
NPC options, or select it unconditionally. A future approved release containing
235 must be pinned before exposing the collection choice: the published alpha.8
archive does not contain it.

Validation on October 4, 2026, using WeiDU 249:

- **35 focused tests passed**, covering SR/non-SR identities, both recruitment
  levels, installed allowances, partial targets, duplicate/missing entries,
  reordered and empty resource blocks, preserved daily limits/readiness and
  unrelated fields, repeat application, rollback and exact uninstall.
- **Four real-resource transformations passed** in two disposable fixtures,
  using copies from non-SR SoD and Combined SR EET. Both recruitment templates
  produced the selected books, preserved every daily-slot header and retained
  memorized record, and left unrelated data unchanged. Both uninstalls restored
  the entire fixture resource tree byte for byte.
- The inspected CREs are unkit Sorcerers. Their available carried-item and linked
  spell/effect resources contain no ordinary spellbook grant. Four absent
  Combined proficiency subspells (`C0PR#111` through `C0PR#114`) could not be
  inspected; this is a bounded audit of available resources.
- Installer/library parse checks and the ten public-surface/release-builder
  tests passed.

Recruitment/level-up/rejoin checks verify resource and script invariants; they
do not establish native gameplay acceptance. No full collection installation,
running-game change or save repair was performed.
