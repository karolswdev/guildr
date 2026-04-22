"""Tests for deterministic next-step packet generation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from orchestrator.lib.intents import create_queued_intent
from orchestrator.lib.next_step import (
    build_next_step_packet,
    emit_next_step_packet_event,
    select_next_step,
)
from orchestrator.lib.state import State
from orchestrator.lib.workflow import default_workflow, save_workflow


def _state_with_workflow(tmp_path: Path) -> State:
    save_workflow(tmp_path, default_workflow())
    state = State(tmp_path)
    memory_dir = tmp_path / ".orchestrator" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "wake-up.md").write_text("wake", encoding="utf-8")
    return state


class _Events:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, **fields):
        event = {"type": event_type, **fields}
        self.events.append(event)
        return event


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


def test_emit_next_step_packet_event_uses_canonical_shape(tmp_path: Path) -> None:
    state = _state_with_workflow(tmp_path)
    with patch("orchestrator.lib.memory_palace.resolve_command", return_value=["mempalace"]):
        packet = build_next_step_packet(state, current_step="memory_refresh")
    assert packet is not None

    packet["source_refs"].append("artifact:README.md")
    packet["refined_by"] = "narrator"
    packet["base_packet_id"] = "next_base"
    packet["narrative_digest_id"] = "digest_1"
    events = _Events()

    emitted = emit_next_step_packet_event(events, "project-1", packet)

    assert emitted is events.events[0]
    assert emitted["type"] == "next_step_packet_created"
    assert emitted["project_id"] == "project-1"
    assert emitted["packet_id"] == packet["packet_id"]
    assert emitted["packet"] is packet
    assert emitted["memory_refs"] == [".orchestrator/memory/wake-up.md"]
    assert emitted["artifact_refs"] == ["README.md"]
    assert emitted["refined_by"] == "narrator"
    assert emitted["base_packet_id"] == "next_base"
    assert emitted["narrative_digest_id"] == "digest_1"
