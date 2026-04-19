"""Tests for Tester role."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.lib.llm import LLMClient, LLMResponse
from orchestrator.lib.state import State
from orchestrator.roles.tester import (
    TaskResult,
    Tester,
    TesterError,
)

# ---------------------------------------------------------------------------
# Sample sprint plan with filled evidence logs
# ---------------------------------------------------------------------------

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
- [x] Test command run, output recorded: ```success```
- [x] Module imported


### Task 2: API
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `app/api.py`

**Acceptance Criteria:**
- [ ] Endpoint returns 200

**Evidence Required:**
- Run `pytest tests/test_api.py -v`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Test command run, output recorded: ```1 passed```


## Risks & Mitigations
1. Risk — Mitigation
"""

# Sprint plan where Coder's evidence is wrong (for mismatch testing)
SAMPLE_SPRINT_PLAN_MISMATCH = """# Sprint Plan

## Overview
Test plan with mismatched evidence.

## Architecture Decisions
- Use FastAPI

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
- [x] Test command run, output recorded: ```should not match```


## Risks & Mitigations
1. Risk — Mitigation
"""

# Sprint plan with empty evidence log (should be skipped)
SAMPLE_SPRINT_PLAN_EMPTY = """# Sprint Plan

## Overview
Test plan.

## Architecture Decisions
- Use FastAPI

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


## Risks & Mitigations
1. Risk — Mitigation
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def state(tmp_path):
    """Create a State instance backed by a temp directory."""
    return State(tmp_path)


@pytest.fixture
def llm_mock():
    """Create a mock LLMClient."""
    return MagicMock(spec=LLMClient)


@pytest.fixture
def tester(llm_mock, state):
    """Create a Tester instance."""
    return Tester(llm_mock, state)


# ---------------------------------------------------------------------------
# Tests: _format_evidence_log
# ---------------------------------------------------------------------------


class TestFormatEvidenceLog:
    """Test evidence log formatting."""

    def test_formats_single_entry(self):
        """Single entry is formatted correctly."""
        entries = [
            {"check": "Test command run", "output": "success", "passed": True},
        ]
        result = Tester._format_evidence_log(entries)
        assert "- [x] Test command run, output recorded: ```success```" in result

    def test_formats_failed_entry(self):
        """Failed entry uses [ ]."""
        entries = [
            {"check": "Test command run", "output": "error", "passed": False},
        ]
        result = Tester._format_evidence_log(entries)
        assert "- [ ] Test command run, output recorded: ```error```" in result

    def test_formats_multiple_entries(self):
        """Multiple entries are formatted."""
        entries = [
            {"check": "Test 1", "output": "pass", "passed": True},
            {"check": "Test 2", "output": "fail", "passed": False},
        ]
        result = Tester._format_evidence_log(entries)
        assert "- [x] Test 1, output recorded: ```pass```" in result
        assert "- [ ] Test 2, output recorded: ```fail```" in result

    def test_no_output_field(self):
        """Entry without output field omits the output section."""
        entries = [
            {"check": "Manual check", "passed": True},
        ]
        result = Tester._format_evidence_log(entries)
        assert "- [x] Manual check" in result
        assert "output recorded:" not in result


# ---------------------------------------------------------------------------
# Tests: _parse_result
# ---------------------------------------------------------------------------


class TestParseResult:
    """Test parsing the Tester's markdown output."""

    def test_parse_verified(self, tester):
        """VERIFIED status is parsed correctly."""
        raw = """### Task 1: Setup
- Status: VERIFIED
- Evidence 1: PASS — import succeeded
- Notes: All good
"""
        from orchestrator.lib.sprint_plan import parse_tasks
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        result = tester._parse_result(raw, tasks[0])
        assert result.status == "VERIFIED"
        assert result.task_id == 1
        assert result.task_name == "Setup"
        assert len(result.evidence) == 1
        assert result.evidence[0]["result"] == "PASS"
        assert "import succeeded" in result.evidence[0]["output"]
        assert "All good" in result.notes

    def test_parse_mismatch(self, tester):
        """MISMATCH status is parsed correctly."""
        raw = """### Task 1: Setup
- Status: MISMATCH
- Evidence 1: FAIL — expected 'success', got 'error'
"""
        from orchestrator.lib.sprint_plan import parse_tasks
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        result = tester._parse_result(raw, tasks[0])
        assert result.status == "MISMATCH"
        assert len(result.evidence) == 1
        assert result.evidence[0]["result"] == "FAIL"

    def test_parse_rerun_failed(self, tester):
        """RERUN_FAILED status is parsed correctly."""
        raw = """### Task 1: Setup
- Status: RERUN_FAILED
- Notes: Command not found
"""
        from orchestrator.lib.sprint_plan import parse_tasks
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        result = tester._parse_result(raw, tasks[0])
        assert result.status == "RERUN_FAILED"
        assert "Command not found" in result.notes

    def test_parse_missing_status_defaults_to_rerun_failed(self, tester):
        """Missing status defaults to RERUN_FAILED."""
        raw = """### Task 1: Setup
- Evidence 1: PASS — ok
"""
        from orchestrator.lib.sprint_plan import parse_tasks
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        result = tester._parse_result(raw, tasks[0])
        assert result.status == "RERUN_FAILED"

    def test_parse_multiple_evidence(self, tester):
        """Multiple evidence items are parsed."""
        raw = """### Task 1: Setup
- Status: VERIFIED
- Evidence 1: PASS — test 1 ok
- Evidence 2: PASS — test 2 ok
"""
        from orchestrator.lib.sprint_plan import parse_tasks
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        result = tester._parse_result(raw, tasks[0])
        assert len(result.evidence) == 2
        assert result.evidence[0]["result"] == "PASS"
        assert result.evidence[1]["result"] == "PASS"


