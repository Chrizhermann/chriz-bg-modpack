# Scroll casting at the reader's level

Alpha.11 replacement for component **430**. The DLL and installer have offline
checks; gameplay testing is still pending. This component has not been installed
in a real game or applied to ongoing saves.

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

The candidate requires Windows x64 BG2:EE or EET with EEex. Install **430**
after spell and item providers, including any other scroll changes. It includes
its own resource reader; players do not need Python or a compiler. Restart
through InfinityLoader after installation. If later mods change a tracked
resource, reinstall 430 to refresh its policy before starting the game.

Native compatibility checks currently cover the reviewed 2.6.6 and 2.7.3 game
builds, with the matching EEex profiles; the default EET installation's EEex
1.2 is included. Unknown native interfaces stop initialization with a diagnostic.
The component can be selected alongside campaign XP banking **650/651**.

The game has not yet exercised casting, the combined startup or save/load.
Offline tests check the actual hook instructions, private native callbacks,
resource preservation and installer rollback; they do not establish game
acceptance. This is not an existing-save repair.

## Short check for later

When you choose to test, use new test saves. Check one direct damage or duration
scroll with an active caster, a non-caster, and a dormant dual. Check a linked
or repeating spell, scroll learning, and save/reload during a continuing effect.
When testing with banking, also use its [short trial](campaign-xp-banking.md#short-check-for-later).
Keep the loader log and the first failing test save if a result is wrong.
