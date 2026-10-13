# Degrodel: hand over the Helm of Balduran or fight him

Component **660**, label `cbm_degrodel_fight`, is optional and unreleased (after
v0.2.0-alpha.11). It supports EET and BG:EE and needs Degrodel's dialog
`DEGROD.DLG`. EEex and SCS are not required.

## In game

Normally Degrodel takes the Helm of Balduran as soon as you bring it to him: he
pays 5,000 gold, leaves, and his servants attack. You get no say.

With 660 you answer him instead:

- **"Here is the helm, as we agreed."** Exactly the normal outcome: gold, the
  helm is taken, his servants appear, the quest is solved and he leaves.
- **"No. The Helm of Balduran stays with us."** Degrodel pays nothing, takes
  nothing and stays. He turns hostile and fights you together with the same
  servants. You keep the helm, and killing him gives his normal equipment and
  experience. The quest's open journal entries close with a short note that
  you refused him.

The servants are whatever the installed hand-in creates, so EET's renamed
stalker, SCS's stronger servants and other mods' changes carry over. No extra
difficulty is added. Degrodel fights with his normal scripts, including SCS's
mage AI when SCS is installed.

## Installation and compatibility

Install after mods that change Degrodel's dialog or his hand-in. Uninstalling
restores the previous `DEGROD.DLG`. The new lines stay in `dialog.tlk`, as
usual for WeiDU, without affecting anything.

The installer finds the hand-in by what it does: the one reply that takes the
helm from the party and makes Degrodel leave. It does not depend on state
numbers, exact wording or action order, and it leaves companion interjections
on other parts of the conversation unchanged. If the hand-in cannot be
identified safely, the installer explains why, changes nothing, and the
component is not recorded as installed. This happens when there is no hand-in,
more than one, a companion interjection directly on the hand-in, or the choice
is already present.

Refusing also sets the global `CBMDegrodelFight` to 1. A later difficulty option
can use that, or extend the fight path in `cbm_degrodel_fight_actions`.

## Testing status

Synthetic WeiDU tests cover vanilla, BG:EE and EET-shaped dialogs, BG1NPC-style
interjections, dialogs rewritten by other tools, extra and reordered actions,
the skip cases, reinstalling and uninstalling. The fight has not yet been played
in game, with or without SCS.
