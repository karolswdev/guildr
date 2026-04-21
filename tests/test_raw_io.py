"""Tests for orchestrator.lib.raw_io round-trip persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from orchestrator.lib.raw_io import raw_io_path, write_round_trip


@dataclass
class FakeResponse:
    content: str
    reasoning_content: str | None = None
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0


def _read_records(project_dir: Path) -> list[dict]:
    path = raw_io_path(project_dir)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_round_trip_is_lossless(tmp_path: Path) -> None:
    messages_a = [
        {"role": "system", "content": "You are the architect."},
        {"role": "user", "content": "qwendea: tiny CLI that uppercases its argv."},
    ]
    response_a = FakeResponse(
        content="Plan: one task, echo upper.",
        reasoning_content="weighing options...",
        finish_reason="stop",
        prompt_tokens=120,
        completion_tokens=40,
        reasoning_tokens=15,
    )

    write_round_trip(
        tmp_path,
        phase="architect",
        role="architect",
        request_id="req-aaa",
        messages=messages_a,
        response=response_a,
        latency_ms=812.4,
        endpoint="primary",
    )

    messages_b = [{"role": "user", "content": "implement task 1"}]
    response_b = FakeResponse(
        content="done",
        prompt_tokens=50,
        completion_tokens=5,
    )
    write_round_trip(
        tmp_path,
        phase="coder",
        role="coder",
        request_id="req-bbb",
        messages=messages_b,
        response=response_b,
        latency_ms=101.0,
        endpoint="alien",
    )

    records = _read_records(tmp_path)
    assert len(records) == 2

    r0, r1 = records
    assert r0["request_id"] == "req-aaa"
    assert r0["phase"] == "architect"
    assert r0["role"] == "architect"
    assert r0["endpoint"] == "primary"
    assert r0["messages"] == messages_a
    assert r0["response_content"] == "Plan: one task, echo upper."
    assert r0["reasoning_content"] == "weighing options..."
    assert r0["finish_reason"] == "stop"
    assert r0["usage"] == {"prompt_tokens": 120, "completion_tokens": 40, "reasoning_tokens": 15}
    assert r0["latency_ms"] == 812.4
    assert "ts" in r0 and r0["ts"].endswith("+00:00")

    assert r1["request_id"] == "req-bbb"
    assert r1["endpoint"] == "alien"
    assert r1["messages"] == messages_b
    assert r1["response_content"] == "done"
    assert r1["reasoning_content"] is None
    assert r1["usage"]["reasoning_tokens"] == 0


def test_secrets_in_messages_are_redacted(tmp_path: Path) -> None:
    messages = [
        {"role": "system", "content": "boot"},
        {
            "role": "user",
            "content": "use these creds",
            "metadata": {
                "api_key": "sk-live-XXXXXXXXXXXXXXXXXXXX",
                "Authorization": "Bearer eyJhbGciOi...",
                "nested": {"password": "hunter2", "safe_field": "keep me"},
                "tokens_used": 42,
            },
        },
    ]
    write_round_trip(
        tmp_path,
        phase="coder",
        role="coder",
        request_id="req-ccc",
        messages=messages,
        response=FakeResponse(content="ok"),
        latency_ms=5.0,
    )

    [record] = _read_records(tmp_path)
    meta = record["messages"][1]["metadata"]
    assert meta["api_key"] == "[redacted]"
    assert meta["Authorization"] == "[redacted]"
    assert meta["nested"]["password"] == "[redacted]"
    assert meta["nested"]["safe_field"] == "keep me"
    assert meta["tokens_used"] == "[redacted]"

    raw_bytes = raw_io_path(tmp_path).read_bytes()
    assert b"sk-live-XXXXXXXXXXXXXXXXXXXX" not in raw_bytes
    assert b"hunter2" not in raw_bytes
    assert b"eyJhbGciOi" not in raw_bytes


def test_file_is_append_only(tmp_path: Path) -> None:
    for i in range(3):
        write_round_trip(
            tmp_path,
            phase="coder",
            role="coder",
            request_id=f"req-{i}",
            messages=[{"role": "user", "content": f"msg {i}"}],
            response=FakeResponse(content=f"reply {i}"),
            latency_ms=float(i),
        )
    assert [r["request_id"] for r in _read_records(tmp_path)] == ["req-0", "req-1", "req-2"]


def test_creates_logs_directory(tmp_path: Path) -> None:
    project = tmp_path / "fresh-project"
    assert not project.exists()
    write_round_trip(
        project,
        phase="architect",
        role="architect",
        request_id="req-init",
        messages=[{"role": "user", "content": "hi"}],
        response=FakeResponse(content="hi"),
        latency_ms=1.0,
    )
    assert raw_io_path(project).is_file()
