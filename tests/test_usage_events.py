"""Tests for normalized provider usage events."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.lib.llm import LLMResponse
from orchestrator.lib.llm_fake import FakeLLMClient
from orchestrator.lib.state import State
from orchestrator.roles.base import BaseRole


class CaptureBus:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, **fields) -> None:
        self.events.append({"type": event_type, **fields})


class FailingLLM:
    def chat(self, messages, **kw):
        raise RuntimeError("provider unavailable")


@pytest.fixture
def state(tmp_path: Path) -> State:
    state = State(tmp_path)
    state.events = CaptureBus()
    return state


def test_fake_provider_emits_deterministic_usage_event(state: State) -> None:
    llm = FakeLLMClient(
        responses={
            "default": LLMResponse(
                content="ok",
                reasoning="",
                prompt_tokens=7,
                completion_tokens=11,
                reasoning_tokens=2,
                finish_reason="stop",
                model="fake-model",
                usage_metadata={"prompt_tokens": 7, "api_key": "redacted"},
            )
        }
    )
    role = BaseRole(llm, state)
    role._phase = "testing"
    role._role = "tester"

    role._chat([{"role": "user", "content": "secret Authorization: Bearer abc"}])

    events = state.events.events  # type: ignore[union-attr]
    usage = [event for event in events if event["type"] == "usage_recorded"]
    assert len(usage) == 1
    event = usage[0]
    assert event["provider_kind"] == "fake"
    assert event["provider_name"] == "fake"
    assert event["model"] == "fake-model"
    assert event["role"] == "tester"
    assert event["step"] == "testing"
    assert event["usage"] == {
        "input_tokens": 7,
        "output_tokens": 11,
        "reasoning_tokens": 2,
        "total_tokens": 20,
    }
    assert event["confidence"] == "none"
    assert event["cost"]["source"] == "unknown"
    assert event["cost"]["effective_cost"] is None
    assert "api_key" not in event["provider_metadata"]
    assert "Authorization" not in repr(event)


def test_provider_failure_emits_error_and_usage_event(state: State) -> None:
    role = BaseRole(FailingLLM(), state)
    role._phase = "review"
    role._role = "reviewer"

    with pytest.raises(RuntimeError):
        role._chat([{"role": "user", "content": "hi"}])

    events = state.events.events  # type: ignore[union-attr]
    assert [event["type"] for event in events] == ["usage_recorded", "provider_call_error"]
    assert events[0]["status"] == "error"
    assert events[0]["usage"]["total_tokens"] == 0
    assert events[0]["error_type"] == "RuntimeError"
    assert events[1]["provider_name"] == "FailingLLM"
