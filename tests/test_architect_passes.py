"""Tests for Architect pass/fail logic (H6.3e: opencode runner)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from orchestrator.lib.config import Config
from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
)
from orchestrator.lib.state import State
from orchestrator.roles.architect import Architect


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
        project_dir=Path(tmp_path),
        architect_max_passes=3,
        architect_pass_threshold=4,
    )


@pytest.fixture
def architect(state, config):
    return Architect(
        runner=_FakeRunner(),
        judge_runner=_FakeRunner(),
        state=state,
        config=config,
    )


class TestPassFailLogic:
    def _make_eval(self, **scores):
        defaults = {c: {"score": 0, "issues": []} for c in
                    ["specificity", "testability", "evidence",
                     "completeness", "feasibility", "risk"]}
        for k, v in scores.items():
            defaults[k] = {"score": v, "issues": []}
        return defaults

    def test_score_5_with_testability_0_fails(self, architect):
        eval_ = self._make_eval(specificity=1, testability=0, evidence=1,
                                completeness=1, feasibility=1, risk=1)
        assert architect._passes(5, eval_) is False

    def test_score_5_with_evidence_0_fails(self, architect):
        eval_ = self._make_eval(specificity=1, testability=1, evidence=0,
                                completeness=1, feasibility=1, risk=1)
        assert architect._passes(5, eval_) is False

    def test_score_4_with_mandatory_1_passes(self, architect):
        eval_ = self._make_eval(specificity=1, testability=1, evidence=1,
                                completeness=1, feasibility=0, risk=0)
        assert architect._passes(4, eval_) is True

    def test_score_6_passes(self, architect):
        eval_ = self._make_eval(specificity=1, testability=1, evidence=1,
                                completeness=1, feasibility=1, risk=1)
        assert architect._passes(6, eval_) is True

    def test_score_3_below_threshold_fails(self, architect):
        eval_ = self._make_eval(specificity=1, testability=1, evidence=1,
                                completeness=0, feasibility=0, risk=0)
        assert architect._passes(3, eval_) is False

    def test_score_4_with_testability_0_fails(self, architect):
        eval_ = self._make_eval(specificity=1, testability=0, evidence=1,
                                completeness=1, feasibility=1, risk=0)
        assert architect._passes(4, eval_) is False

    def test_score_5_with_both_mandatory_passes(self, architect):
        eval_ = self._make_eval(specificity=1, testability=1, evidence=1,
                                completeness=1, feasibility=1, risk=0)
        assert architect._passes(5, eval_) is True

    def test_empty_evaluation_fails(self, architect):
        assert architect._passes(0, {}) is False

    def test_missing_mandatory_treated_as_zero(self, architect):
        eval_ = {
            "specificity": {"score": 1, "issues": []},
            "testability": {"score": 1, "issues": []},
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }
        assert architect._passes(5, eval_) is False


class TestRetryDraftTracking:
    """Regression: a malformed first eval shouldn't block refinement."""

    def test_zero_score_first_draft_can_be_refined(self, state, config):
        (state.project_dir / "qwendea.md").write_text("# Project\n\nBuild x.\n")

        refined_plan = (
            "# Sprint Plan\n\n"
            "## Overview\nRefined.\n\n"
            "## Memory Tiers\n"
            "- **Global Memory:** keep scope crisp.\n"
            "- **Sprint Memory:** deliver one coherent task.\n"
            "- **Task Packet Memory:** preserve file, evidence, and invariants.\n\n"
            "## Traceability Matrix\n- `REQ-1` -> Task 1\n\n"
            "## Tasks\n\n"
            "### Task 1: Refined\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `x.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [ ] Done\n\n"
            "**Implementation Notes:**\n"
            "Source Requirements: `REQ-1`\n"
            "Task Memory: keep the task small.\n"
            "Determinism Notes: use pytest as the deciding signal.\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n"
        )
        good_json = (
            '{"specificity":{"score":1,"issues":[]},'
            '"testability":{"score":1,"issues":[]},'
            '"evidence":{"score":1,"issues":[]},'
            '"completeness":{"score":1,"issues":[]},'
            '"feasibility":{"score":1,"issues":[]},'
            '"risk":{"score":1,"issues":[]}}'
        )

        runner = _FakeRunner(responses=[
            "# Sprint Plan\n\n## Tasks\n\n### Task 1: vague\n",
            refined_plan,
        ])
        judge_runner = _FakeRunner(responses=[
            "not json",
            "still not json",
            good_json,
        ])
        architect = Architect(
            runner=runner,
            judge_runner=judge_runner,
            state=state,
            config=config,
        )

        result = architect.execute()

        assert result == "sprint-plan.md"
        assert (state.project_dir / "sprint-plan.md").exists()
