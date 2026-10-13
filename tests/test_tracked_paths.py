"""Tracked text never names a local user folder.

Evidence records local files as %USERPROFILE% or a folder variable such as
%BG2EE_273_ROOT%, so the public repository and archive carry no user names.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USER_FOLDER = re.compile(
    rb"(?i)\b[a-z]:(?:\\\\|\\|/)+users(?:\\\\|\\|/)+(?!%|public\b|default\b)[^\\/\s\"'`<>|]+"
)


def test_tracked_text_names_no_local_user_folder():
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    offenders = []
    for name in filter(None, listed.split(b"\0")):
        path = ROOT / name.decode("utf-8")
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue
        offenders += [f"{name.decode()}: {m.group(0).decode('utf-8', 'replace')}" for m in USER_FOLDER.finditer(data)]
    assert not offenders, "\n".join(offenders[:20])
