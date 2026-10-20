# Campaign XP banking: local candidate handover

October 9, 2026. Branch `codex/campaign-xp-banking`, based on `d22427a`.
The base includes recruitment components 237/238 and the scroll research.

**Current status: the local source now has selectable experimental components
650/651 and an offline package. Christopher chose to keep testing prepared and
not launch a game.** This is not a completed general-use component: the
unbanked between-level dual rule is still pending. The implementation connects caps, retained XP, saved ownership, immediate
banked dual-classing and manual deferred old-class rewards. The approved HP rule
replaces an overlapping new-class contribution with the old-class contribution.
Cancel/commit, installed proficiency and skill choices, delayed HLA delivery,
cap/release notices and `CBMBank_Status()` are wired.

The current handover and exact next check are in
[the player guide](../docs/campaign-xp-banking.md). The earlier, unexecuted
disposable-trial proposal remains in
[DEFAULT-TRIAL.md](xp-banking-native/DEFAULT-TRIAL.md). The six-DLL build exited 0;
the final Lua integration check passed 222 cases. These are offline checks, not
native gameplay acceptance. The candidate and hash manifest are at
`C:/tmp/campaign-xp-banking-20261009/candidate-bundle`.
The source installation's EEex 1.2.0 APIs and native profiles have also been
checked. Its lifetime entries are included; the 93 loader checks and 32 callback
ABI checks using the actual installed scripts pass. (Correction, October 20:
the conclusion recorded here that no EEex upgrade is required is superseded.
The collection now targets EEex v1.3.1 on 2.7.3.0; the October 17
actor-lifetime hook fix was checked in game on EEex 1.2.0 (October 17) and
on EEex v1.3.1 (October 20). See
[the player guide](../docs/campaign-xp-banking.md).)

The zero-bank, between-threshold dual debit still needs the user's choice.
Exact-threshold unbanked duals are supported because both possible debit rules
give the same result; the focused preview/reset/award/shared-cap check passes.
The source installer and normal mod-directory package for 650/651 passed their
isolated WeiDU install/uninstall and dependency checks. No collection selection
or published release changed.
Universal save recovery/uninstall and unusual external respecs are deferred;
they are not prerequisites for the agreed disposable banked-dual trial. No game
was launched, game or save modified, or full installation copied.

## Earlier integration checkpoint (historical)

The status and trial plan above supersede unfinished-work statements in this
earlier checkpoint and the historical implementation notes below. The
ordinary account is `xp-banking/native_account.lua` schema 2, connected by
`xp-banking-native/bank_runtime.lua`. The native base XP field is the sole
ordinary XP balance. Saved metadata contains the policy, reached campaign,
adoption floor, overflow beyond that native field, and the old account that
native dual-classing would destroy. The earlier pure policy/dual transaction
models remain useful tests; their guessed callback protocol is not the runtime.

- Real native constructor/destructor and Copy/Marshal/CHR boundaries establish
  incarnation and copy context. Save-owned owner keys survive ordinary reload;
  CHR imports receive a new owner after explicit entitlement reconciliation.
  Unknown payloads and unfinished operations are retained, not erased.
  The actual pinned EEex serializer also retains absent handlers through its
  `EEex_Sprite_FallbackMarshalStorage`: two offline Lua52/LuaJIT checks preserve
  the dual bank, overflow and unknown fields over repeated saves and restore
  them when the handler is registered before loading again. This only covers
  data preservation with EEex still present. It neither makes deferred rewards
  available without the component nor proves release-and-disable or EEex removal.
- Party entry captures the baseline before the first award. Delayed EET campaign
  initialization preserves that original baseline rather than grandfathering
  later awards. Ordinary saving never advances a campaign or changes XP.
- The positive permanent opcode-104 bridge calls the original leaf once. Only
  the amount that would overflow uint32 is carried separately. The actual
  extracted leaf has run against synthetic buffers in the compiled harness:
  the current award/writer integration has 671 assertions, plus 48 independent
  instruction-emulator cases across both
  inspected engine builds. This is not an engine playtest.
