"""Tests for operator intent routes."""

from __future__ import annotations

import tempfile
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from web.backend.app import create_app
from web.backend.routes.projects import ProjectStore
from web.backend.routes.stream import event_log_path


@pytest.fixture
def fresh_store() -> ProjectStore:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield ProjectStore(base_dir=tmpdir)


@pytest.fixture
def app(fresh_store: ProjectStore) -> FastAPI:
    with (
        patch("web.backend.routes.projects.get_store", return_value=fresh_store),
        patch("web.backend.routes.intents.get_store", return_value=fresh_store),
        patch("web.backend.routes.stream._projects_base", return_value=fresh_store._base),
    ):
        yield create_app()


@pytest.mark.asyncio
async def test_operator_intent_route_persists_scrubbed_event(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post("/api/projects", json={"name": "Intent Project"})
        project_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/projects/{project_id}/intents",
            json={
                "kind": "intercept",
                "atom_id": "implementation",
                "payload": {
                    "instruction": "Pause after this atom and ask me.",
                    "api_key": "sk-live-value",
                    "nested": {"Authorization": "Bearer secret"},
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"] is True
    assert payload["kind"] == "intercept"

    event_text = event_log_path(project_id).read_text(encoding="utf-8")
    assert "operator_intent" in event_text
    assert "implementation" in event_text
    assert "Pause after this atom" in event_text
    assert "sk-live-value" not in event_text
    assert "Bearer secret" not in event_text
    assert "[redacted]" in event_text
