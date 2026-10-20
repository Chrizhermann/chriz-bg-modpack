# Campaign XP candidate

Experimental and optional; native gameplay acceptance is pending.

Component 650 applies BG1/SoD campaign caps while retaining excess earned XP.
Component 651 depends on 650 and additionally applies the SoA cap. Component 652
depends on 650 (and is mutually exclusive with 651) and instead applies
chapter-by-chapter XP caps across BG1, SoD, SoA, and ToB, plus Baeloth's
Chapter 5+ spawn gate in `BAINVI.BCS` (skipped with a warning when another mod
replaced his entrance scene). All three are optional. They require EET
and the reviewed Windows x64 EEex/native interfaces.
Install after optional recruitment components 237, 238 and 620, then restart
through InfinityLoader. Keep this mod directory in the game folder: the startup
resource loads its private modules and six DLLs from here.

With no pre-dual bank, the retired class uses its current level's threshold from
the installed XPLEVEL table; excess progress is discarded as in vanilla and
neither enters the new class nor uses campaign cap room. A positive pre-dual bank
keeps the exact pre-reset usable XP baseline instead. An unbanked dual exactly at
its level threshold is unchanged.

This package does not claim live gameplay acceptance, authorize existing-save
repairs, or migrate saved account policies when component 651 or 652 is added or
removed. Uninstalling removes startup resources and restores installer-owned
recruitment changes; it is not a saved bank conversion procedure. Do not use
saved banked characters after removal without a separately reviewed recovery plan.

Research sources are canonical. Refresh package mirrors with
`python tools/sync_campaign_xp.py --bundle <offline-candidate-directory>` and
verify them with `python tools/sync_campaign_xp.py --check`. Text mirrors use LF
line endings so the manifest survives a fresh checkout. Native binaries must
match that candidate's manifest; this helper never compiles, installs, or launches.
