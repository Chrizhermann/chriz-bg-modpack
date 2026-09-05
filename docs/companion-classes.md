# Yoshimo and Hexxat class options

| Component | Choice |
|---:|---|
| 220 | Yoshimo: Swashbuckler |
| 221 | Hexxat: Shadowdancer |
| 222 | Hexxat: Fighter/Thief multiclass |
| 223 | Hexxat: Assassin |

Yoshimo's option is independent. Hexxat's three options form one optional WeiDU
subcomponent group: choose one, or skip the group to keep her current class.
These components require BG2:EE or EET. They do not require EEex or Artisan's
Kitpack. The kit names refer to the kits currently installed in the game; if
Artisan revises a kit, the companion receives that revision.

## Installation

Install after kit overhauls, XP/HP/proficiency-table changes and companion mods,
and before starting the playthrough. Choose these options instead of another
class conversion or level-one/respec component for the same companion. In
particular, Artisan's Invisible Blade Hexxat option is an alternative to these
three choices. Install before SCS components that generate NPC behavior when
building a fresh installation.

The installer patches creature templates, not saved actors. An existing save
must predate the companion's first creation in the world, which may precede
recruitment. Loading an already recruited companion will not convert them.

For example, run the normal installer and select 220 plus one of 221–223. For
unattended installation, `--force-install-list 220 221` selects Swashbuckler
Yoshimo and Shadowdancer Hexxat. WeiDU can uninstall or replace these components
through its normal component menu.

## Behavior

The exact creature families are `YOSHI7/8/10/11/12` and
`OHHEX8/9/10/11/13/15/25`. Clara's `OHHFAK*` creatures are not changed.
The companions retain their XP, identity, attributes, portraits, inventory,
dialogue and quest scripts. Yoshimo's personal katana has only its Swashbuckler
usability restriction cleared.

Kit choices keep the existing class levels. The installer resolves kit IDs
from `KIT.IDS`; it does not assume kit-list row numbers or an Artisan install.
It redistributes thief skills using the installed `THIEFSKL.2DA` starting and
per-level points, and the skills enabled by `THIEFSCL.2DA`. Existing allocations
provide the relative weights; disabled skills receive zero. Integer remainders
are distributed deterministically, and no raw skill exceeds 255.

Hexxat retains the embedded human base-skill compensation used by the original
game (45 points across the five applicable skills); disabled skills do not keep
that compensation. Yoshimo's new allocation removes the Bounty Hunter's baked
15-point trap bonus. This also handles Artisan's smaller Swashbuckler/Assassin
budgets and its disabled skills.

Old class/kit CLAB grants are removed from known and memorized spell lists.
Permanent effects with an explicit old CLAB parent spell are removed separately.
Unrelated effects and personal innates, including Hexxat's vampire abilities,
are preserved. The EE recruitment machinery supplies the new kit's CLAB
abilities; the installer does not add duplicate passive effects to the CRE.

Fighter/Thief additionally rebuilds both class levels, THAC0, saving throws,
lore, hit points and proficiencies from the installed progression tables:

- Total XP stays intact and is split only for level calculations. If a creature
  intentionally carries XP above its current thief level, conversion uses at
  most the XP immediately below its next level. This preserves the recruitment
  level-up opportunity in the underleveled ToB template `OHHEX25`.
- THAC0, saves and lore retain the original creature's adjustment relative to
  its old class progression. Hit points preserve its original roll quality by
  scaling current/max HP against expected old and new class HP, including
  installed hit-point-table changes.
- Legal existing weapon proficiencies are retained. Additional warrior points
  go to long sword, dagger, single-weapon style, club and two-weapon style within
  the installed Fighter/Thief caps. The budget is `FIRST_LEVEL + level / RATE`
  with integer division (six points at Fighter 6 with vanilla tables). Class and
  kit table files are not modified.
- Only the two `ohh_dom` progression conditions in each of `HEXXAT.BCS` and
  `HEXXA25.BCS` change. They use the total XP needed for thief levels 14 and 24
  from `XPLEVEL.2DA`, preserving the original XP milestones for extra Domination
  uses. Other script conditions remain unchanged.

An unsupported creature class, missing required progression data or an
unrecognized Domination block causes the component to fail and WeiDU to roll
back its changes. These conversions are not a general saved-character respec
system.

## Research and validation

Local checks compared the actual pristine BIF resources with the installed
Artisan/CDTweaks/EET stack, including both Hexxat scripts. The implementation is
original code informed by these primary sources:

- [jmerry's Hexxat class mod](https://forums.beamdog.com/discussion/85238/mod-request-change-hexxats-class-to-shadowdancer-or-fighter-thief): creature coverage, complete Fighter/Thief conversion, vampire skill compensation and Domination progression.
- [NPC_EE 1.2.1](https://github.com/UnearthedArcana/NPC_EE/blob/1.2.1/npc_ee/npc_ee.tp2): Yoshimo creature coverage and personal-katana usability.
- [Argent77's class-conversion library](https://github.com/Argent77/A7-NoEENPCs/blob/master/A7-ConvenientEENPCs/lib/class_functions.tph): installed thief-skill tables and selective innate cleanup.
- [Artisan's Assassin](https://github.com/TheArtisanBG/The-Artisan-s-Kitpack/blob/master/ArtisansKitpack/lib/Assassin.tpa), [Swashbuckler](https://github.com/TheArtisanBG/The-Artisan-s-Kitpack/blob/master/ArtisansKitpack/lib/Swashbuckler.tpa) and [Shadowdancer](https://github.com/TheArtisanBG/The-Artisan-s-Kitpack/blob/master/ArtisansKitpack/lib/Shadowdancer.tpa): optional overhaul behavior.
- [WeiDU 249 effect helpers](https://github.com/WeiDUorg/weidu/blob/v249.00/src/tph/include/cd_functions.tpa) and [IESDP EFF V2](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/eff_v2.htm): parent-spell matching is distinct from an effect's payload resource.
- [GemRB XP triggers](https://github.com/gemrb/gemrb/blob/master/gemrb/core/GameScript/Triggers.cpp) and [level calculations](https://github.com/gemrb/gemrb/blob/master/gemrb/GUIScripts/LUCommon.py): total XP is compared before multiclass division.

Automated tests exercise the public WeiDU components in disposable synthetic
BG2EE and EET games, including reordered kit IDs, altered kit rules, preserved
vampire state, script scope, rollback and byte-exact uninstall. Eight additional
disposable installations (all four choices against copied pristine resources,
then all four against copied modded resources) passed with byte-exact override
restoration after uninstall. These tests do not launch the engine.

A second source review found no additional defects. The kit choices use
established CRE kit assignment and EE recruitment ability delivery. Fighter/Thief
uses the same general approach as jmerry's component, with original install-time
table calculations and exact XP conditions instead of fixed stat tables and
approximate level thresholds. Those differences are covered by installer tests;
they do not introduce a new runtime system.

In-game testing is optional additional confidence, not a blocker for these
components. A short Fighter/Thief recruitment through normal dialogue, level-up,
vampire-ability check and save/reload would cover the remaining engine integration
when convenient. A full playthrough or four-option live test matrix is not
necessary. No such live smoke test has been performed here.
