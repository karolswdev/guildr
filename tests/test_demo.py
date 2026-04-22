"""Tests for demo ceremony planning (A-10 slice 1)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from orchestrator.lib.demo import (
    ADAPTER_PLAYWRIGHT,
    CONFIDENCE_EXPLICIT,
    CONFIDENCE_INFERRED,
    CONFIDENCE_NONE,
    CONFIDENCE_OPERATOR,
    CONFIDENCE_STATIC,
    DemoPlanError,
    detect_playwright_demo_plan,
    emit_demo_plan,
)
from orchestrator.lib.events import EventBus


def test_detect_explicit_playwright_from_evidence_text() -> None:
    plan = detect_playwright_demo_plan(
        acceptance_text="The map opens on mobile without HUD overlap.",
        evidence_text="Run `npx playwright test web/frontend/tests/demo/game-map.spec.ts`.",
        repo_has_playwright=True,
        changed_files=["web/frontend/src/views/Map.ts"],
        start_command="npm run dev -- --host 127.0.0.1",
        test_command="npx playwright test web/frontend/tests/demo/game-map.spec.ts",
        spec_path="web/frontend/tests/demo/game-map.spec.ts",
        route="/game",
        viewports=["mobile"],
    )

    assert plan["adapter"] == ADAPTER_PLAYWRIGHT
    assert plan["confidence"] == CONFIDENCE_EXPLICIT
    assert plan["route"] == "/game"
    assert plan["viewports"] == ["mobile"]
    assert plan["capture_policy"] == ["gif", "webm", "trace", "screenshot"]


def test_detect_inferred_interactive_when_frontend_changed() -> None:
    plan = detect_playwright_demo_plan(
        acceptance_text="Story Lens shows a demo card near the producing atom.",
        evidence_text="uv run pytest -q web/frontend/tests/test_event_engine.py",
        repo_has_playwright=False,
        changed_files=["web/frontend/src/game/EventEngine.ts"],
    )

    assert plan["confidence"] == CONFIDENCE_INFERRED


def test_detect_operator_requested_overrides_missing_keywords() -> None:
    plan = detect_playwright_demo_plan(
        acceptance_text="Backend-only refactor with no UI surface.",
        operator_requested=True,
    )

    assert plan["confidence"] == CONFIDENCE_OPERATOR


def test_detect_static_visual_when_only_screenshot_keyword_present() -> None:
    plan = detect_playwright_demo_plan(
        acceptance_text="Attach a screenshot of the generated report.",
    )

    assert plan["confidence"] == CONFIDENCE_STATIC


def test_detect_not_demoable_for_pure_backend_work() -> None:
    plan = detect_playwright_demo_plan(
        acceptance_text="Refactor the event bus to prune failed subscribers.",
        evidence_text="uv run pytest -q web/backend/tests/test_stream.py",
    )

    assert plan["confidence"] == CONFIDENCE_NONE


def test_emit_demo_planned_stamps_provenance_and_ids(tmp_path: Path) -> None:
    memory_dir = tmp_path / ".orchestrator" / "memory"
    memory_dir.mkdir(parents=True)
    wakeup_body = "# wake-up\nproject context\n"
    (memory_dir / "wake-up.md").write_text(wakeup_body, encoding="utf-8")
    expected_hash = hashlib.sha256(wakeup_body.encode("utf-8")).hexdigest()

    bus = EventBus()
    trigger = bus.emit("phase_done", name="implementation", run_id="run-1")
    plan = detect_playwright_demo_plan(
        acceptance_text="The map opens on mobile without HUD overlap.",
        evidence_text="Run the Playwright map spec and capture the mobile GIF.",
        repo_has_playwright=True,
        spec_path="web/frontend/tests/demo/game-map.spec.ts",
        route="/game",
        viewports=["mobile"],
    )

    event = emit_demo_plan(
        bus,
        tmp_path,
        plan,
        trigger_event_id=trigger["event_id"],
        task_id="task-001",
        atom_id="implementation",
        source_refs=["artifact:sprint-plan.md"],
    )

    assert event["type"] == "demo_planned"
    assert event["adapter"] == ADAPTER_PLAYWRIGHT
    assert event["confidence"] == CONFIDENCE_EXPLICIT
    assert event["task_id"] == "task-001"
    assert event["route"] == "/game"
    assert event["viewports"] == ["mobile"]
    assert event["wake_up_hash"] == expected_hash
    assert event["memory_refs"] == [".orchestrator/memory/wake-up.md"]
    assert event["demo_id"].startswith("demo_")
    assert f"event:{trigger['event_id']}" in event["source_refs"]
    assert "artifact:sprint-plan.md" in event["source_refs"]


def test_emit_demo_plan_is_idempotent_for_same_trigger(tmp_path: Path) -> None:
    bus = EventBus()
    trigger = bus.emit("phase_done", name="implementation", run_id="run-1")
    plan = detect_playwright_demo_plan(
        acceptance_text="Demo the game map.",
        evidence_text="Run the Playwright map spec.",
        repo_has_playwright=True,
        spec_path="web/frontend/tests/demo/game-map.spec.ts",
    )

    first = emit_demo_plan(bus, tmp_path, plan, trigger_event_id=trigger["event_id"], task_id="task-001")
    second = emit_demo_plan(bus, tmp_path, plan, trigger_event_id=trigger["event_id"], task_id="task-001")

    assert first["demo_id"] == second["demo_id"]


def test_emit_demo_skipped_when_not_demoable(tmp_path: Path) -> None:
    bus = EventBus()
    trigger = bus.emit("phase_done", name="refactor", run_id="run-1")
    plan = detect_playwright_demo_plan(
        acceptance_text="Refactor the event bus.",
    )

    event = emit_demo_plan(bus, tmp_path, plan, trigger_event_id=trigger["event_id"], atom_id="refactor")

    assert event["type"] == "demo_skipped"
    assert event["confidence"] == CONFIDENCE_NONE
    assert "no runnable visual surface" in event["reason"]


def test_emit_demo_plan_rejects_missing_trigger(tmp_path: Path) -> None:
    bus = EventBus()
    plan = detect_playwright_demo_plan(acceptance_text="Demo the thing.", evidence_text="Playwright.")

    with pytest.raises(DemoPlanError, match="trigger_event_id"):
        emit_demo_plan(bus, tmp_path, plan, trigger_event_id="", task_id="task-001")
