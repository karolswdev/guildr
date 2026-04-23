"""Functional mini-sprint event helpers."""

from __future__ import annotations

from typing import Any

from orchestrator.lib.demo import (
    DEMO_COMPATIBILITIES,
    detect_playwright_demo_plan,
    demo_compatibility_from_plan,
)
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
    demo_gate: dict[str, Any] | None = None,
    source_refs: list[str] | None = None,
    mini_sprint_id: str | None = None,
) -> dict[str, Any]:
    """Build a replay-safe functional mini-sprint plan payload."""
    sprint_id = mini_sprint_id or f"ms_{new_event_id()}"
    if demo_gate:
        demo_requested = bool(demo_gate.get("demo_requested"))
        demo_compatibility = str(demo_gate.get("demo_compatibility") or "unknown")
    if demo_compatibility not in DEMO_COMPATIBILITIES:
        demo_compatibility = "unknown"
    plan = {
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
    if demo_gate:
        plan["demo_adapter"] = str(demo_gate.get("demo_adapter") or "")
        plan["demo_confidence"] = str(demo_gate.get("demo_confidence") or "")
        plan["demo_reason"] = str(demo_gate.get("demo_reason") or "")
        plan["demo_plan"] = demo_gate.get("demo_plan") if isinstance(demo_gate.get("demo_plan"), dict) else {}
    return plan


def build_demo_compatibility_gate(
    *,
    acceptance_criteria: list[str] | None = None,
    evidence_required: list[str] | None = None,
    operator_requested: bool = False,
    repo_has_playwright: bool = False,
    changed_files: list[str] | None = None,
    start_command: str | None = None,
    test_command: str | None = None,
    spec_path: str | None = None,
    route: str | None = None,
    viewports: list[str] | None = None,
    capture_policy: list[str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic mini-sprint demo compatibility gate."""
    plan = detect_playwright_demo_plan(
        acceptance_text="\n".join(acceptance_criteria or []),
        evidence_text="\n".join(evidence_required or []),
        operator_requested=operator_requested,
        repo_has_playwright=repo_has_playwright,
        changed_files=changed_files,
        start_command=start_command,
        test_command=test_command,
        spec_path=spec_path,
        route=route,
        viewports=viewports,
        capture_policy=capture_policy,
    )
    compatibility = demo_compatibility_from_plan(plan)
    return {
        "demo_requested": compatibility == "eligible",
        "demo_compatibility": compatibility,
        "demo_adapter": plan["adapter"],
        "demo_confidence": plan["confidence"],
        "demo_reason": plan["reason"],
        "demo_plan": plan,
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


def build_functional_acceptance_gate(
    *,
    acceptance_criteria: list[str] | None = None,
    evidence_required: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    step_results: list[dict[str, Any]] | None = None,
    criteria_results: list[dict[str, Any]] | None = None,
    review_findings: list[str] | None = None,
    review_artifact_ref: str | None = None,
    demo_requested: bool = False,
    demo_status: str | None = None,
    demo_artifact_refs: list[str] | None = None,
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic functional acceptance gate payload."""
    criteria = _clean_strings(acceptance_criteria)
    required = _clean_strings(evidence_required)
    evidence = _dedupe([*_clean_strings(evidence_refs), *_clean_strings(demo_artifact_refs)])
    blockers: list[str] = []

    if not criteria:
        blockers.append("No acceptance criteria declared.")

    for item in step_results or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip().lower()
        if status == "failed":
            step_id = str(item.get("step_id") or item.get("step") or "step").strip()
            blockers.append(f"Functional step failed: {step_id}")

    for expected in required:
        if not _evidence_matches(expected, evidence):
            blockers.append(f"Missing evidence: {expected}")

    for finding in _clean_strings(review_findings):
        blockers.append(finding)

    if demo_requested and demo_status not in {"captured", "presented"} and not demo_artifact_refs:
        blockers.append("Demo requested but no captured or presented demo evidence is attached.")

    normalized_criteria = _normalize_criteria_results(criteria_results, criteria, evidence, blockers)
    for result in normalized_criteria:
        if result.get("passed") is False:
            finding = str(result.get("finding") or result.get("criterion") or "Acceptance criterion failed.").strip()
            if finding and finding not in blockers:
                blockers.append(finding)

    passed = len(blockers) == 0 and all(result.get("passed") is True for result in normalized_criteria)
    recommended_actions = [] if passed else ["repair_loop", "hero_review", "operator_override"]
    return {
        "criteria_results": normalized_criteria,
        "passed": passed,
        "blocking_findings": _dedupe(blockers),
        "review_artifact_ref": review_artifact_ref,
        "evidence_refs": evidence,
        "recommended_actions": recommended_actions,
        "source_refs": _clean_strings(source_refs),
    }


def emit_functional_acceptance_evaluated(
    events: Any,
    run_id: str,
    *,
    mini_sprint_id: str,
    criteria_results: list[dict[str, Any]] | None = None,
    passed: bool = False,
    blocking_findings: list[str] | None = None,
    review_artifact_ref: str | None = None,
    evidence_refs: list[str] | None = None,
    recommended_actions: list[str] | None = None,
    acceptance_gate: dict[str, Any] | None = None,
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Emit an explicit functional acceptance result for a mini-sprint."""
    if acceptance_gate:
        criteria_results = acceptance_gate.get("criteria_results") if isinstance(acceptance_gate.get("criteria_results"), list) else criteria_results
        passed = bool(acceptance_gate.get("passed"))
        blocking_findings = acceptance_gate.get("blocking_findings") if isinstance(acceptance_gate.get("blocking_findings"), list) else blocking_findings
        review_artifact_ref = acceptance_gate.get("review_artifact_ref") or review_artifact_ref
        evidence_refs = acceptance_gate.get("evidence_refs") if isinstance(acceptance_gate.get("evidence_refs"), list) else evidence_refs
        recommended_actions = acceptance_gate.get("recommended_actions") if isinstance(acceptance_gate.get("recommended_actions"), list) else recommended_actions
        source_refs = acceptance_gate.get("source_refs") if isinstance(acceptance_gate.get("source_refs"), list) else source_refs
    return events.emit(
        FUNCTIONAL_ACCEPTANCE_EVALUATED,
        run_id=run_id,
        mini_sprint_id=mini_sprint_id,
        criteria_results=criteria_results or [],
        passed=bool(passed),
        blocking_findings=blocking_findings or [],
        review_artifact_ref=review_artifact_ref,
        evidence_refs=evidence_refs or [],
        recommended_actions=recommended_actions or [],
        source_refs=source_refs or [],
    )


def _clean_strings(values: list[str] | None) -> list[str]:
    return [value.strip() for value in values or [] if isinstance(value, str) and value.strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _evidence_matches(expected: str, evidence_refs: list[str]) -> bool:
    expected_lower = expected.lower()
    return any(expected_lower in ref.lower() or ref.lower() in expected_lower for ref in evidence_refs)


def _normalize_criteria_results(
    criteria_results: list[dict[str, Any]] | None,
    criteria: list[str],
    evidence_refs: list[str],
    blockers: list[str],
) -> list[dict[str, Any]]:
    if criteria_results:
        out: list[dict[str, Any]] = []
        for item in criteria_results:
            if not isinstance(item, dict):
                continue
            criterion = str(item.get("criterion") or "").strip()
            if not criterion:
                continue
            out.append({
                "criterion": criterion,
                "passed": item.get("passed") is True,
                "evidence_refs": _clean_strings(item.get("evidence_refs") if isinstance(item.get("evidence_refs"), list) else []),
                "finding": str(item.get("finding") or "").strip(),
            })
        return out
    return [
        {
            "criterion": criterion,
            "passed": len(blockers) == 0,
            "evidence_refs": evidence_refs,
            "finding": "" if len(blockers) == 0 else "Blocked by required evidence or review findings.",
        }
        for criterion in criteria
    ]
