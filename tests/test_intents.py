"""Tests for the durable operator intent registry."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.lib.control import append_operator_context
from orchestrator.lib.intents import (
    consume_prompt_intents,
    create_queued_intent,
    ignore_queued_intents_for_passed_step,
    intents_path,
    queued_intents_for_step,
)


class _Events:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event_type: str, **fields) -> None:
        self.events.append((event_type, dict(fields)))


def test_create_queued_intent_persists_scrubbed_row(tmp_path: Path) -> None:
    row = create_queued_intent(
        tmp_path,
        kind="interject",
        atom_id="implementation",
        payload={"instruction": "Use pathlib", "api_key": "sk-secret-value"},
        client_intent_id="client-1",
        intent_event_id="event-1",
    )

    assert row["client_intent_id"] == "client-1"
    assert row["intent_event_id"] == "event-1"
    assert row["status"] == "queued"
    text = intents_path(tmp_path).read_text(encoding="utf-8")
    assert "sk-secret-value" not in text
    assert "[redacted]" in text
    persisted = json.loads(text)
    assert persisted["payload"]["instruction"] == "Use pathlib"


def test_queued_intents_for_step_filters_by_atom(tmp_path: Path) -> None:
    create_queued_intent(
        tmp_path,
        kind="interject",
        atom_id="implementation",
        payload={"instruction": "Do it"},
        client_intent_id="targeted",
        intent_event_id="event-1",
    )
    create_queued_intent(
        tmp_path,
        kind="note",
        atom_id=None,
        payload={"instruction": "Global"},
        client_intent_id="global",
        intent_event_id="event-2",
    )
    create_queued_intent(
        tmp_path,
        kind="interject",
        atom_id="testing",
        payload={"instruction": "Wrong step"},
        client_intent_id="other",
        intent_event_id="event-3",
    )

    rows = queued_intents_for_step(tmp_path, "implementation")

    assert [row["client_intent_id"] for row in rows] == ["targeted", "global"]


def test_consume_prompt_intents_marks_matching_intent_applied(tmp_path: Path) -> None:
    create_queued_intent(
        tmp_path,
        kind="interject",
        atom_id="implementation",
        payload={"instruction": "Prefer pathlib."},
        client_intent_id="targeted",
        intent_event_id="event-1",
    )

    lines, events = consume_prompt_intents(tmp_path, "implementation")

    assert lines == ["- [interject] Prefer pathlib."]
    assert events[0]["client_intent_id"] == "targeted"
    assert events[0]["applied_to"] == "prompt_context"
    rows = [json.loads(line) for line in intents_path(tmp_path).read_text(encoding="utf-8").splitlines()]
    assert rows[0]["status"] == "applied"
    assert rows[0]["step"] == "implementation"
    assert consume_prompt_intents(tmp_path, "implementation") == ([], [])


def test_append_operator_context_emits_applied_event_when_intent_consumed(tmp_path: Path) -> None:
    events = _Events()
    create_queued_intent(
        tmp_path,
        kind="interject",
        atom_id="implementation",
        payload={"instruction": "Prefer pathlib."},
        client_intent_id="targeted",
        intent_event_id="event-1",
    )

    prompt = append_operator_context(
        tmp_path,
        "implementation",
        "Base prompt",
        events=events,
    )

    assert "## Operator Intent" in prompt
    assert "Prefer pathlib." in prompt
    assert events.events[0][0] == "operator_intent_applied"
    assert events.events[0][1]["client_intent_id"] == "targeted"
    assert events.events[0][1]["applied_to"] == "prompt_context"


def test_append_operator_context_does_not_consume_intent_without_event_bus(tmp_path: Path) -> None:
    create_queued_intent(
        tmp_path,
        kind="interject",
        atom_id="implementation",
        payload={"instruction": "Prefer pathlib."},
        client_intent_id="targeted",
        intent_event_id="event-1",
    )

    prompt = append_operator_context(tmp_path, "implementation", "Base prompt")

    assert "Prefer pathlib." not in prompt
    rows = [json.loads(line) for line in intents_path(tmp_path).read_text(encoding="utf-8").splitlines()]
    assert rows[0]["status"] == "queued"


def test_append_operator_context_injects_reserved_memory_role_wing(tmp_path: Path) -> None:
    memory_dir = tmp_path / ".orchestrator" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "wake-up.md").write_text("wake packet", encoding="utf-8")

    prompt = append_operator_context(tmp_path, "implementation", "Base prompt")

    assert "## Palace Wake-Up" in prompt
    assert "wake packet" in prompt
    assert "## Palace Role Wing" in prompt
    assert f"project wing: {tmp_path.name}" in prompt
    assert f"role wing: {tmp_path.name}.coder" in prompt
    assert "deterministic wake-up injection remains authoritative" in prompt


def test_ignore_queued_intents_for_passed_step_marks_targeted_intent_ignored(tmp_path: Path) -> None:
    create_queued_intent(
        tmp_path,
        kind="interject",
        atom_id="implementation",
        payload={"instruction": "Too late"},
        client_intent_id="targeted",
        intent_event_id="event-1",
    )

    events = ignore_queued_intents_for_passed_step(tmp_path, "implementation")

    assert events[0]["client_intent_id"] == "targeted"
    assert events[0]["reason"] == "target_step_passed"
    rows = [json.loads(line) for line in intents_path(tmp_path).read_text(encoding="utf-8").splitlines()]
    assert rows[0]["status"] == "ignored"
    assert rows[0]["reason"] == "target_step_passed"
    assert ignore_queued_intents_for_passed_step(tmp_path, "implementation") == []


def test_ignore_queued_intents_for_passed_step_marks_unsupported_note_ignored(tmp_path: Path) -> None:
    create_queued_intent(
        tmp_path,
        kind="note",
        atom_id=None,
        payload={"instruction": "Just FYI"},
        client_intent_id="note-1",
        intent_event_id="event-2",
    )

    events = ignore_queued_intents_for_passed_step(tmp_path, "implementation")

    assert events[0]["client_intent_id"] == "note-1"
    assert events[0]["reason"] == "unsupported_kind"
