# Deferred old-class reward routing

2026-10-09. Offline instruction execution only; neither game was launched.

`dual_old_reward_probe.py` verifies both pinned executable SHA256 values through
`dual_proficiency_probe.load`, then executes the actual native `LevelUp`,
`AddNewSpecialAbilities`, `AddClassAbilities` pre-loop, class/level accessors and
`IsUsableSubClass` instructions. It observes the CLAB loop's exact half-open
column interval and skips that loop. Environmental game calls and derived-stat
allocation/copy/destruction are explicit doubles. This proves requested grant
intervals, not execution or reversibility of arbitrary installed AP_/GA_ spells.

The 320 cases cover both executable builds, all 16 dual-class orientations,
ordinary reactivation, combined reactivation, combined dormant progression,
old-only dormant progression, and active-only dormant progression. Every case
also checks that the active-class grant interval is unchanged and that the priest
spell helper is called once. Results: `dual-old-reward-routing-results.json`.

## Concrete defect and correction

Native `LevelUp` first calls `AddNewSpecialAbilities` against the saved before
stats (2.6 call RVA `0x2b6927`). After priest spells, the native reactivation flag
causes a second call against a private copy with the old level zeroed (call RVA
`0x2b69c4`). Native ordinary dual progression never changes the old level, so the
first call grants no old-class interval and the second restores levels 1..old.

With a combined old 10→11 / active 1→12 progression, using the original before
stats requests old level 11 in the first call, then levels 1..11 in the second:
level 11 is requested twice. The corrected first call uses a private before copy
whose old level already equals the selected old target. Active before levels
remain unchanged. The existing reactivation call then delivers old levels 1..11
exactly once. While still dormant, native usability suppresses old grants; later
ordinary reactivation restores the full committed old target.

This correction belongs only at the first callsite inside an owned combined
transaction. It must not replace the saved native cancellation snapshot, alter
global class usability, or independently replay old AP_/GA_ resources. The probe
projects the call argument directly to prove the routing; the compiled bridge
and transactional hook installation require their separate implementation tests.

## Other normal reward paths

The source inventory is in `dual-old-reward-delivery.json` and the two bounded
native listings. `ResetLevelUpPanel` calls installed saving-throw and THAC0 rules
with the resulting stats, and updates native spell-slot capacities. Those rule
paths consult actual class usability; a level byte alone is not a reward claim.

`dual_old_slots_probe.py` additionally executes the actual native mage/priest
slot helpers, usability and class-level accessors in 768 cases across the two
builds. Every dual orientation is checked with old level 11 and active levels
10, 11 and 12, at spell levels 1, 4, 7 and 9. The old caster's progression table
is requested at level 11 only once the active level actually reaches 12; equality
keeps the old class dormant. Active caster routing remains intact, including
ranger/cleric combinations. The harness supplies deliberately non-vanilla table
values and zero Wisdom bonus at an explicit table boundary, so this verifies
native selection of class, level and table plus resulting arithmetic, not a
particular installation's slot allowance. The result is retained in
`dual-old-slot-routing-results.json`. Normal installed slot calls can remain in
the native ResetLevelUp path; no duplicate slot-award implementation is needed.

The old HLA count needs separate routing because the native dual branch selects
only the active class. That independent integration is still under investigation.

No production component, game, save, or resource installation was changed.
