"""Tests for Reviewer role."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.lib.llm import LLMClient, LLMResponse
from orchestrator.lib.state import State
from orchestrator.roles.reviewer import (
    CriterionResult,
    ReviewResult,
    Reviewer,
    ReviewerError,
)

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

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

### Task 2: API
- Status: VERIFIED
- Evidence 1: PASS — endpoint returns 200
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
  - Notes: Clean import structure
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
def reviewer(llm_mock, state):
    """Create a Reviewer instance."""
    return Reviewer(llm_mock, state)


# ---------------------------------------------------------------------------
# Tests: _extract_criteria
# ---------------------------------------------------------------------------


class TestExtractCriteria:
    """Test acceptance criteria extraction."""

    def test_extracts_criteria_from_tasks(self):
        """Criteria are extracted from tasks."""
        from orchestrator.lib.sprint_plan import parse_tasks

        plan = """# Sprint Plan

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


## Risks & Mitigations
1. Risk — Mitigation
"""
        tasks = parse_tasks(plan)
        result = Reviewer._extract_criteria(tasks)
        assert "Task 1: Setup" in result
        assert "Module imports" in result
        assert "Package installs" in result

    def test_multiple_tasks(self):
        """Criteria from multiple tasks are extracted."""
        from orchestrator.lib.sprint_plan import parse_tasks

        plan = """# Sprint Plan

## Overview
Test.

## Tasks

### Task 1: First
- **Priority**: P0
- **Dependencies**: none
- **Files**: `a.py`

**Acceptance Criteria:**
- [ ] First criterion

**Evidence Required:**
- Run `pytest`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Done

### Task 2: Second
- **Priority**: P0
- **Dependencies**: none
- **Files**: `b.py`

**Acceptance Criteria:**
- [ ] Second criterion

**Evidence Required:**
- Run `pytest`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Done

## Risks & Mitigations
1. Risk — Mitigation
"""
        tasks = parse_tasks(plan)
        result = Reviewer._extract_criteria(tasks)
        assert "Task 1: First" in result
        assert "Task 2: Second" in result
        assert "First criterion" in result
        assert "Second criterion" in result

    def test_no_criteria_returns_message(self):
        """Tasks without criteria produce a message."""
        from orchestrator.lib.sprint_plan import parse_tasks

        plan = """# Sprint Plan

## Overview
Test.

## Tasks

### Task 1: No criteria
- **Priority**: P0
- **Dependencies**: none
- **Files**: `a.py`

**Evidence Required:**
- Run `pytest`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Done

## Risks & Mitigations
1. Risk — Mitigation
"""
        tasks = parse_tasks(plan)
        result = Reviewer._extract_criteria(tasks)
        assert "No acceptance criteria" in result


# ---------------------------------------------------------------------------
# Tests: _parse_result
# ---------------------------------------------------------------------------


class TestParseResult:
    """Test parsing the Reviewer's markdown output."""

    def test_parse_approved_with_notes(self, reviewer):
        """APPROVED WITH NOTES is parsed correctly."""
        result = reviewer._parse_result(SAMPLE_REVIEW_OUTPUT)
        assert result.overall == "APPROVED_WITH_NOTES"
        assert len(result.criteria) == 4
        assert result.criteria[0].verdict == "PASS"
        assert result.criteria[2].verdict == "CONCERN"
        assert result.criteria[3].verdict == "FAIL"

    def test_parse_critical(self, reviewer):
        """CRITICAL verdict is parsed correctly."""
        result = reviewer._parse_result(SAMPLE_REVIEW_CRITICAL)
        assert result.overall == "CRITICAL"
        assert len(result.criteria) == 2
        assert result.criteria[1].verdict == "CRITICAL"

    def test_parse_approved(self, reviewer):
        """APPROVED verdict is parsed correctly."""
        result = reviewer._parse_result(SAMPLE_REVIEW_APPROVED)
        assert result.overall == "APPROVED"
        assert len(result.criteria) == 1

    def test_parse_changes_requested(self, reviewer):
        """CHANGES REQUESTED verdict is parsed correctly."""
        result = reviewer._parse_result(SAMPLE_REVIEW_CHANGES)
        assert result.overall == "CHANGES_REQUESTED"
        assert len(result.criteria) == 1

    def test_parse_missing_verdict_defaults_to_changes_requested(self, reviewer):
        """Missing overall verdict defaults to CHANGES_REQUESTED."""
        raw = """- [PASS] Works
  - Notes: fine
"""
        result = reviewer._parse_result(raw)
        assert result.overall == "CHANGES_REQUESTED"

    def test_parse_notes(self, reviewer):
        """Notes are captured per criterion."""
        result = reviewer._parse_result(SAMPLE_REVIEW_OUTPUT)
        assert "Clean import structure" in result.criteria[0].notes
        assert "SQL injection" in reviewer._parse_result(
            SAMPLE_REVIEW_CRITICAL
        ).criteria[1].notes

    def test_parse_criterion_text(self, reviewer):
        """Criterion text is captured."""
        result = reviewer._parse_result(SAMPLE_REVIEW_OUTPUT)
        assert "Module imports" in result.criteria[0].text
        assert "POST /items" in result.criteria[3].text


# ---------------------------------------------------------------------------
# Tests: _write_review
# ---------------------------------------------------------------------------


