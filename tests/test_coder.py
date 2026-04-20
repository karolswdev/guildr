"""Tests for Coder role."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from orchestrator.lib.llm import LLMClient, LLMResponse
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


@pytest.fixture
def state(tmp_path):
    """Create a State instance backed by a temp directory."""
    return State(tmp_path)


@pytest.fixture
def llm_mock():
    """Create a mock LLMClient."""
    return MagicMock(spec=LLMClient)


@pytest.fixture
def coder(llm_mock, state):
    """Create a Coder instance."""
    return Coder(llm_mock, state)


def _response(data: dict) -> LLMResponse:
    return LLMResponse(
        content=json.dumps(data),
        reasoning="",
        prompt_tokens=100,
        completion_tokens=200,
        reasoning_tokens=0,
        finish_reason="stop",
    )


class TestTopologicalSort:
    """Test that tasks are processed in dependency order."""

    def test_no_dependencies(self, coder):
        """Tasks with no dependencies are returned in order."""
        from orchestrator.lib.sprint_plan import parse_tasks

        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        ordered = coder._topological_sort(tasks)
        ids = [t.id for t in ordered]
        assert ids == [1, 2]

    def test_with_dependencies(self, coder):
        """Task 2 comes after Task 1."""
        from orchestrator.lib.sprint_plan import parse_tasks

        tasks = parse_tasks(SAMPLE_SPRINT_PLAN)
        ordered = coder._topological_sort(tasks)
        ids = [t.id for t in ordered]
        assert ids.index(1) < ids.index(2)

    def test_single_task(self, coder):
        """A single task is returned as-is."""
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

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Done

## Risks & Mitigations
1. Risk - Mitigation
"""
        from orchestrator.lib.sprint_plan import parse_tasks

        tasks = parse_tasks(plan)
        ordered = coder._topological_sort(tasks)
        assert len(ordered) == 1
        assert ordered[0].id == 1


class TestJsonParsing:
    """Test that JSON patch parsing handles malformed output."""

    def test_strict_parse_valid_json(self, coder):
        """_strict_parse succeeds on valid file patch JSON."""
        patch_data = {
            "task_id": 1,
            "files": [
                {"path": "app/__init__.py", "content": "# ok\n"},
            ],
        }
        result = coder._strict_parse(json.dumps(patch_data))
        assert result is not None
        assert result["task_id"] == 1
        assert result["files"][0]["path"] == "app/__init__.py"

    def test_strict_parse_missing_task_id(self, coder):
        """_strict_parse rejects JSON without task_id."""
        result = coder._strict_parse(json.dumps({"files": []}))
        assert result is None

    def test_strict_parse_missing_files(self, coder):
        """_strict_parse rejects JSON without files."""
        result = coder._strict_parse(json.dumps({"task_id": 1}))
        assert result is None

    def test_strict_parse_empty_files(self, coder):
        """_strict_parse rejects JSON with no file writes."""
        result = coder._strict_parse(json.dumps({"task_id": 1, "files": []}))
        assert result is None

    def test_strict_parse_invalid_json(self, coder):
        """_strict_parse returns None for invalid JSON."""
        assert coder._strict_parse("not json") is None

    def test_regex_fallback(self, coder):
        """_extract_json_regex extracts JSON from prose."""
        raw = (
            "Here is the patch:\n```json\n"
            '{"task_id": 1, "files": [{"path": "app/__init__.py", '
            '"content": "# ok\\n"}]}\n```'
        )
        result = coder._extract_json_regex(raw)
        assert result is not None
        assert result["task_id"] == 1

    def test_regex_fails_on_no_braces(self, coder):
        """_extract_json_regex returns None when no braces exist."""
        assert coder._extract_json_regex("no braces here") is None

    def test_parse_patch_valid(self, coder):
        """_parse_patch succeeds on valid JSON."""
        patch_data = {
            "task_id": 1,
            "files": [{"path": "app/__init__.py", "content": "# ok\n"}],
        }
        result = coder._parse_patch(json.dumps(patch_data))
        assert result is not None
        assert result["task_id"] == 1

    def test_parse_patch_malformed_rejects(self, coder):
        """_parse_patch returns None for completely malformed output."""
        assert coder._parse_patch("this is not json at all") is None


