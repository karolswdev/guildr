"""Per-project agent log routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from orchestrator.lib.control import PHASES
from web.backend.routes.projects import get_store

router = APIRouter()


def _project_dir(project_id: str) -> Path:
    project = get_store().get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.project_dir


def _phase_log_path(project_dir: Path, phase: str) -> Path:
    if phase not in PHASES:
        raise HTTPException(status_code=404, detail="Unknown phase")
    return project_dir / ".orchestrator" / "logs" / f"{phase}.jsonl"


def _read_entries(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            entries.append(item)
    if limit > 0:
        return entries[-limit:]
    return entries


@router.get("/{project_id}/logs")
async def list_logs(project_id: str, limit: int = Query(default=20, ge=1, le=500)) -> dict[str, Any]:
    project_dir = _project_dir(project_id)
    phases: list[dict[str, Any]] = []
    for phase in PHASES:
        path = _phase_log_path(project_dir, phase)
        entries = _read_entries(path, limit=limit)
        phases.append({
            "phase": phase,
            "exists": path.exists(),
            "count": len(_read_entries(path, limit=0)),
            "entries": entries,
            "last_event": entries[-1] if entries else None,
        })
    return {"project_id": project_id, "phases": phases}


@router.get("/{project_id}/logs/{phase}")
async def get_phase_log(
    project_id: str,
    phase: str,
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    project_dir = _project_dir(project_id)
    path = _phase_log_path(project_dir, phase)
    entries = _read_entries(path, limit=limit)
    return {"project_id": project_id, "phase": phase, "entries": entries}
