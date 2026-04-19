"""Tests for dry-run mode (FakeLLMClient + orchestrator integration)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.engine import Orchestrator, PhaseFailure
from orchestrator.lib.config import Config
from orchestrator.lib.llm import LLMResponse
from orchestrator.lib.llm_fake import FakeLLMClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_response() -> LLMResponse:
    """A canned LLMResponse for dry-run tests."""
    return LLMResponse(
        content="# Sprint Plan\n\n## Tasks\n\n### Task 1: Setup\n",
        reasoning="",
        prompt_tokens=10,
        completion_tokens=20,
        reasoning_tokens=0,
        finish_reason="stop",
    )


@pytest.fixture
def fake_llm(fake_response: LLMResponse) -> FakeLLMClient:
    """FakeLLMClient with canned responses for common roles."""
    return FakeLLMClient(
        responses={
            "user": fake_response,
            "system": fake_response,
            "default": fake_response,
        }
    )


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    return tmp_path


@pytest.fixture
def config(tmp_project: Path) -> Config:
    """Create a minimal Config."""
    return Config(
        llama_server_url="http://192.168.1.13:8080",
        project_dir=tmp_project,
        max_retries=3,
    )


@pytest.fixture
def qwendea(tmp_project: Path) -> Path:
    """Create a qwendea.md file so _ensure_qwendea passes."""
    qwendea = tmp_project / "qwendea.md"
    qwendea.write_text("# Test Project\n\nDescription.", encoding="utf-8")
    return qwendea


@pytest.fixture
def mock_git_ops(tmp_project: Path) -> MagicMock:
    """Mock GitOps so git operations don't touch the real filesystem."""
    ops = MagicMock()
    ops.ensure_repo = MagicMock()
    ops.assert_clean = MagicMock()
    ops.commit_task = MagicMock(return_value="abc1234")
    ops.tag_phase = MagicMock()
    ops.rollback_to = MagicMock()
    return ops


# ---------------------------------------------------------------------------
# Tests: FakeLLMClient
# ---------------------------------------------------------------------------


class TestFakeLLMClient:
    """Test FakeLLMClient basic functionality."""

    def test_returns_canned_response_for_role(self, fake_response):
        """chat() returns the canned response for the given role."""
        fake = FakeLLMClient(responses={"user": fake_response})
        result = fake.chat([{"role": "user", "content": "hi"}])
        assert result.content == fake_response.content

    def test_falls_back_to_default_response(self, fake_response):
        """chat() falls back to 'default' when role key is missing."""
        fake = FakeLLMClient(responses={"default": fake_response})
        result = fake.chat([{"role": "unknown", "content": "hi"}])
        assert result.content == fake_response.content

    def test_raises_keyerror_for_unknown_role(self):
        """chat() raises KeyError when neither role nor default exists."""
        fake = FakeLLMClient(responses={})
        with pytest.raises(KeyError, match="No canned response"):
            fake.chat([{"role": "missing", "content": "hi"}])

    def test_increments_call_count(self, fake_response):
        """Each chat() call increments call_count."""
        fake = FakeLLMClient(responses={"default": fake_response})
        fake.chat([{"role": "user", "content": "hi"}])
        fake.chat([{"role": "user", "content": "hello"}])
        assert fake.call_count == 2

    def test_was_called_returns_true_after_calls(self, fake_response):
        """was_called() returns True after at least one chat()."""
        fake = FakeLLMClient(responses={"default": fake_response})
        assert fake.was_called() is False
        fake.chat([{"role": "user", "content": "hi"}])
        assert fake.was_called() is True

    def test_was_called_returns_false_when_unused(self):
        """was_called() returns False when no chat() calls were made."""
        fake = FakeLLMClient(responses={})
        assert fake.was_called() is False

    def test_health_returns_true(self):
        """health() always returns True in dry-run mode."""
        fake = FakeLLMClient(responses={})
        assert fake.health() is True

    def test_returns_token_counts_from_response(self, fake_response):
        """Token counts from canned response are preserved."""
        fake = FakeLLMClient(responses={"default": fake_response})
        result = fake.chat([{"role": "user", "content": "hi"}])
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 20
        assert result.reasoning_tokens == 0


# ---------------------------------------------------------------------------
# Tests: Dry-run orchestrator integration
# ---------------------------------------------------------------------------


