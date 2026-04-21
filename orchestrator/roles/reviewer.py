"""Reviewer role — code-review-grade pass via opencode (H6.3c).

The Reviewer runs as an opencode agent session, not a direct LLM call.
It receives the acceptance criteria, the Tester's report, and a git
diff stat summary, and is asked to produce a markdown verdict that we
parse into a :class:`ReviewResult`. Writing ``REVIEW.md`` is still the
orchestrator's job — we don't trust the agent's tool calls for the
report itself because downstream gates parse the exact shape written
here. If a future iteration wants the agent to ``read`` source files
to form its opinion, that works today via opencode's read/grep tools;
only the final verdict text needs to land in the assistant message.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.lib.control import append_operator_context
from orchestrator.lib.opencode import SessionRunner
from orchestrator.lib.opencode_audit import emit_session_audit
from orchestrator.lib.sprint_plan import Task, parse_tasks
from orchestrator.lib.state import State

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


class ReviewerError(Exception):
    """Raised when the Reviewer cannot complete its session."""


@dataclass
class CriterionResult:
    text: str
    verdict: str  # PASS | FAIL | CONCERN | CRITICAL
    notes: str


@dataclass
class ReviewResult:
    criteria: list[CriterionResult]
    overall: str  # APPROVED | APPROVED_WITH_NOTES | CHANGES_REQUESTED | CRITICAL


class Reviewer:
    """Runs one opencode session per review pass and parses the verdict."""

    _phase: str = "review"
    _role: str = "reviewer"

    def __init__(
        self,
        runner: SessionRunner,
        state: State,
        phase_logger: logging.Logger | None = None,
    ) -> None:
        self.runner = runner
        self.state = state
        self._phase_logger = phase_logger

    # -- public API ----------------------------------------------------------

    def execute(
        self,
        sprint_plan_path: str = "sprint-plan.md",
        test_report_path: str = "TEST_REPORT.md",
    ) -> str:
        plan_text = self.state.read_file(sprint_plan_path)
        tasks = parse_tasks(plan_text)

        acceptance_criteria = self._extract_criteria(tasks)
        test_report = self._load_test_report(test_report_path)
        git_diff_summary = self._get_git_diff_summary()

        template = self._load_prompt("reviewer", "generate")
        prompt = template.format(
            acceptance_criteria=acceptance_criteria,
            test_report=test_report,
            git_diff_summary=git_diff_summary,
        )
        prompt = self._augment_prompt(prompt)

        try:
            result = self.runner.run(prompt)
        except Exception as exc:
            raise ReviewerError(f"opencode session failed: {exc}") from exc

        # Emit audit before any failure paths so the trail survives.
        emit_session_audit(
            self.state,
            result,
            role=self._role,
            phase=self._phase,
            step=self._phase,
            prompt=prompt,
        )

        if result.exit_code != 0:
            raise ReviewerError(
                f"opencode session exited with rc={result.exit_code}: "
                f"{result.assistant_text[:200]!r}"
            )

        text = result.assistant_text.strip()
        if not text:
            raise ReviewerError(
                "opencode session returned no assistant text — nothing to parse"
            )

        parsed = self._parse_result(text)
        self._write_review(parsed)
        return "REVIEW.md"

    # -- data extraction -----------------------------------------------------

    @staticmethod
    def _extract_criteria(tasks: list[Task]) -> str:
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
        try:
            return self.state.read_file(path)
        except FileNotFoundError:
            return "No test report available."

    @staticmethod
    def _get_git_diff_summary() -> str:
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
        criteria: list[CriterionResult] = []
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
            criteria.append(CriterionResult(text=text, verdict=verdict, notes=notes))

        overall_match = re.search(
            r"## Overall\s*\n\s*[-•]?\s*"
            r"(APPROVED(?:\s+WITH\s+NOTES)?|"
            r"CHANGES_REQUESTED|CRITICAL)",
            raw,
            re.IGNORECASE,
        )
        if overall_match:
            overall = overall_match.group(1).strip().upper()
            if overall == "APPROVED WITH NOTES":
                overall = "APPROVED_WITH_NOTES"
        else:
            overall = "CHANGES_REQUESTED"

        return ReviewResult(criteria=criteria, overall=overall)

    # -- report writing ------------------------------------------------------

    def _write_review(self, result: ReviewResult) -> None:
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
        self.state.write_file("REVIEW.md", "\n".join(lines))

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _load_prompt(role: str, name: str) -> str:
        return (_PROMPT_DIR / role / f"{name}.txt").read_text(encoding="utf-8")

    def _augment_prompt(self, prompt: str) -> str:
        return append_operator_context(self.state.project_dir, self._phase, prompt)

    # -- convenience ---------------------------------------------------------

    def is_critical(self, sprint_plan_path: str = "sprint-plan.md") -> bool:
        try:
            review_text = self.state.read_file("REVIEW.md")
            return "CRITICAL" in review_text
        except FileNotFoundError:
            return False
