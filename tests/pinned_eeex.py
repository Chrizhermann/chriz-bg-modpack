"""The pinned EEex v1.3.1 scripts that tests run, and the one way to find them.

Both workflows fetch exactly PINS from Bubb13/EEex at COMMIT, check each sha256, and
point CBM_EEEX_SOURCE at the folder that holds EEex/copy/EEex_scripts/
(tests/test_ci_pytest_selection.py keeps the three in step and checks that nothing
in the CI selection reads EEex files another way). To run these tests locally, set
CBM_EEEX_SOURCE to a folder with that layout and the files as they are at COMMIT,
for example the raw files or `git show COMMIT:<path>` from a checkout (a checkout
that converts line endings changes their sha256). With it set, a missing script or
one with another sha256 is a failure; without it, the test is skipped. There is no
local default path.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

VARIABLE = "CBM_EEEX_SOURCE"
COMMIT = "a6d21abe44e20509f5d0259ccc6c7e7f9d12b285"
PINS = {
    "EEex_Action.lua": "18ea2ed7974984d7da66ac315ca035574cc4faa2802f55c4f431efca2862787b",
    "EEex_Keybinds.lua": "0a0ff929beaffc8e5c1b039175600c286cc6816334052b92d648414eb5e14887",
    "EEex_Menu.lua": "13097865d63812e6b006812b21f4d874ee4a1651b2e93c6f2ba551c976732702",
    "EEex_Sprite.lua": "60c48e00d7682be7716306fa10a868f079cb55bec77175467ec316b74354a8be",
}


def pinned_eeex_script(name: str) -> Path:
    """The pinned EEex script `name` under CBM_EEEX_SOURCE; call it from a test or fixture, not at import."""
    if name not in PINS:
        pytest.fail(f"{name} is not pinned: add it to tests/pinned_eeex.py and to both workflows' EEex fetch")
    root = os.environ.get(VARIABLE)
    if not root:
        pytest.skip(f"set {VARIABLE} to the pinned EEex v1.3.1 scripts (commit {COMMIT[:8]}) to run this test")
    path = Path(root) / "EEex" / "copy" / "EEex_scripts" / name
    if not path.is_file():
        pytest.fail(f"{VARIABLE} has no EEex/copy/EEex_scripts/{name}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != PINS[name]:
        pytest.fail(f"{path} has sha256 {digest}, not the pinned {PINS[name]}")
    return path
