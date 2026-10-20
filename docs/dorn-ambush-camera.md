# Dorn's ambush: no camera lock on Senjak

Component **135**, label `cbm_dorn_ambush_camera_fix`, is an optional fix for
the BG1 campaign. It supports BG:EE (with or without SoD) and EET and needs the
ambush cutscene `CUTDN1B.BCS`. EEex and SCS are not required.

## The problem

When Dorn catches up with Senjak and Dorotea, the cutscene locks the camera on
Senjak and starts the conversation. Only Senjak's own script releases the lock,
and only after the conversation reaches Dorotea's last line ("Attack!") while
Senjak is still neutral.

The conversation does not always get there. Players have reported it stalling
on the Beamdog forums: Senjak and Dorotea stay neutral and never fight. The camera
then stays locked on Senjak. Leaving the area unloads it and deletes him, but
the engine keeps following him and crashes on the next frame (an access
violation in the world screen).

## What the component changes

- **Cutscene `CUTDN1B.BCS`:** both copies of the scene no longer lock the camera.
  The conversation still centres on whoever is speaking, and everything else in
  the scene is unchanged.
- **Senjak's script `SENJACK.BCS`:** a new first block releases the camera once
  Senjak is no longer neutral, whatever made him hostile. It runs once and then
  hands over to his normal blocks. His original hostility block, including its
  own release, is unchanged, so the full conversation still ends with Senjak
  and Dorotea attacking.

A stalled conversation still stalls; the component removes the crash it led
to. You can leave the area, or fight Senjak and Dorotea yourself.

## Installation and compatibility

Install after mods that change these two scripts, such as EET. Uninstalling
restores the previous files.

The installer removes the camera-lock actions from the compiled cutscene
itself. Every other block and action keeps its exact bytes, including other
mods' additions. It does not read area names, so both BG:EE (`AR5800`) and
EET (`BG5800`) work.

- A cutscene without a camera lock is already fixed and stays unchanged.
- Senjak's script is not extended twice.
- Without `SENJACK.BCS`, only the cutscene changes.
- Without `CUTDN1B.BCS` (for example BG2:EE alone), the component is skipped.
- If either script is not a valid compiled script, or a camera-lock action
  cannot be read safely, the installer explains why and changes nothing. The
  component is then not recorded as installed.

Installing during a playthrough is safe: every ambush that has not started yet
uses the changed scripts. Loading a save always clears a camera lock, so a game
saved while the ambush was stuck is also safe once it is loaded again. (The
`OH1000` ambush area itself does not allow saving.)

SCS does not change these scripts, and Spell Revisions does not touch them.
The unused cutscene `CUTDN1A.BCS` also locks the camera on Senjak. Nothing in
BG:EE or EET starts it, so it is left unchanged.

## Testing status

Synthetic WeiDU tests cover BG:EE scripts in BIFF archives and EET scripts in
override, other mods' additions, several and differently placed camera locks,
Windows line endings, already-fixed scripts, the skip and abort cases,
reinstalling and byte-exact uninstalling. The installer also passed on copies
of the original BG:EE scripts and of an EET game's scripts with SCS installed.

The component was also tested in a disposable copy of an EET game with SCS and
EEex (BG2:EE 2.7.3.0). The ambush ran through its normal trigger, from `BG5400`
into `OH1000`:

- **Without 135:** after the cutscene the camera stayed on Senjak until the
  conversation ended. When the conversation was cut short and the party left
  the area, the game crashed with the same access violation as the reported
  crashes. Loading a save cleared the lock.
- **With 135:** the camera was never locked, and during the conversation it
  moved to each speaker. The full conversation still ended with Senjak and
  Dorotea hostile and Dorn on the party's side. With the conversation cut short,
  leaving the area did not crash, and the game kept running normally.
- A camera lock placed on Senjak by hand was released once he turned hostile
  without the conversation, and only once.
- Installing changed only the two scripts. Uninstalling restored them byte for
  byte.

On October 20 the release package was checked again in a copy of the
collection's Recommended install (2.7.3.0, EEex v1.3.1). The camera was never
locked, in the full and in the cut-short conversation, and leaving the area
(by a scripted area move) after the cut-short one did not crash.

Why the conversation stalls in some games is still unknown. In the lab it was
cut short by killing Dorotea before her next line, which ends the conversation
the same way a missing speaker does.
