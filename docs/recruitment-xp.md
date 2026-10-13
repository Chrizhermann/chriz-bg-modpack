# Fade and Evandra: first-recruitment SoA XP

Independently selectable companion options, added in alpha.11:

| Component | Label | Recruitment resource | Private script |
|---|---|---|---|
| 237 | `cbm_fade_recruitment_xp` | `E3FADE13.CRE` | `CBMFXP.BCS` |
| 238 | `cbm_evandra_recruitment_xp` | `RH#EVA.CRE` | `CBMEXP.BCS` |

On first recruitment, raise the companion's XP to the highest protagonist-XP
threshold reached: **125,000; 250,000; 500,000; 750,000; 1,000,000; 1,250,000**.
The threshold is inclusive. Below 125,000 protagonist XP, award nothing. Never
reduce companion XP. This is a one-time recruitment adjustment, not ongoing
party XP synchronization or Imoen 620's party-average rule.

An owned local variable completes the evaluation even when no XP award is
needed. Dismissal, rejoining and saving/reloading cannot repeat the award. The
original script resumes on its next evaluation; no romance or quest variable is
changed. In particular, EET's separate `BD_JOINXP` state is preserved.

Award/completion responses deliberately end the script pass without `Continue()`.
The engine may queue actions before applying local/XP changes, so the completion
marker alone is not a safe same-pass exclusion between descending thresholds.

## Installation and scope

Requires BG2:EE or EET and the corresponding NPC's recruitment resource. No
EEex, Spell Revisions, class conversion or portrait component is required.
Install after NPC mods, NPC class/kit changes, SCS NPC customization, EET
finalization and other companion script writers. Install **before the NPC is
first created in the world**, normally before starting a new game.

The installer reads the effective override-script name from the SoA CRE,
creates a private copy, and prepends the XP blocks. The only CRE change is its
eight-byte override-script reference. Original compiled story blocks remain
intact in the copy; the original shared script is unchanged. This also supports
renamed scripts and preserves other actors using them. Missing recruitment
resources produce a warning and no change; a missing required story script or a
collision with the private script name causes a rollback.

Class, kit, current XP, levels, statistics, spellbooks, proficiencies, equipment,
effects, dialogue and story data are otherwise unchanged. Normal level-up choices
remain available. Fade's normal, Shadowdancer and Fighter/Thief builds use the
same SoA recruitment resource. Evandra's Sorcerer and portrait options remain
independent and continue preserving template XP.

ToB templates and scripts are not patched. Fade's vampire/story actor
`E3FADE2` and Evandra's `RH#EVAMP` are not recruitment targets. Upstream/EET
campaign transitions retain their own ToB XP behavior.

**Existing actors retain their old script reference and receive no repair.**
This includes an NPC already created in a previously visited area, even if not
yet recruited. Existing-save migration is a separate design, not part of these
components. Uninstall restores template/script resources, but cannot undo XP or
private script references already serialized in a save; use a pre-creation save
or start a new game when changing this selection.

## Other catch-up providers

SCS 35.21 customization supplies its own catch-up and temporarily resets XP
while the actor is level zero. An effective script containing both its
`dw#aulel` setup application and its level-zero XP-reset block is left unchanged
with an explicit installer message. Use SCS's normal character-screen leveling
flow. A global SCS component flag alone does not prove it handled this actor.

An existing script with a one-shot protagonist-threshold XP setter and an
unconditional party-membership guard in the same block is also preserved with
an explicit message. Its chosen ceiling is not replaced. Recognition compares
the matching completion variable literally, tolerates block/trigger ordering,
and does not combine unrelated quest blocks or accept a negated party guard.
Complex scripted/Lua catch-up providers outside these recognized forms have
not been certified; install ordering is not a universal ownership detector.

## Source evidence

Evandra 2.2's `scripts/bgee.baf:35-124` contains the intended SoA ladder, but
`setup-evandra.tp2:123-127` compiles `dialogue/bgee.d`, not that BAF. The orphan
file also changes romances and has an incomplete no-award completion branch;
neither is copied. Fade 5.6's SoA recruitment has no equivalent catch-up.

SCS 35.21 `leveller/leveller_2.tpa:428-461` replaces XP script behavior with
customization setup. `leveller/leveller_lua.tph:151-194,252-258` supplies its own
party-based XP adjustment through the character-screen callback. Its
`dw#aulel` local indicates setup, not completed XP assignment, so running a
second award after that marker would be a race.

## Validation and limits

`tests/test_recruitment_xp.py` installs through real WeiDU in disposable fixtures
and evaluates the resulting decompiled XP blocks. It checks threshold boundaries,
already-higher XP, below-minimum completion, reload/rejoin persistence, BG2EE/EET,
SR/no-SR, changed builds, renamed/shared scripts, extra/reordered story blocks,
other XP providers, repeated application, malformed inputs, rollback and exact
uninstall. Script evaluation models deferred action execution, so queued
completion markers cannot incorrectly hide same-pass threshold fall-through.

On October 9, 2026, **50 focused recruitment tests and 10 public-surface/release
builder tests passed**, with WeiDU 249 used for installer checks. Six additional
disposable cases covered both companions using copied effective resources,
upstream CREs with compiled source scripts, and source-backed SCS setup scripts.
The four ordinary cases changed only the recruitment CRE's override pointer and
added its private clone; the two SCS cases made no resource changes. Original
compiled script tails, unrelated resources and ToB resources were preserved, and
all six uninstalls restored the baseline exactly. Source resources were read-only.
These are automated installer and script-model results, not native recruitment
or level-up acceptance. No full collection installation was performed.

The remaining manual check is short: naturally recruit each NPC from a
pre-creation save at a known protagonist threshold, verify XP and ordinary
level-up, then dismiss/rejoin once. Where SCS owns customization, use its normal
character-screen flow and confirm it remains the only provider. No game launch
or save modification is authorized by this document.
