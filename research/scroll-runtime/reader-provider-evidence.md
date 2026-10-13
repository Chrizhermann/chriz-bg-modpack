# Native scroll reader provider evidence

Read-only audit, 2026-10-09. This supplies the class/capability inputs for the
uninstalled scroll runtime. It does not establish a working installed detour,
resource lifetime contract, save behavior, or live acceptance.

## Result

The engine has usable target-reader class and casting-capability queries. The
folded getter used by `CGameSprite::GetCasterLevel` is **not** an active-class
filter. Active dual-class restrictions occur in
`CAIObjectType::IsUsableSubClass`, which is called by the native mage/priest
capability methods. Those methods take an explicit sprite and do not read their
UI `this` pointer or the currently selected character.

For native class rules, a provider can use those methods without a kit-name
whitelist or examining known/prepared spells. It must separately verify object
identity, select the same effective stats as the engine, and call the native
caster-level query with the actual `CSpell*`. Arbitrary extension-defined casting
outside these native rules remains a separate integration question.

## Inputs and provenance

Pinned sources:

- EEex `a6d21abe44e20509f5d0259ccc6c7e7f9d12b285` (v1.3.1), cached at
  `C:/tmp/scroll-hook-research-20261009/EEex`.
- InfinityLoader `817925caab3eb9cf600cfaf38853da8d30c28247`, cached at
  `C:/tmp/scroll-hook-research-20261009/InfinityLoader`.
- Function symbols: `EEex/EEex/loader/v2.6.6.0/bg2ee/function_names.db` and
  `v2.7.3.0/bg2ee/function_names.db`.
- Generated declarations: `InfinityLoader/EEex-v2.7.3.0/headers/
  EEex-v2.7.3.0_generated/Baldur_generated.h`, especially `CAIObjectType`,
  `CDerivedStats`, `CGameSprite`, and `type_GetCasterLevel` (short return,
  `CSpell*`, integer include-wild-mage argument).

Executables were opened only for byte reading, never launched or modified:

| Version | Read-only executable | SHA256 |
| --- | --- | --- |
| 2.6.6.0 | `<BG2EE 2.6.6.0 install>/Baldur.exe` | `fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580` |
| 2.7.3.0 | `%USERPROFILE%/CEBG-Tests/Combined-20260908/game/Baldur.exe` | `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57` |

The following are preferred-image virtual addresses, not relocated process
pointers. An eventual host must resolve/certify its own module and signatures.

| Native function | 2.6.6.0 | 2.7.3.0 |
| --- | --- | --- |
| `CGameObjectArray::GetDeny` | `0x140276490` | `0x140276700` |
| `CAIObjectType::GetActiveInactiveClasses` | `0x14011D9B0` | `0x14011D9D0` |
| `CAIObjectType::IsUsableSubClass` | `0x14011E070` | `0x14011E090` |
| `CDerivedStats::GetLevel` | `0x140152A30` | `0x140152C40` |
| `CDerivedStats::GetLevelField` | `0x140152A50` | `0x140152C60` |
| `CDerivedStats::GetMaximumLevel` | `0x140152BD0` | `0x140152DE0` |
| `CScreenWizSpell::CanCastMageSpells` | `0x1402E8010` | `0x1402E8650` |
| `CScreenPriestSpell::CanCastPriestSpells` | `0x1402DBB40` | `0x1402DC1A0` |
| `CSpell::GetCasterType` | `0x14024EDB0` | `0x14024F010` |
| `CGameSprite::GetCasterLevel` | `0x14039C5F0` | `0x14039CC30` |

## Object lookup and exact call contracts

At the Windows x64 ABI, these are sufficient call signatures:

```cpp
uint8_t GetDeny(int32_t instance, void** result);
void GetActiveInactiveClasses(void* ai, uint8_t* newClass, uint8_t* oldClass);
int IsUsableSubClass(void* ai, uint8_t requestedClass, int nativeCallerFlag);
uint8_t GetLevel(void* derivedStats, uint8_t compositeClass, uint8_t subClass);
uint8_t GetMaximumLevel(void* derivedStats, uint8_t compositeClass);
int CanCastMageSpells(void* unusedScreenThis, void* targetSprite);
int CanCastPriestSpells(void* unusedScreenThis, void* targetSprite);
short GetCasterType(void* spell);
short GetCasterLevel(void* sprite, void* spell, int includeWildMage);
```

