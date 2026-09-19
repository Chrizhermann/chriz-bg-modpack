# NPC build overrides

Selecting these components applies the chosen build to the named recruitment
templates. They replace the complete standard weapon and fighting-style
allocation, so unlisted proficiencies become zero even when another mod assigned
them. Other effects and fields outside the component's documented changes stay
intact. Stored XP is preserved; its value does not identify a template.

| Component / template | Complete proficiency allocation |
|---|---|
| Mazzy 140: `MAZZY9` | Short Bow 4, Short Sword 3 |
| Mazzy 140: `MAZZY8`, `MAZZY11`, `MAZZY12`, `MAZZY15` | Short Bow 4, Short Sword 4 |
| Xan 170: `XAN4` | Long Sword 2, Dagger 1, Single-Weapon Style 1 |
| Xan 170: `XAN6`, `TTXAN` | Long Sword 2, Dagger 1, Sling 1, Single-Weapon Style 1 |
| Fade 110: `E3FADE13` | Short Sword 2, Katana 1, Dagger 1, Short Bow 1, Two-Weapon Style 1 |
| Fade 110: `E3FADE25` | Short Sword 2, Katana 1, Dagger 1, Short Bow 1, Two-Weapon Style 3 |

These are authored template presets, not a general point-buy algorithm. Selecting
a different template or changing progression tables does not silently replace
the chosen weapon allocation with the incoming creature's preferences.

## Other owned fields

Xan receives the installed Eldritch Knight kit and Fighter/Mage class. Both
class levels are calculated from half his stored total XP using the installed
`XPLEVEL.2DA`. His authored current/maximum HP are 18/21 for `XAN4`, 30/35 for
`XAN6`, and 35/35 for `TTXAN`; previous HP and unused level bytes do not gate the
conversion. THAC0 remains as installed. `XAN_` is handled by Artisan's component
and is outside component 170.

Fade becomes a true-class Fighter/Thief with split levels calculated from half
her stored total XP. Her Hide/Open Locks/Move Silently/Find Traps preset is
70/70/70/80 for `E3FADE13`, and 85/80/80/95 for `E3FADE25`. Other thief skills,
HP and THAC0 are preserved. The amulet change still only clears its
Fighter/Thief usability restriction.

Both conversions clear former dual-class flags. When the installed kit table
identifies a previous kit's ability table, they remove its granted spells and
effects carrying that kit ability's parent-spell metadata. Personal abilities
and unrelated flags remain. Effects without identifiable kit provenance remain;
this is not a general reconstruction of every earlier mod's changes.

Skie's 160/195 repair is a narrow transfer, rather than a complete thief-skill
preset: add her existing Move Silently points to Open Locks, then set Move
Silently to zero. She must be a Swashbuckler. A total above the CRE field's 255
limit cannot be represented and aborts without discarding points.

The shared clearing code removes both set and increment forms of weapon pips.
It preserves EE's repurposed spell-state slots, including stats 109 and 110.
See the [opcode 233 format](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op233).

Sarah keeps her existing complete Archer allocation and uses the same clearing
code. Hexxat Fighter/Thief
uses the complete table-driven allocation described in the
[companion class guide](companion-classes.md). Other kit-only choices retain
their documented scope instead of acquiring unrequested weapon builds.

## Installation and verification

These changes patch resource templates, not actors already stored in a save.
Use the existing component dependencies and installation order in the README.
Normal WeiDU uninstall/reinstall restores the previous resources before applying
the chosen component again.

Tests exercise changed HP, XP, levels and allocations, missing/duplicate records,
repeat application of the fixed presets, and byte-exact uninstall restoration.
These are automated installer checks, not native recruitment or combat tests.
