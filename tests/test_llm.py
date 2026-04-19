"""Tests for orchestrator.lib.llm."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
import respx
from httpx import Response

from openai import APIConnectionError

from orchestrator.lib.llm import LLMClient, LLMResponse, ThinkingTruncation


def _make_response(content: str = "hello", reasoning: str = "thinking here",
                   finish_reason: str = "stop", prompt_tokens: int = 10,
                   completion_tokens: int = 5, reasoning_tokens: int = 3) -> MagicMock:
    """Build a mock OpenAI response."""
    choice = MagicMock()
    choice.message.content = content
    choice.message.reasoning_content = reasoning
    choice.finish_reason = finish_reason

    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
    }

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


class TestLLMClientParsing:
    """Test that LLMClient.chat() correctly parses responses."""

    def test_parses_content_and_reasoning(self):
        client = LLMClient("http://127.0.0.1:8080")
        mock_resp = _make_response(
            content="The answer is 42.",
            reasoning="Let me think about this step by step...",
        )
        client._client.chat.completions.create = MagicMock(return_value=mock_resp)

        result = client.chat([{"role": "user", "content": "What is 6*7?"}])

        assert result.content == "The answer is 42."
        assert result.reasoning == "Let me think about this step by step..."
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 5
        assert result.reasoning_tokens == 3
        assert result.finish_reason == "stop"

    def test_parses_empty_reasoning(self):
        client = LLMClient("http://127.0.0.1:8080")
        mock_resp = _make_response(reasoning="")
        client._client.chat.completions.create = MagicMock(return_value=mock_resp)

        result = client.chat([{"role": "user", "content": "hi"}])

        assert result.content == "hello"
        assert result.reasoning == ""

    def test_parses_none_reasoning(self):
        client = LLMClient("http://127.0.0.1:8080")
        mock_resp = _make_response()
        mock_resp.choices[0].message.reasoning_content = None
        client._client.chat.completions.create = MagicMock(return_value=mock_resp)

        result = client.chat([{"role": "user", "content": "hi"}])

        assert result.content == "hello"
        assert result.reasoning == ""


class TestThinkingTruncation:
    """Test mid-thinking truncation detection."""

    def test_raises_on_length_with_empty_content(self):
        client = LLMClient("http://127.0.0.1:8080")
        mock_resp = _make_response(
            content="",
            reasoning="long reasoning content that got truncated",
            finish_reason="length",
        )
        client._client.chat.completions.create = MagicMock(return_value=mock_resp)

        with pytest.raises(ThinkingTruncation) as exc_info:
            client.chat([{"role": "user", "content": "hi"}])

        assert exc_info.value.reasoning_len == len("long reasoning content that got truncated")

    def test_no_raise_on_length_with_content(self):
        client = LLMClient("http://127.0.0.1:8080")
        mock_resp = _make_response(
            content="partial answer",
            finish_reason="length",
        )
        client._client.chat.completions.create = MagicMock(return_value=mock_resp)

        result = client.chat([{"role": "user", "content": "hi"}])
        assert result.content == "partial answer"

    def test_no_raise_on_stop_reason(self):
        client = LLMClient("http://127.0.0.1:8080")
        mock_resp = _make_response(finish_reason="stop")
        client._client.chat.completions.create = MagicMock(return_value=mock_resp)

        result = client.chat([{"role": "user", "content": "hi"}])
        assert result.finish_reason == "stop"


class TestHealth:
    """Test LLMClient.health()."""

    def test_health_returns_true_on_ok(self):
        client = LLMClient("http://127.0.0.1:8080")
        with respx.mock:
            route = respx.get("http://127.0.0.1:8080/health").respond(
                json={"status": "ok"}
            )
            assert client.health() is True
            assert route.called

    def test_health_returns_false_on_non_ok(self):
        client = LLMClient("http://127.0.0.1:8080")
        with respx.mock:
            respx.get("http://127.0.0.1:8080/health").respond(
                json={"status": "error"}
            )
            assert client.health() is False

    def test_health_returns_false_on_error(self):
        client = LLMClient("http://127.0.0.1:8080")
        with respx.mock:
            respx.get("http://127.0.0.1:8080/health").mock(
                side_effect=ConnectionError("refused")
            )
            assert client.health() is False


class TestRetryBehavior:
    """Test HTTP 5xx retry with exponential backoff."""

    def test_retries_on_503(self):
        client = LLMClient("http://127.0.0.1:8080")
        call_count = 0

        def retry_handler(request):
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                return Response(status_code=503, json={"error": "service unavailable"})
            return Response(
                status_code=200,
                json={
                    "model": "qwen36",
                    "choices": [{
                        "message": {"content": "ok", "reasoning_content": ""},
                        "finish_reason": "stop",
                    }],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 5},
                },
            )

        with respx.mock:
            respx.post("http://127.0.0.1:8080/v1/chat/completions").mock(
                side_effect=retry_handler
            )
            result = client.chat([{"role": "user", "content": "hi"}])
            assert result.content == "ok"
            assert call_count == 4

    def test_max_retries_exhausted(self):
        client = LLMClient("http://127.0.0.1:8080")

        with respx.mock:
            respx.post("http://127.0.0.1:8080/v1/chat/completions").respond(
                status_code=503, json={"error": "service unavailable"}
            )
            with pytest.raises(Exception):
                client.chat([{"role": "user", "content": "hi"}])

    def test_connection_refused_raises_immediately(self):
        client = LLMClient("http://127.0.0.1:8080")

        with respx.mock:
            respx.post("http://127.0.0.1:8080/v1/chat/completions").mock(
                side_effect=ConnectionError("Connection refused")
            )
            with pytest.raises(APIConnectionError):
                client.chat([{"role": "user", "content": "hi"}])


class TestIntegration:
    """Integration tests gated on LLAMA_SERVER_URL env var."""

    @pytest.mark.integration
    def test_real_server_response(self):
        server_url = os.environ.get("LLAMA_SERVER_URL")
        if not server_url:
            pytest.skip("LLAMA_SERVER_URL not set")

        client = LLMClient(server_url)
        assert client.health(), "llama-server must be reachable"

        result = client.chat(
            [{"role": "user", "content": "Write one sentence about the sea"}],
            max_tokens=128,
        )
        assert result.content or result.reasoning, (
            "Response must have non-empty content or reasoning"
        )
