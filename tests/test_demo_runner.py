"""Tests for the demo runner (A-10 slice 2b)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

from orchestrator.lib.demo import detect_playwright_demo_plan, emit_demo_plan
from orchestrator.lib.demo_runner import (
    DemoRunner,
    DemoRunnerError,
    RunnerDeps,
)
from orchestrator.lib.events import EventBus


class _RecordingBus:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self._inner = EventBus()

    def emit(self, type: str, **fields) -> dict:
        event = self._inner.emit(type, **fields)
        self.events.append(event)
        return event

    def of_type(self, type: str) -> list[dict]:
        return [event for event in self.events if event.get("type") == type]


class _ServerHandle:
    def __init__(self) -> None:
        self.terminated = 0

    def terminate(self) -> None:
        self.terminated += 1


def _make_plan_event(bus: _RecordingBus, project_dir: Path, **overrides) -> dict:
    trigger = bus.emit("phase_done", name="implementation", run_id="run-a10")
    plan = detect_playwright_demo_plan(
        acceptance_text="The map opens on mobile without HUD overlap.",
        evidence_text="Run `npx playwright test demo/game-map.spec.ts`.",
        repo_has_playwright=True,
        start_command=overrides.pop("start_command", "npm run dev -- --host 127.0.0.1"),
        test_command=overrides.pop("test_command", "npx playwright test demo/game-map.spec.ts"),
        spec_path="demo/game-map.spec.ts",
        route=overrides.pop("route", "/game"),
        viewports=["mobile"],
    )
    return emit_demo_plan(
        bus,
        project_dir,
        plan,
        trigger_event_id=trigger["event_id"],
        task_id=overrides.pop("task_id", "task-a10"),
        atom_id="implementation",
    )


def _fake_deps(
    *,
    artifact_source_dir: Path,
    drop_artifacts: dict[str, bytes],
    server_ready: bool = True,
    test_exit_code: int = 0,
    log_tail: str = "",
) -> tuple[RunnerDeps, dict[str, object]]:
    handle = _ServerHandle()
    ledger: dict[str, object] = {"server_handle": handle, "probe_calls": [], "test_calls": []}

    def start_server(command: str, cwd: Path):  # noqa: ARG001
        ledger["server_command"] = command
        return handle

    def probe_ready(url: str, timeout_s: float) -> bool:  # noqa: ARG001
        calls: list = ledger["probe_calls"]  # type: ignore[assignment]
        calls.append(url)
        return server_ready

    def run_test(command: str, cwd: Path, timeout_s: float) -> tuple[int, str]:  # noqa: ARG001
        calls: list = ledger["test_calls"]  # type: ignore[assignment]
        calls.append(command)
        artifact_source_dir.mkdir(parents=True, exist_ok=True)
        for name, payload in drop_artifacts.items():
            (artifact_source_dir / name).write_bytes(payload)
        return (test_exit_code, log_tail)

    return (
        RunnerDeps(start_server=start_server, probe_ready=probe_ready, run_test=run_test),
        ledger,
    )


def test_runner_drives_full_success_lifecycle(tmp_path: Path) -> None:
    bus = _RecordingBus()
    plan_event = _make_plan_event(bus, tmp_path)

    source_dir = tmp_path / "pw-output"
    deps, ledger = _fake_deps(
        artifact_source_dir=source_dir,
        drop_artifacts={
            "demo.gif": b"GIF89a\x00stub",
            "interaction.webm": b"WEBM\x00stub",
            "trace.zip": b"ZIP\x00stub",
            "mobile.png": b"PNG\x00stub",
        },
        log_tail="2 passed",
    )

    runner = DemoRunner(bus, tmp_path, deps=deps)
    terminal = runner.run(
        plan_event,
        artifact_source_dir=source_dir,
        viewport={"name": "mobile", "width": 393, "height": 852},
    )

    assert terminal["type"] == "demo_presented"
    assert terminal["test_status"] == "passed"
    assert len(terminal["artifact_refs"]) >= 4

    started = bus.of_type("demo_capture_started")
    artifacts = bus.of_type("demo_artifact_created")
    presented = bus.of_type("demo_presented")
    assert len(started) == 1
    assert len(artifacts) == 4
    assert len(presented) == 1
    assert bus.of_type("demo_capture_failed") == []

    kinds = sorted(event["kind"] for event in artifacts)
    assert kinds == ["gif", "screenshot", "trace", "webm"]

    metadata_path = tmp_path / ".orchestrator" / "demos" / plan_event["demo_id"] / "metadata.json"
    assert metadata_path.exists()
    loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert loaded["demo_id"] == plan_event["demo_id"]
    assert loaded["test_status"] == "passed"
    assert loaded["plan_event_id"] == plan_event["event_id"]
    assert loaded["capture_event_id"] == started[0]["event_id"]
    assert loaded["artifact_refs"] == terminal["artifact_refs"]

    handle: _ServerHandle = ledger["server_handle"]  # type: ignore[assignment]
    assert handle.terminated == 1


def test_runner_emits_failed_when_test_exits_nonzero(tmp_path: Path) -> None:
    bus = _RecordingBus()
    plan_event = _make_plan_event(bus, tmp_path)

    source_dir = tmp_path / "pw-output"
    deps, ledger = _fake_deps(
        artifact_source_dir=source_dir,
        drop_artifacts={"trace.zip": b"partial"},
        test_exit_code=1,
        log_tail="AssertionError: bad selector",
    )

    runner = DemoRunner(bus, tmp_path, deps=deps)
    terminal = runner.run(plan_event, artifact_source_dir=source_dir)

    assert terminal["type"] == "demo_capture_failed"
    assert "exit" in terminal["error"] or "AssertionError" in terminal["error"]
    assert terminal["artifact_refs"]
    assert bus.of_type("demo_presented") == []

    handle: _ServerHandle = ledger["server_handle"]  # type: ignore[assignment]
    assert handle.terminated == 1


def test_runner_emits_failed_when_server_never_ready(tmp_path: Path) -> None:
    bus = _RecordingBus()
    plan_event = _make_plan_event(bus, tmp_path)

    source_dir = tmp_path / "pw-output"
    deps, ledger = _fake_deps(
        artifact_source_dir=source_dir,
        drop_artifacts={},
        server_ready=False,
    )

    runner = DemoRunner(bus, tmp_path, deps=deps)
    terminal = runner.run(plan_event, artifact_source_dir=source_dir)

    assert terminal["type"] == "demo_capture_failed"
    assert "did not become ready" in terminal["error"]
    assert ledger["test_calls"] == []
    assert bus.of_type("demo_artifact_created") == []

    handle: _ServerHandle = ledger["server_handle"]  # type: ignore[assignment]
    assert handle.terminated == 1


def test_runner_skips_probe_when_no_start_command(tmp_path: Path) -> None:
    bus = _RecordingBus()
    plan_event = _make_plan_event(bus, tmp_path, start_command="")

    source_dir = tmp_path / "pw-output"
    deps, ledger = _fake_deps(
        artifact_source_dir=source_dir,
        drop_artifacts={"demo.gif": b"GIF"},
    )

    runner = DemoRunner(bus, tmp_path, deps=deps)
    terminal = runner.run(plan_event, artifact_source_dir=source_dir)

    assert terminal["type"] == "demo_presented"
    assert ledger["probe_calls"] == []
    assert "server_command" not in ledger


def test_runner_requires_test_command(tmp_path: Path) -> None:
    bus = _RecordingBus()
    plan_event = _make_plan_event(bus, tmp_path, test_command="")

    runner = DemoRunner(bus, tmp_path)
    with pytest.raises(DemoRunnerError, match="test_command"):
        runner.run(plan_event, artifact_source_dir=tmp_path / "pw-output")


def test_runner_rejects_non_plan_event(tmp_path: Path) -> None:
    bus = _RecordingBus()
    bogus = bus.emit("phase_done", name="implementation", run_id="run-x")
    runner = DemoRunner(bus, tmp_path)
    with pytest.raises(DemoRunnerError, match="demo_planned"):
        runner.run(bogus, artifact_source_dir=tmp_path / "pw-output")


def test_runner_terminates_server_even_when_runtime_raises(tmp_path: Path) -> None:
    bus = _RecordingBus()
    plan_event = _make_plan_event(bus, tmp_path)

    handle = _ServerHandle()

    def start_server(command: str, cwd: Path) -> _ServerHandle:  # noqa: ARG001
        return handle

    def probe_ready(url: str, timeout_s: float) -> bool:  # noqa: ARG001
        return True

    def run_test(command: str, cwd: Path, timeout_s: float) -> tuple[int, str]:
        raise RuntimeError("boom")

    deps = RunnerDeps(start_server=start_server, probe_ready=probe_ready, run_test=run_test)
    runner = DemoRunner(bus, tmp_path, deps=deps)
    terminal = runner.run(plan_event, artifact_source_dir=tmp_path / "pw-output")

    assert terminal["type"] == "demo_capture_failed"
    assert "RuntimeError" in terminal["error"] and "boom" in terminal["error"]
    assert handle.terminated == 1


def test_runner_artifact_patterns_override_capture_policy(tmp_path: Path) -> None:
    bus = _RecordingBus()
    plan_event = _make_plan_event(bus, tmp_path)

    source_dir = tmp_path / "pw-output"
    deps, _ledger = _fake_deps(
        artifact_source_dir=source_dir,
        drop_artifacts={
            "only.mp4": b"MP4",
            "ignored.gif": b"GIF",
        },
    )

    runner = DemoRunner(bus, tmp_path, deps=deps)
    runner.run(
        plan_event,
        artifact_source_dir=source_dir,
        artifact_patterns=[("video", "*.mp4")],
    )

    artifacts = bus.of_type("demo_artifact_created")
    assert len(artifacts) == 1
    assert artifacts[0]["kind"] == "video"
    assert artifacts[0]["artifact_ref"].endswith("only.mp4")


def test_runner_default_probe_url_uses_localhost_when_route_missing_scheme(tmp_path: Path) -> None:
    bus = _RecordingBus()
    plan_event = _make_plan_event(bus, tmp_path, route="/game")

    source_dir = tmp_path / "pw-output"
    deps, ledger = _fake_deps(
        artifact_source_dir=source_dir,
        drop_artifacts={"demo.gif": b"GIF"},
    )

    runner = DemoRunner(bus, tmp_path, deps=deps)
    runner.run(plan_event, artifact_source_dir=source_dir)

    probe_calls: list[str] = ledger["probe_calls"]  # type: ignore[assignment]
    assert probe_calls and probe_calls[0].startswith("http://127.0.0.1:5173")
    assert probe_calls[0].endswith("/game")
