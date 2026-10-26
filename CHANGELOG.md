# Changelog

## v0.2.0-alpha.14 - 2026-10-26

Alpha.14 fixes two problems. Scrolls at the reader's level (**430**) now stay on
for the whole session. With campaign XP banking (**650**), a character's script
variables no longer go missing from saves after the bank could not take one of
that character's XP changes. Both write technical information to the loader log
only (`InfinityLoader.log` in the game folder), with one exception for 430,
described below. Collection selection is decided separately.

- **430: scrolls keep the reader's level for the whole session.** Alpha.11 to
  alpha.13 tracked the game's actions by memory address, but the game destroys
  most actions without the one destructor they watched. After a load, a new
  game, an NPC joining or opening a container, they showed "copied action
  construction overlaps an existing lifetime" or "scroll carrier born twice
  without destruction" in an EEex message box, and scrolls cast at their normal
  level until the game was restarted. A queued scroll cast now carries its
  reader in the game's own copy of the action, so no action is tracked by
  address. Checked in a lab game on BG2:EE 2.7.3.0 with EET, Spell Revisions and
  EEex v1.3.1; see the [scroll casting guide](docs/scroll-casting.md).
- **430: nothing in the game, except one box in one rare case.** When 430 turns
  itself off, at startup or later, scrolls cast at their normal level and saves
  stay usable. The loader log gets this line, with the technical cause on the
  next line: "Scrolls at the reader's level (Modpack 430) are turned off for this
  session, so scrolls cast at their normal level. Your saves stay usable." A
  problem found during play is logged the next time any creature starts an
  action. Before, an EEex message box showed it, and alpha.13 waited for a script
  event such as a creature shouting, which in a quiet scene could take minutes.
  The one box: if 430 fails to start and cannot take all of its changes back out
  of the running game, loading or saving a game in that session is not safe.
  Then the cause line in the loader log says so, and one message box appears
  while the game starts, before the main menu: "chriz-bg-modpack: scrolls at the
  reader's level could not start cleanly. Please quit and restart the game
  before you load or save a game." Saves already on disk are not affected. This
  case was never seen in a game; the offline tests force it.
- **430: saves made while it was off load cleanly.** A save made while 430 was
  turned off, or not installed, no longer turns it off when loaded. Such a save
  keeps each creature's earlier scroll data unchanged, and once the game has
  saved that creature again the data no longer matches its effects. 430 now
  drops that data for that creature only and names the creature in the loader
  log; its effects keep their levels, and spells they cast later use their
  normal level. Before, the message box showed "saved effect record count
  mismatch" or "saved effect record identity mismatch", and every scroll cast
  used its normal level until the game was restarted. Scroll data that is
  malformed, internally inconsistent or of an unknown version still turns 430
  off; damage that leaves it well formed looks outdated and is dropped the same
  way.
- **430: safer after a problem.** Once its runtime reports a problem, every
  later scroll cast uses its normal level until the game is restarted, also a
  cast queued before the problem; that one could still use the reader's level
  before. A game call on an unexpected thread is now passed to the game
  unchanged and reported the same way; before, it could crash the game. Loading
  430's startup script a second time now turns 430 off for that session, and the
  loader log says so; before, only the second load was refused, and 430 stayed
  on. One game process can queue 1,048,576 scroll casts at the reader's level,
  far more than a long session uses; later ones use their normal level, and the
  loader log says so. Its loader-log lines now start with `[CBM scroll]` instead
  of `[CBM scroll trial]`.
