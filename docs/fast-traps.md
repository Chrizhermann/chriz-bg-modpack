# Fast Traps (`cbm_fast_traps`)

Component **690** (`cbm_fast_traps`) integrates *Chriz Fast Traps* directly into `chriz-bg-modpack`.

While **Find Traps** is active, the game checks doors, containers, and floor trap regions about once per second (**15 AI ticks**, following game speed) instead of once every **100 AI ticks** (~6.67 seconds).

Only active trap checks change: **Detect Illusion** on creatures, **passive secret-door searches**, skill thresholds, detection range, line of sight, incapacitation checks, and **Time Stop** keep their native engine rules.

---

## Requirements and Support Matrix

- **Target engines:** Windows x64 **2.7.3.0** builds of **BG:EE (including Siege of Dragonspear)**, **BG2:EE**, **EET**, and **IWD:EE**.
- **EEex:** Requires **EEex v1.2.0 or v1.3.1** (launch through `InfinityLoader.exe`). LuaJIT mode is optional.
- **No `GAME_IS` gate:** The component works in standalone **BG:EE**, **SoD**, **BG2:EE**, **EET**, and **IWD:EE** installs.
- **Installer behavior (`We Overwrite`):** If `override/M___EEex.lua` is present, component `690` copies `chriz-bg-modpack/fast-traps/m_czft.lua` to `override/M_CZFT.lua`, overwriting any prior copy regardless of source (`0.1.0`/`0.2.0` standalone or hand edits). If `override/M___EEex.lua` is absent, WeiDU logs one notice and skips writing `M_CZFT.lua` without failing the install; install EEex first and reinstall component `690` to activate it.

Checked from local executables and EEex builds (binary + API audit on 2026-11-08):

| Game `2.7.3.0` | EEex v1.2.0 | EEex v1.3.1 | In-game evidence |
|---|---|---|---|
| **BG:EE / SoD** | Bytes + APIs verified | Bytes + APIs verified | Pending |
| **BG2:EE** | Bytes + APIs verified | Bytes + APIs verified | Pending |
| **EET** | Bytes + APIs verified | Bytes + APIs verified | Pending |
| **IWD:EE** | Bytes + APIs verified | Bytes + APIs verified | Prototype (`0.1.0`) live-tested on `v1.3.1` + LuaJIT; `0.2.0` live pass pending |

---

## Runtime Safety & Failure-Closed Design

At startup (`EEex_GameState_AddInitializedListener`), `override/M_CZFT.lua`:

1. Confirms `EEex_Active` and verifies all **11** required EEex/InfinityLoader API functions exist in `_G`.
2. Reads executable PE headers and verifies the Windows x64 `2.7.3.0` build identity (`TimeDateStamp` + `SizeOfImage`):
   - **BG:EE / SoD (`Baldur.exe`):** timestamp `0x6A18D6DC`, image size `0x3524000` (`CGameSprite::CheckModal` at RVA `0x38CF00`)
   - **BG2:EE / EET (`Baldur.exe`):** timestamp `0x6A18D73D`, image size `0x3532000` (`CheckModal` at RVA `0x38CF00`)
   - **IWD:EE (`icewind.exe`):** timestamp `0x6A18D7E9`, image size `0x3563000` (`CheckModal` at RVA `0x38CF30`)
3. Locates `CGameSprite::CheckModal` by unique unsigned modulo-100 pattern (`CheckModal + 0x23`), verifies all nine guard byte sequences (`0x0`, `0x58`, `0x64`, `0x11C`, `0x308`, `0xF2C`, `0xF32`, `0x16FB`, `0x1DFB`), and resolves the RIP-relative door type byte (`0x21`).
4. Installs three 6-byte trampolines via `EEex_JITNear` / `EEex_JITAt` after preparing all trampolines first, verifying every written `E9 rel32; NOP`, and restoring original bytes if any write fails:
   - **`+0xF2C`:** Dispatches doors (`0x21`), containers (`0x11`), and regions (`0x41`) every `15` ticks while keeping creatures (`0x31`, Detect Illusion) and other targets on modulo `100`.
   - **`+0x11C`:** Keeps passive secret-door searches on the native modulo `100` cadence.
   - **`+0x58`:** Admits extra Find Traps (`+0x3A29 == 2`) passes every `15` ticks into the native active-state/Time-Stop check (`+0x64`) while preserving the shared increment (`+0x4E4C`) only on native due passes (`+0x5E`).

If EEex is missing, an API is absent, or the executable bytes do not match, `M_CZFT.lua` logs a single status line to `chriz_fast_traps.log` (or the engine log) and leaves native engine code untouched—no mandatory loader pattern database entry that could block game startup, and no on-screen notification dialogs.

---

## Automated Verification

Covered offline in `tests/test_fast_traps.py` and in `tests/test_release_new_components.py`:

- Lua 5.2 & LuaJIT 2.1 startup, ASLR/1024-byte `EEex_ReadLString` NUL-chunk reads, guard byte mismatches, duplicate/missing/non-executable pattern rejection, rollback on injected JIT/write faults, and idempotent reloads.
- Full Keystone x64 assembly & Unicorn CPU emulation of generated trampolines across all register/flag states and target types (`118,160` execution cases).
- Real WeiDU 249.00 install, re-install overwriting existing `override/M_CZFT.lua`, missing-EEex clean no-op, and byte-exact uninstall restoration (including extracted release-ZIP acceptance tests).
- Static EEex API coverage check confirming every referenced `EEex_*` symbol is explicitly audited before hooking.
