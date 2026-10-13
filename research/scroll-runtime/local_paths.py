"""Local game files are recorded by folder variable, never by this machine's folders.

Set BG2EE_266_ROOT and BG2EE_273_ROOT to the local game folders. Evidence keeps the
%VARIABLE% form; readers expand it. Other paths under the user profile are recorded
with %USERPROFILE%.
"""
import os
from pathlib import Path, PureWindowsPath

ROOTS = ("BG2EE_266_ROOT", "BG2EE_273_ROOT")


def recorded(path):
    target = Path(path).absolute()
    for name in ROOTS:
        folder = os.environ.get(name)
        if folder:
            base = Path(folder).absolute()
            if target == base or base in target.parents:
                return str(PureWindowsPath(f"%{name}%", *target.relative_to(base).parts))
    home = Path.home()
    if home in target.parents:
        return str(PureWindowsPath("%USERPROFILE%", *target.relative_to(home).parts))
    return str(path)


def resolve(text):
    return Path(os.path.expandvars(text))
