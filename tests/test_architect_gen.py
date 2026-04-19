"""Tests for Architect._generate and Architect._refine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orchestrator.lib.config import Config
from orchestrator.lib.llm import LLMClient, LLMResponse
from orchestrator.lib.state import State
from orchestrator.roles.architect import Architect


@pytest.fixture
def mock_llm():
    """Create a mock LLMClient that returns a fixed response."""
    llm = MagicMock(spec=LLMClient)
    llm.chat = MagicMock(return_value=LLMResponse(
        content="# Sprint Plan\n\n## Overview\nTest plan.\n\n## Architecture Decisions\n- Decision 1\n\n## Tasks\n\n### Task 1: Setup\n- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `setup.py`\n\n**Acceptance Criteria:**\n- [ ] Setup works\n\n**Evidence Required:**\n- Run `pytest tests/`\n\n**Evidence Log:**\n- [ ] Test command run\n\n## Risks & Mitigations\n1. Risk — Mitigation",
        reasoning="",
        prompt_tokens=100,
        completion_tokens=200,
        reasoning_tokens=0,
        finish_reason="stop",
    ))
    return llm


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


@pytest.fixture
def architect(mock_llm, state, config):
    """Create an Architect instance."""
    return Architect(mock_llm, state, config)


class TestGenerate:
    """Test _generate produces valid sprint-plan structure."""

    def test_generate_calls_llm_with_system_and_user(self, architect, mock_llm):
        """_generate sends system prompt (generate.txt) and user prompt."""
        qwendea = "# Project: Test\n\n## Description\nA test project."

        architect._generate(qwendea)

        mock_llm.chat.assert_called_once()
        messages = mock_llm.chat.call_args[0][0]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "Project: Test" in messages[1]["content"]

    def test_generate_includes_qwendea_in_prompt(self, architect, mock_llm):
        """_generate passes qwendea content to the LLM."""
        qwendea = "# Project: Foo\n\n## Description\nBar."

        architect._generate(qwendea)

        messages = mock_llm.chat.call_args[0][0]
        assert "Foo" in messages[1]["content"]
        assert "Bar" in messages[1]["content"]

    def test_generate_produces_markdown_with_headers(self, architect, mock_llm):
        """_generate returns markdown with all required sprint-plan headers."""
        response = architect._generate("# Project: Test\n\n## Description\nTest.")
        assert "# Sprint Plan" in response
        assert "## Overview" in response
        assert "## Architecture Decisions" in response
        assert "## Tasks" in response
        assert "## Risks & Mitigations" in response

    def test_generate_uses_max_tokens(self, architect, mock_llm):
        """_generate sends max_tokens=16384 to the LLM."""
        architect._generate("# Project: Test\n\n## Description\nTest.")

        call_kwargs = mock_llm.chat.call_args[1]
        assert call_kwargs.get("max_tokens") == 16384


class TestRefine:
    """Test _refine strips reasoning and injects targeted feedback."""

    def test_refine_strips_reasoning_content(self, architect, mock_llm):
        """_refine messages array does NOT include reasoning_content field."""
        prior = "# Sprint Plan\n\n## Tasks\n\n### Task 1: Test\n- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `test.py`\n\n**Acceptance Criteria:**\n- [ ] Works\n\n**Evidence Required:**\n- Run `pytest`\n\n**Evidence Log:**\n- [ ] Done\n\n## Risks & Mitigations\n1. Risk — Mitigation"
        prior_eval = {
            "specificity": {"score": 1, "issues": []},
            "testability": {"score": 0, "issues": ["Task 1: 'Works' is not verifiable"]},
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }

        architect._refine("# Project: Test\n\n## Description\nTest.", prior, prior_eval)

        messages = mock_llm.chat.call_args[0][0]
        # Check that no message dict has a 'reasoning_content' key
        for msg in messages:
            assert "reasoning_content" not in msg, (
                f"reasoning_content found in message: {msg}"
            )

    def test_refine_injects_only_failed_criteria(self, architect, mock_llm):
        """_refine injects only failed-criteria feedback, not full eval JSON."""
        prior = "# Sprint Plan\n\n## Tasks\n\n### Task 1: Test\n- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `test.py`\n\n**Acceptance Criteria:**\n- [ ] Works\n\n**Evidence Required:**\n- Run `pytest`\n\n**Evidence Log:**\n- [ ] Done\n\n## Risks & Mitigations\n1. Risk — Mitigation"
        prior_eval = {
            "specificity": {"score": 1, "issues": []},
            "testability": {"score": 0, "issues": ["Task 1: 'Works' is not verifiable"]},
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }

        architect._refine("# Project: Test\n\n## Description\nTest.", prior, prior_eval)

        messages = mock_llm.chat.call_args[0][0]
        user_content = messages[1]["content"]

        # Should contain the failed criterion text
        assert "testability" in user_content.lower()
        assert "not verifiable" in user_content

        # Should NOT contain the full evaluation JSON
        # (e.g., should not have all criterion names as JSON keys)
        assert '"specificity"' not in user_content
        assert '"completeness"' not in user_content
        assert '"feasibility"' not in user_content

    def test_refine_includes_prior_plan(self, architect, mock_llm):
        """_refine includes the prior plan in the prompt."""
        prior = "# Sprint Plan\n\n## Tasks\n\n### Task 1: Test\n- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `test.py`\n\n**Acceptance Criteria:**\n- [ ] Works\n\n**Evidence Required:**\n- Run `pytest`\n\n**Evidence Log:**\n- [ ] Done\n\n## Risks & Mitigations\n1. Risk — Mitigation"
        prior_eval = {
            "specificity": {"score": 1, "issues": []},
            "testability": {"score": 0, "issues": ["Bad criterion"]},
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }

        architect._refine("# Project: Test\n\n## Description\nTest.", prior, prior_eval)

        messages = mock_llm.chat.call_args[0][0]
        user_content = messages[1]["content"]
        assert "# Sprint Plan" in user_content
        assert "Task 1: Test" in user_content

    def test_refine_uses_max_tokens(self, architect, mock_llm):
        """_refine sends max_tokens=16384 to the LLM."""
        prior = "# Sprint Plan\n\n## Tasks\n\n### Task 1: Test\n- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `test.py`\n\n**Acceptance Criteria:**\n- [ ] Works\n\n**Evidence Required:**\n- Run `pytest`\n\n**Evidence Log:**\n- [ ] Done\n\n## Risks & Mitigations\n1. Risk — Mitigation"
        prior_eval = {
            "specificity": {"score": 1, "issues": []},
            "testability": {"score": 0, "issues": ["Bad"]},
            "evidence": {"score": 1, "issues": []},
            "completeness": {"score": 1, "issues": []},
            "feasibility": {"score": 1, "issues": []},
            "risk": {"score": 1, "issues": []},
        }

        architect._refine("# Project: Test\n\n## Description\nTest.", prior, prior_eval)

        call_kwargs = mock_llm.chat.call_args[1]
        assert call_kwargs.get("max_tokens") == 16384
