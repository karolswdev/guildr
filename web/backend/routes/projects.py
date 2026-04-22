"""Project lifecycle routes.

POST   /api/projects            — create project
GET    /api/projects            — list projects
GET    /api/projects/{id}       — get project metadata
POST   /api/projects/{id}/start — begin orchestrator run
"""

from __future__ import annotations

import logging
import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from orchestrator.lib.scrub import scrub_text

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


class PersonaBrief(BaseModel):
    name: str
    archetype: str | None = None
    mandate: str | None = None
    stance: str | None = None
    veto_scope: str | None = None


class ProjectBriefResponse(BaseModel):
    id: str
    name: str
    title: str
    summary: str
    founding_team: list[PersonaBrief] = Field(default_factory=list)
    forum_excerpt: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class StartRequest(BaseModel):
    # Idle-RPG default: don't block on gates unless the caller explicitly
    # opts in. The PWA surfaces this as a "Gate my approval at each phase"
    # toggle on the start panel.
    require_human_approval: bool = False


class StartResponse(BaseModel):
    started: bool
    project_id: str
    require_human_approval: bool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metadata_path(project_dir: Path) -> Path:
    return project_dir / ".orchestrator" / "project.json"


def _read_current_phase(project_dir: Path) -> str | None:
    state_path = project_dir / ".orchestrator" / "state.json"
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    phase = data.get("current_phase")
    return phase if isinstance(phase, str) and phase else None


def _fallback_name(project_dir: Path) -> str:
    for filename in ("initial_idea.txt", "qwendea.md"):
        path = project_dir / filename
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip().lstrip("#").strip()
                if line:
                    return line[:80]
        except OSError:
            continue
    return project_dir.name


def _read_text(path: Path, limit: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


def _brief_title_and_summary(project: Project) -> tuple[str, str, list[str]]:
    source_refs: list[str] = []
    raw = _read_text(project.project_dir / "qwendea.md")
    if raw:
        source_refs.append("artifact:qwendea.md")
    if not raw:
        raw = _read_text(project.project_dir / "initial_idea.txt")
        if raw:
            source_refs.append("artifact:initial_idea.txt")
    lines = [line.strip().lstrip("#").strip() for line in raw.splitlines() if line.strip()]
    title = scrub_text(lines[0] if lines else project.name)
    summary = scrub_text(" ".join(lines[1:4]) if len(lines) > 1 else title)
    return title[:120], summary[:420], source_refs


def _founding_team(project_dir: Path) -> tuple[list[PersonaBrief], list[str]]:
    path = project_dir / "FOUNDING_TEAM.json"
    if not path.exists():
        return [], []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], []
    personas_raw = raw.get("personas") if isinstance(raw, dict) else None
    if not isinstance(personas_raw, list):
        return [], []
    personas: list[PersonaBrief] = []
    for item in personas_raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        personas.append(
            PersonaBrief(
                name=scrub_text(name)[:80],
                archetype=scrub_text(item["archetype"]) if isinstance(item.get("archetype"), str) else None,
                mandate=scrub_text(item["mandate"]) if isinstance(item.get("mandate"), str) else None,
                stance=scrub_text(item["stance"]) if isinstance(item.get("stance"), str) else None,
                veto_scope=scrub_text(item["veto_scope"]) if isinstance(item.get("veto_scope"), str) else None,
            )
        )
    return personas[:8], ["artifact:FOUNDING_TEAM.json"] if personas else []


def _forum_excerpt(project_dir: Path) -> tuple[str | None, list[str]]:
    text = _read_text(project_dir / "PERSONA_FORUM.md", limit=1200).strip()
    if not text:
        return None, []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return scrub_text(" ".join(lines[:5]))[:520], ["artifact:PERSONA_FORUM.md"]


def _created_at_from_dir(project_dir: Path) -> str:
    try:
        return datetime.fromtimestamp(project_dir.stat().st_ctime, timezone.utc).isoformat()
    except OSError:
        return _now_iso()


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
    return Path(os.environ.get("ORCHESTRATOR_PROJECTS_DIR", "/tmp/orchestrator-projects"))


def _recover_legacy_projects_enabled() -> bool:
    """Whether dirs without project.json should appear in the project list."""
    return os.environ.get("ORCHESTRATOR_RECOVER_LEGACY_PROJECTS") == "1"


