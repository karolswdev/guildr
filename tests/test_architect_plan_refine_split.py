"""H6.5 — Architect plan()/refine() split + approve_plan_draft gate.

After H6.5 the architect role is split into two engine phases with a
human gate between:

  architect_plan → approve_plan_draft → architect_refine

These tests lock in three invariants:

1. ``plan()`` stops after pass 1, persists a status file, and writes
   either ``sprint-plan.md`` (pass rubric) or a numbered draft under
   ``.orchestrator/drafts/`` (fail rubric).
2. ``refine()`` resumes from the draft and runs additional passes, or
   no-ops when pass 1 already succeeded.
3. The engine auto-approves ``approve_plan_draft`` when pass 1 already
   produced a passing plan — the human only sees the gate when there's
   a draft to review.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.engine import Orchestrator
from orchestrator.lib.config import Config
from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
)
from orchestrator.lib.state import State
from orchestrator.roles.architect import Architect, ArchitectFailure


_SPRINT_PLAN_MIN = (
    "# Sprint Plan\n\n"
    "## Architecture Decisions\n- None\n\n"
    "## Tasks\n\n"
    "### Task 1: Setup\n"
    "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
    "Source Requirements: qwendea §1\n"
    "Task Memory: none\n"
    "Determinism Notes: deterministic\n\n"
    "**Acceptance Criteria:**\n- [ ] Works\n\n"
    "**Evidence Required:**\n- Run `pytest`\n\n"
    "**Evidence Log:**\n- [x] Done\n\n"
    "## Memory Tiers\n- ephemeral\n\n"
    "## Traceability Matrix\n- qwendea §1 → task-1\n\n"
    "## Risks & Mitigations\n1. Risk — Mitigation\n"
)

_PASSING_JUDGE = json.dumps({
    "specificity": {"score": 1, "issues": []},
    "testability": {"score": 1, "issues": []},
    "evidence": {"score": 1, "issues": []},
    "completeness": {"score": 1, "issues": []},
    "feasibility": {"score": 1, "issues": []},
    "risk": {"score": 1, "issues": []},
})

_FAILING_JUDGE = json.dumps({
    "specificity": {"score": 0, "issues": ["too vague"]},
    "testability": {"score": 0, "issues": ["no tests named"]},
    "evidence": {"score": 0, "issues": ["no evidence"]},
    "completeness": {"score": 1, "issues": []},
    "feasibility": {"score": 1, "issues": []},
    "risk": {"score": 1, "issues": []},
})


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
        text = self.responses.pop(0) if self.responses else "default"
        return _result(text)


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    (tmp_path / "qwendea.md").write_text("# Project\n\nBuild a thing.\n")
    return tmp_path


@pytest.fixture
def state(project_dir: Path) -> State:
    return State(project_dir)


@pytest.fixture
def config(project_dir: Path) -> Config:
    return Config(
        llama_server_url="http://unused",
        project_dir=project_dir,
        architect_max_passes=3,
        architect_pass_threshold=6,
    )


def _status_path(project_dir: Path) -> Path:
    return project_dir / ".orchestrator" / "drafts" / "architect-plan-status.json"


class TestPlanPhase:
    """architect_plan writes sprint-plan.md xor stashes a draft."""

    def test_plan_pass_1_passes_rubric_writes_sprint_plan(
        self, state: State, config: Config, project_dir: Path
    ) -> None:
        runner = _FakeRunner(responses=[_SPRINT_PLAN_MIN])
        judge = _FakeRunner(responses=[_PASSING_JUDGE])
        architect = Architect(runner=runner, judge_runner=judge, state=state, config=config)

        status = architect.plan()

        assert (project_dir / "sprint-plan.md").exists()
        assert status["status"] == "done"
        assert status["pass_num"] == 1
        saved = json.loads(_status_path(project_dir).read_text())
        assert saved["status"] == "done"

    def test_plan_pass_1_fails_rubric_stashes_draft(
        self, state: State, config: Config, project_dir: Path
    ) -> None:
        runner = _FakeRunner(responses=[_SPRINT_PLAN_MIN])
        judge = _FakeRunner(responses=[_FAILING_JUDGE])
        architect = Architect(runner=runner, judge_runner=judge, state=state, config=config)

        status = architect.plan()

        assert not (project_dir / "sprint-plan.md").exists()
        assert status["status"] == "needs_refine"
        draft = project_dir / ".orchestrator" / "drafts" / "architect-pass-1.md"
        assert draft.exists()
        assert draft.read_text() == _SPRINT_PLAN_MIN.strip()


class TestRefinePhase:
    """architect_refine resumes from draft or no-ops."""

    def test_refine_noop_when_pass_1_already_done(
        self, state: State, config: Config, project_dir: Path
    ) -> None:
        runner = _FakeRunner(responses=[_SPRINT_PLAN_MIN])
        judge = _FakeRunner(responses=[_PASSING_JUDGE])
        architect = Architect(runner=runner, judge_runner=judge, state=state, config=config)
        architect.plan()

        # Fresh runners for refine — they must not be called.
        refine_runner = _FakeRunner()
        refine_judge = _FakeRunner()
        architect_r = Architect(
            runner=refine_runner, judge_runner=refine_judge, state=state, config=config
        )
        result = architect_r.refine()

        assert result == "sprint-plan.md"
        assert refine_runner.prompts == []
        assert refine_judge.prompts == []

    def test_refine_resumes_from_draft_and_produces_plan(
        self, state: State, config: Config, project_dir: Path
    ) -> None:
        plan_runner = _FakeRunner(responses=[_SPRINT_PLAN_MIN])
        plan_judge = _FakeRunner(responses=[_FAILING_JUDGE])
        Architect(
            runner=plan_runner, judge_runner=plan_judge, state=state, config=config
        ).plan()
        assert not (project_dir / "sprint-plan.md").exists()

        refine_runner = _FakeRunner(responses=[_SPRINT_PLAN_MIN])
        refine_judge = _FakeRunner(responses=[_PASSING_JUDGE])
        result = Architect(
            runner=refine_runner, judge_runner=refine_judge, state=state, config=config
        ).refine()

        assert result == "sprint-plan.md"
        assert (project_dir / "sprint-plan.md").exists()
        assert refine_runner.prompts, "refine did not call architect runner"
        assert refine_judge.prompts, "refine did not call judge runner"

    def test_refine_escalates_when_every_pass_fails(
        self, state: State, config: Config, project_dir: Path
    ) -> None:
        plan_runner = _FakeRunner(responses=[_SPRINT_PLAN_MIN])
        plan_judge = _FakeRunner(responses=[_FAILING_JUDGE])
        Architect(
            runner=plan_runner, judge_runner=plan_judge, state=state, config=config
        ).plan()

        refine_runner = _FakeRunner(responses=[_SPRINT_PLAN_MIN, _SPRINT_PLAN_MIN])
        refine_judge = _FakeRunner(responses=[_FAILING_JUDGE, _FAILING_JUDGE])
        architect = Architect(
            runner=refine_runner, judge_runner=refine_judge, state=state, config=config
        )
        with pytest.raises(ArchitectFailure):
            architect.refine()

        escalation = project_dir / ".orchestrator" / "escalation.md"
        assert escalation.exists()


class TestApprovePlanDraftGate:
    """Engine auto-approves the gate when pass 1 already passed."""

    def _make_orchestrator(self, config: Config) -> Orchestrator:
        orch = Orchestrator(config=config, git_ops=MagicMock())
        orch._gate = MagicMock()
        return orch

    def test_gate_auto_approved_when_status_done(
        self, config: Config, project_dir: Path
    ) -> None:
        drafts = project_dir / ".orchestrator" / "drafts"
        drafts.mkdir(parents=True)
        (drafts / "architect-plan-status.json").write_text(
            json.dumps({"status": "done", "score": 6, "pass_num": 1})
        )

        orch = self._make_orchestrator(config)
        orch._run_gate_or_checkpoint(
            {"id": "approve_plan_draft", "type": "gate", "handler": "approve_plan_draft"}
        )

        orch._gate.assert_not_called()
        assert orch.state.gates_approved["approve_plan_draft"] is True

    def test_gate_fires_when_status_needs_refine(
        self, config: Config, project_dir: Path
    ) -> None:
        drafts = project_dir / ".orchestrator" / "drafts"
        drafts.mkdir(parents=True)
        (drafts / "architect-plan-status.json").write_text(
            json.dumps({"status": "needs_refine", "score": 3, "pass_num": 1})
        )

        orch = self._make_orchestrator(config)
        orch._run_gate_or_checkpoint(
            {"id": "approve_plan_draft", "type": "gate", "handler": "approve_plan_draft"}
        )

        orch._gate.assert_called_once_with("approve_plan_draft")

    def test_gate_fires_when_status_file_missing(
        self, config: Config, project_dir: Path
    ) -> None:
        orch = self._make_orchestrator(config)
        orch._run_gate_or_checkpoint(
            {"id": "approve_plan_draft", "type": "gate", "handler": "approve_plan_draft"}
        )

        orch._gate.assert_called_once_with("approve_plan_draft")


class TestLegacyExecuteWrapper:
    """execute() still runs the full two-pass loop for legacy workflows."""

    def test_execute_runs_plan_then_refine_back_to_back(
        self, state: State, config: Config, project_dir: Path
    ) -> None:
        runner = _FakeRunner(responses=[_SPRINT_PLAN_MIN, _SPRINT_PLAN_MIN])
        judge = _FakeRunner(responses=[_FAILING_JUDGE, _PASSING_JUDGE])
        result = Architect(
            runner=runner, judge_runner=judge, state=state, config=config
        ).execute()

        assert result == "sprint-plan.md"
        assert (project_dir / "sprint-plan.md").exists()
