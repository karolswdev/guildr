"""Upstream pool — serializes around -np 1 llama.cpp servers.

Full implementation in Task 2.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from orchestrator.lib.llm import LLMClient, LLMResponse

logger = logging.getLogger(__name__)


@dataclass
class Endpoint:
    """A llama.cpp server endpoint."""

    label: str  # operator-chosen name, e.g. "local-gpu" or "openrouter"
    client: LLMClient
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    healthy: bool = True


class NoHealthyEndpoint(Exception):
    """Raised when no healthy endpoint is available for a role."""

    def __init__(self, role: str) -> None:
        self.role = role
        super().__init__(f"No healthy endpoint for role '{role}'")


class LLMResponseExtended(LLMResponse):
    """LLMResponse with endpoint label added."""

    endpoint: str = ""


class UpstreamPool:
    """Manages a pool of OpenAI-compatible chat endpoints with role-based routing.

    Within one endpoint, calls serialize via its lock (honors single-slot
    servers like llama.cpp ``-np 1``). Across endpoints, calls run
    concurrently. Routing entries may be bare endpoint labels (use the
    endpoint's default model) or ``RouteEntry`` records that carry a
    per-role model override — so the same endpoint can serve different
    roles with different models.
    """

    def __init__(
        self,
        endpoints: list[Endpoint],
        routing: dict[str, list[Any]],
    ) -> None:
        from orchestrator.lib.endpoints import RouteEntry

        self._by_label: dict[str, Endpoint] = {e.label: e for e in endpoints}
        self._routing: dict[str, list[RouteEntry]] = {}
        for role, entries in routing.items():
            normalized: list[RouteEntry] = []
            for entry in entries:
                if isinstance(entry, RouteEntry):
                    normalized.append(entry)
                elif isinstance(entry, str):
                    normalized.append(RouteEntry(endpoint=entry))
                else:
                    raise TypeError(
                        f"routing[{role!r}] entries must be str or RouteEntry, "
                        f"got {type(entry).__name__}"
                    )
            self._routing[role] = normalized
        self._orchestrator: Any | None = None

    def set_orchestrator(self, orchestrator: Any) -> None:
        """Set the orchestrator reference (for health watcher)."""
        self._orchestrator = orchestrator

    @property
    def orchestrator(self) -> Any | None:
        return self._orchestrator

    async def chat(
        self,
        role: str,
        messages: list[dict],
        *,
        project_dir: Any | None = None,
        call_id: str | None = None,
        **kw: Any,
    ) -> LLMResponse:
        """Send a chat completion through the pool.

        Routes through [preferred, fallback] endpoints.
        Serializes within each endpoint via lock.

        When ``project_dir`` + ``call_id`` are both provided, one routing
        decision is appended to ``<project_dir>/.orchestrator/logs/pool.jsonl``
        so downstream tools can answer "where did each call land."
        """
        from orchestrator.lib.event_schema import new_event_id
        from orchestrator.lib.pool_log import write_decision

        resolved_call_id = call_id or new_event_id()
        routes = self._routing.get(role, [])
        attempted: list[str] = []

        if not routes:
            write_decision(
                project_dir,
                call_id=resolved_call_id,
                role=role,
                chosen_endpoint=None,
                attempted_endpoints=attempted,
                fell_back=False,
                reason="no_routing_configured",
            )
            raise NoHealthyEndpoint(role)

        # Caller may already pass ``model`` — route override wins over
        # caller intent only when caller didn't specify (routes encode the
        # operator's declared policy).
        caller_model = kw.pop("model", None)
        for route in routes:
            label = route.endpoint
            ep = self._by_label.get(label)
            if not ep or not ep.healthy:
                attempted.append(label)
                continue
            attempted.append(label)
            model_for_call = (
                route.model
                or caller_model
                or getattr(ep.client, "default_model", None)
            )
            call_kw = dict(kw)
            if model_for_call is not None:
                call_kw["model"] = model_for_call
            async with ep.lock:
                try:
                    resp = await asyncio.to_thread(ep.client.chat, messages, **call_kw)
                    resp.endpoint = label  # type: ignore[attr-defined]
                    write_decision(
                        project_dir,
                        call_id=resolved_call_id,
                        role=role,
                        chosen_endpoint=label,
                        chosen_model=model_for_call,
                        attempted_endpoints=attempted,
                        fell_back=len(attempted) > 1,
                    )
                    return resp
                except ConnectionError:
                    ep.healthy = False
                    logger.warning("Endpoint %s marked unhealthy", label)
                    continue

        write_decision(
            project_dir,
            call_id=resolved_call_id,
            role=role,
            chosen_endpoint=None,
            attempted_endpoints=attempted,
            fell_back=True,
            reason="no_healthy_endpoint",
        )
        raise NoHealthyEndpoint(role)

    async def health_check(self, label: str) -> bool:
        """Check health of a specific endpoint."""
        ep = self._by_label.get(label)
        if not ep:
            return False
        try:
            healthy = ep.client.health()
            ep.healthy = healthy
            return healthy
        except Exception:
            ep.healthy = False
            return False

    async def health_watcher(self) -> None:
        """Periodically poll all endpoints for health."""
        import time

        while True:
            for label in self._by_label:
                await self.health_check(label)
            await asyncio.sleep(10)
