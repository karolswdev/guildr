"""SSE stream route for live orchestrator events.

GET /api/projects/{id}/stream — Server-Sent Events stream
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi.responses import StreamingResponse

from orchestrator.lib.event_schema import EventValidationError, normalize_event_for_write

logger = logging.getLogger(__name__)

# -- in-memory event bus per project -----------------------------------------


_REPLAY_LIMIT = 256


class SimpleEventBus:
    """Per-project event bus for SSE streaming.

    Keeps the most recent ``_REPLAY_LIMIT`` events so a subscriber that
    connects after the run already started (or already finished) still
    sees the full sequence. Without replay there's a race where the
    PWA navigates to Progress 200ms after Start Run and shows nothing
    because the dry-run already completed.
    """

    def __init__(self, project_id: str | None = None) -> None:
        self._subscribers: list[list] = []
        self._history: list[str] = []
        self._history_event_ids: set[str] = set()
        self._project_id = project_id

    def emit(self, event_type: str, **fields: Any) -> None:
        """Emit an event to every live subscriber and record it for replay.

        SSE wire format: every payload line must be prefixed with ``data: ``
        followed by ``\\n\\n``. EventSource silently drops anything that
        doesn't match — that's what made the Progress view sit on
        "Connecting..." while the run completed in the background.
        """
        event = normalize_event_for_write(
            event_type,
            fields,
            default_run_id=self._project_id or fields.get("project_id"),
            require_run_id=bool(self._project_id or fields.get("project_id") or fields.get("run_id")),
        )
        event_id = event["event_id"]
        if event_id in self._history_event_ids:
            return

        data = f"data: {json.dumps(event)}\n\n"
        self._history.append(data)
        self._history_event_ids.add(event_id)
        if len(self._history) > _REPLAY_LIMIT:
            removed = self._history[: len(self._history) - _REPLAY_LIMIT]
            del self._history[: len(self._history) - _REPLAY_LIMIT]
            for raw in removed:
                event_id = _event_id_from_sse(raw)
                if event_id:
                    self._history_event_ids.discard(event_id)
        self._persist_event(event)
        for subscriber in self._subscribers:
            try:
                subscriber.append(data)
            except Exception:
                pass

    def subscribe(self) -> list:
        """Create a subscriber pre-seeded with the recent event history."""
        subscriber: list = list(self._history)
        self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: list) -> None:
        """Remove a subscriber."""
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)

    def _persist_event(self, event: dict[str, Any]) -> None:
        if not self._project_id:
            return
        try:
            event = normalize_event_for_write(
                str(event["type"]),
                event,
                default_run_id=self._project_id,
            )
        except EventValidationError:
            logger.debug("Rejected invalid event for %s: %r", self._project_id, event, exc_info=True)
            raise
        path = event_log_path(self._project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event) + "\n")
        except OSError:
            logger.debug("Failed to persist event log for %s", self._project_id, exc_info=True)


class EventStore:
    """Per-project event bus store."""

    def __init__(self) -> None:
        self._buses: dict[str, SimpleEventBus] = {}

    def get_or_create(self, project_id: str) -> SimpleEventBus:
        if project_id not in self._buses:
            self._buses[project_id] = SimpleEventBus(project_id=project_id)
        return self._buses[project_id]

    def has(self, project_id: str) -> bool:
        return project_id in self._buses


# -- singleton store ---------------------------------------------------------

_event_store = EventStore()


def get_event_store() -> EventStore:
    return _event_store


def _projects_base() -> Path:
    return Path(os.environ.get("ORCHESTRATOR_PROJECTS_DIR", "/tmp/orchestrator-projects"))


def event_log_path(project_id: str) -> Path:
    return _projects_base() / project_id / ".orchestrator" / "events.jsonl"


def _event_id_from_sse(raw: str) -> str | None:
    if not raw.startswith("data: "):
        return None
    try:
        event = json.loads(raw[6:])
    except json.JSONDecodeError:
        return None
    event_id = event.get("event_id") if isinstance(event, dict) else None
    return event_id if isinstance(event_id, str) else None


# -- routes ------------------------------------------------------------------


def _setup_routes(router_obj: Any) -> Any:
    """Attach routes to the given router."""
    from fastapi import APIRouter

    router_obj = APIRouter()

    @router_obj.get("/{project_id}/stream")
    async def event_stream(project_id: str) -> StreamingResponse:
        store = get_event_store()
        bus = store.get_or_create(project_id)
        subscriber = bus.subscribe()

        async def event_generator() -> AsyncIterator[str]:
            try:
                last_len = 0
                while True:
                    # Check for new events
                    while last_len < len(subscriber):
                        event_data = subscriber[last_len]
                        last_len += 1
                        yield event_data

                    # Yield keepalive to prevent timeout
                    yield ": keepalive\n\n"
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass
            finally:
                bus.unsubscribe(subscriber)

        import asyncio

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router_obj


router = _setup_routes(None)
