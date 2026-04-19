"""Tests for sprint plan parsing, slicing, and evidence patch helpers."""

from __future__ import annotations

import re

import pytest

from orchestrator.lib.sprint_plan import (
    Task,
    apply_evidence_patch,
    parse_tasks,
    slice_task,
)

# ---------------------------------------------------------------------------
# Sample sprint-plan.md fixture with 5 tasks
# ---------------------------------------------------------------------------

SAMPLE_SPRINT_PLAN = """# Sprint Plan

## Overview
This is a test sprint plan with 5 tasks for testing.

## Architecture Decisions
- Use FastAPI for the web layer
- Use SQLite for local storage
- All code in `app/` package

## Tasks

### Task 1: Setup project
- **Priority**: P0
- **Dependencies**: none
- **Files**: `app/__init__.py`, `pyproject.toml`

**Acceptance Criteria:**
- [ ] `pip install -e .` succeeds
- [ ] `python -c "import app"` works

**Evidence Required:**
- Run `pip install -e .` and capture success output
- Run `python -c "import app"`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```Successfully built```
- [ ] Import verified


### Task 2: Database model
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `app/db.py`, `tests/test_db.py`

**Acceptance Criteria:**
- [ ] `create_engine()` returns a connected engine
- [ ] `Base.metadata.create_all()` creates all tables

**Evidence Required:**
- Run `pytest tests/test_db.py -v`
- Check that tables exist in the database file

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```1 passed```
- [ ] Tables verified in test.db


### Task 3: API endpoints
- **Priority**: P0
- **Dependencies**: Task 2
- **Files**: `app/api.py`, `tests/test_api.py`

**Acceptance Criteria:**
- [ ] `GET /healthz` returns 200 with `{"status": "ok"}`
- [ ] `POST /items` creates an item and returns 201

**Evidence Required:**
- Run `pytest tests/test_api.py -v`
- Check `curl /healthz` returns in < 50ms

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```2 passed```
- [ ] Health check verified


### Task 4: Auth middleware
- **Priority**: P1
- **Dependencies**: Task 3
- **Files**: `app/auth.py`, `tests/test_auth.py`

**Acceptance Criteria:**
- [ ] API key header is validated
- [ ] Invalid key returns 401

**Evidence Required:**
- Run `pytest tests/test_auth.py -v`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```1 passed```


### Task 5: Logging
- **Priority**: P2
- **Dependencies**: Task 2
- **Files**: `app/logging_config.py`

**Acceptance Criteria:**
- [ ] Log output goes to stdout and file
- [ ] Log level is configurable

**Evidence Required:**
- Run `pytest tests/test_logging.py -v`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```1 passed```


## Risks & Mitigations
1. Database corruption → Daily backups
2. API rate limiting → Token bucket algorithm
3. Auth bypass → Regular security audits
"""

# Fixture with already-filled evidence log
SAMPLE_SPRINT_PLAN_FILLED = """# Sprint Plan

## Overview
A filled sprint plan.

## Architecture Decisions
- Use FastAPI

## Tasks

### Task 1: First task
- **Priority**: P0
- **Dependencies**: none
- **Files**: `app/__init__.py`

**Acceptance Criteria:**
- [ ] Works

**Evidence Required:**
- Run `pytest`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [x] Test command run, output recorded: ```1 passed```
- [x] Committed as a1b2c3d


### Task 2: Second task
- **Priority**: P1
- **Dependencies**: Task 1
- **Files**: `app/main.py`

**Acceptance Criteria:**
- [ ] Runs

**Evidence Required:**
- Run `python app/main.py`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```success```


## Risks & Mitigations
1. Risk — Mitigation
"""


# ---------------------------------------------------------------------------
# Tests: parse_tasks
# ---------------------------------------------------------------------------