class TestExecuteTask:
    """Test single task execution."""

    def test_calls_llm_and_writes_files(self, coder, llm_mock, state):
        """_execute_task calls LLM and applies complete file writes."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        patch_data = {
            "task_id": 1,
            "files": [
                {"path": "app/__init__.py", "content": "VALUE = 1\n"},
            ],
        }
        llm_mock.chat.return_value = _response(patch_data)

        from orchestrator.lib.sprint_plan import parse_tasks

        task = parse_tasks(SAMPLE_SPRINT_PLAN)[0]
        result = coder._execute_task(SAMPLE_SPRINT_PLAN, task, "sprint-plan.md")

        assert llm_mock.chat.call_count == 1
        messages = llm_mock.chat.call_args[0][0]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "ARCHITECTURE DECISIONS" in messages[1]["content"]
        assert "### Task 1: Setup" in messages[1]["content"]
        assert "Evidence Log" in result
        assert state.read_file("app/__init__.py") == "VALUE = 1\n"

    def test_handles_llm_failure(self, coder, llm_mock):
        """_execute_task raises CoderError on LLM failure."""
        from orchestrator.lib.sprint_plan import parse_tasks

        task = parse_tasks(SAMPLE_SPRINT_PLAN)[0]
        llm_mock.chat.side_effect = Exception("Connection refused")

        with pytest.raises(CoderError, match="LLM call failed"):
            coder._execute_task(SAMPLE_SPRINT_PLAN, task, "sprint-plan.md")

    def test_handles_malformed_patch(self, coder, llm_mock):
        """_execute_task raises CoderError on unparseable patch."""
        from orchestrator.lib.sprint_plan import parse_tasks

        task = parse_tasks(SAMPLE_SPRINT_PLAN)[0]
        llm_mock.chat.return_value = LLMResponse(
            content="this is not valid json",
            reasoning="",
            prompt_tokens=100,
            completion_tokens=200,
            reasoning_tokens=0,
            finish_reason="stop",
        )

        with pytest.raises(CoderError, match="Failed to parse JSON patch"):
            coder._execute_task(SAMPLE_SPRINT_PLAN, task, "sprint-plan.md")

    def test_rejects_mismatched_task_id(self, coder, llm_mock):
        """_execute_task rejects patches for the wrong task."""
        from orchestrator.lib.sprint_plan import parse_tasks

        task = parse_tasks(SAMPLE_SPRINT_PLAN)[0]
        llm_mock.chat.return_value = _response({
            "task_id": 2,
            "files": [{"path": "app/__init__.py", "content": "# bad\n"}],
        })

        with pytest.raises(CoderError, match="does not match task"):
            coder._execute_task(SAMPLE_SPRINT_PLAN, task, "sprint-plan.md")

    def test_rejects_unsafe_file_path(self, coder, llm_mock):
        """_execute_task rejects path traversal writes."""
        from orchestrator.lib.sprint_plan import parse_tasks

        task = parse_tasks(SAMPLE_SPRINT_PLAN)[0]
        llm_mock.chat.return_value = _response({
            "task_id": 1,
            "files": [{"path": "../outside.txt", "content": "bad\n"}],
        })

        with pytest.raises(CoderError, match="unsafe path"):
            coder._execute_task(SAMPLE_SPRINT_PLAN, task, "sprint-plan.md")


class TestExecute:
    """Test end-to-end execution."""

    def test_processes_all_tasks(self, coder, llm_mock, state):
        """execute processes all tasks in dependency order."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        llm_mock.chat.side_effect = [
            _response({
                "task_id": 1,
                "files": [{"path": "app/__init__.py", "content": "# app\n"}],
            }),
            _response({
                "task_id": 2,
                "files": [{"path": "app/api.py", "content": "# api\n"}],
            }),
        ]

        result = coder.execute("sprint-plan.md")

        assert result == "sprint-plan.md"
        assert llm_mock.chat.call_count == 2
        assert state.read_file("app/__init__.py") == "# app\n"
        assert state.read_file("app/api.py") == "# api\n"
        assert "- [ ] Test command run" in state.read_file("sprint-plan.md")

    def test_no_tasks_returns_immediately(self, coder, llm_mock, state):
        """execute returns immediately if no tasks found."""
        plan = """# Sprint Plan

## Tasks

## Risks & Mitigations
1. Risk - Mitigation
"""
        state.write_file("sprint-plan.md", plan)
        result = coder.execute("sprint-plan.md")
        assert result == "sprint-plan.md"
        assert llm_mock.chat.call_count == 0

    def test_task_id_in_patch(self, coder, llm_mock, state):
        """The prompt includes the task currently being implemented."""
        state.write_file("sprint-plan.md", SAMPLE_SPRINT_PLAN)
        captured_calls = []

        def capture_chat(messages, **kw):
            user_content = messages[1]["content"]
            import re

            match = re.search(r"### Task (\d+):", user_content)
            task_id = int(match.group(1)) if match else 0
            captured_calls.append(task_id)
            return _response({
                "task_id": task_id,
                "files": [
                    {"path": f"app/task{task_id}.py", "content": "# ok\n"},
                ],
            })

        llm_mock.chat.side_effect = capture_chat
        coder.execute("sprint-plan.md")

        assert captured_calls == [1, 2]
