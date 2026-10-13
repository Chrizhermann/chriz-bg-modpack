# Scoped active proficiency UI reads

Read-only source pass, October9. `dual_active_ui_reads.py` verifies both local
engine image hashes before disassembling the five named functions. The JSON
contains exact call bytes and surrounding argument setup; the two text listings
retain complete bodies, including source jump tables (which are data, not code).
This inventory alone is not an executed hook or native UI acceptance.

All listed calls have the actual ABI `int getter(CGameSprite* RCX, uint32 stat EDX)`
with result EAX. Only these UI callsites need the owned session's class-allocation
view; the global sprite/derived-stat getters must retain ordinary equipment and
temporary effects. The private wrapper still has to prove the current actor,
session and phase before substituting anything.

| Caller | Getter | 2.6.6 RVA | 2.7.3 RVA |
| --- | --- | --- | --- |
| ResetLevelUpPanel | active | 2bf6e5 | 2bfd65 |
| ResetLevelUpPanel | inactive | 2bf705 | 2bfd85 |
| ResetLevelUpPanel | active | 2bf7f3 | 2bfe73 |
| UpdateProficienciesPanel | active | 2c741d | 2c7a9d |
| UpdateProficienciesPanel | inactive | 2c749d | 2c7b1d |
| UpdateProficienciesPanel | inactive | 2c750d | 2c7b8d |
| CanSpendProficiencySlots | active | 2b143e | 2b1abe |
| CanSpendProficiencySlots | inactive | 2b15af | 2b1c2f |
| CanSpendProficiencySlots | inactive | 2b1624 | 2b1ca4 |
| OnProficiencyPlusMinusButtonClick | active | 2bdb41 | 2be1c1 |
| OnProficiencyPlusMinusButtonClick | inactive | 2bdbb8 | 2be238 |
| OnProficiencyPlusMinusButtonClick | inactive | 2bdc29 | 2be2a9 |

`ResetLevelUpPanel` reads actor R14. It resolves installed proficiency IDs through
`CRuleTables::GetProficiencyId` immediately before these getter calls; its later
active query subtracts already allocated pips from the available slot count.
`UpdateProficienciesPanel` also reads actor R14, with stat ESI. Availability and
plus/minus handling read their object-array-resolved actor from the frame local
(`[rbp+7]` and `[rbp-11]` respectively), with stat ESI. Their inactive branches
and native maximum/class proficiency rules remain part of the normal UI logic.

`ResetProficienciesPanel` has no calls to either getter or GetAtOffset. Its direct
actor accesses in the inspected body concern class/level, effect-list state and
the seven base skill bytes. In ordinary LEVELUP mode1c it branches past the
new-character/dual-creation proficiency clearing loop at2c1ab9 (2.6). It still
recalculates effects and computes budgets. Do not reuse mode19, which follows
the dual-creation behavior and can clear allocations.

No symbol or generated Lua binding named `IsProficiencyPlusMinusButtonClickable`
was found in the inspected databases/headers. The concrete availability routine
in these builds is `CanSpendProficiencySlots`; the panel update also writes the
normal UI row state. This does not certify arbitrary external custom menu code.

The actual setter sites are already observed by the manual-session bridge.
Both reads and writes must use class-owned allocation in the scoped combined
preview: correcting only the final minimum would still misprice choices when a
temporary SET masks or boosts the displayed aggregate. Preserve native behavior
outside that owned preview and restore the captured allocation on Cancel.