class TestParseTasks:
    """Test that parse_tasks returns tasks in order with id, name, deps, body."""

    def test_returns_all_tasks_in_order(self):
        """parse_tasks returns 5 tasks from the sample plan."""
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        assert len(tasks) == 5

    def test_task_ids_are_correct(self):
        """Task IDs match the document order."""
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        ids = [t.id for t in tasks]
        assert ids == [1, 2, 3, 4, 5]

    def test_task_names_are_correct(self):
        """Task names match the document."""
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        names = [t.name for t in tasks]
        assert names == [
            "Setup project",
            "Database model",
            "API endpoints",
            "Auth middleware",
            "Logging",
        ]

    def test_dependencies_parsed(self):
        """Dependencies are correctly parsed."""
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        assert tasks[0].deps == []  # Task 1: none
        assert tasks[1].deps == ["Task 1"]  # Task 2: Task 1
        assert tasks[2].deps == ["Task 2"]  # Task 3: Task 2
        assert tasks[3].deps == ["Task 3"]  # Task 4: Task 3
        assert tasks[4].deps == ["Task 2"]  # Task 5: Task 2

    def test_priority_parsed(self):
        """Priorities are correctly parsed."""
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        priorities = [t.priority for t in tasks]
        assert priorities == ["P0", "P0", "P0", "P1", "P2"]

    def test_files_parsed(self):
        """Files are correctly parsed."""
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        assert tasks[0].files == ["app/__init__.py", "pyproject.toml"]
        assert tasks[1].files == ["app/db.py", "tests/test_db.py"]

    def test_acceptance_criteria_parsed(self):
        """Acceptance criteria are extracted."""
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        assert len(tasks[0].acceptance_criteria) == 2
        assert "pip install -e ." in tasks[0].acceptance_criteria[0]

    def test_evidence_required_parsed(self):
        """Evidence required items are extracted."""
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        assert len(tasks[0].evidence_required) == 2
        assert "pip install -e ." in tasks[0].evidence_required[0]

    def test_evidence_log_parsed(self):
        """Evidence log entries are parsed with check text and passed status."""
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        # Task 1 has empty evidence log (all [ ])
        assert len(tasks[0].evidence_log) == 2
        assert tasks[0].evidence_log[0]["passed"] is False
        assert "Test command run" in tasks[0].evidence_log[0]["check"]

    def test_task_bodies_contain_full_section(self):
        """Each task body contains the full markdown section."""
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        assert "### Task 1:" in tasks[0].body
        assert "Acceptance Criteria" in tasks[0].body
        assert "Evidence Required" in tasks[0].body
        assert "Evidence Log" in tasks[0].body

    def test_task_bodies_do_not_overlap(self):
        """Task bodies are distinct and non-overlapping."""
        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        for i, t1 in enumerate(tasks):
            for j, t2 in enumerate(tasks):
                if i != j:
                    assert t2.body not in t1.body

    def test_empty_plan_returns_no_tasks(self):
        """An empty sprint plan returns no tasks."""
        tasks = parse_tasks("# Sprint Plan\n\n## Tasks\n")
        assert len(tasks) == 0

    def test_no_tasks_section_returns_no_tasks(self):
        """A plan without ## Tasks returns no tasks."""
        tasks = parse_tasks("# Sprint Plan\n\n## Overview\nTest.\n")
        assert len(tasks) == 0

    def test_single_task(self):
        """A plan with a single task parses correctly."""
        plan = """# Sprint Plan

## Overview
Test.

## Tasks

### Task 1: Only task
- **Priority**: P0
- **Dependencies**: none
- **Files**: `a.py`

**Acceptance Criteria:**
- [ ] Works

**Evidence Required:**
- Run `pytest`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Done


## Risks & Mitigations
1. Risk — Mitigation
"""
        tasks = parse_tasks(plan)
        assert len(tasks) == 1
        assert tasks[0].id == 1
        assert tasks[0].name == "Only task"


# ---------------------------------------------------------------------------
# Tests: slice_task
# ---------------------------------------------------------------------------


