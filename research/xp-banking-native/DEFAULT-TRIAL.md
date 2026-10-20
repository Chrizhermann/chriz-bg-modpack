# Default EET banking candidate: disposable trial

Prepared October 9, 2026. The candidate is uninstalled. No game launch, game
folder modification, save modification, or native gameplay acceptance is claimed.
Christopher chose **Keep it prepared; do not launch** for the proposed trial.
Do not copy/stage a test game or run it without a later explicit instruction.
The source has since gained ordinary installer options 650/651. For Christopher's
later check, use the shorter [player guide](../../docs/campaign-xp-banking.md).
The copying/staging proposal below is retained as historical preparation, not
an outstanding request to create another installation.

## Candidate

Source: `codex/campaign-xp-banking`, isolated worktree
`%USERPROFILE%/.codex/worktrees/campaign-xp-banking/chriz-bg-modpack`.
Build output: `C:/tmp/campaign-xp-banking-20261009/candidate-bundle`.
`research-build.json` identifies the exact Lua/menu/native binaries. The build
executes our DLLs and offline native instruction harnesses, not Baldur.exe.

The ordinary path keeps earned XP in native base storage and limits usable XP
by campaign. Single/multiclass accounting, immediate banked dual reset, actor
ownership, XP awards/SET handling and saved state are assembled in
`bank_bootstrap.lua`. The selected old-class progression uses an additional
manual page followed by the native level-up screen; it has installed-rule
proficiencies, skills, HP and HLA choices. Old HLAs remain queued until native
reactivation. The old HP contribution owns overlapping advancement levels.

The first trial uses the default EET/EEex setup, the BG1/SoD policy, and the
reviewed 2.7.3 executable/EEex profile. The second supported executable remains
covered by the existing offline checks; do not create a second playtest matrix.
The actual source installation and collection use EEex 1.2.0. Its required APIs
and hook layouts were checked, and its lifetime entries are now included in the
reviewed profiles. The focused loader and actual installed callback checks pass.
Correction, October 20: the earlier conclusion here that an EEex 1.3.1 upgrade
is not required is superseded. The collection now targets EEex v1.3.1 on
2.7.3.0; the October 17 actor-lifetime hook fix was checked in game on
EEex 1.2.0 (October 17) and on EEex v1.3.1 (October 20).
The source installation's effective `override/XPLEVEL.2DA` was read on October 9:
Fighter levels 8/9 require 125,000/250,000, and Thief levels 6/10 require
20,000/160,000. The trial amounts below follow that installed table.

## Exact isolation proposed for approval

Use a new disposable test folder, for example
`%USERPROFILE%/CEBG-Tests/Banking-20261009/game`, copied from the existing default
EET installation only after its source is confirmed and copying is approved.
Do not reinstall the collection. Exclude saves, multiplayer saves, cache and
temporary data. Give the test copy its own engine user directory so new saves,
autosaves and settings cannot write into the ongoing campaign's user directory.
Verify those resolved paths before launch. Do not alter the source installation.

If an existing disposable installation has the same reviewed default setup,
prefer it once Christopher identifies/approves it. Folder names alone are not
permission to overwrite an old test or assume that it is disposable.

Before launching, record original test-folder files, stage the six candidate
DLLs and Lua sources, copy `resources/CBMDOLD.menu` to that test's override, and
copy the bundle into `cbm-bank-trial/` beneath that test game and copy the supplied
`resources/M_CBMBNK.lua` into its override. It calls `bank_bootstrap.Install`
with explicit research-only paths and `policy="bg1_sod"`. Start the loader with
the disposable game as its working directory. Installation occurs during initial EEex
startup, before actors load. No hot-loading into an existing session.

## Short trial, stop at the first real defect

1. Start a new test-only game. Confirm the normal UI loads, select a character,
   and call `CBMBank_Status()` through the cheat console. No existing save is
   needed. Confirm unaffected characters can open/cancel normal level-up.
2. On a single-class character, cross 161,000 using one real XP award. Check
   usable/banked totals, one cap notice, native manual leveling, then save and
   reload the new test save. Repeat one award on a multiclass character to
   check its shared cap; do not repeat the whole award-path matrix offline.
3. Use a test Fighter 8 with 300,000 earned XP in BG1: 161,000 usable and
   139,000 banked. Dual immediately to Thief. The old entitlement remains
   300,000; the Thief starts at level one. Earn another 20,000 for the Thief;
   it is banked while BG1 has no remaining room. Do not use a zero-bank dual:
   its between-threshold debit rule is still awaiting Christopher's choice.
4. Use the test-only campaign fixture to open SoD's cap. The old 300,000 and
   new 20,000 become usable. With the default tables, Fighter 9 and Thief 6 are
   due. Open the ordinary level-up button, inspect old-class choices, Cancel,
   and reopen. Cancel must retain XP and restore actor values; reopening must
   reuse the HP roll. Continue/commit once. The Fighter remains dormant.
5. Earn enough new-class XP for Thief 10 (160,000 in the default table). Commit through the ordinary screen.
   Confirm native reactivation, proficiencies/abilities and HP exactly once.
   Save/reload this new test save, then verify another ordinary level-up still
   works. Add one small high-level test actor only if this main path succeeds;
   check an old HLA stays unavailable while dormant and appears once on
   reactivation. No long campaign playthrough or broad kit matrix is required.

The trial fixture changes only new disposable actors/campaign state. It must
use actual native award and UI paths; a Lua arithmetic result cannot substitute
for the observed character sheet, Cancel/Continue, save/load and reactivation.
Record concise before/after evidence and the exact candidate hash manifest.

## Deliberately deferred

Existing-save repair and universal release/uninstall migration are not part of
this trial. Removing the bridge/EEex is not a safe way to recover an old-class
bank. Arbitrary external class/kit rewrites, direct memory XP writers, unusual
save transports and additional UI/mod combinations can receive later focused
fixes if a real report requires them. Native ABI, owner/lifetime and transaction
guards remain because their failure could corrupt a character or lose XP.

The no-bank dual edge does not block the single/multiclass or banked-dual trial.
It does prevent calling this prototype a generally installable public component.
The source now exposes experimental 650/651 with normal mod-directory startup;
this earlier private bundle is retained separately. No public release or
collection defaults changed.
