"""Tests for the Reviewer role on the opencode session runtime (H6.3c)."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import patch

import pytest

from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
)
from orchestrator.lib.state import State
from orchestrator.roles.reviewer import (
    CriterionResult,
    ReviewResult,
    Reviewer,
    ReviewerError,
)


SAMPLE_ACCEPTANCE_CRITERIA = """# Sprint Plan

## Overview
Test.

## Architecture Decisions
- Use FastAPI

## Tasks

### Task 1: Setup
- **Priority**: P0
- **Dependencies**: none
- **Files**: `app/__init__.py`

**Acceptance Criteria:**
- [ ] Module imports
- [ ] Package installs

**Evidence Required:**
- Run `pytest`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Done

### Task 2: API
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `app/api.py`

**Acceptance Criteria:**
- [ ] GET /healthz returns 200
- [ ] POST /items creates an item

**Evidence Required:**
- Run `pytest`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Done

## Risks & Mitigations
1. Risk — Mitigation
"""

SAMPLE_TEST_REPORT = """# Test Report

Tasks verified: 2

### Task 1: Setup
- Status: VERIFIED
- Evidence 1: PASS — import succeeded
"""

SAMPLE_REVIEW_OUTPUT = """- [PASS] Module imports
  - Notes: Clean import structure
- [PASS] Package installs
  - Notes: pyproject.toml is correct
- [CONCERN] GET /healthz returns 200
  - Notes: No timeout handling
- [FAIL] POST /items creates an item
  - Notes: Returns 201 but no body

## Overall

APPROVED WITH NOTES
"""

SAMPLE_REVIEW_CRITICAL = """- [PASS] Module imports
  - Notes: Clean

- [CRITICAL] POST /items creates an item
  - Notes: SQL injection vulnerability

## Overall

CRITICAL
"""

SAMPLE_REVIEW_APPROVED = """- [PASS] Module imports
  - Notes: Clean

## Overall

APPROVED
"""

SAMPLE_REVIEW_CHANGES = """- [FAIL] Module imports
  - Notes: Broken

## Overall

