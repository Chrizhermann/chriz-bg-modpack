# XP banking: minimal native acceptance plan

Prepared October 9, 2026. **Not executed; separate authorization required.**
Use a disposable EET/EEex test run. Do not load Christopher's ongoing game or
saves, replace its executable, or clone a full collection merely for this check.
Use the precise executable/source hashes from the native-hook evidence.

This is staged so a missing first gate does not require a campaign playthrough.
Tests require the final observer/adapter capability first; names of future
banking commands are deliberately not presented as existing APIs.

## 1. Observe the actual award boundary first

Start with a party of three, each with a distinct known XP value, and an unloaded
observer that has not registered mutation callbacks. Load the reviewed read-only
diagnostic, then exercise one event of each kind:

| Trigger | Required observation |
| --- | --- |
| Kill | Per-recipient permanent-add opcode 104 after the native party share |
| `AddExperienceParty(10)` | Native remainder distribution; sum of individual entitlements equals the actual adjusted reward, with no second division |
| `AddXPObject` to one actor | One individual recipient; unrelated party members unchanged |
| Dialogue award | Its actual dispatcher and individual effects, not an inferred visible XP difference |
| One scroll learned, lock opened and trap disarmed | Actual utility awards; current 610/611/other-mod amounts remain unchanged |
| `ChangeStat` XP SET and ADD | Separate writer/context from ordinary opcode-104 earning; no accidental bank event |

Record effect mode/timing, original amount, recipient native identity, base and
derived XP, call nesting and pre/post native values. Compare cap enabled and
underlying cap removed configurations. Stop if an award bypasses the boundary,
arrives already truncated, or lacks classification. Observation cannot establish
banking readiness or account for unsupported arbitrary direct memory writes.

## 2. Prove the derived cap and coherent saved accounting

Only after the cap bridge, complete lifecycle providers and persistence protocol
pass review. The current cap candidate retains ordinary earned XP in native base
storage; it must not credit an additional custom balance for that same surplus:

1. A character at 160,999 usable, zero bank, earns 10. Require 161,000 usable and
   9 banked, with exactly 10 total new entitlement and ordinary manual leveling.
   For the current architecture, native base XP must be 161,009 and derived XP
   161,000. The 9-bank status is their owned difference, not another XP grant.
2. Repeat a distinct award; deliver a repeated callback for the same event using
   the verified native identity protocol. Distinct awards must count once each;
   repeat delivery must not duplicate or suppress another genuine reward. The
   cap callback may repeat without changing native base XP or granting a reward.
3. Save at each supported pre/post boundary. Reload earlier and later saves,
   then an independent run. Native XP and the corresponding ledger snapshot
   must agree. Do not use an exporter that edits XP to conceal a split commit.
4. Repeat with a pooled multiclass and an already-over-cap adopted character.
   Preserve the latter's existing XP, levels, abilities and equipment.
5. Repeat with a huge entitlement near native 32-bit limits. No wraparound,
   discarded bank, or conversion from unsigned XP into a negative amount.

## 3. Campaign and lifecycle sample

For a 600k entitlement sample, require 161k/439k in BG1, 500k/100k after the real
SoD transition, and 600k/0 after SoA. With the SoA option, separately cross 2.95m
and release its excess in ToB. Repeated notifications and travel to old areas
must not re-credit or lower the saved phase. Test each direct start plus a
skipped-SoD transition; initialization delay must not lose an immediate award.

One continuing companion must retain its ledger through dismissal/rejoin,
death/resurrection and an actual area/campaign transport. A fresh replacement
with the same name must not inherit it by name. Reuse a freed object ID and verify
no balance leaks from its previous owner.

Compare ordinary save, CHR export/import, magical clone and item preview. The
owner's ledger never changes during export; only intended persistent characters
retain eligible balances. A clone or preview cannot earn/release a copied bank.
Test wire-valid newer schema and extra fields, preserving them through a save
without silently adopting empty v1 state.

## 4. Dual and disable gates

Dual ownership was approved October 9: switch immediately, retain the pre-dual
bank for the old class, and assign subsequent earnings only to the new class.
These tests await the native reset/deferred-progression adapter, not another
allocation decision:

1. At 500k usable plus 50k banked in SoD, dual immediately. The new class really
   becomes level 1. Preserve the 50k old-class bank across reset/save/reload.
2. Earn 200k after dual. It belongs only to the new class and remains banked
   while the shared 500k cap leaves no room. No old-class abilities become usable
   early, and neither partition leaks into the other class.
3. Enter SoA. Credit only the amount the new campaign/retained native ceiling
   permits: the illustrative unconstrained result is 550k old-class entitlement
   and 200k new-class entitlement. Repeated transition events cannot credit again.
4. Use the installed class XP tables to cover old-bank release both with and
   without an old-class level threshold crossing. The old class's deferred level
   must retain manual choices and full HP, proficiency, kit, spell and other
   progression handling. A level-byte-only correction is a failure.
5. Compare active levels below, equal to and above the final retired level.
   Native old-class availability follows the final retired level; ensure neither
   premature reactivation nor double rewards during both level-up sequences.
6. Capture actual pre-reset XP and native retired-level threshold separately.
   Fighter 7 at 80k has a vanilla retired debit of 64k, leaving 97k under 161k;
   do not turn its vanilla-discarded 16k into new-class XP or confuse that
   between-level reset with the protected old bank.
7. With a pre-dual bank, use an installed hypothetical old-level threshold of
   450k below 500k usable plus 50k banked. Its protected old target must still be
   550k, not 500k from threshold-plus-bank. The preserved 500k baseline consumes
   the SoD shared allowance; post-dual earnings cannot exploit the reset gap.
   This protection is needed for the banked build; the unbanked native reset in
   step 6 remains unchanged.

Include skipped-SoD transitions, retained native ceilings, old/new save snapshots,
an existing dual with unknown history, intentional XP loss, respec and 237/238/620
catch-up. Preserve normal manual level-up and selected catch-up policies. No XP
or level may be debited merely because a deferred advancement screen was canceled
or a native class-progression transaction could not finish.

Release-and-disable must include a dismissed/unloaded bank owner and a retained
native storage ceiling. Verify every credited amount before debiting its bank;
keep inaccessible remainder and unknown schemas. Saving and reloading midway
must resume recovery once. Uninstall is not accepted until the saved recovery
state proves all required owners resolved. Removing EEex is a separate boundary.

## Reporting

Record native build/EEex/EET/mod options, exact event observations and before/after
values. Report source proof, automated policy checks, offline instruction checks
and actual native acceptance separately. SR/no-SR and ordinary/alternate UI
variations must show no mechanical dependency. No full campaign playthrough or
full collection reinstall is requested by this plan.
