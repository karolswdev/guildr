"""Micro-task breakdown role for low-context task execution packets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.lib.control import build_operator_context, write_compact_context
from orchestrator.lib.sprint_plan import Task, parse_tasks, slice_task
from orchestrator.lib.state import State


@dataclass
class MicroTaskBreaker:
    """Generates atomic implementation/verification packets per sprint task."""

    state: State
    _phase_logger: Any = None
    _phase: str = "micro_task_breakdown"
    _role: str = "micro_task_breaker"

    def execute(self, sprint_plan_path: str = "sprint-plan.md") -> str:
        plan_text = self.state.read_file(sprint_plan_path)
        tasks = parse_tasks(plan_text)
        write_compact_context(self.state.project_dir, max_chars=18000)

        phase_dir = self.state.project_dir / "phase-files"
        phase_dir.mkdir(parents=True, exist_ok=True)

        packets: list[tuple[Task, str, str]] = []
        for task in tasks:
            implement_name = f"task-{task.id:03d}-implement.md"
            verify_name = f"task-{task.id:03d}-verify.md"
            implement_path = phase_dir / implement_name
            verify_path = phase_dir / verify_name
            implement_path.write_text(self._implementation_packet(plan_text, task), encoding="utf-8")
            verify_path.write_text(self._verification_packet(task), encoding="utf-8")
            packets.append((task, implement_name, verify_name))

        index_path = phase_dir / "INDEX.md"
        index_path.write_text(self._index(packets), encoding="utf-8")
        return str(index_path.relative_to(self.state.project_dir))

    def _implementation_packet(self, plan_text: str, task: Task) -> str:
        task_slice = slice_task(plan_text, task.id)
        operator_context = build_operator_context(
            self.state.project_dir,
            "implementation",
            max_chars=4000,
        )
        sections = [
            f"# Implementation Packet: Task {task.id} - {task.name}",
            "",
            "Use this packet for a low-context implementation pass.",
            "",
            f"Priority: {task.priority or 'unspecified'}",
            f"Dependencies: {', '.join(task.deps) if task.deps else 'none'}",
            f"Files: {', '.join(task.files) if task.files else 'not declared'}",
            "",
            "## Task Slice",
            "",
            task_slice.strip(),
            "",
        ]
        if operator_context:
            sections.extend([
                "## Project Context Snapshot",
                "",
                operator_context.strip(),
                "",
            ])
        sections.extend([
            "## Output Constraints",
            "",
            "- Stay scoped to this task and the listed files.",
            "- Prefer the repo's existing framework and commands.",
            "- Leave evidence hooks intact for verification.",
            "",
        ])
        return "\n".join(sections).strip() + "\n"

    def _verification_packet(self, task: Task) -> str:
        sections = [
            f"# Verification Packet: Task {task.id} - {task.name}",
            "",
            "Use this packet for an isolated verification pass.",
            "",
            "## Acceptance Criteria",
            "",
        ]
        if task.acceptance_criteria:
            sections.extend(task.acceptance_criteria)
        else:
            sections.append("- No acceptance criteria recorded.")
        sections.extend([
            "",
            "## Evidence Required",
            "",
        ])
        if task.evidence_required:
            sections.extend(f"- {item}" for item in task.evidence_required)
        else:
            sections.append("- No evidence commands recorded.")
        sections.extend([
            "",
            "## Known Files",
            "",
            f"- {', '.join(task.files) if task.files else 'none declared'}",
            "",
        ])
        return "\n".join(sections).strip() + "\n"

    @staticmethod
    def _index(packets: list[tuple[Task, str, str]]) -> str:
        lines = [
            "# Phase Files",
            "",
            "Atomic packets for low-context execution and verification.",
            "",
        ]
        if not packets:
            lines.append("No tasks were found in sprint-plan.md.")
            return "\n".join(lines) + "\n"
        for task, implement_name, verify_name in packets:
            lines.extend([
                f"## Task {task.id}: {task.name}",
                f"- Implement: `{implement_name}`",
                f"- Verify: `{verify_name}`",
                "",
            ])
        return "\n".join(lines).strip() + "\n"
