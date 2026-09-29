# Story-based utility XP — component 611

**Available from v0.2.0-alpha.8:** the BG1/SoD level-16+ lock reward is **155 XP**, using the EE
Fixpack correction approved by Christopher on September 29, 2026. Collection
integration remains separate.

Component **611**, label `cbm_story_utility_xp`, keeps BG1-sized lock, trap and
spell-learning rewards throughout **BG1 and Siege of Dragonspear**. Entering
Shadows of Amn switches to the original BG2 reward schedule; Throne of Bhaal
continues using that schedule. It requires **EET and EEex**.

This is the chosen default for the next CEBG release. Collection integration is
separate and has not been changed by this implementation. Existing component
**610** (`cbm_utility_xp`) remains the optional smooth, protagonist-XP-based
alternative, with its original calculation and settings unchanged. The installer
rejects selecting both: uninstall the other mode before switching. Party-average
scaling is deferred and is implemented by neither option.

## Rewards

These are **party-total XP awards**, divided normally by the engine. The engine
chooses the lock/trap ability-level column; scribing uses the spell's level.
No character XP, party average, party size, or chapter threshold sets the reward
schedule. There is no extra rounding or interpolation.

| Native ability-level bracket | BG1/SoD lock | BG1/SoD trap | SoA/ToB lock | SoA/ToB trap |
|---|---:|---:|---:|---:|
| 1–5 | 25 | 10 | 250 | 1,000 |
| 6–10 | 40 | 17 | 400 | 1,750 |
| 11–15 | 95 | 27 | 950 | 2,750 |
| 16+ | 155* | 32 | 1,550 | 3,250 |

Learning a spell awards **10 × spell level** in BG1/SoD and **1,000 × spell
level** in SoA/ToB (levels 1–9). For example, a level-three scroll gives 30 or
3,000 party XP. Larger personal shares for smaller parties remain normal engine
behavior. The normal ability-level handling of multiclass/dual-class thieves is
retained; 611 does not introduce 610's protagonist-XP normalization.

*The original BG1 table has **15** for level-16+ locks, dropping from 95. This
component uses **155**, the documented EE Fixpack typo correction. All other
values above match the original tables. No intermediate SoD balance was added.

## Campaign selection

The live engine campaign name must be `BG1`, `SOD`, `SOA` or `TOB`. Within these
supported campaigns, use EET's global progression markers:

- `InToB = 1` or `EndOfBG1 = 2`: BG2 schedule.
- `EndOfBG1 = 0` or `1` in the BG1/SoD campaign: BG1 schedule.
- A direct SoA/ToB start whose opening script has not initialized the markers:
  wait and recheck on subsequent updates, without assuming BG1.

EET chapters overlap: BG1 is 0–7, SoD 7–13, SoA 13–19 and ToB 20–22. Chapter 13
therefore cannot by itself authorize BG2 rewards. Direct starts initialize the
markers in `BD0120`, `AR0602` and `AR4000`; carried transitions set the same
progression state. The flags track story progress, including visits to old areas.
`NEWGAME_*` and the menu's Active Campaign setting are not used.

The hidden menu callback also runs while inventory is paused, and successful
action handling gets a refresh at action start. Phase detection is reevaluated,
so transition initialization and loading another campaign cannot leave an old
phase cached merely because XP or a table pointer is unchanged. No marker or
state is written into a save.

Black Pits, tutorial, unknown campaign names, invalid flags and unsupported table
layouts produce a diagnostic. Unsupported campaign/flag states do not publish a
new reward schedule. If this runtime previously applied one, it restores the
installed on-disk XPBONUS values in memory, rather than leaving those rewards in
an unsupported session. Malformed tables are rejected before writing any cells.

## Installation and scope

Install **611 after EEex, EET finalization and other utility-XP tweaks**. It only
publishes its own Lua/menu files; `XPBONUS.2DA` stays unchanged on disk. Launch
through InfinityLoader. Uninstall while the game is closed and restart when
switching modes. WeiDU restores preexisting files through normal backups.

The runtime changes only the three XPBONUS reward rows in memory, preserves
other rows and unnamed allocation padding, and extends the final lock/trap
bracket through any additional named ability-level columns. Scribing columns
above spell level nine are zero, as in the original table. It does not grant XP
directly, edit characters or saves, change XP caps, or alter successful-action
checks, combat XP or quest rewards.

## Evidence and validation

Original tables were extracted through KEY/BIF indexes with all override files
bypassed. The BG1 table and the SoD source table resolve to the same DEFAULT.BIF
payload (SHA-256 `264f230128ae97c436b005862e90e9b626a4e0d52c35ee05227dde21c8cd38cd`).
The BG2 DEFAULT.BIF table is distinct (SHA-256
`b0a1eb7b7b75967ee5bab501bcf4f1d007c0a29f31085e1f81895f422790280c`). There is no
`LEARN_SPELL2` row in either original table.

Supporting primary sources:

- [BG2 XPBONUS reference](https://gibberlings3.github.io/iesdp/files/2da/2da_bgee/xpbonus.htm).
- [EE Fixpack BG1 correction](https://github.com/Gibberlings3/EE_Fixpack/blob/master/eefixpack/files/tph/bgee.tph).
- [EET campaign and chapter documentation](https://github.com/Gibberlings3/EET/blob/master/EET/docs/Modder%27s%20Notes.html).
- [InfinityLoader CInfGame bindings](https://github.com/Bubb13/InfinityLoader/blob/master/Core-Shared-Files/generate_bindings/in/Baldur-v2.6.6.0.h): `m_sCurrentCampaign` is a CString.
- [EEex global reads](https://github.com/Bubb13/EEex/blob/master/EEex/copy/EEex_scripts/EEex_GameState.lua) and [independent 2DA loading](https://github.com/Bubb13/EEex/blob/master/EEex/copy/EEex_scripts/EEex_Resource.lua).

Validation is focused offline Lua/engine-fixture and disposable WeiDU installation
testing, including transitions, direct-start initialization, reload, unsupported
states, mutually exclusive modes and byte-exact uninstall. No live game, save,
stream session or full collection installation was used. Live acceptance
remains separate from release.

The focused results are 174 story calculation/runtime checks across Lua 5.1 and
LuaJIT 2.1, six story installer tests, and 196 existing progressive-XP/installer,
public-surface and packaging regression checks, all passing. Installer syntax and
the actual release allowlist also validate. The source and documentation are
allowlisted. Release integration also checks the extracted package's installer.
