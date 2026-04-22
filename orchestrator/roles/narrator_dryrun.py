"""Dry-run session runner for the Narrator role."""

from __future__ import annotations

import json

from orchestrator.lib.opencode import OpencodeMessage, OpencodeResult, OpencodeTokens
from orchestrator.lib.state import State


class DryRunNarratorRunner:
    """Minimal SessionRunner that returns a sourced narrator JSON payload."""

    def __init__(self, state: State) -> None:
        self._state = state
        self._counter = 0

    def run(self, prompt: str) -> OpencodeResult:
        self._counter += 1
        event_id = _first_event_id(prompt) or "event-dry-run"
        payload = {
            "title": "Narrator dry-run digest",
            "summary": "The narrator summarized the latest replay window and preserved source refs.",
            "highlights": [
                {
                    "text": "Latest event window is ready for operator review.",
                    "source_refs": [f"event:{event_id}"],
                }
            ],
            "risks": [],
            "open_questions": [],
            "next_step_hint": "Continue with the next enabled step.",
            "source_event_ids": [event_id],
            "artifact_refs": [],
        }
        message = OpencodeMessage(
            role="assistant",
            provider="dry-run",
            model="dry-run",
            tokens=OpencodeTokens(total=1, input=1, output=0),
            cost=0.0,
            text_parts=[json.dumps(payload, sort_keys=True)],
            tool_calls=[],
        )
        return OpencodeResult(
            session_id=f"ses_dryrun_narrator_{self._counter}",
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


def _first_event_id(prompt: str) -> str | None:
    marker = '"event_id": "'
    index = prompt.find(marker)
    if index < 0:
        return None
    start = index + len(marker)
    end = prompt.find('"', start)
    return prompt[start:end] if end > start else None
