"""Usage event persistence.

Every normalized ``usage_recorded`` payload also lands on disk at
``.orchestrator/logs/usage.jsonl`` alongside ``raw-io.jsonl``. Together
they give us the bijection needed to answer "how much did this run cost"
without replaying the event bus.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_USAGE_FILENAME = "usage.jsonl"


def usage_path(project_dir: Path) -> Path:
    return project_dir / ".orchestrator" / "logs" / _USAGE_FILENAME


def write_usage(project_dir: Path | None, payload: dict[str, Any]) -> None:
    """Append one usage payload to ``.orchestrator/logs/usage.jsonl``.

    Silent no-op when ``project_dir`` is None — some usage emit sites
    (e.g. the ingestion quiz) only have an event bus, not a project dir,
    and we'd rather drop the on-disk copy than crash the call.
    """
    if project_dir is None:
        return
    path = usage_path(Path(project_dir))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
