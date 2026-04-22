"""Tests for session runner resolution."""

from __future__ import annotations

from pathlib import Path

from orchestrator.lib.session_runners import (
    DRY_RUN_RUNNER_FACTORIES,
    resolve_session_runner,
)
from orchestrator.lib.state import State


def test_dry_run_runner_factory_table_covers_opencode_roles() -> None:
    assert set(DRY_RUN_RUNNER_FACTORIES) == {
        "architect",
        "judge",
        "coder",
        "tester",
        "reviewer",
        "narrator",
        "deployer",
    }


def test_resolve_session_runner_returns_injected_runner(tmp_path: Path) -> None:
    state = State(tmp_path)
    injected = object()
    runners = {"coder": injected}

    assert resolve_session_runner(
        "coder",
        state=state,
        dry_run=False,
        session_runners=runners,
    ) is injected


def test_resolve_session_runner_auto_builds_and_caches_dry_run_runner(tmp_path: Path) -> None:
    state = State(tmp_path)
    runners: dict[str, object] = {}

    first = resolve_session_runner(
        "narrator",
        state=state,
        dry_run=True,
        session_runners=runners,
    )
    second = resolve_session_runner(
        "narrator",
        state=state,
        dry_run=True,
        session_runners=runners,
    )

    assert first is not None
    assert second is first
    assert runners["narrator"] is first


def test_resolve_session_runner_returns_none_when_not_dry_run(tmp_path: Path) -> None:
    assert resolve_session_runner(
        "coder",
        state=State(tmp_path),
        dry_run=False,
        session_runners={},
    ) is None
