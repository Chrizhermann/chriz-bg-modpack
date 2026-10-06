# Edwin: Red Wizard slots and amulet

**Component 236** — `cbm_edwin_redwizard`.

When Artisan's Red Wizard conversion is selected, Edwin receives the kit's
promised **two extra wizard slots per accessible spell level**: one from native
specialization and one from the kit. His amulet adds no slots and can be removed.
This corrects the selected kit; it does not enable Red Wizard or rebalance
ordinary Conjurer Edwin by itself.

## Installation

Install **immediately after Artisan's NPC component 5102**, before Spell Revisions
component **60** if used, and before other later NPC spellbook writers. SR's main
component can already be installed. The missed EET template receives the same
original spell removals as Artisan's conversion, at that conversion's stage;
the final SR spellbook pass must come afterward. Installing after SR 60 is refused.

This component does not require EEex. It requires the installed `C0REDWIZ` kit
and `C0REDWIZ.2DA`. The kit ID is resolved from the installed `KIT.IDS`.

## Scope

- `MISC89.ITM` and EET's `MISC89_.ITM`: set the movable flag, clear cursed if
  present, and neutralize equipped wizard-slot bonuses. Preserve other effects
  and activated abilities. Remove only the amulet's undroppable instance flags
  in the affected Edwin templates.
- Edwin's 11 known recruitment templates: remove only source-less permanent
  +2 single-spell-level effects inherited from vanilla. Preserve unrelated
  effects, stats, XP, level, inventory, identity and scripts.
- EET's `EDWIN7_`: extend the selected Artisan conversion if this template is
  still a mage/Conjurer. A different explicit class/kit conversion is preserved.
- Add one level-one Red Wizard CLAB grant, `AP_CBMEDSL`. The generated spell
  gives +1 for each wizard spell level; it does not unlock inaccessible levels.

The repair does not normalize arbitrary slot bonuses from other mods. An older
private `C0REDW4` correction or a conflicting `CBMEDSL` resource is refused, not
overwritten or stacked. Uninstall that older correction using its own installer
before choosing this component. Do not remove resources or fake WeiDU log rows.

## Existing saves

Recruitment templates are not saved actors. Already-created Edwin retains his
saved spell-slot state; installing this component is not a save migration.
The item change is read after a restart, but effects from already-equipped gear
may need unequip/re-equip. Never repeatedly replay permanent slot grants on an
existing actor. No live game or save is modified by the automated tests.

## Verification and provenance

Real WeiDU 249 generated-fixture tests cover both creature effect formats,
reordered resource blocks, all 11 variants, kit-ID relocation, partial games,
unrelated fields/effects, item ability preservation, repeat application,
prerequisite/order guards, failure rollback and byte-exact uninstall.
This is installer/resource evidence, not native recruitment or slot-screen
acceptance. The original October 3 private repair was separately tested on
captured resources before application; no captured files are distributed here.

The affected CRE/amulet names originate in the games; EET adds the underscore
variants. Artisan's `redwizard.tpa` owns the selected kit conversion and amulet
replacement. CBMEDSL is generated from this mod's source, not copied from a
third-party binary.
