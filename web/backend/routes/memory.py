"""Optional MemPalace routes for project memory sync, wake-up, and search."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orchestrator.lib.control import write_compact_context
from orchestrator.lib.memory_palace import memory_status, refresh_wakeup, search_memory, sync_project_memory
from web.backend.routes.projects import get_store

router = APIRouter()


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1)
    room: str | None = None
    results: int = Field(default=5, ge=1, le=20)


def _project(project_id: str):
    project = get_store().get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/memory/status")
async def get_memory_status(project_id: str) -> dict[str, Any]:
    project = _project(project_id)
    return memory_status(project_id, project.project_dir)


@router.post("/{project_id}/memory/sync")
async def sync_memory(project_id: str) -> dict[str, Any]:
    project = _project(project_id)
    try:
        result = sync_project_memory(project_id, project.project_dir)
        result["compact_context"] = write_compact_context(project.project_dir, max_chars=18000)
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/memory/wake-up")
async def wake_up_memory(project_id: str) -> dict[str, Any]:
    project = _project(project_id)
    try:
        result = refresh_wakeup(project_id, project.project_dir)
        result["compact_context"] = write_compact_context(project.project_dir, max_chars=18000)
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/memory/search")
async def search_project_memory(project_id: str, body: MemorySearchRequest) -> dict[str, Any]:
    project = _project(project_id)
    try:
        return search_memory(
            project_id,
            project.project_dir,
            query=body.query,
            room=body.room,
            results=body.results,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
