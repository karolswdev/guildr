"""Tests for the PWA background runner bridge."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from web.backend.routes.stream import SimpleEventBus
from web.backend.runner import _run_orchestrator


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
