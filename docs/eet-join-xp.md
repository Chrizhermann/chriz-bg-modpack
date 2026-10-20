# EET join-XP catch-up for joinable NPCs (239)

Optional component **239** (`cbm_eet_join_xp`), EET only.

EET gives each joinable BG2:EE NPC a one-time join-XP catch-up, tracked by the
NPC's local `BD_JOINXP`:

- **SoA:** Beamdog's ladder sets a joining NPC to the highest protagonist band
  reached: 125,000; 250,000; 500,000; 750,000; 1,000,000 or 1,250,000. Below
  89,001 protagonist XP it awards nothing; otherwise a final block completes it.
- **ToB:** EET's raise sets a joining NPC to 2,500,000. EET appends it to the
  NPC's ToB script and resets `BD_JOINXP` when the NPC is summoned to the pocket
  plane.

Mod NPCs that EET moves into BG2 often lack the SoA ladder, and some ToB scripts
cannot reach the raise. Component 239 adds EET's own block wherever a joinable
NPC's script lacks it. XP is never lowered.

## How it finds joinable NPCs

It reads EET's rules from the installed game, not a list of NPCs:

1. `CAMPAIGN.2DA` names each campaign's party table in its `PDIALOG` column
   (`PDIALOG` for SoA, `25DIALOG` for ToB in EET). A death variable in that
   table belongs to an NPC who can join in that campaign.
2. EET marks the SoA override script of every joinable NPC with its party block
   (`InPartyAllowDead(Myself)` sets `<DV>PartyBG2`). Every such script of an NPC
   in the SoA table is checked.
3. At the ToB transition EET switches these NPCs to their ToB scripts in
   `AR4000` and `AR4500` (`ChangeAIScript`), and a ToB start creates them in
   `AR4500`. Each of those scripts, and each created creature's override script,
   is checked when its NPC is in the ToB table.

The installer lists the party-table entries for which EET has no such script.
Their join XP is unchanged: they cannot join in that campaign, or a mod adds
them without EET's NPC transition.

## What it adds

- A **SoA script** without a one-shot ladder gets Beamdog's ladder on top. Each
  block also requires `ENDOFBG1` 2 (BG2) and not `INTOB` 1, so it runs only in
  SoA.
- A **ToB script** gets EET's raise on top when it has none, or when a block
  above the raise completes `BD_JOINXP` first. The raise also requires `INTOB` 1,
  so it never runs in SoA, where some of these scripts are used as well.

Left unchanged:

- a SoA ladder of any owner, keyed on any variable, with any thresholds or cap,
  including one without the final block (Pai'Na, Sirene) and the private copies
  of 237/238;
- a ToB raise that can run, keyed on any variable;
- a protagonist ladder in a ToB-only script, which is that mod's ToB catch-up;
- scripts where SCS NPC customization set the actor up (it owns joining XP);
- everything on a second installation. A patched script already has its block.

EET's own "already patched" check looks for the text `"BD_JOINXP"` in the
compiled ToB script. Compiled scripts store `"LOCALSBD_JOINXP"`, so it never
matches; EET adds the raise again on each transition call (Fade's ToB script has
it twice). Component 239 recognises blocks by what they do instead.

## Effects in a game

- A joining NPC gets the catch-up once, at the first script round in the party.
  Leaving and rejoining, a reload or later protagonist XP do not repeat it.
- Patched scripts also apply to existing saves. An NPC in the party whose
  `BD_JOINXP` is still 0 gets the catch-up on its next script round. NPCs that
  already used theirs are unchanged.
- An NPC who completed the SoA ladder keeps `BD_JOINXP` 1 when in the party at
  the ToB transition, so EET does not raise it there. Vanilla NPCs already work
  this way. Before 239, mod NPCs without the SoA ladder still had 0 and were
  raised to 2,500,000 at the transition.
- Fresh SoA Yeslick (YeslickNPC) has EET's ToB raise in his general and default
  scripts. His new SoA ladder completes `BD_JOINXP` first. Without 239 that raise
  could set him to 2,500,000 in SoA (static finding; the engine's run order for
  those script slots was not tested).
- Xan and Yeslick imported from BG1 by component 199, and Safana in Amn, keep
  `BD_JOINXP` 1 from their BG1/SoD ladder and receive no SoA catch-up, as before.
  EET's ladder relies on EET's import reset, which these routes do not do.
- Sarevok (fixed 2,700,000) and Safana (no ToB route in EET) are unchanged.
- With 650, the added blocks behave like the vanilla NPCs' ladders and raise.
- With 237/238 (Fade, Evandra), either order works. 239 leaves 237/238's
  private script with its own ladder and gives the original script, which
  existing actors keep, Beamdog's ladder. Installed after 239, 237/238 find
  that ladder and leave the NPC alone.

No spell, class, kit, Spell Revisions or EEex dependency.

## Installation

Install after the NPC mods, EET's NPC transitions and NPC customization mods.
Uninstalling restores the scripts. It cannot undo XP already awarded in a save.

## Validation

`tests/test_eet_join_xp.py` installs through real WeiDU on synthetic EET games
shaped like EET's tables and transition scripts, and runs the installed scripts
in a bounded script model. It covers Sarah (SoA ladder added), an NPC that
already has the block (unchanged, including a second application), Wilson and
Yoshimo (ToB raise), with and without Spell Revisions, existing providers of
other owners and SCS, raise reachability, malformed or missing EET tables
and scripts, 237 in both orders, and byte-exact uninstall.
`tests/test_recruitment_xp.py` checks that 237/238 recognise an existing ladder
under EET's `TRIGGER.IDS`, where WeiDU decompiles `InParty(Myself)` as
`IsValidForPartyDialogue(Myself)`.

A dry run on copies of the tables and scripts of one real EET install (with
Spell Revisions, SCS and several NPC mods) added the SoA ladder for Fade, Sarah,
Yeslick, Xan and Evandra and the ToB raise for Wilson and Yoshimo. The other 50
SoA and ToB scripts of joinable NPCs already had their catch-up and stayed
unchanged. The party-table entries reported without an EET script were BG1 NPCs
who do not join in BG2, Sarevok, Safana and a few other table entries.

The lab check (October 17) used a disposable copy of that install with 650 and
651, and a copy of a real SoA save whose protagonist had 929,138 XP. WeiDU
patched the same seven scripts as the dry run. Sarah, already in the party at
856,820 XP, kept her XP. A newly created Sarah (89,000 XP in her creature file)
joined at 750,000 with `BD_JOINXP` 1 and EET's party marker set, and campaign
XP banking recorded 750,000 usable and nothing banked. A save and reload kept
these values. The ToB raise was not exercised in game.

A second lab check (October 20) used a copy of the collection's Recommended
install with EEex v1.3.1 and this release's package. Sarah joined at 750,000
with `BD_JOINXP` 1. With 652 in SoA Chapter 1 (EET 13) she also joined at
750,000: 500,000 usable and 250,000 banked. A save kept these values.
