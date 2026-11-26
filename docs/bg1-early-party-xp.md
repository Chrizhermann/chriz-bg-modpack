# BG1 Early-Party XP Boost (`cbm_bg1_early_party_xp`)

Component **695** (`cbm_bg1_early_party_xp`) encourages recruiting a full party right from the start of **Baldur's Gate 1** instead of solo-farming early quests before picking up companions.

---

## How It Works

For every party-shared XP award routed through `CInfGame::AddPartyXP` (monster kills, `AddexperienceParty`, `AddexperiencePartyGlobal`, `AddXP2DA`, locks, traps, and spell scribing) while in the **BG1** campaign:

1. **Living party size `N`:** Counts living party members (`STATE_DEAD = 0x800` clear). Solo play (`N = 1`) and dead companions receive no bonus.
2. **+70% pool bonus per additional living companion (`boostedPool = round(rawXP * (3 + 7 * N) / 10)`):** Computed on the raw party XP *before* integer division so even small early-game awards (5 XP rats, 7 XP kobolds/gibberlings, 10 XP locks/traps) scale cleanly without rounding to zero:
   - **1 (Solo):** `100.0%` per member (`1.0×` pool — unchanged vanilla)
   - **2:** `85.0%` per member (`1.7×` pool)
   - **3:** `80.0%` per member (`2.4×` pool)
   - **4:** `77.5%` per member (`3.1×` pool)
   - **5:** `76.0%` per member (`3.8×` pool)
   - **6:** `75.0%` per member (`4.5×` pool)
3. **Individual `16,000` total-XP cap:** Evaluated separately per living character:
   - `totalXP = activeXP + retiredDualXP`, counting **both** active XP (`m_baseStats.m_xp`) and the retired class's `XPLEVEL` threshold (or `CBMBank` `old.total` if higher) for **any dual-classed protagonist or companion**.
   - Each character receives `max(baseShare, min(boostedShare, 16000 - totalXP))`:
     - Characters at or above `16,000` XP receive only their normal `1/N` share (`0` bonus).
     - Characters crossing `16,000` have only the bonus clipped at `16,000` while teammates still below `16,000` continue receiving their boosted share.
     - Single-character XP (`AddXPObject`, `ChangeStat(XP)`, `BD_JOINXP` recruitment ladders) is never altered.

---

## Campaign Scope & Compatibility

- **Supported games:** Windows x64 **BG:EE** (`2.7.3.0`) and **EET** (`2.7.3.0`, plus `2.6.6.0` fallback bytes) with **EEex v1.2.0 or v1.3.1**.
- **BG1-only gating:**
  - **EET:** Active only when `m_sCurrentCampaign == "BG1"`, `ENDOFBG1 == 0`, `INTOB == 0`, and `0 <= CHAPTER <= 7`.
  - **Standalone BG:EE:** Active only when `m_sCurrentCampaign` is `""` or `"BG1"`, `ENDOFBG1 == 0`, `INTOB == 0`, `0 <= CHAPTER <= 7`, and the visible area is not Siege of Dragonspear (`BD*`), Black Pits (`OH93*`), or Tutorial (`TU00*`).
  - **IWD:EE / plain BG2:EE:** Rejected at install time (`GAME_IS ~bgee eet~`) and at runtime PE/campaign checks.
- **Coexistence with Challenge Mode (`650`–`652`):** Works standalone without `650`/`652`, and coexists seamlessly with `650`/`652` (aligning naturally with `652`'s Chapter 1–2 `16,000` XP cap without pushing artificial bonus XP above `16,000` into the bank).
- **Installer behavior (`We Overwrite`):** If `override/M___EEex.lua` exists, installs `override/M_CZXPBG.lua`, overwriting any prior copy. Without EEex, logs one notice and leaves the game untouched.

---

## Verification

- Covered offline in `tests/test_bg1_early_party_xp.py` and `tests/test_release_new_components.py`:
  - Lua 5.1 / Lua 5.2 / LuaJIT 2.1 math, rounding, remainder distribution, portrait-slot mapping with dead intermediate slots, per-character `16,000` clipping, dual-class (`old + new`) total XP for both protagonist and companions, `CBMBank.old.total` integration, and campaign/area gating.
  - Native PE/byte guard validation, real `EEex v1.3.1` `EEex_PreprocessAssembly` + Keystone x64 assembly & Unicorn CPU emulation of both trampolines and `CBM_BG1EarlyPartyXP_Plan` call contract, rollback on injected JIT/write failures, and real `2.7.3.0` / `2.6.6.0` PE binary checks (plus `IWD:EE` rejection).
  - Real WeiDU 249.00 install, `We Overwrite` reinstall, missing-EEex clean no-op, BG2:EE exclusion, extracted release-ZIP acceptance, and byte-exact uninstall restoration.
- Covered live in quiet labs (`2026-11-27`, hidden desktop, `tripped=false`, `max_job_audio_peak=0.0`, `27/27` checks passed):
  - **Standalone `BG:EE 2.7.3.0` + `EEex v1.3.1` (`6/6`):** hook installed on build `0x6A18D6DC`, empty `CAMPAIGN.2DA` (`m_sCurrentCampaign == ""`) recognized in `AR2600`, `N = 1` solo `+100`, `N = 2` `+85/+85`, `16,000` cap clips protagonist bonus while companion receives full `+170`, `ENDOFBG1=1` disables boost (`+50/+50`).
  - **`EET 2.7.3.0` + `EEex v1.3.1` (`21/21` across 3 runs):** standalone `N = 2..6` (`+85/+85`, `7 -> +6/+6`, `+80×3`, `+78/+78/+77/+77`, `+76×5`, `+75×6`), dead intermediate slot `1` exclusion (`[80, 0, 80, 80]`), `16,000` cap clipping for protagonist/companion/both, live dual-class `XPLEVEL.2DA` threshold resolution (`Fighter 5 -> Mage 1` and `Thief 4 -> Mage 1`), `AddXPObject` untouched, `ENDOFBG1=1` / `CHAPTER=8` / SoD campaign (`campaign == "SOD"`) gating, and full coexistence with Challenge Mode `650` + `652` (`chapter_caps` `CH1` `16,000` gate: `+85/+85` below cap with `0` banked; at `15,950` + `200` gives protagonist exact `100` base share -> `16,050` total, `16,000` usable, `50` banked, `0` bonus XP pushed to bank, companion `+170`).