CHANGES REQUESTED
"""


# ---------------------------------------------------------------------------
# Fake SessionRunner
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def state(tmp_path):
    return State(tmp_path)


@pytest.fixture
def runner():
    return _FakeRunner()


@pytest.fixture
def reviewer(runner, state):
    return Reviewer(runner, state)


# ---------------------------------------------------------------------------
# _extract_criteria / _parse_result / _write_review (unchanged behaviour)
# ---------------------------------------------------------------------------


class TestExtractCriteria:
    def test_extracts_criteria_from_tasks(self):
        from orchestrator.lib.sprint_plan import parse_tasks

        tasks = parse_tasks(SAMPLE_ACCEPTANCE_CRITERIA)
        result = Reviewer._extract_criteria(tasks)
        assert "Task 1: Setup" in result
        assert "Module imports" in result

    def test_no_criteria_returns_message(self):
        from orchestrator.lib.sprint_plan import parse_tasks

        tasks = parse_tasks(
            "# Sprint Plan\n\n## Tasks\n\n### Task 1: x\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)\n"
            "- [x] Done\n\n## Risks & Mitigations\n1. Risk — Mitigation\n"
        )
        assert "No acceptance criteria" in Reviewer._extract_criteria(tasks)


class TestParseResult:
    def test_parse_approved_with_notes(self, reviewer):
        result = reviewer._parse_result(SAMPLE_REVIEW_OUTPUT)
        assert result.overall == "APPROVED_WITH_NOTES"
        assert len(result.criteria) == 4
        assert result.criteria[3].verdict == "FAIL"

    def test_parse_critical(self, reviewer):
        result = reviewer._parse_result(SAMPLE_REVIEW_CRITICAL)
        assert result.overall == "CRITICAL"
        assert any(c.verdict == "CRITICAL" for c in result.criteria)

    def test_parse_approved(self, reviewer):
        assert reviewer._parse_result(SAMPLE_REVIEW_APPROVED).overall == "APPROVED"

    def test_parse_changes_requested(self, reviewer):
        assert reviewer._parse_result(SAMPLE_REVIEW_CHANGES).overall == "CHANGES_REQUESTED"

    def test_missing_verdict_defaults_to_changes_requested(self, reviewer):
        assert reviewer._parse_result("- [PASS] x\n  - Notes: y\n").overall == "CHANGES_REQUESTED"


class TestWriteReview:
    def test_writes_approved(self, reviewer, state):
        reviewer._write_review(
            ReviewResult(
                criteria=[CriterionResult("Module imports", "PASS", "Clean")],
                overall="APPROVED",
            )
        )
        review = state.read_file("REVIEW.md")
        assert "APPROVED" in review
        assert "[PASS]" in review

    def test_writes_critical(self, reviewer, state):
        reviewer._write_review(
            ReviewResult(
                criteria=[CriterionResult("SQL injection", "CRITICAL", "params")],
                overall="CRITICAL",
            )
        )
        review = state.read_file("REVIEW.md")
        assert "Required changes:" in review


# ---------------------------------------------------------------------------
# execute — the opencode-driven path
# ---------------------------------------------------------------------------


class TestExecute:
    def _seed(self, state):
        state.write_file("sprint-plan.md", SAMPLE_ACCEPTANCE_CRITERIA)
        state.write_file("TEST_REPORT.md", SAMPLE_TEST_REPORT)

    def test_spawns_one_session_and_writes_review(self, reviewer, runner, state):
        self._seed(state)
        runner.result = _result(SAMPLE_REVIEW_APPROVED)

        path = reviewer.execute("sprint-plan.md", "TEST_REPORT.md")

        assert path == "REVIEW.md"
        assert len(runner.prompts) == 1
        assert "APPROVED" in state.read_file("REVIEW.md")

    def test_prompt_contains_criteria_and_test_report(self, reviewer, runner, state):
        self._seed(state)
        runner.result = _result(SAMPLE_REVIEW_APPROVED)
        reviewer.execute()
        prompt = runner.prompts[0]
        assert "Module imports" in prompt
        assert "VERIFIED" in prompt  # test report echoed

    def test_missing_test_report_falls_back_to_default(self, reviewer, runner, state):
        state.write_file("sprint-plan.md", SAMPLE_ACCEPTANCE_CRITERIA)
        runner.result = _result(SAMPLE_REVIEW_APPROVED)
        reviewer.execute()
        assert "No test report available." in runner.prompts[0]

    def test_runner_exception_is_wrapped(self, reviewer, runner, state):
        self._seed(state)
        runner.exc = RuntimeError("boom")
        with pytest.raises(ReviewerError, match="opencode session failed"):
            reviewer.execute()

    def test_non_zero_exit_raises(self, reviewer, runner, state):
        self._seed(state)
        runner.result = _result(SAMPLE_REVIEW_APPROVED, exit_code=3)
        with pytest.raises(ReviewerError, match="rc=3"):
            reviewer.execute()

    def test_empty_assistant_text_raises(self, reviewer, runner, state):
        self._seed(state)
        runner.result = _result("")
        with pytest.raises(ReviewerError, match="no assistant text"):
            reviewer.execute()

    def test_emits_audit_entries(self, reviewer, runner, state):
        self._seed(state)
        runner.result = _result(SAMPLE_REVIEW_APPROVED)
        reviewer.execute()
        raw_path = state.project_dir / ".orchestrator" / "logs" / "raw-io.jsonl"
        usage_path = state.project_dir / ".orchestrator" / "logs" / "usage.jsonl"
        assert raw_path.exists()
        assert usage_path.exists()
        assert "reviewer" in raw_path.read_text(encoding="utf-8")

    def test_audit_fires_even_on_non_zero_exit(self, reviewer, runner, state):
        self._seed(state)
        runner.result = _result(SAMPLE_REVIEW_APPROVED, exit_code=2)
        with pytest.raises(ReviewerError):
            reviewer.execute()
        raw_path = state.project_dir / ".orchestrator" / "logs" / "raw-io.jsonl"
        assert raw_path.exists()
        assert "reviewer" in raw_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# is_critical + git diff summary
# ---------------------------------------------------------------------------


class TestIsCritical:
    def test_true_for_critical(self, reviewer, state):
        state.write_file("REVIEW.md", SAMPLE_REVIEW_CRITICAL)
        assert reviewer.is_critical() is True

    def test_false_for_approved(self, reviewer, state):
        state.write_file("REVIEW.md", SAMPLE_REVIEW_APPROVED)
        assert reviewer.is_critical() is False

    def test_false_when_missing(self, reviewer):
        assert reviewer.is_critical() is False


class TestGetGitDiffSummary:
    def test_returns_string(self):
        assert isinstance(Reviewer._get_git_diff_summary(), str)

    def test_missing_git_returns_default(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            assert "No git diff available" in Reviewer._get_git_diff_summary()
