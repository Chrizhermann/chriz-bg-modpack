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

Campaign XP banking remains experimental. Live gameplay acceptance of level-up,
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

Up to alpha.13, an XP change through the XP effect (opcode 104) that the bank
could not take was reported to the game as failed. The game then stopped
processing that character's later effects and tried the XP effect again on
every pass. Script variables set behind it (opcode 187 locals) were therefore
missing from a save and did not come back when it was loaded
([chriz-bg-collection#19](https://github.com/Chrizhermann/chriz-bg-collection/issues/19)).
Now no XP change the bank cannot take stops the rest of the effects:

- **Applied the usual way:** if the bank fails or refuses (an error in its Lua
  code, a character without a bank identity, an earlier XP change of that
  character still unresolved, or a change outside the game's main thread), the
  game applies the XP change as it would without 650. The cap still applies
  while that character's account is in order, because the bank is computed from
  the game's own XP. If the account itself is the fault (no identity, or an
  unresolved earlier change, also one kept in a save), its cap check fails too,
  and that character's XP is not capped. The loader log says once per loaded
  game how many XP changes were applied the usual way and why the last one
  could not be banked; nothing about it is shown in the game. On October 23,
  2026 Christopher accepted the wording on the condition that it does not
  appear inside the game; on October 25, 2026 he confirmed that technical
  information goes to the loader log only.
- **Processed a moment later:** while the game is saving, or while another XP
  change of the same character is still in progress, the change waits without
  holding up other effects and is processed at that character's next effect
  update. If the character's XP or the effect changed while the bank prepared
  the change, the bank withdraws what it had recorded and tries once more with
  the new values; if they change again, the game applies the change the usual
  way. The bank remembers such a retry for up to 64 changes at a time and
  forgets a change once it is done or its character is gone; while all 64 are
  still waiting, a further changed preparation is applied the usual way at
  once. No change waits for good: a save or a change in progress always ends
  first, and a script `ChangeStat` made during another change of that character
  is applied right after it.
- **Finished without XP:** only if what the bank recorded cannot be withdrawn
  (it no longer matches exactly, or the bank lost track of characters
  meanwhile, see below), the effect ends without adding XP. Its amount stays in
  the bank's unresolved journal, as for an interrupted change, and is not added
  twice.
- **Nothing written:** if the bank can tell that the character itself was
  removed or replaced while it prepared the change (it saw that character's
  destruction or a new character at its place), nothing is written to whatever
  now holds its place, and the bank keeps no record of it. The loader log
  counts such changes once per loaded game (status 11); there is no notice in
  the game.
- **Lost track of characters:** if a character is created or destroyed outside
  the game's main thread (see the thread audit below), the bank no longer
  trusts any character's identity and banks nothing for the rest of the
  session: later XP changes are applied the usual way. Restarting the game
  restores banking for a new game and for saves made before the bank lost
  track. Saves made after that keep every character with a bank account out of
  banking, even after a restart: they get XP the usual way, their XP is not
  capped, and `CBMBank_Status()` says that banking is not assigned to them.
  Such a save could not confirm whose account is whose, so it keeps the
  accounts set aside with their data, and nothing brings them back into banking
  yet. A change in progress when the bank lost track is no proof that its
  character was removed, and nothing of it is dropped. If it happened at
  another character's place, the change is handled like one whose values
  changed (tried once more, applied the usual way, or finished without XP as
  above). If it happened at this character's place, the bank cannot tell
  whether that place still holds the same character, so it writes nothing
  there: an effect whose record cannot be withdrawn ends without XP, one
  without a record waits and is applied the usual way at the next pass, and a
  script `ChangeStat` is kept unapplied. The loader log lists the kept changes
  once per loaded game (status 12); there is no notice in the game. A kept
  change is held in memory for the session only: closing the game loses it, and
  only the log keeps what it was.

Destroying or recreating a character inside the bank's callbacks is
prohibited. The game's code that called them (effect processing, and the stat
update after a script `ChangeStat`) keeps using the character and the effect
after the callback returns, which nothing in the bank can make safe; the
nothing-written case only keeps the bank from writing into the wrong
character. A static test (`tests/test_campaign_xp_callback_lifetime.py`)
enforces the prohibition for the shipped Lua: it follows, by name, every
function of the bank that the XP, cap check, party and dual-class callbacks can
reach, and fails on any call that leaves the bank other than reviewed reads and
records (the bank's own native queries, EEex's data and table lookups, the
game's XP cap table, Lua string and table functions), on any call it cannot
resolve, including a function value handed to `pcall`, `xpcall` (both of its
functions), `table.sort` or `gsub`. Because it trusts names, a parser of the
whole package (reachable or not) also fails on code that changes what a name
means: rebinding a reviewed name, a function the walk follows or a module
field it follows; binding a callback global anywhere but its hook; writing a
field under a computed key into anything that may be one of the bank's module
tables, however the code passed it on; calling an engine method (a CString's
`get`, a 2DA's `getAtLabels`, a stat's `GetAtOffset`) on a value that is not
the engine's, or a Lua string method at all; and using metatables, raw writes,
`debug`, `_ENV` or code loading the test cannot read. It trusts the reviewed
game and EEex functions to run no script, action or other Lua, does not model
metatables of game objects (EEex's field reads), does not follow global names
written by computed names (only the bank's own install and uninstall code does
that, for its own names), and does not see what other modules or native code
put into a table they hand over (only the configured fields, by their names,
are taken to hold the bank's modules). The retry, the finish without XP and
the nothing-written case are therefore safeguards; the bank's offline tests
force each one.

An XP change leaves an unresolved journal only where the bank cannot tell what
was stored: an error, an unexpected result or a failed completion after the
game's own XP code ran, or a prepared change that cannot be withdrawn (finished
without XP: its amount is neither added nor banked, and the journal keeps it).
Resolving such a journal is not implemented yet. Until it is, that character
gets every later XP change the usual way and its XP is not capped, also after
saving and loading, because the journal is saved with the account; the cap
check reports it in the loader log. Nothing replays a kept amount by itself.
A script `ChangeStat` kept unapplied because its character's place changed on
another thread (Lost track of characters, above) is in no account: the bank
cannot tell which character it now belongs to, so it is held natively for the
session and listed in the loader log.

Script `ChangeStat` changes to XP do not use the XP effect and cannot hold up
other effects. One the bank refuses is no longer dropped: the game's own code
applies it the usual way, and it is counted in the same loader-log line.
Because the bank is computed from the game's own XP, the next cap check caps it
again and re-derives the bank, while the account is in order.

The game stores at most 4,294,967,295 XP per character; an account can hold
more. A change the game applies the usual way that replaces the stored value (a
`SET`, a percentage, or an addition past either end of that range) makes the
XP the account held above it obsolete. The bank judges this by the change the
game actually runs, also one the bank passes on without banking, and also when
the effect changed while the bank prepared it, whether the game runs it then or
when it is tried once more (an award that became a `SET` counts as a `SET`).
The next cap check then sets the account to what the game stored, drops that XP
and logs the amount; a save made before it already holds the corrected account.
Any other change the game
applies the usual way keeps the stored value plus that XP exact, so nothing is
counted twice. An account with an unresolved journal keeps it unchanged; the
saved journal notes that a later change replaced the stored value.

In 2.7.3.0, script actions and effects run in the game's main loop
(`CChitin::Update`, then the world screen's update, area and character AI, and
effect processing). The game's other threads are the multiplayer network
client, SDL's timer, audio, controller and rumble threads, movie decoding and
crash reporting. `SearchThreadMain` and `CNetwork::ThreadLoop` run inside the
main loop despite their names. EEex's only thread is its optional debug window
(`EEex.OpenDebugWindow`), which nothing in this stack opens.
`research/xp-banking-native/main_thread_audit.py` checks this statically
against the pinned game executable and EEex v1.3.1's binaries;
`main-thread-audit-2.7.3.txt` beside it is its output. It lists every thread the
game or EEex starts and finds no resolved path from any of them to the XP code,
the effect and AI paths into it, or the character constructors and destructor
where EEex hooks them: a path along direct calls and jumps, switch targets, and
the virtual calls it matches in the main loop. It fails if such a path appears.
It does not prove that no other thread gets there. The indirect calls and jumps
on those threads stay unresolved, so a route through them is not excluded; its
result is therefore INCONCLUSIVE and lists each such route with its count (for
example 103 in the lobby thread's `talk_base::Thread::PreRun` and 2,306 in the
lobby code as a whole). The Beamdog internet lobby, which reads the engine's
Lua state without calling Lua, possibly on its network thread, is not covered.
The debug window's indirect call sites are not followed either, the audit is
static only, and threads of Windows, drivers, OpenAL and Steam are not
analysed. An XP change on another thread is applied by the game's own code
exactly as without 650, counted in the same loader-log line but not corrected
as above, because the bank's records belong to the main thread. A character
created or destroyed on another thread switches banking off for the session
(see Lost track of characters above).

If banking cannot start, XP is neither capped nor banked, and Imoen's Spellhold
XP (620) and the 237/238 recruitment catch-up behave as they did before 650 was
installed. The reason is written to the loader log. The game shows no such
technical notice unasked (see above); `CBMBank_Status()`, run in the cheat
console, shows the reason.

The saved account retains its chosen cap policy. Changing installer selections
is not a migration of an existing account. Existing-save repair, arbitrary
external respecs/direct XP memory writes and automatic release before uninstall
are not supported. Removing 650 or EEex does not cash out an old-class
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
  `CBMBank_Status()` repeated it. That message-log line has since been
  removed; the loader log and `CBMBank_Status()` keep the reason.

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

October 26, on the same copy as on October 20, with the alpha.14 release
candidate's package (650, 651 and 430):

- **Banking:** a party award in an SoA save kept the main character's usable XP
  at 2,950,000 and banked that character's share; the two others, below the
  cap, got theirs.
- **Script variables
  ([#19](https://github.com/Chrizhermann/chriz-bg-collection/issues/19)):** with
  the bank forced to refuse every XP effect, a party award was applied the usual
  way, and the main character's usable XP stayed at the cap. The loader log got
  one line counting the three changes; nothing appeared in the game. Two script
  variables set on the main character right after that award were there at
  once, and a save made while the refusal was still forced kept both, loaded in
  the same and in a new game process. With the refusal lifted, the next awards
  were banked again.

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
