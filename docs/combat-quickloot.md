# Disable Quick Loot in Combat (`cbm_no_combat_quickloot`)

Component **696** (`cbm_no_combat_quickloot`) completely disables the **Quick Loot** bar (`WORLD_QUICKLOOT`) while the party is in combat, requiring players to walk up to corpses and ground piles to pick up items directly during fights.

---

## How It Works

1. **Immediate suppression on combat entry:** When combat begins (`m_nCombatCounter > 0` or any living party member sees an `[EVILCUTOFF]` enemy via `See([EVILCUTOFF])`), Quick Loot closes immediately (`StopGroundItems()`, `Infinity_PopMenu('WORLD_QUICKLOOT')`, `groundItemsButtonToggle = 0`, `loot.groundItems` cleared, `mouseOverQuicklootContainer = nil`).
2. **All Quick Loot entry points blocked in combat:**
   - **Actionbar / sidebar toggle button** (`worldScreen:StartGroundItems()`), including `InfinityUI++` `RgIsModernHud` / `RgMessageboxUnlocked` `messagesRect` layout preservation so repeated clicks never shift the message box.
   - **Native Quick Loot keyboard shortcut** (`CScreenWorld::OnKeyDown`), caught via key listeners and the UI frame guard so pressing the Quick Loot hotkey in combat cannot keep `WORLD_QUICKLOOT` open.
   - **Slot clicks, mass-pick, inspection, and scrolling** (`worldScreen:OnGroundButtonClick`, `worldScreen:OnGroundScroll`, `worldScreen:GroundScrollEnabled`, `groundItemClick`, `getGroundItemProperty`, `getSlotContainerId`, `showGroundItemDescription`).
3. **Ground looting stays completely intact:** Walking to a ground pile or corpse (`WORLD_CONTAINER`, `OnContainerButtonClick`, `TakeAllFromContainer`) and picking up items at a character's feet via `INVENTORY` (`characters[id].equipment.ground0..7`) remain fully usable.
4. **Automatic post-combat restore:** If Quick Loot was toggled **on** when combat started, it automatically restores (`groundItemsButtonToggle = 1`, `StartGroundItems()`) as soon as combat ends (or as soon as `WORLD_ACTIONBAR` reopens if the player is in Inventory/Container/Dialog). If Quick Loot was **off** before combat, it stays off.
5. **Runtime toggle & Challenge Mode sync:** Controlled via `Baldur.lua` `[Challenge Mode] NoCombatQuickLoot` (default `1`) and `CZCombatQuickLoot.SetEnabled(0|1)`. When `chriz-bg-rebalance` Component `370` (`CBRCHM`) is installed, disabling Challenge Mode live in `EEex Options` automatically suspends combat Quick Loot blocking too.

---

## Support Matrix & Install Behavior

- **Supported games:** **BG:EE**, **SoD**, **BG2:EE**, **EET**, and **IWD:EE** (`2.7.3.0` target, also compatible with `2.6.6.0`).
- **EEex requirement:** Requires **EEex v1.2.0 or v1.3.1** (Lua 5.1, Lua 5.2, and LuaJIT 2.1 all supported).
- **Load order:** Install after EEex (on EET, after `EET_end` and any UI skin mod; works cleanly with vanilla UI, LeUI, Dragonspear UI++, and InfinityUI++).
- **Installer behavior (`We Overwrite`):** If `override/M___EEex.lua` is present, component `696` copies `chriz-bg-modpack/combat-quickloot/m_czql.lua` to `override/M_CZQL.lua`, overwriting any prior copy. Without EEex, WeiDU logs one notice and leaves the game untouched.

---

## Verification

- Covered offline in `tests/test_combat_quickloot.py` and `tests/test_release_new_components.py` and live in-game:
  - Lua 5.1, Lua 5.2, and LuaJIT 2.1 behavioral tests covering combat entry/exit auto-close and restore, `m_pArea.m_combatCounter` and living `[ENEMY]` sight-range detection (ignoring dead `0x800` corpses), OOC-off preservation, toggle-button blocking across vanilla/LeUI/InfinityUI++ (`messagesRect` drift guard), native hotkey simulation, slot click/mass-pick/scroll blocking, ground container preservation, save-reload reset, INI `[Challenge Mode] NoCombatQuickLoot`, `CBRCHM.IsActive()` live toggle, missing-EEex fallback, and idempotent listener/reload handling.
  - Real WeiDU `249.00` synthetic install, `We Overwrite` reinstall, missing-EEex clean no-op, extracted release-ZIP acceptance, and byte-exact uninstall restoration across `BG:EE`, `BG2:EE`, `EET`, and `IWD:EE`.
  - Live quiet-lab verification on `BuffBot-Dev` (`BG2:EE 2.7.3.0 + EEex v1.3.1`, open-floor baseline) passing OOC open, frame-1 combat suppression on hostile spawn, in-combat button toggle block, in-combat native `WORLD_QUICKLOOT` menu-push block, and automatic OOC restore on enemy removal (`BG:EE / SoD` and `IWD:EE` live passes remain separate if needed).
