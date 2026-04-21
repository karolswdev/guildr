"""Dry-run session runner for the Deployer role (H6.3d).

Returns the canned DEPLOY.md text that used to come out of the
``_DRY_RUN_DEPLOY_REPORT`` branch in ``cli/run.py``.
"""

from __future__ import annotations

from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
)
from orchestrator.lib.state import State


_DRY_RUN_DEPLOY = (
    "# DEPLOY (dry-run)\n\n"
    "1. Deployment target: local\n"
    "2. Required env vars: none\n"
    "3. Manual steps: none\n"
    "4. Smoke-test commands: ls README.md\n"
)


class DryRunDeployerRunner:
    _counter: int = 0

    def __init__(self, state: State) -> None:
        self._state = state

    def run(self, prompt: str) -> OpencodeResult:
        self.__class__._counter += 1
        session_id = f"ses_dryrun_deployer_{self._counter}"
        message = OpencodeMessage(
            role="assistant",
            provider="dry-run",
            model="dry-run",
            tokens=OpencodeTokens(total=1, input=1, output=0),
            cost=0.0,
            text_parts=[_DRY_RUN_DEPLOY],
            tool_calls=[],
        )
        return OpencodeResult(
            session_id=session_id,
            exit_code=0,
            directory=str(self._state.project_dir),
            messages=[message],
            total_tokens=message.tokens,
            total_cost=0.0,
            summary_additions=0,
            summary_deletions=0,
            summary_files=0,
            raw_export={},
            raw_events=[],
        )
