"""Run the CI pytest selection: the files listed in tests/ci-pytest.txt plus any extra pytest arguments.

Usage, from the repository root (both CI workflows run pytest only this way):
  python -m tools.ci_pytest [extra pytest arguments]
Exits with pytest's status, or 2 when the selection lists a file that does not exist.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "tests" / "ci-pytest.txt"


def selection(path: Path | None = None) -> list[str]:
    """The listed test paths in file order; blank lines and # comment lines are skipped."""
    lines = (line.strip() for line in (path or SELECTION).read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def main(argv: list[str] | None = None) -> int:
    files = selection()
    missing = [f for f in files if not (ROOT / f).is_file()]
    if missing:
        print("ci_pytest: the selection %s lists missing files: %s" % (SELECTION, ", ".join(missing)), file=sys.stderr)
        return 2
    import pytest

    return int(pytest.main([str(ROOT / f) for f in files] + list(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":
    sys.exit(main())
