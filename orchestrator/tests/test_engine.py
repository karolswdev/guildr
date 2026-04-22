"""Tests for resumable orchestrator execution."""

from __future__ import annotations

from pathlib import Path

from orchestrator.engine import Orchestrator
from orchestrator.lib.config import Config


class RecordingOrchestrator(Orchestrator):
    """Engine variant that records the executed steps."""

    def __init__(self, config: Config) -> None:
        super().__init__(config=config, dry_run=True)
        self.calls: list[str] = []

    def _ensure_git_repo(self) -> None:
        return None

    def _ensure_qwendea(self) -> None:
        return None

    def _validate(self, name: str) -> bool:
        return True

    def _architect(self, *, phase_logger=None) -> None:
        self.calls.append("architect")

    def _coder(self, *, phase_logger=None) -> None:
        self.calls.append("implementation")

    def _tester(self, *, phase_logger=None) -> None:
        self.calls.append("testing")

    def _reviewer(self, *, phase_logger=None) -> None:
        self.calls.append("review")

    def _deployer(self, *, phase_logger=None) -> None:
        self.calls.append("deployment")

    def _gate(self, name: str) -> None:
        self.calls.append(name)


def _config(tmp_path: Path) -> Config:
    return Config(
        llama_server_url="http://127.0.0.1:8080",
        project_dir=tmp_path,
        require_human_approval=False,
    )


def test_run_can_resume_from_named_step(tmp_path: Path) -> None:
    engine = RecordingOrchestrator(_config(tmp_path))

    engine.run(start_at="testing")

    assert engine.calls == ["testing", "review", "approve_review", "deployment"]


def test_run_rejects_unknown_resume_step(tmp_path: Path) -> None:
    engine = RecordingOrchestrator(_config(tmp_path))

    try:
        engine.run(start_at="shipit")
    except ValueError as exc:
        assert "Unknown run step" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid start_at")