- The stat44 SetAtOffset bridge completes its XP store and metadata operation
  before the native effect recalculation. Its compiled harness executes the
  real reviewed native windows and Windows unwind records: 473 assertions.
  ADD, loss, absolute SET and explicitly scoped recruitment policies are
  distinct. Unknown absolute SET retains native replacement semantics, records
  the before/after amounts and warns when it removes banked active XP; arbitrary
  external respec/direct-memory writers are not claimed compatible.
  Permanent opcode-104 loss, SET and percentage operations now use that journal
  too. Percentage arithmetic preserves the engine's low-32-bit product before
  division; a percentage operation against additional overflow is explicitly
  unresolved, rather than inventing a different arithmetic policy.
- The runtime preserves pre-write journals for award/reset/setter failures and
  rejects replay of unresolved operations. This is recoverable evidence, not a
  claim that a partially failed native operation can always be rolled back.
- The private recruitment adapter compares 237/238 catch-up against retained
  active XP, moves their completion marker after verified success, and preserves
  620's existing active-class party-average SET and 3M limit. The uninstalled
  WeiDU patch passed generated non-SR/SR-presence, altered class, reordered and
  unrelated story, repeat-application and exact resource restoration checks.
  It does not make independent 237/238 require EEex or banking.
- Both independent MakeDualClass implementations are wrapped. CScreenCreateChar
  clears XP after an earlier RemoveAbilities call; preparation now precedes
  that removal. The StartEditing(mode18) boundary captures original-class
  evidence before new-class choices mutate the actor. Prefixes, caller argument
  setup and the real reset instructions have offline coverage; complete dual
  screen cancellation is still under investigation. Aggregate proficiency
  snapshots include unrelated effects and must not be treated as class-owned
  allocations or compared as a universal compatibility fingerprint. Reopening
  at the same old class/level keeps the earliest and latest snapshots separately;
  normal equipment, skill, HP or kit changes do not trigger an equality gate.
- Manual level-up session capture records actual HP contributions and accepted
  choices under the saved owner and current incarnation. The usable retired
  class screen and complete proficiency/spell/CLAB/HLA reconciliation are still
  under implementation. The native dual-creation proficiency screen cannot be
  reused unchanged as a retired-class level-up screen.
  `bank_runtime.OldProgression` now supplies saved owner/revision, current
  incarnation, original class/kit, actual old level and both usable XP amounts
  to the native target resolver; it does not calculate vanilla levels or grant
  rewards. It refuses unresolved native transactions and distinguishes adopted
  existing duals without reconstructing their lost history.
  The detached old-class picker and its menu source now exist, with 45 focused
  Lua51/LuaJIT and structural checks. They preserve installed choice order,
  enforce the supplied budgets/limits, retain incoming above-cap values and
  discard only detached choices on Cancel. The menu has not been parsed or
  rendered by the game, and its native reward transaction is still being wired.
  Actual native proficiency merge probes also showed that temporary SET effects
  can erase earned pips or become permanent pips. The deferred transaction uses
  a scoped permanent-allocation merge instead of copying displayed totals;
  dormant pending pips remain inert until the owned reactivation preview.
- Actual EEex-generated callback assembly revealed an upstream final pcall
  argument-layout defect. The private `callback_abi.lua` adapter supplies ctx/k
  in the proper Win64 stack slots without replacing the upstream generator.
  Its instruction checks initialize the stack with nonzero bytes and clobber
  volatile registers and all register-home slots; the uncorrected generator
  fails the negative control. Eighteen repaired callback instruction cases pass,
  including manual-screen callbacks. Provider calls remain explicit test substitutes,
  not an actual game Lua host.

Christopher explicitly chose the HP overlap rule in the owner chat: a deferred
old-class level **replaces that level's previously awarded new-class HP
contribution with the old class's normal contribution**. Do not add both or take
the higher contribution. Actual committed levels control normal dual usability;
unselected deferred levels do not automatically alter the old level. Ordinary
zero-bank dual handling remains a separate pending question; the runtime does
not silently decide it.

