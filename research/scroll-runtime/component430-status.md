# Component430 delivery status — October 9, 2026

The component now installs the independent native scroll runtime instead of rewriting
item effect levels to15. The package and installer are implemented and checked offline.
**No real game was installed, copied, staged, launched, or saved. Native acceptance is pending.**

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

Startup binds the loaded modules, installs177/conditional/persistence/action/dispatch/cast
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
`d1597335f01621e709baa6eaf7957d500c330e12d59f5cf16614c2b6ffc951b1`.
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
opaque and disables affected new overrides with a visible error. General process-failure
recovery and arbitrary new queue transports are not promised. Normal native queues are
not made newly persistent by this component.

## Bounded validation

Latest focused results, all exit0:

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
- 28 focused EEex1.2 binding cases, alongside already tested1.3 profiles;42 action host cases;
  19 linked177 cases. Earlier selector/provider/unwind evidence remains separately recorded.

Private instruction fixtures and actual-byte emulation verify different parts from a running
engine. SEC_IMAGE views do not initialize native imports/globals and never invoke game
functions. Windows unwind checks use real RtlVirtualUnwind; the in-frame continuation uses
a body jump rather than an epilogue-recognized FF25. See Microsoft's
[x64 prolog/epilog rules](https://learn.microsoft.com/en-us/cpp/build/prolog-and-epilog).
Unchanged historical suites were not repeatedly rerun to inflate coverage.

## User-run acceptance, when authorized

Use a disposable EET installation and new test saves, launch through InfinityLoader, and
install430 after item/spell providers. Reinstall430 after changing those resources. Confirm
the startup verification message and absence of a refusal before testing.

1. Compare an active mage/divine reader, a non-caster and a dormant dual class. Check a
   visible level-dependent result and exactly one consumed scroll, including point targeting.
2. Check Sleep/Invisibility/Improved Haste and a linked/conditional delayed chain; include
   Combust/Acid Storm repeat behavior, a reflected target and an independent nested cast.
3. Learn a scroll normally and use a fixed protection scroll; verify their native behavior.
4. Save/reload with a pending delayed effect in the disposable test, then check its original
   reader attribution and continuation. Do not interpret offline serialization tests as this check.

Stop on any runtime diagnostic. Actual charge use, native UI/results, third-party loaded
detour coexistence and real save/load remain untested. No launch or staging is authorized now.
