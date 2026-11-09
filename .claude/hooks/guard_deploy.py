#!/usr/bin/env python3
"""PreToolUse (Bash): refuse to deploy while the test suite is failing."""
import re
import sys

from common import read_payload, run_suite

# Matches a command being run, not a mention of it inside a commit message.
DEPLOY = re.compile(r"(^|[;&|]\s*)(?:(?:bash\s+)?(?:\./)?)deploy\.sh\b|\bgcloud\s+run\s+deploy\b")


def main():
    command = read_payload().get("tool_input", {}).get("command", "")
    if not DEPLOY.search(command):
        return 0
    passed, output = run_suite()
    if passed:
        return 0
    print(f"Deploy blocked: tests are failing.\n{output}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
