# Campaign XP caps with banking

Experimental and optional in alpha.11. On October 12, 650 (without 651) was
added to one existing private run at the author's request; adoption kept that
run's existing XP and levels. That run has not yet exercised a cap crossing,
save/reload or campaign release, so this is not gameplay acceptance. No save
repair or migration was performed.

Component **650** limits usable XP to 161,000 in BG1 and 500,000 in SoD while
retaining excess earned XP for later. Optional component **651** also limits
Shadows of Amn to 2,950,000 XP and requires 650. Optional component **652**
(`cbm_campaign_xp_chapters`, requires 650 and is mutually exclusive with 651)
instead applies chapter-by-chapter XP caps across BG1, SoD, SoA, and ToB:

- **BG1:** Ch. 1-2: 16,000 | Ch. 3: 20,000 | Ch. 4: 32,000 | Ch. 5: 64,000 | Ch. 6: 85,000 | Ch. 7: 161,000
- **SoD:** Ch. 7: 161,000 | Ch. 8: 200,000 | Ch. 9: 250,000 | Ch. 10: 350,000 | Ch. 11: 420,000 | Ch. 12-13: 500,000
- **SoA:** Ch. 1 (EET 13): 500,000 | Ch. 2 (EET 14): 1,000,000 | Ch. 3 (EET 15): 2,500,000 | Ch. 4 (EET 16): 2,900,000 | Ch. 5 (EET 17): 3,250,000 | Ch. 6-7 (EET 18-19): 3,500,000
- **ToB:** Ch. 8 (EET 20): 5,000,000 | Ch. 9 (EET 21): 8,000,000 | Ch. 10 (EET 22): 8,900,000

Component **652** also gates Baeloth's Larswood entrance scene (`BAINVI.BCS`) to
Chapter 5+ (`GlobalGT("Chapter","GLOBAL",4)`) when `BAINVI.BCS` is present, so
his 40,000 starting XP fits under Chapter 5's 64,000 XP cap without altering
`BAELOTH.CRE`. The gate patches the blocks that start his entrance (they name
`BA_START_SCENE` or `CUTBA01`). If another mod replaced the scene, or
`BAINVI.BCS` is not a valid script, 652 still installs the caps, leaves the
script unchanged and warns. Baeloth can then join earlier; banking keeps his
starting XP and banks what he earns until the chapter cap passes it.

To reach the 8,900,000 cap in ToB Finale (Ch. 10 / EET Ch. 22), use an XP cap remover such as Tweaks Anthology (`cdtweaks`) component 2090;
other installed total caps and level tables still apply.

The initial target is EET on Windows with EEex. The collection targets game
2.7.3.0 with EEex v1.3.1. Alpha.12 gave no character a bank account there; the
hook fix below was checked in game on EEex 1.2.0 and on EEex v1.3.1 (see the
lab checks below).

Install after EET finalization and the companion XP options you use. SR is not
a dependency. This component neither increases rewards nor levels characters
automatically. Multiclasses share one character cap.

## Seeing your bank

With 650 installed, open the character record screen and select the **Class**
tab. On the default interface, **Banked XP: N** appears below that character's
class and XP details, before the kit description. Normal XP stays separate.
The bank is shown even when it is zero. A short explanation gives the current
usable XP limit and when a later campaign makes the bank usable; other installed
XP limits and any XP kept when adopting an existing character still apply.

Changing the selected character updates the display. Multiclass characters see
one shared bank, and dual-class characters see the sum of their old- and
new-class banks. Viewing the record does not release XP, change levels, or
produce award messages. An account still being initialized or reconciled is
left to the existing banking system before its bank can be displayed.

The default BG1, BG2 and SoD record layouts have been checked from their source,
with automated checks of the display logic. The display has not been tested in
game. Infinity UI++, Dragonspear UI++, LeUI's BG1/BG2/SoD styles and EET's
SoD-style UI are **not verified** for this feature. If the expected class XP
panel cannot be identified, the interface stays unchanged and one diagnostic is
written to the log. Cap/release notices and `CBMBank_Status()` in the cheat
console remain available.

## Dual-classing with banked XP

Dual-classing happens immediately. With a pre-dual bank, XP earned before the
dual remains assigned to the old class; XP earned afterward belongs to the new
class. When a later campaign permits progression, both balances become usable
within the shared cap. The old class's bank never becomes a new-class XP award.
Any positive pre-dual bank preserves the exact pre-reset usable XP as the old
class's baseline, including progress above its current level's threshold.

Use the normal level-up button. If an old-class level is due, an additional
choice page handles its proficiency, skill and high-level ability selections
before the ordinary level-up screen. Cancel must preserve XP and undo the
preview. The new class must exceed the old class's resulting level to reactivate
it. Old-class abilities remain unavailable while that class is dormant.

For an overlapping level, the old class's HP contribution replaces the new
class's contribution. It does not award both. Living characters retain the same
missing HP, bounded by their new maximum; this is not a free heal or resurrection.

## Dual-classing without banked XP

With no pre-dual bank, dual-classing follows vanilla: the retired class uses its
current level's threshold from the installed `XPLEVEL` table, and any XP above
that threshold is discarded. That progress is neither awarded to the new class
nor counted against the campaign cap.

For example, a level-7 Fighter with 80,000 XP and a 64,000 level threshold uses
64,000 of BG1's 161,000 cap after the dual. The remaining 16,000 is discarded,
leaving 97,000 usable XP of room for the new class before banking. A dual exactly
at its level threshold is unchanged. A bank of even one XP uses the banked rule
above instead; this difference from a zero bank is intentional. Multiclass and
triple-class accounting is unchanged.

## Remaining limits

