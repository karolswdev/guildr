"""Coder role — implements tasks from sprint-plan.md via opencode (H6.3a).

Each task is one opencode session: the role sends "here's the
architecture, here's the task, write the files" and trusts the agent's
tool calls to land the changes on disk. We don't parse a JSON-of-files
patch anymore; opencode's ``write``/``edit`` tools handle that layer,
confined to ``--dir <project>``. The role's job is just to sequence
tasks in dependency order and surface session failures as
``CoderError``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from orchestrator.lib.control import append_operator_context
from orchestrator.lib.opencode import SessionRunner
from orchestrator.lib.sprint_plan import Task, parse_tasks, slice_task
from orchestrator.lib.state import State

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


class CoderError(Exception):
    """Raised when the Coder cannot complete a task."""


class Coder:
    """Implements sprint-plan tasks sequentially via an opencode agent session.

    One :class:`SessionRunner` is reused across tasks — each task calls
    :meth:`SessionRunner.run` with its own prompt. The runner is
    expected to spawn a fresh opencode session per call (that is how
    :class:`orchestrator.lib.opencode.OpencodeSession` behaves).
    """

    _phase: str = "implementation"
    _role: str = "coder"

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

    def execute(self, sprint_plan_path: str = "sprint-plan.md") -> str:
        """Execute all tasks from the sprint plan in dependency order."""
        plan_text = self.state.read_file(sprint_plan_path)
        tasks = parse_tasks(plan_text)

        if not tasks:
            logger.warning("No tasks found in sprint plan")
            return sprint_plan_path

        ordered = self._topological_sort(tasks)
        for task in ordered:
            logger.info("Coder: executing task %d: %s", task.id, task.name)
            self._execute_task(plan_text, task)

        return sprint_plan_path

    # -- per-task session ----------------------------------------------------

    def _execute_task(self, plan_text: str, task: Task) -> None:
        """Drive one opencode session for one task, raise on session failure."""
        prompt = self._build_prompt(plan_text, task)

        try:
            result = self.runner.run(prompt)
        except Exception as exc:
            raise CoderError(
                f"opencode session failed for task {task.id}: {exc}"
            ) from exc

        if result.exit_code != 0:
            raise CoderError(
                f"opencode session for task {task.id} exited with "
                f"rc={result.exit_code}: {result.assistant_text[:200]!r}"
            )

        # An agent that writes zero files for a coding task is almost
        # always a prompt regression or a provider short-circuit. Flag
        # it loudly — the Tester would fail on the same task anyway,
        # but at the Tester stage the signal is "tests fail" rather
        # than "nothing was written."
        wrote_any = any(
            call.tool in ("write", "edit", "patch")
            and call.status == "completed"
            for call in result.tool_calls
        )
        if not wrote_any:
            raise CoderError(
                f"opencode session for task {task.id} completed without "
                "any write/edit tool call"
            )

    def _build_prompt(self, plan_text: str, task: Task) -> str:
        template = self._load_prompt("coder", "generate")
        rendered = template.format(
            architecture=self._extract_architecture(plan_text),
            task=self._task_context(task.id, plan_text),
        )
        return self._augment_prompt(rendered)

    def _task_context(self, task_id: int, plan_text: str) -> str:
        packet_path = (
            self.state.project_dir / "phase-files" / f"task-{task_id:03d}-implement.md"
        )
        if packet_path.exists():
            return packet_path.read_text(encoding="utf-8")
        return slice_task(plan_text, task_id)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _load_prompt(role: str, name: str) -> str:
        return (_PROMPT_DIR / role / f"{name}.txt").read_text(encoding="utf-8")

    def _augment_prompt(self, prompt: str) -> str:
        return append_operator_context(self.state.project_dir, self._phase, prompt)

    @staticmethod
    def _extract_architecture(plan_text: str) -> str:
        m = re.search(
            r"## Architecture Decisions\n(.*?)(?=\n## |\Z)",
            plan_text,
            re.DOTALL,
        )
        return m.group(1).strip() if m else "No architecture decisions recorded."

    def _topological_sort(self, tasks: list[Task]) -> list[Task]:
        task_map = {t.id: t for t in tasks}
        visited: set[int] = set()
        result: list[Task] = []

        def visit(task: Task) -> None:
            if task.id in visited:
                return
            visited.add(task.id)
            for dep in task.deps:
                m = re.search(r"(\d+)", dep)
                if m:
                    dep_id = int(m.group(1))
                    if dep_id in task_map:
                        visit(task_map[dep_id])
            result.append(task)

        for task in tasks:
            visit(task)
        return result
