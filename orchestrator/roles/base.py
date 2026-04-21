"""Base role shared by all orchestrator roles."""

from __future__ import annotations

import logging
import time
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

    def __init__(
        self,
        llm: LLMClient,
        state: State,
        phase_logger: logging.Logger | None = None,
    ) -> None:
        self.llm = llm
        self.state = state
        self._phase_logger = phase_logger

    def _chat(
        self,
        messages: list[dict],
        **kw: Any,
    ) -> LLMResponse:
        """Send a chat completion request."""
        from orchestrator.lib.event_schema import new_event_id
        call_id = new_event_id()
        start = time.monotonic()
        try:
            response = self.llm.chat(messages, **kw)
            elapsed_ms = (time.monotonic() - start) * 1000
            from orchestrator.lib.usage import emit_llm_usage
            emit_llm_usage(
                self.state,
                self.llm,
                response,
                role=getattr(self, "_role", "unknown"),
                step=getattr(self, "_phase", ""),
                runtime_ms=elapsed_ms,
                call_id=call_id,
                attempt=kw.get("attempt"),
                atom_id=kw.get("atom_id"),
            )
            if self._phase_logger is not None:
                from orchestrator.lib.logger import log_llm_call
                log_llm_call(
                    self._phase_logger,
                    phase=getattr(self, "_phase", ""),
                    role=getattr(self, "_role", "unknown"),
                    messages=messages,
                    response=response,
                    latency_ms=elapsed_ms,
                    endpoint=getattr(self.llm, "base_url", None),
                    request_id=call_id,
                )
            return response
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            from orchestrator.lib.usage import emit_llm_usage, emit_provider_error
            emit_llm_usage(
                self.state,
                self.llm,
                None,
                role=getattr(self, "_role", "unknown"),
                step=getattr(self, "_phase", ""),
                runtime_ms=elapsed_ms,
                call_id=call_id,
                status="error",
                error=e,
                attempt=kw.get("attempt"),
                atom_id=kw.get("atom_id"),
            )
            emit_provider_error(
                self.state,
                provider_kind=type(self.llm).__name__,
                provider_name=type(self.llm).__name__,
                model="",
                role=getattr(self, "_role", "unknown"),
                step=getattr(self, "_phase", ""),
                runtime_ms=elapsed_ms,
                error=e,
                call_id=call_id,
            )
            if self._phase_logger is not None:
                from orchestrator.lib.logger import log_llm_error
                log_llm_error(
                    self._phase_logger,
                    phase=getattr(self, "_phase", ""),
                    role=getattr(self, "_role", "unknown"),
                    error=e,
                    latency_ms=elapsed_ms,
                )
            raise

    def _load_prompt(self, role: str, name: str) -> str:
        """Load a prompt template from roles/prompts/<role>/<name>.txt."""
        path = _PROMPT_DIR / role / f"{name}.txt"
        return path.read_text(encoding="utf-8")

    def _augment_prompt(self, prompt: str) -> str:
        """Append durable operator context for the current phase."""
        phase = getattr(self, "_phase", "")
        if not phase:
            return prompt
        from orchestrator.lib.control import append_operator_context

        return append_operator_context(self.state.project_dir, phase, prompt)
