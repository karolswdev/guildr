"""Tester role — independently re-verifies Coder's Evidence Log."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Any

from orchestrator.lib.llm import LLMClient
from orchestrator.lib.sprint_plan import (
    Task,
    apply_evidence_patch,
    parse_tasks,
    slice_task,
)
from orchestrator.lib.state import State
from orchestrator.roles.base import BaseRole

logger = logging.getLogger(__name__)


class TesterError(Exception):
    """Raised when the Tester encounters a fatal error."""


@dataclass
class TaskResult:
    """Result of verifying a single task."""

    task_id: int
    task_name: str
    status: str  # VERIFIED | MISMATCH | RERUN_FAILED
    evidence: list[dict[str, str]]
    notes: str = ""


class Tester(BaseRole):
    """Independently re-verifies Coder's Evidence Log entries."""

    _phase: str = "testing"
    _role: str = "tester"

    def __init__(
        self,
        llm: LLMClient,
        state: State,
        phase_logger: Any = None,
    ) -> None:
        super().__init__(llm, state, phase_logger=phase_logger)

    # -- public API ----------------------------------------------------------

    def execute(self, sprint_plan_path: str = "sprint-plan.md") -> str:
        """Execute verification on all tasks with filled Evidence Logs.

        Returns the path to TEST_REPORT.md.
        Raises TesterError on fatal failure.
        """
        plan_text = self.state.read_file(sprint_plan_path)
        tasks = parse_tasks(plan_text)

        if not tasks:
            logger.warning("No tasks found in sprint plan")
            self._write_report(sprint_plan_path, [])
            return "TEST_REPORT.md"

        results: list[TaskResult] = []
        for task in tasks:
            # Only verify tasks with at least one [x] (checked) evidence entry
            if not any(e.get("passed", False) for e in task.evidence_log):
                continue
            logger.info("Tester: verifying task %d: %s", task.id, task.name)
            result = self._verify_task(plan_text, task, sprint_plan_path)
            results.append(result)

        self._write_report(sprint_plan_path, results)
        return "TEST_REPORT.md"

    def verify_task(self, sprint_plan_path: str, task_id: int) -> TaskResult:
        """Verify a single task by ID.

        Returns the TaskResult for the task.
        Raises TesterError if the task is not found or has no evidence log.
        """
        plan_text = self.state.read_file(sprint_plan_path)
        tasks = parse_tasks(plan_text)
        target = None
        for t in tasks:
            if t.id == task_id:
                target = t
                break

        if target is None:
            raise TesterError(f"Task {task_id} not found in sprint plan")
        if not any(e.get("passed", False) for e in target.evidence_log):
            raise TesterError(
                f"Task {task_id} has no Evidence Log to verify"
            )

        return self._verify_task(plan_text, target, sprint_plan_path)

    # -- task verification ---------------------------------------------------

    def _verify_task(
        self, plan_text: str, task: Task, sprint_plan_path: str
    ) -> TaskResult:
        """Verify a single task: call LLM, parse result, write report."""
        sliced = slice_task(plan_text, task.id)
        evidence_log_text = self._format_evidence_log(task.evidence_log)

        system_prompt = self._load_prompt("tester", "generate")
        user_prompt = system_prompt.format(
            task=sliced,
            evidence_log=evidence_log_text,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self._chat(messages)
        except Exception as exc:
            raise TesterError(
                f"LLM call failed for task {task.id}: {exc}"
            ) from exc

        result = self._parse_result(response.content, task)
        return result

    # -- evidence log formatting ---------------------------------------------

    @staticmethod
    def _format_evidence_log(entries: list[dict[str, Any]]) -> str:
        """Format evidence log entries for the prompt."""
        lines = []
        for i, entry in enumerate(entries, 1):
            check = entry.get("check", "")
            output = entry.get("output", "")
            passed = entry.get("passed", False)
            marker = "[x]" if passed else "[ ]"
            line = f"- {marker} {check}"
            if output:
                line += f", output recorded: ```{output}```"
            lines.append(line)
        return "\n".join(lines)

    # -- result parsing ------------------------------------------------------

    def _parse_result(self, raw: str, task: Task) -> TaskResult:
        """Parse the Tester's markdown result into a TaskResult."""
        # Extract status
        status_match = re.search(
            r"Status:\s*(VERIFIED|MISMATCH|RERUN_FAILED)", raw
        )
        status = status_match.group(1) if status_match else "RERUN_FAILED"

        # Extract evidence items
        evidence: list[dict[str, str]] = []
        evidence_matches = re.finditer(
            r"Evidence\s+\d+:\s*(PASS|FAIL)\s*—\s*(.+?)(?=\n-|\n\n|\Z)",
            raw,
            re.DOTALL,
        )
        for m in evidence_matches:
            evidence.append({
                "result": m.group(1),
                "output": m.group(2).strip(),
            })

        # Extract notes
        notes_match = re.search(r"Notes:\s*(.+?)(?:\n\n|\Z)", raw, re.DOTALL)
        notes = notes_match.group(1).strip() if notes_match else ""

        return TaskResult(
            task_id=task.id,
            task_name=task.name,
            status=status,
            evidence=evidence,
            notes=notes,
        )

    # -- report writing ------------------------------------------------------

    def _write_report(
        self, sprint_plan_path: str, results: list[TaskResult]
    ) -> None:
        """Write TEST_REPORT.md with per-task status."""
        lines = [
            "# Test Report",
            "",
            f"Tasks verified: {len(results)}",
            "",
        ]

        for r in results:
            lines.append(f"### Task {r.task_id}: {r.task_name}")
            lines.append(f"- Status: {r.status}")
            for i, ev in enumerate(r.evidence, 1):
                lines.append(f"- Evidence {i}: {ev['result']} — {ev['output']}")
            if r.notes:
                lines.append(f"- Notes: {r.notes}")
            lines.append("")

        report = "\n".join(lines)
        self.state.write_file("TEST_REPORT.md", report)

        # Also update the sprint plan with verification status
        plan_text = self.state.read_file(sprint_plan_path)
        for r in results:
            if r.status == "VERIFIED":
                # Mark evidence log entries as verified
                patch = {
                    "task_id": r.task_id,
                    "entries": [
                        {
                            "check": f"Verified by Tester",
                            "output": r.status,
                            "passed": True,
                        },
                    ],
                }
                plan_text = apply_evidence_patch(plan_text, patch)

        self.state.write_file(sprint_plan_path, plan_text)

    # -- helper: run shell command -------------------------------------------

    @staticmethod
    def _run_cmd(cmd: str, timeout: int = 120) -> tuple[int, str]:
        """Run a shell command and return (returncode, stdout)."""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return -1, f"Command timed out after {timeout}s"
        except Exception as exc:
            return -1, str(exc)
