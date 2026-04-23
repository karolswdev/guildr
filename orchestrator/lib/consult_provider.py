"""Direct provider call for model-backed consult (A-8.5b).

Wraps one bounded chat-completion HTTP call to an OpenAI-compatible
endpoint and returns a ``ModelCall`` closure that
:func:`orchestrator.lib.consult_model.render_consult_model` can consume.

No retries. No streaming. One call, one usage row. Errors propagate so the
consult_model layer can fall back to the deterministic renderer.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import httpx

from orchestrator.lib.consult_routing import ResolvedConsultPolicy
from orchestrator.lib.endpoints import EndpointSpec, EndpointsConfig
from orchestrator.lib.memory_palace import memory_event_fields
from orchestrator.lib.usage import emit_advisor_usage

logger = logging.getLogger(__name__)


class ConsultProviderUnavailable(RuntimeError):
    """The policy's provider is not configured in EndpointsConfig."""


ModelCall = Callable[[str, str], str]


def build_consult_model_call(
    *,
    policy: ResolvedConsultPolicy,
    endpoints: EndpointsConfig,
    state: Any,
    role: str = "founding_team_consult",
    step: str | None = None,
    http_client_factory: Callable[[float], httpx.Client] | None = None,
) -> ModelCall:
    """Return a closure that performs one bounded chat-completion call."""
    endpoint = endpoints.by_name.get(policy.provider)
    if endpoint is None:
        raise ConsultProviderUnavailable(
            f"no endpoint configured for provider={policy.provider!r}"
        )
    model_name = policy.model or endpoint.model
    step_name = step or policy.trigger_tag or "consult"
    factory = http_client_factory or (lambda timeout: httpx.Client(timeout=timeout))

    def _call(system: str, user: str) -> str:
        body = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": policy.max_tokens,
            "temperature": policy.temperature,
            "response_format": {"type": "json_object"},
        }
        if isinstance(endpoint.extra_body, dict):
            body.update(endpoint.extra_body)
        headers = dict(endpoint.headers or {})
        if endpoint.api_key:
            headers["Authorization"] = f"Bearer {endpoint.api_key}"

        t0 = time.monotonic()
        try:
            with factory(policy.timeout_s) as client:
                response = client.post(
                    _chat_completions_url(endpoint),
                    headers=headers,
                    json=body,
                )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001 — any failure ⇒ fallback
            elapsed_ms = (time.monotonic() - t0) * 1000
            _emit_failure(state, policy, role, step_name, elapsed_ms, exc, model_name)
            raise

        elapsed_ms = (time.monotonic() - t0) * 1000
        raw = _extract_assistant_text(data)
        _emit_success(state, policy, role, step_name, elapsed_ms, data, model_name)
        return raw

    return _call


def _chat_completions_url(endpoint: EndpointSpec) -> str:
    base = endpoint.base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _extract_assistant_text(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices") or []
    if not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None
    return content if isinstance(content, str) else ""


def _policy_metadata(
    policy: ResolvedConsultPolicy, model_name: str, state: Any
) -> dict[str, Any]:
    project_dir = getattr(state, "project_dir", None)
    provenance = (
        memory_event_fields(getattr(project_dir, "name", None), project_dir)
        if project_dir is not None
        else {}
    )
    return {
        "consult_policy": {
            "mode": policy.mode,
            "provider": policy.provider,
            "model": model_name,
            "trigger_tag": policy.trigger_tag,
            "max_tokens": policy.max_tokens,
        },
        "wake_up_hash": provenance.get("wake_up_hash"),
        "memory_refs": list(provenance.get("memory_refs") or []),
    }


def _emit_success(
    state: Any,
    policy: ResolvedConsultPolicy,
    role: str,
    step: str,
    elapsed_ms: float,
    response_payload: Any,
    model_name: str,
) -> None:
    usage = (
        response_payload.get("usage")
        if isinstance(response_payload, dict)
        and isinstance(response_payload.get("usage"), dict)
        else None
    )
    has_cost = isinstance(usage, dict) and isinstance(usage.get("cost"), (int, float))
    metadata = _policy_metadata(policy, model_name, state)
    metadata["usage"] = usage
    emit_advisor_usage(
        state,
        provider_kind="llama-server",
        provider_name=policy.provider,
        model=model_name,
        role=role,
        step=step,
        runtime_ms=elapsed_ms,
        status="ok",
        usage=usage,
        cost_usd=float(usage["cost"]) if has_cost else None,
        source="provider_reported" if has_cost else "unknown",
        confidence="high" if has_cost else "none",
        extraction_path="response_usage" if has_cost else "consult.no_cost",
        provider_metadata=metadata,
    )


def _emit_failure(
    state: Any,
    policy: ResolvedConsultPolicy,
    role: str,
    step: str,
    elapsed_ms: float,
    exc: BaseException,
    model_name: str,
) -> None:
    emit_advisor_usage(
        state,
        provider_kind="llama-server",
        provider_name=policy.provider,
        model=model_name,
        role=role,
        step=step,
        runtime_ms=elapsed_ms,
        status="error",
        source="unknown",
        confidence="none",
        extraction_path="consult.error",
        error=exc,
        provider_metadata=_policy_metadata(policy, model_name, state),
    )
