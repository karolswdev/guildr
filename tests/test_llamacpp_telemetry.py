"""llama.cpp telemetry normalization tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from orchestrator.lib.llm import LLMClient, LLMResponse
from orchestrator.lib.local_cost import (
    estimate_local_cost,
    load_local_cost_profile,
)
from orchestrator.lib.state import State
from orchestrator.lib.usage import emit_llm_usage


class CaptureBus:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, **fields) -> None:
        self.events.append({"type": event_type, **fields})


@pytest.fixture
def state(tmp_path: Path) -> State:
    s = State(tmp_path)
    s.events = CaptureBus()
    return s


def _llamacpp_response() -> LLMResponse:
    return LLMResponse(
        content="hello",
        reasoning="",
        prompt_tokens=0,
        completion_tokens=0,
        reasoning_tokens=0,
        finish_reason="stop",
        model="qwen36",
        usage_metadata={},
        timings={
            "prompt_n": 1,
            "cache_n": 236,
            "predicted_n": 35,
            "prompt_ms": 30.958,
            "predicted_ms": 661.064,
            "prompt_per_second": 32.30,
            "predicted_per_second": 52.94,
        },
    )


class _LlamaLLM:
    base_url = "http://127.0.0.1:8080"

    def chat(self, messages, **kw):  # pragma: no cover - not used here
        raise NotImplementedError


def test_timings_map_to_input_cache_output_and_throughput(state: State) -> None:
    emit_llm_usage(
        state,
        _LlamaLLM(),
        _llamacpp_response(),
        role="architect",
        step="plan",
        runtime_ms=692.0,
    )
    events = state.events.events  # type: ignore[union-attr]
    assert len(events) == 1
    event = events[0]
    assert event["provider_kind"] == "llamacpp"
    assert event["source"] == "local_estimate"
    assert event["confidence"] == "medium"
    assert event["extraction_path"] == "llamacpp_timings"
    assert event["usage"]["input_tokens"] == 1
    assert event["usage"]["output_tokens"] == 35
    assert event["usage"]["cache_read_tokens"] == 236
    llama = event["runtime"]["llamacpp"]
    assert llama["cache_tokens"] == 236
    assert llama["prompt_tokens_processed"] == 1
    assert llama["predicted_tokens"] == 35
    assert llama["context_tokens"] == 1 + 236 + 35
    assert llama["predicted_per_second"] == pytest.approx(52.94)
    assert event["rate_card_version"].startswith("local-")


def test_metrics_endpoint_failure_does_not_fail_call() -> None:
    client = LLMClient(base_url="http://127.0.0.1:1")  # closed port
    start = time.monotonic()
    result = client.metrics()
    elapsed = time.monotonic() - start
    assert result is None
    assert elapsed < 5.0


def test_local_estimate_uses_versioned_local_cost_profile(tmp_path: Path) -> None:
    rate_dir = tmp_path / ".orchestrator" / "costs" / "rate-cards"
    rate_dir.mkdir(parents=True)
    (rate_dir / "local-mac-studio-2026-04-21T20:00:00Z.json").write_text(
        '{"machine_id": "mac-studio", "hourly_cost_usd": 3.6,'
        ' "rate_card_version": "local-mac-studio-2026-04-21T20:00:00Z"}',
        encoding="utf-8",
    )
    profile, version = load_local_cost_profile(tmp_path)
    assert version == "local-mac-studio-2026-04-21T20:00:00Z"
    assert profile["hourly_cost_usd"] == 3.6
    cost = estimate_local_cost(profile, wall_ms=3_600_000.0)
    assert cost == pytest.approx(3.6)


def test_local_estimate_default_profile_when_no_rate_card(tmp_path: Path) -> None:
    profile, version = load_local_cost_profile(tmp_path)
    assert version.startswith("local-")
    assert version.endswith("Z")
    assert profile["default_source"] == "local_estimate"


def test_llamacpp_call_uses_versioned_rate_card_from_disk(tmp_path: Path) -> None:
    rate_dir = tmp_path / ".orchestrator" / "costs" / "rate-cards"
    rate_dir.mkdir(parents=True)
    (rate_dir / "local-mac-studio-2026-04-21T20:00:00Z.json").write_text(
        '{"machine_id": "mac-studio", "hourly_cost_usd": 3.6,'
        ' "rate_card_version": "local-mac-studio-2026-04-21T20:00:00Z"}',
        encoding="utf-8",
    )
    state = State(tmp_path)
    state.events = CaptureBus()
    emit_llm_usage(
        state,
        _LlamaLLM(),
        _llamacpp_response(),
        role="architect",
        step="plan",
        runtime_ms=3_600_000.0,
    )
    event = state.events.events[0]  # type: ignore[union-attr]
    assert event["rate_card_version"] == "local-mac-studio-2026-04-21T20:00:00Z"
    assert event["cost_usd"] == pytest.approx(3.6)
