"""Usage event normalization for LLM and advisor calls."""

from __future__ import annotations

from typing import Any

from orchestrator.lib.budget import apply_budget_to_usage, emit_budget_events
from orchestrator.lib.event_schema import new_event_id
from orchestrator.lib.local_cost import (
    annotate_rate_card_snapshot_status,
    estimate_local_cost,
    load_local_cost_profile,
    rate_card_snapshot_ref,
)


def emit_llm_usage(
    state: Any,
    llm: Any,
    response: Any | None,
    *,
    role: str,
    step: str,
    runtime_ms: float,
    call_id: str | None = None,
    status: str = "ok",
    error: Exception | str | None = None,
    atom_id: str | None = None,
    attempt: int | None = None,
) -> None:
    """Emit normalized usage for an LLM-style call when an event bus exists."""
    event_bus = getattr(state, "events", None)
    if event_bus is None:
        return

    provider = _provider_for_llm(llm)
    is_llamacpp = provider["kind"] == "llamacpp"

    timings = getattr(response, "timings", None) if response is not None else None
    if not isinstance(timings, dict):
        timings = None

    input_tokens = _int_attr(response, "prompt_tokens")
    output_tokens = _int_attr(response, "completion_tokens")
    reasoning_tokens = _int_attr(response, "reasoning_tokens")
    cache_read_tokens = 0
    runtime_extra: dict[str, Any] = {}
    extraction_path = "LLMResponse.token_fields" if response is not None else "error.no_usage"

    if is_llamacpp and response is not None:
        usage_present = input_tokens > 0 or output_tokens > 0
        if timings is not None:
            prompt_n = _int_key(timings, "prompt_n")
            cache_n = _int_key(timings, "cache_n")
            predicted_n = _int_key(timings, "predicted_n")
            if not usage_present:
                input_tokens = prompt_n
                output_tokens = predicted_n
                extraction_path = "llamacpp_timings"
            else:
                extraction_path = "llamacpp_openai_usage"
            cache_read_tokens = cache_n
            runtime_extra["llamacpp"] = {
                "cache_tokens": cache_n,
                "prompt_tokens_processed": prompt_n,
                "predicted_tokens": predicted_n,
                "prompt_ms": _opt_float(timings.get("prompt_ms")),
                "predicted_ms": _opt_float(timings.get("predicted_ms")),
                "prompt_per_second": _opt_float(timings.get("prompt_per_second")),
                "predicted_per_second": _opt_float(timings.get("predicted_per_second")),
                "context_tokens": prompt_n + cache_n + predicted_n,
                "metrics_enabled": False,
            }
        elif usage_present:
            extraction_path = "llamacpp_openai_usage"

    if is_llamacpp:
        source = "local_estimate"
        if response is None:
            confidence = "none"
        elif timings is not None or input_tokens > 0 or output_tokens > 0:
            confidence = "medium"
        else:
            confidence = "none"
        project_dir = getattr(state, "project_dir", None)
        profile, rate_card_version = load_local_cost_profile(project_dir)
        cost_usd = estimate_local_cost(profile, wall_ms=runtime_ms) if response is not None else None
    else:
        cost_usd = _optional_float_attr(response, "cost_usd")
        source = "provider_reported" if cost_usd is not None else "unknown"
        confidence = "high" if cost_usd is not None else "none"
        rate_card_version = None

    payload = _usage_payload(
        provider_kind=provider["kind"],
        provider_name=provider["name"],
        model=_response_model(response, provider["model"]),
        role=role,
        step=step,
        runtime_ms=runtime_ms,
        call_id=call_id,
        status=status,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cache_read_tokens=cache_read_tokens,
        cost_usd=cost_usd,
        provider_reported_cost=cost_usd if source == "provider_reported" else None,
        estimated_cost=cost_usd if source in {"local_estimate", "rate_card_estimate"} else None,
        source=source,
        confidence=confidence,
        extraction_path=extraction_path,
        atom_id=atom_id,
        attempt=attempt,
        finish_reason=str(getattr(response, "finish_reason", "") or "") or None,
        error=error,
        provider_metadata=getattr(response, "usage_metadata", None),
        runtime_extra=runtime_extra,
        rate_card_version=rate_card_version,
    )
    annotate_rate_card_snapshot_status(getattr(state, "project_dir", None), payload)
    evaluation = apply_budget_to_usage(state, payload)
    event_bus.emit("usage_recorded", **payload)
    from orchestrator.lib.usage_writer import write_usage
    write_usage(getattr(state, "project_dir", None), payload)
    emit_budget_events(state, event_bus, evaluation)


def emit_provider_error(
    state: Any,
    *,
    provider_kind: str,
    provider_name: str,
    model: str | None,
    role: str,
    step: str,
    runtime_ms: float,
    error: Exception | str,
    call_id: str | None = None,
) -> None:
    """Emit a structured provider error event without secrets or prompts."""
    event_bus = getattr(state, "events", None)
    if event_bus is None:
        return
    event_bus.emit(
        "provider_call_error",
        call_id=call_id or new_event_id(),
        provider_kind=provider_kind,
        provider_name=provider_name,
        model=model or "",
        role=role,
        step=step,
        runtime_ms=round(runtime_ms, 1),
        error_type=type(error).__name__ if isinstance(error, Exception) else "ProviderError",
        error=str(error)[:1200],
    )


