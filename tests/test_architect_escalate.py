"""Tests for Architect escalation logic (H6.3e: opencode runner)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

from orchestrator.lib.config import Config
from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
)
from orchestrator.lib.state import State
from orchestrator.roles.architect import Architect, ArchitectFailure


def _result(text: str) -> OpencodeResult:
    message = OpencodeMessage(
        role="assistant",
        provider="fake",
        model="fake",
        tokens=OpencodeTokens(total=1, input=1, output=0),
        cost=0.0,
        text_parts=[text],
        tool_calls=[],
    )
    return OpencodeResult(
        session_id="ses_test",
        exit_code=0,
        directory=".",
        messages=[message],
        total_tokens=message.tokens,
        total_cost=0.0,
        summary_additions=0,
        summary_deletions=0,
        summary_files=0,
        raw_export={},
        raw_events=[],
    )


@dataclass
class _FakeRunner:
    responses: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)

    def run(self, prompt: str) -> OpencodeResult:
        self.prompts.append(prompt)
        if not self.responses:
            return _result("default")
        return _result(self.responses.pop(0))


@pytest.fixture
def state(tmp_path):
    return State(tmp_path)


@pytest.fixture
def config(tmp_path):
    return Config(
        llama_server_url="http://127.0.0.1:8080",
        project_dir=tmp_path,
        architect_max_passes=3,
        architect_pass_threshold=4,
    )


def _make_architect(state, config):
    return Architect(
        runner=_FakeRunner(),
        judge_runner=_FakeRunner(),
        state=state,
        config=config,
    )


class TestEscalationFiles:
    def test_writes_draft_files(self, state, config):
        architect = _make_architect(state, config)
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
        architect = _make_architect(state, config)
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
        architect = _make_architect(state, config)
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

    def test_escalation_lists_best_draft(self, state, config):
        architect = _make_architect(state, config)
        drafts = [
            ("# Draft 1\n", 5, {"specificity": {"score": 1, "issues": []}}),
            ("# Draft 2\n", 3, {"specificity": {"score": 1, "issues": []}}),
            ("# Draft 3\n", 4, {"specificity": {"score": 1, "issues": []}}),
        ]
        architect._escalate(drafts)
        escalation = (state.project_dir / ".orchestrator" / "escalation.md").read_text()
        assert "best draft is `drafts/architect-pass-1.md`" in escalation


class TestArchitectFailure:
    def _write_qwendea(self, state):
        (state.project_dir / "qwendea.md").write_text(
            "# Project: Test\n\n## Description\nA test project."
        )

    def test_raises_with_best_score(self, state, config):
        self._write_qwendea(state)
        architect = _make_architect(state, config)
        architect._self_evaluate = MagicMock(
            return_value=(2, {"specificity": {"score": 0, "issues": ["bad"]}})
        )
        architect._generate = MagicMock(return_value="# Draft 1\n")
        architect._refine = MagicMock(return_value="# Draft 2\n")

        with pytest.raises(ArchitectFailure) as exc_info:
            architect.execute()
        assert "3 passes" in str(exc_info.value)
        assert "best score: 2/6" in str(exc_info.value)

    def test_writes_drafts_on_failure(self, state, config):
        self._write_qwendea(state)
        architect = _make_architect(state, config)
        architect._self_evaluate = MagicMock(
            return_value=(2, {"specificity": {"score": 0, "issues": ["bad"]}})
        )
        architect._generate = MagicMock(return_value="# Draft 1\n")
        architect._refine = MagicMock(return_value="# Draft 2\n")

        with pytest.raises(ArchitectFailure):
            architect.execute()

        drafts_dir = state.project_dir / ".orchestrator" / "drafts"
        assert (drafts_dir / "architect-pass-1.md").exists()
        assert (drafts_dir / "architect-pass-2.md").exists()
        assert (drafts_dir / "architect-pass-3.md").exists()

    def test_writes_escalation_on_failure(self, state, config):
        self._write_qwendea(state)
        architect = _make_architect(state, config)
        architect._self_evaluate = MagicMock(
            return_value=(2, {"specificity": {"score": 0, "issues": ["bad"]}})
        )
        architect._generate = MagicMock(return_value="# Draft 1\n")
        architect._refine = MagicMock(return_value="# Draft 2\n")

        with pytest.raises(ArchitectFailure):
            architect.execute()
        assert (state.project_dir / ".orchestrator" / "escalation.md").exists()


class TestExecuteSuccess:
    def _write_qwendea(self, state):
        (state.project_dir / "qwendea.md").write_text(
            "# Project: Test\n\n## Description\nA test project."
        )

    def test_writes_sprint_plan_on_pass(self, state, config):
        self._write_qwendea(state)
        architect = _make_architect(state, config)
        architect._self_evaluate = MagicMock(side_effect=[
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
        ])
        architect._generate = MagicMock(return_value="# Sprint Plan v1\n")
        architect._refine = MagicMock(return_value="# Sprint Plan v2\n")

        result = architect.execute()
        assert result == "sprint-plan.md"
        assert state.read_file("sprint-plan.md") == "# Sprint Plan v2\n"
        architect._generate.assert_called_once()
        architect._refine.assert_called_once()

    def test_returns_immediately_on_first_pass(self, state, config):
        self._write_qwendea(state)
        architect = _make_architect(state, config)
        architect._self_evaluate = MagicMock(return_value=(6, {
            c: {"score": 1, "issues": []} for c in
            ["specificity", "testability", "evidence",
             "completeness", "feasibility", "risk"]
        }))
        architect._generate = MagicMock(return_value="# Sprint Plan\n")
        architect._refine = MagicMock(return_value="# Sprint Plan v2\n")

        result = architect.execute()
        assert result == "sprint-plan.md"
        architect._generate.assert_called_once()
        architect._refine.assert_not_called()


class TestFormatFailures:
    def test_formats_single_failure(self, state, config):
        architect = _make_architect(state, config)
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
        architect = _make_architect(state, config)
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
        architect = _make_architect(state, config)
        assert architect._format_failures({"reason": "malformed"}) == "malformed"

    def test_returns_default_when_no_failures(self, state, config):
        architect = _make_architect(state, config)
        eval_ = {c: {"score": 1, "issues": []} for c in
                 ["specificity", "testability", "evidence",
                  "completeness", "feasibility", "risk"]}
        assert architect._format_failures(eval_) == "No specific feedback available."
