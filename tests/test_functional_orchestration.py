"""Tests for functional mini-sprint event helpers."""

from __future__ import annotations

from orchestrator.lib.functional import (
    build_demo_compatibility_gate,
    build_functional_acceptance_gate,
    build_mini_sprint_plan,
    emit_functional_acceptance_evaluated,
    emit_mini_sprint_planned,
    emit_mini_sprint_step_completed,
)


class _Events:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, **fields):
        event = {"type": event_type, **fields}
        self.events.append(event)
        return event


def test_build_mini_sprint_plan_has_replay_safe_defaults() -> None:
    plan = build_mini_sprint_plan(
        title="Ship login",
        objective="Make login usable.",
        acceptance_criteria=["User can sign in."],
        evidence_required=["pytest"],
        source_refs=["next:implementation"],
        mini_sprint_id="ms_login",
    )

    assert plan == {
        "mini_sprint_id": "ms_login",
        "title": "Ship login",
        "objective": "Make login usable.",
        "scope_refs": [],
        "acceptance_criteria": ["User can sign in."],
        "evidence_required": ["pytest"],
        "demo_requested": False,
        "demo_compatibility": "unknown",
        "source_refs": ["next:implementation"],
    }


def test_demo_compatibility_gate_threads_into_mini_sprint_plan() -> None:
    gate = build_demo_compatibility_gate(
        acceptance_criteria=["PWA map opens on mobile and shows the next move."],
        evidence_required=["Run Playwright and capture demo.gif."],
        repo_has_playwright=True,
        changed_files=["web/frontend/src/game/GameShell.ts"],
        test_command="npx playwright test web/frontend/tests/demo/game-map.spec.ts",
        spec_path="web/frontend/tests/demo/game-map.spec.ts",
        route="/game",
        viewports=["mobile"],
    )
    plan = build_mini_sprint_plan(
        title="Ship Next Move",
        objective="Make orchestration visible.",
        acceptance_criteria=["PWA map opens on mobile and shows the next move."],
        evidence_required=["Run Playwright and capture demo.gif."],
        demo_gate=gate,
        mini_sprint_id="ms_next_move",
    )

    assert gate["demo_requested"] is True
    assert gate["demo_compatibility"] == "eligible"
    assert gate["demo_confidence"] == "explicit_playwright"
    assert plan["demo_requested"] is True
    assert plan["demo_compatibility"] == "eligible"
    assert plan["demo_adapter"] == "playwright_web"
    assert plan["demo_plan"]["route"] == "/game"


def test_emit_functional_mini_sprint_events() -> None:
    events = _Events()
    plan = build_mini_sprint_plan(
        title="Ship login",
        objective="Make login usable.",
        scope_refs=["workflow:implementation"],
        acceptance_criteria=["User can sign in."],
        evidence_required=["pytest"],
        demo_requested=True,
        demo_compatibility="eligible",
        source_refs=["event:next"],
        mini_sprint_id="ms_login",
    )

    planned = emit_mini_sprint_planned(events, "run-1", plan)
    step = emit_mini_sprint_step_completed(
        events,
        "run-1",
        mini_sprint_id="ms_login",
        step_id="implementation",
        step_kind="build",
        status="done",
        artifact_refs=["app.py"],
        evidence_refs=["TEST_REPORT.md"],
        source_event_ids=["evt-phase-done"],
        source_refs=["event:evt-phase-done"],
    )
    accepted = emit_functional_acceptance_evaluated(
        events,
        "run-1",
        mini_sprint_id="ms_login",
        criteria_results=[{"criterion": "User can sign in.", "passed": True}],
        passed=True,
        blocking_findings=[],
        review_artifact_ref="REVIEW.md",
        source_refs=["artifact:REVIEW.md"],
    )

    assert planned["type"] == "mini_sprint_planned"
    assert planned["run_id"] == "run-1"
    assert planned["mini_sprint_id"] == "ms_login"
    assert step["type"] == "mini_sprint_step_completed"
    assert step["artifact_refs"] == ["app.py"]
    assert step["evidence_refs"] == ["TEST_REPORT.md"]
    assert accepted["type"] == "functional_acceptance_evaluated"
    assert accepted["passed"] is True
    assert events.events == [planned, step, accepted]


def test_functional_acceptance_gate_blocks_on_missing_evidence_and_failed_step() -> None:
    gate = build_functional_acceptance_gate(
        acceptance_criteria=["User can sign in."],
        evidence_required=["TEST_REPORT.md", "demo.gif"],
        evidence_refs=["TEST_REPORT.md"],
        step_results=[{"step_id": "testing", "status": "failed"}],
        demo_requested=True,
        demo_status="failed",
        review_findings=["Mobile viewport proof is missing."],
        review_artifact_ref="REVIEW.md",
        source_refs=["event:review"],
    )

    assert gate["passed"] is False
    assert gate["criteria_results"] == [
        {
            "criterion": "User can sign in.",
            "passed": False,
            "evidence_refs": ["TEST_REPORT.md"],
            "finding": "Blocked by required evidence or review findings.",
        }
    ]
    assert "Functional step failed: testing" in gate["blocking_findings"]
    assert "Missing evidence: demo.gif" in gate["blocking_findings"]
    assert "Demo requested but no captured or presented demo evidence is attached." in gate["blocking_findings"]
    assert gate["recommended_actions"] == ["repair_loop", "hero_review", "operator_override"]
    assert gate["review_artifact_ref"] == "REVIEW.md"
    assert gate["source_refs"] == ["event:review"]


def test_functional_acceptance_gate_can_emit_full_payload() -> None:
    events = _Events()
    gate = build_functional_acceptance_gate(
        acceptance_criteria=["Story Lens shows evidence."],
        evidence_required=["TEST_REPORT.md"],
        evidence_refs=["TEST_REPORT.md", "demo.gif"],
        demo_requested=True,
        demo_status="presented",
        demo_artifact_refs=["demo.gif"],
        review_artifact_ref="REVIEW.md",
    )

    event = emit_functional_acceptance_evaluated(
        events,
        "run-1",
        mini_sprint_id="ms_story",
        acceptance_gate=gate,
    )

    assert event["type"] == "functional_acceptance_evaluated"
    assert event["passed"] is True
    assert event["criteria_results"][0]["passed"] is True
    assert event["evidence_refs"] == ["TEST_REPORT.md", "demo.gif"]
    assert event["recommended_actions"] == []
