"""Tests for durable agent log routes."""

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
    ):
        yield create_app()


@pytest.mark.asyncio
async def test_logs_routes_return_phase_entries(app: FastAPI, fresh_store: ProjectStore) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Log Project", "initial_idea": "Build it"},
        )
        project_id = create_resp.json()["id"]
        project = fresh_store.get(project_id)
        assert project is not None

        logs_dir = project.project_dir / ".orchestrator" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "architect.jsonl").write_text(
            '{"ts":"2026-04-20T00:00:00Z","level":"INFO","event":"phase_start","message":"Starting architect"}\n'
            '{"ts":"2026-04-20T00:00:01Z","level":"INFO","event":"phase_done","message":"Architect done"}\n',
            encoding="utf-8",
        )

        list_resp = await client.get(f"/api/projects/{project_id}/logs")
        detail_resp = await client.get(f"/api/projects/{project_id}/logs/architect")

    assert list_resp.status_code == 200
    phases = {item["phase"]: item for item in list_resp.json()["phases"]}
    assert phases["architect"]["count"] == 2
    assert phases["architect"]["last_event"]["event"] == "phase_done"

    assert detail_resp.status_code == 200
    assert len(detail_resp.json()["entries"]) == 2
    assert detail_resp.json()["entries"][0]["event"] == "phase_start"
