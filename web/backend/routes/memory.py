"""Optional MemPalace routes for project memory sync, wake-up, and search."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orchestrator.lib.control import write_compact_context
from orchestrator.lib.memory_palace import memory_provenance, memory_status, refresh_wakeup, search_memory, sync_project_memory
from orchestrator.lib.scrub import scrub_text
from web.backend.routes.projects import get_store
from web.backend.routes.stream import get_event_store

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


def _memory_event_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": result.get("project_id"),
        "available": bool(result.get("available")),
        "initialized": bool(result.get("initialized")),
        "wing": result.get("wing"),
        "cached_wakeup": result.get("cached_wakeup", ""),
        "last_search": result.get("last_search", ""),
        "wake_up_hash": result.get("wake_up_hash"),
        "wake_up_bytes": int(result.get("wake_up_bytes") or 0),
        "memory_refs": list(result.get("memory_refs") or []),
        "artifact_refs": list(result.get("memory_refs") or []),
    }


def _emit_memory_event(project_id: str, event_type: str, result: dict[str, Any], **fields: Any) -> None:
    project = _project(project_id)
    provenance = memory_provenance(project_id, project.project_dir)
    get_event_store().get_or_create(project_id).emit(
        event_type,
        **{**_memory_event_payload(result), "provenance": provenance},
        **fields,
    )


@router.get("/{project_id}/memory/status")
async def get_memory_status(project_id: str) -> dict[str, Any]:
    project = _project(project_id)
    result = memory_status(project_id, project.project_dir)
    _emit_memory_event(project_id, "memory_status", result)
    return result


@router.post("/{project_id}/memory/sync")
async def sync_memory(project_id: str) -> dict[str, Any]:
    project = _project(project_id)
    try:
        result = sync_project_memory(project_id, project.project_dir)
        result["compact_context"] = write_compact_context(project.project_dir, max_chars=18000)
        _emit_memory_event(
            project_id,
            "memory_refreshed",
            result,
            compact_context=result["compact_context"],
        )
        return result
    except RuntimeError as exc:
        get_event_store().get_or_create(project_id).emit("memory_error", project_id=project_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/memory/wake-up")
async def wake_up_memory(project_id: str) -> dict[str, Any]:
    project = _project(project_id)
    try:
        result = refresh_wakeup(project_id, project.project_dir)
        result["compact_context"] = write_compact_context(project.project_dir, max_chars=18000)
        _emit_memory_event(
            project_id,
            "memory_refreshed",
            result,
            compact_context=result["compact_context"],
        )
        return result
    except RuntimeError as exc:
        get_event_store().get_or_create(project_id).emit("memory_error", project_id=project_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/memory/search")
async def search_project_memory(project_id: str, body: MemorySearchRequest) -> dict[str, Any]:
    project = _project(project_id)
    try:
        result = search_memory(
            project_id,
            project.project_dir,
            query=body.query,
            room=body.room,
            results=body.results,
        )
        _emit_memory_event(
            project_id,
            "memory_search_completed",
            result,
            query=scrub_text(body.query),
            room=scrub_text(body.room) if body.room else None,
            results=body.results,
        )
        return result
    except RuntimeError as exc:
        get_event_store().get_or_create(project_id).emit("memory_error", project_id=project_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
