"""SDLC loop event helpers."""

from __future__ import annotations

from typing import Any


LOOP_STAGE_BY_STEP: dict[str, str] = {
    "memory_refresh": "learn",
    "persona_forum": "discover",
    "architect": "plan",
    "micro_task_breakdown": "plan",
    "implementation": "build",
    "testing": "verify",
    "guru_escalation": "repair",
    "review": "review",
    "deployment": "ship",
}


def loop_stage_for_step(step: str) -> str:
    return LOOP_STAGE_BY_STEP.get(step, "plan")


def emit_loop_event(
    events: Any,
    event_type: str,
    *,
    step: str,
    loop_stage: str | None = None,
    atom_id: str | None = None,
    artifact_refs: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    memory_refs: list[str] | None = None,
    cost_snapshot_ref: str | None = None,
    **fields: Any,
) -> None:
    """Emit a schema-stable SDLC loop event."""
    stage = loop_stage or loop_stage_for_step(step)
    atom = atom_id or step
    payload: dict[str, Any] = {
        "step": step,
        "atom_id": atom,
        "loop_id": f"{atom}:{stage}",
        "loop_stage": stage,
        "artifact_refs": artifact_refs or [],
        "evidence_refs": evidence_refs or [],
        "memory_refs": memory_refs or [],
        **fields,
    }
    if cost_snapshot_ref is not None:
        payload["cost_snapshot_ref"] = cost_snapshot_ref
    events.emit(event_type, **payload)
