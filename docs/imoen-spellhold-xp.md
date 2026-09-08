# Imoen's Spellhold recruitment XP (component 620)

Imoen receives the other current party members' average XP when she joins in
the Spellhold maze, capped at **3,000,000 mage XP**. The adjustment happens once,
on her first script update after recruitment. Fractional XP rounds down.

For example, party members with 1.5M, 2M and 2.5M XP give Imoen 2M mage XP. A
party averaging 3.5M gives her 3M. Imoen is excluded from the average; occupied
party slots count even if a companion is dead. For multiclasses, the engine's
pooled XP counts once. For dual classes, the active class's XP counts; retired
class thresholds are not added. Her old thief XP is not subtracted from the award.

This sets her XP, with level-ups handled normally. It does not change her class,
kit, thief levels, spellbook or other characters' XP. Dismissing and recruiting
her again does not repeat the adjustment, including after saving and loading.

## Installation

Requires **BG2:EE or EET and EEex**. Install after EEex, EET's finalization and any
mods that replace Imoen's recruitment script. Select component **620** in the
installer and start the game through InfinityLoader. Component 610 is independent.

Install before recruiting Imoen in Spellhold; no new game is required. An existing
save with Imoen already in the party in the maze will also receive the one-time
adjustment. Saves beyond the maze are unaffected. Uninstall restores the original
script and any previous helper file; it does not undo XP already saved in a game.

## Implementation and evidence

`IMOEN2.BCS` gets one block before the existing script. It is restricted to party
membership, maze areas AR1512/AR1513/AR1514 and an unset creature-local marker.
`M_CBMIXP.lua` calculates the average and uses the native `ChangeStat` action to
set XP. The helper then sets `BD_JOINXP` to 2 and its own saved local marker to 1.

The base-game script inspected on 2026-09-05 uses fixed protagonist-XP thresholds
up to 1,250,000, gated by `BD_JOINXP = 0`. The effective EET script also uses
`BD_JOINXP = 1` for retired-thief deductions and 2 for completion. Using 2 prevents
both adjustments from altering the requested mage XP. The rest of the script is
preserved, including its dialogue and quest logic.

References: [IESDP ChangeStat](https://gibberlings3.github.io/iesdp/scripting/actions/bgeeactions.htm#370),
[STATMOD.IDS](https://gibberlings3.github.io/iesdp/files/ids/bgee/statmod.htm), and
[EEex action implementation](https://github.com/Bubb13/EEex/blob/master/EEex/copy/EEex_scripts/EEex_Action.lua).

Verified on Windows on 2026-09-05:

- Full repository suite: **186 passed**, including 47 new Imoen checks. Production
  Lua runs in Lua 5.1 and LuaJIT; installer tests use disposable synthetic games.
- WeiDU 249 parses the installer, all six libraries and the new BAF. BAF parsing
  uses real game IDS tables; `--nogame` cannot resolve its script symbols.
- Separate install/uninstall checks with the extracted base-game and effective
  EET `IMOEN2.BCS` preserve every original compiled block and restore all original
  bytes. The real game directory is only read.

Actual recruitment, level-ups and save persistence still require in-game
acceptance testing. On Windows, Python's fault handler prints LuaJIT's handled
exception `0xe24c4a02` during deliberate failure tests; the Lua errors are caught
and the full test process exits successfully.
