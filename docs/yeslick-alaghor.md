# BG1 Yeslick: Fighter/Alaghor of Clangeddin (188)

YeslickNPC v5 component 1 assigns Alaghor to its BG2 templates only. Component
**188** extends that selected preset to the two BG1 recruitment templates,
`YESLIC.CRE` and `YESLIC5.CRE`. Later native EET routes carry the existing actor;
continuity 199 preserves that actor's developed build when bringing him to BG2.

Install YeslickNPC **1**, other relevant kit/progression changes, **188**,
then **199**, then **EET_end**. Component 188 requires EET and must precede
Yeslick's first creation in the saved world. Use a new campaign for continuity.
It does not need EEex. Existing saved actors are not migrated.

This is an optional preset. Omit 188 for the collection's vanilla-companion
opt-out. Selecting YeslickNPC **0** makes 188 skip without changing any resources,
even if an unrelated mod also installed the Alaghor kit. An unexpected class or
different kit on either recruitment template is an installation error, not
permission to overwrite an intentional conversion.

## Kit and ability handling

The installer resolves `LK_ALAGHOR` from the local `KIT.IDS`, finds its unique
`KITLIST.2DA` row and reads that row's `ABILITIES` CLAB. It validates the
installed priest-level delivery for each nonempty AP_/GA_ entry: either an
existing base-priest CLAB entry at that level, or the provider's qd_multiclass
dispatcher and kit-filtered EFF. Missing resources, stale kit IDs, missing
priest dispatch and unexpected source shapes fail with rollback.

After that preflight, only the recruitment CREs' kit dword changes. The native
recruitment/level-up mechanism supplies the installed grants at priest levels.
The installer does not bake additional spells/effects into the CRE, replay kit
abilities at transitions, change levels to match XP, or assign the BG2 template's
build. XP, both class levels, attributes, proficiencies, spellbooks (including
SPIN112), memorization state, effects, inventory, scripts and dialogue remain.

Yeslick v5's original kit table grants `LK#Y1` at priest level **8**, `LK#Y2` at
**14**, and `LK#Y3` at **16**. A Fighter 17 / Cleric 5 still receives none of
these three innates from the preset. Later priest-wide passives in the effective
CLAB remain on their installed schedule. The spell header's casting level is
not the level at which the kit grants it.

`YESLIC5` is a BG1 level-dependent recruitment template, not a separate
SoD-specific actor. The EET `NPCLVLDS.2DA` table and SCS
`gameplay/standardise_bg1_spells.tpa` identify the two-member family. `YESLID`
is the dream-script creature named in BGDIALOG/BDDIALOG and is excluded, as are
other similarly named creatures and the provider's BG2 `LK#YESL`/`LK#YES25`.

Source references: Yeslick v5 `yeslicknpc/lib/main_component.tpa:142-154`,
`lib/alaghor_kit.tpa:125-132`, `lib/qd_multiclass.tpa:94-161,177-280`, and
`2da/lk#yk.2da`; EET `lib/bg1_CRE.tph:680-704`.
The [Yeslick source](https://github.com/Spellhold-Studios/Yeslick-NPC) supplies
the multiclass implementation. The [KITLIST reference](https://gibberlings3.github.io/iesdp/files/2da/2da_tob/kitlist.htm)
documents the CLAB mapping. Resource names and numeric kit IDs are resolved
from the target installation, not copied from a different game's tables/TLK.

## Existing-save migration proposal — not applied

An override-template patch cannot repair an already-saved Yeslick. Keep an
existing-save migration separate from component 188 and test it on a disposable
copy of the specific installation and save.

1. Identify the actual party/stored actor by its installation's DV (`YESLICK`
   before normalization, `LK#YESLK` after 199), class, kit, XP and both levels.
   Require an explicitly intended Alaghor conversion and an unkitted
   Fighter/Cleric. A different kit or ambiguous actor requires review.
2. Resolve that installation's kit, priest CLAB and delivery records. Compare
   the actor's already-earned kit grants and priest-wide passives through his
   **actual priest level**, preserving spent uses and unrelated permanent effects.
   Do not replay every AP_ spell or assume an absent effect record proves a
   missing passive: some effects change base data instead.
3. Apply the kit and only proven missing, level-appropriate grants once. Existing
   qd_multiclass once-only markers may have been consumed while he was unkitted;
   a kit-field write alone is not a general migration. For the reported 5/5
   Yeslick, the original level-8/14/16 innates must not be granted.
4. Verify recruitment state, level-up, dismiss/rejoin, and save/reload against
   the recorded base attributes, progression, spell counts and effects. Keep the
   original save and installation copy for rollback.

No migration code is installed by 188. A general saved-character migration is
not required for the fresh-install patch.

## Existing-install Dispel proposal — component 410 unchanged

Component **410** already supplies hostile-only Yeslick Dispel at
`floor(1.5 * level)` and preserves the intended installed Keldorn/SCS behavior.
It is separate from kit selection and needs no duplicate implementation here.

For an older installation where 410 is absent, first test **only 410** on an
isolated copy with its matching local sources and supported effective SPIN112 /
SPCL231 shapes and SCS 3540 selection. Record the existing component log and
resource hashes; verify preserved non-dispel/casting effects and byte-exact
uninstall restoration. An already-correct installation needs no rewrite.

Any later authorized live application must close the game, install that selected
component, restart, and verify a native cast; do not reinstall the whole modpack
or copy another installation's spell/TLK files. An app update alone changes
neither installed spells nor saved companions.

The collection's existing vanilla-Yeslick route suppresses combined 410,
including its Keldorn portion. This separate customization policy is unchanged.

## Verification limits

The automated tests use real WeiDU on authored synthetic games. They cover
dynamic kit/CLAB resolution, both targets and exclusions, vanilla/missing-provider
and ordering gates, priest levels 1/5/7/8/13/14/15/16/24, stale or early-only
dispatch, later base-priest passives, malformed/custom actors, rollback,
byte-exact uninstall, and preservation through the real component 199 installer.
They verify installed resource contracts, not execution of the native engine.

A separate disposable synthetic install used read-only copies of **64** effective
Combined provider resources and both pre-199 CRE backups; only the two kit fields
changed, and uninstall restored all bytes. Actual fresh recruitment, level-up
across 8/14/16, transition and save/reload remain pending. No installed game or player save was
modified during this work.
