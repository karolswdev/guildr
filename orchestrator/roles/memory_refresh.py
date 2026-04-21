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
        sync_project_memory(None, self.state.project_dir)
        write_compact_context(self.state.project_dir, max_chars=18000)
        return str(wakeup_path(self.state.project_dir).relative_to(self.state.project_dir))
