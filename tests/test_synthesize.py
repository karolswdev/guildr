"""Tests for QuizEngine.synthesize() and header validation."""

from unittest.mock import MagicMock

import pytest

from orchestrator.ingestion.quiz import (
    QuizEngine,
    SynthesisError,
    _SYNTHESIZE_PROMPT,
    _SYNTHESIZE_RETRY_PROMPT,
)


def _make_llm(*, responses: list[str] | None = None):
    """Create a mock LLMClient that returns given responses in sequence."""
    llm = MagicMock()
    if responses is None:
        responses = ["# Project: Test\n\n## Description\ntest\n\n## Target Users\nusers\n\n## Core Requirements\n1. req\n\n## Constraints\n- c\n\n## Out of Scope\n- o"]

    mock_responses = []
    for text in responses:
        r = MagicMock()
        r.content = text
        mock_responses.append(r)

    llm.chat.side_effect = mock_responses
    return llm


def _make_config(max_turns=10):
    """Create a minimal Config mock."""
    config = MagicMock()
    config.quiz_max_turns = max_turns
    return config


class TestSynthesizeSuccess:
    """synthesize() produces markdown with all required headers."""

    def test_produces_valid_qwendea(self):
        """Mock LLM returning well-formed output → passes on first try."""
        llm = _make_llm()
        config = _make_config()
        engine = QuizEngine(llm, config)

        engine.qa = [
            MagicMock(question="Q1", answer="A1"),
            MagicMock(question="Q2", answer="A2"),
        ]

        result = engine.synthesize()

        assert "# Project:" in result
        assert "## Description" in result
        assert "## Target Users" in result
        assert "## Core Requirements" in result
        assert "## Constraints" in result
        assert "## Out of Scope" in result

    def test_strips_code_fences(self):
        """Output wrapped in ```markdown fences is unwrapped."""
        wrapped = (
            "```markdown\n"
            "# Project: Test\n\n"
            "## Description\ntest\n\n"
            "## Target Users\nusers\n\n"
            "## Core Requirements\n1. req\n\n"
            "## Constraints\n- c\n\n"
            "## Out of Scope\n- o\n"
            "```"
        )
        llm = _make_llm(responses=[wrapped])
        config = _make_config()
        engine = QuizEngine(llm, config)

        engine.qa = [
            MagicMock(question="Q1", answer="A1"),
        ]

        result = engine.synthesize()

        # Should not start with backtick
        assert not result.startswith("```")
        assert "# Project: Test" in result

    def test_strips_code_fences_without_language_tag(self):
        """Output wrapped in bare ``` fences is unwrapped."""
        wrapped = (
            "```\n"
            "# Project: Test\n\n"
            "## Description\ntest\n\n"
            "## Target Users\nusers\n\n"
            "## Core Requirements\n1. req\n\n"
            "## Constraints\n- c\n\n"
            "## Out of Scope\n- o\n"
            "```"
        )
        llm = _make_llm(responses=[wrapped])
        config = _make_config()
        engine = QuizEngine(llm, config)

        engine.qa = [MagicMock(question="Q1", answer="A1")]
        result = engine.synthesize()

        assert not result.startswith("```")
        assert "# Project: Test" in result