# ---------------------------------------------------------------------------
# Tests: _write_report
# ---------------------------------------------------------------------------


class TestWriteReport:
    """Test TEST_REPORT.md writing."""

    def test_writes_report_with_results(self, tester, state):
        """Report is written with task results."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        results = [
            TaskResult(
                task_id=1,
                task_name="Setup",
                status="VERIFIED",
                evidence=[{"result": "PASS", "output": "ok"}],
            ),
        ]
        tester._write_report("sprint-plan.md", results)

        report = state.read_file("TEST_REPORT.md")
        assert "# Test Report" in report
        assert "Task 1: Setup" in report
        assert "VERIFIED" in report
        assert "PASS" in report

    def test_report_includes_notes(self, tester, state):
        """Report includes notes."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        results = [
            TaskResult(
                task_id=1,
                task_name="Setup",
                status="MISMATCH",
                evidence=[{"result": "FAIL", "output": "expected ok"}],
                notes="Output differs from Coder's record",
            ),
        ]
        tester._write_report("sprint-plan.md", results)

        report = state.read_file("TEST_REPORT.md")
        assert "MISMATCH" in report
        assert "Output differs from Coder's record" in report

    def test_updates_sprint_plan_on_verified(self, tester, state):
        """Sprint plan is updated with verification status for VERIFIED tasks."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)

        results = [
            TaskResult(
                task_id=1,
                task_name="Setup",
                status="VERIFIED",
                evidence=[{"result": "PASS", "output": "ok"}],
            ),
        ]
        tester._write_report("sprint-plan.md", results)

        plan = state.read_file("sprint-plan.md")
        assert "Verified by Tester" in plan


# ---------------------------------------------------------------------------
# Tests: verify_task
# ---------------------------------------------------------------------------


class TestVerifyTask:
    """Test single task verification."""

    def test_calls_llm_with_correct_prompt(self, tester, llm_mock, state):
        """verify_task calls LLM with task + evidence log."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)

        llm_mock.chat.return_value = LLMResponse(
            content="### Task 1: Setup\n- Status: VERIFIED\n- Evidence 1: PASS — ok\n",
            reasoning="",
            prompt_tokens=100,
            completion_tokens=200,
            reasoning_tokens=0,
            finish_reason="stop",
        )

        result = tester.verify_task("sprint-plan.md", 1)

        assert llm_mock.chat.call_count == 1
        messages = llm_mock.chat.call_args[0][0]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "Task 1: Setup" in messages[1]["content"]
        assert "should not match" not in messages[1]["content"]  # from filled log

        assert result.status == "VERIFIED"
        assert result.task_id == 1

    def test_raises_on_missing_task(self, tester, state):
        """verify_task raises TesterError for non-existent task."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)

        with pytest.raises(TesterError, match="Task 99 not found"):
            tester.verify_task("sprint-plan.md", 99)

    def test_raises_on_empty_evidence_log(self, tester, state):
        """verify_task raises TesterError when evidence log is empty."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN_EMPTY)

        with pytest.raises(TesterError, match="no Evidence Log"):
            tester.verify_task("sprint-plan.md", 1)

    def test_handles_llm_failure(self, tester, llm_mock, state):
        """verify_task raises TesterError on LLM failure."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)

        llm_mock.chat.side_effect = Exception("Connection refused")

        with pytest.raises(TesterError, match="LLM call failed"):
            tester.verify_task("sprint-plan.md", 1)


# ---------------------------------------------------------------------------
# Tests: execute
# ---------------------------------------------------------------------------


class TestExecute:
    """Test end-to-end execution."""

    def test_processes_all_tasks_with_evidence(self, tester, llm_mock, state):
        """execute processes all tasks that have evidence logs."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)

        llm_mock.chat.side_effect = [
            LLMResponse(
                content="### Task 1: Setup\n- Status: VERIFIED\n- Evidence 1: PASS — ok\n",
                reasoning="",
                prompt_tokens=100,
                completion_tokens=200,
                reasoning_tokens=0,
                finish_reason="stop",
            ),
            LLMResponse(
                content="### Task 2: API\n- Status: VERIFIED\n- Evidence 1: PASS — ok\n",
                reasoning="",
                prompt_tokens=100,
                completion_tokens=200,
                reasoning_tokens=0,
                finish_reason="stop",
            ),
        ]

        result_path = tester.execute("sprint-plan.md")

        assert result_path == "TEST_REPORT.md"
        assert llm_mock.chat.call_count == 2

        report = state.read_file("TEST_REPORT.md")
        assert "Task 1: Setup" in report
        assert "Task 2: API" in report
        assert "VERIFIED" in report

    def test_skips_tasks_without_evidence(self, tester, llm_mock, state):
        """execute skips tasks with empty evidence logs."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN_EMPTY)

        result_path = tester.execute("sprint-plan.md")

        assert result_path == "TEST_REPORT.md"
        assert llm_mock.chat.call_count == 0

        report = state.read_file("TEST_REPORT.md")
        assert "Tasks verified: 0" in report

    def test_no_tasks_returns_immediately(self, tester, llm_mock, state):
        """execute returns immediately if no tasks found."""
        plan = """# Sprint Plan