Latest root runtime checks: 72 passed across Lua 5.1/LuaJIT, including separate
preview history and the concrete old-progression provider; cap checks: 50 passed.
The independent loader and actual EEex serializer checks
passed 119 cases. Passing these fixtures is not native cancellation acceptance. Separate recruitment
compatibility checks: 7 passed with real WeiDU and Lua. These are bounded offline
claims. The inert startup bundle has no public component number, selectable
option, M_ publication, collection recipe, push, merge or release.

## Agreed player behavior

Two independent choices, with the second dependent on the first:

- **Campaign XP caps — keep excess XP for later:** BG1 161,000; SoD 500,000.
- **Also cap Shadows of Amn at 2,950,000 XP.**

Both are optional/off by default. No extra ToB restriction, reward multiplier,
automatic leveling, utility-reward change or class-table extension. Banking does
not depend on 610/611, Spell Revisions, an NPC conversion or a custom UI.
The eventual platform is EET with the verified EEex/native hook capability;
minimum version is not established by merely testing EEex 1.3.1 source.

The current public TP2 allocations were checked: 237/238 are preserved, and
612/613 are unallocated. **No banking IDs or labels have been published or added
to TP2, TRA, CI, the release manifest or CEBG.** Assign final IDs with integration
only after a viable runtime exists. Uninstalled research is excluded from release
archives. Do not advertise an unavailable option in the collection.

For a single-class or pooled multiclass character with 600,000 earned XP:

| Campaign | Usable | Banked |
| --- | ---: | ---: |
| BG1 | 161,000 | 439,000 |
| SoD | 500,000 | 100,000 |
| SoA | 600,000 | 0 |

The bank is character/save-owned. Release transfers existing entitlement; it
does not create XP or pass through award multipliers again. Existing over-cap XP
and levels are retained on adoption; future earnings bank until a later ceiling
has room. Previously lost XP is not reconstructed. This adoption rule is a
design contract, **not acceptance of existing-save support**.

## Completed local code and checks

`research/xp-banking/cbmbank_policy.lua` is a pure, uninstalled Lua module. It
plans earned awards, forward campaign releases and monotonic catch-up from
explicit snapshots. It reads no game state, registers no hook, writes no XP,
serializes no actor and touches no INI. A plan carries expected revision and
before-values; applying stale or inconsistent plans fails without changing its input.
Applying a plan is a pure state operation, not a native transaction.

The original module validates exact integer domains, overflow, schema, saved policy and
campaign state. Unknown fields remain on the original snapshot; unknown schemas
are refused without zeroing or migrating the payload. It accepts single-class
and pooled multiclass XP only. The separate `cbmbank_dual.lua` now implements the
approved ownership arithmetic, but native reset/deferred progression is not
implemented. Component 610's `LifetimeXP` cannot substitute for that accounting.

`tests/test_campaign_xp_banking_policy.py`: **196 passed**, Lua 5.1 and LuaJIT,
zero skips/failures. Coverage includes cap boundaries, large/consecutive awards,
conservation, already-distributed entitlements for parties of 1/3/6, pooled
multiclass caps, the 600k example, direct starts/initialization delay, repeated
transitions, old-save snapshot independence, over-cap adoption, catch-up against
usable plus banked XP, stale/reentrant plans, malformed plans and preservation
of inputs/extensions. These tests do not prove native party rounding, award
interception, marshal round-trips, dual allocation or other installed XP ceilings.

The Windows LuaJIT run emitted nonfatal `0xe24c4a02` diagnostics while all tests
passed. The isolated older-save test also completed; `jit.attach` identified a
trace abort. LuaJIT's trace-abort SEH is displayed by CPython's faulthandler before
the handler chain continues. JIT, diagnostics and tests were not disabled.

Additional uninstalled implementation:

- `research/xp-banking/cbmbank_dual.lua` and its focused tests: **106 passed**
  across Lua 5.1/LuaJIT. Immediate dual snapshots, class-owned awards, chronological
  release within shared campaign/native ceilings, no-threshold and altered
  threshold inputs, ordinary unbanked native reset, overflow, stale/tampered
  plans and repeated transitions. No class levels or native XP are written.
