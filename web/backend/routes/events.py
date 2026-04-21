"""Durable run event ledger routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from orchestrator.lib.event_schema import EventValidationError, FutureSchemaVersionError, validate_event
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
    seen_event_ids: set[str] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        try:
            item = validate_event(item, require_run_id=True)
        except FutureSchemaVersionError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Event ledger contains unsupported schema at line {line_number}: {exc}",
            ) from exc
        except EventValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Event ledger contains invalid event at line {line_number}: {exc}",
            ) from exc
        event_id = item["event_id"]
        if event_id in seen_event_ids:
            continue
        seen_event_ids.add(event_id)
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
