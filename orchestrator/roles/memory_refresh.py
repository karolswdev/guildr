"""Memory refresh role backed by MemPalace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orchestrator.lib.control import write_compact_context
from orchestrator.lib.memory_palace import sync_project_memory, wakeup_path
from orchestrator.lib.state import State


@dataclass
class MemoryRefresh:
    """Sync project files into MemPalace and refresh the wake-up packet."""

    state: State
    step_config: dict[str, Any] | None = None
    _phase_logger: Any = None
    _phase: str = "memory_refresh"
    _role: str = "memory_refresh"

    def execute(self) -> str:
        try:
            result = sync_project_memory(None, self.state.project_dir)
            compact = write_compact_context(self.state.project_dir, max_chars=18000)
        except Exception as exc:
            self._emit_memory_error(exc)
            raise
        self._emit_memory_refreshed(result, compact)
        return str(wakeup_path(self.state.project_dir).relative_to(self.state.project_dir))

    def _emit_memory_refreshed(self, result: dict[str, Any], compact: dict[str, Any]) -> None:
        events = getattr(self.state, "events", None)
        if events is None or not hasattr(events, "emit"):
            return
        artifact_refs = [
            ref
            for ref in (".orchestrator/memory/wake-up.md", compact.get("path"))
            if isinstance(ref, str) and ref
        ]
        events.emit(
            "memory_refreshed",
            step=self._phase,
            role=self._role,
            project_id=result.get("project_id") or self.state.project_dir.name,
            available=bool(result.get("available")),
            initialized=bool(result.get("initialized")),
            wing=result.get("wing"),
            role_wings=dict(result.get("role_wings") or {}),
            cost_accounting=dict(result.get("cost_accounting") or {}),
            wake_up_hash=result.get("wake_up_hash"),
            wake_up_bytes=int(result.get("wake_up_bytes") or 0),
            memory_refs=list(result.get("memory_refs") or []),
            artifact_refs=artifact_refs,
            compact_context=compact,
        )

    def _emit_memory_error(self, exc: Exception) -> None:
        events = getattr(self.state, "events", None)
        if events is None or not hasattr(events, "emit"):
            return
        events.emit(
            "memory_error",
            step=self._phase,
            role=self._role,
            error=str(exc),
            memory_refs=[],
            artifact_refs=[],
        )
