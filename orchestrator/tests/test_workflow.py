"""Tests for workflow definitions and low-context phase files."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.lib.workflow import load_workflow, save_workflow, valid_start_steps
from orchestrator.lib.state import State
from orchestrator.roles.guru_escalation import GuruEscalation
from orchestrator.roles.memory_refresh import MemoryRefresh
from orchestrator.roles.micro_task_breaker import MicroTaskBreaker
from orchestrator.roles.persona_forum import PersonaForum


class CaptureEvents:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, **fields) -> None:
        self.events.append({"type": event_type, **fields})


def test_default_workflow_contains_persona_microtask_and_guru_steps(tmp_path: Path) -> None:
    steps = load_workflow(tmp_path)
    ids = [step["id"] for step in steps]
    assert "memory_refresh" in ids
    assert "persona_forum" in ids
    assert "micro_task_breakdown" in ids
    assert "guru_escalation" in ids
    assert "memory_refresh" in valid_start_steps(tmp_path)


def test_memory_refresh_returns_wakeup_artifact(tmp_path: Path) -> None:
    state = State(tmp_path)
    memory_dir = tmp_path / ".orchestrator" / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "wake-up.md").write_text("L0", encoding="utf-8")
    with patch(
        "orchestrator.roles.memory_refresh.sync_project_memory",
        return_value={
            "project_id": tmp_path.name,
            "available": True,
            "initialized": True,
            "wing": tmp_path.name,
            "wake_up": "L0",
            "wake_up_hash": "hash123",
            "wake_up_bytes": 2,
            "memory_refs": [".orchestrator/memory/wake-up.md"],
        },
    ):
        result = MemoryRefresh(state).execute()

    assert result == ".orchestrator/memory/wake-up.md"
    assert (tmp_path / ".orchestrator" / "control" / "context.compact.md").exists()


def test_memory_refresh_emits_provenance_event(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.events = CaptureEvents()
    memory_dir = tmp_path / ".orchestrator" / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "wake-up.md").write_text("L0", encoding="utf-8")

    with patch(
        "orchestrator.roles.memory_refresh.sync_project_memory",
        return_value={
            "project_id": "project-1",
            "available": True,
            "initialized": True,
            "wing": "project-1",
            "wake_up": "L0",
            "wake_up_hash": "hash123",
            "wake_up_bytes": 2,
            "memory_refs": [".orchestrator/memory/wake-up.md"],
        },
    ):
        MemoryRefresh(state).execute()

    assert state.events is not None
    event = state.events.events[-1]
    assert event["type"] == "memory_refreshed"
    assert event["wake_up_hash"] == "hash123"
    assert event["memory_refs"] == [".orchestrator/memory/wake-up.md"]
    assert ".orchestrator/memory/wake-up.md" in event["artifact_refs"]
    assert event["compact_context"]["path"] == ".orchestrator/control/context.compact.md"


def test_memory_refresh_emits_memory_error_before_reraising(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.events = CaptureEvents()

    with patch("orchestrator.roles.memory_refresh.sync_project_memory", side_effect=RuntimeError("no palace")):
        with pytest.raises(RuntimeError):
            MemoryRefresh(state).execute()

    assert state.events is not None
    event = state.events.events[-1]
    assert event["type"] == "memory_error"
    assert event["step"] == "memory_refresh"
    assert "no palace" in event["error"]


def test_persona_forum_writes_roster_and_forum_artifacts(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.write_file("qwendea.md", "# Project\n\nBuild a game with tactical combat.\n")

    forum = PersonaForum(state)
    result = forum.execute()

    assert result == "PERSONA_FORUM.md"
    assert (tmp_path / "PERSONA_FORUM.md").exists()
    assert (tmp_path / "FOUNDING_TEAM.json").exists()
    assert "Player Advocate" in (tmp_path / "PERSONA_FORUM.md").read_text(encoding="utf-8")
    workflow = load_workflow(tmp_path)
    persona_step = next(step for step in workflow if step["id"] == "persona_forum")
    personas = persona_step["config"]["personas"]
    assert personas[0]["turn_order"] == 1
    assert "veto_scope" in personas[0]


def test_micro_task_breaker_writes_phase_files(tmp_path: Path) -> None:
    project_dir = tmp_path
    state = State(project_dir)
    state.write_file(
        "sprint-plan.md",
        "# Sprint Plan\n\n"
        "## Architecture Decisions\n- Use FastAPI\n\n"
        "## Tasks\n\n"
        "### Task 1: Setup API\n"
        "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `app.py`\n\n"
        "**Acceptance Criteria:**\n- [ ] API exists\n\n"
        "**Evidence Required:**\n- Run `pytest -q`\n\n"
        "**Evidence Log:**\n- [ ] pending\n\n"
        "## Risks & Mitigations\n1. None - none\n",
    )
    state.write_file("qwendea.md", "# Project\n\nBuild it.\n")

    breaker = MicroTaskBreaker(state)
    result = breaker.execute("sprint-plan.md")

    assert result == "phase-files/INDEX.md"
    assert (project_dir / "phase-files" / "INDEX.md").exists()
    assert (project_dir / "phase-files" / "task-001-implement.md").exists()
    assert (project_dir / "phase-files" / "task-001-verify.md").exists()


def test_guru_escalation_writes_summary_even_when_providers_missing(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.current_phase = "testing"
    state.write_file("qwendea.md", "# Project\n\nBuild it.\n")
    with patch("shutil.which", return_value=None):
        escalation = GuruEscalation(state, step_config={"providers": [{"kind": "codex"}, {"kind": "claude"}]})
        result = escalation.execute()

    assert result == "ESCALATION_PLAN.md"
    summary = (tmp_path / "ESCALATION_PLAN.md").read_text(encoding="utf-8")
    assert "codex" in summary
    assert "missing" in summary


def test_custom_checkpoint_can_be_saved(tmp_path: Path) -> None:
    steps = load_workflow(tmp_path)
    steps.insert(2, {
        "id": "user_checkpoint",
        "title": "User Checkpoint",
        "type": "checkpoint",
        "handler": "operator_checkpoint",
        "enabled": True,
        "description": "Pause here for operator input.",
    })
    saved = save_workflow(tmp_path, steps)

    ids = [step["id"] for step in saved]
    assert "user_checkpoint" in ids


def test_legacy_workflow_is_migrated_with_new_persona_forum_step(tmp_path: Path) -> None:
    legacy = [
        {
            "id": "architect",
            "title": "Architect",
            "type": "phase",
            "handler": "architect",
            "enabled": True,
        },
        {
            "id": "deployment",
            "title": "Deployment",
            "type": "phase",
            "handler": "deployment",
            "enabled": True,
        },
    ]
    save_workflow(tmp_path, legacy)

    steps = load_workflow(tmp_path)

    ids = [step["id"] for step in steps]
    assert "memory_refresh" in ids
    assert "persona_forum" in ids
    assert ids.index("memory_refresh") < ids.index("persona_forum")
    assert ids.index("persona_forum") < ids.index("architect")
