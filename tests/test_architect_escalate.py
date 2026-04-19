"""Tests for Architect escalation logic."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.lib.config import Config
from orchestrator.lib.llm import LLMClient, LLMResponse
from orchestrator.lib.state import State
from orchestrator.roles.architect import Architect, ArchitectFailure


@pytest.fixture
def state(tmp_path):
    """Create a State instance backed by a temp directory."""
    return State(tmp_path)


@pytest.fixture
def config(tmp_path):
    """Create a minimal Config with 3 max passes."""
    return Config(
        llama_server_url="http://192.168.1.13:8080",
        project_dir=tmp_path,
        architect_max_passes=3,
        architect_pass_threshold=4,
    )


class TestEscalationFiles:
    """Test that _escalate writes the correct files."""

    def test_writes_draft_files(self, state, config):
        """_escalate writes all drafts to .orchestrator/drafts/."""
        llm = MagicMock(spec=LLMClient)
        architect = Architect(llm, state, config)

        drafts = [
            ("# Draft 1\n", 2, {"reason": "malformed"}),
            ("# Draft 2\n", 3, {"specificity": {"score": 1, "issues": []}}),
            ("# Draft 3\n", 1, {"testability": {"score": 0, "issues": ["bad"]}}),
        ]

        architect._escalate(drafts)

        drafts_dir = state.project_dir / ".orchestrator" / "drafts"
        assert (drafts_dir / "architect-pass-1.md").read_text() == "# Draft 1\n"
        assert (drafts_dir / "architect-pass-2.md").read_text() == "# Draft 2\n"
        assert (drafts_dir / "architect-pass-3.md").read_text() == "# Draft 3\n"

    def test_writes_evaluation_jsons(self, state, config):
        """_escalate writes evaluation JSONs alongside drafts."""
        llm = MagicMock(spec=LLMClient)
        architect = Architect(llm, state, config)

        drafts = [
            ("# Draft 1\n", 2, {"specificity": {"score": 0, "issues": ["bad"]}}),
            ("# Draft 2\n", 3, {"testability": {"score": 1, "issues": []}}),
        ]

        architect._escalate(drafts)

        drafts_dir = state.project_dir / ".orchestrator" / "drafts"
        eval1 = json.loads((drafts_dir / "architect-pass-1-eval.json").read_text())
        assert eval1["specificity"]["score"] == 0

        eval2 = json.loads((drafts_dir / "architect-pass-2-eval.json").read_text())
        assert eval2["testability"]["score"] == 1

    def test_writes_escalation_md(self, state, config):
        """_escalate writes human-readable escalation.md."""
        llm = MagicMock(spec=LLMClient)
        architect = Architect(llm, state, config)

        drafts = [
            ("# Draft 1\n", 2, {
                "specificity": {"score": 0, "issues": ["bad"]},
                "testability": {"score": 0, "issues": ["bad"]},
                "evidence": {"score": 1, "issues": []},
                "completeness": {"score": 1, "issues": []},
                "feasibility": {"score": 1, "issues": []},
                "risk": {"score": 1, "issues": []},
            }),
            ("# Draft 2\n", 4, {
                "specificity": {"score": 1, "issues": []},
                "testability": {"score": 0, "issues": ["still bad"]},
                "evidence": {"score": 1, "issues": []},
                "completeness": {"score": 1, "issues": []},
                "feasibility": {"score": 1, "issues": []},
                "risk": {"score": 1, "issues": []},
            }),
        ]

        architect._escalate(drafts)

        escalation = (state.project_dir / ".orchestrator" / "escalation.md").read_text()
        assert "# Architect Escalation" in escalation
        assert "Best score" in escalation
        assert "4/6" in escalation
        assert "PASS" in escalation
        assert "FAIL" in escalation
        assert "drafts/architect-pass-1.md" in escalation
        assert "drafts/architect-pass-2.md" in escalation

    def test_escalation_lists_best_draft(self, state, config):
        """Escalation.md identifies the best draft by score."""
        llm = MagicMock(spec=LLMClient)
        architect = Architect(llm, state, config)

        drafts = [
            ("# Draft 1\n", 5, {"specificity": {"score": 1, "issues": []}}),
            ("# Draft 2\n", 3, {"specificity": {"score": 1, "issues": []}}),
            ("# Draft 3\n", 4, {"specificity": {"score": 1, "issues": []}}),
        ]

        architect._escalate(drafts)

        escalation = (state.project_dir / ".orchestrator" / "escalation.md").read_text()
        assert "best draft is `drafts/architect-pass-1.md`" in escalation


class TestArchitectFailure:
    """Test that execute raises ArchitectFailure on exhaustion."""

    def _write_qwendea(self, state):
        """Helper to create a qwendea.md in the state's project dir."""
        qwendea = state.project_dir / "qwendea.md"
        qwendea.write_text("# Project: Test\n\n## Description\nA test project.")

    def test_raises_with_best_score(self, state, config):
        """execute raises ArchitectFailure with best score in message."""
        self._write_qwendea(state)

        llm = MagicMock(spec=LLMClient)
        architect = Architect(llm, state, config)

        # Make _self_evaluate always return score 2 (below threshold)
        architect._self_evaluate = MagicMock(return_value=(2, {"specificity": {"score": 0, "issues": ["bad"]}}))

        # Make _generate return a valid-looking plan
        architect._generate = MagicMock(return_value="# Sprint Plan\n\n## Tasks\n\n### Task 1: Test\n- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `test.py`\n\n**Acceptance Criteria:**\n- [ ] Works\n\n**Evidence Required:**\n- Run `pytest`\n\n**Evidence Log:**\n- [ ] Done\n\n## Risks & Mitigations\n1. Risk — Mitigation")

        # Make _refine return something
        architect._refine = MagicMock(return_value="# Sprint Plan v2\n\n## Tasks\n\n### Task 1: Test\n- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `test.py`\n\n**Acceptance Criteria:**\n- [ ] Works\n\n**Evidence Required:**\n- Run `pytest`\n\n**Evidence Log:**\n- [ ] Done\n\n## Risks & Mitigations\n1. Risk — Mitigation")

        with pytest.raises(ArchitectFailure) as exc_info:
            architect.execute()

        assert "3 passes" in str(exc_info.value)
        assert "best score: 2/6" in str(exc_info.value)

    def test_writes_drafts_on_failure(self, state, config):
        """execute writes drafts before raising ArchitectFailure."""
        self._write_qwendea(state)

        llm = MagicMock(spec=LLMClient)
        architect = Architect(llm, state, config)

        architect._self_evaluate = MagicMock(return_value=(2, {"specificity": {"score": 0, "issues": ["bad"]}}))
        architect._generate = MagicMock(return_value="# Draft 1\n")
        architect._refine = MagicMock(return_value="# Draft 2\n")

        with pytest.raises(ArchitectFailure):
            architect.execute()

        drafts_dir = state.project_dir / ".orchestrator" / "drafts"
        assert (drafts_dir / "architect-pass-1.md").exists()
        assert (drafts_dir / "architect-pass-2.md").exists()
        assert (drafts_dir / "architect-pass-3.md").exists()

    def test_writes_escalation_on_failure(self, state, config):
        """execute writes escalation.md before raising ArchitectFailure."""
        self._write_qwendea(state)

        llm = MagicMock(spec=LLMClient)
        architect = Architect(llm, state, config)

        architect._self_evaluate = MagicMock(return_value=(2, {"specificity": {"score": 0, "issues": ["bad"]}}))
        architect._generate = MagicMock(return_value="# Draft 1\n")
        architect._refine = MagicMock(return_value="# Draft 2\n")

        with pytest.raises(ArchitectFailure):
            architect.execute()

        assert (state.project_dir / ".orchestrator" / "escalation.md").exists()


