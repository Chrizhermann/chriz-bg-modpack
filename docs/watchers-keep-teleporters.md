# Watcher's Keep: Instant Teleporters (`cbm_watchers_keep_teleporters`)

Component **697** (`cbm_watchers_keep_teleporters`) removes the multi-second black-screen cutscene fade/wait stalls from Watcher's Keep teleporters while preserving every quest, item, and statue check, autosave trigger, party arrival placement, and portal audio/visual effect.

---

## How It Works

In vanilla **BG2:EE** and **EET**, every Watcher's Keep portal trigger script (`TP30*`, `ITPORTAL`, `ITFSEALB`) starts one of 36 `CUT202*` / `CUT211A` / `CUT246A` cutscene scripts that run `FadeToColor([30.0],0)` + `Wait(2)` before moving the party and `Wait(2)` + `FadeFromColor([30.0],0)` afterward (up to 5–8 seconds of black screen per portal).

Component **697** overwrites those 37 compiled scripts directly from clean authored `.BAF` sources (`We Overwrite` policy):

- **35 standard portal cutscenes (`CUT202A`–`CUT202Y`, `CUT202ZA`–`CUT202ZH`, `CUT211A`, `CUT246A`):**
  - Keep exact vanilla destination area resrefs, entry labels, `[x.y]` offsets, facings, `LeaveAreaLUAPanic*` + `LeaveAreaLUA*` for `Player1..Player6`, and `MultiPlayerSync()`.
  - Remove `FadeToColor`, `FadeFromColor`, and all `Wait(1)` / `Wait(2)` black-screen delays, leaving only a 1-tick `SmallWait(1)` sync and `CreateVisualEffectObject("ICRMPARI",Player1)` (portal visual + `M52` sound) before `EndCutSceneMode()`.
- **`CUT202Z` (first arrival on Watcher's Keep Level 3, chaining Carston's scene `cut207a`):**
  - Removes departure `FadeToColor([30.0],0)` + `Wait(2)` and replaces post-move `Wait(2)` with `SmallWait(2)` + `MultiPlayerSync()` + `CreateVisualEffectObject("ICRMPARI",Player1)` before `StartCutSceneEx("cut207a",FALSE)`, keeping Carston's Githyanki vs. Illithid opening scene intact.
- **`ITPORTAL` (`AR3001` central mirror portal to Level 2):**
  - Preserves all statue checks, Vigil Stone (`PLOT01B`) check, timers, combat-log feedback strings, `CreateVisualEffect("ICRMPAR2",[1450.1156])`, and `StartCutSceneEx("cut202q",FALSE)`, removing only the 2-second `Wait(2)` pause before firing the portal.
- **Unmodified scenes:** Watcher's Keep Spirit Warrior boardgame scripts (`SCUT*` in `AR3023`) and Odren's Knights cutscene (`CUT208A`) are left untouched.

---

## Supported Games & Load Order

- **Supported games:** **BG2:EE** and **EET** (`GAME_IS ~bg2ee eet~`). Requires no EEex.
- **Load order:** In EET, install post-`EET_end`. Overwrites any earlier `override/CUT202*.BCS`, `override/CUT211A.BCS`, `override/CUT246A.BCS`, and `override/ITPORTAL.BCS` cleanly.

---

## Verification

- Verified offline in `tests/test_watchers_keep_teleporters.py` and `tests/test_release_new_components.py`:
  - WeiDU 249.00 compile/install/`We Overwrite` mutated-override overwrite/byte-exact uninstall across BG2:EE and EET, plus clean BG:EE and IWD:EE exclusion.
  - Every compiled script decompiles with zero `FadeToColor`, zero `FadeFromColor`, and zero `Wait(` calls, while preserving exact vanilla destinations, entry labels, coordinates, facings, and `CreateVisualEffectObject("ICRMPARI",Player1)`.
- Verified live in `%BG2EE_273_ROOT%` (`BG2:EE 2.7.3.0 + EEex v1.3.1` quiet lab) with a 6-member party across `CUT202D`, `CUT202F`, `CUT202C`, and `AR3016`.
