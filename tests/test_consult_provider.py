"""Tests for consult_provider (A-8.5b)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from orchestrator.lib.consult_provider import (
    ConsultProviderUnavailable,
    build_consult_model_call,
)
from orchestrator.lib.consult_routing import ResolvedConsultPolicy
from orchestrator.lib.endpoints import EndpointSpec, EndpointsConfig


def _policy(
    *,
    provider: str = "primary",
    model: str = "qwen2.5-coder-32b",
    trigger: str = "reviewer_done",
    timeout: float = 5.0,
) -> ResolvedConsultPolicy:
    return ResolvedConsultPolicy(
        trigger_tag=trigger,
        mode="model",
        provider=provider,
        model=model,
        max_tokens=512,
        temperature=0.2,
        timeout_s=timeout,
        fallback_on_error=True,
    )


def _endpoints(
    *,
    name: str = "primary",
    base_url: str = "http://lan.example/v1",
    model: str = "qwen2.5-coder-32b",
    api_key: str | None = None,
) -> EndpointsConfig:
    return EndpointsConfig(
        endpoints=[
            EndpointSpec(
                name=name,
                base_url=base_url,
                model=model,
                api_key=api_key,
            )
        ],
        routing={},
    )


def _state(tmp_path: Path) -> SimpleNamespace:
    events = MagicMock()
    return SimpleNamespace(
        project_dir=tmp_path,
        events=events,
    )


class _FakeResponse:
    def __init__(self, *, status: int = 200, payload: dict | None = None):
        self.status_code = status
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "bad", request=MagicMock(), response=MagicMock(status_code=self.status_code)
            )

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, *, response: _FakeResponse | Exception):
        self._response = response
        self.last_url: str | None = None
        self.last_headers: dict | None = None
        self.last_json: dict | None = None

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *a) -> None:
        return None

    def post(self, url, *, headers, json):
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _factory_with(client: _FakeClient):
    def _make(_timeout: float):
        return client
    return _make


def test_happy_path_returns_assistant_content(tmp_path):
    client = _FakeClient(
        response=_FakeResponse(
            payload={
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        )
    )
    call = build_consult_model_call(
        policy=_policy(),
        endpoints=_endpoints(),
        state=_state(tmp_path),
        http_client_factory=_factory_with(client),
    )
    out = call("system prompt", "user prompt")
    assert out == '{"ok":true}'
    assert client.last_url == "http://lan.example/v1/chat/completions"
    assert client.last_json["model"] == "qwen2.5-coder-32b"
    assert client.last_json["messages"][0]["role"] == "system"
    assert client.last_json["response_format"] == {"type": "json_object"}


def test_authorization_header_added_when_api_key_set(tmp_path):
    client = _FakeClient(
        response=_FakeResponse(
            payload={"choices": [{"message": {"content": "x"}}]}
        )
    )
    call = build_consult_model_call(
        policy=_policy(),
        endpoints=_endpoints(api_key="sk-abc"),
        state=_state(tmp_path),
        http_client_factory=_factory_with(client),
    )
    call("s", "u")
    assert client.last_headers["Authorization"] == "Bearer sk-abc"


def test_usage_row_emitted_on_success(tmp_path):
    state = _state(tmp_path)
    client = _FakeClient(
        response=_FakeResponse(
            payload={
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        )
    )
    call = build_consult_model_call(
        policy=_policy(),
        endpoints=_endpoints(),
        state=state,
        http_client_factory=_factory_with(client),
    )
    call("s", "u")
    # emit_advisor_usage calls state.events.emit("usage_recorded", ...)
    emits = [c for c in state.events.emit.call_args_list if c.args and c.args[0] == "usage_recorded"]
    assert len(emits) == 1
    kwargs = emits[0].kwargs
    assert kwargs["status"] == "ok"
    assert kwargs["role"] == "founding_team_consult"
    assert kwargs["step"] == "reviewer_done"


def test_usage_row_emitted_on_http_error(tmp_path):
    state = _state(tmp_path)
    client = _FakeClient(response=_FakeResponse(status=500))
    call = build_consult_model_call(
        policy=_policy(),
        endpoints=_endpoints(),
        state=state,
        http_client_factory=_factory_with(client),
    )
    with pytest.raises(httpx.HTTPStatusError):
        call("s", "u")
    emits = [c for c in state.events.emit.call_args_list if c.args and c.args[0] == "usage_recorded"]
    assert len(emits) == 1
    assert emits[0].kwargs["status"] == "error"


def test_timeout_raises_and_emits_error(tmp_path):
    state = _state(tmp_path)
    client = _FakeClient(response=httpx.ReadTimeout("slow"))
    call = build_consult_model_call(
        policy=_policy(timeout=0.01),
        endpoints=_endpoints(),
        state=state,
        http_client_factory=_factory_with(client),
    )
    with pytest.raises(httpx.ReadTimeout):
        call("s", "u")
    emits = [c for c in state.events.emit.call_args_list if c.args and c.args[0] == "usage_recorded"]
    assert emits and emits[0].kwargs["status"] == "error"


def test_unknown_provider_raises_unavailable(tmp_path):
    with pytest.raises(ConsultProviderUnavailable):
        build_consult_model_call(
            policy=_policy(provider="missing"),
            endpoints=_endpoints(name="primary"),
            state=_state(tmp_path),
        )


def test_cost_extraction_when_provider_reports(tmp_path):
    state = _state(tmp_path)
    client = _FakeClient(
        response=_FakeResponse(
            payload={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "cost": 0.0042},
            }
        )
    )
    call = build_consult_model_call(
        policy=_policy(),
        endpoints=_endpoints(),
        state=state,
        http_client_factory=_factory_with(client),
    )
    call("s", "u")
    emit = [c for c in state.events.emit.call_args_list if c.args[0] == "usage_recorded"][0]
    assert emit.kwargs["cost"]["provider_reported_cost"] == pytest.approx(0.0042)
    assert emit.kwargs["source"] == "provider_reported"


def test_cost_none_when_provider_silent(tmp_path):
    state = _state(tmp_path)
    client = _FakeClient(
        response=_FakeResponse(
            payload={"choices": [{"message": {"content": "ok"}}]}
        )
    )
    call = build_consult_model_call(
        policy=_policy(),
        endpoints=_endpoints(),
        state=state,
        http_client_factory=_factory_with(client),
    )
    call("s", "u")
    emit = [c for c in state.events.emit.call_args_list if c.args[0] == "usage_recorded"][0]
    assert emit.kwargs["cost"]["provider_reported_cost"] is None
    assert emit.kwargs["source"] == "unknown"