- `research/xp-banking/cbmbank_store.lua`: **128 focused tests passed** across
  both Lua runtimes. Immutable actor-owned snapshots, opaque newer schemas,
  validated marshal domains, revision-bound pending/commit/abort and per-actor
  recovery primitives. Adapter observations are required before commit; this
  does not establish an atomic native save boundary or identity classification.
- `research/xp-banking-native/cap_hook.lua`: an EEex hook prototype that requires
  an explicit Install call, after CheckStatsChange's native GetXPCap call. It limits only
  derived XP before native level eligibility; base XP remains retained. **50 Lua
  checks passed**, plus **734 executions of the real downstream native cap
  instructions** across 2.6.6/2.7.3 with fixture helper providers. Base XP and
  unrelated actor memory remained unchanged. The generated EEex bridge itself
  has not executed, and actor lifecycle/state providers are still missing.
- `research/xp-banking-native/dual_transaction.h/.cpp`: compiled native
  transaction coordination for player choices, preview/cancel, identity/revision
  checks and uncertain commit outcomes. It preserves both classes' XP and does
  not select the pending unbanked-dual policy. Its engine callback table remains
  unimplemented: compiled protocol checks are not proof of actual old-class
  HP, proficiency, spell, kit or HLA rewards. **64 scenarios / 645 assertions**
  passed in both MSVC and GCC ASan/UBSan builds. All ten public methods reject
  wrong-thread calls before reaching the adapter; caller initialization on the
  actual engine thread remains a binding requirement. See the
  [deferred-progression report](2026-10-09-dual-class-deferred-progression.md)
  for current compiler results and the exact missing bindings.

