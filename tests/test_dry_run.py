"""Tests for dry-run mode — the ``dry_run=True`` flag on Orchestrator.

Post pool-sunset the dry-run slot is a simple bool: when set, the engine
auto-wires each opencode-driven role to its ``*_dryrun`` SessionRunner.
No FakeLLMClient, no canned LLMResponse — every SDLC role produces its
artifacts via the dry-run runners directly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.engine import Orchestrator, PhaseFailure
from orchestrator.lib.config import Config


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def config(tmp_project: Path) -> Config:
    return Config(
        llama_server_url="http://127.0.0.1:8080",
        project_dir=tmp_project,
        max_retries=3,
    )


@pytest.fixture
def qwendea(tmp_project: Path) -> Path:
    qwendea = tmp_project / "qwendea.md"
    qwendea.write_text("# Test Project\n\nDescription.", encoding="utf-8")
    return qwendea


@pytest.fixture
def mock_git_ops() -> MagicMock:
    ops = MagicMock()
    ops.ensure_repo = MagicMock()
    ops.assert_clean = MagicMock()
    ops.commit_task = MagicMock(return_value="abc1234")
    ops.tag_phase = MagicMock()
    ops.rollback_to = MagicMock()
    return ops


class TestDryRunFlag:
    def test_is_dry_run_reflects_flag(self, config, qwendea, mock_git_ops):
        orch = Orchestrator(config=config, dry_run=True, git_ops=mock_git_ops)
        assert orch.is_dry_run() is True

    def test_is_dry_run_false_by_default(self, config, qwendea, mock_git_ops):
        orch = Orchestrator(config=config, git_ops=mock_git_ops)
        assert orch.is_dry_run() is False

    def test_session_runner_autowired_in_dry_run(self, config, qwendea, mock_git_ops):
        """With dry_run=True, requesting a role's runner auto-builds its dry-run double."""
        orch = Orchestrator(config=config, dry_run=True, git_ops=mock_git_ops)
        for role in ("coder", "tester", "reviewer", "deployer", "architect", "judge"):
            runner = orch._session_runner_for(role)
            assert runner is not None, f"{role} runner was not auto-wired"

    def test_no_runner_when_not_dry_run(self, config, qwendea, mock_git_ops):
        orch = Orchestrator(config=config, git_ops=mock_git_ops)
        assert orch._session_runner_for("coder") is None

    def test_phase_fails_without_dry_run_or_runner(self, config, qwendea):
        """Phase fails when neither dry_run nor an explicit runner is set."""
        orch = Orchestrator(config=config)
        with pytest.raises(PhaseFailure, match="implementation"):
            orch._coder()
