"""Async coverage for `orchestrator.lib.pool.UpstreamPool`.

Replaces the previous stub tests that never awaited `pool.chat`. Covers:

- happy-path routing (chosen endpoint label appears on the response)
- lock serialization within a single endpoint under concurrent load
- fallback to the next label on ``ConnectionError`` + healthy flag flip
- ``NoHealthyEndpoint`` when every candidate is unhealthy
- ``health_check`` reflects the underlying client's health result
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import pytest

from orchestrator.lib.llm import LLMResponse
from orchestrator.lib.pool import Endpoint, NoHealthyEndpoint, UpstreamPool


@dataclass
class _FakeClient:
    """Minimal LLMClient-ish stub with deterministic timing hooks."""

    label: str
    health_value: bool = True
    raise_connection: bool = False
    delay_s: float = 0.0
    call_count: int = 0
    last_start: float = 0.0
    last_end: float = 0.0
    default_model: str = "fake-default"
    last_model: str | None = None

    def chat(self, messages: list[dict[str, Any]], **kw: Any) -> LLMResponse:
        self.last_start = time.monotonic()
        if self.raise_connection:
            raise ConnectionError(f"{self.label} is down")
        if self.delay_s:
            time.sleep(self.delay_s)
        self.call_count += 1
        self.last_model = kw.get("model")
        self.last_end = time.monotonic()
        return LLMResponse(
            content=f"served by {self.label}",
            reasoning="",
            model="fake",
            prompt_tokens=0,
            completion_tokens=0,
            reasoning_tokens=0,
            finish_reason="stop",
        )

    def health(self) -> bool:
        return self.health_value


def _pool(*clients: _FakeClient, routing: dict[str, list[str]] | None = None) -> UpstreamPool:
    endpoints = [Endpoint(label=c.label, client=c) for c in clients]
    default = {"coder": [c.label for c in clients]}
    return UpstreamPool(endpoints=endpoints, routing=routing or default)


@pytest.mark.asyncio
async def test_chat_routes_to_preferred_endpoint() -> None:
    primary = _FakeClient(label="primary")
    alien = _FakeClient(label="alien")
    pool = _pool(primary, alien, routing={"coder": ["primary", "alien"]})

    resp = await pool.chat("coder", [{"role": "user", "content": "hi"}])

    assert resp.endpoint == "primary"  # type: ignore[attr-defined]
    assert primary.call_count == 1
    assert alien.call_count == 0


@pytest.mark.asyncio
async def test_chat_falls_back_on_connection_error() -> None:
    primary = _FakeClient(label="primary", raise_connection=True)
    alien = _FakeClient(label="alien")
    pool = _pool(primary, alien, routing={"coder": ["primary", "alien"]})

    resp = await pool.chat("coder", [])

    assert resp.endpoint == "alien"  # type: ignore[attr-defined]
    assert primary.call_count == 0  # raised before counting
    assert alien.call_count == 1
    ep_primary = pool._by_label["primary"]
    assert ep_primary.healthy is False  # failure flips the flag


@pytest.mark.asyncio
async def test_chat_raises_when_every_candidate_is_unhealthy() -> None:
    primary = _FakeClient(label="primary")
    alien = _FakeClient(label="alien")
    pool = _pool(primary, alien, routing={"coder": ["primary", "alien"]})
    pool._by_label["primary"].healthy = False
    pool._by_label["alien"].healthy = False

    with pytest.raises(NoHealthyEndpoint):
        await pool.chat("coder", [])


@pytest.mark.asyncio
async def test_chat_raises_for_unknown_role() -> None:
    pool = _pool(_FakeClient(label="primary"), routing={"coder": ["primary"]})

    with pytest.raises(NoHealthyEndpoint):
        await pool.chat("reviewer", [])


@pytest.mark.asyncio
async def test_lock_serializes_calls_within_one_endpoint() -> None:
    """Two concurrent calls to the same endpoint must not overlap."""
    primary = _FakeClient(label="primary", delay_s=0.1)
    pool = _pool(primary, routing={"coder": ["primary"]})

    async def call_it() -> tuple[float, float]:
        await pool.chat("coder", [])
        return primary.last_start, primary.last_end

    # Race two calls at once; the lock should force them to run serially.
    results = await asyncio.gather(call_it(), call_it())
    assert primary.call_count == 2

    # The earlier call's end must precede the later call's start. The
    # client mutates last_start/last_end in place, so we can only
    # compare the totals: min start → max end should cover ≥ 2 * delay.
    total_wall = max(r[1] for r in results) - min(r[0] for r in results)
    assert total_wall >= 0.18, f"calls overlapped (wall={total_wall:.3f}s)"


@pytest.mark.asyncio
async def test_concurrent_calls_across_endpoints_run_in_parallel() -> None:
    """Different endpoints must serve concurrently, not serialize."""
    primary = _FakeClient(label="primary", delay_s=0.1)
    alien = _FakeClient(label="alien", delay_s=0.1)
    pool = UpstreamPool(
        endpoints=[
            Endpoint(label="primary", client=primary),
            Endpoint(label="alien", client=alien),
        ],
        routing={"coder": ["primary"], "reviewer": ["alien"]},
    )

    start = time.monotonic()
    await asyncio.gather(pool.chat("coder", []), pool.chat("reviewer", []))
    elapsed = time.monotonic() - start

    # If the two endpoints serialized we'd see ~0.2s. Parallel should be
    # well under 0.18s with some scheduler slack.
    assert elapsed < 0.18, f"endpoints serialized (elapsed={elapsed:.3f}s)"
    assert primary.call_count == 1
    assert alien.call_count == 1


@pytest.mark.asyncio
async def test_route_model_override_wins_over_endpoint_default() -> None:
    from orchestrator.lib.endpoints import RouteEntry

    primary = _FakeClient(label="primary", default_model="default-m")
    pool = _pool(primary, routing={"coder": [RouteEntry(endpoint="primary", model="override-m")]})

    await pool.chat("coder", [])

    assert primary.last_model == "override-m"


@pytest.mark.asyncio
async def test_caller_model_used_when_no_route_override() -> None:
    primary = _FakeClient(label="primary", default_model="default-m")
    pool = _pool(primary, routing={"coder": ["primary"]})

    await pool.chat("coder", [], model="caller-m")

    assert primary.last_model == "caller-m"


@pytest.mark.asyncio
async def test_endpoint_default_model_used_when_nothing_specified() -> None:
    primary = _FakeClient(label="primary", default_model="default-m")
    pool = _pool(primary, routing={"coder": ["primary"]})

    await pool.chat("coder", [])

    assert primary.last_model == "default-m"


@pytest.mark.asyncio
async def test_health_check_flips_flag() -> None:
    primary = _FakeClient(label="primary", health_value=False)
    pool = _pool(primary, routing={"coder": ["primary"]})

    healthy = await pool.health_check("primary")

    assert healthy is False
    assert pool._by_label["primary"].healthy is False


@pytest.mark.asyncio
async def test_health_check_recovers_endpoint() -> None:
    primary = _FakeClient(label="primary", health_value=True)
    pool = _pool(primary, routing={"coder": ["primary"]})
    pool._by_label["primary"].healthy = False  # simulate prior failure

    healthy = await pool.health_check("primary")

    assert healthy is True
    assert pool._by_label["primary"].healthy is True
