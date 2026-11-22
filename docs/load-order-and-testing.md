# Detailed Load Order, Collection Choices & Testing Status

This reference preserves the detailed component-ordering rules, collection selection notes, and historical testing boundaries for **Chriz BG Modpack**.

## Collection choices

- **650 / 651 / 652** are optional, experimental, and off by default.
- **611** is the approved Chriz Easy BG default; **610** retains its smooth protagonist-XP curve as a mutually exclusive alternative.
- **224 / 225** are independent defaults when Evandra's core is selected.
- **630** requires excluding Item Randomiser's cursed-appearance option; normal loot randomization can remain.
- **640** follows LeUI / Dragonspear UI and precedes Bubb's Spell Menu; it does not depend on Hidden Gameplay Options.
- **235** stays optional as a planned Challenge choice.
- **236** is the recommended correction when Artisan's Red Wizard conversion (`5102`) is selected; it also writes the installed Red Wizard kit when explicitly selected, including templates that an earlier conversion missed.
- **190 (Sarah Archer)** is optional; when selected, it converts both Sarah ToB v8 CREs to Archer and assigns Long Bow `3`, Long Sword `1`, Short Bow `2`, Two-Handed Weapon Style `0`, Two-Weapon Style `2`. Component `191` is reserved for private collection portrait configuration and is not distributed in this repository or release.
- **225 (Evandra portrait)** uses owner-created, ChatGPT-generated artwork approved for inclusion on September 29, 2026 (`chriz-bg-modpack/portraits/evandra/rh#eval.bmp`).
- Complete Mazzy, Xan, and Fade allocations are listed in the [NPC build guide](npc-builds.md); presets replace incoming proficiencies under the [We Overwrite policy](we-overwrite.md).
- Components `192`–`198` are recommended where their NPCs and prerequisites are present. For Garrick's kit, the collection selects Artisan's Kitpack `99001` directly; his optional stat improvement (`233`) is separate.
- **220** (Yoshimo Swashbuckler) is independent; **221–223** (Hexxat options) are mutually exclusive and leave Clara unchanged (see [companion class guide](companion-classes.md)).
- **230–234** (base ability-score improvements) are independent of each other and of any class/kit choice; missing variants are logged individually without warnings (see [companion stat guide](companion-stats.md)).

## Dependencies and ordering

- Install **188** only with YeslickNPC `1`, after its kit/progression providers and before **199 / `EET_end`** and Yeslick's first creation (see [Yeslick guide](yeslick-alaghor.md)).
- Install all selected companion, content, class, and kit changes before **199**, then run **`EET_end`** and start a new BG1 campaign. Split this modpack into separate installation runs so late patches do not move continuity past finalization (see [continuity guide](companion-continuity.md)).
- Install **189** after *Safana in Amn* and the final `AR0311.BCS` writer, before her first SoA arrival. No EEex is required for `189` or `199`.
- Install **620** after EEex, `EET_end`, and every `IMOEN2.BCS` replacer, before first Spellhold recruitment (see [Imoen XP guide](imoen-spellhold-xp.md)).
- Install Fade before **110**, BG1NPC Kivan quest before **130**, and Sarah ToB v8 before **190**. Install **130** after SCS and **190** after other kit/proficiency edits.
- **160**, **170**, and **192–198** target EET resources; **170** requires the installed Eldritch Knight kit. **192** reconstructs priest memorization groups while preserving spent casts and unrelated spell types.
- When using Artisan's Kitpack with **194**, install Artisan's corrected release before `194` so the Dwarven Defender Shield Bash grant is present.
- **236** belongs immediately after Artisan NPC `5102` and before Spell Revisions' final NPC spellbook pass (`60`); **235** belongs after all such passes (see [Edwin guide](edwin-redwizard.md) and [Baeloth guide](baeloth-spellbook.md)).
- Install **220–223** after kit overhauls and companion/progression-table changes (requires a save from before the companion first appeared).
- Install **230–234** after companion content, EET's BG1 import, and other stat/class/kit conversions, before the companion first appears.
- Install **239** after NPC mods, EET's NPC transitions, and NPC customization mods (see [EET join-XP guide](eet-join-xp.md)).
- Install **400**, **410**, and **430** after the spell/item systems they refine (`430` belongs after all spell/item providers and any scroll-caster-level changes; see [scroll casting guide](scroll-casting.md)).
- Install **440** after Ascension's Improved Slayer Transformation and EE Fixpack; install **450** after the SCS shapechange-spell tweak and EE Fixpack.
- Install **460** after EET and any mod that adds or changes `PARTYAI.2DA` party AI scripts.
- Install **610** (or **611**) after EEex, `EET_end`, and other utility-XP tweaks, then launch through `InfinityLoader.exe`. Edit `override/CBMUXPC.lua` and restart to adjust anchors/multipliers/rounding for `610` (see [utility-XP guide](utility-xp.md) and [story utility XP](story-utility-xp.md)).
- Install **630** after `EET_end` and item mods, excluding Item Randomiser's cursed-appearance option (see [unidentified artwork](unidentified-items.md)).
- Install **640** after LeUI / Dragonspear UI and before Bubb's Spell Menu (see [legacy UI compatibility](legacy-ui-strings.md)).
- Install **650** after `EET_end` and companion XP options (`237`/`238`/`239`/`620`), then **651** or **652**, and launch through `InfinityLoader.exe` (see [banking guide](campaign-xp-banking.md)).
- Install **135** after mods that change Dorn's ambush cutscene `CUTDN1B.BCS` or Senjak's script (see [Dorn ambush guide](dorn-ambush-camera.md)).
- Install **660** after mods that change Degrodel's dialog (see [Degrodel guide](degrodel-fight.md)).
- Install **670** after mods that change `MAREK.CRE` / `MAREK1.CRE` (such as SCS) and before mods that read creature items (such as Item Randomiser; see [Marek guide](marek-boomerang-dagger.md)).
- Install **680** after `EET_end` and any worldmap, quest, or SoD mods (`NTotSC`, `Blackhearts`, `Aura`, `chriz-sod-remix`, `SCS`; see [EET world progression guide](eet-world-progression.md)).

## Testing status

- Automated CI runs WeiDU 249 parse-checks, generated-fixture regression suites, We Overwrite mutation tests, package reproducibility tests, and extracted-archive install/uninstall tests across synthetic BG2:EE/EET games.
- **188, 189, 199, 620:** Focused synthetic installer/runtime coverage; full campaign transitions and save/reload remain pending in combined EET playtests.
- **220–223, 230–234, 460:** Focused synthetic + extracted-archive installs against copied resources with byte-exact uninstall restoration (`460` BG1 Defensive Stance gate also verified in a disposable EET lab).
- **610:** Native smoke test covered startup, load/save, and paused-inventory scribing award in a disposable EET install.
- **650–652, 239, 135, 460 (alpha.13) & 430 + 650 (alpha.14):** Checked in-game on disposable Recommended installs (`2.7.3.0`, EEex `v1.3.1`).
- **670:** Synthetic + extracted-archive coverage plus disposable installs on copied BG:EE and EET+SCS+BG1NPC resources with byte-exact uninstall restoration.
- **680 (`v0.2.0-alpha.17`):** Standalone WeiDU parse-checks, synthetic EET install/uninstall + We Overwrite mutation tests, policy-override tests, extracted release-archive tests, and disposable smoke tests on 2.7.3.0 EET `WORLDMAP.WMP` and script files; full campaign-transition playthrough remains pending.
- Live playthrough acceptance across the entire combined collection does not follow from synthetic tests alone; see individual component guides in `docs/` for exact coverage boundaries.
