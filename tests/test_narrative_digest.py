"""Tests for deterministic narrative digest generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.lib.narrative import (
    NarrativeValidationError,
    build_narrative_digest,
    emit_narrative_digest,
    validate_narrative_digest,
)
from orchestrator.lib.events import EventBus


def test_build_narrative_digest_is_sourced_scrubbed_and_deterministic(tmp_path: Path) -> None:
    events = [
        {
            "event_id": "evt-1",
            "type": "phase_done",
            "name": "implementation",
            "artifact_refs": ["TEST_REPORT.md"],
            "error": "api_key=sk-live-secret-value",
        },
    ]
    packet = {
        "step": "testing",
        "title": "Testing",
        "source_refs": ["artifact:sprint-plan.md"],
    }

    first = build_narrative_digest(tmp_path, events, next_step_packet=packet)
    second = build_narrative_digest(tmp_path, events, next_step_packet=packet)

    assert first["digest_id"] == second["digest_id"]
    assert first["source_event_ids"] == ["evt-1"]
    assert first["highlights"][0]["source_refs"] == ["event:evt-1"]
    assert first["artifact_refs"] == ["TEST_REPORT.md", "sprint-plan.md"]
    assert "Testing (testing)" in first["summary"]
    assert "sk-live-secret-value" not in json.dumps(first)


def test_emit_narrative_digest_writes_artifacts_and_event(tmp_path: Path) -> None:
    bus = EventBus()
    source = bus.emit("phase_done", name="memory_refresh", run_id="run-1")

    emitted = emit_narrative_digest(
        bus,
        tmp_path,
        [source],
        next_step_packet={"step": "persona_forum", "title": "Team"},
    )

    assert emitted is not None
    assert emitted["type"] == "narrative_digest_created"
    assert emitted["digest"]["source_event_ids"] == [source["event_id"]]
    assert all(ref.startswith(".orchestrator/narrative/digests/") for ref in emitted["artifact_refs"])
    for ref in emitted["artifact_refs"]:
        assert (tmp_path / ref).exists()


def test_validate_narrative_digest_rejects_unsourced_and_unsafe_refs() -> None:
    source = {"event_id": "evt-1", "type": "phase_done", "name": "implementation"}
    digest = build_narrative_digest(Path("."), [source])
    digest["highlights"][0]["source_refs"] = []
    with pytest.raises(NarrativeValidationError, match="missing source_refs"):
        validate_narrative_digest(digest, [source])

    digest = build_narrative_digest(Path("."), [source])
    digest["artifact_refs"] = ["../secret.txt"]
    with pytest.raises(NarrativeValidationError, match="unsafe artifact"):
        validate_narrative_digest(digest, [source])

    digest = build_narrative_digest(Path("."), [source])
    digest["source_event_ids"] = ["evt-missing"]
    with pytest.raises(NarrativeValidationError, match="unknown source events"):
        validate_narrative_digest(digest, [source])
