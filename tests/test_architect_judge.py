"""Tests for Architect._self_evaluate with JSON robustness."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from orchestrator.lib.config import Config
from orchestrator.lib.llm import LLMClient, LLMResponse
from orchestrator.lib.state import State
from orchestrator.roles.architect import Architect


@pytest.fixture
def state(tmp_path):
    """Create a State instance backed by a temp directory."""
    return State(tmp_path)


@pytest.fixture
def config(tmp_path):
    """Create a minimal Config."""
    from pathlib import Path
    return Config(
        llama_server_url="http://127.0.0.1:8080",
        project_dir=Path(tmp_path),
        architect_max_passes=3,
        architect_pass_threshold=4,
    )


class TestStrictJsonParse:
    """Test that strict JSON parse succeeds on well-formed output."""

    def test_parses_valid_json(self, state, config):
        """_parse_json succeeds on well-formed JSON."""
        eval_result = {
            "specificity": {"score": 1, "issues": []},
            "testability": {"score": 1, "issues": []},
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }
        raw = '{"specificity": {"score": 1, "issues": []}, "testability": {"score": 1, "issues": []}, "evidence": {"score": 1, "issues": []}, "completeness": {"score": 1, "issues": []}, "feasibility": {"score": 1, "issues": []}, "risk": {"score": 1, "issues": []}}'
        result = Architect._parse_json(raw)
        assert result is not None
        assert result["specificity"]["score"] == 1
        assert result["testability"]["score"] == 1

    def test_rejects_non_dict_json(self, state, config):
        """_parse_json returns None for non-dict JSON."""
        result = Architect._parse_json('[1, 2, 3]')
        assert result is None

    def test_rejects_invalid_json(self, state, config):
        """_parse_json returns None for invalid JSON."""
        result = Architect._parse_json('not json at all')
        assert result is None

    def test_rejects_empty_string(self, state, config):
        """_parse_json returns None for empty string."""
        result = Architect._parse_json('')
        assert result is None


class TestReprompt:
    """Test re-prompt on malformed output."""

    def test_reprompt_on_prose_wrapper(self, state, config):
        """Re-prompt succeeds when LLM initially wraps JSON in prose."""
        llm = MagicMock(spec=LLMClient)
        # First call returns prose + JSON, second call returns clean JSON
        llm.chat.side_effect = [
            LLMResponse(
                content="Here is my evaluation:\n```json\n{\"specificity\": {\"score\": 1, \"issues\": []}, \"testability\": {\"score\": 0, \"issues\": [\"vague\"]}, \"evidence\": {\"score\": 1, \"issues\": []}, \"completeness\": {\"score\": 1, \"issues\": []}, \"feasibility\": {\"score\": 1, \"issues\": []}, \"risk\": {\"score\": 1, \"issues\": []}}\n```",
                reasoning="",
                prompt_tokens=100,
                completion_tokens=200,
                reasoning_tokens=0,
                finish_reason="stop",
            ),
            LLMResponse(
                content='{"specificity": {"score": 1, "issues": []}, "testability": {"score": 0, "issues": ["vague"]}, "evidence": {"score": 1, "issues": []}, "completeness": {"score": 1, "issues": []}, "feasibility": {"score": 1, "issues": []}, "risk": {"score": 1, "issues": []}}',
                reasoning="",
                prompt_tokens=100,
                completion_tokens=200,
                reasoning_tokens=0,
                finish_reason="stop",
            ),
        ]
        architect = Architect(llm, state, config)

        score, evaluation = architect._self_evaluate("# Project: Test\n\n## Description\nTest.", "# Sprint Plan\n\n## Tasks\n\n### Task 1: Test\n- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `test.py`\n\n**Acceptance Criteria:**\n- [ ] Works\n\n**Evidence Required:**\n- Run `pytest`\n\n**Evidence Log:**\n- [ ] Done\n\n## Risks & Mitigations\n1. Risk — Mitigation")

        assert score == 5  # 5/6 (testability=0)
        assert evaluation["testability"]["score"] == 0
        assert llm.chat.call_count == 2

    def test_reprompt_on_trailing_junk(self, state, config):
        """Re-prompt succeeds when LLM adds trailing junk after JSON."""
        llm = MagicMock(spec=LLMClient)
        llm.chat.side_effect = [
            LLMResponse(
                content='{"specificity": {"score": 1, "issues": []}, "testability": {"score": 1, "issues": []}, "evidence": {"score": 1, "issues": []}, "completeness": {"score": 1, "issues": []}, "feasibility": {"score": 1, "issues": []}, "risk": {"score": 1, "issues": []}}\n\nHope this helps!',
                reasoning="",
                prompt_tokens=100,
                completion_tokens=200,
                reasoning_tokens=0,
                finish_reason="stop",
            ),
            LLMResponse(
                content='{"specificity": {"score": 1, "issues": []}, "testability": {"score": 1, "issues": []}, "evidence": {"score": 1, "issues": []}, "completeness": {"score": 1, "issues": []}, "feasibility": {"score": 1, "issues": []}, "risk": {"score": 1, "issues": []}}',
                reasoning="",
                prompt_tokens=100,
                completion_tokens=200,
                reasoning_tokens=0,
                finish_reason="stop",
            ),
        ]
        architect = Architect(llm, state, config)

        score, evaluation = architect._self_evaluate("# Project: Test\n\n## Description\nTest.", "# Sprint Plan\n\n## Tasks\n\n### Task 1: Test\n- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `test.py`\n\n**Acceptance Criteria:**\n- [ ] Works\n\n**Evidence Required:**\n- Run `pytest`\n\n**Evidence Log:**\n- [ ] Done\n\n## Risks & Mitigations\n1. Risk — Mitigation")

        assert score == 6
        assert evaluation["specificity"]["score"] == 1
        assert llm.chat.call_count == 2


class TestRegexFallback:
    """Test regex fallback for outermost {...} extraction."""

    def test_regex_extracts_outermost_json(self, state, config):
        """_extract_json_regex extracts outermost {...} block."""
        raw = 'Some prose before {\n  "specificity": {"score": 1, "issues": []},\n  "testability": {"score": 0, "issues": ["vague"]},\n  "evidence": {"score": 1, "issues": []},\n  "completeness": {"score": 1, "issues": []},\n  "feasibility": {"score": 1, "issues": []},\n  "risk": {"score": 1, "issues": []}\n} and prose after'
        result = Architect._extract_json_regex(raw)
        assert result is not None
        assert result["specificity"]["score"] == 1
        assert result["testability"]["score"] == 0

    def test_regex_fails_on_completely_malformed(self, state, config):
        """_extract_json_regex returns None when no {...} block exists."""
        result = Architect._extract_json_regex('no braces at all')
        assert result is None

    def test_regex_fails_on_nested_unbalanced(self, state, config):
        """_extract_json_regex returns None on deeply nested unbalanced braces."""
        # This tests that the regex doesn't match partial nested content
        result = Architect._extract_json_regex('{ { broken }')
        assert result is None

    def test_regex_fails_on_invalid_json_inside_braces(self, state, config):
        """_extract_json_regex returns None when extracted block is invalid JSON."""
        result = Architect._extract_json_regex('{not valid json}')
        assert result is None


class TestMalformedExhaustion:
    """Test behavior after 2 failed reparse attempts."""

    def test_returns_score_0_on_exhaustion(self, state, config):
        """After 2 parse failures + regex failure, returns (0, {"reason": "malformed"})."""
        llm = MagicMock(spec=LLMClient)
        # First call: malformed, second call: still malformed, regex won't help
        llm.chat.side_effect = [
            LLMResponse(
                content='this is completely not json at all and has no braces',
                reasoning="",
                prompt_tokens=100,
                completion_tokens=200,
                reasoning_tokens=0,
                finish_reason="stop",
            ),
            LLMResponse(
                content='still not json, the model just cannot do it',
                reasoning="",
                prompt_tokens=100,
                completion_tokens=200,
                reasoning_tokens=0,
                finish_reason="stop",
            ),
        ]
        architect = Architect(llm, state, config)

        score, evaluation = architect._self_evaluate("# Project: Test\n\n## Description\nTest.", "# Sprint Plan\n\n## Tasks\n\n### Task 1: Test\n- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `test.py`\n\n**Acceptance Criteria:**\n- [ ] Works\n\n**Evidence Required:**\n- Run `pytest`\n\n**Evidence Log:**\n- [ ] Done\n\n## Risks & Mitigations\n1. Risk — Mitigation")

        assert score == 0
        assert evaluation == {"reason": "malformed"}
        assert llm.chat.call_count == 2

    def test_reprompt_message_is_injected(self, state, config):
        """The re-prompt message includes the correction instruction."""
        llm = MagicMock(spec=LLMClient)
        llm.chat.side_effect = [
            LLMResponse(
                content='{broken json',
                reasoning="",
                prompt_tokens=100,
                completion_tokens=200,
                reasoning_tokens=0,
                finish_reason="stop",
            ),
            LLMResponse(
                content='{"specificity": {"score": 1, "issues": []}, "testability": {"score": 1, "issues": []}, "evidence": {"score": 1, "issues": []}, "completeness": {"score": 1, "issues": []}, "feasibility": {"score": 1, "issues": []}, "risk": {"score": 1, "issues": []}}',
                reasoning="",
                prompt_tokens=100,
                completion_tokens=200,
                reasoning_tokens=0,
                finish_reason="stop",
            ),
        ]
        architect = Architect(llm, state, config)

        architect._self_evaluate("# Project: Test\n\n## Description\nTest.", "# Sprint Plan\n\n## Tasks\n\n### Task 1: Test\n- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `test.py`\n\n**Acceptance Criteria:**\n- [ ] Works\n\n**Evidence Required:**\n- Run `pytest`\n\n**Evidence Log:**\n- [ ] Done\n\n## Risks & Mitigations\n1. Risk — Mitigation")

        # Check that the second call's messages include the correction
        second_call = llm.chat.call_args_list[1]
        messages = second_call[0][0]
        last_user = [m for m in messages if m["role"] == "user"][-1]
        assert "not valid JSON" in last_user["content"]


class TestComputeScore:
    """Test _compute_score computation."""

    def test_score_6_all_pass(self, state, config):
        """Score is 6 when all criteria pass."""
        evaluation = {
            "specificity": {"score": 1, "issues": []},
            "testability": {"score": 1, "issues": []},
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }
        score, _ = Architect._compute_score(evaluation)
        assert score == 6

    def test_score_0_all_fail(self, state, config):
        """Score is 0 when all criteria fail."""
        evaluation = {
            "specificity": {"score": 0, "issues": ["bad"]},
            "testability": {"score": 0, "issues": ["bad"]},
            "evidence": {"score": 0, "issues": ["bad"]},
            "completeness": {"score": 0, "issues": ["bad"]},
            "feasibility": {"score": 0, "issues": ["bad"]},
            "risk": {"score": 0, "issues": ["bad"]},
        }
        score, _ = Architect._compute_score(evaluation)
        assert score == 0

    def test_score_partial(self, state, config):
        """Score correctly counts partial passes."""
        evaluation = {
            "specificity": {"score": 1, "issues": []},
            "testability": {"score": 0, "issues": ["bad"]},
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 0, "issues": ["bad"]},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 0, "issues": ["bad"]},
        }
        score, _ = Architect._compute_score(evaluation)
        assert score == 3

    def test_missing_criteria_treated_as_fail(self, state, config):
        """Missing criterion entries are treated as score 0."""
        evaluation = {
            "specificity": {"score": 1, "issues": []},
            # testability, evidence, etc. missing
        }
        score, _ = Architect._compute_score(evaluation)
        assert score == 1

    def test_non_dict_entry_treated_as_fail(self, state, config):
        """Non-dict entries are treated as score 0."""
        evaluation = {
            "specificity": "not a dict",
            "testability": 42,
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }
        score, _ = Architect._compute_score(evaluation)
        assert score == 4
