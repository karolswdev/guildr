"""Dry-run session runners for the Architect + Judge roles (H6.3e).

Each runner returns a canned ``OpencodeResult`` so dry-run pipelines
can exercise the opencode-agent code path without an opencode binary.
The sprint-plan and judge-JSON payloads mirror the content-aware
fake previously served by ``cli/run.py:_build_dry_run_llm``.
"""

from __future__ import annotations

from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
)
from orchestrator.lib.state import State


_DRY_RUN_SPRINT_PLAN = (
    "# Sprint Plan (dry-run)\n\n"
    "## Overview\n"
    "Dry-run uses a single tiny slice that still preserves traceability.\n\n"
    "## Memory Tiers\n"
    "- **Global Memory:** dry-run stays self-contained and verifier-safe.\n"
    "- **Sprint Memory:** produce one README artifact and verify it from the shell.\n"
    "- **Task Packet Memory:** remember the target file, evidence command, and expected output.\n\n"
    "## Traceability Matrix\n"
    "- `REQ-1` -> Task 1\n"
    "- `RISK-1` -> Task 1\n\n"
    "## Architecture Decisions\n"
    "- Keep dry-run self-contained.\n\n"
    "## Tasks\n\n"
    "### Task 1: bootstrap\n"
    "- **Priority**: P0\n"
    "- **Dependencies**: none\n"
    "- **Files**: `README.md`\n\n"
    "**Acceptance Criteria:**\n"
    "- [ ] README exists\n\n"
    "**Evidence Required:**\n"
    "- Run `ls README.md`\n\n"
    "**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)\n"
    "- [ ] README.md check pending\n\n"
    "**Implementation Notes:**\n"
    "Source Requirements: `REQ-1`, `RISK-1`\n"
    "Task Memory: Create README.md and keep verification bounded to a single ls command.\n"
    "Determinism Notes: Only README.md may change; verifier expects README.md to exist.\n\n"
    "## Risks & Mitigations\n"
    "1. None - dry-run fixture only.\n"
)

_DRY_RUN_JUDGE_JSON = (
    '{"specificity":{"score":1,"issues":[]},'
    '"testability":{"score":1,"issues":[]},'
    '"evidence":{"score":1,"issues":[]},'
    '"completeness":{"score":1,"issues":[]},'
    '"feasibility":{"score":1,"issues":[]},'
    '"risk":{"score":1,"issues":[]}}'
)


def _canned_result(text: str, session_id: str, directory: str) -> OpencodeResult:
    message = OpencodeMessage(
        role="assistant",
        provider="dry-run",
        model="dry-run",
        tokens=OpencodeTokens(total=1, input=1, output=0),
        cost=0.0,
        text_parts=[text],
        tool_calls=[],
    )
    return OpencodeResult(
        session_id=session_id,
        exit_code=0,
        directory=directory,
        messages=[message],
        total_tokens=message.tokens,
        total_cost=0.0,
        summary_additions=0,
        summary_deletions=0,
        summary_files=0,
        raw_export={},
        raw_events=[],
    )


class DryRunArchitectRunner:
    _counter: int = 0

    def __init__(self, state: State) -> None:
        self._state = state

    def run(self, prompt: str) -> OpencodeResult:
        self.__class__._counter += 1
        return _canned_result(
            _DRY_RUN_SPRINT_PLAN,
            f"ses_dryrun_architect_{self.__class__._counter}",
            str(self._state.project_dir),
        )


class DryRunJudgeRunner:
    _counter: int = 0

    def __init__(self, state: State) -> None:
        self._state = state

    def run(self, prompt: str) -> OpencodeResult:
        self.__class__._counter += 1
        return _canned_result(
            _DRY_RUN_JUDGE_JSON,
            f"ses_dryrun_judge_{self.__class__._counter}",
            str(self._state.project_dir),
        )
