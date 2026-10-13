"""Shipped Lua never concatenates values into EEex assembly text.

EEex writes number elements of an assembly table exactly (EEex_ToDecStr). The
game's Lua 5.2 coerces numbers in string concatenation with "%.14g", so a
15-digit 64-bit DLL address becomes lossy scientific notation such as
"call 1.4070581297618e+14", which EEex's assembler rejects (first seen live on
2026-10-13: "EEex_JITNear() failed: InvalidState" during banking startup).
Values must stay separate table elements next to the assembly strings.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = sorted((ROOT / "chriz-bg-modpack").rglob("*.lua"))
LITERAL = r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\''
ASSEMBLY = re.compile(r"#ENDL|^[\"']\s*(?:mov|movabs|call|jmp|lea|push|pop|sub|add|cmp|test|xor|and|or)\b")
AFTER_LITERAL = re.compile(rf"({LITERAL})\s*\.\.\s*(\S)")
BEFORE_LITERAL = re.compile(rf"(\S)\s*\.\.\s*({LITERAL})")


def concatenated_assembly(text):
    """Line numbers where an assembly string literal is joined to something other than a literal."""
    found = set()
    for match in AFTER_LITERAL.finditer(text):
        if ASSEMBLY.search(match.group(1)) and match.group(2) not in "\"'":
            found.add(text.count("\n", 0, match.start()) + 1)
    for match in BEFORE_LITERAL.finditer(text):
        if ASSEMBLY.search(match.group(2)) and match.group(1) not in "\"'":
            found.add(text.count("\n", 0, match.start()) + 1)
    return sorted(found)


def test_detector_flags_the_live_failure_and_allows_literal_joins():
    live = 'assembly[#assembly+1]="call "..at.." #ENDL mov edx,eax #ENDL"\n'
    register = 'x="mov "..({"rcx","rdx"})[i]..", "..tostring(value).." #ENDL"\n'
    literal_join = 'return "mov qword ptr ss:[rsp+32], 0 #ENDL "..\n    "call #L(Hardcoded_lua_pcallk)"\n'
    message = 'assert(ok,"Missing writer callback: "..name)\n'
    table = 'assembly[#assembly+1]="call ";assembly[#assembly+1]=at\n'
    assert concatenated_assembly(live) == [1]
    assert concatenated_assembly(register) == [1]
    assert concatenated_assembly(literal_join + message + table) == []


def test_shipped_lua_exists():
    assert any("xp-banking-native" in path.as_posix() for path in SHIPPED)


@pytest.mark.parametrize("path", SHIPPED, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_assembly_values_are_table_elements(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    found = concatenated_assembly(text)
    assert not found, f"pass numbers as assembly table elements, not via '..' (lines {found})"