class TestSliceTask:
    """Test that slice_task returns the correct section + architecture header."""

    def test_returns_architecture_and_task(self):
        """slice_task returns architecture decisions + the specific task."""
        sliced = slice_task(SAMPLE_SPRINT_PLAN, 1)
        assert "## Architecture Decisions" in sliced
        assert "Use FastAPI" in sliced
        assert "### Task 1: Setup project" in sliced

    def test_excludes_other_tasks(self):
        """slice_task excludes other task sections."""
        sliced = slice_task(SAMPLE_SPRINT_PLAN, 1)
        assert "### Task 2:" not in sliced
        assert "### Task 3:" not in sliced

    def test_includes_acceptance_criteria(self):
        """sliced task includes acceptance criteria."""
        sliced = slice_task(SAMPLE_SPRINT_PLAN, 2)
        assert "Acceptance Criteria" in sliced
        assert "create_engine" in sliced

    def test_includes_evidence_required(self):
        """sliced task includes evidence required."""
        sliced = slice_task(SAMPLE_SPRINT_PLAN, 3)
        assert "Evidence Required" in sliced
        assert "healthz" in sliced

    def test_raises_for_missing_task(self):
        """slice_task raises ValueError for non-existent task ID."""
        with pytest.raises(ValueError, match="Task 99 not found"):
            slice_task(SAMPLE_SPRINT_PLAN, 99)

    def test_slices_last_task(self):
        """slice_task works for the last task in the plan."""
        sliced = slice_task(SAMPLE_SPRINT_PLAN, 5)
        assert "### Task 5: Logging" in sliced
        assert "## Risks" not in sliced

    def test_slices_middle_task(self):
        """slice_task works for a middle task."""
        sliced = slice_task(SAMPLE_SPRINT_PLAN, 3)
        assert "### Task 3: API endpoints" in sliced
        assert "## Risks" not in sliced


# ---------------------------------------------------------------------------
# Tests: apply_evidence_patch
# ---------------------------------------------------------------------------


class TestApplyEvidencePatch:
    """Test that apply_evidence_patch ticks checkboxes and inserts outputs idempotently."""

    def test_ticks_checkbox_and_adds_output(self):
        """apply_evidence_patch marks checkbox as [x] and adds output."""
        result = apply_evidence_patch(SAMPLE_SPRINT_PLAN_FILLED, {
            "task_id": 2,
            "entries": [
                {"check": "Test command run", "output": "success", "passed": True},
            ],
        })
        assert "- [x] Test command run, output recorded: ```success```" in result

    def test_marks_failed_entry(self):
        """apply_evidence_patch marks failed entries as [ ]."""
        result = apply_evidence_patch(SAMPLE_SPRINT_PLAN_FILLED, {
            "task_id": 2,
            "entries": [
                {"check": "Test command run", "output": "error", "passed": False},
            ],
        })
        assert "- [ ] Test command run, output recorded: ```error```" in result

    def test_preserves_already_checked_entries(self):
        """Already checked entries in the original remain checked."""
        result = apply_evidence_patch(SAMPLE_SPRINT_PLAN_FILLED, {
            "task_id": 1,
            "entries": [
                {"check": "Existing entry", "output": "ok", "passed": True},
            ],
        })
        assert "- [x] Existing entry, output recorded: ```ok```" in result

    def test_multiple_entries(self):
        """apply_evidence_patch handles multiple entries."""
        result = apply_evidence_patch(SAMPLE_SPRINT_PLAN_FILLED, {
            "task_id": 2,
            "entries": [
                {"check": "Test 1", "output": "pass", "passed": True},
                {"check": "Test 2", "output": "fail", "passed": False},
                {"check": "Test 3", "output": "ok", "passed": True},
            ],
        })
        assert "- [x] Test 1, output recorded: ```pass```" in result
        assert "- [ ] Test 2, output recorded: ```fail```" in result
        assert "- [x] Test 3, output recorded: ```ok```" in result

    def test_raises_for_missing_task(self):
        """apply_evidence_patch raises ValueError for non-existent task."""
        with pytest.raises(ValueError, match="Task 99 not found"):
            apply_evidence_patch(SAMPLE_SPRINT_PLAN_FILLED, {
                "task_id": 99,
                "entries": [],
            })

    def test_preserves_other_tasks(self):
        """apply_evidence_patch does not modify other tasks."""
        result = apply_evidence_patch(SAMPLE_SPRINT_PLAN_FILLED, {
            "task_id": 2,
            "entries": [{"check": "Test", "output": "ok", "passed": True}],
        })
        assert "- [x] Test command run, output recorded: ```1 passed```" in result
        assert "- [x] Committed as a1b2c3d" in result

    def test_no_output_field(self):
        """apply_evidence_patch works when output is omitted."""
        result = apply_evidence_patch(SAMPLE_SPRINT_PLAN_FILLED, {
            "task_id": 2,
            "entries": [
                {"check": "Manual check", "passed": True},
            ],
        })
        assert "- [x] Manual check" in result
        match = re.search(r"- \[x\] Manual check(.*?)(?:\n|$)", result)
        assert match is not None
        assert ", output recorded:" not in match.group(1)

    def test_idempotent_on_repeated_application(self):
        """Applying the same patch twice produces the same result."""
        patch = {
            "task_id": 2,
            "entries": [
                {"check": "Test", "output": "ok", "passed": True},
            ],
        }
        result1 = apply_evidence_patch(SAMPLE_SPRINT_PLAN_FILLED, patch)
        result2 = apply_evidence_patch(result1, patch)
        assert result1 == result2


