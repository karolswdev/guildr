"""Pool routing decision persistence.

Every `UpstreamPool.chat` call appends one decision to
``.orchestrator/logs/pool.jsonl``. Pairs with raw-io.jsonl + usage.jsonl
via the shared ``call_id`` so the rollup can answer "where did each
call land, and did it fall back."
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_POOL_FILENAME = "pool.jsonl"


def pool_log_path(project_dir: Path) -> Path:
    return project_dir / ".orchestrator" / "logs" / _POOL_FILENAME


def write_decision(
    project_dir: Path | None,
    *,
    call_id: str,
    role: str,
    chosen_endpoint: str | None,
    attempted_endpoints: list[str],
    fell_back: bool,
    reason: str = "",
) -> None:
    """Append one routing decision to ``.orchestrator/logs/pool.jsonl``.

    Silent no-op when ``project_dir`` is None — matches the usage_writer
    pattern so in-process tests without a project tree keep working.
    """
    if project_dir is None:
        return
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "call_id": call_id,
        "role": role,
        "chosen_endpoint": chosen_endpoint,
        "attempted_endpoints": attempted_endpoints,
        "fell_back": fell_back,
        "reason": reason,
    }
    path = pool_log_path(Path(project_dir))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
