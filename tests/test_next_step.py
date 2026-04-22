"""Tests for deterministic next-step packet generation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from orchestrator.lib.intents import create_queued_intent
from orchestrator.lib.next_step import build_next_step_packet, select_next_step
from orchestrator.lib.state import State
from orchestrator.lib.workflow import default_workflow, save_workflow


def _state_with_workflow(tmp_path: Path) -> State:
    save_workflow(tmp_path, default_workflow())
    state = State(tmp_path)
    memory_dir = tmp_path / ".orchestrator" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "wake-up.md").write_text("wake", encoding="utf-8")
    return state


def test_select_next_step_defaults_to_first_enabled_incomplete(tmp_path: Path) -> None:
    state = _state_with_workflow(tmp_path)

    step = select_next_step(state)

    assert step is not None
    assert step["id"] == "memory_refresh"


def test_select_next_step_after_completed_step(tmp_path: Path) -> None:
    state = _state_with_workflow(tmp_path)

    step = select_next_step(state, completed_step="memory_refresh")

    assert step is not None
    assert step["id"] == "persona_forum"


def test_current_step_packet_describes_step_about_to_run(tmp_path: Path) -> None:
    state = _state_with_workflow(tmp_path)

    step = select_next_step(state, current_step="memory_refresh")

    assert step is not None
    assert step["id"] == "memory_refresh"


def test_packet_includes_memory_provenance_and_source_refs(tmp_path: Path) -> None:
    state = _state_with_workflow(tmp_path)

    with patch("orchestrator.lib.memory_palace.resolve_command", return_value=["mempalace"]):
        packet = build_next_step_packet(state, current_step="memory_refresh")

    assert packet is not None
    assert packet["step"] == "memory_refresh"
    assert packet["packet_id"].startswith("next_")
    assert packet["memory_provenance"]["wake_up_hash"]
    assert packet["inputs"] == [
        {
            "kind": "memory",
            "ref": ".orchestrator/memory/wake-up.md",
            "label": "Wake-up packet",
        }
    ]
    assert "memory:.orchestrator/memory/wake-up.md" in packet["source_refs"]


def test_packet_includes_queued_intents_for_step(tmp_path: Path) -> None:
    state = _state_with_workflow(tmp_path)
    create_queued_intent(
        tmp_path,
        kind="interject",
        atom_id="memory_refresh",
        payload={"instruction": "Be careful"},
        client_intent_id="client-1",
        intent_event_id="event-1",
    )

    with patch("orchestrator.lib.memory_palace.resolve_command", return_value=["mempalace"]):
        packet = build_next_step_packet(state, current_step="memory_refresh")

    assert packet is not None
    assert packet["queued_intents"] == [
        {
            "client_intent_id": "client-1",
            "intent_event_id": "event-1",
            "kind": "interject",
            "atom_id": "memory_refresh",
            "payload": {"instruction": "Be careful"},
            "status": "queued",
        }
    ]
