"""Tests for project routes."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from web.backend.app import create_app
from web.backend.routes.projects import ProjectStore


@pytest.fixture
def fresh_store() -> ProjectStore:
    """Create a fresh project store in a temp directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield ProjectStore(base_dir=tmpdir)


@pytest.fixture
def app(fresh_store: ProjectStore) -> FastAPI:
    """Create app with a fresh project store."""
    with patch("web.backend.routes.projects.get_store", return_value=fresh_store):
        yield create_app()


@pytest.mark.asyncio
async def test_create_project(app: FastAPI) -> None:
    """POST /api/projects creates a project and returns correct shape."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/projects",
            json={"name": "Test Project", "initial_idea": "Build a todo app"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Project"
    assert data["needs_quiz"] is False
    assert data["id"] is not None
    assert data["current_phase"] is None


@pytest.mark.asyncio
async def test_create_project_needs_quiz_when_no_idea(app: FastAPI) -> None:
    """Creating without initial_idea sets needs_quiz=True."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/projects",
            json={"name": "Quiz Project"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["needs_quiz"] is True


@pytest.mark.asyncio
async def test_list_projects(app: FastAPI) -> None:
    """GET /api/projects returns all projects."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create two projects
        await client.post("/api/projects", json={"name": "Project A"})
        await client.post("/api/projects", json={"name": "Project B"})

        response = await client.get("/api/projects")
    assert response.status_code == 200
    data = response.json()
    assert len(data["projects"]) == 2
    names = {p["name"] for p in data["projects"]}
    assert names == {"Project A", "Project B"}


@pytest.mark.asyncio
async def test_get_project(app: FastAPI) -> None:
    """GET /api/projects/{id} returns the correct project."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Get Me"},
        )
        project_id = create_resp.json()["id"]

        response = await client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Get Me"


@pytest.mark.asyncio
async def test_get_project_not_found(app: FastAPI) -> None:
    """GET /api/projects/{id} returns 404 for unknown id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/projects/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_start_project(app: FastAPI) -> None:
    """POST /api/projects/{id}/start enqueues the run and updates phase."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Start Me"},
        )
        project_id = create_resp.json()["id"]

        response = await client.post(f"/api/projects/{project_id}/start")
        assert response.status_code == 200
        data = response.json()
        assert data["started"] is True
        assert data["project_id"] == project_id

        # Verify phase was updated
        get_resp = await client.get(f"/api/projects/{project_id}")
        assert get_resp.json()["current_phase"] == "architect"


@pytest.mark.asyncio
async def test_start_project_not_found(app: FastAPI) -> None:
    """POST /api/projects/{id}/start returns 404 for unknown id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/projects/nonexistent/start")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_project_dir_created(app: FastAPI) -> None:
    """Creating a project writes a project directory."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/projects",
            json={"name": "Dir Test"},
        )
        project_id = response.json()["id"]

        # Verify via the API that the project exists
        get_resp = await client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 200


@pytest.mark.asyncio
async def test_initial_idea_written_to_disk(app: FastAPI) -> None:
    """Creating with initial_idea writes it to disk."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/projects",
            json={"name": "Idea Test", "initial_idea": "My idea text"},
        )
        project_id = response.json()["id"]

        # Verify the project exists and was created with the idea
        get_resp = await client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Idea Test"


def test_project_store_persists_metadata(fresh_store: ProjectStore) -> None:
    """Creating a project writes metadata that a new store can reload."""
    project = fresh_store.create("Persistent Project", "Build it.")

    reloaded = ProjectStore(base_dir=str(fresh_store._base))
    recovered = reloaded.get(project.id)

    assert recovered is not None
    assert recovered.name == "Persistent Project"
    assert recovered.needs_quiz is False
    assert recovered.created_at == project.created_at


def test_project_store_recovers_legacy_project(tmp_path: Path) -> None:
    """Existing project dirs without metadata should still load after restart."""
    project_dir = tmp_path / "f7508af9776b"
    (project_dir / ".orchestrator").mkdir(parents=True)
    (project_dir / "initial_idea.txt").write_text("Recovered idea\nMore text\n")
    (project_dir / "qwendea.md").write_text("# Recovered qwendea\n")
    (project_dir / ".orchestrator" / "state.json").write_text(
        json.dumps({"current_phase": "architect"}),
        encoding="utf-8",
    )

    store = ProjectStore(base_dir=str(tmp_path))
    recovered = store.get("f7508af9776b")

    assert recovered is not None
    assert recovered.name == "Recovered idea"
    assert recovered.needs_quiz is False
    assert recovered.current_phase == "architect"


@pytest.mark.asyncio
async def test_recovered_project_can_start(tmp_path: Path) -> None:
    """Recovered projects are addressable through the API start route."""
    project_dir = tmp_path / "f7508af9776b"
    (project_dir / ".orchestrator").mkdir(parents=True)
    (project_dir / "qwendea.md").write_text("# Project\n\nBuild it.\n")
    store = ProjectStore(base_dir=str(tmp_path))
    app = create_app()

    async def _fake_start(project_id: str, initial_idea=None):
        return True

    with (
        patch("web.backend.routes.projects.get_store", return_value=store),
        patch("web.backend.runner.start_run_async", side_effect=_fake_start),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/projects/f7508af9776b/start")
            get_resp = await client.get("/api/projects/f7508af9776b")

    assert response.status_code == 200
    assert response.json()["started"] is True
    assert get_resp.json()["current_phase"] == "architect"
