"""Tests for the PWA background runner bridge."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from web.backend.routes.stream import EventStore, SimpleEventBus
from web.backend.runner import BridgingEventBus, RunRegistry, _run_orchestrator, start_run


def test_web_runner_allows_extra_architect_refine_passes(tmp_path: Path) -> None:
    """Live PWA runs should give Architect enough passes to converge."""
    captured = {}

    class FakeOrchestrator:
        def __init__(self, *, config, events, gate_registry=None, **kwargs):
            captured["config"] = config

        def run(self) -> None:
            return None

    with patch("web.backend.runner.Orchestrator", FakeOrchestrator):
        _run_orchestrator(
            "project-id",
            tmp_path,
            SimpleEventBus(),
            dry_run=True,
            llama_url="http://127.0.0.1:8080",
        )

    assert captured["config"].architect_max_passes == 5


def test_web_runner_passes_resume_step_to_engine(tmp_path: Path) -> None:
    """The PWA runner should be able to restart from a named step."""
    captured = {}

    class FakeOrchestrator:
        def __init__(self, *, config, events, gate_registry=None, **kwargs):
            return None

        def run(self, *, start_at=None) -> None:
            captured["start_at"] = start_at

    with patch("web.backend.runner.Orchestrator", FakeOrchestrator):
        _run_orchestrator(
            "project-id",
            tmp_path,
            SimpleEventBus(),
            dry_run=True,
            llama_url="http://127.0.0.1:8080",
            start_at="testing",
        )

    assert captured["start_at"] == "testing"


def test_web_runner_defaults_to_idle_rpg_mode(tmp_path: Path) -> None:
    """Runner defaults to require_human_approval=False — PWA is a touch
    surface, not a coercion. Caller must explicitly opt into gates."""
    captured = {}

    class FakeOrchestrator:
        def __init__(self, *, config, events, gate_registry=None, **kwargs):
            captured["config"] = config

        def run(self, *, start_at=None) -> None:
            return None

    with patch("web.backend.runner.Orchestrator", FakeOrchestrator):
        _run_orchestrator(
            "project-id",
            tmp_path,
            SimpleEventBus(),
            dry_run=True,
            llama_url="http://127.0.0.1:8080",
        )

    assert captured["config"].require_human_approval is False


def test_web_runner_threads_gate_opt_in_into_config(tmp_path: Path) -> None:
    """When the caller opts into gates, the flag lands in the engine's Config."""
    captured = {}

    class FakeOrchestrator:
        def __init__(self, *, config, events, gate_registry=None, **kwargs):
            captured["config"] = config

        def run(self, *, start_at=None) -> None:
            return None

    with patch("web.backend.runner.Orchestrator", FakeOrchestrator):
        _run_orchestrator(
            "project-id",
            tmp_path,
            SimpleEventBus(),
            dry_run=True,
            llama_url="http://127.0.0.1:8080",
            require_human_approval=True,
        )

    assert captured["config"].require_human_approval is True


def test_bridge_event_bus_receives_run_lifecycle_events() -> None:
    sink = SimpleEventBus(project_id="project-id")
    bridge = BridgingEventBus(sink)
    events = []

    class _Queue:
        def put_nowait(self, event):
            events.append(event)

    bridge._subscribers.append(_Queue())

    bridge.emit("run_started", project_id="project-id")
    bridge.emit("run_complete", project_id="project-id")
    bridge.emit("run_error", project_id="project-id", error="boom", kind="exception")

    assert [event["type"] for event in events] == [
        "run_started",
        "run_complete",
        "run_error",
    ]
    assert all(event["run_id"] == "project-id" for event in events)
    replay = "".join(sink.subscribe())
    assert '"type": "run_started"' in replay
    assert '"type": "run_complete"' in replay
    assert '"type": "run_error"' in replay


def test_start_run_concurrent_calls_schedule_one_thread(tmp_path: Path, monkeypatch) -> None:
    """Concurrent starts for one project must reserve one run slot."""
    registry = RunRegistry()
    run_started = threading.Event()
    release_run = threading.Event()
    run_calls: list[str] = []
    calls_lock = threading.Lock()

    def slow_resolve(project_id: str) -> Path:
        time.sleep(0.05)
        project_dir = tmp_path / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir

    def fake_run(project_id, *args, **kwargs) -> None:
        with calls_lock:
            run_calls.append(project_id)
        run_started.set()
        release_run.wait(timeout=2)

    monkeypatch.setattr("web.backend.runner._registry", registry)
    monkeypatch.setattr("web.backend.runner._resolve_project_dir", slow_resolve)
    monkeypatch.setattr("web.backend.runner._run_orchestrator", fake_run)

    event_store = EventStore()

    def attempt_start() -> bool:
        return start_run(
            "project-race",
            initial_idea="Build it.",
            dry_run=True,
            event_store=event_store,
        )

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(lambda _: attempt_start(), range(12)))

    assert results.count(True) == 1
    assert results.count(False) == 11
    assert run_started.wait(timeout=2)
    assert run_calls == ["project-race"]

    release_run.set()
