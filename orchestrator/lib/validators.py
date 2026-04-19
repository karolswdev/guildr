"""Phase validators — structural checks on phase outputs.

Full implementation in Task 3.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from orchestrator.lib.state import State


def validate_architect(state: State) -> tuple[bool, str]:
    """Returns (passed, failure_reason). Trusts Architect's internal
    self-eval — if sprint-plan.md is written with Evidence Required, it passed."""
    path = state.project_dir / "sprint-plan.md"
    if not path.exists():
        return False, "sprint-plan.md not written"
    content = path.read_text()
    if "Evidence Required:" not in content:
        return False, "no Evidence Required sections"
    return True, ""


def validate_implementation(state: State) -> tuple[bool, str]:
    """Every task has filled Evidence Log."""
    path = state.project_dir / "sprint-plan.md"
    if not path.exists():
        return False, "sprint-plan.md not written"
    content = path.read_text()
    # Parse tasks and check each has at least one [x] evidence entry
    task_pattern = re.compile(r"### Task (\d+): (.+)$", re.MULTILINE)
    matches = list(task_pattern.finditer(content))
    if not matches:
        # No tasks defined — trivially passes
        return True, ""
    for i, match in enumerate(matches):
        task_id = int(match.group(1))
        start = match.start()
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            risks = re.search(r"## Risks", content, re.MULTILINE)
            end = risks.start() if risks else len(content)
        task_body = content[start:end]
        # Check for at least one filled evidence checkbox
        if "[x]" not in task_body:
            return False, f"task-{task_id} has no filled evidence entries"
    return True, ""


def validate_testing(state: State) -> tuple[bool, str]:
    """TEST_REPORT.md has no MISMATCH or RERUN_FAILED."""
    report_path = state.project_dir / "TEST_REPORT.md"
    if not report_path.exists():
        return False, "TEST_REPORT.md not written"
    report = report_path.read_text()
    for bad in ("MISMATCH", "RERUN_FAILED"):
        if bad in report:
            return False, f"TEST_REPORT contains {bad}"
    return True, ""


def validate_review(state: State) -> tuple[bool, str]:
    """REVIEW.md verdict is APPROVED or APPROVED WITH NOTES."""
    review_path = state.project_dir / "REVIEW.md"
    if not review_path.exists():
        return False, "REVIEW.md not written"
    review = review_path.read_text()
    if "CRITICAL" in review:
        return False, "REVIEW marked CRITICAL"
    if "CHANGES REQUESTED" in review:
        return False, "REVIEW requested changes"
    return True, ""
