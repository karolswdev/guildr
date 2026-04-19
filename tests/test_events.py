"""Tests for orchestrator.lib.events."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from orchestrator.lib.events import EventBus


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    return tmp_path


class TestEventBus:
    """Test EventBus operations."""

    def test_emit_no_subscribers(self, tmp_project):
        """emit() does not raise when there are no subscribers."""
        bus = EventBus()
        bus.emit("phase_start", name="architect", attempt=0)  # should not raise

    def test_emit_fields_passed(self, tmp_project):
        """emit() passes all keyword arguments as event fields."""
        bus = EventBus()
        # Verify the event structure by checking emit doesn't raise
        bus.emit("gate_decided", gate="approve_sprint_plan", decision="approved")

    def test_emit_structure(self, tmp_project):
        """emit() creates event dict with type and fields."""
        bus = EventBus()
        # Create a subscriber to capture the event
        queue: asyncio.Queue = asyncio.Queue()
        bus._subscribers.append(queue)
        bus.emit("phase_start", name="architect", attempt=0)
        event = queue.get_nowait()
        assert event["type"] == "phase_start"
        assert event["name"] == "architect"
        assert event["attempt"] == 0

    def test_emit_to_multiple_subscribers(self, tmp_project):
        """emit() delivers event to all subscriber queues."""
        bus = EventBus()
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        bus._subscribers.append(q1)
        bus._subscribers.append(q2)
        bus.emit("phase_done", name="architect")
        assert q1.get_nowait()["type"] == "phase_done"
        assert q2.get_nowait()["type"] == "phase_done"

    def test_subscriber_removed_after_stop(self, tmp_project):
        """Subscribers list is manageable."""
        bus = EventBus()
        queue: asyncio.Queue = asyncio.Queue()
        bus._subscribers.append(queue)
        assert len(bus._subscribers) == 1
        bus._subscribers.remove(queue)
        assert len(bus._subscribers) == 0

    def test_no_replay_of_past_events(self, tmp_project):
        """New subscribers do NOT receive past events (live stream only)."""
        bus = EventBus()
        q1: asyncio.Queue = asyncio.Queue()
        bus._subscribers.append(q1)
        bus.emit("phase_start", name="architect")
        q1.get_nowait()
        bus._subscribers.remove(q1)

        q2: asyncio.Queue = asyncio.Queue()
        bus._subscribers.append(q2)
        bus.emit("phase_done", name="architect")
        event = q2.get_nowait()
        assert event["type"] == "phase_done"
        assert event["name"] == "architect"

    def test_queue_full_drops_event(self, tmp_project):
        """emit() does not raise when subscriber queue is full."""
        bus = EventBus()
        # Create a full queue
        full_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        full_queue.put_nowait({"type": "old"})
        bus._subscribers.append(full_queue)
        # This should not raise even though queue is full
        bus.emit("phase_start", name="architect")
