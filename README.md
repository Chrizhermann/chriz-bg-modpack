# Chriz BG Modpack (`chriz-bg-modpack`)

First-party companion builds, EET world and companion continuity, reader-level scroll
casting, scaling utility XP, Challenge Mode XP banking, Fast Traps (`690`), and
engine/quest fixes for **Baldur's Gate II: Enhanced Edition** and **EET** (with
standalone **BG:EE**, **SoD**, and **IWD:EE `2.7.3.0`** support for `470` and
Fast Traps `690`).

**Release:** `v0.2.0-alpha.17`

**[Chriz Easy BG](https://bg.chrizfader.org/collection)** · **[Rules & Balance](https://bg.chrizfader.org/rules)** · **[Latest Release](https://github.com/Chrizhermann/chriz-bg-modpack/releases/latest)**

---

## Part 1 — For Players

*Chriz BG Modpack* collects first-party companion options, campaign-boundary fixes,
and gameplay/quality-of-life rules for **BG2:EE** and **EET**. It is one of the core
building blocks of **[Chriz Easy BG](https://bg.chrizfader.org/collection)**.

### Highlights

- **Companion builds, kits & stats:** Optional kit conversions (`190`–`198`,
  `220`–`225`), ability score tweaks (`230`–`234`), Baeloth/Edwin spellbook adjustments
  (`235`/`236`), Fade/Evandra SoA catch-up XP (`237`/`238`), EET join-XP ladder (`239`),
  and whole-actor BG1→SoA continuity for Xan and Yeslick (`199`).
- **Story-consistent EET world boundaries (`680`):** Closes cross-campaign
  backtracking exploits (`AR0020 ↔ BG4800`, `BD1000 ↔ BG0900`, `AR3000 → SoA` from
  ToB), keeps Watcher's Keep reachable in both SoA and ToB, cleans out-of-era worldmap
  icons at campaign starts, and fixes SoD chapter 8–10 camp backtracking.
- **Reader-level scroll casting (`430`, Windows EEex):** Scroll spells scale with
  the reader's caster level (or half the highest active class level when non-casters
  cast through Use Any Item).
- **Unidentified item artwork (`630`, Windows EEex):** Shows generic neutral icons
  until items are identified so drop art doesn't spoil loot.
- **Scaling utility XP (`610` / `611`, EEex):** Scales lockpicking, trap disarming,
  and spell-learning XP with progression (`611` uses BG1-sized rewards through SoD and
  native BG2 rates from SoA onward).
- **Challenge Mode XP banking & chapter caps (`650`–`652`, experimental, Windows EEex):**
  Preserves excess XP past BG1/SoD caps (`650`) with optional SoA (`651`) or
  chapter-by-chapter (`652`) progression caps.
- **Fast Traps (`690`, Windows EEex):** Speeds up active Find Traps checks on doors,
  containers, and floor traps to once per second (~15 AI ticks instead of ~6.67s)
  across **BG:EE, SoD, BG2:EE, EET, and IWD:EE `2.7.3.0`** without touching Detect
  Illusion or secret doors.
- **RAW spell-scroll learning (`470`, Windows EEex):** Restricts the ±15%
  specialist scroll-learning modifier to the 8 specialist mage schools across
  **BG:EE, SoD, BG2:EE, EET, and IWD:EE `2.7.3.0`**, removing the unintended
  −15% engine penalty from kitted Bards (Blade, Jester, Skald), Wild Mages, and
  kitted dual-class Mages while fixing custom specialist school matching.
- **Targeted quest & engine fixes:** Fixes Dorn's BG1 ambush camera lock/crash
  (`135`), repairs Ascension/SCS/EE Fixpack Slayer & Shapechange links (`440`/`450`),
  guards party AI Defensive Stance (`460`), restores legacy UI strings on EE 2.7
  (`640`), adds the Degrodel Helm fight choice (`660`), and equips Marek with a
  Boomerang Dagger +2 (`670`).

### Fast Traps (Component 690)

In vanilla Infinity Engine games, active **Find Traps** checks run only once every
100 AI ticks (~6.67 seconds at normal speed), so moving thieves often walk onto traps
or miss locked chests before the next sweep runs. Component **`690`** (`cbm_fast_traps`)
integrates *Chriz Fast Traps* directly into the modpack:

- **What changes:** Active **Find Traps** sweeps doors, containers, and floor trap
  regions every **15 AI ticks** (~1 second at normal game speed, scaling naturally with
  speed/haste).
- **What stays native:** **Detect Illusion** on creatures, passive secret-door searches,
  skill requirements, detection range, line of sight, incapacitation checks, and **Time
  Stop** keep their exact native engine timing and rules.
- **Supported games & EEex:** Targets Windows x64 `2.7.3.0` builds of **BG:EE
  (including SoD)**, **BG2:EE**, **EET**, and **IWD:EE** with **EEex `v1.2.0` or
  `v1.3.1`** (LuaJIT is optional). Overwrites any earlier standalone `override/M_CZFT.lua`
  cleanly; if EEex is missing at install time, it logs an inactive notice without
  failing the setup, and checks executable guard bytes at startup before touching memory.
- **Details:** See the [Fast Traps Guide](docs/fast-traps.md).

### Simple Install

1. Close the game and any mod manager using the game directory.
2. Download the [latest release ZIP](https://github.com/Chrizhermann/chriz-bg-modpack/releases/latest)
   and extract it into your game folder containing `chitin.key`.
3. Run `setup-chriz-bg-modpack.exe` and select only components whose upstream content
   is installed.
4. Respect the EET split order:
   - Install companion kits, conversions, stats, and continuity (`188`, `199`)
     **before `EET_end`** (with `236` directly after Artisan NPC `5102` and before
     Spell Revisions `60`).
   - Install post-`EET_end` rules and fixes (`430`, `470`, `610`/`611`, `620`, `630`,
     `650`–`652`, `680`, `690`) **after `EET_end`** (on standalone **BG:EE**, **SoD**,
     or **IWD:EE**, install `470` and `690` anytime after EEex).
5. Launch through `InfinityLoader.exe` when using EEex components.

---

## Part 2 — Component Table, Load Order & License

### Companion Builds, Continuity & Stats (`1xx`–`2xx`)

| ID | Label | Purpose |
|---:|---|---|
| `110` | `cbm_fade_ft_fix` | Complete Fade's Fighter/Thief conversion, authored build, and amulet usability |
| `130` | `cbm_kivan_quest_fix` | Protect the BG1NPC Kivan sea-elf dialogue phase from SCS combat AI |
| `135` | `cbm_dorn_ambush_camera_fix` | Stop Dorn's BG1 ambush from locking the camera on Senjak and crashing on area exit (BG:EE/EET) |
| `140` | `cbm_mazzy_prof_fix` | Replace Mazzy's proficiencies with Short Bow 4 / Short Sword 3–4 |
| `160` | `cbm_skie_skill_fix` | Move unusable Move Silently points to Open Locks after a Swashbuckler conversion |
| `170` | `cbm_xan_ek_fix` | Extend Artisan's Eldritch Knight conversion to EET Xan resources |
| `188` | `cbm_yeslick_alaghor` | Extend selected YeslickNPC Alaghor to the BG1 recruit family (before `199`/`EET_end`) |
| `189` | `cbm_safana_inventory` | Clear Safana's imported gear once at her SoA arrival |
| `190` | `cbm_sarah_archer` | Optionally convert Sarah to Archer with the selected proficiency build |
| `192` | `cbm_viconia_cleric_thief` | Permanently convert Viconia to a true-class Cleric/Thief |
| `193` | `cbm_sharteel_wizard_slayer` | Give joinable Shar-Teel variants the Wizard Slayer kit |
| `194` | `cbm_kagain_dwarven_defender` | Give Kagain the Dwarven Defender kit |
| `195` | `cbm_skie_swashbuckler` | Atomically give Skie the Swashbuckler kit and compatible thief skills |
| `196` | `cbm_faldorn_avenger` | Give Faldorn the Avenger kit |
| `197` | `cbm_dynaheir_haste` | Add the effective installed Haste spell to Dynaheir once |
| `198` | `cbm_kivan_archer` | Give joinable Kivan variants the Archer kit |
| `199` | `cbm_companion_continuity` | Preserve returning Xan and Yeslick actors across campaigns (new game, before `EET_end`) |
| `220` | `cbm_yoshimo_swashbuckler` | Give Yoshimo the installed Swashbuckler kit |
| `221` | `cbm_hexxat_shadowdancer` | Give Hexxat the installed Shadowdancer kit (choose at most one of `221`–`223`) |
| `222` | `cbm_hexxat_fighter_thief` | Convert Hexxat to Fighter/Thief with rebuilt stats and preserved vampire powers |
| `223` | `cbm_hexxat_assassin` | Give Hexxat the installed Assassin kit |
| `224` | `cbm_evandra_sorcerer` | Give Evandra a Sorcerer starting spellbook, preserving level-up choices |
| `225` | `cbm_evandra_portrait` | Use Chriz's custom Evandra portrait independently of class |
| `230` | `cbm_rasaad_stats` | Rasaad: base Dexterity 17 and Constitution 16 |
| `231` | `cbm_dorn_stats` | Dorn: base Constitution 16 |
| `232` | `cbm_eldoth_stats` | Eldoth: base Strength 17, Intelligence 14, Wisdom 9, Constitution 16 |
| `233` | `cbm_garrick_stats` | Garrick: base Dexterity 17 and Intelligence 15 |
| `234` | `cbm_quayle_stats` | Quayle: base Constitution 15 |
| `235` | `cbm_baeloth_spellbook` | Major rebalance: standard Sorcerer spells known for Baeloth (Challenge Mode option) |
| `236` | `cbm_edwin_redwizard` | Fix Red Wizard Edwin's slots and removable amulets (after Artisan `5102`, before SR `60`) |
| `237` | `cbm_fade_recruitment_xp` | Fade: one-time SoA recruitment XP catch-up, capped at 1.25M |
| `238` | `cbm_evandra_recruitment_xp` | Evandra: one-time SoA recruitment XP catch-up, capped at 1.25M |
| `239` | `cbm_eet_join_xp` | EET: write EET's SoA join-XP ladder and ToB raise for joinable NPCs |

### Spell, AI & Scroll Rules (`4xx`)

| ID | Label | Purpose |
|---:|---|---|
| `400` | `cbm_branwen_hammer_fix` | Correct Spiritual Hammer's Create Weapon quantity |
| `410` | `cbm_yeslick_keldorn_dispel_fix` | Make Yeslick/Keldorn dispels hostile-only and correctly scaled |
| `430` | `cbm_uai_caster_level` | Reader-level scroll casting (half highest active class level via UAI; Windows EEex) |
| `440` | `cbm_ascension_slayer_eefp_fix` | Repair Ascension / EE Fixpack upgraded-Slayer subspell links |
| `450` | `cbm_scs_shapechange_eefp_fix` | Repair the SCS / EE Fixpack arcane shapechange interaction |
| `460` | `cbm_defensive_stance_ai` | Party AI uses Defensive Stance only while "Use special abilities" is enabled |
| `470` | `cbm_scroll_learn_fix` | Restrict ±15% specialist scroll-learning modifier to specialist mages (BG:EE/SoD/BG2:EE/EET/IWD:EE + Windows EEex) |

### XP, UI, Items, Campaign Progression & Quests (`6xx`)

| ID | Label | Purpose |
|---:|---|---|
| `610` | `cbm_utility_xp` | Scale lock, trap, and spell-learning XP with party progression (EEex; excludes `611`) |
| `611` | `cbm_story_utility_xp` | BG1-sized utility XP through SoD, native BG2 rewards from SoA (EET + EEex; excludes `610`) |
| `620` | `cbm_imoen_spellhold_xp` | Set Spellhold Imoen to party-average XP, capped at 3M mage XP (EEex) |
| `630` | `cbm_unidentified_appearance` | Generic artwork until identification (Windows EEex) |
| `640` | `cbm_legacy_ui_strings` | Restore the legacy text helper for LeUI / Dragonspear UI on EE 2.7 |
| `650` | `cbm_campaign_xp` | Experimental: retain excess XP beyond BG1/SoD caps (EET + Windows EEex) |
| `651` | `cbm_campaign_xp_soa` | Experimental: also cap SoA at 2,950,000 XP (requires `650`; excludes `652`) |
| `652` | `cbm_campaign_xp_chapters` | Experimental: chapter-by-chapter XP caps across BG1/SoD/SoA/ToB + Baeloth Ch.5+ gate (requires `650`; excludes `651`) |
| `660` | `cbm_degrodel_fight` | Helm of Balduran hand-in: give Degrodel the helm or keep it and fight him (BG:EE/EET) |
| `670` | `cbm_marek_boomerang_dagger` | Both Marek creatures carry one Boomerang Dagger +2 in BG1 (BG:EE/EET) |
| `680` | `cbm_eet_world_progression` | Story-consistent EET campaign boundaries across BG1/SoD/SoA/ToB and SoD backtracking fixes (EET) |
| `690` | `cbm_fast_traps` | Fast Traps: check doors, containers, and floor traps every ~1s instead of ~6.7s (BG:EE/SoD/BG2:EE/EET/IWD:EE + Windows EEex) |

> Component IDs `191` and `600` are reserved and are not exposed by this release.

### Key Load Order & We Overwrite Policy

- **Pre-`EET_end` pass:** Install companion builds, class conversions (`220`–`223`), stats (`230`–`234`), `188`, and `199` continuity after upstream NPC/kit mods and before `EET_end` (`236` goes immediately after Artisan NPC `5102` and before Spell Revisions `60`; `235` after spellbook passes).
- **Post-`EET_end` pass:** Install `430` (after spell/item mods), `470` (after EEex, or standalone BG:EE/SoD/IWD:EE), `610` or `611`, `620`, `630` (excluding Item Randomiser's cursed-appearance option), `650`–`652`, `680` (after worldmap, quest, and SoD mods), and `690` (after EEex on EET, or standalone BG:EE/SoD/IWD:EE).
- **We Overwrite:** Every component writes its decided fields and behavior directly over pre-existing edits or other mods' versions of the same files ([We Overwrite Scope](docs/we-overwrite.md)). Missing optional targets and unreadable resources are logged individually without blocking remaining components; native memory signatures remain required.
- **Further Guides & CI:** See [Detailed Load Order & Testing Notes](docs/load-order-and-testing.md), [Alpha.17 Release Notes](docs/releases/v0.2.0-alpha.17.md), [Spell Learning Fix (470)](docs/scroll-learn-fix.md), [Fast Traps (690)](docs/fast-traps.md), [EET World Progression (680)](docs/eet-world-progression.md), [Scroll Casting (430)](docs/scroll-casting.md), [Campaign XP Banking (650–652)](docs/campaign-xp-banking.md), [Story Utility XP (611)](docs/story-utility-xp.md), and the other guides in `docs/`. CI runs WeiDU 249 `--parse-check`, generated fixtures, deterministic archive builds (`tools/build_release.py`), and extracted-archive install/uninstall tests.

## License

First-party source and documentation are licensed under the **[MIT License](LICENSE)** (`Copyright (c) 2026 Christopher Hermann`).

Third-party notices are documented in **[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**, covering:
- The bundled **WeiDU 249.00** executable (GNU GPL v2, shipped as `WEIDU-COPYING.txt`).
- PyInstaller / Python license notices for `CBMSPolicy.exe`.
- Evandra portrait provenance (`chriz-bg-modpack/portraits/evandra/rh#eval.bmp`) and stock game fallback artwork/data.
