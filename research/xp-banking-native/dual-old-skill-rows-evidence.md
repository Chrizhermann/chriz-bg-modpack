# Installed old-class skill choices

2026-10-09. Read-only native queries; no game process, save, or component installed.

The normal skill +/- availability method only checks whether a skill budget
exists. Individual rows are instead filtered in `UpdateProficienciesPanel` by
`GetThiefSkillPercentage` (2.6 RVA `0x2492b0`). A nonzero class override selects
that class with the sprite's kit, then reads installed `THIEFSCL` (rules offset
`0x3270`). It combines this with the class-zero/default lookup and clamps the
result below at zero. Zero means the row is not offered. Thus a budget alone
does not authorize all seven skills.

Native allocation IDs are 0 Pick Pockets, 1 Open Locks, 2 Find Traps, 3 Move
Silently, 4 Hide in Shadows, 5 Detect Illusion, 6 Set Traps. ID 7 is a composite
stealth display, not a separate stored allocation. The exact row keys and native
label strrefs come from the inspected screen and `GetSkillName(byte)`; that
function is static, not a sprite method.

The native plus handler compares the displayed value against a mutable global
maximum (250 in both inspected files), then increments the base value. Therefore
the equivalent base limit is `clamp(nativeMaximum - (display - base), 0, 255)`.
Do not hardcode 250 or ignore bonuses. Already higher base values remain intact;
the picker only prevents additional increases.

`dual_skill_rows.cpp` calls the real installed class-name/table/value/name
helpers, using the captured old kit only in detached class-name lookups. It
does not temporarily change the actor's kit or class. It verifies native dual
identity, engine-thread ownership of the bound query, source signatures, byte
storage bounds, and result completeness before publishing seven rows. The
percentage helper source signature is retained to bind the replicated two-row
combination to the audited native semantics. No specific kit row name, table
ordering, or prior allocation value is required.

The compiled wrapper plus actual native `GetSkillValue`, `GetSkillName` and
dual-class selection instructions passed 120 offline cases across 2.6 and 2.7.
They cover different enabled/disabled/default percentages, bonuses -30 through
300, and mutable displayed caps 180/250/300. Every actor byte remains unchanged;
foreign-thread queries refuse before dereferencing dummy actor pointers. Class
name resolution, table values, skill-bonus outputs and environment lookup are
declared doubles in these checks. This does not claim that each installed kit
has been played in the engine.

`dual_skill_rows_bridge.lua` transports the seven complete rows as one bounded
numeric text result through the actual Lua provider. The read-only DLL was built
at `C:/tmp/campaign-xp-banking-20261009/native-skill-rows/dual_skill_rows.dll`.
`dual_retired_rows.lua` preserves installed WEAPPROF ordering, deduplicates aliases
of the same owned stat, uses native per-stat caps and old allocation values, and
offers only positive-percentage skills. Display-label failures have a fallback;
they are not an eligibility prerequisite.

The detached picker supports native HLA eligibility callbacks and durable full
descriptors. It retains ordered choices beyond a native 24-entry delivery batch,
rejects removing prerequisites that invalidate remaining choices, and closes its
query catalog once. Picker/row assembly checks passed 73 cases on Lua51/LuaJIT.
Those provider fixtures do not prove a rendered native menu or the HLA delivery
adapter, which has its own integration work.
