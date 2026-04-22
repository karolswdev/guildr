"""Demo artifact route (A-10 slice 2b).

GET /api/projects/{id}/demos/{demo_id}/{name:path}
    — serves binary files from .orchestrator/demos/<demo_id>/.

Demo IDs are structured (``demo_<hex16>``), and the relative artifact path is
restricted to a single subdirectory under the project's demo root. The route
mirrors the traversal-safety posture in ``artifacts.py`` but serves bytes
instead of text so it can deliver GIF/WEBM/PNG/ZIP payloads to the PWA.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)


DEMO_ID_PATTERN = re.compile(r"^demo_[A-Za-z0-9_-]{4,64}$")


def _default_projects_base() -> Path:
    return Path(os.environ.get("ORCHESTRATOR_PROJECTS_DIR", "/tmp/orchestrator-projects"))


class DemoArtifactStore:
    """Reads demo artifacts from ``.orchestrator/demos/<demo_id>/`` on disk."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base = Path(base_dir) if base_dir else _default_projects_base()

    def get_artifact_path(self, project_id: str, demo_id: str, name: str) -> Path:
        """Resolve a safe absolute path under the demo directory, or raise."""
        if not DEMO_ID_PATTERN.match(demo_id or ""):
            raise HTTPException(status_code=400, detail="Invalid demo id")

        project_dir = (self._base / project_id).resolve()
        demo_root = (project_dir / ".orchestrator" / "demos" / demo_id).resolve()

        rel = Path(name)
        if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
            raise HTTPException(status_code=400, detail="Invalid artifact path")

        file_path = (demo_root / rel).resolve()
        try:
            file_path.relative_to(demo_root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid artifact path")

        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail=f"Demo artifact not found: {name}")

        return file_path


_store = DemoArtifactStore()


def get_store() -> DemoArtifactStore:
    return _store


def _media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _build_router() -> Any:
    router_obj = APIRouter()

    @router_obj.get("/{project_id}/demos/{demo_id}/{name:path}")
    async def get_demo_artifact(project_id: str, demo_id: str, name: str) -> FileResponse:
        file_path = get_store().get_artifact_path(project_id, demo_id, name)
        return FileResponse(file_path, media_type=_media_type(file_path))

    return router_obj


router = _build_router()