class TestWriteReview:
    """Test REVIEW.md writing."""

    def test_writes_review_with_verdicts(self, reviewer, state):
        """Review is written with criterion verdicts."""
        state.write_file("sprint-plan.md", SAMPLE_ACCEPTANCE_CRITERIA)
        result = ReviewResult(
            criteria=[
                CriterionResult(
                    text="Module imports",
                    verdict="PASS",
                    notes="Clean structure",
                ),
            ],
            overall="APPROVED",
        )
        reviewer._write_review(result)

        review = state.read_file("REVIEW.md")
        assert "# Review" in review
        assert "APPROVED" in review
        assert "[PASS]" in review
        assert "Module imports" in review

    def test_writes_critical_review(self, reviewer, state):
        """CRITICAL review includes required changes."""
        state.write_file("sprint-plan.md", SAMPLE_ACCEPTANCE_CRITERIA)
        result = ReviewResult(
            criteria=[
                CriterionResult(
                    text="SQL injection",
                    verdict="CRITICAL",
                    notes="Need parameterized queries",
                ),
            ],
            overall="CRITICAL",
        )
        reviewer._write_review(result)

        review = state.read_file("REVIEW.md")
        assert "CRITICAL" in review
        assert "Required changes:" in review
        assert "SQL injection" in review

    def test_writes_changes_requested_review(self, reviewer, state):
        """CHANGES REQUESTED review includes required changes."""
        state.write_file("sprint-plan.md", SAMPLE_ACCEPTANCE_CRITERIA)
        result = ReviewResult(
            criteria=[
                CriterionResult(
                    text="Broken import",
                    verdict="FAIL",
                    notes="Import path wrong",
                ),
            ],
            overall="CHANGES_REQUESTED",
        )
        reviewer._write_review(result)

        review = state.read_file("REVIEW.md")
        assert "CHANGES_REQUESTED" in review
        assert "Required changes:" in review


# ---------------------------------------------------------------------------
# Tests: execute
# ---------------------------------------------------------------------------


class TestExecute:
    """Test end-to-end execution."""

    def test_calls_llm_with_correct_prompt(self, reviewer, llm_mock, state):
        """execute calls LLM with acceptance criteria + test report + diff."""
        state.write_file("sprint-plan.md", SAMPLE_ACCEPTANCE_CRITERIA)
        state.write_file("TEST_REPORT.md", SAMPLE_TEST_REPORT)

        llm_mock.chat.return_value = LLMResponse(
            content="APPROVED",
            reasoning="",
            prompt_tokens=100,
            completion_tokens=200,
            reasoning_tokens=0,
            finish_reason="stop",
        )

        result_path = reviewer.execute("sprint-plan.md", "TEST_REPORT.md")

        assert result_path == "REVIEW.md"
        assert llm_mock.chat.call_count == 1
        messages = llm_mock.chat.call_args[0][0]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "Module imports" in messages[1]["content"]
        assert "GET /healthz" in messages[1]["content"]

    def test_handles_llm_failure(self, reviewer, llm_mock, state):
        """execute raises ReviewerError on LLM failure."""
        state.write_file("sprint-plan.md", SAMPLE_ACCEPTANCE_CRITERIA)
        state.write_file("TEST_REPORT.md", SAMPLE_TEST_REPORT)

        llm_mock.chat.side_effect = Exception("Connection refused")

        with pytest.raises(ReviewerError, match="LLM call failed"):
            reviewer.execute("sprint-plan.md", "TEST_REPORT.md")

    def test_missing_test_report_uses_default(self, reviewer, llm_mock, state):
        """Missing TEST_REPORT.md uses default message."""
        state.write_file("sprint-plan.md", SAMPLE_ACCEPTANCE_CRITERIA)

        llm_mock.chat.return_value = LLMResponse(
            content="APPROVED",
            reasoning="",
            prompt_tokens=100,
            completion_tokens=200,
            reasoning_tokens=0,
            finish_reason="stop",
        )

        # Should not raise even though TEST_REPORT.md doesn't exist
        result_path = reviewer.execute("sprint-plan.md", "TEST_REPORT.md")
        assert result_path == "REVIEW.md"


# ---------------------------------------------------------------------------
# Tests: is_critical
# ---------------------------------------------------------------------------


class TestIsCritical:
    """Test critical review detection."""

    def test_returns_true_for_critical(self, reviewer, state):
        """Returns True when REVIEW.md has CRITICAL verdict."""
        state.write_file("REVIEW.md", SAMPLE_REVIEW_CRITICAL)
        assert reviewer.is_critical() is True

    def test_returns_false_for_approved(self, reviewer, state):
        """Returns False when REVIEW.md is APPROVED."""
        state.write_file("REVIEW.md", SAMPLE_REVIEW_APPROVED)
        assert reviewer.is_critical() is False

    def test_returns_false_when_missing(self, reviewer, state):
        """Returns False when REVIEW.md doesn't exist."""
        assert reviewer.is_critical() is False


# ---------------------------------------------------------------------------
# Tests: _get_git_diff_summary
# ---------------------------------------------------------------------------


class TestGetGitDiffSummary:
    """Test git diff summary generation."""

    def test_returns_diff_stat(self):
        """Returns git diff stat output."""
        result = Reviewer._get_git_diff_summary()
        # In a real repo, this should return some output
        assert isinstance(result, str)

    def test_returns_empty_on_error(self):
        """Returns empty string on subprocess error."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = Reviewer._get_git_diff_summary()
            assert "No git diff available" in result
