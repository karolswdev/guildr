"""Dry-run session runner for the Reviewer role (H6.3c).

Mirrors :class:`orchestrator.roles.coder_dryrun.DryRunCoderRunner` but
returns the canned APPROVED review text that used to come out of the
``_DRY_RUN_REVIEWER_REPORT`` branch in ``cli/run.py``. Every dry-run
test (cli, integration, rehearsal) keeps working without each call
site hand-building a fake runner.
"""

from __future__ import annotations

from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
)
from orchestrator.lib.state import State


_DRY_RUN_REVIEW = (
    "- [PASS] Criterion: README exists\n"
    "  - Notes: verified by tester\n"
    "\n## Overall\n"
    "APPROVED\n"
)


class DryRunReviewerRunner:
    """Minimal SessionRunner that returns an APPROVED canned review."""

    _counter: int = 0

    def __init__(self, state: State) -> None:
        self._state = state

    def run(self, prompt: str) -> OpencodeResult:
        self.__class__._counter += 1
        session_id = f"ses_dryrun_reviewer_{self._counter}"
        message = OpencodeMessage(
            role="assistant",
            provider="dry-run",
            model="dry-run",
            tokens=OpencodeTokens(total=1, input=1, output=0),
            cost=0.0,
            text_parts=[_DRY_RUN_REVIEW],
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
