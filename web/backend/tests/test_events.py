"""Tests for durable run event ledger routes."""

from __future__ import annotations

import json
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
    assert all("event_id" in event for event in payload["events"])
    assert all(event["schema_version"] == 1 for event in payload["events"])
    assert all(event["run_id"] == project_id for event in payload["events"])
    assert event_log_path(project_id).exists()


@pytest.mark.asyncio
async def test_event_route_deduplicates_by_event_id(app: FastAPI, fresh_store: ProjectStore) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Replay Project", "initial_idea": "Build it"},
        )
        project_id = create_resp.json()["id"]

        bus = SimpleEventBus(project_id=project_id)
        bus.emit("phase_start", event_id="01ARZ3NDEKTSV4RRFFQ69G5FAV", name="architect")
        bus.emit("phase_start", event_id="01ARZ3NDEKTSV4RRFFQ69G5FAV", name="architect")

        response = await client.get(f"/api/projects/{project_id}/events")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["events"]) == 1
    assert payload["events"][0]["event_id"] == "01ARZ3NDEKTSV4RRFFQ69G5FAV"


@pytest.mark.asyncio
async def test_event_route_rejects_invalid_ledger_event(app: FastAPI, fresh_store: ProjectStore) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Replay Project", "initial_idea": "Build it"},
        )
        project_id = create_resp.json()["id"]
        path = event_log_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"type": "phase_start", "run_id": project_id}) + "\n", encoding="utf-8")

        response = await client.get(f"/api/projects/{project_id}/events")

    assert response.status_code == 422
    assert "event_id is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_event_route_rejects_future_schema_version(app: FastAPI, fresh_store: ProjectStore) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Replay Project", "initial_idea": "Build it"},
        )
        project_id = create_resp.json()["id"]
        path = event_log_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "event_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                    "schema_version": 999,
                    "run_id": project_id,
                    "ts": "2026-04-20T00:00:00+00:00",
                    "type": "phase_start",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        response = await client.get(f"/api/projects/{project_id}/events")

    assert response.status_code == 422
    assert "unsupported schema" in response.json()["detail"]
