"""Tests for Coder role (H6.3a — opencode session runtime)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from orchestrator.lib.intents import create_queued_intent, intents_path
from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
    OpencodeToolCall,
)
from orchestrator.lib.state import State
from orchestrator.roles.coder import Coder, CoderError


SAMPLE_SPRINT_PLAN = """# Sprint Plan

## Overview
Test plan.

## Architecture Decisions
- Use FastAPI
- Use SQLite

## Tasks

### Task 1: Setup
- **Priority**: P0
- **Dependencies**: none
- **Files**: `app/__init__.py`

**Acceptance Criteria:**
- [ ] Module imports

**Evidence Required:**
- Run `python -c "import app"`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run


### Task 2: API
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `app/api.py`

**Acceptance Criteria:**
- [ ] Endpoint returns 200

**Evidence Required:**
- Run `python -c "from app import api"`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run


## Risks & Mitigations
1. Risk - Mitigation
"""


def _result(
    *,
    exit_code: int = 0,
    tool: str = "write",
    status: str = "completed",
    text: str = "done",
) -> OpencodeResult:
    call = OpencodeToolCall(
        tool=tool, input={"filePath": "f", "content": "c"},
        output="ok", status=status, started_ms=0, ended_ms=1,
    )
    msg = OpencodeMessage(
        role="assistant", provider="p", model="m",
        tokens=OpencodeTokens(total=1), cost=0.0,
        text_parts=[text], tool_calls=[call],
    )
    return OpencodeResult(
        session_id=f"ses_{id(call)}",
        exit_code=exit_code,
        directory="/fake",
        messages=[msg],
        total_tokens=msg.tokens,
        total_cost=0.0,
        summary_additions=1, summary_deletions=0, summary_files=1,
        raw_export={}, raw_events=[],
    )


@dataclass
class _FakeRunner:
    """Session runner that records prompts + returns canned results."""

    results: list[OpencodeResult] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    exc: Exception | None = None

    def run(self, prompt: str) -> OpencodeResult:
        self.prompts.append(prompt)
        if self.exc is not None:
            raise self.exc
        if not self.results:
            return _result()
        return self.results.pop(0)


class _Events:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event_type: str, **fields) -> None:
        self.events.append((event_type, dict(fields)))


@pytest.fixture
def state(tmp_path: Path) -> State:
    return State(tmp_path)


@pytest.fixture
def runner() -> _FakeRunner:
    return _FakeRunner()


@pytest.fixture
def coder(runner: _FakeRunner, state: State) -> Coder:
    return Coder(runner, state)


class TestTopologicalSort:
    """Tasks are processed in dependency order."""

    def test_with_dependencies(self, coder: Coder) -> None:
        from orchestrator.lib.sprint_plan import parse_tasks
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        ordered = coder._topological_sort(tasks)
        ids = [t.id for t in ordered]
        assert ids.index(1) < ids.index(2)

    def test_single_task(self, coder: Coder) -> None:
        plan = """# Sprint Plan

## Tasks

### Task 1: Only
- **Priority**: P0
- **Dependencies**: none
- **Files**: `a.py`

**Acceptance Criteria:**
- [ ] Works

**Evidence Required:**
- Run `python a.py`

**Evidence Log:**
- [ ] Done

## Risks & Mitigations
1. Risk - Mitigation
"""
        from orchestrator.lib.sprint_plan import parse_tasks
        tasks = parse_tasks(plan)
        ordered = coder._topological_sort(tasks)
        assert [t.id for t in ordered] == [1]


class TestExecute:
    """End-to-end session driving."""

    def test_spawns_one_session_per_task(
        self, coder: Coder, runner: _FakeRunner, state: State
    ) -> None:
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        runner.results = [_result(), _result()]
        result = coder.execute("sprint-plan.md")
        assert result == "sprint-plan.md"
        assert len(runner.prompts) == 2

    def test_prompt_includes_architecture_and_task(
        self, coder: Coder, runner: _FakeRunner, state: State
    ) -> None:
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        coder.execute("sprint-plan.md")
        first = runner.prompts[0]
        assert "Use FastAPI" in first  # architecture decision threaded in
        assert "Task 1: Setup" in first  # task body threaded in

    def test_prompt_intent_is_applied_once(
        self, coder: Coder, runner: _FakeRunner, state: State
    ) -> None:
        state.events = _Events()
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        create_queued_intent(
            state.project_dir,
            kind="interject",
            atom_id="implementation",
            payload={"instruction": "Prefer pathlib for file edits."},
            client_intent_id="client-1",
            intent_event_id="event-1",
        )
        runner.results = [_result(), _result()]

        coder.execute("sprint-plan.md")

        assert "Prefer pathlib for file edits." in runner.prompts[0]
        assert "Prefer pathlib for file edits." not in runner.prompts[1]
        assert state.events.events[0][0] == "operator_intent_applied"
        assert state.events.events[0][1]["client_intent_id"] == "client-1"
        rows = [
            json.loads(line)
            for line in intents_path(state.project_dir).read_text(encoding="utf-8").splitlines()
        ]
        assert rows[0]["status"] == "applied"

    def test_task_packet_preferred_over_inline_slice(
        self, coder: Coder, runner: _FakeRunner, state: State
    ) -> None:
        """phase-files/task-NNN-implement.md wins over the sprint-plan slice."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        packet_dir = state.project_dir / "phase-files"
        packet_dir.mkdir()
        (packet_dir / "task-001-implement.md").write_text(
            "PACKET BODY FOR TASK 1", encoding="utf-8"
        )
        coder.execute("sprint-plan.md")
        assert "PACKET BODY FOR TASK 1" in runner.prompts[0]

    def test_no_tasks_returns_immediately(
        self, coder: Coder, runner: _FakeRunner, state: State
    ) -> None:
        plan = "# Sprint Plan\n\n## Tasks\n\n## Risks & Mitigations\n1. Risk\n"
        state.write_file("sprint-plan.md", plan)
        assert coder.execute("sprint-plan.md") == "sprint-plan.md"
        assert runner.prompts == []

    def test_raises_when_session_exits_nonzero(
        self, coder: Coder, runner: _FakeRunner, state: State
    ) -> None:
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        runner.results = [_result(exit_code=2)]
        with pytest.raises(CoderError, match="rc=2"):
            coder.execute("sprint-plan.md")

    def test_raises_when_runner_raises(
        self, coder: Coder, runner: _FakeRunner, state: State
    ) -> None:
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        runner.exc = RuntimeError("boom")
        with pytest.raises(CoderError, match="opencode session failed"):
            coder.execute("sprint-plan.md")

    def test_raises_when_no_write_tool_call(
        self, coder: Coder, runner: _FakeRunner, state: State
    ) -> None:
        """A zero-writes session is a prompt/provider regression, not success."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        runner.results = [_result(tool="glob")]  # read-only tool, no write
        with pytest.raises(CoderError, match="without any write"):
            coder.execute("sprint-plan.md")

    def test_accepts_edit_as_valid_write(
        self, coder: Coder, runner: _FakeRunner, state: State
    ) -> None:
        """The Coder doesn't require a ``write`` specifically — ``edit``
        and ``patch`` are equally acceptable (and what real opencode uses
        for incremental changes)."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        runner.results = [_result(tool="edit"), _result(tool="patch")]
        coder.execute("sprint-plan.md")  # does not raise