class TestExecuteSuccess:
    """Test that execute writes sprint-plan.md on success."""

    def _write_qwendea(self, state):
        """Helper to create a qwendea.md in the state's project dir."""
        qwendea = state.project_dir / "qwendea.md"
        qwendea.write_text("# Project: Test\n\n## Description\nA test project.")

    def test_writes_sprint_plan_on_pass(self, state, config):
        """execute writes sprint-plan.md and returns its path on success."""
        self._write_qwendea(state)

        llm = MagicMock(spec=LLMClient)
        architect = Architect(llm, state, config)

        # First pass: score 3 (below threshold)
        # Second pass: score 5 with mandatory met (pass)
        architect._self_evaluate = MagicMock(
            side_effect=[
                (3, {
                    "specificity": {"score": 1, "issues": []},
                    "testability": {"score": 1, "issues": []},
                    "evidence": {"score": 1, "issues": []},
                    "completeness": {"score": 0, "issues": ["bad"]},
                    "feasibility": {"score": 0, "issues": ["bad"]},
                    "risk": {"score": 0, "issues": ["bad"]},
                }),
                (5, {
                    "specificity": {"score": 1, "issues": []},
                    "testability": {"score": 1, "issues": []},
                    "evidence": {"score": 1, "issues": []},
                    "completeness": {"score": 1, "issues": []},
                    "feasibility": {"score": 1, "issues": []},
                    "risk": {"score": 0, "issues": ["bad"]},
                }),
            ]
        )
        architect._generate = MagicMock(return_value="# Sprint Plan v1\n")
        architect._refine = MagicMock(return_value="# Sprint Plan v2\n")

        result = architect.execute()

        assert result == "sprint-plan.md"
        assert state.read_file("sprint-plan.md") == "# Sprint Plan v2\n"
        # Should call _generate once, then _refine once
        architect._generate.assert_called_once()
        architect._refine.assert_called_once()

    def test_returns_immediately_on_first_pass(self, state, config):
        """execute returns after first pass if it passes."""
        self._write_qwendea(state)

        llm = MagicMock(spec=LLMClient)
        architect = Architect(llm, state, config)

        architect._self_evaluate = MagicMock(
            return_value=(6, {
                "specificity": {"score": 1, "issues": []},
                "testability": {"score": 1, "issues": []},
                "evidence": {"score": 1, "issues": []},
                "completeness": {"score": 1, "issues": []},
                "feasibility": {"score": 1, "issues": []},
                "risk": {"score": 1, "issues": []},
            })
        )
        architect._generate = MagicMock(return_value="# Sprint Plan\n")
        architect._refine = MagicMock(return_value="# Sprint Plan v2\n")

        result = architect.execute()

        assert result == "sprint-plan.md"
        architect._generate.assert_called_once()
        architect._refine.assert_not_called()