- **650: script variables survive saving and loading again**
  ([chriz-bg-collection#19](https://github.com/Chrizhermann/chriz-bg-collection/issues/19)).
  Up to alpha.13, an XP change through the XP effect (opcode 104) that the bank
  could not take was reported to the game as failed. The game then retried it on
  every pass and stopped processing that character's later effects, so script
  variables set behind it were missing from saves and after loading. Now no such
  change holds up the character's other effects. Checked in lab games on BG2:EE
  2.7.3.0 with EET and EEex v1.3.1, also with the release candidate's package;
  see the banking guide's [Lab checks](docs/campaign-xp-banking.md#lab-checks).
- **650: rare cases accepted for this release.** In these cases an XP change is
  not banked the normal way. Nothing about them is shown in the game; the loader
  log counts them once per loaded game. Details are in
  [Remaining limits](docs/campaign-xp-banking.md#remaining-limits).
  - If the bank fails or refuses an XP change, the game applies it the usual
    way, as without 650. The cap still applies while the character's bank
    account is in order; if the account itself is at fault, that character's XP
    is not capped.
  - While a save is written, or while another XP change of the same character is
    in progress, the change waits and is processed at that character's next
    effect update.
  - If the character's XP or the change itself changed while the bank prepared
    it, the bank tries once more, then applies it the usual way. At most 64 such
    retries wait at a time; with all 64 waiting, a further one is applied the
    usual way at once. No change waits for good.
  - Only if the bank cannot withdraw what it had already recorded does the change
    end without XP. Its amount stays in the bank's unresolved journal and is not
    added twice. That character then gets XP the usual way and is not capped,
    also after saving and loading, until resolving such journals is
    implemented.
  - If the bank sees that the character was removed or replaced while it
    prepared a change, nothing is written; when it cannot tell, the change is
    not dropped.
  - If a character is created or destroyed outside the game's main thread,
    banking switches off for the rest of the session, and later XP changes are
    applied the usual way. A change in progress for a character at that moment
    writes nothing there, and a script `ChangeStat` change is kept unapplied for
    the session and listed in the loader log. Saves made after that keep every
    character with a bank account out of banking, also after a restart, so their
    XP is not capped; `CBMBank_Status()` says so. A static check of the game's
    threads found no way for this to happen, but it cannot rule one out.
  - A script `ChangeStat` XP change the bank refuses is no longer dropped: the
    game applies it the usual way, and the next cap check caps it again. A
    refused change that sets XP to a value no longer leaves an unresolved journal
    behind.
  - An account can hold more XP than the game's per-character limit of
    4,294,967,295. When the game replaces the stored XP the usual way, the
    account is corrected to what the game stored, at the next cap check and in
    saves.
- **650: startup problems go to the loader log only.** A startup failure is no
  longer shown in the game's message log. The loader log keeps the reason, and
  `CBMBank_Status()` in the cheat console shows it.
- Build records: 650's package now records how each of its native DLLs was
  built. Each build compiles a frozen copy of the sources in a folder of its own,
  so the DLL does not depend on that folder, and each DLL carries the digest of
  its inputs and its build's identifier. A build records a DLL once, after its
  checks, and only if it can tie the DLL to itself. The package check fails when
  a source, header or build script changed since, or a DLL carries other inputs.
  `CBMScroll.dll` (430) rebuilds byte for byte from its sources, but only from
  the same folder path: the compiler derives some internal names from where the
  source files are. Its build record now says that component 430 installs it.

## v0.2.0-alpha.13 - 2026-10-20

- Add **460**: the party AI uses Defensive Stance only while **Use special
  abilities** is on. EET adds a BG1-only Defensive Stance block to the default
  party AI script `BDDEFAI` without that check, so the protagonist and other
  characters on the default script kept entering the stance with the option off
  ([Gibberlings3/EET#210](https://github.com/Gibberlings3/EET/issues/210)).
  The component reads the party AI scripts from `PARTYAI.2DA` and adds the check
  to each block that uses `SPDWD02` without it; other blocks and scripts keep
  their bytes. Existing saves use the fix after a restart. No collection
  selection changes.
- **650/651**: banking now really works; it was checked in game on EEex 1.2.0
  and v1.3.1. Alpha.11 and alpha.12 never wrote the two actor-lifetime hooks
  inside `EEex.dll`: EEex's hook writer
  cannot reach `EEex.dll` from its code pages beside the game and silently left
  the entries unchanged. Banking still started, but no character got a bank
  account, so every permanent XP award was refused: XP stayed unchanged and
  nothing was banked. The bank now places its own small relay pages beside
  `EEex.dll`, writes those two entries itself, restores the original memory
  protection, and refuses to start if any of its hooks, in the game or in
  `EEex.dll`, was not written. A startup failure leaves XP uncapped and
  unbanked as before, and is now also shown in the game's message log once per
  loaded game; `CBMBank_Status()` repeats it. XP refused under alpha.11/12 is
  not restored. A new game's main character now gets its account at its first
  cap check; until its first XP change, every cap check used to fail.
- **652** (`cbm_campaign_xp_chapters`): optional, experimental chapter-by-chapter
  XP caps across BG1, SoD, SoA, and ToB (requires **650**, mutually exclusive
  with **651**). Caps usable XP per chapter (BG1: Ch. 1-2 16k, Ch. 3 20k,
  Ch. 4 32k, Ch. 5 64k, Ch. 6 85k, Ch. 7 161k; SoD: Ch. 7 161k, Ch. 8 200k,
  Ch. 9 250k, Ch. 10 350k, Ch. 11 420k, Ch. 12-13 500k; SoA: Ch. 1/EET 13 500k,
  Ch. 2/EET 14 1,000k, Ch. 3/EET 15 2,500k, Ch. 4/EET 16 2,900k, Ch. 5/EET 17
  3,250k, Ch. 6-7/EET 18-19 3,500k; ToB: Ch. 8/EET 20 5,000k, Ch. 9/EET 21
  8,000k, Ch. 10/EET 22 8,900k), banks excess XP and releases it as chapters
  advance, and gates Baeloth's Larswood spawn (`BAINVI.BCS`) to Chapter 5+
  when `BAINVI.BCS` is present. If another mod replaced his entrance scene or
  the script is not valid, the caps still install, `BAINVI.BCS` stays
  unchanged and the installer warns. Compatible with `cdtweaks` component 2090.
- Add optional **239** for EET: EET's own SoA join-XP ladder and ToB raise for
  every joinable NPC whose scripts lack them, found from EET's campaign tables
  and NPC transitions rather than a list of NPCs. Existing catch-ups of any
  owner, SCS customization and a second installation are left unchanged. See the
  [EET join-XP guide](docs/eet-join-xp.md).
- **237/238** now recognise an existing catch-up ladder under EET's
  `TRIGGER.IDS`, where WeiDU decompiles `InParty(Myself)` as
  `IsValidForPartyDialogue(Myself)`. Before, they added their ladder even next
  to an existing one.
- Add optional **135 — Dorn's BG1 ambush: no camera lock on Senjak**. The ambush
  cutscene locked the camera on Senjak, and only a completed conversation
  released it. After a stalled conversation, leaving the area crashed the game.
  135 removes the lock from `CUTDN1B.BCS` without touching the rest of the
  scene, and adds a one-shot release to `SENJACK.BCS` once Senjak is no longer
  neutral. His hostility behavior is unchanged. Works on BG:EE and EET; already
  fixed scripts stay unchanged. See the [Dorn ambush guide](docs/dorn-ambush-camera.md).
  No collection selection changes.

## v0.2.0-alpha.12 - 2026-10-14

- Add five independent, optional companion stat components: Rasaad DEX 17/CON 16
  (**230**), Dorn CON 16 (**231**), Eldoth STR 17/CON 16/WIS 9/INT 14 (**232**),
  Garrick DEX 17/INT 15 (**233**) and Quayle CON 15 (**234**). Cover 35 named
  creature resources across BG:EE, SoD, BG2:EE and EET, including later-campaign
  appearances. Patch the variants present, in override or BIFF archives, and warn
  about missing ones without requiring a complete family.
- The selected scores are authoritative: incoming scores, class, kit, level, XP
  and HP never gate the change. Clear Eldoth's exceptional strength with STR 17.
  Stored HP, every other field and saved actors stay unchanged. Install after
  other companion stat/class/kit changes, before the companion first appears.
  No collection selection changes. See the
  [companion stat guide](docs/companion-stats.md).
- **196** (Faldorn Avenger) and **197** (Dynaheir Haste) no longer require every
  creature variant. They patch each variant that exists and name missing ones in
  installer warnings; with none present they install and change nothing. The
  class, kit and death-variable checks on patched variants are unchanged.
- Release builds package exactly the committed files. The builder refuses an
  input whose bytes differ from the commit, such as a CRLF copy from a Windows
  checkout, so a local build and the CI build of a release are byte-identical.
  Installed content is unchanged.
- All alpha.11 components remain available. No unrelated defaults changed.
  In-game acceptance of 230-234 is still pending.

## v0.2.0-alpha.11 - 2026-10-13

- Add independent **237/238** options for Fade/Evandra first-recruitment SoA
  XP catch-up, using protagonist thresholds through 1,250,000 XP. Preserve higher
  earned XP, normal leveling and unrelated companion data; complete even when
  no award is needed so rejoining cannot farm XP. Use private SoA script copies
  for new recruitment actors, preserving existing actors and ToB behavior.
  Retain recognized existing catch-up providers, including SCS customization.
- Replace **430** with reader-level scroll casting: arcane and divine scrolls use
  the reader's active caster level of that type; other legitimate readers use half
  their highest active class level, rounded down, minimum 1. Dormant dual classes
  do not count. The installer resolves the installed spells, including Spell
  Revisions, keeps scroll learning and genuine fixed protection scrolls unchanged,
  and reports ambiguous abilities it leaves alone. Windows EEex; install after all
  spell and item changes and reinstall 430 if they change later.
- Add optional, experimental **650/651**: BG1 161,000 and SoD 500,000 campaign
  caps with excess XP banked for later campaigns (651 adds a 2,950,000 SoA cap).
  Existing XP and levels are kept on adoption. Dual-classing keeps old- and
  new-class XP separate. With no bank, a dual between level thresholds counts the
  retired level's installed `XPLEVEL` threshold and drops the progress above it,
  as in vanilla: a Fighter 7 at 80,000 XP uses 64,000 of BG1's cap, leaving
  97,000. A positive bank keeps the exact pre-dual usable XP. The default
  character record's Class tab shows **Banked XP** with the usable limit and when
  the bank becomes usable; other interfaces keep the notices and the
  `CBMBank_Status()` console command. Do not remove 650 or EEex from a run with
  banked XP: uninstalling does not cash out the bank.
- The first launches in a real game (CEBG lab: game 2.7.3.0, EEex 1.2) found
  startup problems that offline checks could not show; all are fixed:
  - **430** accepts the 16-byte jump EEex really writes at its Unmarshal hook.
  - **650** accepts the call form EEex writes for its stats hooks (`40 E8`),
    writes its code bytes unsigned, hands 64-bit DLL addresses to EEex's
    assembler as numbers (the game's Lua rounded them to scientific notation in
    text), and starts once the game object exists instead of when its file
    loads. Scroll casting starts the bank first, because it chains onto the
    bank's actor hook.
  - Both now start in the lab: banking reports that it initialized and scroll
    casting verifies its native carriers. Gameplay acceptance is still pending.
- If banking cannot start, it logs why, and Imoen's Spellhold XP (620) and the
  237/238 catch-up keep their pre-650 behavior.
- Add optional **660 — Degrodel: hand over the Helm of Balduran or keep it and
  fight him**. Handing it over keeps the normal reward and ending. Refusing makes
  Degrodel stay and fight with the same servants; you keep the helm and the
  quest closes with a short journal note. No extra difficulty is added. Supports
  EET and BG:EE, with or without SCS. The installer skips with a reason, changing
  nothing, when the hand-in cannot be identified safely. See the
  [Degrodel guide](docs/degrodel-fight.md).
- No unrelated defaults changed. In-game acceptance of 237/238, 430, 650/651 and
  660 is still pending; see the component guides for the short checks.

## v0.2.0-alpha.10 - 2026-10-07

The alpha.9 tag was an unpublished release candidate. Alpha.10 includes its
companion changes and corrects Linux test-fixture log filename casing.

- Add independently selectable **235 — Baeloth: standard sorcerer spells known
  (major rebalance)** for the planned Challenge Mode. Normalize his BG1 and fresh
  SoD recruitment books against installed known-spell allowances, with Identify
  for the SR level-seven pick and Blindness without SR. Preserve daily cast
  limits, existing readiness, later level-up choices and unrelated fields.
  Install after NPC spellbook writers, including optional SR component 60.
  This is not an unconditional collection default or an existing-save repair.

- Add **236 — Edwin Red Wizard: correct spell slots and removable amulet**.
  Remove inherited bonus slots and the amulet's slot bonus; the selected kit
  supplies its promised +1 alongside the native specialist +1. Both BG2 and
  EET's BG1 amulets can be removed. Cover the EET recruitment template missed
  by Artisan's conversion, without undoing a different selected kit.
  Requires Artisan NPC 5102; install immediately after it and before SR 60.
  Existing saved actors are not rewritten.
- Generate the new slot spell from source and retain unrelated creature/item
  effects. Refuse conflicting older private slot fixes instead of stacking them.
- Keep every alpha.8 option available, with no default or balance changes to
  unrelated components. Collection defaults and download pins are separate.

## v0.2.0-alpha.8 - 2026-09-29

- Add **224 — Evandra: Sorcerer**, restoring the collection's missing class
  preference with a legal starting spellbook for Spell Revisions or vanilla.
  Keep her stored level and XP so recruitment level-ups remain available.
- Add independent **225 — Evandra: Chriz's custom portrait**, using Christopher's
  approved ChatGPT-created artwork. No save editing is required
  for actors already using Evandra's standard portrait resource name.

- Add **611 — Story-based utility XP**: BG1 rewards throughout BG1 and SoD,
  then native BG2 rewards from SoA through ToB. Include the approved EE Fixpack
  correction for BG1/SoD level-16+ locks (155 XP). Use EET campaign flags and
  handle direct starts, reloads and unsupported states without editing saves.
- Keep **610** unchanged as the smooth protagonist-XP alternative, with reciprocal
  installer exclusions. Neither mode uses party-average XP.

- Add optional **630 — Generic artwork for unidentified items**. Unidentified
  items share artwork by item category, including cursed items. Identified copies
  retain their own artwork. No item powers, descriptions, string references or
  saved items are rewritten.
- Independent of Randomiser; ordinary loot randomization remains compatible.
  Choose either this component or Randomiser's cursed-appearance option, not both.
- Windows BG2EE/EET with EEex; native game-code signatures are checked before
  installation and again at startup. Live UI acceptance is still pending.

- Add independent **640 — Legacy UI text compatibility** for LeUI and
  Dragonspear UI. Restore the old `t()` helper through `getUiString` when needed,
  before skin loaders capture it, and preserve any already-working `t()`.
  Install after the UI provider and before Bubb's Spell Menu. No HGO dependency.

- Verify the new components through focused automated and extracted-package
  installer checks. No running-game or save changes were performed for this
  release, and no full collection/live acceptance claim is made.

## v0.2.0-alpha.7 - 2026-09-19

### Fixed

- Fix component **140** rejecting different incoming Mazzy proficiencies and
  component **170** rejecting different Xan HP, levels or proficiency records.
  Explicit recruitment variants now select their authored builds. Mazzy, Xan
  and Fade replace their complete weapon/style allocations; missing, duplicate
  and previously modified proficiencies are normalized without retaining stray
  pips. Incoming XP is preserved and is not used as an identity fingerprint.
- Apply the same policy to Fade **110**, including its authored thief skills.
  Fade and Xan derive split levels from the installed XP tables without
  requiring the original source levels or exact XP values. Xan requires the
  target Eldritch Knight kit, not a particular incoming specialist kit.
  Both conversions clear former dual-class flags and remove identifiable
  previous-kit grants while preserving personal abilities and unrelated effects.
- Skie's narrow skill repair **160/195** transfers the actual Move Silently
  points to Open Locks, instead of recognizing only fixed example allocations.
  Already-transferred skills are unchanged; unrepresentable totals report the
  actual 255-point storage limit.
- Hexxat Fighter/Thief **222** replaces the full proficiency allocation using
  its existing weapon preferences and the installed point budget and caps.
- Share proficiency clearing across these presets and Sarah **190**. Remove
  increment-mode weapon records as well as ordinary pips, while preserving
  EE's repurposed spell-state fields and unrelated effects.
- Fix dispel component **410** rejecting valid casting-first effect layouts,
  including the layout produced by WeiDU's casting-effect helper. Follow actual
  indexes for all effect slices; preserve casting hooks, per-tier effects and
  Keldorn's installed scaling. Yeslick retains the intended 40-level, 1.5x
  hostile-only dispel progression, including when the input uses shared or
  differently arranged effect lists.

These changes have automated installer coverage; native gameplay acceptance
and testing against the reporter's installation remain separate.

## v0.2.0-alpha.6 - 2026-09-16

### Added

- Add optional component **188** (`cbm_yeslick_alaghor`) for the missing BG1
  Fighter/Alaghor recruitment preset. It requires YeslickNPC 1, resolves the
  installed kit and priest-level ability delivery, and preserves the entire
  build apart from the kit field. Install before 199/EET_end and actor creation.
- Respect the vanilla option and reject conflicting custom builds. Preserve
  native level-dependent grants without baking early or duplicate abilities.
- Document a bounded existing-save migration and component-410 tail-patch
  proposal. Neither was applied. Component 410 and continuity 199 are unchanged.

- Add EET actor continuity as **199** for PPG Xan v19 and Yeslick v5. Preserve
  permanent development and the original build, clear imported equipment, and
  use native later-campaign presentation. Install after companion conversions
  and before EET_end; a new game is required.
- Add Safana in Amn v0.5's one-time SoA arrival equipment cleanup as **189**.
- Add Imoen Spellhold party-average XP as **620**, capped at 3M mage XP. Install
  after EEex, EET_end and every IMOEN2.BCS replacer; independent of utility XP 610.
- Preserve public alpha.5 behavior and component numbers, including Sarah Archer
  190, conversions 192-198/220-223, and the private Sarah portrait reservation 191.
  The older unpublished continuity 190 / Safana 191 numbers must not be used.
- Windows packaging includes the WeiDU 249 executable, license/notices, SHA-256
  checksum and per-file contents manifest. Native companion recruitment,
  transition, level-up and save/reload checks remain for the full collection
  candidate; this release does not migrate existing saved actors.

## v0.2.0-alpha.5 - 2026-09-06

### Fixed

- Component `170` resolves Xan's source Enchanter kit through the canonical
  `MAGESCHOOL_ENCHANTER` symbol in installed `KIT.IDS`. The Eldritch Knight
  conversion and CRE kit encoding are unchanged.
- Component `192` accepts a stale count on Viconia's final populated priest
  memorization row when the declared ranges form an unambiguous contiguous
  prefix. It corrects that row and following empty indices to the actual table
  length, preserving every existing memorized spell and flag. Ambiguous ranges
  still fail; class, skill, proficiency, ability and spell-slot policy is unchanged.
- Authored regressions cover both observed stale-range shapes, invalid metadata,
  canonical kit symbols, install scope and byte-exact uninstall restoration.

## v0.2.0-alpha.4 - 2026-09-05

### Added

- Optional Yoshimo Swashbuckler (`220`), plus mutually exclusive Hexxat
  Shadowdancer (`221`), Fighter/Thief (`222`) and Assassin (`223`) choices.
- Installed-table thief-skill allocation and kit resolution support vanilla kits
  or Artisan revisions. Old class abilities are removed selectively; Hexxat's
  vampire powers, equipment and quest state are preserved, and Clara is untouched.
- Fighter/Thief rebuilds levels, HP, THAC0, saves, lore and proficiencies while
  retaining total XP and recruitment level-up opportunities. Extra Domination
  uses retain their original total-XP milestones.
- The public companion guide and focused installer/package acceptance tests.

### Compatibility and verification

- New choices use `220`-`223` to preserve all existing public component IDs.
  The earlier unpublished `190`-`193` draft numbers must not be used for these
  choices. No existing component was renumbered.
- Install after kit/progression changes and before the companion first appears
  in the saved world. EEex and Artisan's Kitpack are optional for these choices.
- Focused synthetic tests cover BG2EE/EET, altered kit rules, wrong/missing data,
  script scope, option exclusion, rollback and byte-exact uninstall. All four
  options also passed disposable installs against copied pristine and modded
  resources. Live recruitment remains untested; a broad live test pass is not
  a release blocker after source review.

## v0.2.0-alpha.3 - 2026-09-05

### Added

- Component `610`, progressive XP for lockpicking, trap disarming and spell
  learning in BG2EE/EET. It keeps early rewards small and approaches native BG2
  rewards using the protagonist's total XP plus a retired dual class's level
  threshold. Multiclass, triple-class and both dual directions share that scale.
- Scribing reaches 1,000 XP per spell level at 440,000 progression XP, including
  low-level catch-up spells learned by newly recruited mages and bards.
- Editable anchors, category multipliers and rounding in `CBMUXPC.lua`; settings
  apply to existing saves after a restart. Final party awards round up to 10 XP
  by default (the tested 732 XP scribing example becomes 740).
- Lua 5.1/LuaJIT regression tests and real WeiDU synthetic install/uninstall
  checks, plus component 610 acceptance from the extracted release package.

### Compatibility and verification

- Component 610 requires EEex. Install after other utility-XP tweaks and launch
  through InfinityLoader. Native XP sharing and caps remain in force.
- In a disposable EET installation, startup, load/save and an actual scribing
  award passed. The maintainer confirmed the test worked. The later rounding
  adjustment is covered by automated tests; live lock/trap awards and the full
  class matrix were not exhaustively tested.
- The native adapter preserves trailing unnamed XPBONUS padding columns and
  rejects interior gaps before writing. The included `docs/utility-xp.md` explains
  the curve, settings, sources and validation limits.
- Source filenames support Linux WeiDU, and the installer test harness supports
  Windows temporary paths containing `~`. The alpha.2 tag failed the latter
  build check and was not published as a release.

## v0.2.0-alpha.1 - 2026-09-04

First public alpha.

### Added

- NPC and collection fixes: Fade Fighter/Thief (`110`), BG1NPC Kivan quest/SCS
  guard (`130`), Mazzy proficiencies (`140`), Skie thief skills (`160`), and EET
  Xan Eldritch Knight reconciliation (`170`).
- Optional Sarah Archer conversion (`190`) with Long Bow 3, Long Sword 1, Short
  Bow 2, Two-Handed Weapon Style 0, and Two-Weapon Style 2. Omitting it leaves a
  normally installed Sarah unchanged.
- Collection-oriented NPC defaults: permanent Viconia Cleric/Thief (`192`),
  Shar-Teel Wizard Slayer (`193`), Kagain Dwarven Defender (`194`), atomic Skie
  Swashbuckler plus skill correction (`195`), Faldorn Avenger (`196`), Dynaheir
  Haste (`197`), and Kivan Archer (`198`).
- Spell and compatibility fixes: Branwen Spiritual Hammer (`400`), Yeslick and
  Keldorn Dispel Magic (`410`), Use Any Item scroll caster level (`430`),
  Ascension/EE Fixpack Slayer transformation (`440`), and SCS/EE Fixpack
  shapechange (`450`).
- Deterministic, allowlisted release packaging with an official pinned WeiDU
  249.00 AMD64 executable, recorded checksums, license text, and package contents.
- Generated-fixture and synthetic-game coverage for component behavior,
  fail-closed guards, idempotence, installer paths, and uninstall restoration.

### Compatibility and collection notes

- Xan component `170` requires Artisan's Kitpack `20000` and Artisan's NPC
  component `20002` first.
- Garrick remains an external collection selection through Artisan's component
  `99001`; no duplicate component is provided here.
- Kagain component `194` should follow Artisan's Kitpack `v1.3.1` when that mod is
  present, preserving the corrected Dwarven Defender Shield Bash grant.
- Components `440` and `450` are independently expressed compatibility patches
  intended to run after their relevant Ascension, SCS, and EE Fixpack components.

### Not included

- Component `191` and the owner's custom Sarah portrait are private/unavailable
  publicly and are not bundled.
- Components `199` and `600` are reserved or deferred and are absent rather than
  exposed as installer-time failure stubs.
- Live-game acceptance has not yet been performed; this alpha's current evidence
  is automated fixture and synthetic-game testing.
