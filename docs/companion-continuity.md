# Companion continuity across EET campaigns

Research baseline: 2026-09-06. This document separates existing EET actor continuity
from gaps caused by companion mods creating a second actor. Source inspection is not
live transition acceptance. No changes were made to the reference playthrough.

## Contract and scope

When a recruited companion returns in a later campaign, their permanent development
should survive: base attributes, exceptional Strength, learned mage/bard spells, spent
thief skill points, proficiencies, class/kit and level progression, and earned permanent
abilities or effects. Preserve the existing actor where its mod already does so.
Copying whole CRE templates over that actor would discard player choices and local
quest state. Temporary buffs and equipment bonuses must never become permanent stat
increases through a snapshot of displayed statistics.

This does not create new companion content in campaigns where none exists, change
story deaths, or require every campaign-specific presentation and plot variable to
remain identical. Equipment carried out of SoD has its own balancing policy: clear
the imported loadout at the specific SoA arrival hook, before recruitment can expose
it to the player. Equipment received during BG2 must survive subsequent visits.

The roster audited on 2026-09-06 comes from the collection curation worksheet
and its newer component catalogs. Default companion mods are Xan, Yeslick, Safana,
Sirene BG2, Evandra, Fade, Pai'Na and Sarah. Branwen's newer catalog makes her optional
and unchecked; Aura is also optional and unchecked. Ajantis BG2 and Bristlelick are
excluded. Adding the separate Sirene BG1 package is still an open collection decision.
The historical installed-mod TSV alone is not the default roster.

## Installing the components

With YeslickNPC's Alaghor choice (component 1), install modpack **188** before
**199** to give the BG1 recruitment templates that starting kit. Omit 188 for
the vanilla-companion choice. Continuity preserves the original actor's kit;
it does not impose the BG2 preset during a transition. See the
[Yeslick guide](yeslick-alaghor.md) for level-dependent grants and saved actors.

**199 — EET companion continuity** supports PPG Xan v19 and Yeslick v5's audited
spawn blocks. Install all companion, content and class/kit mods first, install
199, then run **EET_end**. Start a **new campaign**: this changes installed actor
identifiers and references, and cannot rename the actors already embedded in a
save. EET's finalization merges their campaign dialogue tables under the shared
identity. Later mods adding references to the old identities would bypass the
conversion, which is why this belongs immediately before EET_end.

Returning Xan and Yeslick keep their entire original build, including any class,
kit or dual-class choices made during play, XP, base statistics, learned and
memorized spells, thief skills, proficiencies, effects and personal history.
BG2 template class/kit settings do not overwrite returning companions; coordinate
the BG1 class preset separately if that is the desired starting build. Their
BG2 dialogue, script slots, allegiance, specifics and soundset come from the
effective BG2 CRE. Their existing name and portraits remain. Talk count and
the kicked-out local are reset for their new introduction.

Imported equipment is cleared. Only Xan's required BG2 mod moonblade is recreated,
using the blade variant selected by his installed class component. Yeslick receives
an empty loadout. Xan's template-based additive XP catch-up is marked complete for
the imported actor so that it cannot add experience on top of his actual total.
Native later progression, including EET's ToB XP floor, remains in place. Existing
BG1 quest locals are preserved; no generic runtime merge of two actors occurs.

If never recruited earlier, their original BG2 spawn and its equipment remain.
A previously recruited dead actor is neither replaced nor resurrected. The BG2
mods' existing SoA-to-ToB registrations continue to control later availability;
this does not add a new Fate Spirit route for companions never recruited in SoA.

**189 — Safana in Amn inventory cleanup** is independent of 199. Install after
Safana in Amn v0.5, before her SoA arrival has executed. It inserts the native
`DestroyAllEquipment()` into that exact existing one-time arrival response after
its movement wait. Safana receives no replacement items. It can affect an ongoing
campaign whose arrival has not occurred, but deliberately does not strip a Safana
who has already arrived, since she could now be carrying legitimate BG2 equipment.

Neither component needs EEex. Unexpected spawn code, duplicate hooks, missing
required resources and conflicting identity-table rows cause installation to fail
and roll back rather than silently accepting partial support. Component 199 also
rejects the legacy stat-transfer module described below.

## Audited support map

EET's native BG1-to-BG2 returning roster is **Dorn, Edwin, Imoen, Jaheira,
Minsc, Neera, Rasaad and Viconia**. Its native BG2-only registrations cover
**Aerie, Anomen, Cernd, Haer'Dalis, Hexxat, Jan, Keldorn, Korgan, Mazzy, Nalia,
Valygar, Wilson and Yoshimo**, subject to their existing campaign/plot rules.
The other vanilla BG1/SoD companions retain their native earlier-campaign routes;
their presence in EET does not provide new joinable BG2 content by itself.

The collection defaults with new bridge behavior are **Xan and Yeslick**.
**Safana** receives the independent inventory fix. **Sirene, Evandra, Fade,
Pai'Na and Sarah** retain their existing native EET transitions. Optional **Aura**
already moves her actor; optional **Branwen** still needs a separate bridge and
is not included in component 199.

