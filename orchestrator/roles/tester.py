"""Tester role — runs evidence commands via opencode (H6.3b).

One opencode session per ``execute()`` pass. The role still extracts
the shell-runnable evidence commands from each sprint-plan task (so the
agent isn't free to invent its own verification story), but hands them
to an agent which runs them via its bash tool and writes the final
``TEST_REPORT.md`` as its last assistant message. The orchestrator
writes that text verbatim, the way ``Deployer`` writes ``DEPLOY.md`` —
downstream gates parse the exact shape below, so we don't trust the
agent's file-write tool for the report itself.

Helpers for evidence-command extraction and validation are kept as
static methods: they feed the prompt and are covered by unit tests
that don't need an opencode session.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from orchestrator.lib.control import append_operator_context
from orchestrator.lib.opencode import SessionRunner
from orchestrator.lib.opencode_audit import emit_session_audit
from orchestrator.lib.sprint_plan import Task, parse_tasks
from orchestrator.lib.state import State

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


class TesterError(Exception):
    """Raised when the Tester cannot complete its session."""


class Tester:
    """Runs one opencode session that verifies every sprint-plan task."""

    _phase: str = "testing"
    _role: str = "tester"

    def __init__(
        self,
        runner: SessionRunner,
        state: State,
        phase_logger: Any = None,
    ) -> None:
        self.runner = runner
        self.state = state
        self._phase_logger = phase_logger

    # -- public API ----------------------------------------------------------

    def execute(self, sprint_plan_path: str = "sprint-plan.md") -> str:
        plan_text = self.state.read_file(sprint_plan_path)
        tasks = parse_tasks(plan_text)

        if not tasks:
            logger.warning("No tasks found in sprint plan")
            self.state.write_file(
                "TEST_REPORT.md",
                "# Test Report\n\nTasks verified: 0\n",
            )
            return "TEST_REPORT.md"

        task_block = self._render_tasks_for_prompt(tasks)
        template = self._load_prompt("tester", "generate")
        prompt = template.format(task_block=task_block)
        prompt = self._augment_prompt(prompt)

        try:
            result = self.runner.run(prompt)
        except Exception as exc:
            raise TesterError(f"opencode session failed: {exc}") from exc

        # Audit first — failed sessions still leave a forensic trail.
        emit_session_audit(
            self.state,
            result,
            role=self._role,
            phase=self._phase,
            step=self._phase,
            prompt=prompt,
        )

        if result.exit_code != 0:
            raise TesterError(
                f"opencode session exited with rc={result.exit_code}: "
                f"{result.assistant_text[:200]!r}"
            )

        report = result.assistant_text.strip()
        if not report:
            raise TesterError(
                "opencode session returned no assistant text — nothing to write"
            )
        self.state.write_file("TEST_REPORT.md", report)
        return "TEST_REPORT.md"

    # -- prompt rendering ----------------------------------------------------

    @classmethod
    def _render_tasks_for_prompt(cls, tasks: list[Task]) -> str:
        """Emit the per-task block the tester prompt interpolates.

        Each task lists its id, name, acceptance criteria, and the
        shell-runnable evidence commands the framework extracted. Any
        validation error (e.g. long-running dev server) is flagged in
        place so the agent records it as FAIL without running it.
        """
        blocks: list[str] = []
        for task in tasks:
            block = [f"### Task {task.id}: {task.name}"]
            if task.acceptance_criteria:
                block.append("Acceptance criteria:")
                for ac in task.acceptance_criteria:
                    block.append(f"- {ac}")
            commands = cls._extract_commands(task.evidence_required)
            if not commands:
                block.append(
                    "Evidence commands: NONE — mark this task as "
                    "RERUN_FAILED (missing runnable command)."
                )
            else:
                block.append("Evidence commands (run each one, record exit code + trimmed output):")
                for item in commands:
                    err = cls._command_validation_error(item["command"])
                    if err:
                        block.append(f"- {item['label']} — SKIP / FAIL: {err}")
                    else:
                        block.append(f"- {item['label']} — run: `{item['command']}`")
            blocks.append("\n".join(block))
        return "\n\n".join(blocks)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _load_prompt(role: str, name: str) -> str:
        return (_PROMPT_DIR / role / f"{name}.txt").read_text(encoding="utf-8")

    def _augment_prompt(self, prompt: str) -> str:
        return append_operator_context(
            self.state.project_dir,
            self._phase,
            prompt,
            events=getattr(self.state, "events", None),
        )

    # -- command extraction (prompt inputs) ----------------------------------

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
    def _command_validation_error(command: str) -> str | None:
        lowered = command.lower().strip()
        if re.search(
            r"\b(npm|pnpm|yarn)\s+run\s+dev\b|\b(next|vite)\s+dev\b|\bwebpack\s+serve\b|\bpython\s+-m\s+http\.server\b|\buvicorn\b|^vite(?:\s|$)",
            lowered,
        ):
            return (
                "Evidence command is a long-running dev server. "
                "Use a finite verifier command such as install, build, lint, "
                "test, or a bounded smoke script."
            )
        return None
