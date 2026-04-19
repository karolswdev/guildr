"""Base role shared by all orchestrator roles."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from orchestrator.lib.llm import LLMClient, LLMResponse
from orchestrator.lib.state import State

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


class BaseRole:
    """Shared base for all orchestrator roles.

    Provides LLM chat, prompt loading, and state access.
    """

    def __init__(self, llm: LLMClient, state: State) -> None:
        self.llm = llm
        self.state = state

    def _chat(
        self,
        messages: list[dict],
        **kw: Any,
    ) -> LLMResponse:
        """Send a chat completion request."""
        return self.llm.chat(messages, **kw)

    def _load_prompt(self, role: str, name: str) -> str:
        """Load a prompt template from roles/prompts/<role>/<name>.txt."""
        path = _PROMPT_DIR / role / f"{name}.txt"
        return path.read_text(encoding="utf-8")
