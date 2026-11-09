#!/usr/bin/env python3
"""SessionStart: add the facts that drive this project's improvement loop."""
import json
import subprocess
import sys

from common import project_dir

READY_MARK = "מוכן לקידום"


def git_state(project):
    result = subprocess.run(
        ["git", "status", "--porcelain", "--branch"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "אין ריפו git בתיקייה"
    lines = result.stdout.splitlines()
    return f"{lines[0].removeprefix('## ')}, קבצים שהשתנו: {len(lines) - 1}"


def ready_candidates(project):
    path = project / "docs" / "skill-candidates.md"
    if not path.exists():
        return 0
    return sum(is_ready(row) for row in path.read_text(encoding="utf-8").splitlines())


def is_ready(row):
    """Only the status cell counts: the mark also appears in the explanation table and in notes."""
    cells = row.split("|")
    return row.startswith("|") and len(cells) > 3 and READY_MARK in cells[3]


def main():
    project = project_dir()
    context = f"git: {git_state(project)}. מוכנים לקידום ל-skill: {ready_candidates(project)}."
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
