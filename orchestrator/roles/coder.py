"""Coder role — implements tasks from sprint-plan.md."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from orchestrator.lib.llm import LLMClient
from orchestrator.lib.sprint_plan import (
    Task,
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
        """Execute a single task: call LLM, parse patch, apply file writes."""
        context = slice_task(plan_text, task.id)

        system_prompt = self._load_prompt("coder", "generate")
        user_prompt = system_prompt.format(
            architecture=self._extract_architecture(plan_text),
            task=context,
        )
        user_prompt = self._augment_prompt(user_prompt)

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

        if int(patch.get("task_id", -1)) != task.id:
            raise CoderError(
                f"Patch task_id {patch.get('task_id')} does not match task {task.id}"
            )

        self._apply_file_patch(patch)

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
            if Coder._is_valid_file_patch(data):
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
                if Coder._is_valid_file_patch(data):
                    return data
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    @staticmethod
    def _is_valid_file_patch(data: object) -> bool:
        """Return True when data follows the Coder file patch schema."""
        if not isinstance(data, dict):
            return False
        if "task_id" not in data or "files" not in data:
            return False
        files = data.get("files")
        if not isinstance(files, list) or not files:
            return False
        for entry in files:
            if not isinstance(entry, dict):
                return False
            if not isinstance(entry.get("path"), str):
                return False
            if not isinstance(entry.get("content"), str):
                return False
        return True

    def _apply_file_patch(self, patch: dict[str, Any]) -> None:
        """Apply Coder file writes under project_dir."""
        for entry in patch["files"]:
            rel = entry["path"]
            self._validate_project_relative_path(rel)
            self.state.write_file(rel, entry["content"])

    def _validate_project_relative_path(self, path: str) -> None:
        """Reject absolute paths, traversal, and orchestrator internals."""
        from pathlib import Path

        rel = Path(path)
        if rel.is_absolute():
            raise CoderError(f"Refusing absolute path: {path}")
        if any(part in ("", ".", "..") for part in rel.parts):
            raise CoderError(f"Refusing unsafe path: {path}")
        if rel.parts[0] in (".git", ".orchestrator"):
            raise CoderError(f"Refusing internal path: {path}")
        target = (self.state.project_dir / rel).resolve()
        try:
            target.relative_to(self.state.project_dir)
        except ValueError as exc:
            raise CoderError(f"Refusing path outside project: {path}") from exc

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
