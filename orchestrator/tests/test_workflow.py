"""Tests for workflow definitions and low-context phase files."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from orchestrator.lib.workflow import load_workflow, save_workflow, valid_start_steps
from orchestrator.lib.state import State
from orchestrator.roles.guru_escalation import GuruEscalation
from orchestrator.roles.micro_task_breaker import MicroTaskBreaker


def test_default_workflow_contains_microtask_and_guru_steps(tmp_path: Path) -> None:
    steps = load_workflow(tmp_path)
    ids = [step["id"] for step in steps]
    assert "micro_task_breakdown" in ids
    assert "guru_escalation" in ids
    assert "architect" in valid_start_steps(tmp_path)


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