class TestFormatFailures:
    """Test _format_failures helper."""

    def test_formats_single_failure(self, state, config):
        """_format_failures formats a single failed criterion."""
        llm = MagicMock(spec=LLMClient)
        architect = Architect(llm, state, config)

        eval_ = {
            "specificity": {"score": 1, "issues": []},
            "testability": {"score": 0, "issues": ["Task 1: 'Works' is not verifiable"]},
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }

        result = architect._format_failures(eval_)
        assert "FAILED: [Testability]" in result
        assert "not verifiable" in result

    def test_formats_multiple_failures(self, state, config):
        """_format_failures formats multiple failed criteria."""
        llm = MagicMock(spec=LLMClient)
        architect = Architect(llm, state, config)

        eval_ = {
            "specificity": {"score": 0, "issues": ["vague"]},
            "testability": {"score": 0, "issues": ["not verifiable"]},
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }

        result = architect._format_failures(eval_)
        assert "FAILED: [Specificity]" in result
        assert "FAILED: [Testability]" in result

    def test_returns_reason_for_malformed(self, state, config):
        """_format_failures returns reason for malformed evals."""
        llm = MagicMock(spec=LLMClient)
        architect = Architect(llm, state, config)

        result = architect._format_failures({"reason": "malformed"})
        assert result == "malformed"

    def test_returns_default_when_no_failures(self, state, config):
        """_format_failures returns default when all pass."""
        llm = MagicMock(spec=LLMClient)
        architect = Architect(llm, state, config)

        eval_ = {
            "specificity": {"score": 1, "issues": []},
            "testability": {"score": 1, "issues": []},
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }

        result = architect._format_failures(eval_)
        assert result == "No specific feedback available."
