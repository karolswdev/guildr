"""Coverage for ``orchestrator.lib.sync_pool.SyncPoolClient`` (H5.1).

The facade exists so roles — which call ``self.llm.chat(...)`` synchronously —
can reach the async ``UpstreamPool`` in a live run. Before H5.1 the engine
handed ``pool.chat`` (a coroutine-returning bound method) straight to the
role; the first real call would ``TypeError``. These tests pin the three
properties a live run depends on:

1. a sync ``.chat(...)`` call returns a materialized ``LLMResponse``
2. the ``call_id`` threaded in matches what lands in ``pool.jsonl``
   (the H4 join key)
3. after a successful call, ``base_url`` reflects the chosen endpoint so
   ``log_llm_call`` records the real destination
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.lib.llm import LLMResponse
from orchestrator.lib.pool import Endpoint, UpstreamPool
from orchestrator.lib.sync_pool import SyncPoolClient


@dataclass
class _FakeClient:
    label: str
    call_count: int = 0
    last_kwargs: dict[str, Any] | None = None

    def chat(self, messages: list[dict[str, Any]], **kw: Any) -> LLMResponse:
        self.call_count += 1
        self.last_kwargs = kw
        return LLMResponse(
            content=f"served by {self.label}",
            reasoning="",
            model="fake",
            prompt_tokens=1,
            completion_tokens=1,
            reasoning_tokens=0,
            finish_reason="stop",
        )

    def health(self) -> bool:
        return True


def _pool(client: _FakeClient) -> UpstreamPool:
    return UpstreamPool(
        endpoints=[Endpoint(label=client.label, client=client)],
        routing={"coder": [client.label]},
    )


def test_sync_chat_returns_materialized_response() -> None:
    client = _FakeClient(label="primary")
    facade = SyncPoolClient(_pool(client), role="coder")

    resp = facade.chat([{"role": "user", "content": "hi"}])

    assert isinstance(resp, LLMResponse)
    assert resp.content == "served by primary"
    assert client.call_count == 1


def test_sync_chat_forwards_max_tokens_to_inner_client() -> None:
    client = _FakeClient(label="primary")
    facade = SyncPoolClient(_pool(client), role="coder")

    facade.chat([{"role": "user", "content": "hi"}], max_tokens=4096)

    assert client.last_kwargs == {"max_tokens": 4096}


def test_sync_chat_updates_base_url_to_chosen_endpoint() -> None:
    client = _FakeClient(label="primary")
    facade = SyncPoolClient(_pool(client), role="coder")
    assert facade.base_url is None

    facade.chat([{"role": "user", "content": "hi"}])

    assert facade.base_url == "primary"


def test_sync_chat_threads_call_id_into_pool_log(tmp_path: Path) -> None:
    client = _FakeClient(label="primary")
    facade = SyncPoolClient(_pool(client), role="coder", project_dir=tmp_path)
    call_id = "01JXXXXXXXXXXXXXXXXXXXXXXX"  # 26-char-ish placeholder

    facade.chat([{"role": "user", "content": "hi"}], call_id=call_id)

    log_path = tmp_path / ".orchestrator" / "logs" / "pool.jsonl"
    assert log_path.is_file(), "pool.jsonl must exist when project_dir is set"
    records = [json.loads(line) for line in log_path.read_text().splitlines() if line]
    assert len(records) == 1
    assert records[0]["call_id"] == call_id
    assert records[0]["chosen_endpoint"] == "primary"
    assert records[0]["role"] == "coder"


def test_sync_chat_is_safe_on_thread_with_no_running_loop() -> None:
    """Regression: roles run on a daemon thread with no ambient loop.

    ``asyncio.run`` builds and tears down a fresh loop each call — which is
    fine here, but *would* raise ``RuntimeError`` if called with a loop
    already running on the current thread. This test asserts the happy path
    on a bare thread; the running-loop failure mode is a separate concern
    (not applicable today because roles are synchronous).
    """
    client = _FakeClient(label="primary")
    facade = SyncPoolClient(_pool(client), role="coder")

    # Two consecutive calls prove the loop is rebuilt cleanly.
    facade.chat([{"role": "user", "content": "first"}])
    start = time.monotonic()
    facade.chat([{"role": "user", "content": "second"}])
    elapsed = time.monotonic() - start

    assert client.call_count == 2
    assert elapsed < 1.0  # no leak / no hang
