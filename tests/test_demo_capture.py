"""Tests for demo capture ceremony events (A-10 slice 2)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from orchestrator.lib.demo import detect_playwright_demo_plan, emit_demo_plan
from orchestrator.lib.demo_capture import (
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_PASSED,
    DemoCaptureError,
    artifact_sha256,
    demo_dir,
    emit_demo_capture_failed,
    emit_demo_capture_started,
    emit_demo_presented,
    record_demo_artifact,
    write_demo_metadata,
)
from orchestrator.lib.events import EventBus


def _plan_event(bus: EventBus, project_dir: Path) -> dict:
    trigger = bus.emit("phase_done", name="implementation", run_id="run-1")
    plan = detect_playwright_demo_plan(
        acceptance_text="The map opens on mobile without HUD overlap.",
        evidence_text="Run `npx playwright test web/frontend/tests/demo/game-map.spec.ts`.",
        repo_has_playwright=True,
        spec_path="web/frontend/tests/demo/game-map.spec.ts",
        route="/game",
        viewports=["mobile"],
    )
    return emit_demo_plan(
        bus,
        project_dir,
        plan,
        trigger_event_id=trigger["event_id"],
        task_id="task-001",
        atom_id="implementation",
    )


def test_emit_demo_capture_started_inherits_plan_fields(tmp_path: Path) -> None:
    bus = EventBus()
    plan_event = _plan_event(bus, tmp_path)

    event = emit_demo_capture_started(
        bus,
        tmp_path,
        plan_event,
        viewport={"name": "mobile", "width": 393, "height": 852},
    )

    assert event["type"] == "demo_capture_started"
    assert event["demo_id"] == plan_event["demo_id"]
    assert event["task_id"] == "task-001"
    assert event["adapter"] == "playwright_web"
    assert event["spec_path"] == "web/frontend/tests/demo/game-map.spec.ts"
    assert event["viewport"] == {"name": "mobile", "width": 393, "height": 852}
    assert f"event:{plan_event['event_id']}" in event["source_refs"]


def test_record_demo_artifact_hashes_file_and_builds_ref(tmp_path: Path) -> None:
    bus = EventBus()
    plan_event = _plan_event(bus, tmp_path)
    capture_event = emit_demo_capture_started(bus, tmp_path, plan_event)

    artifact_dir = demo_dir(tmp_path, plan_event["demo_id"])
    artifact_file = artifact_dir / "demo.gif"
    artifact_file.write_bytes(b"GIF89a\x00fake-bytes\x00")
    expected_hash = hashlib.sha256(artifact_file.read_bytes()).hexdigest()

    event = record_demo_artifact(
        bus,
        tmp_path,
        capture_event=capture_event,
        artifact_path=artifact_file,
        kind="gif",
        test_status=CAPTURE_STATUS_PASSED,
    )

    assert event["type"] == "demo_artifact_created"
    assert event["artifact_sha256"] == expected_hash
    assert event["artifact_bytes"] == artifact_file.stat().st_size
    assert event["kind"] == "gif"
    assert event["test_status"] == "passed"
    assert event["artifact_ref"].endswith(f"demos/{plan_event['demo_id']}/demo.gif")
    assert f"event:{capture_event['event_id']}" in event["source_refs"]
    assert event["artifact_refs"] == [event["artifact_ref"]]


def test_record_demo_artifact_rejects_missing_file(tmp_path: Path) -> None:
    bus = EventBus()
    plan_event = _plan_event(bus, tmp_path)
    capture_event = emit_demo_capture_started(bus, tmp_path, plan_event)

    with pytest.raises(DemoCaptureError, match="artifact not found"):
        record_demo_artifact(
            bus,
            tmp_path,
            capture_event=capture_event,
            artifact_path=tmp_path / "nope.gif",
            kind="gif",
        )


def test_emit_demo_capture_failed_stamps_error_and_partials(tmp_path: Path) -> None:
    bus = EventBus()
    plan_event = _plan_event(bus, tmp_path)
    capture_event = emit_demo_capture_started(bus, tmp_path, plan_event)

    event = emit_demo_capture_failed(
        bus,
        tmp_path,
        capture_event=capture_event,
        error="playwright spec timed out at 30s",
        partial_artifact_refs=[".orchestrator/demos/foo/trace.zip"],
    )

    assert event["type"] == "demo_capture_failed"
    assert event["error"] == "playwright spec timed out at 30s"
    assert event["artifact_refs"] == [".orchestrator/demos/foo/trace.zip"]
    assert f"event:{capture_event['event_id']}" in event["source_refs"]


def test_emit_demo_presented_requires_artifact_refs(tmp_path: Path) -> None:
    bus = EventBus()
    plan_event = _plan_event(bus, tmp_path)
    capture_event = emit_demo_capture_started(bus, tmp_path, plan_event)

    with pytest.raises(DemoCaptureError, match="artifact_refs"):
        emit_demo_presented(bus, tmp_path, capture_event=capture_event, artifact_refs=[])


def test_emit_demo_presented_carries_summary_and_artifacts(tmp_path: Path) -> None:
    bus = EventBus()
    plan_event = _plan_event(bus, tmp_path)
    capture_event = emit_demo_capture_started(bus, tmp_path, plan_event)

    event = emit_demo_presented(
        bus,
        tmp_path,
        capture_event=capture_event,
        artifact_refs=[
            f".orchestrator/demos/{plan_event['demo_id']}/demo.gif",
            f".orchestrator/demos/{plan_event['demo_id']}/trace.zip",
        ],
        summary_ref=f".orchestrator/demos/{plan_event['demo_id']}/summary.md",
        test_status=CAPTURE_STATUS_PASSED,
    )

    assert event["type"] == "demo_presented"
    assert event["test_status"] == "passed"
    assert event["summary_ref"].endswith("summary.md")
    assert len(event["artifact_refs"]) == 2


def test_emit_demo_presented_accepts_failed_status(tmp_path: Path) -> None:
    bus = EventBus()
    plan_event = _plan_event(bus, tmp_path)
    capture_event = emit_demo_capture_started(bus, tmp_path, plan_event)

    event = emit_demo_presented(
        bus,
        tmp_path,
        capture_event=capture_event,
        artifact_refs=[f".orchestrator/demos/{plan_event['demo_id']}/trace.zip"],
        test_status=CAPTURE_STATUS_FAILED,
    )

    assert event["test_status"] == "failed"


def test_require_plan_event_rejects_mismatched_type(tmp_path: Path) -> None:
    bus = EventBus()
    plan_event = _plan_event(bus, tmp_path)

    with pytest.raises(DemoCaptureError, match="expected event type"):
        record_demo_artifact(
            bus,
            tmp_path,
            capture_event=plan_event,
            artifact_path=tmp_path / "nope.gif",
            kind="gif",
        )


def test_write_demo_metadata_serialises_deterministically(tmp_path: Path) -> None:
    demo_id = "demo_abc123"
    payload = {
        "demo_id": demo_id,
        "adapter": "playwright_web",
        "artifact_refs": [
            f".orchestrator/demos/{demo_id}/demo.gif",
            f".orchestrator/demos/{demo_id}/trace.zip",
        ],
        "test_status": "passed",
    }

    path = write_demo_metadata(tmp_path, demo_id, payload)
    again = write_demo_metadata(tmp_path, demo_id, payload)

    assert path == again
    assert path == tmp_path / ".orchestrator" / "demos" / demo_id / "metadata.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == payload


def test_artifact_sha256_matches_hashlib(tmp_path: Path) -> None:
    target = tmp_path / "file.bin"
    target.write_bytes(b"hello world" * 100)
    assert artifact_sha256(target) == hashlib.sha256(target.read_bytes()).hexdigest()


def test_capture_event_provenance_matches_wakeup_file(tmp_path: Path) -> None:
    memory_dir = tmp_path / ".orchestrator" / "memory"
    memory_dir.mkdir(parents=True)
    wakeup_body = "# wake-up\nslice-2 provenance check\n"
    (memory_dir / "wake-up.md").write_text(wakeup_body, encoding="utf-8")
    expected_hash = hashlib.sha256(wakeup_body.encode("utf-8")).hexdigest()

    bus = EventBus()
    plan_event = _plan_event(bus, tmp_path)
    capture_event = emit_demo_capture_started(bus, tmp_path, plan_event)

    assert capture_event["wake_up_hash"] == expected_hash
    assert capture_event["memory_refs"] == [".orchestrator/memory/wake-up.md"]
