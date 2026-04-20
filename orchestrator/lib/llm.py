"""LLM client for llama-server (OpenAI-compatible protocol)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
from openai._exceptions import APIStatusError, InternalServerError

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str
    reasoning: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    finish_reason: str


class ThinkingTruncation(Exception):
    """Raised when the model truncates mid-thinking (length finish with empty content)."""

    def __init__(self, reasoning_len: int) -> None:
        self.reasoning_len = reasoning_len
        super().__init__(
            f"Thinking truncated after {reasoning_len} reasoning tokens, content empty"
        )


class LLMClient:
    """Wraps the OpenAI SDK pointed at llama-server.

    Handles reasoning_content parsing, truncation detection, and retry logic.
    """

    def __init__(self, base_url: str, api_key: str = "placeholder") -> None:
        self._client = OpenAI(
            base_url=f"{base_url}/v1",
            api_key=api_key,
            timeout=600,
        )
        self.base_url = base_url

    def chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 8192,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Send a chat completion request.

        Raises:
            ThinkingTruncation: if finish_reason=length and content is empty.
            APIConnectionError: if connection is refused (not retried).
        """
        kwargs: dict = {
            "model": "qwen36",
            "max_tokens": max_tokens,
            "messages": messages,
            # Qwen thinking can consume the entire completion budget before
            # emitting artifact content. llama.cpp accepts this OpenAI extra
            # body field and disables that reasoning channel at the template.
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }
        if temperature is not None:
            kwargs["temperature"] = temperature

        backoff = 1.0
        for attempt in range(4):
            try:
                response = self._client.chat.completions.create(**kwargs)
                return self._parse_response(response)
            except (InternalServerError, APIStatusError) as exc:
                status = getattr(exc, "status_code", None)
                if status not in (500, 502, 503, 504):
                    raise
                if attempt == 3:
                    logger.error("LLM 5xx after 4 retries: %s", exc)
                    raise
                logger.warning("LLM 5xx (attempt %d/4), retrying in %.0fs: %s",
                               attempt + 1, backoff, exc)
                time.sleep(backoff)
                backoff *= 2
            except RateLimitError as exc:
                if attempt == 3:
                    logger.error("LLM rate limit after 4 retries: %s", exc)
                    raise
                logger.warning("LLM rate limit (attempt %d/4), retrying in %.0fs: %s",
                               attempt + 1, backoff, exc)
                time.sleep(backoff)
                backoff *= 2
            except APITimeoutError as exc:
                if attempt == 3:
                    logger.error("LLM timeout after 4 retries: %s", exc)
                    raise
                logger.warning("LLM timeout (attempt %d/4), retrying in %.0fs: %s",
                               attempt + 1, backoff, exc)
                time.sleep(backoff)
                backoff *= 2

    def _parse_response(self, response) -> LLMResponse:
        """Parse an OpenAI chat completion response into LLMResponse."""
        choice = response.choices[0]
        msg = choice.message

        reasoning = getattr(msg, "reasoning_content", "") or ""
        content = msg.content or ""

        # Detect mid-thinking truncation
        if choice.finish_reason == "length" and not content.strip():
            raise ThinkingTruncation(reasoning_len=len(reasoning))

        usage = response.usage or {}
        def _tok(key: str) -> int:
            if isinstance(usage, dict):
                return usage.get(key, 0)
            val = getattr(usage, key, None)
            return val if val else 0

        return LLMResponse(
            content=content,
            reasoning=reasoning,
            prompt_tokens=_tok("prompt_tokens"),
            completion_tokens=_tok("completion_tokens"),
            reasoning_tokens=_tok("reasoning_tokens"),
            finish_reason=choice.finish_reason or "stop",
        )

    def health(self) -> bool:
        """Check llama-server health via GET /health."""
        import httpx

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{self.base_url}/health")
                resp.raise_for_status()
                data = resp.json()
                return data.get("status") == "ok"
        except Exception:
            return False
