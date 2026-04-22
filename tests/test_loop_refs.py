"""Tests for ``orchestrator.lib.loop_refs``.

Two guarantees the helper must provide:

1. A ref is a promise that the referenced artifact exists. Missing
   files never leak into the returned lists.
2. ``include_outputs=False`` suppresses the phase's output artifacts
   (so ``loop_entered`` / ``loop_blocked`` on exception don't imply
   the phase produced anything), while memory + task-evidence refs
   still come through.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.engine import Orchestrator
from orchestrator.lib.config import Config
from orchestrator.lib.loop_refs import refs_for_phase
from orchestrator.lib.state import State


_TASK_PLAN = (
    "# Sprint Plan\n\n"
    "## Architecture Decisions\n- None\n\n"
    "## Tasks\n\n"
    "### Task 1: Seed\n"
    "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
    "Source Requirements: qwendea §1\nTask Memory: none\nDeterminism Notes: ok\n\n"
    "**Acceptance Criteria:**\n- [ ] Works\n\n"
    "**Evidence Required:**\n- Run `pytest`\n\n"
    "**Evidence Log:**\n- [x] Done\n\n"
    "### Task 2: Ship\n"
    "- **Priority**: P1\n- **Dependencies**: task-1\n- **Files**: `b.py`\n\n"
    "Source Requirements: qwendea §2\nTask Memory: none\nDeterminism Notes: ok\n\n"
    "**Acceptance Criteria:**\n- [ ] Works\n\n"
    "**Evidence Required:**\n- Run `pytest -k b`\n\n"
    "**Evidence Log:**\n- [ ] Pending\n\n"
    "## Memory Tiers\n- ephemeral\n\n"
    "## Traceability Matrix\n- qwendea §1 → task-1\n- qwendea §2 → task-2\n\n"
    "## Risks & Mitigations\n1. Risk — Mitigation\n"
)


@pytest.fixture
def state(tmp_path: Path) -> State:
    return State(tmp_path)


def test_missing_files_are_filtered_out(state: State) -> None:
    refs = refs_for_phase("architect", state)
    assert refs == {"artifact_refs": [], "evidence_refs": [], "memory_refs": []}


def test_architect_refs_include_sprint_plan_when_written(state: State) -> None:
    (state.project_dir / "sprint-plan.md").write_text("stub", encoding="utf-8")
    refs = refs_for_phase("architect", state)
    assert refs["artifact_refs"] == ["sprint-plan.md"]


def test_include_outputs_false_omits_phase_outputs(state: State) -> None:
    (state.project_dir / "sprint-plan.md").write_text("stub", encoding="utf-8")
    refs = refs_for_phase("architect", state, include_outputs=False)
    assert refs["artifact_refs"] == []


def test_architect_plan_exposes_draft_and_status_on_fail(state: State) -> None:
    drafts = state.project_dir / ".orchestrator" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "architect-pass-1.md").write_text("draft", encoding="utf-8")
    (drafts / "architect-plan-status.json").write_text(
        json.dumps({"status": "needs_refine"}), encoding="utf-8"
    )
    refs = refs_for_phase("architect_plan", state)
    assert ".orchestrator/drafts/architect-pass-1.md" in refs["artifact_refs"]
    assert ".orchestrator/drafts/architect-plan-status.json" in refs["artifact_refs"]
    assert "sprint-plan.md" not in refs["artifact_refs"]


def test_testing_evidence_refs_expand_to_task_ids(state: State) -> None:
    (state.project_dir / "sprint-plan.md").write_text(_TASK_PLAN, encoding="utf-8")
    (state.project_dir / "TEST_REPORT.md").write_text("all good", encoding="utf-8")
    refs = refs_for_phase("testing", state)
    assert refs["evidence_refs"] == ["task-1", "task-2"]
    assert refs["artifact_refs"] == ["TEST_REPORT.md"]
    assert refs["memory_refs"] == ["sprint-plan.md"]


def test_implementation_adds_task_files_that_exist(state: State) -> None:
    (state.project_dir / "sprint-plan.md").write_text(_TASK_PLAN, encoding="utf-8")
    (state.project_dir / "a.py").write_text("# a", encoding="utf-8")
    # b.py deliberately missing — should not appear in artifact_refs
    refs = refs_for_phase("implementation", state)
    assert "a.py" in refs["artifact_refs"]
    assert "b.py" not in refs["artifact_refs"]
    assert refs["evidence_refs"] == ["task-1", "task-2"]


def test_review_memory_refs_include_test_report(state: State) -> None:
    (state.project_dir / "sprint-plan.md").write_text(_TASK_PLAN, encoding="utf-8")
    (state.project_dir / "TEST_REPORT.md").write_text("ok", encoding="utf-8")
    (state.project_dir / "REVIEW.md").write_text("APPROVED", encoding="utf-8")
    refs = refs_for_phase("review", state)
    assert refs["artifact_refs"] == ["REVIEW.md"]
    assert refs["memory_refs"] == ["sprint-plan.md", "TEST_REPORT.md"]
    assert refs["evidence_refs"] == ["task-1", "task-2"]


def test_unknown_phase_returns_empty_lists(state: State) -> None:
    assert refs_for_phase("nonexistent_phase", state) == {
        "artifact_refs": [],
        "evidence_refs": [],
        "memory_refs": [],
    }


class _CapturingEvents:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, **fields) -> None:
        self.events.append({"type": event_type, **fields})


def test_engine_loop_completed_carries_refs(tmp_path: Path) -> None:
    """End-to-end: a phase that produces an artifact emits
    ``loop_completed`` with that artifact in ``artifact_refs``."""
    (tmp_path / "qwendea.md").write_text("# P\n", encoding="utf-8")
    config = Config(
        llama_server_url="http://unused",
        project_dir=tmp_path,
        max_retries=1,
    )
    events = _CapturingEvents()
    orch = Orchestrator(config=config, events=events, git_ops=MagicMock())

    def produce_test_report() -> None:
        (tmp_path / "TEST_REPORT.md").write_text("ok", encoding="utf-8")

    orch._run_phase("testing", produce_test_report)

    completed = [e for e in events.events if e.get("type") == "loop_completed"]
    assert completed, "no loop_completed emitted"
    assert "TEST_REPORT.md" in completed[-1]["artifact_refs"]


def test_engine_loop_entered_omits_outputs(tmp_path: Path) -> None:
    """``loop_entered`` fires before the phase runs, so output artifacts
    shouldn't appear even if (stale copies of) them exist on disk."""
    (tmp_path / "qwendea.md").write_text("# P\n", encoding="utf-8")
    (tmp_path / "TEST_REPORT.md").write_text("stale", encoding="utf-8")
    config = Config(
        llama_server_url="http://unused",
        project_dir=tmp_path,
        max_retries=1,
    )
    events = _CapturingEvents()
    orch = Orchestrator(config=config, events=events, git_ops=MagicMock())

    orch._run_phase("testing", lambda: None)

    entered = [e for e in events.events if e.get("type") == "loop_entered"]
    assert entered
    assert "TEST_REPORT.md" not in entered[0]["artifact_refs"]
