# Spell Learning RAW Fix (`cbm_scroll_learn_fix`)

Component **470** (`cbm_scroll_learn_fix`) restores **Rules as Written** spell-scroll learning (`opcode 147`, `CGameEffectLearnSpell::ApplyEffect`) across **BG:EE (including Siege of Dragonspear)**, **BG2:EE**, **EET**, and **IWD:EE**.

## Why This Exists

In the vanilla Infinity Engine (`2.6.6.0` and `2.7.3.0`), `CGameEffectLearnSpell::ApplyEffect` checks only whether the character's low 16-bit kit ID equals `0x4000` (`TRUECLASS`). Every other kit falls through `CRuleTables::MapCharacterSpecializationToSchool`, which returns school `0` (None/Generalist) for everything outside the 8 vanilla wizard specialist masks (`0x0040`–`0x2000`). Because regular spell scrolls have schools `1`–`8`, non-trueclass kits suffer an unintended **−15%** scribing penalty on every scroll:

| Class / Kit | Vanilla Engine | With Component `470` (RAW) |
|---|---|---|
| **8 Specialist Mages** (Abjurer–Transmuter, single or multiclass) | +15% own school, −15% others | **+15% own school, −15% others** |
| **Custom / Multi-school Specialist Mages** (e.g., Red Wizard `0x1080`) | −15% on everything (broken school lookup) | **+15% on matching school bit(s), −15% others** |
| **Bards** (Trueclass, **Blade**, **Jester**, **Skald**, mod kits) | −15% on all school `1`–`8` scrolls (for kits) | **0% modifier** (pure `INTMOD.2DA` roll) |
| **Wild Mage** | −15% on all school `1`–`8` scrolls | **0% modifier** |
| **Trueclass Mage & Kitted Dual-Class Mages** (Kensai/Mage, Berserker/Mage, etc.) | −15% on all school `1`–`8` scrolls (for kitted duals) | **0% modifier** |

---

## Requirements and Support Matrix

- **Target engines:** Windows x64 **2.7.3.0** builds of **BG:EE (including SoD)**, **BG2:EE**, **EET**, and **IWD:EE**.
- **EEex:** Requires **EEex v1.2.0 or v1.3.1** (launch through `InfinityLoader.exe`). LuaJIT mode is optional.
- **No `GAME_IS` gate:** Installs cleanly in standalone **BG:EE**, **SoD**, **BG2:EE**, **EET**, and **IWD:EE**.
- **Installer behavior (`We Overwrite`):** If `override/M___EEex.lua` is present, component `470` copies `chriz-bg-modpack/scroll-learn/m_czsl.lua` to `override/M_CZSL.lua`, overwriting any prior file cleanly. If `override/M___EEex.lua` is absent, WeiDU logs one notice and skips writing `M_CZSL.lua` without failing the install; install EEex first and reinstall component `470` to activate it.

Checked from local executables (PE signatures, guard bytes, and offline x64 CPU emulation on 2026-11-23):

| Game `2.7.3.0` | EEex v1.2.0 / v1.3.1 | In-game evidence |
|---|---|---|
| **BG:EE / SoD** | Signatures + guard bytes verified | Pending live lab pass |
| **BG2:EE / EET** | Signatures + guard bytes verified | Pending live lab pass |
| **IWD:EE** | Signatures + guard bytes verified | Pending live lab pass |

---

## Runtime Safety & Failure-Closed Design

At startup (`EEex_GameState_AddInitializedListener`), `override/M_CZSL.lua`:

1. Confirms `EEex_Active` and verifies all **11** required EEex/InfinityLoader API functions exist in `_G`.
2. Reads executable PE headers and verifies the Windows x64 `2.7.3.0` build identity (`TimeDateStamp` + `SizeOfImage`):
   - **BG:EE / SoD (`Baldur.exe`):** timestamp `0x6A18D6DC`, image size `0x3524000`
   - **BG2:EE / EET (`Baldur.exe`):** timestamp `0x6A18D73D`, image size `0x3532000`
   - **IWD:EE (`icewind.exe`):** timestamp `0x6A18D7E9`, image size `0x3563000`
3. Locates three unique signatures (`LearnSpell`, `CGameSprite::GetKitMask`, `CGameSprite::CanWriteSpellScroll`), verifies all byte guards, and resolves and checks both `CSpell::GetSchool` and `CAIObjectType::IsUsableSubClass` (proving `m_typeAI.m_Class` at `sprite + 0x4B5B`).
4. Installs a single 6-byte `E9 rel32; NOP` trampoline at the specialist check inside `CGameEffectLearnSpell::ApplyEffect`:
   - Applies `+15` / `-15` only for arcane spell scribing (`casterType == 1`), Mage classes (`1, 7, 10, 13, 14, 17` = mask `0x00026482`), and kits carrying specialist school bits `0x0040..0x2000` (`GetKitMask & 0x3FC0 != 0`).
   - Leaves `[rsp + 0x60]` unchanged (`0%`) for all other classes/kits (Blade, Jester, Skald, mod Bards, Wild Mage, kitted dual-class Mages, non-Mage classes).

If EEex is missing, an API is absent, or any executable byte differs, `M_CZSL.lua` logs a single status line to `chriz_scroll_learn_fix.log` (or the engine log) and leaves native engine code untouched—no mandatory loader pattern database entry, and no on-screen dialog.

---

## Automated Verification

Covered offline in `tests/test_scroll_learn_fix.py` and `tests/test_release_new_components.py`:

- Lua 5.2 & LuaJIT 2.1 startup, ASLR/1024-byte `EEex_ReadLString` NUL-chunk reads, guard byte mismatches, duplicate/missing/non-executable pattern rejection, rollback on injected JIT/write faults, and idempotent reloads.
- Real Windows x64 `2.7.3.0` executable verification against local `BG:EE`, `BG2:EE`, and `IWD:EE` binaries when present.
- Keystone x64 assembly & Unicorn CPU emulation across all Mage/Bard/Fighter/Thief/Cleric/Sorcerer classes, vanilla & custom specialist masks, Blade/Jester/Skald/Wild Mage, kitted dual-classes, all spell schools `0..10`, and all `casterType` values while verifying register/stack preservation.
- Real WeiDU 249.00 `--parse-check`, install, re-install overwriting existing `override/M_CZSL.lua`, missing-EEex clean no-op, and byte-exact uninstall across `BG:EE`, `BG2:EE`, `EET`, and `IWD:EE` (including extracted release-ZIP acceptance tests).
- Static EEex API coverage check confirming every referenced `EEex_*` symbol is explicitly audited before hooking.