The combined policy, dual, storage and cap suite passed **480 tests**. Independent
review found and corrected shared nested snapshot references and extension fields
filling missing dual metadata; regressions cover both. Native cap checks include
unhooked controls that force real clamp writes and verify execution reaches the
level-eligibility boundary, in addition to the bounded pre-clamp cases.
An additional integration review reproduced and fixed the derived XP Lua member
name (`m_nXP`, not the base header's `m_xp`). The callback test now rejects unknown
native members instead of duplicating the implementation's incorrect fixture.

All these modules are excluded from installation and are not loaded by M_ Lua.
Their separation makes engine gaps visible; passing policy/storage tests does
not substitute for coherent native integration.

## Four-campaign detection

The candidate adapter input is the engine's current campaign plus EET's saved
`ENDOFBG1` and `INTOB`, and an owned **save-bound** reached phase. Do not use the
INI campaign selector, area names, protagonist XP or chapter alone.

| Observation | Result |
| --- | --- |
| BG1, `ENDOFBG1` 0 or 1 | BG1, including post-Sarevok Endless BG1 |
| SOD, `ENDOFBG1` 1 | SoD |
| `ENDOFBG1` 2 with initialized campaign | SoA, including visits to old areas |
| `INTOB` 1 | ToB |
| Direct later campaign before its opening flags settle | Pending; never silently initialize as BG1 |
| Earlier observed area/campaign within the same saved progression | Retain that save's reached phase |
| Load an earlier save / another run | Load that save's phase; no process-global high-water mark |

Source inspected at EET v14.0 commit
[`6e51624e7389430e147cfdb23d69457f566465a9`](https://github.com/Gibberlings3/EET/tree/6e51624e7389430e147cfdb23d69457f566465a9):

- [`CAMPAIGN.2DA`](https://github.com/Gibberlings3/EET/blob/6e51624e7389430e147cfdb23d69457f566465a9/EET/base/2da/CAMPAIGN.2DA)
  defines BG1/SOD/SOA/TOB and their direct-start resources.
- [`bg1_BCS.tph:1159–1196`](https://github.com/Gibberlings3/EET/blob/6e51624e7389430e147cfdb23d69457f566465a9/EET/lib/bg1_BCS.tph#L1159-L1196)
  initializes direct SoD. The captured effective `BDSODTRN.BCS` uses
  `MoveToCampaign("SoD")` after setting `EndOfBG1` to 1; the global alone is not
  the transition. The offline decompile is in
  `C:/tmp/campaign-xp-banking-20261009/BDSODTRN.baf`.
- [`K#TELBGT.baf:169`](https://github.com/Gibberlings3/EET/blob/6e51624e7389430e147cfdb23d69457f566465a9/EET/compile/baf/K%23TELBGT.baf#L169)
  moves to SoA; [`bg2_BCS.tph:1754`](https://github.com/Gibberlings3/EET/blob/6e51624e7389430e147cfdb23d69457f566465a9/EET/lib/bg2_BCS.tph#L1754)
  substitutes `MoveToCampaign("ToB")` for the expansion transition.
- [`bg2_BCS.tph:2569–2600`](https://github.com/Gibberlings3/EET/blob/6e51624e7389430e147cfdb23d69457f566465a9/EET/lib/bg2_BCS.tph#L2569-L2600)
  initializes SoA; [3501–3546](https://github.com/Gibberlings3/EET/blob/6e51624e7389430e147cfdb23d69457f566465a9/EET/lib/bg2_BCS.tph#L3501-L3546)
  initializes ToB.
- [`bg2_GUI.tph:948–968`](https://github.com/Gibberlings3/EET/blob/6e51624e7389430e147cfdb23d69457f566465a9/EET/lib/bg2_GUI.tph#L948-L968)
  explicitly repairs the INI selection because `MoveToCampaign` does not update
  it. That UI fallback is not an accounting source.
- [IESDP's GAM header](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/gam_v2.0.htm)
  identifies the EE saved campaign at offset `0x94`, eight bytes. Current native
  headers also declare `m_campaign[8]`. This supports save-owned campaign state;
  a real round-trip through the chosen runtime adapter remains untested.

The larger captured opening scripts were decompiled with missing auxiliary IDS
warnings (for unrelated class/equipment/worldmap symbols). The named campaign
actions/globals above were resolved; those partial decompiles are not installer
tests or proof of all story behavior. Native save/load of the current-campaign
field and award handling during initialization remain runtime acceptance work.

## Native boundary and writers

See [native award-hook evidence](2026-10-09-xp-banking-native-hook.md) for exact
executable hashes, disassembly and the uninstalled prototype. Party XP reaches
per-recipient opcode 104 effects **after** native splitting and remainder
distribution. The ordinary positive award path is distinct from native XP SET.
Never re-divide those effects or give the original party total to every actor.
The native instruction emulator passed 30 cases, 15 on each inspected build;
the observer's Lua contract checks passed. Its EEex bridge was not executed.

Current recipient-local opcode 403 screening alone does not prove capture of
the first award. The proposed unconditional opcode-104 entry hook must also
establish native success and coherent ledger publication. A read-only observer
is useful evidence; it does not bank XP or prevent leveling.

`ChangeStat`/`SetAtOffset` can write XP without opcode 104. Classification needs
scoped writer context: earned addition, absolute SET, catch-up, intentional loss,
respec, dual reset and own release cannot share one guessed delta rule. Unknown
external writers must be reported, not silently absorbed into the bank.

237/238 use monotonic catch-up and must compare their intended target with
relevant existing entitlement. 620 deliberately has a party-average XP SET
policy and active-only dual accounting; it needs its own explicit integration.
Neither current component is banking-aware yet. Their chosen thresholds/reward
amounts must not change, and banking must not require their selection.

Keep XPCAP/native storage limits separate from the player-visible campaign cap.
The examined native permanent-add path writes base XP without a cap check, and
the creature marshal/unmarshal copies that base XP. The observed XPCAP clamp is
in derived XP before level eligibility, rather than discarding the base award.
The current native prototype therefore retains base XP as ordinary earned
storage and imposes a scoped derived campaign cap. It does not grant ordinary
banked XP again on a campaign change. The complete adapter still needs proof of
every XP reader/writer, dual reset, grandfathering and clone/disable behavior.
Never count retained native excess a second time in a custom bank. Independent
class-owned data is needed when MakeDualClass destroys the old base-XP field.

Do not blindly reject CDTweaks 2090 or rewrite XPLEVEL/class rows. Establish
compatibility with retained cap choices and EET Tweaks writers before integration.

## Approved dual ownership; native progression remains a gate

Christopher chose the following behavior on October 9 after discussing both a
reactivation lock and a delayed dual request. **Neither alternative is selected.**
Dual-classing happens immediately. Preserve the pre-dual bank for the old class;
all XP earned afterward belongs to the new class. Campaign limits still apply
to the character as a whole. Do not transfer either class's bank into the other,
discard it at the native reset, or award previously used XP again.

Required hypothetical example (550k is illustrative, not a vanilla Fighter
level threshold):

| Moment | Old-class available XP | Old-class bank | New-class available XP | New-class bank |
| --- | ---: | ---: | ---: | ---: |
| SoD, before dual | 500,000 | 50,000 | — | — |
| Dual immediately | 500,000 retained by the old class | 50,000 | 0; new class starts at level 1 | 0 |
| Earn a further 200,000 in SoD | 500,000 | 50,000 | 0 | 200,000 |
| SoA allows the full release | 550,000 assigned to the old class | 0 | 200,000 | 0 |

The last row is the **required allocation, not an implemented native result**.
Release is limited by the selected campaign and any retained native ceiling;
uncredited amounts remain in their original class's bank. The player really
spends the intervening period in the new class. We do not hold the dual request
while leaving the Fighter active and simultaneously training Thief. Do not add
an extra anti-abuse rule beyond the agreed campaign limits and class ownership.

Native cap accounting uses active XP plus the minimum XP for the retired class's
actual level; this is not an exact lifetime-earned ledger. Verified example:
Fighter 7 at 80,000 XP becomes retired Fighter 7 at a 64,000 cap debit, leaving
97,000 for the new class under the BG1 161,000 cap. Native dual-classing discards
the 16,000 between-level progress. It does not offer a fresh full 161,000 cap.
Keep that ordinary **unbanked** reset accounting distinct from the newly protected
old-class build. When a pre-dual bank exists, its deferred progression needs the
exact pre-reset usable XP as its baseline: 500k usable plus 50k bank must still
mean a 550k old-class target even if an installed class has its preceding level
at 450k. Keeping only 450k plus the 50k would break the approved example. The
prototype preserves the full old baseline in that case and counts it against
the shared cap. With no pre-dual bank, it retains vanilla's ordinary threshold
debit/discard behavior. Neither case credits the discarded difference to the
new class. Capture all these values explicitly; existing dual adoption cannot
reconstruct an unknown pre-dual history.

**New narrow edge decision pending:** retaining the exact baseline only when a
bank exists creates a discontinuity between zero bank and a one-XP bank. The
current uninstalled prototype models vanilla discard for an unbanked dual, but
Christopher has now been asked whether to preserve all pre-reset old-class XP
consistently instead. That alternative would count Fighter 7 at 80k as an 80k
debit (81k new-class room), while vanilla uses 64k (97k room). Duals taken exactly
at a level threshold are unaffected. This question does not reopen immediate
dual-classing or separate old/new bank ownership. Do not install the provisional
edge behavior while that question is unresolved.

Vanilla permanently freezes the old class at its dual level. Therefore preserving
50k of Fighter entitlement is only part of this feature: if that XP makes another
Fighter level due when the campaign opens, there must be a reviewed way to offer
that deferred progression with its normal player choices and benefits. Merely
setting the old level byte would bypass proficiency, HP, kit and other progression
handling. It would not fulfill the requirement. Normal manual leveling remains
part of the contract; a campaign transition must not silently choose a build.

The native class-usability comparison also follows the retired class's actual
level. If the deferred old level increases, the new class must exceed that level
before old abilities are usable. This is a normal dual-class consequence, not
the discarded proposal to lock banked XP until reactivation. Review old and new
progression together before publishing a transition, including avoiding duplicate
rewards, premature reactivation and partial level changes.

The original single/multiclass module continues to refuse duals; their arithmetic
now lives in the separately tested dual module. The native reset and full deferred
old-class progression adapter remain missing, **not user approval of the bank
allocation**. No dual bank has been installed or used on a game or save. See the
[deferred-progression investigation](2026-10-09-dual-class-deferred-progression.md)
for the bounded native evidence and implementation status.

## Persistence, disable and installation gates

See [the persistence audit](2026-10-09-xp-banking-persistence.md). Actor-owned
EEex marshal/UDAux is a suitable carrier, but is not itself a complete ledger
transaction. Register before actor load, preserve unknown wire-valid payloads
and immutable export snapshots, and do not interpret an exporter exception as
safe data preservation. No balance belongs in INI or a sidecar shared by saves.

`IsMarshallingCopy` also marks CHR export and does not identify every preview or
direct copy. A verified scoped copy/export reason is needed to exclude clones
without losing a real character's bank. Destroy/recreate is not identity
continuity; EET's preserved actors and fresh direct-start actors must differ.

**No safe uninstall with a nonempty bank is implemented.** The planned
release-and-disable mode retains its reader, recovery state and save-bound policy
while each actor's bank transfers through the proven credit/commit path. Keep
native-cap remainders and unknown payloads. Dismissed, dead and unloaded owners
must be accounted for before claiming completion; six party slots are inadequate.
Removing the mod or EEex is not a recovery operation. No save edits are authorized.

Final install order is consequently not settled. The runtime must follow EET
and its required EEex capability, detect effective cap/writer arrangements and
coordinate owned catch-up providers. It must not depend on SR or a particular UI.
Brief cap/release notices and an on-demand status action remain planned, not
implemented presentation.

## Shortest separately approved native check

First use a disposable supported EEex/EET run with the **read-only observer**:
one split party award and individual award, plus lock/trap/scribe and kill paths;
record actual amounts, actor, mode, base/derived XP and selection ordering.
Verify SET, dual reset and release are distinguishable before allowing mutation.

After the missing hooks and transaction path are implemented: one character just
below cap, one pooled multiclass, one dual, and one already above cap; cross a
threshold, save/reload old/new snapshots, then perform each campaign handoff and
a repeated notification. Check charges/reward totals remain native. Include a
clone/export comparison and a dismissed bank owner in release-and-disable.
These checks are prepared only; no launch or native acceptance occurred here.

The October 10 target is a reviewable candidate. Unresolved hook, persistence or
class-progression gates must remain visible; synthetic arithmetic passing is not
permission to ship a partial working default.

## Related local batch handover

The separate `codex/recruitment-xp-scroll-levels` branch includes these local
checkpoints; inspect its current head for subsequent native-runtime work:

- `4687538` adds independently selectable first-recruitment catch-up for Fade
  (237) and Evandra (238). Focused checks passed: 50 XP checks, 10 public/release
  checks and 6 copied-resource/source-backed checks. Native recruitment remains
  untested; there is no existing-actor repair.
- `d22427a` records the approved reader-level scroll behavior and initial hook
  investigation. `b6daaa9` adds the later native selector proof and corrects its
  mode assumptions: 336 selector cases passed across the two inspected builds.
  A subsequent uninstalled C++ extension implements original-reader context,
  queued/nested/reflected cast ownership, linked-effect propagation and a native
  reader provider. An independent probe passed 1,750 native class/capability
  calls across both executables. Engine detours, installed resource classification
  and pending-cast save/transport persistence are still missing; component 430
  has not been replaced. The separate branch's `research/scroll-runtime/README.md`
  records its current compiled checks and binding status.

These are local commits only. No push, merge, release or collection recipe
change is included. The banking branch includes recruitment and the initial
scroll note through `d22427a`; its copy of that note predates the later scroll
investigation. Consult the separate branch for the corrected scroll findings.
