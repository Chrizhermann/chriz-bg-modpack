# Yeslick BG1 Alaghor intake — 2026-09-15

Source base: `85cbc42551ca256b167cfdb1ffc4bd3c22df85e4`, the retained combined
modpack integration. This change is its isolated successor on
`codex/yeslick-bg1-alaghor`; pin the exact commit supplied in the task handoff.
Version markers retain the alpha.5 base because this assignment does not publish
a release. The original integration worktree and dirty owner checkout are preserved.

- New optional component: **188**, label **cbm_yeslick_alaghor**.
- Selection: YeslickNPC **1** and the desired Alaghor preset. Omit for vanilla
  companions; YeslickNPC 0 is an installer skip, even if the kit exists.
- Order: relevant kit/progression providers → **188** → **199** → **EET_end**.
  Apply before Yeslick is created in a new campaign.
- Runtime scope: `YESLIC.CRE` / `YESLIC5.CRE` kit field only, with local
  KIT/CLAB/priest-dispatch validation. No new transition reset or grant script.
- Dispel: existing **410** remains unchanged and should retain its current
  collection selection/order. The existing vanilla-route/Keldorn limitation
  remains separate.

TDD recorded the missing-component failure before implementation. The focused
verification command then ran `test_yeslick_alaghor.py`,
`test_companion_continuity.py`, `test_continuity_identity.py`,
`test_public_surface.py`, `test_spell_tail.py`, `test_release_builder.py` and
`test_release_archive.py` with real WeiDU **24900**, EET's parser and a locally
built package: **53 passed, 1 skipped**. The skip was the older optional full
installed-companion source-copy test; the new focused source-copy check below ran.
The full unrelated repository suite was not rerun.

The TP2/new TPA parse checks and package build passed. A separate disposable
synthetic game used **64** copied effective Combined provider resources plus both
pre-199 Yeslick CRE backups. The installed kit resolved as `0x402b`; only the
two kit fields changed, and uninstall restored all resource bytes. No actual
installation or player save was passed to WeiDU.

The 188→199 regression verifies the converted kit, original progression,
personal spells and all remaining CRE bytes survive the identity rename. The
199 implementation and both continuity libraries, plus 410's library, are
unchanged from the source base.

No unresolved implementation choice or focused test failure remains. Fresh
recruitment, priest level-ups across 8/14/16, transition and save/reload need
native acceptance. No release, push, collection edit, live patch or saved-actor
migration was performed.

The [Yeslick guide](../yeslick-alaghor.md) separately records the unapplied
existing-save migration and targeted 410 tail-patch proposals. CEBG intake owns
the new component's selection and order, and a later release pin.
