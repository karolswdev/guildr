"""Durable run event ledger routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from web.backend.routes.projects import get_store
from web.backend.routes.stream import event_log_path

router = APIRouter()


def _project(project_id: str):
    project = get_store().get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/events")
async def list_events(
    project_id: str,
    limit: int = Query(default=200, ge=1, le=5000),
    event_type: str | None = Query(default=None),
    step: str | None = Query(default=None),
) -> dict[str, Any]:
    _project(project_id)
    path = event_log_path(project_id)
    if not path.exists():
        return {"project_id": project_id, "events": []}

    events: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        if event_type and item.get("type") != event_type:
            continue
        if step:
            current_step = item.get("name") or item.get("phase") or item.get("gate")
            if current_step != step:
                continue
        events.append(item)
    if limit > 0:
        events = events[-limit:]
    return {"project_id": project_id, "events": events}
