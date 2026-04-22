"""Run control routes: inject instructions, compact context, resume phases."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orchestrator.lib.control import (
    PHASES,
    append_instruction,
    validate_phase,
    write_compact_context,
)
from orchestrator.lib.workflow import load_workflow, save_workflow, valid_start_steps
from web.backend.routes.projects import get_store

router = APIRouter()


class InjectInstructionRequest(BaseModel):
    instruction: str = Field(min_length=1)
    phase: str | None = None


class CompactContextRequest(BaseModel):
    max_chars: int = Field(default=18000, ge=2000, le=100000)


class ResumeRunRequest(BaseModel):
    start_at: str = Field(default="architect")
    instruction: str | None = None
    compact_context: bool = False
    max_chars: int = Field(default=18000, ge=2000, le=100000)


class WorkflowRequest(BaseModel):
    steps: list[dict[str, Any]]


def _project(project_id: str):
    project = get_store().get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/{project_id}/control/instructions")
async def inject_instruction(project_id: str, body: InjectInstructionRequest) -> dict[str, Any]:
    project = _project(project_id)
    try:
        entry = append_instruction(project.project_dir, body.instruction, phase=body.phase)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"project_id": project_id, "entry": entry}


@router.post("/{project_id}/control/compact")
async def compact_context(project_id: str, body: CompactContextRequest) -> dict[str, Any]:
    project = _project(project_id)
    result = write_compact_context(project.project_dir, max_chars=body.max_chars)
    return {"project_id": project_id, **result}


@router.post("/{project_id}/control/resume")
async def resume_run(project_id: str, body: ResumeRunRequest) -> dict[str, Any]:
    from web.backend.runner import start_run_async

    project = _project(project_id)
    valid_steps = valid_start_steps(project.project_dir)
    start_at = body.start_at.strip()
    if start_at not in valid_steps:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown run step '{start_at}'. Expected one of: {', '.join(valid_steps)}",
        )

    if body.instruction:
        phase = start_at if start_at in PHASES else None
        append_instruction(project.project_dir, body.instruction, phase=phase)
    if body.compact_context:
        write_compact_context(project.project_dir, max_chars=body.max_chars)

    effective_phase = start_at
    if start_at not in PHASES:
        if start_at == "approve_sprint_plan":
            effective_phase = "architect"
        elif start_at == "approve_review":
            effective_phase = "review"
    if effective_phase in PHASES:
        validate_phase(effective_phase)
        get_store().update_phase(project_id, effective_phase)

    started = await start_run_async(project_id, initial_idea=None, start_at=start_at)
    return {"project_id": project_id, "started": started, "start_at": start_at}


@router.get("/{project_id}/control/workflow")
async def get_workflow(project_id: str) -> dict[str, Any]:
    project = _project(project_id)
    return {
        "project_id": project_id,
        "steps": load_workflow(project.project_dir),
    }


@router.put("/{project_id}/control/workflow")
async def put_workflow(project_id: str, body: WorkflowRequest) -> dict[str, Any]:
    project = _project(project_id)
    try:
        steps = save_workflow(project.project_dir, body.steps)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"project_id": project_id, "steps": steps}


@router.post("/{project_id}/control/personas/synthesize")
async def synthesize_personas(project_id: str) -> dict[str, Any]:
    project = _project(project_id)
    from orchestrator.roles.persona_forum import PersonaForum
    from orchestrator.lib.state import State

    workflow = load_workflow(project.project_dir)
    persona_step = next((step for step in workflow if step["id"] == "persona_forum"), None)
    if persona_step is None:
        raise HTTPException(status_code=400, detail="persona_forum step not found in workflow")
    forum = PersonaForum(
        state=State(project.project_dir),
        step_config=persona_step.get("config", {}),
    )
    brief = (project.project_dir / "qwendea.md").read_text(encoding="utf-8")
    personas = forum._personas(brief)
    forum._persist_personas(personas)
    return {
        "project_id": project_id,
        "personas": personas,
        "steps": load_workflow(project.project_dir),
    }
