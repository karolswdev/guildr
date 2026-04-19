"""Project state persistence with atomic JSON writes."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class State:
    """Persists orchestrator state to JSON in .orchestrator/."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir.resolve()
        self.state_file = self.project_dir / ".orchestrator" / "state.json"
        self.current_phase: str | None = None
        self.sessions: dict[str, str] = {}
        self.retries: dict[str, int] = {}
        self.gates_approved: dict[str, bool] = {}

    # -- loading / saving ---------------------------------------------------

    def load(self) -> None:
        """Load state from disk. Tolerates missing file and missing keys."""
        if not self.state_file.exists():
            return
        raw = self.state_file.read_text(encoding="utf-8")
        data = json.loads(raw)
        self.current_phase = data.get("current_phase")
        self.sessions = data.get("sessions", {})
        self.retries = data.get("retries", {})
        self.gates_approved = data.get("gates_approved", {})

    def save(self) -> None:
        """Atomically write state: write to .tmp then rename."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_file.with_suffix(".tmp")
        data = {
            "current_phase": self.current_phase,
            "sessions": self.sessions,
            "retries": self.retries,
            "gates_approved": self.gates_approved,
        }
        tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.replace(tmp_path, self.state_file)
        except Exception:
            # Clean up tmp on failure
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    # -- arbitrary file helpers (project_dir-relative) -----------------------

    def read_file(self, name: str) -> str:
        """Read a file relative to project_dir."""
        path = self.project_dir / name
        return path.read_text(encoding="utf-8")

    def write_file(self, name: str, content: str) -> None:
        """Write a file relative to project_dir, creating parents as needed."""
        path = self.project_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
