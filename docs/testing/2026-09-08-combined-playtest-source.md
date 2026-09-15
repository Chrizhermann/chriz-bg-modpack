# Combined-playtest modpack source - 2026-09-08

This integration is a local test-source commit on `codex/combined-playtest-modpack`.
It is not a public release. VERSION, TP2 and the package manifest retain the
`v0.2.0-alpha.5` base identity; the coordinator must pin the exact Git commit
reported with this handoff, not the alpha.5 tag or an uncommitted checkout.

## Sources and preservation

- Base: public alpha.5/main `d4b1e687242ceff1f37968614d142ce90191060d`.
- Continuity/Safana: `fbacb809113ff2cf8548566d66ab64d98b9e5e5b`. Import only
  `cbm_companion_continuity.tpa`, `cbm_continuity_identity.tpa`,
  `cbm_safana_inventory.tpa`, their three focused test modules and the continuity
  guide. Merge installer/translation/documentation wiring into the current tree.
- Imoen: allowlisted dirty additions based on
  `ebdb7424d4155335c2029146c5f29c8693c93bc0`, branch
  `codex/progressive-utility-xp`. Six new files are copied exactly. TP2/TRA 620
  additions are merged; README/changelog/catalog information is adapted to the
  current public documentation instead of replacing those files wholesale.
- Every pre-existing alpha.5 runtime file and implemented TP2 component body is
  preserved. The three continuity/Safana libraries retain their source content.
  The dirty source checkout, unrelated files, installed games and saves are
  unchanged. No collection recipe/plan files were edited by this integration.

## Component mapping

| Component | Stable label | Mapping decision |
|---:|---|---|
| 189 | `cbm_safana_inventory` | New unused ID; replaces unpublished Safana 191 |
| 190 | `cbm_sarah_archer` | Preserve published ID and behavior |
| 191 | Private Sarah portrait reservation | Still absent from the public installer; do not assign Safana here |
| 192-198 | Existing companion conversions | Preserve all published IDs and behavior |
| 199 | `cbm_companion_continuity` | Allocate the unnamed reservation; replaces unpublished continuity 190 |
| 220-223 | Existing Yoshimo/Hexxat choices | Preserve all published IDs and behavior |
| 610 | `cbm_utility_xp` | Preserve published behavior; independent of 620 |
| 620 | `cbm_imoen_spellhold_xp` | New Imoen component |

The collection plan's tentative claim that 191 was free is incorrect: public
alpha.5 documents its private Sarah portrait reservation, and the private Sarah
branch defines that component. The coordinator must use Safana **189** in the
combined recipe. No public component was renumbered.

## Required installation split

1. Install selected companion/content/class/kit changes and their prerequisite
   mods, including the selected modpack companion conversions, before **199**.
   Preserve the collection's required SCS ordering.
2. Run **199** after those changes and immediately before **EET_end**. Its identity
   conversion requires a **new BG1 campaign**. Keep EET's source macros available.
3. Keep the existing late spell/XP repair stage. Run **189** after Safana in Amn
   and the final AR0311.BCS writer, before Safana's first SoA arrival.
4. Run **620** after EEex, EET_end and **every IMOEN2.BCS replacer**, before first
   Spellhold recruitment for the intended test. Component 610 is independent.

Continuity bridges audited PPG Xan v19 and Yeslick v5 actors. Native EET routes
and the other audited native mod transitions stay in place; optional Branwen is
not bridged. The legacy BG2EE-EET-FIXPACK component 200 / M_K#FP.lua stat-transfer
module conflicts with 199 and must be absent. Unexpected spawn blocks fail with
rollback, so full-stack compatibility remains for the fresh combined installation.
See [continuity](../companion-continuity.md) and [Imoen XP](../imoen-spellhold-xp.md)
for supported resources, equipment policy and acceptance cases.

## Verification on this integration

- Full `python -m pytest -q -rs tests`: **375 passed, 2 skipped**, using WeiDU
  **24900**, the inspected EET v14 parser, both Lua runtimes, a locally built
  archive and its bundled WeiDU for extracted-package acceptance.
- The two skips are the optional read-only installed companion/Safana source
  checks. They were not enabled for this focused integration run.
- WeiDU 249 parsed the TP2 and all **19** TPA libraries. The Imoen installer
  tests compile its BAF with authored IDS and install/uninstall the real script.
- Two deterministic local package builds matched SHA-256
  `bf354cc120f957315cdee5bb8ecdc6faeb1d7e6bb307168f75891350ca4c9a7c`.
  Packaging retains all previous allowlist entries and includes all new runtime
  files plus both user guides; this internal handoff is not packaged.
- Focused independent review confirmed released-runtime preservation, unique
  component/translation IDs, correct mapping, source provenance and ordering.
- No unresolved automated failure or source-integration blocker remains.

The combined fresh SR-on EET installation, full EET_end pass and native
recruitment/transition/level-up/save-reload acceptance are **not performed here**.
The coordinator owns those tests and the recipe's new 189/199/620 mapping/order.
This handoff alone does not authorize a public release or establish live acceptance.

## Imoen dirty-source capture

SHA-256 values before copying; all eleven allowlisted source files were checked
unchanged afterward. The first six are complete new-file imports. The remaining
five supplied reviewed hunks or documentation information only.

| Source-relative file | SHA-256 |
|---|---|
| `chriz-bg-modpack/baf/cbm_imoen_spellhold_xp.baf` | `fd2ab1e9fdfb17eb69924805da2709f2856b8fbf54f8787682515707d39f6f47` |
| `chriz-bg-modpack/imoen-xp/M_CBMIXP.lua` | `371a0811c14855f41dd18ede1bd4ca43bc6b9a4e502030d5ff57d6732bd73599` |
| `chriz-bg-modpack/lib/cbm_imoen_spellhold_xp.tpa` | `6aa112480831486f84081e719e609234a096583fd8a6a9945494d5d44ae5d2f0` |
| `docs/imoen-spellhold-xp.md` | `d106c503fc32a22709a5c0a0b00ca093db2293c8ee38d6ce518c2881ce21f266` |
| `tests/test_imoen_spellhold_xp.py` | `217e430a97f597bae4c4c01319973080cfac859fa7de18f401c9a5a47cdc0487` |
| `tests/test_imoen_spellhold_xp_installer.py` | `cb2ef8c292b6e68f4c7a71b7e784e36bbd449fb31bcc209b0fe6610281c10d6d` |
| `setup-chriz-bg-modpack.tp2` | `d39c0c654b8856f4f54b113f8b958dde35dedae570c6f4ba79e47c6b01c4f508` |
| `chriz-bg-modpack/languages/english/setup.tra` | `ab4b823352d51b5d4d28afd9a56dce22c3f88dbb37f97eab418077c548e820a4` |
| `README.md` | `868505d834797ca0c66c2748664fb562606a818cca7a7435479aca5ae13a8f29` |
| `CHANGELOG.md` | `83b166dc439837ded9691dde32b3b6ca3c0d7d1729bef426b33f41328ece635a` |
| `docs/component-catalog.md` | `b9bc4f581bd6a273fd289be4580c42728a456b39f93c7082ed68a89ad559299a` |