def emit_advisor_usage(
    state: Any,
    *,
    provider_kind: str,
    provider_name: str,
    model: str | None,
    role: str,
    step: str,
    runtime_ms: float,
    status: str,
    usage: dict[str, Any] | None = None,
    cost_usd: float | None = None,
    source: str,
    confidence: str,
    extraction_path: str,
    call_id: str | None = None,
    error: Exception | str | None = None,
    provider_metadata: dict[str, Any] | None = None,
) -> str:
    """Emit normalized usage for external advisor APIs and CLIs."""
    event_bus = getattr(state, "events", None)
    call_id = call_id or new_event_id()
    if event_bus is None:
        return call_id
    usage = usage or {}
    payload = _usage_payload(
        provider_kind=provider_kind,
        provider_name=provider_name,
        model=model or "",
        role=role,
        step=step,
        runtime_ms=runtime_ms,
        call_id=call_id,
        status=status,
        input_tokens=_int_key(usage, "prompt_tokens"),
        output_tokens=_int_key(usage, "completion_tokens"),
        reasoning_tokens=_int_key(usage, "reasoning_tokens"),
        cost_usd=cost_usd,
        provider_reported_cost=cost_usd if source == "provider_reported" else None,
        estimated_cost=cost_usd if source in {"local_estimate", "rate_card_estimate"} else None,
        source=source,
        confidence=confidence,
        extraction_path=extraction_path,
        error=error,
        provider_metadata=provider_metadata,
    )
    annotate_rate_card_snapshot_status(getattr(state, "project_dir", None), payload)
    evaluation = apply_budget_to_usage(state, payload)
    event_bus.emit("usage_recorded", **payload)
    from orchestrator.lib.usage_writer import write_usage
    write_usage(getattr(state, "project_dir", None), payload)
    emit_budget_events(state, event_bus, evaluation)
    return call_id


def _usage_payload(
    *,
    provider_kind: str,
    provider_name: str,
    model: str,
    role: str,
    step: str,
    runtime_ms: float,
    call_id: str | None,
    status: str,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    cost_usd: float | None,
    source: str,
    confidence: str,
    extraction_path: str,
    provider_reported_cost: float | None = None,
    estimated_cost: float | None = None,
    cache_read_tokens: int = 0,
    atom_id: str | None = None,
    attempt: int | None = None,
    finish_reason: str | None = None,
    error: Exception | str | None = None,
    provider_metadata: Any = None,
    runtime_extra: dict[str, Any] | None = None,
    rate_card_version: str | None = None,
) -> dict[str, Any]:
    rate_card_ref = rate_card_snapshot_ref(rate_card_version) if rate_card_version else None
    usage = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": input_tokens + output_tokens + reasoning_tokens,
    }
    if cache_read_tokens:
        usage["cache_read_tokens"] = cache_read_tokens
    runtime: dict[str, Any] = {"wall_ms": round(runtime_ms, 1)}
    if runtime_extra:
        runtime.update(runtime_extra)
    payload: dict[str, Any] = {
        "call_id": call_id or new_event_id(),
        "provider_kind": provider_kind,
        "provider_name": provider_name,
        "model": model,
        "role": role,
        "step": step,
        "atom_id": atom_id,
        "attempt": attempt,
        "usage": usage,
        "runtime_ms": round(runtime_ms, 1),
        "runtime": runtime,
        "cost_usd": cost_usd,
        "cost": {
            "currency": "USD",
            "provider_reported_cost": provider_reported_cost,
            "estimated_cost": estimated_cost,
            "effective_cost": cost_usd,
            "source": source,
            "confidence": confidence,
            "extraction_path": extraction_path,
            "rate_card_version": rate_card_version,
            "rate_card_ref": rate_card_ref,
        },
        "source": source,
        "confidence": confidence,
        "extraction_path": extraction_path,
        "status": status,
    }
    if rate_card_version:
        payload["rate_card_version"] = rate_card_version
        payload["rate_card_ref"] = rate_card_ref
    if finish_reason:
        payload["finish_reason"] = finish_reason
    if error is not None:
        payload["error_type"] = type(error).__name__ if isinstance(error, Exception) else "ProviderError"
        payload["error"] = str(error)[:1200]
    if isinstance(provider_metadata, dict):
        payload["provider_metadata"] = _safe_metadata(provider_metadata)
    return payload


def _provider_for_llm(llm: Any) -> dict[str, str]:
    class_name = type(llm).__name__
    if class_name == "FakeLLMClient":
        return {"kind": "fake", "name": "fake", "model": "fake"}
    base_url = str(getattr(llm, "base_url", "") or "")
    if base_url:
        return {"kind": "llamacpp", "name": base_url, "model": "qwen36"}
    return {"kind": "unknown", "name": class_name, "model": ""}


def _response_model(response: Any | None, fallback: str) -> str:
    if response is None:
        return fallback
    model = getattr(response, "model", None)
    return model if isinstance(model, str) and model else fallback


def _int_attr(obj: Any | None, name: str) -> int:
    if obj is None:
        return 0
    value = getattr(obj, name, 0)
    return value if isinstance(value, int) and value >= 0 else 0


def _optional_float_attr(obj: Any | None, name: str) -> float | None:
    if obj is None:
        return None
    value = getattr(obj, name, None)
    if isinstance(value, int | float):
        return float(value)
    return None


def _int_key(data: dict[str, Any], name: str) -> int:
    value = data.get(name)
    return value if isinstance(value, int) and value >= 0 else 0


def _opt_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    blocked = {"authorization", "api_key", "apikey", "token", "secret", "password"}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = key.lower()
        if any(part in lowered for part in blocked):
            continue
        if isinstance(value, dict):
            safe[key] = _safe_metadata(value)
        elif isinstance(value, list):
            safe[key] = value[:20]
        elif isinstance(value, str | int | float | bool) or value is None:
            safe[key] = value
        else:
            safe[key] = str(value)
    return safe
