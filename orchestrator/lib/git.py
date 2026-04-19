"""Git operations for the orchestrator.

Full implementation in Task 5.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class UncleanWorkingTree(Exception):
    """Raised when git reports a dirty working tree."""

    def __init__(self) -> None:
        super().__init__("Working tree is not clean; human investigation required")


class GitOps:
    """Git operations owned by the orchestrator. Roles never commit directly."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir.resolve()

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command in the project directory."""
        return subprocess.run(
            ["git", *args],
            cwd=str(self.project_dir),
            capture_output=True,
            text=True,
            check=check,
        )

    def ensure_repo(self, project_dir: Path) -> None:
        """Initialize git repo if needed; write .gitignore with .orchestrator/."""
        git_dir = Path(project_dir) / ".git"
        if not git_dir.exists():
            self._run("init", str(project_dir), check=True)

        gitignore = Path(project_dir) / ".gitignore"
        if not gitignore.exists():
            content = (
                "# Orchestrator runtime state — not source of truth\n"
                ".orchestrator/\n"
                "\n"
                "# Language defaults\n"
                "__pycache__/\n"
                "*.pyc\n"
                "*.egg-info/\n"
                ".venv/\n"
                ".pytest_cache/\n"
                ".mypy_cache/\n"
                "\n"
                "# Node/PWA\n"
                "node_modules/\n"
                "dist/\n"
                ".cache/\n"
                "\n"
                "# Secrets\n"
                ".env\n"
                "*.key\n"
                "*.pem\n"
            )
            gitignore.write_text(content, encoding="utf-8")
            self._run("add", ".gitignore")
            self._run("commit", "-m", "chore: seed .gitignore", "--allow-empty")

    def assert_clean(self) -> None:
        """Raise UncleanWorkingTree if `git diff-index --quiet HEAD --` is non-zero."""
        result = subprocess.run(
            ["git", "diff-index", "--quiet", "HEAD", "--"],
            cwd=str(self.project_dir),
            capture_output=True,
        )
        if result.returncode != 0:
            raise UncleanWorkingTree()

    def commit_task(self, phase: str, task_id: int, name: str, prior_head: str) -> str:
        """Stage all, commit with the mandatory message template, return short SHA."""
        self._run("add", "-A")
        short_sha = prior_head[:7]
        message = (
            f"phase-{phase}(task-{task_id}): {name}\n"
            f"\n"
            f"Verified-by: tester at {short_sha}\n"
            f"Evidence-log: sprint-plan.md#task-{task_id}"
        )
        self._run("commit", "-m", message)
        result = self._run("rev-parse", "--short", "HEAD")
        return result.stdout.strip()

    def tag_phase(self, phase_num: int) -> None:
        """Create annotated tag `phase-<N>-done` at HEAD."""
        self._run(
            "tag",
            "-a",
            f"phase-{phase_num}-done",
            "-m",
            f"Phase {phase_num} completed",
        )

    def rollback_to(self, ref: str) -> None:
        """git reset --hard <ref>. Only called via explicit CLI; never automatic."""
        self._run("reset", "--hard", ref)
