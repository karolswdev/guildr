"""Dry-run session runner for the Coder role (H6.3a).

Implements :class:`orchestrator.lib.opencode.SessionRunner` without
spawning ``opencode``. Writes ``README.md`` to the project directory —
matches what ``_DRY_RUN_CODER_JSON`` did in the pre-H6.3 dry-run — and
returns a synthesised :class:`OpencodeResult` whose ``tool_calls``
contain a single completed ``write``. The engine treats this the same
as a real session, so every dry-run test (cli, integration,
rehearsal) keeps working without each call site hand-building a fake.
"""

from __future__ import annotations

from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
    OpencodeToolCall,
)
from orchestrator.lib.state import State


class DryRunCoderRunner:
    """Minimal SessionRunner that writes ``README.md`` and reports success."""

    _counter: int = 0

    def __init__(self, state: State) -> None:
        self._state = state

    def run(self, prompt: str) -> OpencodeResult:
        self.__class__._counter += 1
        session_id = f"ses_dryrun_coder_{self._counter}"
        content = "# Dry run\n"
        self._state.write_file("README.md", content)
        write_call = OpencodeToolCall(
            tool="write",
            input={"filePath": "README.md", "content": content},
            output="Wrote file successfully.",
            status="completed",
            started_ms=0,
            ended_ms=1,
        )
        message = OpencodeMessage(
            role="assistant",
            provider="dry-run",
            model="dry-run",
            tokens=OpencodeTokens(total=1, input=1, output=0),
            cost=0.0,
            text_parts=["Wrote README.md."],
            tool_calls=[write_call],
        )
        return OpencodeResult(
            session_id=session_id,
            exit_code=0,
            directory=str(self._state.project_dir),
            messages=[message],
            total_tokens=message.tokens,
            total_cost=0.0,
            summary_additions=1,
            summary_deletions=0,
            summary_files=1,
            raw_export={},
            raw_events=[],
        )
