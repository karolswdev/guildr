"""Coder role — implements tasks from sprint-plan.md."""

from __future__ import annotations

import json
import logging
import re
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


class CoderError(Exception):
    """Raised when the Coder encounters a fatal error."""


class Coder(BaseRole):
    """Implements tasks from sprint-plan.md sequentially."""

    _phase: str = "implementation"
    _role: str = "coder"

    def __init__(
        self,
        llm: LLMClient,
        state: State,
        max_tokens: int = 16384,
        phase_logger: Any = None,
    ) -> None:
        super().__init__(llm, state, phase_logger=phase_logger)
        self.max_tokens = max_tokens

    # -- public API ----------------------------------------------------------

    def execute(self, sprint_plan_path: str = "sprint-plan.md") -> str:
        """Execute all tasks from the sprint plan in dependency order.

        Returns the sprint_plan_path on success.
        Raises CoderError on fatal failure.
        """
        plan_text = self.state.read_file(sprint_plan_path)
        tasks = parse_tasks(plan_text)

        if not tasks:
            logger.warning("No tasks found in sprint plan")
            return sprint_plan_path

        ordered = self._topological_sort(tasks)

        for task in ordered:
            logger.info("Coder: executing task %d: %s", task.id, task.name)
            plan_text = self._execute_task(plan_text, task, sprint_plan_path)

        return sprint_plan_path

    # -- task execution ------------------------------------------------------

    def _execute_task(
        self, plan_text: str, task: Task, sprint_plan_path: str
    ) -> str:
        """Execute a single task: call LLM, parse patch, apply patch."""
        context = slice_task(plan_text, task.id)

        system_prompt = self._load_prompt("coder", "generate")
        user_prompt = system_prompt.format(
            architecture=self._extract_architecture(plan_text),
            task=context,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self._chat(messages, max_tokens=self.max_tokens)
        except Exception as exc:
            raise CoderError(f"LLM call failed for task {task.id}: {exc}") from exc

        patch = self._parse_patch(response.content)
        if patch is None:
            raise CoderError(
                f"Failed to parse JSON patch for task {task.id}"
            )

        plan_text = apply_evidence_patch(plan_text, patch)
        self.state.write_file(sprint_plan_path, plan_text)

        return plan_text

    # -- JSON parsing (same robustness as Architect) -------------------------

    def _parse_patch(self, raw: str) -> dict[str, Any] | None:
        """Parse the JSON patch from LLM output.

        Uses 3-tier robustness: strict -> re-prompt -> regex fallback.
        """
        result = self._strict_parse(raw)
        if result is not None:
            return result

        messages = [
            {"role": "system", "content": "You are a code generator."},
            {"role": "user", "content": raw},
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": "Your last output was not valid JSON. "
                "Return only the JSON object, nothing else.",
            },
        ]
        try:
            response = self._chat(messages, max_tokens=self.max_tokens)
            result = self._strict_parse(response.content)
            if result is not None:
                return result
        except Exception:
            pass

        result = self._extract_json_regex(raw)
        if result is not None:
            return result

        return None

    @staticmethod
    def _strict_parse(raw: str) -> dict[str, Any] | None:
        """Try strict JSON parse. Returns None on failure."""
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "task_id" in data and "entries" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    @staticmethod
    def _extract_json_regex(raw: str) -> dict[str, Any] | None:
        """Extract the outermost {...} block from raw text."""
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, dict) and "task_id" in data and "entries" in data:
                    return data
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    # -- helpers -------------------------------------------------------------

    def _topological_sort(self, tasks: list[Task]) -> list[Task]:
        """Sort tasks in dependency order."""
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

    def _extract_architecture(self, plan_text: str) -> str:
        """Extract the Architecture Decisions section from the plan."""
        m = re.search(
            r"## Architecture Decisions\n(.*?)(?=\n## |\Z)",
            plan_text,
            re.DOTALL,
        )
        return m.group(1).strip() if m else "No architecture decisions recorded."
