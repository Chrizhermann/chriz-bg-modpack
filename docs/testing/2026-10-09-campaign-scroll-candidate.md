# Local campaign and scroll candidate, 2026-10-09

The combined source is on `codex/campaign-scroll-integration`, in the
`campaign-xp-banking/chriz-bg-modpack` worktree. Nothing has been pushed,
published, installed in a real game, copied to a new game directory, launched,
or applied to ongoing saves. The user explicitly deferred the game trial.

## Delivered source

- 237/238: independent Fade/Evandra recruitment XP catch-up, inherited from the
  common branch. Their companion conversions are separate choices.
- 430: installed-resource-aware reader-level scroll runtime, packaged native
  DLL, self-contained inventory helper and normal WeiDU installation.
- 650/651: optional BG1/SoD banking and dependent SoA cap. Immediate duals keep
  old/new XP separate, deferred old-class choices use the normal level-up entry,
  and overlapping HP uses the agreed old-class replacement.
- Banking and scroll casting share the actor destruction boundary through an
  authenticated handler chain. Banking initializes first. Neither relocates an
  arbitrary existing jump; scroll rollback restores banking's bytes.

The main checkout and collection configuration were not changed. Version and
release markers remain alpha.10; these are unreleased changes.

## Focused evidence

- Combined source: **115 passed**, no skips, including public package contents,
  both actual WeiDU installers, one combined 430/650/651 install/uninstall,
  canonical source/package hashes and banking accounting regressions.
  Log: `C:/tmp/campaign-xp-banking-20261009/work/combined-source-acceptance.log`.
- Remaining spell structural patches: **16 passed**. The obsolete fixed-level-15
  test was removed in favor of the resource-preserving full 430 installer tests.
- Shared native boundary: **24 passed**, using private mappings and compiled
  stand-in callbacks; no game code executed. Scroll startup/installer checks
  and native host/link checks also passed before integration.
- Banking's real identity-loader offer: **96 checks passed** before integration.
- Combined TP2 and all three changed action libraries parse with WeiDU 249.
  All 48 managed banking package files match source/binary hashes. Unittest
  discovery imports cleanly with the declared test dependencies.

The Windows workflow now includes both installer suites. Portable banking and
resource checks also join the normal CI selection. Workflows were edited locally;
no remote workflow was dispatched. This was not a full collection installation.

## Still pending

Unbanked duals between level thresholds await a user choice: debit exact incoming
XP, or vanilla's retired-class level threshold. The banked-dual rule is settled;
an unbanked dual exactly on a threshold works because both rules agree there.
The candidate therefore remains experimental, not a finished general-use banking
release. No existing-save migration or repair is approved.

Actual combined startup, casting, old/new level-up choices, Cancel/Continue,
reactivation, and game save/reload remain unplayed. The short user-run checks are
in [banking](../campaign-xp-banking.md#short-check-for-later) and
[scroll casting](../scroll-casting.md#short-check-for-later). No additional game
copy or launch is requested now.

The prepared research bundle at
`C:/tmp/campaign-xp-banking-20261009/candidate-bundle` has current text sources and
refreshed hashes; its six previously built native binaries are unchanged. For
normal installation, use the integrated mod package and component selections.

## October 13 update: versioned alpha.11 candidate

The integrated source is now versioned **v0.2.0-alpha.11** as an unpublished,
locally built release candidate; nothing was pushed, tagged or published. The
earlier "nothing installed / no existing-save use" statement is superseded for
banking only: on October 12 component 650 (not 651) was privately added to the
author's existing run with existing XP and levels retained by adoption. That
installation has not yet been played, so it is not gameplay acceptance. 430,
237/238 and 651 have not been installed in any real game.

The full suite was run for the first time on the integrated tree: one stale
expectation in `tests/test_scroll_runtime_policy_table.py` still treated an
opcode 326 scroll as unresolved, although the analyzer and its own tests
deliberately support that dispatch. The test now expects an ordinary scroll and
keeps unresolved coverage with a missing-child ability. A dangling reference in
the shipped scroll README now points to `docs/scroll-casting.md`.
