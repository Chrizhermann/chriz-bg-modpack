# Uninstalled derived-XP cap implementation

Current integration: this cap is included in the uninstalled native candidate
assembled by `bank_bootstrap.lua`. See [DEFAULT-TRIAL.md](DEFAULT-TRIAL.md) for
the built bundle and next acceptance check. Missing-integration statements below
describe the earlier isolated cap checkpoint; they do not supersede that plan.
No game launch or native gameplay acceptance has occurred.

The native investigation found that ordinary permanent XP remains in saved base
storage while level eligibility uses a capped derived value. `cap_hook.lua`
implements the missing scoped cap callback at the reviewed CheckStatsChange
boundary. It is not automatically loaded, referenced by a TP2, or installed.

## Actual behavior

`BeforeNativeClamp` reads a committed actor snapshot through an explicit provider,
then owns only `sprite.m_derivedStats.m_nXP`. It caps that value before the native
single/multi/dual cap branch and before GetNextLevel. It never writes base XP,
bank state, class levels, items or effects. Ordinary campaign release therefore
requires a derived-stat refresh under the new saved phase, not a new XP award.

For a dual with a protected old-class balance, the available active-class XP is
bounded by the shared limit minus the old-class released entitlement. This may
be greater than the native retired-level threshold. Clamping derived active XP
first also avoids overflow in the native active-plus-retired 32-bit addition.
It does not prevent overflow when native base XP itself receives another award.

The provider must supply verified eligibility, a save-owned policy/phase,
the preserved adoption floor, class accounting, and—for duals—the committed
old entitlement plus the current installed retired-level threshold. It must be
a read-only lookup of already initialized state. It must not infer old history
from the reset base-XP field, refresh mutable state during export, or use names,
portrait slots or copied actor IDs as ownership evidence.

Unknown/malformed snapshots are reported and leave this callback's XP untouched.
The underlying engine then continues its existing native behavior. This error
route preserves data but **does not keep the promised campaign cap active**;
the complete component must detect and surface unsupported actors/configuration.
It cannot treat a logged provider failure as successful banking.

## Native binding

`cap-loader-patterns.txt` contains new labels. The shared signature was matched
once in each inspected executable. Its signed relative-call target resolves to
the mapped GetXPCap function. The pattern operation grammar was checked against
InfinityLoader's `handlePatternOperations` and existing relative-call labels.

The generated shim preserves GetXPCap's RAX through both Lua success and failure.
EEex's argument generator captures the two arguments before making calls and
restores RBX; standard native nonvolatile registers remain preserved. The saved
RAX at stack offset 88 does not overlap the generator's locals/arguments through
offset 79. This is a source review, not execution of the generated shim.

Install first validates the required capabilities, callback ownership, call
target and surrounding instructions. A failed patch attempt restores the five
owned call-site bytes and removes the callback. No runtime install was attempted.
The two reviewed builds are identified by hashes in `cap-check-results.json`.

## Executed checks

- `tests/test_campaign_xp_banking_cap.py`: 50 passed across Lua 5.1/LuaJIT.
- `check_cap.py`: 734 native-window executions, 367 per executable.
- Four independent unhooked controls per executable force native writes for
  single, multiclass, dual and exhausted retired-class allowance.
- Hooked cases cover all four campaigns, both policies, single/multi/dual,
  retained native ceilings, over-cap adoption and near-uint32 inputs.
- Tests assert the exact end instruction and class-helper call count. Native
  writes are limited to stack and the derived-XP word; base and unrelated actor
  memory remain unchanged.

The class helpers are fixture providers; the native clamp instructions are the
actual executable bytes. These tests do not execute the EEex/Lua bridge, native
level-up screen, real marshal path, party lifecycle or ordinary reward dispatch.
The separate opcode-104 observer has its own 30 instruction tests.

Integration review caught an incorrect Lua member name: generated
`CDerivedStatsTemplate` exposes `m_nXP`, whereas the base creature header exposes
`m_xp`. The original callback test repeated that mistake. A strict native-member
proxy reproduced the failure on both Lua runtimes before the fix; the corrected
callback writes only the derived member and leaves base XP unchanged. The member
was checked against the pinned generated header and Lua bindings, rather than
inferred from the fixture. This regression still does not execute native userdata.

## Missing integration required for a working component

1. Initialize/import eligible real actors before their first cap check or award,
   with verified save/copy/export identity and correct saved campaign state.
2. Wire and verify the actual EEex bridge plus refresh timing at campaign changes.
3. Capture immediate dual reset coherently and preserve the old-class entitlement;
   complete the manual deferred old-class progression/reward adapter.
4. Coordinate XP SET, respec, losses and owned catch-up against retained base XP,
   including 237/238 and 620 without changing their selected amounts.
5. Prevent native base-XP overflow with a proven coherent overflow carrier; the
   pure arithmetic modules' 53-bit domain does not extend native 32-bit storage.
6. Prove save boundaries, clone/export handling, unknown-data preservation and
   release-and-disable across unloaded owners. The storage core alone does not
   make native XP plus custom old-class state an atomic transaction.

These are implementation/acceptance gaps, not another pending decision about
whether old/new earnings should remain assigned to their respective classes.