Source paths below are relative to the inspected game/source tree. Versions
identify that read-only research baseline, not the latest upstream release.

| Route | Actor identity and evidence | Status / treatment |
|---|---|---|
| Native and EE companions | EET v14.0 `EET/lib/transition.tph` registers campaign routes; `EET/lib/bg1_BCS.tph`, `bg2_BCS.tph` and `other/EET_functions.tph` implement moves and script/dialogue transitions. Jaheira's existing actor is moved in `bg2_BCS.tph` rather than recreated when previously recruited. | Retain native continuity. Only routes provided by EET are covered; individually test the enabled companion/campaign combinations. |
| Xan BG1 → PPG Xan BG2 | BG1 DV `Xan`; BG2 DV `O#XAN`. Xan v19 `Xan/Scripts/AR1000.baf:5` creates `O#Xan09`. `Xan/xan.tp2:395` registers type 2, meaning BG2-only continuity. | Component 199 unifies identities and moves the original actor. Installer-verified; live acceptance pending. |
| Yeslick BG1 → Yeslick BG2 | BG1 DV `Yeslick`; BG2 DV `LK#YESLK`. Yeslick v5.0 `yeslicknpc/scripts/ar2010.baf:6` creates `lk#yesl`; `lib/main_component.tpa:95` registers type 2. | Component 199 unifies identities and moves the original actor. Installer-verified; live acceptance pending. |
| Branwen BG1 → PPG Branwen BG2 | BG1 DV `Branwen`; BG2 DV `O#Bran`. Branwen v8/v8pre `Branwen/Scripts/AR0500.baf:10` creates `O#Bran`; `branwen.tp2:337` registers BG2-only continuity and removes the original BG1 Fate Spirit entry. | Optional adapter candidate; do not advertise implemented continuity without a bridge. |
| Safana → Safana in Amn | Safana v0.5 `Safana/Extend/ar0311.baf:9` moves the existing `SAFANA` to `AR0311`, then assigns `SAFANA2` script/dialogue. No inventory destruction occurs in the original block. | Actor progression already survives. Component 189 adds one-time cleanup; live acceptance pending. |
| Sirene BG1/SoD → BG2 | Same DV `C0Sirene`. Unversioned `sirene_bg2/scripts/ar0903_e.baf:14` moves the actor; line 19 calls `DestroyAllEquipment()`, followed by basic/native equipment. `lib/Sirene_BG2.tpa:1071` registers type 3 if the BG1 CRE exists, otherwise type 2. | Preserve native move and cleanup. BG1 support is conditional on the separate package being selected. |
| Aura BG1/SoD → BG2 | Same DV `C0Aura`. Unversioned `aura_bg1_2_eet/scripts/BG2EE/c0auf1_e.baf:17` moves the actor; line 22 destroys fragile droppable equipment, then recreates/upgrades native gear. | Preserve native continuity and its item exceptions. The transfer adds WIS +2 intentionally; `C0AUREET.SPL` contains portrait changes only. |
| Evandra, Fade, Pai'Na, Sarah SoA → ToB | Native type-2 registrations: Evandra v2.2 `setup-evandra.tp2:138`, DV `rh#Eva`; Fade v5.6 `Setup-Fade.tp2:458`, DV `E3Fade`; Pai'Na v1.9 source snapshot `Paina.tp2:316`, DV `C0Paina`; Sarah v8 `lib/sarah_main.tpa:133`, DV `K#SARAH`. | BG2-only companions with existing EET continuity. No BG1 actor to bridge. Fade also has a separate romance Fate Spirit path requiring acceptance coverage. |

