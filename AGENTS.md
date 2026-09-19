# chriz-bg-modpack project decisions

## Authoritative NPC conversions and proficiency allocations

User decision, 2026-09-19; applies across this project's NPC conversions and
reallocation components, including older implementations that need updating.

- Selecting an explicit NPC build or reallocation makes the component's defined
  result authoritative for the fields it owns. Apply that result even when an
  earlier mod supplied different values.
- Do not use exact incoming HP, proficiency values, level bytes, or XP values as
  a fingerprint that must match a development fixture. In particular, current
  HP is never evidence of whether an intended NPC can receive a build override.
  Read incoming values when an explicitly intended calculation needs them;
  do not confuse that with requiring arbitrary source-value equality.
- For a complete proficiency allocation, clear the existing weapon and fighting
  style allocation and write the complete chosen build, including zeros for
  unselected proficiencies. Do not retain old pips merely because they came from
  another mod. Scope clearing to proficiency fields; preserve unrelated effects.
  A component explicitly designed as a narrow adjustment keeps its stated scope.
- Define the final allocation for each supported recruitment/progression tier.
  Use installed progression rules where the component promises to follow them;
  do not guess a complete build from the user's current allocation. Apply the
  same policy consistently across conversions and document authored exceptions.
- Verify the resulting values and repeat-application stability. Existing source
  values, missing/duplicate proficiency records, and harmless record ordering
  differences belong in compatibility tests, not arbitrary installation gates.

## Resource layout and evidence

- Follow declared offsets, indexes, and counts when patching resource blocks.
  Do not require a particular physical ordering of independently indexed blocks.
  Preserve the internal order of each effect list unless changing it is intended.
- A proven installer defect can be corrected and regression-tested without a
  reporter's files. Do not make those files a prerequisite when the failure is
  already explained by source inspection and a controlled reproduction.
- These decisions are implementation requirements, not a claim that the old
  components have already been changed or live-tested.
