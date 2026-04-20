"""Tests for Tester role."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orchestrator.lib.llm import LLMClient
from orchestrator.lib.state import State
from orchestrator.roles.tester import (
    TaskResult,
    Tester,
    TesterError,
)


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
- Run `python -c "from pathlib import Path; assert Path('app/__init__.py').exists(); print('import-ready')"`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run


### Task 2: API
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `app/api.py`

**Acceptance Criteria:**
- [ ] Endpoint returns 200

**Evidence Required:**
- Run `python -c "from pathlib import Path; assert Path('app/api.py').exists(); print('api-ready')"`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run


## Risks & Mitigations
1. Risk - Mitigation
"""


SAMPLE_SPRINT_PLAN_EMPTY = """# Sprint Plan

## Tasks

### Task 1: Setup
- **Priority**: P0
- **Dependencies**: none
- **Files**: `app/__init__.py`

**Acceptance Criteria:**
- [ ] Module imports

**Evidence Required:**
- Manually inspect the interface

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Manual check

## Risks & Mitigations
1. Risk - Mitigation
"""


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


class TestParseResult:
    """Test parsing legacy markdown output."""

    def test_parse_verified(self, tester):
        """VERIFIED status is parsed correctly."""
        raw = """### Task 1: Setup
- Status: VERIFIED
- Evidence 1: PASS - import succeeded
- Notes: All good
"""
        from orchestrator.lib.sprint_plan import parse_tasks

        task = parse_tasks(SAMPLE_SPRINT_PLAN)[0]
        result = tester._parse_result(raw, task)
        assert result.status == "VERIFIED"
        assert result.task_id == 1
        assert result.task_name == "Setup"
        assert "All good" in result.notes

    def test_parse_rerun_failed(self, tester):
        """RERUN_FAILED status is parsed correctly."""
        raw = """### Task 1: Setup
- Status: RERUN_FAILED
- Notes: Command not found
"""
        from orchestrator.lib.sprint_plan import parse_tasks

        task = parse_tasks(SAMPLE_SPRINT_PLAN)[0]
        result = tester._parse_result(raw, task)
        assert result.status == "RERUN_FAILED"
        assert "Command not found" in result.notes

    def test_parse_missing_status_defaults_to_rerun_failed(self, tester):
        """Missing status defaults to RERUN_FAILED."""
        raw = """### Task 1: Setup
- Evidence 1: PASS - ok
"""
        from orchestrator.lib.sprint_plan import parse_tasks

        task = parse_tasks(SAMPLE_SPRINT_PLAN)[0]
        result = tester._parse_result(raw, task)
        assert result.status == "RERUN_FAILED"


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
                status="RERUN_FAILED",
                evidence=[{"result": "FAIL", "output": "expected ok"}],
                notes="Command failed.",
            ),
        ]
        tester._write_report("sprint-plan.md", results)

        report = state.read_file("TEST_REPORT.md")
        assert "RERUN_FAILED" in report
        assert "Command failed." in report

    def test_does_not_mutate_sprint_plan(self, tester, state):
        """Report writing itself does not alter sprint-plan.md."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        before = state.read_file("sprint-plan.md")
        tester._write_report("sprint-plan.md", [])
        assert state.read_file("sprint-plan.md") == before


class TestVerifyTask:
    """Test single task verification."""

    def test_runs_evidence_commands_without_llm(self, tester, llm_mock, state):
        """verify_task runs Evidence Required commands in the project dir."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        state.write_file("app/__init__.py", "# app\n")

        result = tester.verify_task("sprint-plan.md", 1)

        assert llm_mock.chat.call_count == 0
        assert result.status == "VERIFIED"
        assert result.task_id == 1
        assert result.evidence[0]["result"] == "PASS"
        assert "import-ready" in result.evidence[0]["output"]
        plan = state.read_file("sprint-plan.md")
        assert "- [x]" in plan
        assert "import-ready" in plan

    def test_raises_on_missing_task(self, tester, state):
        """verify_task raises TesterError for non-existent task."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)

        with pytest.raises(TesterError, match="Task 99 not found"):
            tester.verify_task("sprint-plan.md", 99)

    def test_no_runnable_evidence_returns_failed_result(self, tester, state):
        """verify_task fails closed when Evidence Required has no command."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN_EMPTY)

        result = tester.verify_task("sprint-plan.md", 1)

        assert result.status == "RERUN_FAILED"
        assert "No runnable Evidence Required command" in result.evidence[0]["output"]

    def test_failed_command_returns_failed_result(self, tester, state):
        """verify_task returns RERUN_FAILED when a command exits non-zero."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)

        result = tester.verify_task("sprint-plan.md", 1)

        assert result.status == "RERUN_FAILED"
        assert result.evidence[0]["result"] == "FAIL"


class TestExecute:
    """Test end-to-end execution."""

    def test_processes_all_tasks_with_evidence(self, tester, llm_mock, state):
        """execute processes all tasks and writes TEST_REPORT.md."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        state.write_file("app/__init__.py", "# app\n")
        state.write_file("app/api.py", "# api\n")

        result_path = tester.execute("sprint-plan.md")

        assert result_path == "TEST_REPORT.md"
        assert llm_mock.chat.call_count == 0

        report = state.read_file("TEST_REPORT.md")
        assert "Task 1: Setup" in report
        assert "Task 2: API" in report
        assert "VERIFIED" in report
        plan = state.read_file("sprint-plan.md")
        assert "import-ready" in plan
        assert "api-ready" in plan

    def test_no_tasks_returns_immediately(self, tester, llm_mock, state):
        """execute returns immediately if no tasks found."""
        plan = """# Sprint Plan

## Tasks

## Risks & Mitigations
1. Risk - Mitigation
"""
        state.write_file("sprint-plan.md", plan)
        result_path = tester.execute("sprint-plan.md")

        assert result_path == "TEST_REPORT.md"
        assert llm_mock.chat.call_count == 0
        assert "Tasks verified: 0" in state.read_file("TEST_REPORT.md")

    def test_failed_command_reported(self, tester, state):
        """Failed Evidence Required commands are flagged in report."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)

        result = tester.verify_task("sprint-plan.md", 1)
        assert result.status == "RERUN_FAILED"


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

    def test_command_uses_cwd(self, tmp_path):
        """Command runs in the supplied working directory."""
        (tmp_path / "marker.txt").write_text("ok", encoding="utf-8")
        rc, out = Tester._run_cmd("ls marker.txt", cwd=tmp_path)
        assert rc == 0
        assert "marker.txt" in out

    def test_timeout(self):
        """Timed-out command returns -1."""
        rc, out = Tester._run_cmd("sleep 5", timeout=1)
        assert rc == -1
        assert "timed out" in out

    def test_nonexistent_command(self):
        """Nonexistent command returns non-zero rc."""
        rc, out = Tester._run_cmd("nonexistent_command_xyz")
        assert rc != 0


class TestExtractCommands:
    """Test Evidence Required command extraction."""

    def test_extracts_run_backtick_command(self):
        result = Tester._extract_commands(["Run `python -c \"print('ok')\"`"])
        assert result == [{
            "label": "Run `python -c \"print('ok')\"`",
            "command": "python -c \"print('ok')\"",
        }]

    def test_extracts_bare_command_in_backticks(self):
        result = Tester._extract_commands(["Verify with `pytest -q`"])
        assert result[0]["command"] == "pytest -q"

    def test_ignores_manual_only_evidence(self):
        result = Tester._extract_commands(["Manual verification in browser"])
        assert result == []

    def test_trims_long_output(self):
        output = Tester._trim_output("x" * 2100, limit=20)
        assert output == "x" * 20 + "\n...<truncated>"
