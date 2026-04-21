"""Tests for MemPalace integration routes."""

from __future__ import annotations

import tempfile
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from web.backend.app import create_app
from web.backend.routes.projects import ProjectStore


@pytest.fixture
def fresh_store() -> ProjectStore:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield ProjectStore(base_dir=tmpdir)


@pytest.fixture
def app(fresh_store: ProjectStore) -> FastAPI:
    with (
        patch("web.backend.routes.projects.get_store", return_value=fresh_store),
        patch("web.backend.routes.control.get_store", return_value=fresh_store),
        patch("web.backend.routes.logs.get_store", return_value=fresh_store),
        patch("web.backend.routes.memory.get_store", return_value=fresh_store),
    ):
        yield create_app()


@pytest.mark.asyncio
async def test_memory_status_route_returns_cached_memory(app: FastAPI, fresh_store: ProjectStore) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Memory Project", "initial_idea": "Build it"},
        )
        project_id = create_resp.json()["id"]
        project = fresh_store.get(project_id)
        assert project is not None
        memory_dir = project.project_dir / ".orchestrator" / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        (memory_dir / "wake-up.md").write_text("Wake-up text", encoding="utf-8")
        (memory_dir / "status.txt").write_text("Status text", encoding="utf-8")

        response = await client.get(f"/api/projects/{project_id}/memory/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cached_wakeup"] == "Wake-up text"
    assert payload["cached_status"] == "Status text"


@pytest.mark.asyncio
async def test_memory_sync_route_calls_backend(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Sync Project", "initial_idea": "Build it"},
        )
        project_id = create_resp.json()["id"]

        with patch(
            "web.backend.routes.memory.sync_project_memory",
            return_value={"project_id": project_id, "available": True, "wing": project_id, "wake_up": "L0"},
        ) as sync_mock:
            response = await client.post(f"/api/projects/{project_id}/memory/sync")

    assert response.status_code == 200
    assert response.json()["wake_up"] == "L0"
    assert sync_mock.called


@pytest.mark.asyncio
async def test_memory_search_route_returns_results(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Search Project", "initial_idea": "Build it"},
        )
        project_id = create_resp.json()["id"]

        with patch(
            "web.backend.routes.memory.search_memory",
            return_value={"project_id": project_id, "output": "Found it", "query": "GraphQL"},
        ):
            response = await client.post(
                f"/api/projects/{project_id}/memory/search",
                json={"query": "GraphQL", "results": 3},
            )

    assert response.status_code == 200
    assert response.json()["output"] == "Found it"
