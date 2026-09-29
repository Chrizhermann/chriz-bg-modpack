# Generic artwork for unidentified items

Component **630**, label `cbm_unidentified_appearance`, marker `CBMID.MRK`.
Available from **v0.2.0-alpha.8**. Native in-game acceptance remains pending.

## What it does

An unidentified item uses the same generic artwork as other unidentified items
in its category. For example, unidentified rings share a ring icon. Cursed items
are included. An identified copy keeps its real artwork, even when another copy
of that same item remains unidentified.

The component replaces inventory, ground and item-description artwork at display
time. Native inventory/dragging/quick-item paths and the engine's item-to-Lua
conversion are covered; no `UI.menu` replacement is installed. The default EET UI
is the acceptance target. UIs using the same engine item fields may work without
an adaptation, but are not separately certified.

It does **not** change names, descriptions, prices, item abilities, curses,
resrefs or saved-item data. It is an artwork-hiding option, not an attempt to
remove every possible clue about an item. It does not change creature equipment
animations. Game type categories are sometimes broad: swords share one category,
as does armor. Unknown/custom categories get neutral artwork rather than leaking
their unique image.

## Requirements and installation

- Windows BG2EE/EET and EEex / InfinityLoader. The initial native-code audit used
  BG2EE **2.7.3.0**, EEex **1.2.0**, and the CEBG default EET setup. Other executable
  layouts are not promised: missing/ambiguous signatures are rejected.
- Close the game, install after EEex and item/artwork mods, and launch through
  `InfinityLoader.exe`. No need to install Randomiser.
- **Do not combine with Randomiser 570 (cursed-item appearance).** Ordinary loot
  randomization can stay installed. The future per-campaign cursed-appearance
  option must also exclude this component. CEBG integration must enforce both
  directions, not just rely on installation order.
- Selecting 630 in CEBG must turn Randomiser 570 off. Collection recipe changes
  are delivered separately from this mod release.
- Existing saves are not rewritten and no new campaign state is stored. This
  is not a released CEBG hotpatch; do not overlay it onto a running installation.
  Install/uninstall with WeiDU and the game closed.

The installer reads a small donor catalog from the installed game, validates the
art resources, and writes `CBMIDCFG.lua`. Missing nonessential donors use the
neutral fallback. Invalid present donors or a missing fallback fail before any
component files are published. Mod-added items automatically inherit their type's
artwork at runtime; they do not need a list of individual resrefs.

Uninstallation restores the original loader database and any replaced component
files through normal WeiDU backups. The executable on disk, ITMs, UI.menu,
dialog.tlk, game settings and saves are never patched by this component.

## Implementation evidence

The four entries in `unidentified-items/hooks.2da` point immediately before native
`CResRef::operator=` calls. They replace only the source pointer (R8) when the item
instance's identified bit is clear. All other registers and flags are preserved.
The process-owned artwork table contains resref strings, not CItem/resource
pointers, and survives loading another game without retaining old game objects.

| Native path | Item pointer | Header source field | Purpose |
|---|---|---|---|
| CItem::GetItemIcon | RDI | 0x3A | Inventory, dragging and native quick-item callers |
| CItem::GetGroundIcon | RDI | 0x44 | Ground artwork |
| CItem::PushToLua | RBX | 0x3A | Shops, containers and other Lua item icons |
| CItem::PushToLua | RBX | 0x58 | Item-description picture |

These paths were inspected offline using the installed executable and matching
EEex function-name database. The identified bit is bit 0 at CItem+0x24, not the
ITM header flags. Item type is the unsigned word at ITM+0x1C. The single shared
ITM icon field is why permanently changing ITMs would not satisfy this feature.
Audited executable SHA-256:
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
Each catalog signature occurred exactly once in that executable.
See the [ITM format](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/itm_v1.htm)
and [WeiDU documentation](https://weidu.org/~thebigg/README-WeiDU.html).

Both installer and startup checks require every hook site. Startup also verifies
all four calls share the same copy-function target before changing any native
code. A failed hook installation restores all original call bytes. A second
bootstrap is a no-op. Runtime failure is reported, not silently called success.

## Verification and remaining acceptance

Automated checks cover Lua 5.1 and LuaJIT startup/guards/rollback, all four actual
generated x64 stubs in a CPU emulator, flags/register preservation, identified
and unidentified instances, high addresses and unknown/max item-type IDs.
Real WeiDU synthetic-game checks cover install, reinstall, exact uninstall,
prerequisite/conflict rejection and preservation of unrelated files.
These checks are not a substitute for native in-game acceptance.

September 27 verification: **228 Lua/emulated-native checks**, **21 WeiDU 249
installer checks**, and **4 public-surface checks** pass. The wider repository
run passed 612 tests initially; 37 strict file-preservation checks rejected the
unexpected debug filename produced by running a renamed WeiDU executable. With
the identical binary copied locally under its normal `weidu.exe` name, all 37
passed unchanged (649 passed across the run/recheck; 5 existing opt-in checks
remain skipped). TP2/TPA parse checks and `git diff --check` pass. No test assertion
was weakened to accommodate the runner issue. The final focused run also loads
each generated config through Lua and the production validator.

The remaining native acceptance check, when a disposable copy of the **default
setup** is available, is below. It was not an additional gate for alpha.8 and
was not performed during its release preparation. Use a copy without Randomiser
570:

1. Open the game with InfinityLoader; confirm no Lua/native initialization error.
2. Compare two different unidentified items of the same category, including a
   cursed item. Check inventory, shops, bags/containers, ground and drag cursor.
3. Inspect the description image. Identify one item: its correct original image
   should return immediately. An unidentified duplicate must remain generic.
4. Check quick slots/equipped unidentified items and ordinary identified gear.
   Confirm powers, charges, prices, names and descriptions remain normal.
5. Save/reload, switch to another save and repeat the identification check.
6. Close the game, uninstall 630, restart and confirm normal artwork is restored.

No live install or save was changed during implementation. Do not describe the
component as accepted for the default setup until this checklist passes.
