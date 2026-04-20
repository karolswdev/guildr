"""Tests for project artifact routes."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from web.backend.app import create_app


@pytest.mark.asyncio
async def test_artifact_route_serves_nested_source_file() -> None:
    project_id = "nested-source"
    project_dir = Path(os.environ["ORCHESTRATOR_PROJECTS_DIR"]) / project_id
    source = project_dir / "src" / "engine" / "Game.ts"
    source.parent.mkdir(parents=True)
    source.write_text("export const ok = true;\n", encoding="utf-8")

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            f"/api/projects/{project_id}/artifacts/src%2Fengine%2FGame.ts"
        )

    assert response.status_code == 200
    assert "export const ok" in response.json()


@pytest.mark.asyncio
async def test_artifact_route_rejects_traversal() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/projects/nested-source/artifacts/../secret.txt"
        )

    assert response.status_code in (400, 404)
