# Legacy UI text compatibility

Component **640**, label `cbm_legacy_ui_strings`, is independently selectable
from **v0.2.0-alpha.8**. It supports BG2EE/EET and requires the game's `UTIL.LUA`.
EEex and Hidden Gameplay Options are not required by this component.

LeUI 4.9.1 and maintained Dragonspear UI 22.01.3 use the old global `t()` text
helper. EE 2.7 exposes `getUiString` instead. Dragonspear's `M_dui.lua` captures
`t` while it loads and wraps it for its own translations, so creating an alias
in an independently ordered `M_` loader would be too late on some load orders.

Component 640 appends a guarded adapter to the installed `UTIL.LUA`, after the
game's helper definitions and before the UI's `M_` scripts execute. If `t` is
already a function, it is preserved exactly. Otherwise a function-valued
`getUiString` becomes the alias. If neither is callable, the adapter raises a
clear error identifying component 640 and the missing helpers. It does not
guess how an unknown UI implements translations.

Install **after the selected LeUI/Dragonspear provider and before Bubb's Spell
Menu**. The optional HGO alias is harmless but is not a prerequisite. Older
games with a working `t` keep it unchanged. This component does not replace
`UI.menu`, alter skin layouts, or change gameplay. WeiDU uninstall restores
the previous `UTIL.LUA` through its normal backups.

## Evidence and scope

The source review covers LeUI 4.9.1 and Dragonspear anongit tag 22.01.3,
commit `d86bdddd0d74ebadc9ebcd40351021d6d1dadbc0`. In Dragonspear,
`content-common/all/M_dui.lua` captures and wraps `t` at lines 21–42. HGO 5.2's
installer already demonstrates a `UTIL.LUA` alias, but users must not need to
select HGO for their chosen skin to load.

Focused Lua and disposable WeiDU fixtures check old and new helpers, wrapper
load order, repeat application, unsupported missing helpers, preservation of
unrelated content, and exact uninstall. This is source and synthetic evidence;
no native game startup or complete skin acceptance pass was performed for this
release. No running installation or save was changed.
