"""Shipped Lua writes code bytes with EEex's unsigned writers.

InfinityLoader range-checks every typed write (castLuaIntArg): EEex_Write8 is
int8 and refuses anything above 127, EEex_Write16 refuses anything above
32767. Code bytes and opcodes are 0-255, so a signed byte write fails in the
real game (first seen live on 2026-10-13: "arg #2 (139) too large (max: 127)"
during banking startup and again during its rollback) while lenient test
doubles accept it.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = sorted((ROOT / "chriz-bg-modpack").rglob("*.lua"))
SIGNED_SMALL = re.compile(r"\bEEex_Write(8|16)\b")


def test_shipped_lua_exists():
    assert any("xp-banking-native" in path.as_posix() for path in SHIPPED)


@pytest.mark.parametrize("path", SHIPPED, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_no_signed_byte_or_word_writes(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    found = [text.count("\n", 0, match.start()) + 1 for match in SIGNED_SMALL.finditer(text)]
    assert not found, f"use EEex_WriteU8/EEex_WriteU16 for code bytes (lines {found})"
