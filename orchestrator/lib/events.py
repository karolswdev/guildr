"""Event bus for PWA SSE streaming.

Full implementation in Task 6.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator


class EventBus:
    """Async event bus for PWA progress streaming."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def emit(self, type: str, **fields: Any) -> None:
        """Emit an event to all subscribers."""
        event = {"type": type, **fields}
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Back-pressure: drop for slow subscribers

    async def subscribe(self) -> AsyncIterator[dict]:
        """Subscribe to events. Does NOT replay past events (live stream only)."""
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.remove(queue)
