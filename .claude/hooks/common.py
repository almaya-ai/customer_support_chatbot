"""Shared helpers for this project's Claude Code hooks (stdlib only, no jq here)."""
import json
import os
import subprocess
import sys
from pathlib import Path


def project_dir():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))


def read_payload():
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError:
        return {}


def run_suite():
    """Return (passed, tail of output). HOOK_TEST_COMMAND replaces unittest in tests."""
    project = project_dir()
    command = os.environ.get("HOOK_TEST_COMMAND") or f'"{project}/.venv/bin/python" -m unittest discover -s tests -q'
    result = subprocess.run(
        command, shell=True, cwd=project, capture_output=True, text=True, timeout=120
    )
    return result.returncode == 0, (result.stdout + result.stderr)[-1500:]
