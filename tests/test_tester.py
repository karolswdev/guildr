"""Tests for the Tester role on the opencode session runtime (H6.3b)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
)
from orchestrator.lib.state import State
from orchestrator.roles.tester import Tester, TesterError


SAMPLE_SPRINT_PLAN = """# Sprint Plan

## Tasks

### Task 1: Setup
- **Priority**: P0
- **Dependencies**: none
- **Files**: `app/__init__.py`

**Acceptance Criteria:**
- [ ] Module imports

**Evidence Required:**
- Run `ls app/__init__.py`

**Evidence Log:**
- [ ] check pending


### Task 2: API
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `app/api.py`

**Acceptance Criteria:**
- [ ] Endpoint returns 200

**Evidence Required:**
- Run `ls app/api.py`

**Evidence Log:**
- [ ] check pending


## Risks & Mitigations
1. Risk - Mitigation
"""


def _result(text: str, *, exit_code: int = 0) -> OpencodeResult:
    message = OpencodeMessage(
        role="assistant",
        provider="fake",
        model="fake",
        tokens=OpencodeTokens(total=1, input=1, output=0),
        cost=0.0,
        text_parts=[text],
        tool_calls=[],
    )
    return OpencodeResult(
        session_id="ses_test",
        exit_code=exit_code,
        directory=".",
        messages=[message] if text else [],
        total_tokens=message.tokens,
        total_cost=0.0,
        summary_additions=0,
        summary_deletions=0,
        summary_files=0,
        raw_export={},
        raw_events=[],
    )


@dataclass
class _FakeRunner:
    result: OpencodeResult | None = None
    exc: Exception | None = None
    prompts: list[str] = field(default_factory=list)

    def run(self, prompt: str) -> OpencodeResult:
        self.prompts.append(prompt)
        if self.exc is not None:
            raise self.exc
        assert self.result is not None
        return self.result


@pytest.fixture
def state(tmp_path):
    return State(tmp_path)


@pytest.fixture
def runner():
    return _FakeRunner()


@pytest.fixture
def tester(runner, state):
    return Tester(runner, state)


# ---------------------------------------------------------------------------
# _extract_commands / _command_validation_error (static, no session needed)
# ---------------------------------------------------------------------------


class TestExtractCommands:
    def test_picks_run_backtick(self):
        cmds = Tester._extract_commands(["- Run `ls README.md`"])
        assert cmds == [{"label": "- Run `ls README.md`", "command": "ls README.md"}]

    def test_accepts_git_diff_line(self):
        cmds = Tester._extract_commands(["git diff --stat"])
        assert cmds[0]["command"] == "git diff --stat"

    def test_accepts_known_command_prefix_in_backticks(self):
        cmds = Tester._extract_commands(["- Verify with `pytest -q`"])
        assert cmds[0]["command"] == "pytest -q"

    def test_skips_manual_verification_without_run(self):
        assert Tester._extract_commands(["- Manual verification required"]) == []

    def test_skips_prose_without_command(self):
        assert Tester._extract_commands(["- Check that it looks right"]) == []


class TestCommandValidation:
    def test_flags_npm_run_dev(self):
        err = Tester._command_validation_error("npm run dev")
        assert err and "long-running dev server" in err

    def test_accepts_pytest(self):
        assert Tester._command_validation_error("pytest -q") is None

    def test_flags_uvicorn(self):
        assert Tester._command_validation_error("uvicorn app:app") is not None


# ---------------------------------------------------------------------------
# _render_tasks_for_prompt
# ---------------------------------------------------------------------------


class TestRenderTasksForPrompt:
    def test_includes_task_id_and_commands(self, tester, state):
        from orchestrator.lib.sprint_plan import parse_tasks
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        block = Tester._render_tasks_for_prompt(tasks)
        assert "### Task 1: Setup" in block
        assert "ls app/__init__.py" in block
        assert "### Task 2: API" in block

    def test_flags_missing_commands(self):
        from orchestrator.lib.sprint_plan import parse_tasks
        plan = SAMPLE_SPRINT_PLAN.replace("- Run `ls app/__init__.py`", "- Manual verification required")
        tasks = parse_tasks(plan)
        block = Tester._render_tasks_for_prompt(tasks)
        assert "RERUN_FAILED" in block

    def test_flags_dev_server_commands(self):
        from orchestrator.lib.sprint_plan import parse_tasks
        plan = SAMPLE_SPRINT_PLAN.replace("- Run `ls app/__init__.py`", "- Run `npm run dev`")
        tasks = parse_tasks(plan)
        block = Tester._render_tasks_for_prompt(tasks)
        assert "long-running dev server" in block


# ---------------------------------------------------------------------------
# execute — opencode-driven path
# ---------------------------------------------------------------------------


class TestExecute:
    def test_writes_test_report_from_assistant_text(self, tester, runner, state):
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        report = (
            "# Test Report\n\nTasks verified: 2\n\n"
            "### Task 1: Setup\n- Status: VERIFIED\n- Evidence 1: PASS - ok\n\n"
            "### Task 2: API\n- Status: VERIFIED\n- Evidence 1: PASS - ok\n"
        )
        runner.result = _result(report)
        path = tester.execute("sprint-plan.md")
        assert path == "TEST_REPORT.md"
        assert state.read_file("TEST_REPORT.md") == report.strip()
        assert len(runner.prompts) == 1

    def test_prompt_includes_task_commands(self, tester, runner, state):
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        runner.result = _result("# Test Report\n")
        tester.execute("sprint-plan.md")
        prompt = runner.prompts[0]
        assert "ls app/__init__.py" in prompt
        assert "ls app/api.py" in prompt

    def test_no_tasks_short_circuits(self, tester, runner, state):
        state.write_file("sprint-plan.md", "# Sprint Plan\n\n## Tasks\n\n")
        path = tester.execute("sprint-plan.md")
        assert path == "TEST_REPORT.md"
        assert "Tasks verified: 0" in state.read_file("TEST_REPORT.md")
        # Runner is never invoked when there are no tasks.
        assert runner.prompts == []

    def test_runner_exception_is_wrapped(self, tester, runner, state):
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        runner.exc = RuntimeError("boom")
        with pytest.raises(TesterError, match="opencode session failed"):
            tester.execute("sprint-plan.md")

    def test_non_zero_exit_raises(self, tester, runner, state):
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        runner.result = _result("partial", exit_code=3)
        with pytest.raises(TesterError, match="rc=3"):
            tester.execute("sprint-plan.md")

    def test_empty_assistant_text_raises(self, tester, runner, state):
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        runner.result = _result("")
        with pytest.raises(TesterError, match="no assistant text"):
            tester.execute("sprint-plan.md")

    def test_emits_audit_entries(self, tester, runner, state):
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        runner.result = _result("# Test Report\n\nTasks verified: 0\n")
        tester.execute("sprint-plan.md")
        raw_path = state.project_dir / ".orchestrator" / "logs" / "raw-io.jsonl"
        usage_path = state.project_dir / ".orchestrator" / "logs" / "usage.jsonl"
        assert raw_path.exists()
        assert usage_path.exists()
        assert "tester" in raw_path.read_text(encoding="utf-8")

    def test_audit_fires_even_on_non_zero_exit(self, tester, runner, state):
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        runner.result = _result("partial", exit_code=2)
        with pytest.raises(TesterError):
            tester.execute("sprint-plan.md")
        raw_path = state.project_dir / ".orchestrator" / "logs" / "raw-io.jsonl"
        assert raw_path.exists()
        assert "tester" in raw_path.read_text(encoding="utf-8")
