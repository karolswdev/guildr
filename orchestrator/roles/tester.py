"""Tester role — independently runs sprint-plan evidence commands."""

from __future__ import annotations

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
    """Runs Evidence Required commands and records actual outputs."""

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
        """Execute verification on all tasks.

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
        return self._verify_task(plan_text, target, sprint_plan_path)

    # -- task verification ---------------------------------------------------

    def _verify_task(
        self, plan_text: str, task: Task, sprint_plan_path: str
    ) -> TaskResult:
        """Verify a single task by running commands from Evidence Required."""
        commands = self._extract_commands(task.evidence_required)
        evidence: list[dict[str, str]] = []
        evidence_entries: list[dict[str, Any]] = []

        if not commands:
            return TaskResult(
                task_id=task.id,
                task_name=task.name,
                status="RERUN_FAILED",
                evidence=[{
                    "result": "FAIL",
                    "output": "No runnable Evidence Required command found",
                }],
                notes="Each task must include at least one shell-runnable evidence command.",
            )

        all_passed = True
        for item in commands:
            rc, output = self._run_cmd(item["command"], cwd=self.state.project_dir)
            passed = rc == 0
            all_passed = all_passed and passed
            clean_output = self._trim_output(output)
            label = f"{item['label']} (`{item['command']}`)"
            evidence.append({
                "result": "PASS" if passed else "FAIL",
                "output": clean_output,
            })
            evidence_entries.append({
                "check": label,
                "output": clean_output,
                "passed": passed,
            })

        plan_text = self.state.read_file(sprint_plan_path)
        plan_text = apply_evidence_patch(
            plan_text,
            {"task_id": task.id, "entries": evidence_entries},
        )
        self.state.write_file(sprint_plan_path, plan_text)

        return TaskResult(
            task_id=task.id,
            task_name=task.name,
            status="VERIFIED" if all_passed else "RERUN_FAILED",
            evidence=evidence,
            notes="" if all_passed else "One or more evidence commands failed.",
        )

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

    # -- helper: run shell command -------------------------------------------

    @staticmethod
    def _run_cmd(cmd: str, timeout: int = 120, cwd=None) -> tuple[int, str]:
        """Run a shell command and return (returncode, stdout)."""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
            return result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return -1, f"Command timed out after {timeout}s"
        except Exception as exc:
            return -1, str(exc)

    @staticmethod
    def _extract_commands(evidence_required: list[str]) -> list[dict[str, str]]:
        """Extract shell-runnable commands from Evidence Required lines."""
        commands: list[dict[str, str]] = []
        for line in evidence_required:
            lowered = line.lower()
            if "manual verification" in lowered and "run `" not in lowered:
                continue

            command = None
            run_match = re.search(r"\bRun\s+`([^`]+)`", line, re.IGNORECASE)
            if run_match:
                command = run_match.group(1).strip()
            elif lowered.startswith("git diff"):
                command = line.strip()
            else:
                backtick_match = re.search(r"`([^`]+)`", line)
                if backtick_match:
                    candidate = backtick_match.group(1).strip()
                    if Tester._looks_like_command(candidate):
                        command = candidate

            if command:
                commands.append({"label": line, "command": command})
        return commands

    @staticmethod
    def _looks_like_command(text: str) -> bool:
        return bool(
            re.match(
                r"^(npm|node|python|python3|pytest|uv|curl|git|ls|test|npx|pnpm|yarn)\b",
                text,
            )
        )

    @staticmethod
    def _trim_output(output: str, limit: int = 2000) -> str:
        output = output.strip()
        if len(output) <= limit:
            return output
        return output[:limit] + "\n...<truncated>"