class ProjectStore:
    """Project store backed by project directories on disk."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base = Path(base_dir) if base_dir else _default_projects_base()
        self._projects: dict[str, Project] = {}
        self._lock = threading.Lock()
        self._load_existing_projects()

    def _load_existing_projects(self) -> None:
        """Rebuild the in-memory index from existing project directories."""
        if not self._base.exists():
            return
        for project_dir in sorted(self._base.iterdir()):
            if not project_dir.is_dir():
                continue
            project = self._load_project_dir(project_dir)
            if project is None:
                continue
            self._projects[project.id] = project

    def _load_project_dir(self, project_dir: Path) -> Project | None:
        """Load metadata for one project directory.

        New projects have ``.orchestrator/project.json``. Legacy dirs
        without metadata are only recovered when explicitly enabled so
        test debris and unrelated temp dirs do not pollute the PWA list.
        """
        meta_path = _metadata_path(project_dir)
        if not meta_path.exists() and not _recover_legacy_projects_enabled():
            logger.debug("Skipping project dir without metadata: %s", project_dir)
            return None

        metadata: dict[str, Any] = {}
        if meta_path.exists():
            try:
                raw = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    metadata = raw
            except (json.JSONDecodeError, OSError):
                logger.warning("Ignoring unreadable project metadata: %s", meta_path)
                return None

        project_id = metadata.get("id") if isinstance(metadata.get("id"), str) else project_dir.name
        name = metadata.get("name") if isinstance(metadata.get("name"), str) else _fallback_name(project_dir)
        created_at = (
            metadata.get("created_at")
            if isinstance(metadata.get("created_at"), str)
            else _created_at_from_dir(project_dir)
        )
        current_phase = _read_current_phase(project_dir)
        if current_phase is None and isinstance(metadata.get("current_phase"), str):
            current_phase = metadata["current_phase"]

        has_seed = (project_dir / "qwendea.md").exists() or (project_dir / "initial_idea.txt").exists()
        needs_quiz = metadata.get("needs_quiz") if isinstance(metadata.get("needs_quiz"), bool) else not has_seed

        return Project(
            id=project_id,
            name=name,
            project_dir=project_dir,
            needs_quiz=needs_quiz,
            current_phase=current_phase,
            created_at=created_at,
        )

    def _write_metadata(self, project: Project) -> None:
        meta_path = _metadata_path(project.project_dir)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(
                {
                    "id": project.id,
                    "name": project.name,
                    "needs_quiz": project.needs_quiz,
                    "current_phase": project.current_phase,
                    "created_at": project.created_at,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _refresh_project_locked(self, project: Project) -> Project:
        """Refresh volatile fields from orchestrator state on disk."""
        current_phase = _read_current_phase(project.project_dir)
        if current_phase is not None and current_phase != project.current_phase:
            project.current_phase = current_phase
            self._write_metadata(project)
        return project

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
            self._write_metadata(project)

        logger.info("Created project '%s' (%s) at %s", name, pid, project_dir)
        return project

    def get(self, project_id: str) -> Project | None:
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return None
            return self._refresh_project_locked(project)

    def list_all(self) -> list[Project]:
        with self._lock:
            for project in self._projects.values():
                self._refresh_project_locked(project)
            return sorted(
                self._projects.values(),
                key=lambda p: p.created_at,
                reverse=True,
            )

    def update_phase(self, project_id: str, phase: str) -> None:
        with self._lock:
            proj = self._projects.get(project_id)
            if proj is None:
                raise HTTPException(status_code=404, detail="Project not found")
            proj.current_phase = phase
            self._write_metadata(proj)

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

    @router_obj.get("/{project_id}/brief", response_model=ProjectBriefResponse)
    async def get_project_brief(project_id: str) -> ProjectBriefResponse:
        store = get_store()
        proj = store.get(project_id)
        if proj is None:
            raise HTTPException(status_code=404, detail="Project not found")
        title, summary, source_refs = _brief_title_and_summary(proj)
        founding_team, team_refs = _founding_team(proj.project_dir)
        forum_excerpt, forum_refs = _forum_excerpt(proj.project_dir)
        return ProjectBriefResponse(
            id=proj.id,
            name=proj.name,
            title=title,
            summary=summary,
            founding_team=founding_team,
            forum_excerpt=forum_excerpt,
            source_refs=[*source_refs, *team_refs, *forum_refs],
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
    async def start_project(
        project_id: str, body: StartRequest | None = None
    ) -> StartResponse:
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

        req = body or StartRequest()
        # initial_idea was persisted to project_dir/initial_idea.txt by
        # ProjectStore.create; the runner re-reads it from there.
        started = await start_run_async(
            project_id,
            initial_idea=None,
            require_human_approval=req.require_human_approval,
        )
        return StartResponse(
            started=started,
            project_id=project_id,
            require_human_approval=req.require_human_approval,
        )

    return router_obj


# Module-level router (populated at import time by app.py)
router = _setup_routes(None)