# ---------------------------------------------------------------------------
# Tests: round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Test parse -> slice -> patch -> parse unchanged task count."""

    def test_task_count_preserved(self):
        """After parse -> slice -> patch -> parse, task count is unchanged."""
        original_tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        original_count = len(original_tasks)

        modified = SAMPLE_SPRINT_PLAN
        for task in original_tasks:
            sliced = slice_task(modified, task.id)
            patch = {
                "task_id": task.id,
                "entries": [
                    {"check": task.evidence_required[0] if task.evidence_required else "Test",
                     "output": "ok", "passed": True},
                ],
            }
            modified = apply_evidence_patch(modified, patch)

        modified_tasks = parse_tasks(modified)
        assert len(modified_tasks) == original_count

    def test_task_ids_preserved(self):
        """Task IDs are preserved after round-trip."""
        original_tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        original_ids = [t.id for t in original_tasks]

        modified = SAMPLE_SPRINT_PLAN
        for task in original_tasks:
            sliced = slice_task(modified, task.id)
            patch = {
                "task_id": task.id,
                "entries": [
                    {"check": "Test", "output": "ok", "passed": True},
                ],
            }
            modified = apply_evidence_patch(modified, patch)

        modified_tasks = parse_tasks(modified)
        modified_ids = [t.id for t in modified_tasks]
        assert modified_ids == original_ids

    def test_task_names_preserved(self):
        """Task names are preserved after round-trip."""
        original_tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        original_names = [t.name for t in original_tasks]

        modified = SAMPLE_SPRINT_PLAN
        for task in original_tasks:
            sliced = slice_task(modified, task.id)
            patch = {
                "task_id": task.id,
                "entries": [
                    {"check": "Test", "output": "ok", "passed": True},
                ],
            }
            modified = apply_evidence_patch(modified, patch)

        modified_tasks = parse_tasks(modified)
        modified_names = [t.name for t in modified_tasks]
        assert modified_names == original_names

    def test_evidence_log_filled_after_patch(self):
        """After patching, evidence log entries are marked as passed."""
        modified = SAMPLE_SPRINT_PLAN
        tasks = parse_tasks(modified)

        for task in tasks:
            patch = {
                "task_id": task.id,
                "entries": [
                    {"check": f"Evidence for {task.name}", "output": "ok", "passed": True},
                ],
            }
            modified = apply_evidence_patch(modified, patch)

        final_tasks = parse_tasks(modified)
        for task in final_tasks:
            assert len(task.evidence_log) >= 1
            assert task.evidence_log[0]["passed"] is True
