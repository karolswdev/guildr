"""Dry-run session runner for the Tester role (H6.3b).

Returns a canned TEST_REPORT.md matching the one-task dry-run sprint
plan emitted by ``cli/run.py:_DRY_RUN_SPRINT_PLAN`` so every dry-run
integration test advances through the testing phase without an
opencode binary.
"""

from __future__ import annotations

from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
)
from orchestrator.lib.state import State


_DRY_RUN_REPORT = (
    "# Test Report\n\n"
    "Tasks verified: 1\n\n"
    "### Task 1: bootstrap\n"
    "- Status: VERIFIED\n"
    "- Evidence 1: PASS - README.md\n"
    "- Notes: dry-run\n"
)


class DryRunTesterRunner:
    _counter: int = 0

    def __init__(self, state: State) -> None:
        self._state = state

    def run(self, prompt: str) -> OpencodeResult:
        self.__class__._counter += 1
        session_id = f"ses_dryrun_tester_{self._counter}"
        message = OpencodeMessage(
            role="assistant",
            provider="dry-run",
            model="dry-run",
            tokens=OpencodeTokens(total=1, input=1, output=0),
            cost=0.0,
            text_parts=[_DRY_RUN_REPORT],
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
