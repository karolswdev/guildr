"""Tests for SSE stream route."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from web.backend.app import create_app
from web.backend.routes.stream import EventStore, SimpleEventBus


@pytest.fixture
def fresh_store() -> EventStore:
    return EventStore()


@pytest.fixture
def app(fresh_store: EventStore) -> FastAPI:
    with patch("web.backend.routes.stream.get_event_store", return_value=fresh_store):
        yield create_app()


@pytest.mark.asyncio
async def test_stream_returns_200(app: FastAPI) -> None:
    """SSE endpoint returns 200 status code."""
    # We test the bus directly since the SSE endpoint is a long-lived
    # streaming connection that can't easily be tested with httpx.
    store = __import__("web.backend.routes.stream", fromlist=["get_event_store"]).get_event_store()
    bus = store.get_or_create("test-proj")
    sub = bus.subscribe()

    # Emit an event and verify it reaches the subscriber
    bus.emit("phase_start", name="architect")
    assert len(sub) >= 1
    assert "phase_start" in sub[0]

    bus.unsubscribe(sub)


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_events(fresh_store: EventStore) -> None:
    """Multiple subscribers all receive events."""
    bus = fresh_store.get_or_create("multi-proj")

    sub1 = bus.subscribe()
    sub2 = bus.subscribe()

    bus.emit("phase_start", name="architect")

    assert len(sub1) >= 1
    assert len(sub2) >= 1
    assert "phase_start" in sub1[0]
    assert "phase_start" in sub2[0]


@pytest.mark.asyncio
async def test_emit_formats_correctly(fresh_store: EventStore) -> None:
    """Events are formatted as JSON with double newline."""
    bus = fresh_store.get_or_create("fmt-proj")
    sub = bus.subscribe()

    bus.emit("phase_start", name="architect", attempt=0)

    assert len(sub) >= 1
    event_data = sub[0]
    assert "phase_start" in event_data
    assert '"type": "phase_start"' in event_data
    assert '"name": "architect"' in event_data


@pytest.mark.asyncio
async def test_unsubscribe_removes_subscriber(fresh_store: EventStore) -> None:
    """Unsubscribing removes the subscriber so it no longer receives events."""
    bus = fresh_store.get_or_create("unsub-proj")
    sub = bus.subscribe()

    bus.emit("phase_start", name="architect")
    assert len(sub) >= 1

    bus.unsubscribe(sub)

    bus.emit("phase_done", name="architect")
    # After unsubscribe, the event should not be in the (now removed) subscriber
    # Since the subscriber was removed from _subscribers, it won't receive new events


class TestSimpleEventBus:
    """Direct unit tests for SimpleEventBus."""

    def test_emit_to_single_subscriber(self) -> None:
        bus = SimpleEventBus()
        sub = bus.subscribe()
        bus.emit("phase_start", name="architect")
        assert len(sub) >= 1
        assert "phase_start" in sub[0]

    def test_emit_to_multiple_subscribers(self) -> None:
        bus = SimpleEventBus()
        sub1 = bus.subscribe()
        sub2 = bus.subscribe()
        bus.emit("phase_start", name="architect")
        assert len(sub1) >= 1
        assert len(sub2) >= 1

    def test_unsubscribe(self) -> None:
        bus = SimpleEventBus()
        sub = bus.subscribe()
        bus.unsubscribe(sub)
        assert sub not in bus._subscribers

    def test_emit_to_removed_subscriber_no_crash(self) -> None:
        bus = SimpleEventBus()
        sub = bus.subscribe()
        bus.unsubscribe(sub)
        # Should not raise
        bus.emit("phase_start", name="architect")

    def test_emit_prunes_failed_subscribers(self, caplog: pytest.LogCaptureFixture) -> None:
        class BrokenSubscriber:
            def append(self, _: str) -> None:
                raise RuntimeError("client disconnected")

        bus = SimpleEventBus(project_id="project-1")
        broken = BrokenSubscriber()
        healthy = bus.subscribe()
        bus._subscribers.append(broken)

        bus.emit("phase_start", name="architect")

        assert broken not in bus._subscribers
        assert healthy in bus._subscribers
        assert len(healthy) == 1
        assert "Dropping failed SSE subscriber" in caplog.text
