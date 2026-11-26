# Unpaused Inventory (`699` & `700`)

**Components:**
- **`699` (`cbm_unpaused_inventory_always`)** — Unpaused inventory: always keep the game unpaused in Inventory
- **`700` (`cbm_unpaused_inventory_combat`)** — Unpaused inventory: keep the game unpaused in Inventory during combat only

**Supported engines:** `BG:EE`, `SoD`, `BG2:EE`, `EET`, `IWD:EE` (`2.7.3.0` and `2.6.6.0` fallback where matching) on Windows x64 with **EEex** (`v1.2.0` / `v1.3.1`).
Mutually exclusive components (`699` and `700`).

## What Each Option Does

### Option `699` — Always unpaused in Inventory
- Opening the Inventory screen (`CScreenInventory`) in singleplayer cancels any active pause (manual spacebar, clock button, or Auto-Pause) without displaying the `"Game Paused"` inventory banner or playing the pause sound, and resumes the world timer immediately if the world screen stopped it during the transition.
- Attempting to pause via `TogglePauseGame` while `CScreenInventory` is the active screen is suppressed.
- Closing Inventory leaves the game unpaused. Switching to another pausing screen (such as Record, Spellbook, Map, or Options) still pauses natively.

### Option `700` — Unpaused in Inventory during combat only
- **Out of combat:** 100% native Inventory pause behavior.
- **In combat:** Behaves like `699` — cancels active pause on opening Inventory, suppresses pause requests while Inventory stays open, and automatically unpauses on the next asynchronous frame if combat begins while paused inside Inventory.
- **Combat detection:** Active combat is detected when the visible area has `m_nBattleSongCounter` (`+0xFA4`) `> 0` or its secondary combat counter (`+0xFA8`) `> 0`, or when any living party member (`STATE_DEAD` clear) satisfies `See([EVILCUTOFF])`.

## Installation & Load Order

- Install anytime after **EEex** (on **EET**, in the post-`EET_end` pass).
- Choose at most one of `699` or `700`.
- Ships `override/M_CZINVU.lua` and `override/CZINVUCF.lua`. Following [We Overwrite](we-overwrite.md), preexisting versions of both files are overwritten cleanly. If `override/M___EEex.lua` is missing at install time, WeiDU logs an inactive notice and exits cleanly without failing the setup.

## Verification Scope

- Verified across local `2.7.3.0` Windows x64 executables (`BG:EE`, `BG2:EE / EET`, `IWD:EE`), synthetic PE / `EEex_PreprocessAssembly` + Keystone + Unicorn x64 execution tests across all three hook trampolines, Lua `5.2` / `LuaJIT 2.1` unit tests, extracted release-archive tests, and real WeiDU `249.00` install/overwrite/exclusivity/uninstall tests.
- Live quiet-lab gameplay verification in `BuffBot-Dev` (`BG2:EE 2.7.3.0 + EEex v1.3.1`, muted hidden-desktop runner, `tripped=false`, `max_job_audio_peak=0.0`) passed `11/11` runtime checks across component `699` (6 checks) and component `700` (5 checks), with exact `WeiDU.log` and `override/` restoration after uninstall.
