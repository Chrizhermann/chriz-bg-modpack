# Scroll casting at the reader's level

Replacement for component **430** since alpha.11. Alpha.11 to alpha.13 stop their
scroll runtime soon after a game starts (see [Earlier versions](#earlier-versions)).
This version was checked in a lab game, not yet in an ongoing playthrough.

Arcane scrolls use the reader's active arcane caster level; divine scrolls use
their active divine caster level. When the reader has no active caster level
of that type, use half their highest active class level, rounded down, with a
minimum of 1. A dormant dual class does not count. For example, an active
Fighter 20/Thief 24 uses level 12; a dormant Mage 13 dualed to Thief 12 uses
level 6 until the Mage reactivates.

This replaces the previous fixed-level-15 compromise. The component resolves
the installed spells and their delivery effects, including Spell Revisions,
instead of assuming that resource names have vanilla meanings. It preserves
scroll learning, genuine fixed protection scrolls and unrelated item/spell
data. Ambiguous mixed learning/casting abilities retain their existing
behavior and are listed in the install report. In the checked default EET
installation, only the special tutorial Flame Arrow scroll needed that exception.

## Installation and current limits

430 requires Windows x64 BG2:EE or EET with EEex. Install **430**
after spell and item providers, including any other scroll changes. It includes
its own resource reader; players do not need Python or a compiler. Restart
through InfinityLoader after installation. If later mods change a tracked
resource, reinstall 430 to refresh its policy before starting the game.

Native compatibility checks currently cover the reviewed 2.6.6 and 2.7.3 game
builds, with the matching EEex profiles; the default EET installation's EEex
1.2 is included. Unknown native interfaces keep 430 from starting, and the
loader log says why. The component can be selected alongside campaign XP
banking **650/651**.

430 shows nothing in the game, with one exception described below. When it
finds a problem, at startup or later in a session, it turns itself off for the
rest of that session: scrolls then cast at their normal level, as without this
component. Loading its startup script again once it has started also turns it
off. It writes this line to the loader log (`InfinityLoader.log` in the game
folder), with the technical cause on the next line:

```text
[CBM scroll] Scrolls at the reader's level (Modpack 430) are turned off for this session, so scrolls cast at their normal level. Your saves stay usable.
[CBM scroll] Cause: ...
```

The exception: if 430 fails to start and then cannot take all of its changes
back out of the running game, those changes stay until the game closes, and
loading or saving a game in that session is not safe. The cause line then says
to exit the game and not to load or save, and after the two lines 430 shows
one message box. It comes while the game starts, before the main menu and
before any game can be loaded, and at most once per session:

```text
chriz-bg-modpack: scrolls at the reader's level could not start cleanly. Please quit and restart the game before you load or save a game.
```

Saves already on disk are not affected. This case was never seen in a game;
the offline tests force it.

Restart the game to turn 430 on again. For what this version does not cover
yet, see [Known limitations](#known-limitations).

Checked in a lab game on October 23, 2026, on Steam BG2:EE 2.7.3.0 with EET,
Spell Revisions and EEex v1.3.1. With the first build of this version
(`CBMScroll.dll` SHA-256
`9671cf3f2838ebdbc487c4cf1882a7d937b6cc673568e35358f691c954901b3c`), levels
matched the rules above for active casters, non-casters and dormant dual
classes, with single-target, area and point-targeted scrolls. Scroll learning,
loading older saves, a new game, NPCs joining, opening containers, and saving
and reloading during continuing scroll effects or a queued scroll cast all
worked.

The second build (SHA-256
`41fed66c93f86a138afa853d203835ad755f0176ac627d8d42d42f4b63adb11b`) changed
only how the component handles a problem. In the same lab, after loading a
save, it gave Sleep, Invisibility and Improved Haste scrolls the reader's level,
including effects they apply through helper spells. The repeating parts of
Combust and Acid Storm kept their normal levels, as the same spells do without
this component. A scroll spell turned back at its reader by a spell-turning
effect still had the reader's level, and fixed protection scrolls kept their
own level. A problem forced on purpose during a scroll cast made that cast and
every later one use the normal scroll level. That build showed a message box
about it the next time any creature started an action or a script event ran,
once per session; before, it waited for a script event such as a creature
shouting, so in a quiet scene it came 15 minutes later. The current build
writes it to the loader log at that point instead.

A third pass with the second build, also in the lab, repeated the remaining
cases. After using a scroll, opening containers worked several times over, both
in a save from an older installation and in a new game. A new BG1 game and a
new SoA game started, Xan, Sarah and Imoen joined, the party changed areas, and
Imoen learned a scroll. Saving and reloading while Spell Shield's repeating
effect was still running worked in the same and in a new game session.

The third build (SHA-256
`88ce92e2ae3af6b07a67693eef97d88dd8c2061667bacda9196cb7b4d9b68e11`, checked in
the lab on October 24) changes how it loads saves made while 430 was turned
off, or not installed. Such a save keeps each creature's earlier scroll data
unchanged, and once the game has saved that creature again, the data no longer
matches its effects. 430 now drops that data for that creature only and names
it in the loader log: its effects keep their levels, and spells they cast
later use their normal level. Before, loading such a save turned 430 off for
the whole session. In the lab, three such saves loaded without a problem, with
one log line per creature. In a save that also held up-to-date data for a
creature in another area, 430 kept that creature's data and saved it again.
New scrolls used the reader's level, and saves made afterwards loaded without
dropping anything again.

On October 25 the third build's DLL got a new `CBMS_Startup.lua` (SHA-256
`6899144fe12e9ef8381559022221c0f421b3feb12b851839bca894e043d192a8`) that
writes every notice to the loader log only. In the lab on October 25, Imoen
read a Haste scroll, and 430 stayed on while the Haste ran out and its later
fatigue came due: across area changes, Imoen leaving and rejoining the party or
staying behind while the party traveled, and saving and reloading in the same
and in a new game session. The Haste kept her level throughout. When 430 turned
itself off, after a second load of its startup script and in the fourth case
under [Known limitations](#known-limitations), the loader log got the two lines
above and nothing appeared in the game.

The current build (`CBMScroll.dll` SHA-256
`74ea73d879c906d57497eb7f3d3ec6dc4b890da5a066961ec46e596b2a29aa54`,
`CBMS_Startup.lua` SHA-256
`8f1cef80bc362a02a63801567b29e99ca7fa8f3b9f08a8380917a62cde15e3bb`) adds the
one message box described above and starts its loader-log lines with
`[CBM scroll]`. Its DLL tells the startup script whether a failed start had to
leave its changes in the game; the script never reads that from the message
text. In the lab on October 26 it started normally without a box, and Imoen's
Free Action scroll got level 4, half her level. After a second load of its
startup script, 430 turned itself off with only the two loader-log lines and no
box, and her next Free Action scroll got its normal level 1.

The alpha.14 release candidate's package, installed in the same lab on October
26 together with campaign XP banking (650 and 651), did the same: it started
without a box, Imoen's Free Action scroll got level 4, and 430 stayed on while
two more saves were loaded in that session and one in a new session.

Offline tests check the actual hook instructions, private native callbacks,
resource preservation and installer rollback. This is not an existing-save
repair.

## Known limitations

This release does not handle the cases below. A source review of this version
(October 25, 2026) found the first three; none was seen in a game. The lab
check of the same day found the fourth.

- **Failed startup while another thread is inside a hook.** If 430 cannot
  finish starting, it removes the hooks it already installed and frees their
  small code pages. It waits for any call it can see inside them, but a call on
  a thread other than the game's main thread is invisible for a few
  instructions, right after it enters and again right after its handler
  returns. Such a call could then run freed code and crash the game. This can
  happen only during startup, before any game is loaded, and only if startup
  fails while the game runs those code paths on another thread; the game was
  never seen doing that. The practical risk is very low.
- **Hooks written while other threads run.** While starting, 430 writes its
  hooks into the game's code without pausing other threads, as EEex does with
  its own hooks. A thread running one of those instructions at that very
  moment could execute a half-written instruction and crash. Nothing makes sure
  that no other thread runs there during startup; this relies on the game
  running those paths only on its main thread, which is busy with the startup
  itself. It applies once per start, before any game is loaded. The practical
  risk is very low.
- **A cast in progress when 430 turns itself off.** If 430 turns itself off
  while it is choosing or passing on the level of a scroll cast, that one cast
  can still get the reader's level; every later one uses the normal level.
  This needs a game call from another thread at exactly that moment, which was
  never seen. The practical risk is very low, and the effect is that one cast.
- **A saved scroll effect whose reader is not there.** Some scroll spells cast
  a later part on their own, such as the fatigue that follows Haste. If a save
  holds such an effect from a scroll read by a creature outside the party, and
  after loading that save the reader is not in a loaded area when the later
  part comes due, 430 turns itself off for that session. That happens when the
  reader was removed from the game or stayed behind in another area. Back in
  the reader's area before the later part came due, 430 stayed on. Party
  members who read a scroll were found after every load, also after leaving the
  party. The practical risk is low.

## Earlier versions

Alpha.11 to alpha.13 tracked the game's actions by memory address, but the game
destroys most actions without the one destructor they watched. After a load, a
new game, an NPC joining or opening containers, they showed "copied action
construction overlaps an existing lifetime" or "scroll carrier born twice
without destruction" in an EEex message box and stopped changing scroll levels
for that session; scrolls then behaved as without this component. Saves from an
earlier installation are not the cause. Installing this version replaces the old
runtime; restart the game afterwards.

## Short check for later

The lab passes above covered new games, NPCs joining, containers, area changes,
learning and saving during continuing scroll spells. An ongoing playthrough has
not been checked yet. When you choose to test, use new test saves. When testing
with banking, also use its
[short trial](campaign-xp-banking.md#short-check-for-later). Keep the loader log
and the first failing test save if a result is wrong.
