"""Tests for orchestrator.lib.validators."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.lib.validators import (
    validate_architect,
    validate_implementation,
    validate_testing,
    validate_review,
)
from orchestrator.lib.state import State


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    return tmp_path


@pytest.fixture
def state(tmp_project: Path):
    """Create a State object for testing."""
    return State(tmp_project)


class TestValidateArchitect:
    """Test validate_architect."""

    def test_passes_with_evidence_required(self, tmp_project, state):
        """Returns (True, ...) when sprint-plan.md has Evidence Required section."""
        (tmp_project / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n\n"
            "**Evidence Required:**\n- Run tests\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )
        passed, reason = validate_architect(state)
        assert passed is True

    def test_fails_missing_file(self, tmp_project, state):
        """Returns (False, ...) when sprint-plan.md is missing."""
        passed, reason = validate_architect(state)
        assert passed is False

    def test_fails_no_evidence_required(self, tmp_project, state):
        """Returns (False, ...) when sprint-plan.md lacks Evidence Required."""
        (tmp_project / "sprint-plan.md").write_text(
            "# Sprint Plan\n\nNo evidence sections here.",
            encoding="utf-8",
        )
        passed, reason = validate_architect(state)
        assert passed is False


class TestValidateImplementation:
    """Test validate_implementation."""

    def test_passes_when_declared_files_exist(self, tmp_project, state):
        """Returns (True, ...) when all task-declared files exist."""
        (tmp_project / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Files**: `app/__init__.py`\n\n"
            "**Evidence Required:**\n- Run `python -c \"import app\"`\n\n"
            "**Evidence Log:**\n- [ ] Done\n\n"
            "### Task 2: Test\n"
            "- **Files**: `tests/test_app.py`\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [ ] Passed\n\n",
            encoding="utf-8",
        )
        (tmp_project / "app").mkdir()
        (tmp_project / "app" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_project / "tests").mkdir()
        (tmp_project / "tests" / "test_app.py").write_text("", encoding="utf-8")
        passed, reason = validate_implementation(state)
        assert passed is True

    def test_fails_missing_declared_file(self, tmp_project, state):
        """Returns (False, ...) when a declared file is missing."""
        (tmp_project / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Files**: `app/__init__.py`\n\n"
            "**Evidence Log:**\n- [ ] Not done\n\n",
            encoding="utf-8",
        )
        passed, reason = validate_implementation(state)
        assert passed is False
        assert "missing files" in reason

    def test_fails_no_declared_files(self, tmp_project, state):
        """Returns (False, ...) when a task declares no files."""
        (tmp_project / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n\n"
            "**Evidence Log:**\n- [ ] Not done\n\n",
            encoding="utf-8",
        )
        passed, reason = validate_implementation(state)
        assert passed is False
        assert "declares no files" in reason

    def test_fails_missing_file(self, tmp_project, state):
        """Returns (False, ...) when sprint-plan.md is missing."""
        passed, reason = validate_implementation(state)
        assert passed is False


class TestValidateTesting:
    """Test validate_testing."""

    def test_passes_no_failures(self, tmp_project, state):
        """Returns (True, ...) when TEST_REPORT.md has no failures."""
        (tmp_project / "TEST_REPORT.md").write_text("All tests passed.", encoding="utf-8")
        passed, reason = validate_testing(state)
        assert passed is True

    def test_fails_mismatch(self, tmp_project, state):
        """Returns (False, ...) when TEST_REPORT contains MISMATCH."""
        (tmp_project / "TEST_REPORT.md").write_text("MISMATCH found in task 2.", encoding="utf-8")
        passed, reason = validate_testing(state)
        assert passed is False

    def test_fails_rerun_failed(self, tmp_project, state):
        """Returns (False, ...) when TEST_REPORT contains RERUN_FAILED."""
        (tmp_project / "TEST_REPORT.md").write_text("RERUN_FAILED in task 3.", encoding="utf-8")
        passed, reason = validate_testing(state)
        assert passed is False

    def test_fails_missing_file(self, tmp_project, state):
        """Returns (False, ...) when TEST_REPORT.md is missing."""
        passed, reason = validate_testing(state)
        assert passed is False


class TestValidateReview:
    """Test validate_review."""

    def test_passes_approved(self, tmp_project, state):
        """Returns (True, ...) when REVIEW.md verdict is APPROVED."""
        (tmp_project / "REVIEW.md").write_text("APPROVED", encoding="utf-8")
        passed, reason = validate_review(state)
        assert passed is True

    def test_passes_approved_with_notes(self, tmp_project, state):
        """Returns (True, ...) when REVIEW.md verdict is APPROVED WITH NOTES."""
        (tmp_project / "REVIEW.md").write_text("APPROVED WITH NOTES", encoding="utf-8")
        passed, reason = validate_review(state)
        assert passed is True

    def test_fails_critical(self, tmp_project, state):
        """Returns (False, ...) when REVIEW.md contains CRITICAL."""
        (tmp_project / "REVIEW.md").write_text("CRITICAL: Major issues found", encoding="utf-8")
        passed, reason = validate_review(state)
        assert passed is False

    def test_fails_changes_requested(self, tmp_project, state):
        """Returns (False, ...) when REVIEW.md contains CHANGES REQUESTED."""
        (tmp_project / "REVIEW.md").write_text("CHANGES REQUESTED: Fix these issues", encoding="utf-8")
        passed, reason = validate_review(state)
        assert passed is False

    def test_fails_missing_file(self, tmp_project, state):
        """Returns (False, ...) when REVIEW.md is missing."""
        passed, reason = validate_review(state)
        assert passed is False
