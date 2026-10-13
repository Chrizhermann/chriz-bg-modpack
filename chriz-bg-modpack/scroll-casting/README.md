# Reader-level scroll casting — component430

Install after EEex and all item/spell changes. Launch through InfinityLoader.
The component uses the reader's relevant active caster level, or half their highest active
class level rounded down, minimum1. Dormant dual classes do not count.

Manual scroll learning and genuine fixed protection scrolls keep their normal behavior.
The installer resolves your installed spell resources, including Spell Revisions, and lists
any ambiguous abilities that it preserves. Read `CBMScroll/CBMSPOL1.json` for that report.
Reinstall430 after changing item/spell resources; startup rejects a stale policy.

The native runtime supports the audited Windows BG2EE/EET2.6.6.0 and2.7.3.0 profiles,
with supported EEex builds checked at startup. An incompatible binary or conflicting hook
produces a visible diagnostic. Do not hot-load or unload the runtime in a running session.
Use WeiDU while the game is closed for installation/removal. Prior installed files are backed
up and restored by WeiDU; item and spell resources are not rewritten.

This source package has passed offline native and synthetic installer checks. Native game
acceptance remains pending; use a disposable game/test save when testing is authorized.
No running game or existing save was modified to prepare it. The short acceptance check is
in `docs/scroll-casting.md` in this release.

`CBMScroll.dll` is built from the repository's scroll-runtime sources; `native-build.json`
records its inputs. `tools/CBMSPolicy.exe` is self-contained. Python and a compiler are not
required by players; its build record and third-party notices accompany the executable.
