"""Session runner resolution for opencode-driven roles."""

from __future__ import annotations

from typing import Any, Callable

from orchestrator.lib.state import State

RunnerFactory = Callable[[State], Any]


def _architect_runner(state: State) -> Any:
    from orchestrator.roles.architect_dryrun import DryRunArchitectRunner
    return DryRunArchitectRunner(state)


def _judge_runner(state: State) -> Any:
    from orchestrator.roles.architect_dryrun import DryRunJudgeRunner
    return DryRunJudgeRunner(state)


def _coder_runner(state: State) -> Any:
    from orchestrator.roles.coder_dryrun import DryRunCoderRunner
    return DryRunCoderRunner(state)


def _tester_runner(state: State) -> Any:
    from orchestrator.roles.tester_dryrun import DryRunTesterRunner
    return DryRunTesterRunner(state)


def _reviewer_runner(state: State) -> Any:
    from orchestrator.roles.reviewer_dryrun import DryRunReviewerRunner
    return DryRunReviewerRunner(state)


def _narrator_runner(state: State) -> Any:
    from orchestrator.roles.narrator_dryrun import DryRunNarratorRunner
    return DryRunNarratorRunner(state)


def _deployer_runner(state: State) -> Any:
    from orchestrator.roles.deployer_dryrun import DryRunDeployerRunner
    return DryRunDeployerRunner(state)


DRY_RUN_RUNNER_FACTORIES: dict[str, RunnerFactory] = {
    "architect": _architect_runner,
    "judge": _judge_runner,
    "coder": _coder_runner,
    "tester": _tester_runner,
    "reviewer": _reviewer_runner,
    "narrator": _narrator_runner,
    "deployer": _deployer_runner,
}


def resolve_session_runner(
    role: str,
    *,
    state: State,
    dry_run: bool,
    session_runners: dict[str, Any],
) -> Any | None:
    """Return an injected or auto-created dry-run session runner."""
    if role in session_runners:
        return session_runners[role]
    if not dry_run:
        return None
    factory = DRY_RUN_RUNNER_FACTORIES.get(role)
    if factory is None:
        return None
    runner = factory(state)
    session_runners[role] = runner
    return runner
