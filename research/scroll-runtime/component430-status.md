# Component430 delivery status — October 9, 2026

The component now installs the independent native scroll runtime instead of rewriting
item effect levels to15. The package and installer are implemented and checked offline.
**As of October 9 no real game was installed, copied, staged, launched, or saved.** See the
October 23 update for the first lab acceptance.

## October 23 update

The action copy/destruction host is removed. 2.7.3.0 destroys most CAIActions inline, so its
address-keyed lifetimes went stale, and the alpha.11 to alpha.13 runtime disabled itself after
a load, during a new game or when an NPC joined. Ownership now travels as a witness inside the
queued action's own `m_source` CString; see [action-witness-evidence.md](action-witness-evidence.md).
The DLL links with `/Brepro` and rebuilds byte for byte from the same source folder; sources in
another folder change the anonymous-namespace names MSVC derives from their path (287 bytes on
October 26). First in-game acceptance: a disposable
lab on 2.7.3.0, EET with Spell Revisions and EEex v1.3.1
([lab acceptance](action-witness-evidence.md#lab-acceptance)). No player game or save was used.

A review of that package found three defects, fixed the same day: a hooked entry called on
another thread could throw into the engine, a fault left already queued overrides active,
and retired witnesses grew without bound. Each entry now checks its thread first and passes
a foreign call unchanged to the native original; every reported error latches one disabled
state that every later selection consults; a process issues at most 1,048,576 witnesses, and
each scroll cast audits a fixed batch of retired ones
([design](action-witness-evidence.md#design), [review questions](action-witness-evidence.md#review-questions)).
The fixed package then passed a second lab pass: linked and conditional chains, the Combust
and Acid Storm repeats, a reflected scroll spell, fixed protection scrolls, and one forced
witness fault, after which the queued cast and every later one kept their native level
([lab acceptance](action-witness-evidence.md#lab-acceptance)).

The fault's message box had waited about 15 minutes for a scripting-object update.
`CBMS_Startup.lua` now also polls on every sprite action start, still once per process and as
a flag test, and an error inside the poll only logs. A third lab pass with that script found
the box once at the next event after a forced fault, and repeated the open cases: containers
after scroll use, with a save from an earlier installation and in a new game, the October 20
failure paths (Xan, Sarah, a new SoA game with Imoen), an area change, learning, opcode 272
and save/reload in the same and a fresh process. It also showed that an envelope kept unparsed
(loaded while overrides were off, or while 430 was uninstalled) is saved again unchanged and,
once stale, turns every override off whenever that save is loaded later
([limits](action-witness-evidence.md#limits)); October 24 narrowed this to the one actor.

## October 24 update

A well-formed envelope whose rows no longer equal the actor's decoded records, in count or bytes,
is now dropped for that actor alone: `CBMS_FinishEffectImport` returns 2 with the reason, the
loaded listener logs the actor by its creature name string, script name and EEex UUID, and the
next save writes only what that load owns for that actor. Actors in areas not loaded since, and
envelopes kept unparsed while overrides are off, are written again unchanged. The actor's effects
keep their saved levels; only spells they cast later use the native level. Malformed or
internally inconsistent data, unknown schema or fields, duplicate envelopes, conflicting origins
and ancestry gained before the import still disable every override; damage that keeps an
envelope well formed looks outdated and is dropped the same way
([persistence](persistence-edge-evidence.md)). The lab showed that a kept envelope is
outdated as soon as its actor is saved again: its op187 local-variable records are written with
the current game time, and in this install another mod rewrites its own effects after a load.
That is the normal outcome for a save made while overrides were off. Five lab processes loaded
the October 23 outdated saves healthy with one logged drop per actor, restored a current envelope
(an actor in an area the faulted process never wrote) next to two outdated ones and saved it
again, and reloaded the saves made afterwards in fresh processes without a drop
([lab acceptance](action-witness-evidence.md#lab-acceptance)).

## October 25 update

Christopher decided that 430 shows no technical notice in the game (October 23, confirmed
October 25). `CBMS_Startup.lua` now writes every fallback to the loader log only: startup
refusals, a missing EEex API, late activation, and a latched fault, which the poll still logs
once per process at the next sprite action start or scripting-object update. The first line
says that 430 is off for this session, that scrolls cast at their normal level and that saves
stay usable; the cause follows on the next line. Neither `EEex_MessageBox` nor
`Infinity_DisplayString` is called any more. A second load of the script after a successful
start used to print a refusal while the first load's overrides stayed active. It now calls the
native start once more; its single-attempt refusal runs `CBMS_DisableOverrides` before reading
any argument, and the first load's poll logs the fallback. A second load before initialization
still only refuses and leaves the first load's start alone. The DLL is unchanged;
`native-build.json` records the new Lua and header hashes. A source review the same day found
three narrow cases this release does not handle; see
[known limitations](../../docs/scroll-casting.md#known-limitations) and
[limits](action-witness-evidence.md#limits).

Five lab processes the same day tested the restored-effect reader check in normal play, with
Haste's delayed fatigue as the child spell. With Imoen as the reader, 430 stayed healthy across
area changes, Imoen leaving and rejoining the party, Imoen dismissed into no area while the party
traveled, and reloads in the same and a fresh process. A save holding a continuing Haste read by
a creature outside the party turned every override off when the fatigue came due ("original
scroll reader UUID is pending load binding"), in the same and in a fresh process, if that reader
was not loaded then: removed from the game, or left in an area the party had left. With the party
back in the reader's area first, the same save stayed healthy. This is the fourth known
limitation. The fatigue's level could not show what 430 does to a restored child: with the
overrides off the engine gave the same levels, live and after a reload. Each fault and a second
startup load wrote only the two loader-log lines; no box or in-game message appeared
([lab acceptance](action-witness-evidence.md#lab-acceptance)).

Later that day Christopher made one exception. When startup fails and its rollback cannot remove
every hook, `startup.cpp` keeps the runtime (`retained`); the new export `CBMS_StartupRetained`
reports that on the startup thread (a call on another thread reads 0 and latches the foreign
entry), and `startup_lua.cpp` exposes it as `CBMS_NativeRetained`. After its two log lines, whose
cause still says "Exit this process; do not load or save a game", `CBMS_Startup.lua` then shows
one `EEex_MessageBox` from the initialized listener, before the main menu, once per process:
"chriz-bg-modpack: scrolls at the reader's level could not start cleanly. Please quit and restart
the game before you load or save a game." The Modpack ships English only and has no translation
path for runtime Lua strings, so the text is a literal, like the earlier boxes. Every other
fallback and a second load stay log-only, and the script no longer starts without the new
binding. The startup tests force the failed removal in the stub transaction and in the real
`startup.cpp` over the real core, and the log tag is now `[CBM scroll]`. The DLL is now
`74ea73d879c906d57497eb7f3d3ec6dc4b890da5a066961ec46e596b2a29aa54`. A lab process on October 26,
started through the slot tool, showed no box at a normal start or after a second startup load
(no dialog window on the quiet runner's desktop, recorder 0), with Free Action at the reader's
level 4 before that load and at the native 1 after it
([lab acceptance](action-witness-evidence.md#lab-acceptance)).

## Behavior and package

Original readers use their relevant active caster level. Other readers use
`max(1, floor(highest active class level / 2))`; dormant dual classes do not contribute.
Installed spell type determines arcane/divine handling. Native non-caster helper spells
keep their own ability selection while carrying original scroll ownership to typed children.
Manual learning, non-scroll items, and the eight explicitly verified protection-scroll
families retain native behavior. Charges, targets, casting mode, and unrelated effects
are not rewritten. Existing saves are not repaired.

`cbm_uai_caster_level.tpa` invokes the shipped `CBMSPolicy.exe`, accepts complete inventory
or explicit per-ability review rows, and refuses malformed root inventory. The builder
uses effective override plus KEY/BIF resources, writes only its fixed installer work
directory, and requires no installed Python. WeiDU backs up/copies the DLL, three Lua
files and policy pair, then uses `APPEND_OUTER ... KEEP_CRLF` for one early
`EEex_scripts/EEex_Modules.lua` entry. This preserves the actual path and existing text;
ordinary APPEND would write an override resource instead. See the
[WeiDU action definitions](https://weidu.org/~thebigg/README-WeiDU.html#APPEND_OUTER).

Startup binds the loaded modules, installs177/conditional/persistence/dispatch/cast
groups, validates every effective resource digest, then admits item roots. Failures remove
already installed groups in reverse order; an unsafe removal retains its dependencies and
requires process exit. No game module is loaded by our code. No automatic hot unload exists.

XP banking's M_ bootstrap runs before the initialized-listener pass and already owns
`EEex::Sprite_Hook_OnDestruct`. Scroll accepts only banking's authenticated
`CBMBank_Identity.ActorDestroyChain(expectedEntry)` offer at this one boundary. It verifies
the loaded `cbmbank_identity.dll` export `CBMI_Destruct`, exact current entry and relay,
and the complete original EEex body with only the offered seven bytes reconstructed for
hashing. Scroll cleanup then calls banking's handler directly; banking retains its own
original EEex call. No existing E9 is relocated. Scroll rollback restores banking's exact
entry bytes. Other third-party jumps still refuse. This preserves bank-first startup and
banking's earlier full decoder-body preflight.

Supported audited pairings are BG2EE2.6.6.0 with pinned EEex1.3.1, and BG2EE2.7.3.0 with
the pinned EEex1.3.1 or actual default EEex1.2.0 builds. Timestamps alone are insufficient:
mapped boundaries, architecture and reviewed instruction spans must also match. Unsupported
ABI/detours refuse with a diagnostic. This is not a promise that every binary named1.2/1.3
or every third-party detour is compatible. Actual default1.2 loader DLLs supply all21
symbols imported from InfinityLoaderCommon/LuaBindingsCore/LuaProvider; see
`default-loader-imports.json`. PE inspection did not load or invoke those DLLs.

Current shipped DLL SHA256:
`88ce92e2ae3af6b07a67693eef97d88dd8c2061667bacda9196cb7b4d9b68e11`, unchanged on October 25
when only the Lua files and a header comment changed.
The package's `native-build.json` records compiled sources, headers, dependencies and assets.
The policy tool has its separate build manifest and Python/PyInstaller notices.

## Common installed chains

The read-only default Combined inventory contains 4,932 ITMs, 470 category11 scrolls and 614
use/learn ability rows: 316 typed cast candidates, 259 learning, 29 native-only, 8 genuine
fixed exceptions and 2 mixed tutorial rows. There are no root errors or unresolved graph
rows. `TTSCRL01` abilities0/1 combine learning/casting and remain native with explicit
builder diagnostics. Counts describe this installed example, not acceptance preconditions.

Sleep, Invisibility, Improved Invisibility, Shadow Door, Improved Haste, Mislead, Greater
Malison, Fire Shield, Spell Shield and the other default conditional chains resolve through
implemented native sites. Opcode326 enters the existing owned EffectFire path. Opcode272
uses its actual persistent parent and exact decoder return. Opcode232 attributes all six
native calls through the copied embedded effect and removes ownership at all four native
cleanup calls. Their generated profiles and native body captures are in this directory.

Combust (`CDIA230 → SPWI230 → SPWI230B`) repeats through326; Acid Storm
(`CDIA709 → SPWI709 → SPWI709Z`) repeats through146 mode1. Both repeating helpers are
installed type0. Their native level/ability mechanics remain unchanged and their ancestry
uses the already implemented carriers. The inventory records each repeating edge without
re-expanding its resource, continuing through all other effects and headers. No prefix or
parameter1 heuristic grants eligibility.

Actor metadata follows the actual native emitted record order and exact decoded-record
association. Pending reader UUIDs remain pending; another actor is never substituted.
An already resolved cast scalar survives reader unload. Unknown future schema is kept
opaque and disables every later override; the loader log names the cause. General
process-failure recovery and arbitrary new queue transports are not promised. Normal native
queues are not made newly persistent by this component.

## Bounded validation

October 23, with the witness package: the whole scroll suite (`tests/test_scroll_runtime_*.py`,
37 files, real WeiDU249 included) gave 814 passed and 1 skipped, the optional check that needs
unbundled local game samples; WeiDU249 parse-checks the TP2 and all 37 libraries. With the
review-fix package the same suite, now 38 files with the foreign-thread checks, gave 841 passed
and the same 1 skipped; with the late-box startup script, 847 passed and the same 1 skipped.
October 24, with the per-actor drop: 877 passed and the same 1 skipped; with the drop line naming
the actor, 879 passed and the same 1 skipped. October 25, with log-only fallbacks and the
duplicate-load disable: 885 passed and the same 1 skipped, and the TP2 and all 37 libraries
parse-check. The CI checks passed locally on Windows with the official WeiDU 249: unittest
discovery with the pinned EET fixture (237 tests; the 20 release-archive tests run separately,
3 optional installed-game checks skipped), the CI pytest list (1,037 passed, the same 1
skipped), two release builds byte for byte identical, and the 20 release-archive tests.

Latest focused results of October 9, all exit0:

- 6 real WeiDU249 install/remove checks using generated BG2EE/EET inputs and the shipped
  EXE: status0/2, resource preservation, exact restoration of prior owned files, prerequisite
  and malformed-root failures. Latest final package run: `C:/tmp/scroll-final-startup-installer.log`.
- 33 resource checks: declared layouts, SR/non-SR samples, installed types, repeating edges
  plus invalid later branches, fixed exceptions and bounded graphs. `scroll-resource-cycles.log`.
- 25 conditional native/carrier cases: all326/272/232 edges, copied ancestry, nested unowned
  masking, exact return/receiver matching, cleanup/reuse, both relocated images and transaction
  rollback. Native game functions were not called.
- 31 startup checks: compiled startup ordering/rollback and Lua51/LuaJIT bootstrap, including
  banking becoming available before the initialized callback. Together with the6 installer
  checks:37 passed in `scroll-final-startup-installer.log`. The12 persistence-host cases and
  one actual independent DLL link passed separately in `scroll-bank-chain-build-fixed.log`.
- 7 actor/save bridge checks after enforcing verified startup. `scroll-save-bridge-current.log`.
- 24 banking-chain checks: all three mapped game/EEex pairings, both known relay forms,
  changed body/entry/handler/relay refusal, direct previous-handler invocation, exact
  rollback to banking bytes and later-owner removal refusal. The invoked previous handler
  was a tiny compiled fixture DLL, not an engine function or a live banking session.
- 28 focused EEex1.2 binding cases, alongside already tested1.3 profiles; 19 linked177 cases.
  The 42 action host cases went with the host on October 23. Earlier selector/provider/unwind
  evidence remains separately recorded.

Private instruction fixtures and actual-byte emulation verify different parts from a running
engine. SEC_IMAGE views do not initialize native imports/globals and never invoke game
functions. Windows unwind checks use real RtlVirtualUnwind; the in-frame continuation uses
a body jump rather than an epilogue-recognized FF25. See Microsoft's
[x64 prolog/epilog rules](https://learn.microsoft.com/en-us/cpp/build/prolog-and-epilog).
Unchanged historical suites were not repeatedly rerun to inflate coverage.

## User-run acceptance, when authorized

Use a disposable EET installation and new test saves, launch through InfinityLoader, and
install430 after item/spell providers. Reinstall430 after changing those resources. Confirm
the startup verification line in the loader log and the absence of a fallback line before
testing.

1. Compare an active mage/divine reader, a non-caster and a dormant dual class. Check a
   visible level-dependent result and exactly one consumed scroll, including point targeting.
2. Check Sleep/Invisibility/Improved Haste and a linked/conditional delayed chain; include
   Combust/Acid Storm repeat behavior, a reflected target and an independent nested cast.
3. Learn a scroll normally and use a fixed protection scroll; verify their native behavior.
4. Save/reload with a pending delayed effect in the disposable test, then check its original
   reader attribution and continuation. Do not interpret offline serialization tests as this check.

Stop on any runtime diagnostic (in the loader log). The October 23 labs covered item1 including
point targeting, item2 except the independent nested cast, item3, and item4 with continuing
effects, a repeating opcode 272 chain and a save made while a scroll cast was queued. The
late-box package repeated the first pass's new game, NPC joins, containers, learning and
save/reload; the October 24 package repeated loading outdated and current saves, save/reload in
fresh processes, an area change and scroll levels for active casters and a cleric reading arcane
scrolls; the current package (October 25) added Haste's delayed fatigue across area changes,
party changes and save/reload. Other delayed chains across save/load, a restored child spell
whose engine level differs from the reader's, an independent nested cast, third-party detours
beyond the collection's, multiplayer and an ongoing playthrough remain untested.
