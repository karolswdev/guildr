"""H3.3 — pool routing observability guardrail.

Proves the "two endpoints, two concurrent roles, two distinct labels"
promise the product makes. Two `pool.chat` calls run concurrently through
`asyncio.gather`; each should land on its own endpoint, write its own
decision to ``pool.jsonl``, and the log must reconcile with the shared
``call_id``.

Also covers the fallback-on-ConnectionError path — the scenario H2.2 will
eventually need to survive against a real down PRIMARY.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from orchestrator.lib.llm import LLMResponse
from orchestrator.lib.pool import Endpoint, UpstreamPool
from orchestrator.lib.pool_log import pool_log_path


@dataclass
class _FakeClient:
    label: str
    raise_connection: bool = False
    delay_s: float = 0.0
    call_count: int = 0

    def chat(self, messages: list[dict[str, Any]], **kw: Any) -> LLMResponse:
        if self.raise_connection:
            raise ConnectionError(f"{self.label} is down")
        if self.delay_s:
            time.sleep(self.delay_s)
        self.call_count += 1
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
        return True


def _read_decisions(project_dir: Path) -> list[dict]:
    path = pool_log_path(project_dir)
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.asyncio
async def test_two_concurrent_calls_land_on_distinct_endpoints(tmp_path: Path) -> None:
    primary = _FakeClient(label="primary", delay_s=0.05)
    alien = _FakeClient(label="alien", delay_s=0.05)
    pool = UpstreamPool(
        endpoints=[
            Endpoint(label="primary", client=primary),
            Endpoint(label="alien", client=alien),
        ],
        routing={"coder": ["primary"], "reviewer": ["alien"]},
    )

    resp_coder, resp_reviewer = await asyncio.gather(
        pool.chat("coder", [], project_dir=tmp_path, call_id="call-coder"),
        pool.chat("reviewer", [], project_dir=tmp_path, call_id="call-reviewer"),
    )

    assert resp_coder.endpoint == "primary"  # type: ignore[attr-defined]
    assert resp_reviewer.endpoint == "alien"  # type: ignore[attr-defined]
    assert primary.call_count == 1
    assert alien.call_count == 1

    decisions = _read_decisions(tmp_path)
    by_call = {d["call_id"]: d for d in decisions}
    assert by_call["call-coder"]["chosen_endpoint"] == "primary"
    assert by_call["call-coder"]["fell_back"] is False
    assert by_call["call-reviewer"]["chosen_endpoint"] == "alien"
    assert by_call["call-reviewer"]["fell_back"] is False


@pytest.mark.asyncio
async def test_fallback_writes_fell_back_true(tmp_path: Path) -> None:
    primary = _FakeClient(label="primary", raise_connection=True)
    alien = _FakeClient(label="alien")
    pool = UpstreamPool(
        endpoints=[
            Endpoint(label="primary", client=primary),
            Endpoint(label="alien", client=alien),
        ],
        routing={"coder": ["primary", "alien"]},
    )

    resp = await pool.chat("coder", [], project_dir=tmp_path, call_id="call-fb")

    assert resp.endpoint == "alien"  # type: ignore[attr-defined]
    decision = _read_decisions(tmp_path)[0]
    assert decision["call_id"] == "call-fb"
    assert decision["chosen_endpoint"] == "alien"
    assert decision["attempted_endpoints"] == ["primary", "alien"]
    assert decision["fell_back"] is True