class TestSynthesizeRetry:
    """Retries once on missing-header output with targeted feedback."""

    def test_retry_on_missing_headers(self):
        """Mock LLM returning malformed output → retry → valid output → passes."""
        malformed = "# Project: Test\n\n## Description\ntest\n"
        # Missing: Target Users, Core Requirements, Constraints, Out of Scope
        valid = (
            "# Project: Test\n\n"
            "## Description\ntest\n\n"
            "## Target Users\nusers\n\n"
            "## Core Requirements\n1. req\n\n"
            "## Constraints\n- c\n\n"
            "## Out of Scope\n- o\n"
        )
        llm = _make_llm(responses=[malformed, valid])
        config = _make_config()
        engine = QuizEngine(llm, config)

        engine.qa = [MagicMock(question="Q1", answer="A1")]

        result = engine.synthesize()

        assert "# Project:" in result
        assert "## Target Users" in result
        assert "## Core Requirements" in result

        # Should have called LLM twice: initial + retry
        assert llm.chat.call_count == 2

    def test_retry_prompt_contains_missing_headers(self):
        """Retry prompt lists the specific missing headers."""
        malformed = "# Project: Test\n\n## Description\ntest\n"
        valid = (
            "# Project: Test\n\n"
            "## Description\ntest\n\n"
            "## Target Users\nusers\n\n"
            "## Core Requirements\n1. req\n\n"
            "## Constraints\n- c\n\n"
            "## Out of Scope\n- o\n"
        )
        llm = _make_llm(responses=[malformed, valid])
        config = _make_config()
        engine = QuizEngine(llm, config)

        engine.qa = [MagicMock(question="Q1", answer="A1")]
        engine.synthesize()

        # Second call is the retry
        retry_messages = llm.chat.call_args_list[1][0][0]
        retry_content = retry_messages[0]["content"]

        # Should mention the missing headers
        assert "## Target Users" in retry_content
        assert "## Core Requirements" in retry_content
        assert "## Constraints" in retry_content
        assert "## Out of Scope" in retry_content


class TestSynthesisError:
    """On second failure, raises SynthesisError with the bad output."""

    def test_raises_on_double_failure(self):
        """Mock LLM returning malformed output twice → SynthesisError raised."""
        malformed = "# Project: Test\n\n## Description\ntest\n"
        llm = _make_llm(responses=[malformed, malformed])
        config = _make_config()
        engine = QuizEngine(llm, config)

        engine.qa = [MagicMock(question="Q1", answer="A1")]

        with pytest.raises(SynthesisError) as exc_info:
            engine.synthesize()

        # bad_output is stripped by _strip_code_fences
        assert exc_info.value.bad_output == malformed.strip()

    def test_error_message_lists_missing_headers(self):
        """SynthesisError message includes the missing headers."""
        malformed = "# Project: Test\n\n## Description\ntest\n"
        llm = _make_llm(responses=[malformed, malformed])
        config = _make_config()
        engine = QuizEngine(llm, config)

        engine.qa = [MagicMock(question="Q1", answer="A1")]

        with pytest.raises(SynthesisError) as exc_info:
            engine.synthesize()

        error_msg = str(exc_info.value)
        assert "Target Users" in error_msg
        assert "Core Requirements" in error_msg

    def test_raises_on_llm_error_during_retry(self):
        """LLM error during retry raises SynthesisError with original output."""
        malformed = "# Project: Test\n\n## Description\ntest\n"
        llm = _make_llm(responses=[malformed])
        llm.chat.side_effect = [
            MagicMock(content=malformed),
            Exception("Network error"),
        ]
        config = _make_config()
        engine = QuizEngine(llm, config)

        engine.qa = [MagicMock(question="Q1", answer="A1")]

        with pytest.raises(SynthesisError) as exc_info:
            engine.synthesize()

        # bad_output is stripped by _strip_code_fences
        assert exc_info.value.bad_output == malformed.strip()


class TestSynthesisPrompt:
    """Verify prompt construction."""

    def test_synthesize_prompt_includes_qa_log(self):
        """The synthesize prompt includes the Q&A log."""
        llm = _make_llm()
        config = _make_config()
        engine = QuizEngine(llm, config)

        engine.qa = [
            MagicMock(question="What are you building?", answer="A todo app"),
        ]

        engine.synthesize()

        call_content = llm.chat.call_args[0][0][0]["content"]
        assert "What are you building?" in call_content
        assert "A todo app" in call_content

    def test_synthesize_prompt_structure(self):
        """The synthesize prompt has the expected structure."""
        prompt = _SYNTHESIZE_PROMPT
        assert "{qa_log}" in prompt
        assert "# Project:" in prompt
        assert "## Description" in prompt
        assert "## Target Users" in prompt
        assert "## Core Requirements" in prompt
        assert "## Constraints" in prompt
        assert "## Out of Scope" in prompt

    def test_retry_prompt_structure(self):
        """The retry prompt includes missing headers and Q&A log."""
        prompt = _SYNTHESIZE_RETRY_PROMPT
        assert "{missing}" in prompt
        assert "{qa_log}" in prompt