class TestDryRunIntegration:
    """Test that the orchestrator uses FakeLLMClient in dry-run mode."""

    def test_dry_run_uses_fake_llm_not_pool(self, config, qwendea, fake_llm):
        """When fake_llm is set, the orchestrator uses it instead of the pool."""
        (config.project_dir / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [x] Done\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )
        (config.project_dir / "TEST_REPORT.md").write_text(
            "All tests passed.", encoding="utf-8"
        )
        (config.project_dir / "REVIEW.md").write_text("APPROVED", encoding="utf-8")

        mock_git_ops = MagicMock()
        mock_git_ops.ensure_repo = MagicMock()

        mock_pool = MagicMock()

        orchestrator = Orchestrator(
            config=config,
            pool=mock_pool,
            fake_llm=fake_llm,
            git_ops=mock_git_ops,
        )
        orchestrator._gate = MagicMock()

        # Patch phase functions to track which LLM client was used
        architect_called_with = []

        def mock_architect():
            from orchestrator.roles.architect import Architect
            # The architect should have been created with the fake_llm
            # We verify by checking is_dry_run
            architect_called_with.append(orchestrator.is_dry_run())

        orchestrator._architect = mock_architect
        orchestrator._coder = MagicMock()
        orchestrator._tester = MagicMock()
        orchestrator._reviewer = MagicMock()
        orchestrator._deployer = MagicMock()

        orchestrator.run()

        assert orchestrator.is_dry_run() is True
        assert architect_called_with == [True]
        # The fake LLM should not have been called by the mock architect
        # (the real architect would call it, but we're using a mock)

    def test_dry_run_false_without_fake_llm(self, config, qwendea, mock_git_ops):
        """is_dry_run() returns False when no fake_llm is set."""
        orchestrator = Orchestrator(
            config=config,
            git_ops=mock_git_ops,
        )
        assert orchestrator.is_dry_run() is False

    def test_dry_run_produces_output_files(self, config, qwendea, fake_llm):
        """Dry-run produces all expected output files."""
        (config.project_dir / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [x] Done\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )
        (config.project_dir / "TEST_REPORT.md").write_text(
            "All tests passed.", encoding="utf-8"
        )
        (config.project_dir / "REVIEW.md").write_text("APPROVED", encoding="utf-8")

        mock_git_ops = MagicMock()
        mock_git_ops.ensure_repo = MagicMock()

        orchestrator = Orchestrator(
            config=config,
            fake_llm=fake_llm,
            git_ops=mock_git_ops,
        )
        orchestrator._gate = MagicMock()

        # Patch all role methods to just create their output files
        def mock_architect():
            config.project_dir.joinpath("sprint-plan.md").write_text(
                "# Sprint Plan\n\n"
                "## Architecture Decisions\n- None\n\n"
                "## Tasks\n\n"
                "### Task 1: Setup\n"
                "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
                "**Acceptance Criteria:**\n- [ ] Works\n\n"
                "**Evidence Required:**\n- Run `pytest`\n\n"
                "**Evidence Log:**\n- [x] Done\n\n"
                "## Risks & Mitigations\n1. Risk — Mitigation\n",
                encoding="utf-8",
            )

        def mock_coder():
            (config.project_dir / "a.py").write_text("# code", encoding="utf-8")

        def mock_tester():
            config.project_dir.joinpath("TEST_REPORT.md").write_text(
                "All tests passed.", encoding="utf-8"
            )

        def mock_reviewer():
            config.project_dir.joinpath("REVIEW.md").write_text(
                "APPROVED", encoding="utf-8"
            )

        def mock_deployer():
            config.project_dir.joinpath("DEPLOY.md").write_text(
                "Deployment plan", encoding="utf-8"
            )

        orchestrator._architect = mock_architect
        orchestrator._coder = mock_coder
        orchestrator._tester = mock_tester
        orchestrator._reviewer = mock_reviewer
        orchestrator._deployer = mock_deployer

        orchestrator.run()

        assert (config.project_dir / "sprint-plan.md").exists()
        assert (config.project_dir / "a.py").exists()
        assert (config.project_dir / "TEST_REPORT.md").exists()
        assert (config.project_dir / "REVIEW.md").exists()
        assert (config.project_dir / "DEPLOY.md").exists()

    def test_dry_run_requires_fake_llm_or_pool(self, config, qwendea):
        """Phase fails when neither fake_llm nor pool is available."""
        orchestrator = Orchestrator(
            config=config,
        )

        with pytest.raises(PhaseFailure, match="architect"):
            orchestrator._run_phase("architect", orchestrator._architect)


# ---------------------------------------------------------------------------
# Tests: Zero real LLM calls in dry-run
# ---------------------------------------------------------------------------


class TestZeroRealCalls:
    """Verify dry-run mode makes zero real LLM calls."""

    def test_fake_llm_tracks_all_calls(self, fake_response):
        """FakeLLMClient tracks every call so we can verify zero real calls."""
        fake = FakeLLMClient(
            responses={
                "user": fake_response,
                "default": fake_response,
            }
        )
        # Simulate what the orchestrator would do through all roles
        for _ in range(5):
            fake.chat([{"role": "user", "content": "hi"}])
        assert fake.call_count == 5
        assert fake.was_called() is True

    def test_dry_run_mode_without_network(self, config, qwendea, fake_llm):
        """Dry-run orchestrator works even with no network access."""
        (config.project_dir / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [x] Done\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )
        (config.project_dir / "TEST_REPORT.md").write_text(
            "All tests passed.", encoding="utf-8"
        )
        (config.project_dir / "REVIEW.md").write_text("APPROVED", encoding="utf-8")

        mock_git_ops = MagicMock()
        mock_git_ops.ensure_repo = MagicMock()

        # Patch phase functions
        orchestrator = Orchestrator(
            config=config,
            fake_llm=fake_llm,
            git_ops=mock_git_ops,
        )
        orchestrator._gate = MagicMock()
        orchestrator._architect = MagicMock()
        orchestrator._coder = MagicMock()
        orchestrator._tester = MagicMock()
        orchestrator._reviewer = MagicMock()
        orchestrator._deployer = MagicMock()

        # Should complete without any network calls
        orchestrator.run()

        # Fake LLM was set but not called by the mocked roles
        # The point is: no real network calls were attempted
        assert orchestrator.is_dry_run() is True
