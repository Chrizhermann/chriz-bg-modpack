# October 7 owner release — v0.2.0-alpha.9

Worktree: `modpack-release-alpha6/chriz-bg-modpack`, branch
`codex/baeloth-known-spells`, starting commit `3d3381f`.

## Included and integration contract

- **235**, `cbm_baeloth_spellbook`: standard Sorcerer spells-known allowances,
  with SR and non-SR choices. Optional planned Challenge choice, **not an
  unconditional default**. Install after all NPC spellbook writers, particularly
  SR **60** when selected, and after EET finalization.
- **236**, `cbm_edwin_redwizard`: only with selected Artisan NPC **5102**.
  Removable no-slot `MISC89`/`MISC89_`, remove source-less inherited +2 slot
  effects on Red Wizard Edwin templates, and generate the missing +1 kit grant
  (native specialist +1 plus kit +1 gives the promised +2 total). Covers the
  EET `EDWIN7_` Conjurer template missed by the provider; preserves other chosen
  kits/classes and unrelated effects. No new kit balance.
- Order: **SR main 0 → Artisan NPC 5102 → Modpack 236 → SR 60**. The public
  guard refuses an already-installed SR 60. Do not move its original Artisan
  forbidden-spell removals after the final NPC spellbook pass.
- Both components change recruitment resources, not already saved companions.
  Existing alpha.8 components/default choices remain unchanged, including
  Evandra **224/225**. Collection pins and default integration are separate.

## Verification

- Full TP2 and all TPA libraries parse with pinned WeiDU 249.
- Focused 235/236, public-surface and release-builder checks: **63 passed**,
  including **18** new Edwin installer tests and **35** Baeloth tests.
- Full suite: **967 passed, 2 skipped**, exit 0, 189.85 seconds. Skips are the
  optional installed-source Safana and companion-continuity checks; no live
  game was supplied. This run includes extracted-release ZIP tests using its
  bundled WeiDU, with both new public entry points exercised.
- Tests cover indexed/reordered CRE V1/V2 effects and inventory; unrelated
  preservation; missing provider/wrong-order skips; malformed-data rollback;
  private/foreign resource collisions; repeated application; exact uninstall.
- Windows LuaJIT/Unicorn print handled native-exception diagnostics while
  running existing negative/emulation tests. The process completed normally;
  pytest's final result and saved status both confirm exit 0.
- Release built twice byte-identically. Explicit allowlist contains runtime,
  public docs and pinned WeiDU only, no private captures/adapters/test output.
  SHA256: `0439559cdd3e73d3dc2d5c3b079fa42bc412c5e791be5b265a212f5fb36abf6e`.
- Independent owner review found no blockers. No live-game playtest or save
  migration is claimed. No game files were changed or game processes launched.

## Release evidence and boundaries

Version markers, README, changelog, component guides, release allowlist and both
CI workflows are synchronized to alpha.9. Cleanup/security review found no
debug artifacts, secrets, network/auth changes or new runtime dependencies.
Bounds checks and collision refusal protect existing resources. This is a
WeiDU/data change, not a graphical UI change; UI/a11y review is not applicable.

The owner's approved release is to the **public** remote
`Chrizhermann/chriz-bg-modpack`, not the historical private `origin` archive.
Verify tagged commit, uploaded ZIP hash and GitHub packaging workflow before
passing immutable artifact metadata to the collection lead. Do not publish a
new CEBG installer or mutate another owner repository as part of this release.

Local logs and disposable authored fixtures remain ignored under
`target/release-checks-oct07/`; local package files are under `dist/`.
The October 3 private adapter/captures remain outside this public repository.
Relevant ordering and data-format findings are recorded in component docs;
no global memory or shared skill was edited.
