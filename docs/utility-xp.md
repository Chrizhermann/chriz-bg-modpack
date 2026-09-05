# Progressive utility XP — component 610

Component `610`, label `cbm_utility_xp`, scales experience for picking locks,
disarming traps and learning spells throughout BG1, SoD and BG2 in EET. It
requires BG2:EE/EET and a working EEex installation. The implementation is in
`chriz-bg-modpack/utility-xp/`; the balance file is `CBMUXPC.lua`.

## Research and design

The reference component is **EET Tweaks 2042, “Vanilla friendly progressive.”**
It retains low rewards through ability level 10 and reaches the BG2 maximum
only at level 40. Its spell-level-9 scribing reward is 4,000 XP; levels 1–4
still give only 10/20/30/40. It contains no class normalization.
[Upstream implementation, pinned](https://github.com/K4thos/EET_Tweaks/blob/a55b5b47ebf4fbf3a38309d85f30df941bfcca56/EET_Tweaks/EET_Tweaks.tp2#L937-L964).

EET itself substitutes BG1-sized rewards without a later campaign switch.
[EET implementation, pinned](https://github.com/Gibberlings3/EET/blob/74e91d72bca5d073fa11c1d088b90d7ff0c7105d/EET/lib/bg2_2DA.tph#L1448-L1453).
In native BG2, locks award 250/400/950/1,550 and traps 1,000/1,750/2,750/3,250
across ability-level brackets 1–5/6–10/11–15/16+. Scribing awards 1,000 times
**spell level**, independent of caster level.
[IESDP XPBONUS reference](https://gibberlings3.github.io/iesdp/files/2da/2da_bgee/xpbonus.htm).

A static reward table cannot select a different progression basis for a
multiclass or retired dual-class thief, or scale scribing by character progress.
This component instead uses **Player1's current total XP plus the minimum XP
required for any retired dual-class level**. All party members use that same
scale. Recruitment, portrait reordering and selecting a different thief or mage
cannot change it. The native engine still decides whether an action succeeds,
awards the XP, and distributes it among the party.

Using total XP makes progression comparable across class builds: an F/M/T does
not suffer three-way level dilution, and a Thief 7 -> Mage keeps progressing
after the thief class stops leveling. It also follows level progression without
reward jumps at every level-up or changes due to temporary level drain. It uses
base XP and class levels, not temporarily modified combat stats.

This is a deliberate balance curve rather than exact campaign emulation: the
same total XP can occur in late BG1 or at the start of standalone BG2, so one
continuous curve cannot exactly reproduce both. Early BG1 stays conservative;
rewards reach the BG2 level-6–10 bracket around the BG1 expansion cap, the
level-11–15 bracket by late SoD, and the normal maximum during BG2. High-level
rewards stop growing. The anchors are policy choices and can all be changed.

## Default rewards

Values are **party-total awards before the engine's normal distribution**, not
XP for each companion. Intermediate rewards interpolate linearly by XP and
round **up to a multiple of 10 XP**. Scribing multiplies the interpolated rate by
spell level before rounding. Rounding adds less than 10 XP to each party award;
it does not add that amount separately for each companion.

| Protagonist progression XP | Lock | Trap | Scribing per spell level | Level-5 spell |
|---:|---:|---:|---:|---:|
| 0–10,000 | 30 | 10 | 10 | 50 |
| 40,000 | 50 | 100 | 50 | 250 |
| 89,000 | 150 | 500 | 250 | 1,250 |
| 161,000 | 400 | 1,750 | 500 | 2,500 |
| 440,000 | 950 | 2,750 | 1,000 | 5,000 |
| 1,320,000+ | 1,550 | 3,250 | 1,000 | 5,000 |

For example, at 125,000 XP a lock gives 280, a trap 1,130, and a level-4 spell
1,500 XP. At 440,000 XP and above, level-9 scribing gives the native BG2 9,000 XP.
The default intentionally increases late-BG1 scribing over vanilla BG1.

At the smoke-test save's 290,500 XP, the level-1 scribing calculation is
`500 + (290500 - 161000) / (440000 - 161000) * 500 = 732.07885...`.
The original whole-point result was 732; the default now rounds that up to 740.
The configured early lock anchor remains 25 before rounding, giving 30 by default.

Newly recruited mages and bards also receive these rates for their low-level
catch-up spells: from 440,000 protagonist progression XP, levels 1–5 award
1,000/2,000/3,000/4,000/5,000 XP regardless of the learner's own XP. For an
illustrative library of ten spells at each of those levels, that is 150,000 XP
for the party, or about 25,000 per character in a six-person party. The curve
targets approximate per-action rewards; total campaign XP also depends on how
many locks, traps and spells the player uses. No fixed campaign-total parity
with vanilla is claimed.

## Multiclass and dual-class accounting

Multiclass CRE XP already stores the total across classes: do not multiply or
divide it. Read-only native-resource checks found Jan at 161,000 XP with
Mage 7 / Thief 8, Aerie at 90,000 with Cleric 6 / Mage 6, and Jaheira at 90,000
with Fighter 6 / Druid 7. These agree with the independent GemRB engine's
class-count division during level checks.
[GemRB XP interpretation](https://github.com/gemrb/gemrb/blob/90dab6cd1353073e4543f9a112dcb7afbe62d1c3/gemrb/GUIScripts/LUCommon.py#L27-L57).

Dual-class flags identify the original class. Current XP tracks the active
class, so its retired class's threshold is read from the **installed XPLEVEL**
table and added back. Native Nalia has Mage 9 / Thief 4, 161,000 current XP and
the original-thief flag: this component uses 166,000 progression XP. Both dual
directions and the period before reactivation use the same rule.

The class map covers every standard two-class combination in both dual
directions. Thief combinations are Fighter/Thief, Mage/Thief and Cleric/Thief,
plus Fighter/Mage/Thief as a multiclass. Kits use their underlying class; no
kit-specific branch is needed. Tests exercise all ten standard multiclass IDs
and all sixteen directions across the eight two-class combinations.

[CRE flags/level slots](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/cre_v1.htm),
[GemRB dual-class XP reset](https://github.com/gemrb/gemrb/blob/90dab6cd1353073e4543f9a112dcb7afbe62d1c3/gemrb/GUIScripts/DualClass.py#L218-L223).

**Limitation:** excess XP discarded when dual-classing is unavailable afterwards.
For example, retiring Fighter 8 at 200,000 XP reconstructs its level threshold
of 125,000 XP. Rewards can decrease at that moment. No historical XP ledger or
save-state tracking is introduced. For an existing dual, the level threshold is
the recoverable contribution; assuming the next threshold would over-credit it.

## Installation and tuning

Install after EEex, EET's finalization, and other XP reward tweaks. Source APIs
were checked against EEex v0.11 and current EEex; a working loader configuration
is required. Launch using `InfinityLoader.exe`. Standalone BG1:EE is deliberately
excluded: its native XPBONUS row conventions differ from BG2/EET.

Copy the main TP2 and `chriz-bg-modpack` content directory into the game folder
alongside WeiDU, close the game, and select component 610. For a **first install**
of this component on an English game:

```powershell
.\weidu.exe setup-chriz-bg-modpack.tp2 --language 0 --use-lang en_US --force-install-list 610 --no-exit-pause
```

Edit `chriz-bg-modpack/utility-xp/cbmuxpc.lua` before installing. Afterwards,
edit the installed `override/CBMUXPC.lua` and restart the game. Changes apply
to existing saves; **no reinstall is needed for balance adjustments**. Keep a
copy of custom settings before replacing the mod with a newer distribution.

Each anchor contains `xp`, `lock`, `trap`, and `scribe`. Add or move anchors to
reshape the transition. XP thresholds must be increasing nonnegative integers
starting at zero, and rewards must be nonnegative and nondecreasing. Independent
`lockMultiplier`, `trapMultiplier`, and `scribeMultiplier` settings adjust an
entire reward category; `1.25` gives 25% more, `0` disables that category.
`roundingStep` sets the final award increment (default `10`). `roundingMode` is
`"up"` by default; `"nearest"` rounds to the closest increment instead. For the
original exact whole-point behavior, use `roundingStep = 1` and
`roundingMode = "nearest"`. Older configs omitting both settings retain that
whole-point behavior. The step must be a positive integer; overflow checks
include the rounded result. A disabled category still awards zero.
Invalid numbers and integer-overflowing rewards are rejected with a Lua log
message. Syntax errors are reported during initialization.

Scribing becomes more valuable later, including for low-level spells. This
creates an incentive to save scrolls for later, and the base game's erase/relearn
behavior is retained. There is no additional bonus for those actions and no
extra mechanism preventing repeated learning.

## Implementation and compatibility

The hidden, noninteractive menu refreshes the existing engine-owned
`m_ruleTables.m_tXPBonus`, including while inventory is paused. An action-start
listener also refreshes it. It follows EEex's own persistent hidden-menu pattern.
[EEex B3TimeStep](https://github.com/Bubb13/EEex/blob/204040502ac920161d60046d90b766b8d2d08152/EEex/copy/EEex_scripts/B3TimeStep.lua).

Every existing lock/trap level column receives the current shared reward, so
native class-level selection no longer affects the amount. Scribing columns
1–9 receive spell-level rewards. Higher custom scribing columns, unrelated rows,
headers and defaults are preserved. In particular, a 50-column table with
missing level-41–50 values is filled for locks and traps. No new columns are
invented; other mods must provide columns for any supported levels above the
existing table's width. The native parser can allocate extra unnamed columns:
the disposable EET installation exposed 51 allocated columns for 50 level
headers. Trailing unnamed columns remain untouched, and the allocated width
is retained when addressing each row. Interior gaps or reordered level headers
are rejected before any write.

Cells are assigned with the native CString assignment operator. The adapter
does not retain creature or cell pointers between callbacks and clears caches
when loading another save. It does not add XP directly, alter character stats,
write save variables, replace UI.MENU, or edit disk XPBONUS/XPLEVEL.
[EEex resource access](https://github.com/Bubb13/EEex/blob/204040502ac920161d60046d90b766b8d2d08152/EEex/copy/EEex_scripts/EEex_Resource.lua),
[CString alias](https://github.com/Bubb13/EEex/blob/204040502ac920161d60046d90b766b8d2d08152/EEex/copy/EEex_scripts/EEex_Alias.lua).

The runtime values take precedence over install-time XPBONUS edits for the three
supported rewards. Compatibility with a second runtime mod owning those same
cells is not provided. The component changes neither kill nor quest rewards,
and it leaves normal engine XP caps and sharing in force. Rewards refresh at UI
callbacks/action starts; it is not an interception of each individual XP award.

WeiDU owns five payload files and restores their prior bytes on uninstall.
Restart after uninstall to clear the modified in-memory table. No extra files
or character effects need cleanup.

## Verification

Install test dependencies with `python -m pip install -r tests/requirements.txt`,
then run `python -m pytest -q`. Set `WEIDU` and `WEIDU_BIN` to the same executable
path or put WeiDU on PATH; the utility suites on Windows also find the ignored
`weidu.exe` in the repository root.
Without WeiDU, installer tests explicitly skip. CI supplies it.

Automated checks cover production Lua under Lua 5.1 and LuaJIT 2.1, curve values
and boundaries, custom settings, multiclass XP, both dual directions, downtime,
missing thresholds, 40/50/80-column engine doubles, paused-menu callback logic,
session resets, pointer reuse, absence of a party, API/configuration errors,
and writes confined to the intended table cells. Synthetic KEY/BIF/TLK games
exercise the real component installation, prerequisites and byte-exact uninstall.
The TP2 and every included TPA are independently parse-checked.

The release candidate passed 276 tests on Windows, including 185 utility-XP
checks and both extracted-ZIP installer checks. Set `CBM_RELEASE_ARCHIVE` to a
built ZIP to enable those archive checks; on Windows, `CBM_USE_BUNDLED_WEIDU=1`
tests the executable actually shipped in that ZIP. Both hosted workflows build
the package twice, compare bytes and exercise installation from the extracted ZIP.

On Windows, Python's fault handler can print `0xe24c4a02` diagnostics for LuaJIT's
handled software exceptions (including deliberate error-path tests). Check the
pytest result and process exit code; a printed diagnostic alone is not a failed
test. The utility-XP suites include native padding regressions, configurable
rounding and the real WeiDU installer checks.
[LuaJIT's Windows exception mechanism](https://github.com/LuaJIT/LuaJIT/issues/781).

On 2026-09-05, component 610 was installed in an independent copy of a modded
EET game, with a separate save/settings profile. BG2:EE 2.6.6.0 with
EEex v0.11.0-alpha reached the menu, loaded a BG2 opening-area save, and saved
successfully. A native inspection confirmed 50 named XP columns plus one blank
padding column; all intended reward cells matched the curve and padding stayed
untouched. This exposed and fixed the original strict-width validation issue.

**One actual scribing award passed:** at 290,500 protagonist XP, Imoen learned
Grease while inventory was paused. The game displayed 732 party XP, and native
base XP increased by 366 for each of the two party members. The maintainer also
confirmed the throwaway test worked. This native test preceded the rounding
adjustment; the same progression now calculates 740 XP. Live lock/trap awards,
the full class matrix, and longer gameplay sessions remain separate acceptance work.

Use disposable games and saves for the remaining checks:

1. At a configured milestone, pick a lock and disarm a trap; compare the total
   party XP change with the configured rewards, allowing native integer sharing.
2. Repeat with a multiclass thief and a reactivated dual-class thief at the same
   protagonist progression. Confirm success gives the same award and failure none.
3. With inventory paused, learn spells of different levels. Change progression
   between trials and confirm the new rate applies. Check a failed scribe too.
4. Load a low-XP save after a high-XP save in the same process. Reorder portraits
   and change the selected character; verify rewards still follow Player1.
5. Edit the installed config, restart and repeat a known award. Uninstall/restart
   and verify the previous XPBONUS behavior returns.

For diagnostics, `CBM_UtilityXP_Runtime.lastXP`, `.lastRewards`, and `.lastError`
are readable Lua values. They do not grant XP or modify characters.
