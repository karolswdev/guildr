"""Sync facade over the async ``UpstreamPool``.

Roles call ``self.llm.chat(messages, ...)`` synchronously; the pool exposes
``async def chat(role, messages, ...)``. ``SyncPoolClient`` bridges the two
so a live run can actually reach a pool endpoint instead of TypeError'ing on
the first coroutine return (H5).

Scope (H5.1): plumbing only. The inner client call already happens via
``asyncio.to_thread`` inside the pool, so the round-trip reaches a
``threading.Thread``-hosted engine without blocking the caller's loop.
Each ``chat()`` starts its own short-lived loop via ``asyncio.run`` — fine
because roles run on a daemon worker thread with no ambient loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from orchestrator.lib.llm import LLMResponse


class SyncPoolClient:
    """Sync ``LLMClient``-shaped adapter for a single role against an ``UpstreamPool``.

    One instance per role per run. ``base_url`` tracks whichever endpoint
    served the most recent call, so ``getattr(llm, "base_url", None)`` in
    ``log_llm_call`` surfaces the real destination.
    """

    def __init__(
        self,
        pool: Any,
        role: str,
        *,
        project_dir: Path | None = None,
    ) -> None:
        self._pool = pool
        self._role = role
        self._project_dir = project_dir
        self.base_url: str | None = None

    def chat(
        self,
        messages: list[dict],
        *,
        call_id: str | None = None,
        **kw: Any,
    ) -> LLMResponse:
        """Dispatch one chat turn through the pool and return synchronously.

        ``call_id`` is threaded so ``pool.jsonl`` shares the join key with
        ``raw-io.jsonl`` and ``usage.jsonl`` (H4's bijection).
        """
        coro = self._pool.chat(
            self._role,
            messages,
            project_dir=self._project_dir,
            call_id=call_id,
            **kw,
        )
        resp = asyncio.run(coro)
        endpoint = getattr(resp, "endpoint", None)
        if endpoint:
            self.base_url = endpoint
        return resp