## Overview
No tasks.

## Architecture Decisions
- None

## Tasks

## Risks & Mitigations
1. Risk — Mitigation
"""
        state.write_file("sprint-plan.md", plan)
        result_path = tester.execute("sprint-plan.md")

        assert result_path == "TEST_REPORT.md"
        assert llm_mock.chat.call_count == 0

    def test_mismatch_detected(self, tester, llm_mock, state):
        """Mismatch is detected and flagged in report."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)

        llm_mock.chat.return_value = LLMResponse(
            content="### Task 1: Setup\n- Status: MISMATCH\n- Evidence 1: FAIL — expected 'success', got 'error'\n",
            reasoning="",
            prompt_tokens=100,
            completion_tokens=200,
            reasoning_tokens=0,
            finish_reason="stop",
        )

        result = tester.verify_task("sprint-plan.md", 1)
        assert result.status == "MISMATCH"


# ---------------------------------------------------------------------------
# Tests: _run_cmd
# ---------------------------------------------------------------------------


class TestRunCmd:
    """Test shell command execution."""

    def test_successful_command(self):
        """Successful command returns (0, stdout)."""
        rc, out = Tester._run_cmd("echo hello")
        assert rc == 0
        assert "hello" in out

    def test_failed_command(self):
        """Failed command returns non-zero rc."""
        rc, out = Tester._run_cmd("false")
        assert rc != 0

    def test_timeout(self):
        """Timed-out command returns -1."""
        rc, out = Tester._run_cmd("sleep 5", timeout=1)
        assert rc == -1
        assert "timed out" in out

    def test_nonexistent_command(self):
        """Nonexistent command returns non-zero rc."""
        rc, out = Tester._run_cmd("nonexistent_command_xyz")
        assert rc != 0
