# Banked XP record display source check

Component 650 presentation only. No game was installed, launched or modified.
Private resources were read in place, not copied into the repository.

The default `CHARACTER` menu's Class tab is the scrolling panel containing the
actual class XP values. The label below the portrait calls
`getNextLevelString()` and shows XP **remaining** until the next level.
The implementation extends the former, after the existing class details and
before the kit description. It retains the original callback and its complete
text, without changing the menu's geometry or class accounting.

## Source evidence

The resource line numbers below refer to the decoded `UI.MENU` text. No decoded
game resource is tracked here.

| Default UI | Resource container and locator | Getter; Class panel |
| --- | --- | --- |
| BG2 | `<BG2EE 2.6.6.0 install>/data/Patch2.bif`, via that installation's `chitin.key` | `getClassString` 385-397; scrolling text 656-663 |
| BG1 | `%USERPROFILE%/Games/Chriz Easy BG/bg1/data/PATCH20.BIF`, via `bg1/weidu_external/backup/DlcMerger/1/chitin.key` | `getClassString` 399-411; scrolling text 841-848 |
| SoD | `%USERPROFILE%/Games/Chriz Easy BG/bg1/SOD-DLC/SODUI.BIF`, via `bg1/chitin.key` | `getClassString` 425-437; scrolling text 705-712 |

All three panels use `getClassString()` and a scrollbar. This getter joins
`characters[currentID].classlevel.first/second/third.details` and `kitDesc`.
Their existing `CHARACTER.onOpen` calls `updateAttrTable()`, which already reads
the selected character. Matching is deferred until after that callback; it
does not fetch localized strings during initial menu loading. Class-tab
visibility is not required for discovery because it starts disabled.

The installed EEex 1.2 source in
`%USERPROFILE%/Games/Chriz Easy BG/game/EEex_scripts/EEex_Menu.lua` supplies
function/variant access (132-198), before/after main-file listeners (313-346),
and reload dispatch (421-438). Its `EEex_Options.lua` semantic text lookup
executes text callbacks to identify their content. The matching LuaBindings
binary exposes `uiItem::scrollbar_t.bam` as `ConstCharString`, hence `bam:get()`.
Any nonempty scrollbar resource is accepted; a fixed-height text box cannot
safely receive more lines and is left alone.

BG2EE 2.6.6 `CScreenCharacter::UpdateMainPanel` (RVA `0x2AD240`, identified by
the matching EEex function-name database) assigns the selected actor array ID
to Lua `currentID` and passes the same ID to `CGameObjectArray::GetDeny` and
`CGameSprite::UpdateLuaStats`. The display resolves this ID afresh each draw;
world selection and cached actor pointers are not used.

## Boundaries

The Lua tests use actual EEex menu helper bodies with synthetic UI objects,
plus the real banking account/runtime with synthetic actors. They cover
selection changes, shared banks, unchanged state/text, translated descriptions,
extra/reordered elements, callback ownership, reloads, and safe fallback.
They do not establish in-engine rendering, font zoom, or save/load acceptance.

Infinity UI++ and EET SoD-style source were inspected but no adapter or display
acceptance was established. Dragonspear UI++ and LeUI were not source-audited
for this feature. All alternative interfaces remain unverified.

## Validation on this worktree

The banking `tests/test_campaign_xp_*.py`, release `tests/test_release*.py`,
public-surface tests and `identity_loader_test.py` ran together with the supplied
dependency/WeiDU/EET environment: **925 passed, 1 failed**, no skipped tests.
Release acceptance used a locally built ZIP and official WeiDU 249.00.
Source/package hash parity also passed. The separate bank/scroll hook-chain
suite passed **24 tests**, using copies of its five image fixtures in owned
scratch; no game images were invoked.

The remaining failure is
`test_scroll_and_banking_publications_coexist_and_uninstall`: the existing
component 430 policy helper's PyInstaller bootstrap could not extract
`VCRUNTIME140.dll` (`fopen: Permission denied`). This happens before any banking
installation. Its empty extraction directory had a private DACL granting only
the desktop user access, unlike the sandbox-accessible parent. No helper,
validation or access-control setting was changed to bypass that restriction.
The combined 430/650/651 install/uninstall check therefore remains unverified
in this sandbox; the separate banking installer and release checks passed.
