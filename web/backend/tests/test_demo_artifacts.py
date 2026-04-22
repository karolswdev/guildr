"""Tests for the demo artifact route (A-10 slice 2b)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from web.backend.app import create_app


def _demo_dir(project_id: str, demo_id: str) -> Path:
    base = Path(os.environ["ORCHESTRATOR_PROJECTS_DIR"]) / project_id
    target = base / ".orchestrator" / "demos" / demo_id
    target.mkdir(parents=True, exist_ok=True)
    return target


@pytest.mark.asyncio
async def test_demo_artifact_serves_binary_with_mime() -> None:
    project_id = "demo-proj-1"
    demo_id = "demo_abcdef1234567890"
    payload = b"GIF89a\x00demo-binary\x00"
    (_demo_dir(project_id, demo_id) / "demo.gif").write_bytes(payload)

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/projects/{project_id}/demos/{demo_id}/demo.gif")

    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["content-type"] == "image/gif"


@pytest.mark.asyncio
async def test_demo_artifact_serves_nested_file() -> None:
    project_id = "demo-proj-2"
    demo_id = "demo_cafef00d00000001"
    nested = _demo_dir(project_id, demo_id) / "playwright-report" / "index.html"
    nested.parent.mkdir(parents=True, exist_ok=True)
    nested.write_text("<html><body>ok</body></html>", encoding="utf-8")

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            f"/api/projects/{project_id}/demos/{demo_id}/playwright-report/index.html"
        )

    assert response.status_code == 200
    assert "<body>ok</body>" in response.text


@pytest.mark.asyncio
async def test_demo_artifact_rejects_path_traversal() -> None:
    project_id = "demo-proj-3"
    demo_id = "demo_deadbeef00000002"
    _demo_dir(project_id, demo_id)

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            f"/api/projects/{project_id}/demos/{demo_id}/../../../etc/passwd"
        )

    assert response.status_code in (400, 404)


@pytest.mark.asyncio
async def test_demo_artifact_rejects_invalid_demo_id() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/projects/demo-proj-4/demos/not-a-demo-id/demo.gif"
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_demo_artifact_404_on_missing_file() -> None:
    project_id = "demo-proj-5"
    demo_id = "demo_feedface00000003"
    _demo_dir(project_id, demo_id)

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            f"/api/projects/{project_id}/demos/{demo_id}/missing.webm"
        )

    assert response.status_code == 404
