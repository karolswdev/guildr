"""Tests for Architect pass/fail logic with mandatory criteria."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orchestrator.lib.config import Config
from orchestrator.lib.llm import LLMClient
from orchestrator.lib.state import State
from orchestrator.roles.architect import Architect


@pytest.fixture
def state(tmp_path):
    """Create a State instance backed by a temp directory."""
    return State(tmp_path)


@pytest.fixture
def config(tmp_path):
    """Create a minimal Config."""
    from pathlib import Path
    return Config(
        llama_server_url="http://192.168.1.13:8080",
        project_dir=Path(tmp_path),
        architect_max_passes=3,
        architect_pass_threshold=4,
    )


@pytest.fixture
def architect(state, config):
    """Create an Architect instance."""
    llm = MagicMock(spec=LLMClient)
    return Architect(llm, state, config)


class TestPassFailLogic:
    """Test the _passes method against all 5 required cases."""

    def _make_eval(self, **scores):
        """Helper to create an evaluation dict with specified scores."""
        defaults = {
            "specificity": {"score": 0, "issues": []},
            "testability": {"score": 0, "issues": []},
            "evidence": {"score": 0, "issues": []},
            "completeness": {"score": 0, "issues": []},
            "feasibility": {"score": 0, "issues": []},
            "risk": {"score": 0, "issues": []},
        }
        defaults.update(scores)
        return defaults

    def test_score_5_with_testability_0_fails(self, architect):
        """Score 5/6 with Testability=0 → FAIL (mandatory)."""
        eval_ = self._make_eval(
            specificity=1, testability=0, evidence=1,
            completeness=1, feasibility=1, risk=1,
        )
        assert architect._passes(5, eval_) is False

    def test_score_5_with_evidence_0_fails(self, architect):
        """Score 5/6 with Evidence=0 → FAIL (mandatory)."""
        eval_ = self._make_eval(
            specificity=1, testability=1, evidence=0,
            completeness=1, feasibility=1, risk=1,
        )
        assert architect._passes(5, eval_) is False

    def test_score_4_with_mandatory_1_passes(self, architect):
        """Score 4/6 with Testability=1 AND Evidence=1 → PASS."""
        eval_ = self._make_eval(
            specificity=1, testability=1, evidence=1,
            completeness=1, feasibility=0, risk=0,
        )
        assert architect._passes(4, eval_) is True

    def test_score_6_passes(self, architect):
        """Score 6/6 → PASS."""
        eval_ = self._make_eval(
            specificity=1, testability=1, evidence=1,
            completeness=1, feasibility=1, risk=1,
        )
        assert architect._passes(6, eval_) is True

    def test_score_3_below_threshold_fails(self, architect):
        """Score 3/6 with all mandatory=1 → FAIL (below threshold)."""
        eval_ = self._make_eval(
            specificity=1, testability=1, evidence=1,
            completeness=0, feasibility=0, risk=0,
        )
        assert architect._passes(3, eval_) is False

    def test_score_4_with_testability_0_fails(self, architect):
        """Score 4/6 with Testability=0 → FAIL (mandatory)."""
        eval_ = self._make_eval(
            specificity=1, testability=0, evidence=1,
            completeness=1, feasibility=1, risk=0,
        )
        assert architect._passes(4, eval_) is False

    def test_score_4_with_evidence_0_fails(self, architect):
        """Score 4/6 with Evidence=0 → FAIL (mandatory)."""
        eval_ = self._make_eval(
            specificity=1, testability=1, evidence=0,
            completeness=1, feasibility=1, risk=0,
        )
        assert architect._passes(4, eval_) is False

    def test_score_5_with_both_mandatory_passes(self, architect):
        """Score 5/6 with both mandatory=1 → PASS."""
        eval_ = self._make_eval(
            specificity=1, testability=1, evidence=1,
            completeness=1, feasibility=1, risk=0,
        )
        assert architect._passes(5, eval_) is True

    def test_score_exactly_at_threshold(self, architect):
        """Score exactly at threshold with mandatory met → PASS."""
        eval_ = self._make_eval(
            specificity=1, testability=1, evidence=1,
            completeness=1, feasibility=0, risk=0,
        )
        assert architect._passes(4, eval_) is True

    def test_score_below_threshold_fails_even_with_mandatory(self, architect):
        """Score 2/6 with mandatory met → FAIL (below threshold)."""
        eval_ = self._make_eval(
            specificity=1, testability=1, evidence=1,
            completeness=0, feasibility=0, risk=0,
        )
        assert architect._passes(2, eval_) is False

    def test_empty_evaluation_fails(self, architect):
        """Empty evaluation dict → FAIL."""
        assert architect._passes(0, {}) is False

    def test_missing_mandatory_treated_as_zero(self, architect):
        """Missing mandatory criteria entries → FAIL."""
        eval_ = {
            "specificity": {"score": 1, "issues": []},
            "testability": {"score": 1, "issues": []},
            # evidence is missing
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }
        # Score would be 5 but evidence is missing → treated as 0
        assert architect._passes(5, eval_) is False
