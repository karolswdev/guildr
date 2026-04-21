"""Raw LLM round-trip persistence.

Every LLM call — prompt, response, reasoning, usage — is appended to
`.orchestrator/logs/raw-io.jsonl` in the project directory, one JSON object
per line. This is the audit trail that makes "review" real. Token-count
summaries in the phase logs tell you a call happened; this file tells you
what was asked and what was answered.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrator.lib.scrub import scrub_payload

_RAW_IO_FILENAME = "raw-io.jsonl"


def raw_io_path(project_dir: Path) -> Path:
    return project_dir / ".orchestrator" / "logs" / _RAW_IO_FILENAME


def write_round_trip(
    project_dir: Path,
    *,
    phase: str,
    role: str,
    request_id: str,
    messages: list[dict[str, Any]],
    response: Any,
    latency_ms: float,
    endpoint: str | None = None,
) -> None:
    """Append one LLM round-trip to `.orchestrator/logs/raw-io.jsonl`.

    `response` is an ``LLMResponse``-like object; the function reads
    attributes defensively so fakes and real clients both work.
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "phase": phase,
        "role": role,
        "endpoint": endpoint,
        "messages": scrub_payload(messages),
        "response_content": _get(response, "content"),
        "reasoning_content": _get(response, "reasoning_content", default=_get(response, "reasoning")),
        "finish_reason": _get(response, "finish_reason"),
        "usage": {
            "prompt_tokens": _get(response, "prompt_tokens", default=0) or 0,
            "completion_tokens": _get(response, "completion_tokens", default=0) or 0,
            "reasoning_tokens": _get(response, "reasoning_tokens", default=0) or 0,
        },
        "latency_ms": round(float(latency_ms), 1),
    }

    path = raw_io_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    return getattr(obj, name, default)