`GetDeny` has **a byte return**, not an integer return. The success path at
2.7 `0x14027674A` loads the actor pointer into RAX, stores it through RDX, then
executes `xor al,al`. Upper RAX bits remain pointer residue. The function clears
`*result` first; AL=0 indicates success, AL=2 an instance-generation mismatch,
AL=3 invalid/range failure. It has no lock/unlock call in the audited body.
Require successful byte status **and result == the original reader** before
using AI methods. This is additional to the runtime generation/lifetime registry,
not a replacement for it.

`GetActiveInactiveClasses` initially writes `ai.m_Class` to both outputs. Invalid
instance -1 or failed GetDeny simply returns those identical outputs. Thus
`newClass == oldClass` alone cannot distinguish multiclass from lookup failure.
With verified identity, split outputs denote a two-class dual and equal outputs
denote the native single/multiclass path.

Native callers pass the third IsUsableSubClass argument as 1. The audited body
does not use that input; keep the native calling convention rather than infer a
different API from the unused argument.

## Class activity and level source

Offsets below are identical in both audited builds:

| Field | Sprite-relative offset |
| --- | --- |
| Current `m_typeAI` | `0x30` |
| `m_startTypeAI`, used by mage/priest capability methods | `0x4B68` |
| Class within either AI object | `+0xB` |
| Instance within either AI object | `+0xC` |
| Main derived stats | `0x1120` |
| Temporary derived stats | `0x1DC8` |
| Native effective-stats selector | `0x4EA4` |
| Base creature flags | `0x568` |

The effective stats are main when the selector dword is nonzero, temporary when
zero. IsUsableSubClass and GetCasterLevel independently make that exact choice.
Do not always read the main stats or the CRE level bytes.

GetActiveInactiveClasses maps composite class plus original-class flags to new
and old classes; it does not decide whether the old class has reactivated.
IsUsableSubClass then reads both levels through native GetLevel. New class is
usable; old class is usable **only when new level is strictly greater than old**.
The equality boundary remains dormant. Native GetLevel maps the composite and
constituent to the appropriate indexed derived level field. It does not inspect
XP or compare an old fixture value.

For a dual, the new class level is always the highest active level: before
reactivation it is the only active class, and after reactivation it exceeds the
old one. For a nondual character, native GetMaximumLevel maps the class to one,
two, or three fields and returns their maximum. This is enough for the fallback
formula without manually recreating a full physical slot table in production.
If a consumer needs an actual list, native IsUsableSubClass plus native GetLevel
can enumerate the engine's class constituents; do not present the maximum as a
literal list of all classes.

Both functions use native byte level results (GetMaximumLevel has word
comparisons in some branches before returning a byte maximum). Do not reinterpret
them as unrestricted integer levels based only on the generated storage types.

The original-class flags are bits 3–8, and fallen Paladin/Ranger flags are bits
9–10. This agrees with the [CRE format reference](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/cre_v1.htm).

## Native capability semantics and kit boundary

In both builds, CanCastMageSpells reads target sprite from RDX, ignores RCX, and
calls IsUsableSubClass on start AI for class constants 1, 19, 5 (Mage, Sorcerer,
Bard). CanCastPriestSpells similarly checks 3, 11, 21, 6, 12 (Cleric, Druid,
Shaman, Paladin, Ranger). There is no known/prepared spell lookup, slot count,
current selection, screen widget, spell-disable-button effect, or minimum
character-level test in either body.

The priest path excludes the Paladin branch if native GetKitMask has bit 0x10,
and finally returns false when base creature flags &0x600 is nonzero. These are
native Inquisitor/fallen mechanics. GetKitMask itself resolves indexed kits
through the loaded rule table rather than comparing custom kit names. A copied
handwritten kit-name list would therefore be an inferior substitute.

