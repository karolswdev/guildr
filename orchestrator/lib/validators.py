"""Phase validators — structural checks on phase outputs.

Full implementation in Task 3.
"""

from __future__ import annotations

from orchestrator.lib.state import State
from orchestrator.lib.sprint_plan import parse_tasks


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
    """Every task's declared files exist after Coder runs."""
    path = state.project_dir / "sprint-plan.md"
    if not path.exists():
        return False, "sprint-plan.md not written"
    content = path.read_text()
    tasks = parse_tasks(content)
    if not tasks:
        # No tasks defined — trivially passes
        return True, ""
    for task in tasks:
        if not task.files:
            return False, f"task-{task.id} declares no files"
        missing = [
            file
            for file in task.files
            if not (state.project_dir / file).exists()
        ]
        if missing:
            return False, f"task-{task.id} missing files: {', '.join(missing)}"
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
