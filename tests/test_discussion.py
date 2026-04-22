"""Tests for durable discussion log projections."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.lib.discussion import (
    DiscussionValidationError,
    append_discussion_entry,
    append_discussion_highlight,
    append_persona_discussion_entries,
    discussion_highlights_path,
    discussion_log_path,
    rebuild_projection,
    validate_discussion_entry,
)
from orchestrator.lib.events import EventBus


def test_append_discussion_entry_scrubs_persists_and_emits(tmp_path: Path) -> None:
    bus = EventBus()

    row = append_discussion_entry(
        tmp_path,
        speaker="operator",
        entry_type="operator_note",
        atom_id="testing",
        text="Use token=sk-live-secret-value while testing.",
        source_refs=["event:evt-1"],
        artifact_refs=[".orchestrator/control/intents.jsonl"],
        event_bus=bus,
        project_id="project-1",
    )

    assert row["text"] == "Use token=[redacted] while testing."
    assert row["source_refs"] == ["event:evt-1"]
    log_text = discussion_log_path(tmp_path).read_text(encoding="utf-8")
    assert "sk-live-secret-value" not in log_text
    assert json.loads(log_text)["discussion_entry_id"] == row["discussion_entry_id"]


def test_persona_discussion_entries_and_highlight_are_sourced(tmp_path: Path) -> None:
    personas = [
        {
            "name": "Founder",
            "perspective": "business owner",
            "mandate": "Keep scope sharp.",
            "turn_order": 1,
            "veto_scope": "scope drift",
        }
    ]

    rows = append_persona_discussion_entries(tmp_path, personas)

    assert rows[0]["speaker"] == "Founder"
    assert rows[0]["entry_type"] == "persona_statement"
    assert rows[0]["source_refs"] == ["artifact:FOUNDING_TEAM.json", "artifact:PERSONA_FORUM.md"]
    highlight = json.loads(discussion_highlights_path(tmp_path).read_text(encoding="utf-8"))
    assert highlight["source_refs"] == [f"entry:{rows[0]['discussion_entry_id']}"]


def test_rebuild_projection_from_discussion_events(tmp_path: Path) -> None:
    entry = append_discussion_entry(
        tmp_path,
        speaker="operator",
        entry_type="operator_instruction",
        text="Keep context lean.",
        source_refs=["artifact:.orchestrator/control/instructions.jsonl"],
        artifact_refs=[".orchestrator/control/instructions.jsonl"],
    )
    highlight = append_discussion_highlight(
        tmp_path,
        text="Instruction captured.",
        source_refs=[f"entry:{entry['discussion_entry_id']}"],
    )
    events = [
        {"type": "discussion_entry_created", "entry": entry},
        {"type": "discussion_highlight_created", "highlight": highlight},
    ]

    paths = rebuild_projection(tmp_path, events)

    assert paths["log"].read_text(encoding="utf-8") == discussion_log_path(tmp_path).read_text(encoding="utf-8")
    assert (
        paths["highlights"].read_text(encoding="utf-8")
        == discussion_highlights_path(tmp_path).read_text(encoding="utf-8")
    )


class _RecordingBus:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, type: str, **fields):  # type: ignore[no-untyped-def]
        event = {"type": type, **fields}
        self.events.append(event)
        return event


def test_discussion_entry_stamps_memory_provenance(tmp_path: Path) -> None:
    import hashlib

    memory_dir = tmp_path / ".orchestrator" / "memory"
    memory_dir.mkdir(parents=True)
    wakeup_body = "# wake-up\nfounding team roster\n"
    (memory_dir / "wake-up.md").write_text(wakeup_body, encoding="utf-8")
    expected_hash = hashlib.sha256(wakeup_body.encode("utf-8")).hexdigest()

    bus = _RecordingBus()
    row = append_discussion_entry(
        tmp_path,
        speaker="Founder",
        entry_type="persona_statement",
        text="Keep scope sharp.",
        source_refs=["artifact:FOUNDING_TEAM.json"],
        event_bus=bus,
    )

    assert row["wake_up_hash"] == expected_hash
    assert row["memory_refs"] == [".orchestrator/memory/wake-up.md"]
    event = bus.events[-1]
    assert event["type"] == "discussion_entry_created"
    assert event["wake_up_hash"] == expected_hash
    assert event["memory_refs"] == [".orchestrator/memory/wake-up.md"]
    assert event["entry"]["wake_up_hash"] == expected_hash
    assert event["entry"]["memory_refs"] == [".orchestrator/memory/wake-up.md"]


def test_discussion_highlight_stamps_memory_provenance(tmp_path: Path) -> None:
    import hashlib

    memory_dir = tmp_path / ".orchestrator" / "memory"
    memory_dir.mkdir(parents=True)
    wakeup_body = "# wake-up\nproject context\n"
    (memory_dir / "wake-up.md").write_text(wakeup_body, encoding="utf-8")
    expected_hash = hashlib.sha256(wakeup_body.encode("utf-8")).hexdigest()

    bus = _RecordingBus()
    row = append_discussion_highlight(
        tmp_path,
        text="Founding team convened.",
        source_refs=["artifact:PERSONA_FORUM.md"],
        event_bus=bus,
    )

    assert row["wake_up_hash"] == expected_hash
    assert row["memory_refs"] == [".orchestrator/memory/wake-up.md"]
    event = bus.events[-1]
    assert event["wake_up_hash"] == expected_hash
    assert event["memory_refs"] == [".orchestrator/memory/wake-up.md"]
    assert event["highlight"]["wake_up_hash"] == expected_hash


def test_validate_discussion_entry_rejects_unsourced_and_unsafe_refs() -> None:
    row = {
        "discussion_entry_id": "disc_1",
        "speaker": "operator",
        "entry_type": "operator_note",
        "text": "Check this.",
        "source_refs": [],
        "artifact_refs": [],
    }
    with pytest.raises(DiscussionValidationError, match="source_refs"):
        validate_discussion_entry(row)

    row["source_refs"] = ["artifact:../secret.txt"]
    with pytest.raises(DiscussionValidationError, match="unsafe artifact"):
        validate_discussion_entry(row)
