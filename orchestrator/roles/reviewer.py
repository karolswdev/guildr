"""Reviewer role — code-review-grade pass against sprint plan."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Any

from orchestrator.lib.llm import LLMClient
from orchestrator.lib.sprint_plan import Task, parse_tasks
from orchestrator.lib.state import State
from orchestrator.roles.base import BaseRole

logger = logging.getLogger(__name__)


class ReviewerError(Exception):
    """Raised when the Reviewer encounters a fatal error."""


@dataclass
class CriterionResult:
    """Result for a single acceptance criterion."""

    text: str
    verdict: str  # PASS | FAIL | CONCERN
    notes: str


@dataclass
class ReviewResult:
    """Overall review result."""

    criteria: list[CriterionResult]
    overall: str  # APPROVED | APPROVED_WITH_NOTES | CHANGES_REQUESTED | CRITICAL


class Reviewer(BaseRole):
    """Reviews implementation against sprint plan without re-running tests."""

    _phase: str = "review"
    _role: str = "reviewer"

    def __init__(
        self,
        llm: LLMClient,
        state: State,
        phase_logger: Any = None,
    ) -> None:
        super().__init__(llm, state, phase_logger=phase_logger)

    # -- public API ----------------------------------------------------------

    def execute(
        self,
        sprint_plan_path: str = "sprint-plan.md",
        test_report_path: str = "TEST_REPORT.md",
    ) -> str:
        """Execute review on the current implementation.

        Returns the path to REVIEW.md.
        Raises ReviewerError on fatal failure.
        """
        plan_text = self.state.read_file(sprint_plan_path)
        tasks = parse_tasks(plan_text)

        acceptance_criteria = self._extract_criteria(tasks)
        test_report = self._load_test_report(test_report_path)
        git_diff_summary = self._get_git_diff_summary()

        system_prompt = self._load_prompt("reviewer", "generate")
        user_prompt = system_prompt.format(
            acceptance_criteria=acceptance_criteria,
            test_report=test_report,
            git_diff_summary=git_diff_summary,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self._chat(messages)
        except Exception as exc:
            raise ReviewerError(f"LLM call failed: {exc}") from exc

        result = self._parse_result(response.content)
        self._write_review(result)
        return "REVIEW.md"

    # -- data extraction -----------------------------------------------------

    @staticmethod
    def _extract_criteria(tasks: list[Task]) -> str:
        """Extract acceptance criteria from all tasks."""
        lines = []
        has_criteria = False
        for task in tasks:
            lines.append(f"### Task {task.id}: {task.name}")
            for criterion in task.acceptance_criteria:
                lines.append(f"- {criterion}")
                has_criteria = True
            lines.append("")
        if not has_criteria:
            return "No acceptance criteria found."
        return "\n".join(lines)

    def _load_test_report(self, path: str) -> str:
        """Load TEST_REPORT.md content."""
        try:
            return self.state.read_file(path)
        except FileNotFoundError:
            return "No test report available."

    @staticmethod
    def _get_git_diff_summary() -> str:
        """Get a git diff summary (headlines per file, not full diffs)."""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", "HEAD"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return "No git diff available."

    # -- result parsing ------------------------------------------------------

    def _parse_result(self, raw: str) -> ReviewResult:
        """Parse the Reviewer's markdown output into a ReviewResult."""
        criteria: list[CriterionResult] = []

        # Parse per-criterion verdicts
        # Handles both formats:
        #   - [PASS] Criterion: text
        #   - [PASS] text
        criterion_pattern = re.compile(
            r"- \[(PASS|FAIL|CONCERN|CRITICAL)\]\s+"
            r"(?:Criterion:\s*)?"
            r"(.+?)"
            r"(?:\n\s*- Notes:\s*(.+?))?(?=\n- \[|\Z)",
            re.DOTALL,
        )
        for m in criterion_pattern.finditer(raw):
            verdict = m.group(1)
            text = m.group(2).strip()
            notes = m.group(3).strip() if m.group(3) else ""
            criteria.append(CriterionResult(
                text=text,
                verdict=verdict,
                notes=notes,
            ))

        # Parse overall verdict
        overall_match = re.search(
            r"## Overall\s*\n\s*[-•]?\s*"
            r"(APPROVED(?:\s+WITH\s+NOTES)?|"
            r"CHANGES_REQUESTED|CRITICAL)",
            raw,
            re.IGNORECASE,
        )
        if overall_match:
            overall = overall_match.group(1).strip().upper()
            # Normalize "APPROVED WITH NOTES" → "APPROVED_WITH_NOTES"
            if overall == "APPROVED WITH NOTES":
                overall = "APPROVED_WITH_NOTES"
        else:
            overall = "CHANGES_REQUESTED"

        return ReviewResult(
            criteria=criteria,
            overall=overall,
        )

    # -- report writing ------------------------------------------------------

    def _write_review(self, result: ReviewResult) -> None:
        """Write REVIEW.md with per-criterion verdicts."""
        lines = [
            "# Review",
            "",
            f"Overall verdict: {result.overall}",
            "",
        ]

        for cr in result.criteria:
            lines.append(f"- [{cr.verdict}] {cr.text}")
            if cr.notes:
                lines.append(f"  - Notes: {cr.notes}")

        lines.append("")
        lines.append("## Overall")
        lines.append("")
        lines.append(result.overall)
        if result.overall in ("CHANGES_REQUESTED", "CRITICAL"):
            lines.append("")
            lines.append("Required changes:")
            for cr in result.criteria:
                if cr.verdict in ("FAIL", "CRITICAL"):
                    lines.append(f"- {cr.text}: {cr.notes}")

        report = "\n".join(lines)
        self.state.write_file("REVIEW.md", report)

    # -- convenience ---------------------------------------------------------

    def is_critical(self, sprint_plan_path: str = "sprint-plan.md") -> bool:
        """Check if the current review is CRITICAL.

        Returns True if REVIEW.md exists and has CRITICAL verdict.
        """
        try:
            review_text = self.state.read_file("REVIEW.md")
            return "CRITICAL" in review_text
        except FileNotFoundError:
            return False
