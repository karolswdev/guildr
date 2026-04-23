"""Unit tests for the H6.4 opencode → audit-trail translator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
    OpencodeToolCall,
)
from orchestrator.lib.opencode_audit import emit_session_audit
from orchestrator.lib.raw_io import raw_io_path
from orchestrator.lib.usage import emit_advisor_usage
from orchestrator.lib.usage_writer import usage_path


def _message(
    *,
    text: str = "",
    provider: str = "prov",
    model: str = "m",
    cost: float = 0.001,
    input_tokens: int = 10,
    output_tokens: int = 5,
    reasoning_tokens: int = 0,
    cache_read: int = 0,
    created_ms: int = 1_000,
    completed_ms: int = 1_250,
    role: str = "assistant",
    tool_calls: list[OpencodeToolCall] | None = None,
) -> OpencodeMessage:
    return OpencodeMessage(
        role=role,
        provider=provider,
        model=model,
        tokens=OpencodeTokens(
            total=input_tokens + output_tokens + reasoning_tokens,
            input=input_tokens,
            output=output_tokens,
            reasoning=reasoning_tokens,
            cache_read=cache_read,
        ),
        cost=cost,
        created_ms=created_ms,
        completed_ms=completed_ms,
        text_parts=[text] if text else [],
        tool_calls=tool_calls or [],
    )


def _result(messages: list[OpencodeMessage], *, exit_code: int = 0) -> OpencodeResult:
    total_tokens = OpencodeTokens()
    total_cost = 0.0
    for m in messages:
        total_tokens = total_tokens + m.tokens
        total_cost += m.cost
    return OpencodeResult(
        session_id="ses_test",
        exit_code=exit_code,
        directory=".",
        messages=messages,
        total_tokens=total_tokens,
        total_cost=total_cost,
        summary_additions=0,
        summary_deletions=0,
        summary_files=0,
        raw_export={},
        raw_events=[],
    )


class _CollectingBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event_type: str, **fields: object) -> None:
        self.events.append((event_type, dict(fields)))


@pytest.fixture
def state(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(project_dir=tmp_path, events=_CollectingBus())


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
    ]


def test_one_row_per_assistant_message(state: SimpleNamespace) -> None:
    result = _result([
        _message(text="first", input_tokens=10, output_tokens=3, cost=0.0001),
        _message(text="second", input_tokens=7, output_tokens=4, cost=0.0002),
    ])

    ids = emit_session_audit(
        state, result, role="coder", phase="implementation",
        step="implementation", prompt="do the thing", atom_id="task-001",
    )

    assert len(ids) == 2
    raw = _read_jsonl(raw_io_path(state.project_dir))
    usage = _read_jsonl(usage_path(state.project_dir))
    assert len(raw) == 2
    assert len(usage) == 2
    assert {r["request_id"] for r in raw} == set(ids)
    assert {u["call_id"] for u in usage} == set(ids)


def test_user_messages_are_skipped(state: SimpleNamespace) -> None:
    result = _result([
        _message(role="user", text="user-turn"),
        _message(role="assistant", text="assistant-turn"),
    ])

    ids = emit_session_audit(
        state, result, role="coder", phase="implementation",
        step="implementation", prompt="p",
    )

    assert len(ids) == 1
    raw = _read_jsonl(raw_io_path(state.project_dir))
    assert raw[0]["response_content"] == "assistant-turn"


def test_raw_io_carries_prompt_and_tokens(state: SimpleNamespace) -> None:
    result = _result([
        _message(
            text="hello",
            input_tokens=42, output_tokens=7, reasoning_tokens=3,
            cache_read=5, created_ms=2000, completed_ms=2500,
            provider="openrouter",
        ),
    ])

    emit_session_audit(
        state, result, role="coder", phase="implementation",
        step="implementation", prompt="THE PROMPT",
    )

    raw = _read_jsonl(raw_io_path(state.project_dir))[0]
    assert raw["messages"] == [{"role": "user", "content": "THE PROMPT"}]
    assert raw["response_content"] == "hello"
    assert raw["usage"] == {
        "prompt_tokens": 42, "completion_tokens": 7, "reasoning_tokens": 3,
    }
    assert raw["latency_ms"] == 500.0
    assert raw["endpoint"] == "openrouter"


def test_usage_carries_session_metadata(state: SimpleNamespace) -> None:
    memory_dir = state.project_dir / ".orchestrator" / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "wake-up.md").write_text("wake up", encoding="utf-8")
    result = _result([
        _message(text="t", cost=0.0025, provider="gpt5-provider", model="gpt-5"),
    ])

    emit_session_audit(
        state, result, role="coder", phase="implementation",
        step="implementation", prompt="p", atom_id="task-007", attempt=2,
    )

    usage = _read_jsonl(usage_path(state.project_dir))[0]
    assert usage["provider_kind"] == "opencode"
    assert usage["provider_name"] == "gpt5-provider"
    assert usage["model"] == "gpt-5"
    assert usage["atom_id"] == "task-007"
    assert usage["attempt"] == 2
    assert usage["cost_usd"] == 0.0025
    assert usage["cost"]["source"] == "provider_reported"
    assert usage["finish_reason"] == "stop"
    assert usage["runtime"]["opencode"] == {
        "session_id": "ses_test", "message_index": 0, "exit_code": 0,
    }
    assert usage["runtime"]["memory"] == {
        "wake_up_hash": hashlib.sha256(b"wake up").hexdigest(),
        "memory_refs": [".orchestrator/memory/wake-up.md"],
    }
    assert usage["provider_metadata"]["opencode"] == {
        "session_id": "ses_test", "message_index": 0, "exit_code": 0,
    }


def test_bus_receives_usage_event(state: SimpleNamespace) -> None:
    result = _result([_message(text="t")])
    emit_session_audit(
        state, result, role="coder", phase="implementation",
        step="implementation", prompt="p",
    )
    emitted = [(t, f["call_id"]) for t, f in state.events.events]
    assert len(emitted) == 1
    event_type, call_id = emitted[0]
    assert event_type == "usage_recorded"
    usage = _read_jsonl(usage_path(state.project_dir))[0]
    assert usage["call_id"] == call_id


def test_failed_session_still_audits_with_error_status(state: SimpleNamespace) -> None:
    result = _result([_message(text="partial")], exit_code=3)
    emit_session_audit(
        state, result, role="coder", phase="implementation",
        step="implementation", prompt="p",
    )
    raw = _read_jsonl(raw_io_path(state.project_dir))[0]
    usage = _read_jsonl(usage_path(state.project_dir))[0]
    assert raw["finish_reason"] == "error"
    assert usage["status"] == "error"
    assert usage["finish_reason"] == "error"
    assert usage["error_type"] == "ProviderError"
    assert usage["error"] == "opencode exited with code 3"


def test_zero_cost_reports_unknown_source(state: SimpleNamespace) -> None:
    result = _result([_message(text="t", cost=0.0)])
    emit_session_audit(
        state, result, role="coder", phase="implementation",
        step="implementation", prompt="p",
    )
    usage = _read_jsonl(usage_path(state.project_dir))[0]
    assert usage["cost_usd"] is None
    assert usage["cost"]["source"] == "unknown"


def test_zero_cost_local_provider_uses_local_estimate(state: SimpleNamespace) -> None:
    rate_dir = state.project_dir / ".orchestrator" / "costs" / "rate-cards"
    rate_dir.mkdir(parents=True)
    (rate_dir / "local-test.json").write_text(
        json.dumps({
            "rate_card_version": "local-test",
            "hourly_cost_usd": 36.0,
            "default_source": "local_estimate",
        }),
        encoding="utf-8",
    )
    result = _result([
        _message(text="t", provider="local-gpu", cost=0.0, created_ms=1000, completed_ms=1500),
    ])

    emit_session_audit(
        state, result, role="coder", phase="implementation",
        step="implementation", prompt="p",
    )

    usage = _read_jsonl(usage_path(state.project_dir))[0]
    assert usage["cost_usd"] == pytest.approx(0.005)
    assert usage["source"] == "local_estimate"
    assert usage["confidence"] == "medium"
    assert usage["extraction_path"] == "opencode_message.local_estimate"
    assert usage["cost"]["estimated_cost"] == pytest.approx(0.005)
    assert usage["cost"]["rate_card_version"] == "local-test"
    assert usage["cost"]["rate_card_ref"] == ".orchestrator/costs/rate-cards/local-test.json"
    assert usage["rate_card_version"] == "local-test"
    assert usage["rate_card_ref"] == ".orchestrator/costs/rate-cards/local-test.json"


def test_opencode_and_advisor_usage_rows_share_core_schema(state: SimpleNamespace) -> None:
    result = _result([_message(text="t", provider="opencode-provider", cost=0.002)])
    opencode_ids = emit_session_audit(
        state, result, role="coder", phase="implementation",
        step="implementation", prompt="p", atom_id="task-1", attempt=1,
    )
    advisor_id = emit_advisor_usage(
        state,
        provider_kind="advisor",
        provider_name="claude",
        model="opus",
        role="reviewer",
        step="review",
        runtime_ms=123.4,
        status="error",
        usage={"prompt_tokens": 3, "completion_tokens": 4, "reasoning_tokens": 1},
        cost_usd=0.1,
        source="provider_reported",
        confidence="high",
        extraction_path="advisor.response.usage",
        error="advisor failed",
        provider_metadata={"request_id": "safe", "api_key": "redacted"},
    )

    rows = _read_jsonl(usage_path(state.project_dir))
    by_call_id = {row["call_id"]: row for row in rows}
    shared_keys = {
        "call_id", "provider_kind", "provider_name", "model", "role", "step",
        "atom_id", "attempt", "usage", "runtime_ms", "runtime", "cost_usd",
        "cost", "source", "confidence", "extraction_path", "status",
        "provider_metadata",
    }
    cost_keys = {
        "currency", "provider_reported_cost", "estimated_cost", "effective_cost",
        "source", "confidence", "extraction_path", "rate_card_version", "rate_card_ref",
    }
    for call_id in [opencode_ids[0], advisor_id]:
        row = by_call_id[call_id]
        assert shared_keys <= set(row)
        assert cost_keys <= set(row["cost"])
        assert {"input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"} <= set(row["usage"])

    advisor_row = by_call_id[advisor_id]
    assert "api_key" not in advisor_row["provider_metadata"]


def test_join_key_matches_between_raw_io_and_usage(state: SimpleNamespace) -> None:
    result = _result([
        _message(text="a"),
        _message(text="b"),
        _message(text="c"),
    ])
    ids = emit_session_audit(
        state, result, role="coder", phase="implementation",
        step="implementation", prompt="p",
    )
    raw = _read_jsonl(raw_io_path(state.project_dir))
    usage = _read_jsonl(usage_path(state.project_dir))
    raw_ids = [r["request_id"] for r in raw]
    usage_ids = [u["call_id"] for u in usage]
    assert raw_ids == ids == usage_ids
    assert len(set(raw_ids)) == 3  # unique
