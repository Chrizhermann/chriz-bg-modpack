# Campaign XP caps with banking

Experimental and optional in alpha.11. On October 12, 650 (without 651) was
added to one existing private run at the author's request; adoption kept that
run's existing XP and levels. That run has not yet exercised a cap crossing,
save/reload or campaign release, so this is not gameplay acceptance. No save
repair or migration was performed.

Component **650** limits usable XP to 161,000 in BG1 and 500,000 in SoD while
retaining excess earned XP for later. Optional component **651** also limits
Shadows of Amn to 2,950,000 XP and requires 650. Both are optional. Without 651,
this mod stops imposing a campaign cap in SoA; with it, the restriction ends in
ToB. Other installed total caps and level tables still apply.

The initial target is EET on Windows with EEex. The collection's EEex 1.2 and
2.7.3 game have been checked offline; no upgrade to EEex 1.3.1 is required.
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

This candidate remains experimental. Live gameplay acceptance of startup, level-up,
Cancel/Continue, save/load and reactivation is still pending. Offline checks cover
the accounting, actual hook instructions, saved data and installer behavior;
they do not replace that later player check.

The first real start (Steam 2.7.3.0, EEex 1.2.0) refused to bank. EEex's
assembler writes the first call of its stats-hook relays with a REX prefix
(`40 E8`), which the startup check did not accept. The check now accepts that
form, plain `E8` and the address-table form `FF 15`, as long as the call still
reaches the original game function. If banking still cannot start, the log says
so, and Imoen's Spellhold XP (620) and the 237/238 recruitment catch-up behave as
they did before 650 was installed.

The saved account retains its chosen cap policy. Changing installer selections
is not a migration of an existing account. Existing-save repair, arbitrary
external respecs/direct XP memory writes and automatic release before uninstall
are outside this candidate. Removing 650 or EEex does not cash out an old-class
bank; do not remove them from a run whose bank you need to keep using.

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
