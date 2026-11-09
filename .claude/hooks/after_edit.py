#!/usr/bin/env python3
"""PostToolUse (Edit|Write): run the tests after code changes and report failures.

Exit 2 shows stderr to Claude; the edit stays in place, so red tests during TDD
are feedback rather than a block.
"""
import sys
from pathlib import PurePosixPath

from common import read_payload, run_suite


def is_code(path):
    parts = PurePosixPath(path)
    return parts.suffix in {".py", ".sh"} or {"templates", "static"}.intersection(parts.parts)


def main():
    path = read_payload().get("tool_input", {}).get("file_path", "")
    if not is_code(path):
        return 0
    passed, output = run_suite()
    if passed:
        return 0
    print(f"Tests are failing after editing {path}:\n{output}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