This candidate remains experimental. Live gameplay acceptance of level-up,
Cancel/Continue and reactivation is still pending. Offline checks cover the
accounting, actual hook instructions, saved data and installer behavior; the lab
checks below cover startup, capping, banking and save/load on two installs. They
do not replace that later player check.

The first real start (Steam 2.7.3.0, EEex 1.2.0) refused to bank. EEex's
assembler writes the first call of its stats-hook relays with a REX prefix
(`40 E8`), which the startup check did not accept. The check now accepts that
form, plain `E8` and the address-table form `FF 15`, as long as the call still
reaches the original game function.

Alpha.11 and alpha.12 then started, but never wrote the two actor-lifetime hooks
inside `EEex.dll`. EEex 1.2.0 writes a hook as a 32-bit jump to code it places
beside the game. `EEex.dll` loads more than 2 GB away, and EEex's hook writer
then leaves the entry unchanged without an error. No character got a bank
account, so every permanent XP award was refused and XP stayed unchanged. The
bank now places its own small relay pages beside `EEex.dll`, writes those two
entries itself and restores the original memory protection. Before banking
starts, it checks that every hook it installs, in the game or in `EEex.dll`, was
written. XP refused under alpha.11/12 is not restored.

If banking cannot start, XP is neither capped nor banked, and Imoen's Spellhold
XP (620) and the 237/238 recruitment catch-up behave as they did before 650 was
installed. The reason is written to the loader log and shown in the game's
message log once per loaded game, at the first action taken there.
`CBMBank_Status()` repeats it.

The saved account retains its chosen cap policy. Changing installer selections
is not a migration of an existing account. Existing-save repair, arbitrary
external respecs/direct XP memory writes and automatic release before uninstall
are outside this candidate. Removing 650 or EEex does not cash out an old-class
bank; do not remove them from a run whose bank you need to keep using.

## Lab checks

October 17, on a disposable copy of the collection install (Steam 2.7.3.0,
EEex 1.2.0, EET with Spell Revisions), with saves copied from a real run:

- **BG1 (650):** a party award, a script `ChangeStat` award and kill XP stopped
  usable XP at 161,000 and banked the excess for the three characters who
  crossed it; the others were unchanged. Saving and reloading in the same game,
  and loading in a new game process, kept the same amounts. A later 600 XP party
  award added 100 to each bank.
- **SoA (650 and 651):** a large party award stopped five characters, two of
  them dual-classed, at 2,950,000 and banked the excess; a sixth stayed below
  the cap. A save and reload kept the same amounts.
- **Startup failure** (forced with an invalid cap policy): banking did not
  start and XP stayed uncapped and unbanked. The reason appeared once in the
  message log right after loading, not again on later actions, and
  `CBMBank_Status()` repeated it.

Not covered there: manual level-up, a multiclass sharing the cap, the dual-class
level-up pages, the record screen and a campaign transition that releases XP.

October 20, on a disposable copy of the collection's Recommended install (Steam
2.7.3.0, EEex v1.3.1, EET with Spell Revisions), with this release's package:

- **Alpha.12 first:** as reported, no character got a bank account and every
  XP change was refused.
- **Startup:** every hook was written, including the two `EEex.dll`
  actor-lifetime entries. Characters from loaded saves, joiners and a
  dual-classed character got accounts.
- **BG1 (652):** awards above a chapter cap kept usable XP at the cap and
  banked the rest (Chapters 1-2: 16,000 usable, 4,600 banked). Raising the
  chapter released banked XP up to the new cap. Saves reloaded with the same
  amounts, also in a new game process.
- **SoD and SoA (652):** the same at the SoD chapter steps and at SoA
  Chapters 1 and 2 (EET 13 and 14).
- **Baeloth (652):** at Chapter 4 he did not appear in Larswood; at Chapter 5
  he appeared and joined at 40,000 XP.
- **SoA (651):** usable XP stopped at 2,950,000 and the rest was banked; a save
  reloaded unchanged.
- **A save from alpha.12** loaded with an account and lost no XP.

That check found two faults, fixed and checked again in the same lab before
this release. A new game's main character got no account until its first XP
change, so every cap check before then failed with "Party bank has not been
initialized before cap check"; it is now adopted at its first cap check. With
652, XP awards in the BG1 prologue (Chapter 0) were refused until the chapter
was set; an account still waiting for EET's campaign or chapter flags is now
checked against the first phase of its own cap policy.

Chapters were set directly and XP was given from the console, not through
story progression. Manual level-up, multiclass characters and the record
screen were not covered.

## Short check for later

Use new test characters when you choose to test. No additional installation or
game copy is requested now. The status command is `CBMBank_Status()` in the
cheat console; cap and release messages also appear in game.

1. Cross 161,000 with an ordinary XP award. Check that usable XP stops there,
   excess XP remains banked, normal manual leveling works and a new test save
   reloads with the same amounts. Check one multiclass shares that limit.
   In the record screen's Class tab, check the bank matches the status command,
   stays separate from normal XP, and updates when you select another character.
   Check long class descriptions, font zoom, and reopening the screen.
2. Give a suitable human Fighter 300,000 earned XP in BG1 and level to Fighter 8.
   Dual to Thief, then earn another 20,000. The Fighter retains its 300,000
   entitlement; the Thief's 20,000 is banked while the BG1 cap has no room.
3. At the SoD transition, Fighter 9 and Thief 6 are due under the installed
   default XP table. Open level-up, Cancel and reopen, then complete it. Check
   the choices, unchanged XP after Cancel, HP and the still-dormant Fighter.
4. At Thief 10, check that the Fighter reactivates once, with its correct HP,
   proficiencies and abilities. Save/reload, then check another normal level-up.

Stop at the first incorrect result and keep that new test save and the loader
log. A full campaign playthrough or a second collection installation is not
needed for this check.
