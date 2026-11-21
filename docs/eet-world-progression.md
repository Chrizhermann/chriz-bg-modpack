# EET: Story-Consistent Campaign Boundaries and SoD Backtracking Fixes

Component **680**, label `cbm_eet_world_progression`, applies to **EET** only. It preserves a single unified EET installation, continuous campaigns, and new-game starts in BG1, Siege of Dragonspear, Shadows of Amn, and Throne of Bhaal, while closing EET's cross-campaign worldmap backtracking bridges and fixing SoD within-campaign backtracking issues.

## Why

In default EET:

1. Entering Shadows of Amn from BG1/SoD keeps the bidirectional worldmap link between Athkatla City Gates (`AR0020`) and Nashkel (`BG4800`), letting a mid-SoA or ToB party travel freely back to the Sword Coast and Dragonspear.
2. Watcher's Keep (`AR3000`) links both SoA and ToB on the same worldmap node, so in a continuous run into Throne of Bhaal walking to `AR3000` still routes back into Amn (`AR0020`, `AR1100`, etc.) and BG1/SoD.
3. Entering Siege of Dragonspear keeps `BD1000 <-> BG0900` open into the southern Sword Coast, while fresh-game starts show out-of-campaign worldmap icons (`AR0020..AR1000`, `BD3000`, `BD4000`, etc.) and SoD chapters leave abandoned-camp triggers, chests, and NPC crowds inconsistent when backtracking in chapters 9 and 10.

## What the component changes

All behavior is driven by `chriz-bg-modpack/data/eet_world_progression.2da` (with an optional override table at `override/EET_WORLD_PROGRESSION.2DA`):

- **Worldmap boundaries (`WORLDMAP.WMP`)**:
  - Severs `AR0020 <-> BG4800` and `BD1000 <-> BG0900` under default rules (`BLOCK_SOA_TO_BG1_SOD`, `BLOCK_SOD_TO_BG1`).
  - Ensures SoD chapters 8–10 reverse road links (`BD7100 -> BD1000`, `BD3000 -> BD2000`, `BD7400 -> BD3000`) are present (`SOD_OPEN_CH8_TO_CH10_ROAD`), while keeping removed areas such as `BD7000` hidden when already disabled in the installed map.
  - Classifies every worldmap area into `BG1`, `SOD`, `SOA`, `TOB`, or `SHARED_SOA_TOB` (`AR3000`), including quest-mod areas (`NTotSC`, `Blackhearts`, `Aura`) and dynamic neighbors.
- **Campaign start & transition gating (`BG2600`, `BDCUT08`, `BDDEBUG`, `BD1000`, `AR0602`, `AR4000`, `BD4000`)**:
  - Clears out-of-era worldmap flags (`RemoveWorldmapAreaFlag(..., 15)`) at every campaign start and transition, restoring native static flags (`VISIBLE | ENABLED`) for the active campaign (`BD7200`, `BD3000`, `BD4000`, Athkatla districts, `AR4000`).
  - Keeps Watcher's Keep (`AR3000`) reachable in both SoA and ToB (`WATCHERS_KEEP_IN_SOA = 1`) while cutting all `AR3000 -> SoA` routes upon entering ToB (`BLOCK_TOB_TO_SOA = 1`), and keeps Dragonspear closed after SoA begins (`BD4000.BCS` no longer re-enables post-SoD travel).
- **SoD chapter 8–10 backtracking fixes**:
  - Keeps `BD2000`, `BD5000`, and `BD7400` open after the Coalition Camp defense (`BD3000.BCS` at `bd_plot = 402`) until entering `BD4000` (`SOD_KEEP_PRE_ASSAULT_OPEN = 1`).
  - Prevents dismissing companions inside abandoned camps (`BD1000`, `BD7100`) from trapping them on old `ff_camp` triggers (`BDPARTY.BCS` + `CBM_OldCamp` in `MYAREA`).
  - Forwards and locks abandoned `PlayerChest00` chests in `BD1000` (Ch. 9+) and `BD7100` (Ch. 10+) so items cannot be stranded in vacated camps (without touching `Container009`).
  - Keeps Baeloth's Black Pits crowd intact in `BD1000` until `BD_Baeloth_Intro > 5` when not yet triggered, and cleans up leftover camp sentries (`BDFIST.BCS`, `BDOTILDA`), duplicate `BDJEGG` in saved `BD2100`, and Bridgefort siege audio/NPCs (`BD2000`) once chapters advance.

## Installation order and testing

Install after `EET_end` and any worldmap or quest mods (such as `NTotSC`, `Blackhearts`, `Aura`, `chriz-sod-remix`, `SCS`). Covered by WeiDU parse-checks, synthetic EET worldmap/script install and byte-exact uninstall tests, We Overwrite mutation tests (custom policy overrides, damaged single scripts/worldmap isolation, pre-existing markers), extracted release-archive tests, and disposable smoke tests against real 2.7.3.0 EET worldmap and script files. Live playthrough testing across full campaign transitions has not yet been performed.
