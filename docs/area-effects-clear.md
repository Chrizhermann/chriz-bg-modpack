# Clear Lingering Room Effects on Exit (`cbm_area_effects_clear_on_leave`)

Component **698** (`cbm_area_effects_clear_on_leave`) prevents area- and room-pulsed hazard effects from lingering for a full round (or 14 seconds) after a character leaves the room or area.

---

## Problem Solved

In the Infinity Engine, room hazards such as Watcher's Keep Maze **Dead Magic** (`SPIN646`, 14s duration, re-pulsed every 14s), **Wild Magic** (`SPIN645`, 14s duration), Neera's Wild Forest/Refuge (`OH6000`/`OH6100`/`OH6200`), Vicross's anti-wild-magic field (`OHNWILDX` in `OH6400`, 7s), SoD's Dead Magic canyon (`BD0063`), and Watcher's Keep Level 2 Ice Library **Slow Freeze** (`SPIN628`/`SPIN628A` in `AR3016`, 3s) apply timed spell effects rather than true area-owned suppressions. Leaving the room via a teleporter, door, or area transition leaves the debuff active outside the hazard room—blocking spells like *Stoneskin* or causing unexpected Wild Surges after travel.

---

## How It Works

Installs `override/M_CZRMFX.lua` via EEex (`EEex v1.2.0` and `v1.3.1`, Lua 5.1 / Lua 5.2 / LuaJIT 2.1):

1. **Scoped strictly to room-pulsed hazard spells:**
   - `SPIN646` (`AR3004`, `AR3008`, `BD0063`, or dynamically observed in any modded area that pulses it)
   - `SPIN645` (`AR3005`, `AR3009`, `OH6000`, `OH6100`, `OH6200`, or dynamically observed)
   - `SPIN778` (dynamically bound to the area where it applied)
   - `OHNWILDX` (`OH6400`, or dynamically observed)
   - `SPIN628` and Spell Revisions / `chriz-bg-magic` subspell `SPIN628A` (only valid while inside `AR3016`'s Ice Library room bounded by `DOOR05`/`DOOR06` and north wall `1775 <= x <= 2375, y >= 2400`)
2. **Creature combat debuffs are never touched:** Beholder Antimagic Rays (`SPIN550B`, `SPIN992B`), Black Dragon Insect (`SPIN689D`), Sahuagin Anti-Magic Zone (`SPIN779`), Wizard Slayer miscast (`SPCL132`), Wild Surge debuffs (`SPWM128`), and Black Pits II hub suppression (`OHBANTIM`) remain untouched across area changes.
3. **Immediate removal + paused toolbar refresh:**
   - Checks active timed effects on `EEex_Opcode_AddListsResolvedListener` as well as on visible-area transitions (`WORLD_ACTIONBAR` open and `EEex_Actionbar_AddButtonsUpdatedListener`), so stale effects clear on frame 0 even under **Auto-Pause: Area Load**.
   - Removes each out-of-zone resource via `EEex_GameObject_ApplyEffect` with opcode `321` (`immediateResolve = 1`, `noSave = 1`) and refreshes the actionbar when Dead Magic / miscast is cleared from an active party member so *Cast Spell* becomes usable immediately.

---

## Supported Games & Load Order

- **Supported games:** **BG:EE**, **SoD**, **BG2:EE**, and **EET** (`GAME_IS ~bgee bg2ee eet~`) with **EEex `v1.2.0` or `v1.3.1`**.
- **Load order:** Install after EEex (in EET, in the post-`EET_end` pass). Overwrites any prior `override/M_CZRMFX.lua` cleanly; if `override/M___EEex.lua` is absent, logs one inactive notice without failing.

---

## Verification

- Covered offline in `tests/test_area_effects_clear_on_leave.py` and `tests/test_release_new_components.py`:
  - WeiDU 249.00 install, `We Overwrite` mutated-override overwrite, missing-EEex clean no-op, IWD:EE exclusion, extracted release-ZIP acceptance, and byte-exact uninstall across BG:EE, BG2:EE, and EET.
  - Multi-runtime Lua (`lua51`, `lua52`, `luajit21`) coverage for `AR3004`/`AR3008`/`BD0063`, `AR3005`/`OH6000`, `OH6400`, `AR3016` Ice Library boundaries (`SPIN628` + `SPIN628A`), custom modded areas, save-reload resets, paused arrival sweeps + toolbar refresh, and preservation of enemy rays (`SPIN992B`, `SPIN550B`, `SPIN779`).
- Verified live in `%BG2EE_273_ROOT%` (`BG2:EE 2.7.3.0 + EEex v1.3.1` quiet lab) across `AR3004 -> AR3006` (including immediate `SPWI408` *Stoneskin* cast), `AR3005 -> AR3003`, `AR3016` Ice Library exit, and `SPIN992B` preservation.
