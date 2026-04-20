"""Artifact routes for project files.

GET /api/projects/{id}/tree               — project file tree
GET /api/projects/{id}/artifacts/{name}   — fetch artifact or source file
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# -- in-memory artifact store ------------------------------------------------

KNOWN_ARTIFACTS = frozenset([
    "qwendea.md",
    "sprint-plan.md",
    "TEST_REPORT.md",
    "REVIEW.md",
    "DEPLOY.md",
])


def _default_projects_base() -> Path:
    """Same env-driven default as ProjectStore — must agree or artifacts
    are read from a different directory than they were written to."""
    import os
    return Path(os.environ.get("ORCHESTRATOR_PROJECTS_DIR", "/tmp/orchestrator-projects"))


class ArtifactStore:
    """Reads artifacts from project directories on disk."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base = Path(base_dir) if base_dir else _default_projects_base()

    def get_tree(self, project_id: str) -> list[dict[str, Any]]:
        """Return a file tree for the project directory.

        Skips ``.git/`` and ``.orchestrator/`` since those are bookkeeping
        the user doesn't want to scroll through in the PWA.
        """
        project_dir = self._base / project_id
        if not project_dir.exists():
            return []

        skip_prefixes = (".git", ".orchestrator", "__pycache__")
        result: list[dict[str, Any]] = []
        for item in sorted(project_dir.rglob("*")):
            rel = item.relative_to(project_dir)
            if rel.parts and rel.parts[0] in skip_prefixes:
                continue
            result.append({
                "path": str(rel),
                "is_dir": item.is_dir(),
            })
        return result

    def get_artifact(self, project_id: str, name: str) -> str:
        """Read an artifact file from the project directory."""
        project_dir = self._base / project_id

        # Only allow known artifacts and files within the project dir
        if name not in KNOWN_ARTIFACTS:
            # Allow source files too, but prevent directory traversal
            safe_name = Path(name).name
            file_path = project_dir / safe_name
            if not file_path.exists() or not file_path.is_file():
                raise HTTPException(
                    status_code=404,
                    detail=f"Artifact not found: {name}",
                )
        else:
            file_path = project_dir / name

        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to read artifact %s: %s", name, e)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read artifact: {e}",
            )


# -- singleton store ---------------------------------------------------------

_store = ArtifactStore()


def get_store() -> ArtifactStore:
    return _store


# -- routes ------------------------------------------------------------------


def _setup_routes(router_obj: Any) -> Any:
    """Attach routes to the given router."""
    from fastapi import APIRouter

    router_obj = APIRouter()

    @router_obj.get("/{project_id}/tree")
    async def project_tree(project_id: str) -> list[dict[str, Any]]:
        store = get_store()
        return store.get_tree(project_id)

    @router_obj.get("/{project_id}/artifacts/{name}")
    async def get_artifact(project_id: str, name: str) -> str:
        store = get_store()
        return store.get_artifact(project_id, name)

    return router_obj


router = _setup_routes(None)
