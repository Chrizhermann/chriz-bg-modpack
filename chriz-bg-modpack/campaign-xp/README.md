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

`research/xp-banking-native/bank_build.ps1 -BuildDir <new or empty folder>`
builds the candidate and records how each DLL was built. Before anything
compiles, `--capture` claims that folder (one build per folder), freezes the
research sources into it (`src/`) and hashes every input of each DLL there: its
build script, the sources and local headers it compiles (`native-inputs.json`).
Every check then runs from that frozen copy, and each packaged DLL embeds the
digest of its inputs and the build's identifier (`cbm_build_inputs.cpp`). Each
DLL's compile maps the frozen folder to `research\xp-banking-native`
(`/experimental:deterministic /pathmap`): MSVC otherwise names anonymous
namespaces after the source path, and every build folder would lay the DLL out
differently. The checks also run without the options `cl` and `link` read from
the environment (`CL`, `_CL_`, `LINK`, `_LINK_`). After the checks, `--record`
writes `native-build.json` from the capture and the MSVC version banners. It
needs the secret only that `bank_build.ps1` run holds, so an
abandoned capture records nothing; it consumes the capture on its first attempt,
and it refuses a DLL that does not embed this build's identifier and the digest
of its frozen inputs, or whose frozen inputs a probe rewrote meanwhile. A record
therefore needs one whole build: rebuilding some DLLs into an existing folder is
not supported. This binds a DLL to its sources through what the build passed
its compiler, not through a signature: it refuses a stale, foreign or
same-second leftover image without consulting any clock, but a compile given a
build's identifier and digest by hand would pass. What the probes regenerate
returns to the checkout where it still has the frozen version; they write LF
and only changed text, so an unchanged build rewrites nothing there. The sync
refuses a candidate built from sources other than the checkout's or whose DLLs
do not embed the inputs and build its record names, keeps a packaged DLL whose
rebuild differs only in the build identifier, link timestamps, debug
identifiers and the checksum, and writes the record into `package-manifest.json`.
`--check`, also run in CI, fails when a recorded input changed, an input was
added or removed, a DLL's compile would depend on its build folder, a packaged
DLL changed or embeds other inputs than its record names, or a DLL's linker
version and Rich header do not match the recorded toolchain.
