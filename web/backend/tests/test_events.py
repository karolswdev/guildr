"""Tests for durable run event ledger routes."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from web.backend.app import create_app
from web.backend.routes.projects import ProjectStore
from web.backend.routes.stream import SimpleEventBus, event_log_path


@pytest.fixture
def fresh_store() -> ProjectStore:
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("web.backend.routes.stream._projects_base", return_value=Path(tmpdir)):
            yield ProjectStore(base_dir=tmpdir)


@pytest.fixture
def app(fresh_store: ProjectStore) -> FastAPI:
    with (
        patch("web.backend.routes.projects.get_store", return_value=fresh_store),
        patch("web.backend.routes.control.get_store", return_value=fresh_store),
        patch("web.backend.routes.logs.get_store", return_value=fresh_store),
        patch("web.backend.routes.memory.get_store", return_value=fresh_store),
        patch("web.backend.routes.events.get_store", return_value=fresh_store),
        patch("web.backend.routes.stream._projects_base", return_value=fresh_store._base),
    ):
        yield create_app()


@pytest.mark.asyncio
async def test_event_route_returns_persisted_run_events(app: FastAPI, fresh_store: ProjectStore) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Replay Project", "initial_idea": "Build it"},
        )
        project_id = create_resp.json()["id"]

        bus = SimpleEventBus(project_id=project_id)
        bus.emit("run_started", project_id=project_id)
        bus.emit("phase_start", name="architect")
        bus.emit("phase_done", name="architect")

        response = await client.get(f"/api/projects/{project_id}/events?step=architect")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["events"]) == 2
    assert payload["events"][0]["type"] == "phase_start"
    assert payload["events"][1]["type"] == "phase_done"
    assert event_log_path(project_id).exists()
