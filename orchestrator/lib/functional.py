"""Functional mini-sprint event helpers."""

from __future__ import annotations

from typing import Any

from orchestrator.lib.event_schema import new_event_id
from orchestrator.lib.event_types import (
    FUNCTIONAL_ACCEPTANCE_EVALUATED,
    MINI_SPRINT_PLANNED,
    MINI_SPRINT_STEP_COMPLETED,
)


def build_mini_sprint_plan(
    *,
    title: str,
    objective: str,
    scope_refs: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    evidence_required: list[str] | None = None,
    demo_requested: bool = False,
    demo_compatibility: str = "unknown",
    source_refs: list[str] | None = None,
    mini_sprint_id: str | None = None,
) -> dict[str, Any]:
    """Build a replay-safe functional mini-sprint plan payload."""
    sprint_id = mini_sprint_id or f"ms_{new_event_id()}"
    return {
        "mini_sprint_id": sprint_id,
        "title": title,
        "objective": objective,
        "scope_refs": scope_refs or [],
        "acceptance_criteria": acceptance_criteria or [],
        "evidence_required": evidence_required or [],
        "demo_requested": bool(demo_requested),
        "demo_compatibility": demo_compatibility,
        "source_refs": source_refs or [],
    }


def emit_mini_sprint_planned(events: Any, run_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Emit the canonical mini-sprint planning event."""
    return events.emit(MINI_SPRINT_PLANNED, run_id=run_id, **plan)


def emit_mini_sprint_step_completed(
    events: Any,
    run_id: str,
    *,
    mini_sprint_id: str,
    step_id: str,
    step_kind: str,
    status: str,
    artifact_refs: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    source_event_ids: list[str] | None = None,
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Emit a functional progress marker over one or more low-level events."""
    return events.emit(
        MINI_SPRINT_STEP_COMPLETED,
        run_id=run_id,
        mini_sprint_id=mini_sprint_id,
        step_id=step_id,
        step_kind=step_kind,
        status=status,
        artifact_refs=artifact_refs or [],
        evidence_refs=evidence_refs or [],
        source_event_ids=source_event_ids or [],
        source_refs=source_refs or [],
    )


def emit_functional_acceptance_evaluated(
    events: Any,
    run_id: str,
    *,
    mini_sprint_id: str,
    criteria_results: list[dict[str, Any]] | None = None,
    passed: bool,
    blocking_findings: list[str] | None = None,
    review_artifact_ref: str | None = None,
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Emit an explicit functional acceptance result for a mini-sprint."""
    return events.emit(
        FUNCTIONAL_ACCEPTANCE_EVALUATED,
        run_id=run_id,
        mini_sprint_id=mini_sprint_id,
        criteria_results=criteria_results or [],
        passed=bool(passed),
        blocking_findings=blocking_findings or [],
        review_artifact_ref=review_artifact_ref,
        source_refs=source_refs or [],
    )
