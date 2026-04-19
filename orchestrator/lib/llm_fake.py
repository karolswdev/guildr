"""Fake LLM client for dry-run mode.

Returns canned responses keyed by role instead of calling a real server.
Used by the orchestrator's dry-run mode to validate pipeline logic
without burning tokens on actual LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from orchestrator.lib.llm import LLMResponse


@dataclass
class FakeLLMClient:
    """Deterministic LLM client that returns canned responses.

    Responses are keyed by role name. Each call increments a counter
    so callers can verify how many LLM calls were made.

    Attributes:
        responses: Mapping of role name -> canned LLMResponse.
        call_count: Number of times ``chat()`` has been invoked.
    """

    responses: dict[str, LLMResponse] = field(default_factory=dict)
    call_count: int = 0

    def chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 8192,
        temperature: float | None = None,
        **kw: Any,
    ) -> LLMResponse:
        """Return the canned response for the last message's role.

        Falls back to the ``"default"`` key if the role is not found.
        Raises ``KeyError`` if neither the role nor ``"default"`` exists.
        """
        self.call_count += 1

        # Extract role from the last user/assistant message
        role = "default"
        for msg in reversed(messages):
            if msg.get("role") in ("user", "assistant", "system"):
                role = msg["role"]
                break

        if role in self.responses:
            return self.responses[role]
        if "default" in self.responses:
            return self.responses["default"]
        raise KeyError(
            f"No canned response for role '{role}' and no 'default' response. "
            f"Available roles: {list(self.responses.keys())}"
        )

    def health(self) -> bool:
        """Always healthy in dry-run mode."""
        return True

    def was_called(self) -> bool:
        """Return True if at least one chat call was made."""
        return self.call_count > 0
