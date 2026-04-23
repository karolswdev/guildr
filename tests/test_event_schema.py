"""Tests for durable event schema validation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from orchestrator.lib.event_schema import EventValidationError, normalize_event_for_write
from orchestrator.lib.event_types import EVENT_TYPES


def test_normalize_event_rejects_unknown_event_type() -> None:
    with pytest.raises(EventValidationError, match="unknown event type: typo_event"):
        normalize_event_for_write(
            "typo_event",
            {"run_id": "project-1"},
        )


def test_registry_contains_next_step_packet_event() -> None:
    assert "next_step_packet_created" in EVENT_TYPES


def test_registry_contains_functional_mini_sprint_events() -> None:
    assert "mini_sprint_planned" in EVENT_TYPES
    assert "mini_sprint_step_completed" in EVENT_TYPES
    assert "functional_acceptance_evaluated" in EVENT_TYPES


def test_frontend_event_type_mirror_matches_backend_registry() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "web/frontend/src/game/eventTypes.ts").read_text(encoding="utf-8")
    array_source = source.split("] as const;", 1)[0]
    mirrored = set(re.findall(r'"([a-z_]+)"', array_source))

    assert mirrored == set(EVENT_TYPES)
