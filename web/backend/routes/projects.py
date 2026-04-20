"""Project lifecycle routes.

POST   /api/projects            — create project
GET    /api/projects            — list projects
GET    /api/projects/{id}       — get project metadata
POST   /api/projects/{id}/start — begin orchestrator run
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field
from starlette.responses import PlainTextResponse

logger = logging.getLogger(__name__)

# -- models ------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    name: str
    initial_idea: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    needs_quiz: bool
    current_phase: str | None = None
    created_at: str = field(default_factory=lambda: _now_iso())


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]


class StartResponse(BaseModel):
    started: bool
    project_id: str


def _now_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# -- in-memory store ---------------------------------------------------------


@dataclass
class Project:
    id: str
    name: str
    project_dir: Path
    needs_quiz: bool
    current_phase: str | None = None
    created_at: str = ""


def _default_projects_base() -> Path:
    """Resolve the on-disk root for projects.

    ORCHESTRATOR_PROJECTS_DIR overrides the default so the demo recorder
    (and tests) can isolate runs in a tempdir without colliding with a
    user's real /tmp/orchestrator-projects state.
    """
    import os
    return Path(os.environ.get("ORCHESTRATOR_PROJECTS_DIR", "/tmp/orchestrator-projects"))


class ProjectStore:
    """In-memory project store with directory creation."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base = Path(base_dir) if base_dir else _default_projects_base()
        self._projects: dict[str, Project] = {}
        self._lock = threading.Lock()

    def create(self, name: str, initial_idea: str | None = None) -> Project:
        pid = uuid.uuid4().hex[:12]
        project_dir = self._base / pid
        project_dir.mkdir(parents=True, exist_ok=True)

        # Write initial_idea if provided
        if initial_idea:
            (project_dir / "initial_idea.txt").write_text(
                initial_idea, encoding="utf-8"
            )

        project = Project(
            id=pid,
            name=name,
            project_dir=project_dir,
            needs_quiz=initial_idea is None,
            created_at=_now_iso(),
        )

        with self._lock:
            self._projects[pid] = project

        logger.info("Created project '%s' (%s) at %s", name, pid, project_dir)
        return project

    def get(self, project_id: str) -> Project | None:
        with self._lock:
            return self._projects.get(project_id)

    def list_all(self) -> list[Project]:
        with self._lock:
            return list(self._projects.values())

    def update_phase(self, project_id: str, phase: str) -> None:
        with self._lock:
            proj = self._projects.get(project_id)
            if proj is None:
                raise HTTPException(status_code=404, detail="Project not found")
            proj.current_phase = phase

    def start_run(self, project_id: str) -> bool:
        """Enqueue orchestrator run. Returns True if started."""
        proj = self.get(project_id)
        if proj is None:
            raise HTTPException(status_code=404, detail="Project not found")

        # In a real implementation, this would enqueue the orchestrator run.
        # For now, update phase and return success.
        self.update_phase(project_id, "architect")
        return True


# -- singleton store ---------------------------------------------------------

_store = ProjectStore()


def get_store() -> ProjectStore:
    return _store


# -- routes ------------------------------------------------------------------

router = None  # type: ignore  # populated below by FastAPI


def _setup_routes(router_obj: Any) -> Any:
    """Attach routes to the given router. Called from app.py."""
    from fastapi import APIRouter

    router_obj = APIRouter()

    @router_obj.post("", response_model=ProjectResponse)
    async def create_project(body: CreateProjectRequest) -> ProjectResponse:
        store = get_store()
        proj = store.create(body.name, body.initial_idea)
        return ProjectResponse(
            id=proj.id,
            name=proj.name,
            needs_quiz=proj.needs_quiz,
            current_phase=proj.current_phase,
            created_at=proj.created_at,
        )

    @router_obj.get("", response_model=ProjectListResponse)
    async def list_projects() -> ProjectListResponse:
        store = get_store()
        projects = store.list_all()
        return ProjectListResponse(
            projects=[
                ProjectResponse(
                    id=p.id,
                    name=p.name,
                    needs_quiz=p.needs_quiz,
                    current_phase=p.current_phase,
                    created_at=p.created_at,
                )
                for p in projects
            ]
        )

    @router_obj.get("/{project_id}", response_model=ProjectResponse)
    async def get_project(project_id: str) -> ProjectResponse:
        store = get_store()
        proj = store.get(project_id)
        if proj is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectResponse(
            id=proj.id,
            name=proj.name,
            needs_quiz=proj.needs_quiz,
            current_phase=proj.current_phase,
            created_at=proj.created_at,
        )

    @router_obj.post("/{project_id}/start", response_model=StartResponse)
    async def start_project(project_id: str) -> StartResponse:
        # Lazy import to avoid a hard dependency cycle: runner.py imports
        # this module's get_event_store sibling, and importing runner at
        # module load time would force the engine + every role to load
        # before the FastAPI app is even built.
        from web.backend.runner import start_run_async

        store = get_store()
        proj = store.get(project_id)
        if proj is None:
            raise HTTPException(status_code=404, detail="Project not found")
        store.update_phase(project_id, "architect")

        # Fire-and-forget: the run streams events via the SSE bus.
        # PWA gate-approval flow is not wired yet, so the engine runs
        # with require_human_approval=False (set inside runner.py).
        # initial_idea was persisted to project_dir/initial_idea.txt by
        # ProjectStore.create; the runner re-reads it from there.
        started = await start_run_async(project_id, initial_idea=None)
        return StartResponse(started=started, project_id=project_id)

    return router_obj


# Module-level router (populated at import time by app.py)
router = _setup_routes(None)