Canonical upstream sources: [EET](https://github.com/Gibberlings3/EET),
[Xan](https://github.com/Pocket-Plane-Group/Xan_for_BGII),
[Yeslick](https://github.com/Spellhold-Studios/Yeslick-NPC),
[Branwen](https://github.com/Pocket-Plane-Group/Branwen_for_BGII),
[Safana in Amn](https://github.com/RoxanneSHS/SafanaBG2),
[Sirene BG2](https://github.com/TheArtisanBG/Sirene-NPC-for-BG2-EE),
[Aura](https://github.com/TheArtisanBG/Aura_BG1_BG2_EET),
[Fade](https://github.com/Spellhold-Studios/Fade-NPC),
[Pai'Na](https://github.com/TheArtisanBG/Pai-Na-NPC-mod-for-BG2-EE),
[Sarah](https://github.com/Gibberlings3/Sarah). Evandra's collection acquisition route
is the author's G3 download, supplied manually; do not redistribute the local package.

## Native exceptions and compatibility

- EET changes Minsc's alignment to Chaotic Good and racial enemy to `HATEDRACE=125`
  when he arrives in SoA (`EET/lib/bg2_BCS.tph:2198`). These explicit campaign changes
  are separate from accidentally replacing player-earned attributes or skill points.
  The adjacent old Dexterity floor block is commented out in the inspected source.
- Imoen has native automatic dual-class and XP handling. The class/XP result depends
  on her existing class, original class and levels; `EET/lib/bg1_BCS.tph:231` begins
  the dual-class XP adjustment logic. Test both an untouched thief and a player-dualed
  Imoen. A generic continuity patch must not blindly restore an earlier class or XP
  total over intentional campaign progression. Incompatible custom-class cases need
  an explicit adapter policy.
- Component 199 preserves the original build. It does not apply the BG2 template's
  stat/kit defaults or copy its spell/effect lists onto the returning actor. Native
  scripted campaign progression still runs. Cross-mod quest-local interactions and
  alternate-class routes are part of the live acceptance matrix below.
- Legacy `BG2EE-EET-FIXPACK` component **200** is unsafe and must conflict with the
  replacement. Its `components/stat_transfer/lua/M_K#FP.lua` captures displayed
  active-minus-template attribute differences, including buffs and equipped items,
  then misuses opcode 44 as a general attribute modifier. It covers only Branwen,
  Xan, Ajantis and Yeslick, and does not transfer learned spells or thief skills.
  Do not run both systems or treat its previous success messages as verification.

## Acceptance matrix

Use a disposable EET installation and a new BG1 campaign with the supported mods and
components installed before the relevant actors are created. Record effective versions,
class choices and save names. Inspect saved base state as well as the character screen;
an accepted Lua/script queue alone does not prove an applied, persisted result.

| Case | Required observation |
|---|---|
| BG1 progression and save/load | Spend an attribute tome, teach a mage/bard a distinguishable spell, assign thief points and proficiencies where applicable. Save/reload and record base attributes, known spells, skill allocation and class/levels. Include exceptional Strength when applicable. |
| BG1 → SoD → SoA → ToB | Compare those records at each implemented route, before and after recruitment and a save/reload. Each upgrade survives once; intentional native growth remains. Repeat departure/rejoin and area visits to detect repeated grants. |
| Dismissed companion | Recruit, develop, dismiss in an earlier area, then advance the campaign. The last persistent development survives when that companion returns; capture must not require being in the current party or visible area. |
| Never recruited / direct SoA or ToB start | Use the mod's normal fresh spawn and loadout. Do not import unrelated actor data or invent prior tome/spell gains. |
| Death paths | Test recoverable death and irreversible death separately. Preserve each mod's recruitment/resurrection rules; a transfer must not create duplicate or unexpectedly resurrected companions. |
| Equipment handed over before SoA | Give Safana strong equipped items, backpack items and a container immediately before her transition, including when dismissed. The imported loadout is cleared before BG2 recruitment. Check undroppable/plot slots separately against the actual engine action. |
| Equipment handed over after arrival | Give new equipment after the BG2 arrival has completed; save/reload, revisit and rejoin. Those later items remain. Sirene's basic equipment and Aura's explicit native exceptions are retained. |
| Class/kit mismatch | Test native classes, selected collection conversions, dual class and incompatible source/target classes. No illegal spellbook, duplicated innate grants, discarded trained skills or silently overwritten kit. Any unsupported configuration is reported rather than guessed. |
| Equipment/buff stat inflation | Apply a temporary attribute buff and equip a stat-setting item during a candidate capture point. After removal/expiry, only permanent base development remains. |

These remain acceptance requirements, **not completed live tests**.
Installer fixtures can establish bounded patch matching, dependency handling,
idempotence and uninstall restoration; they cannot prove the in-game transition result.

## Recorded installer verification

On 2026-09-06, **25 tests passed** with WeiDU **24900**. All TP2/TPA parse checks
and `git diff --check` also passed. The run enabled optional read-only copies of
the installed Safana arrival and Xan/Yeslick donor resources. The old live
stat-transfer hooks correctly caused those unmodified Xan/Yeslick area scripts
to be rejected; the audited original spawn fixtures passed with the effective
donor scripts, dialogue, personal item and 100 sound slots. No live installation
or save was modified.

Tests cover public component dispatch and prerequisites, both arrival branches,
typed identity references versus similarly named resources, CRE/effect/embedded
area byte preservation, interaction tables and item restrictions, unexpected
source shapes, partial-install rollback, and byte-exact uninstall/reinstall.
CI fetches EET v14.0's parser at commit
`ad20ca29ae797e773fffb10c25537c1b1a674716`; it matches the inspected local parser.

To repeat with your own paths in PowerShell:

```powershell
$env:WEIDU = 'C:\path\to\weidu.exe'
$env:CBM_EET_SOURCE = 'C:\path\to\EET'
python -m unittest discover -s tests -v
```

Optional `CBM_SAFANA_GAME` and `CBM_CONTINUITY_GAME` point to an installed game
for the additional read-only source checks. Every installer mutation occurs in
temporary synthetic games. This suite does not run EET_end on a full mod stack
or execute the generated actions inside the native game engine.