This is **native class casting capability**, not a claim that every kit can cast
every spell or currently has a spell slot. A low-level Paladin or level-zero Mage
can satisfy it. A zero class level is distinguishable from a failed identity
lookup; the fallback formula's minimum of one can handle zero if the active
class identity is resolved. Provider review found an unnecessary zero-level
rejection; the implementation worker removed it and distinguished an absent
active entry from a resolved active entry whose level is zero.

These native methods do not discover arbitrary mod-defined casting systems
implemented outside native class/kit mechanics. A mod that implements a caster
through custom buttons or special abilities may need an explicit integration.
An empty spellbook, nonzero native CL=1, or a stock kit whitelist cannot resolve
that question. Runtime patches to these native methods also require an honest
integration audit rather than assuming the pristine-byte probe tested them.

## Actual installed CSpell type and relevant caster level

At 2.7 `GetCasterLevel+0x52/+0x8C`, RCX is sprite+0x30 and the called folded
function at `0x14011DC40` is only `movzx eax,byte[rcx+0xB]; ret`. The nearest
symbol `CGameAnimationType::GetMoveScale` is misleading: this use is the current
class getter. It contains no dormant-class filtering.

GetCasterLevel first calls CSpell::GetCasterType on the actual CSpell. The type
getter demands its resource, reads the loaded header pointer through CRes+0x68,
and returns the word at SPL header+0x1C. Native values 1 and 2 are wizard and
priest, respectively, matching the [SPL format reference](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/spl_v1.htm).
Unresolved/special/innate wrappers must not be classified from their resref or
from the scroll's title. This audit does not resolve wrapper-chain policy.

The native relevant caster-level calculation uses **current AI**, while the
capability methods use **start AI**. Preserve each native method's actual
semantics and expose both class IDs as provenance; do not assume equality or
reject a legitimate class transformation solely because they differ.

The native wizard/priest level helpers return one for noncasters. They are not
capability predicates. The priest query includes native Paladin/Ranger reduced
progression; the full wizard query includes the include-wild-mage flag, stored
roll, and a spell-specific minimum. Pass the actual CSpell and let the native
method calculate these details after capability has been resolved.

## Bounded native evidence

`reader-native-probe.py` runs unmodified code from the pinned PE images in
Unicorn, with a synthetic GetDeny object lookup. `reader-probe-2.6.json` and
`reader-probe-2.7.json` record **875 successful native calls per build**, 1,750
total. Coverage includes:

- All 21 native class/composite IDs, independently expected physical level
  ordering, all active constituents, and native maximums for up to three classes.
- Both old/new orientations of all eight supported two-class composites, each
  below/equal/above the reactivation boundary (48 dual cases per build).
- Main versus temporary effective stats, including an equality/dormancy change.
- Native Inquisitor and both fallen flags; empty spellbooks throughout.
- Arbitrary custom kit ID 0x4025 and zero-level Mage, Cleric, Bard, Sorcerer and
  Shaman inputs, without a kit-name check.
- Failed synthetic lookup leaves identical composite class outputs, demonstrating
  why provider identity preflight is required.
- All target actor bytes remain unchanged after every native call.

This probe does not emulate an installed custom Paladin KITLIST mapping, resource
demand, wild-mage tables, or GetCasterLevel itself. Those conclusions above come
from disassembly/source tracing and are labeled separately. It substitutes
GetDeny and does not prove live object locking, registry lifetime, installed
detours, thread behavior, or game acceptance.

Reproduce with ordinary Python plus analysis-only dependencies:

```powershell
$env:PYTHONPATH='C:/tmp/xp-banking-analysis-deps'
python research/scroll-runtime/reader-native-probe.py <read-only-exe> <matching-function_names.db>
```

Dependencies used: pefile 2024.8.26, capstone 5.0.9, Unicorn 2.1.4. Textual
disassembly is captured in `reader-native-2.6.txt`, `reader-native-2.7.txt`,
`reader-active-2.7.txt`, `reader-caster-2.7.txt`,
`reader-progression-2.7.txt`, and `reader-lookup-2.6.txt` / `reader-lookup-2.7.txt`.
Jump tables shown as disassembled data in those raw
captures are not claimed to be executable instructions.
