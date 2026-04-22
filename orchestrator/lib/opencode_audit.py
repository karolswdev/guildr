"""Translate opencode session results into raw-io + usage audit rows (H6.4).

H6.3a rewired the Coder to drive an opencode agent session. Roles that
go through the direct ``LLMClient`` emit one row per LLM call into
``.orchestrator/logs/raw-io.jsonl`` (prompt + response + tokens) and
one matching row into ``.orchestrator/logs/usage.jsonl`` (cost +
provider metadata), keyed by the same ``request_id`` / ``call_id`` so
downstream rollups can join them. Opencode sessions skip that path,
which left coder entries missing from the audit trail.

This module re-opens that contract. Given an :class:`OpencodeResult`
and the role/phase context, :func:`emit_session_audit` writes one
raw-io row and one usage row per **assistant message** in the session.
Per-message (not per-session) because each assistant turn is the
natural analogue of a single LLM call today — it carries its own
token counts, its own cost, its own latency.

Join keys:

- ``request_id`` (raw-io) == ``call_id`` (usage) — fresh id per message.
- ``session_id`` — same across every row from one ``OpencodeResult``,
  so a rollup can group "this task's work" even though it spans
  multiple assistant turns.
- ``atom_id`` — the sprint-plan task id, so rollups can group across
  the full implementation phase.

Not here: opencode's tool-call records themselves. Those live in
``raw_export`` / ``raw_events`` on the :class:`OpencodeResult` and are
a separate concern (H6 follow-up: opencode event replay).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.lib.event_schema import new_event_id
from orchestrator.lib.memory_palace import wakeup_hash
from orchestrator.lib.opencode import OpencodeMessage, OpencodeResult
from orchestrator.lib.raw_io import write_round_trip
from orchestrator.lib.usage_writer import write_usage


@dataclass
class _RawIoResponseView:
    """Attribute shim so we can reuse ``write_round_trip`` unchanged.

    ``write_round_trip`` reads ``content`` / ``reasoning_content`` /
    ``finish_reason`` / token fields off the response object via
    ``getattr``. Building a one-off dataclass here is simpler than
    generalising the writer's signature.
    """

    content: str
    reasoning_content: str
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int


def emit_session_audit(
    state: Any,
    result: OpencodeResult,
    *,
    role: str,
    phase: str,
    step: str,
    prompt: str,
    atom_id: str | None = None,
    attempt: int | None = None,
) -> list[str]:
    """Emit one raw-io + one usage row per assistant message in ``result``.

    Returns the list of ``request_id``s written, in order. Caller uses
    this for logging / correlation; tests assert on it.

    ``prompt`` is the full user prompt that opened the session — we
    record it as the sole ``messages[0]`` in each raw-io row so the
    audit log reads like the old LLM-call trail. Opencode's intra-
    session messages are already captured in ``result.raw_export`` if
    a reviewer needs them.
    """
    project_dir = _project_dir_of(state)
    memory_hash = wakeup_hash(project_dir) if project_dir is not None else None
    request_ids: list[str] = []

    for idx, msg in enumerate(result.messages):
        if msg.role != "assistant":
            continue
        call_id = new_event_id()
        request_ids.append(call_id)

        response = _RawIoResponseView(
            content="".join(msg.text_parts),
            reasoning_content="",
            finish_reason="stop" if result.exit_code == 0 else "error",
            prompt_tokens=msg.tokens.input,
            completion_tokens=msg.tokens.output,
            reasoning_tokens=msg.tokens.reasoning,
        )

        if project_dir is not None:
            write_round_trip(
                project_dir,
                phase=phase,
                role=role,
                request_id=call_id,
                messages=[{"role": "user", "content": prompt}],
                response=response,
                latency_ms=msg.latency_ms,
                endpoint=msg.provider,
            )

        _emit_usage(
            state,
            msg,
            role=role,
            step=step,
            call_id=call_id,
            atom_id=atom_id,
            attempt=attempt,
            session_id=result.session_id,
            message_index=idx,
            session_exit_code=result.exit_code,
            wake_up_hash=memory_hash,
        )

    return request_ids


def _emit_usage(
    state: Any,
    msg: OpencodeMessage,
    *,
    role: str,
    step: str,
    call_id: str,
    atom_id: str | None,
    attempt: int | None,
    session_id: str,
    message_index: int,
    session_exit_code: int,
    wake_up_hash: str | None,
) -> None:
    """Build + persist one usage row for a single assistant message."""
    cost_usd = msg.cost if msg.cost > 0 else None
    source = "provider_reported" if cost_usd is not None else "unknown"
    confidence = "high" if cost_usd is not None else "none"

    usage = {
        "input_tokens": msg.tokens.input,
        "output_tokens": msg.tokens.output,
        "reasoning_tokens": msg.tokens.reasoning,
        "total_tokens": msg.tokens.input + msg.tokens.output + msg.tokens.reasoning,
    }
    if msg.tokens.cache_read:
        usage["cache_read_tokens"] = msg.tokens.cache_read

    status = "ok" if session_exit_code == 0 else "error"

    payload: dict[str, Any] = {
        "call_id": call_id,
        "provider_kind": "opencode",
        "provider_name": msg.provider or "opencode",
        "model": msg.model or "",
        "role": role,
        "step": step,
        "atom_id": atom_id,
        "attempt": attempt,
        "usage": usage,
        "runtime_ms": round(msg.latency_ms, 1),
        "runtime": {
            "wall_ms": round(msg.latency_ms, 1),
            "opencode": {
                "session_id": session_id,
                "message_index": message_index,
            },
            "memory": {
                "wake_up_hash": wake_up_hash,
                "memory_refs": [".orchestrator/memory/wake-up.md"] if wake_up_hash else [],
            },
        },
        "cost_usd": cost_usd,
        "cost": {
            "currency": "USD",
            "provider_reported_cost": cost_usd,
            "estimated_cost": None,
            "effective_cost": cost_usd,
            "source": source,
            "confidence": confidence,
            "extraction_path": "opencode_message.cost",
            "rate_card_version": None,
        },
        "source": source,
        "confidence": confidence,
        "extraction_path": "opencode_message.cost",
        "status": status,
    }

    event_bus = getattr(state, "events", None)
    if event_bus is not None:
        event_bus.emit("usage_recorded", **payload)

    write_usage(_project_dir_of(state), payload)


def _project_dir_of(state: Any) -> Path | None:
    pd = getattr(state, "project_dir", None)
    if pd is None:
        return None
    return Path(pd)
