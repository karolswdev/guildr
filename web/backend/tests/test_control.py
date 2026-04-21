"""Tests for run control routes."""

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
async def test_control_instruction_route_persists_operator_note(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post("/api/projects", json={"name": "Control Project"})
        project_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/projects/{project_id}/control/instructions",
            json={"instruction": "Keep context lean and preserve the PRD."},
        )

    assert response.status_code == 200
    assert response.json()["entry"]["instruction"] == "Keep context lean and preserve the PRD."


@pytest.mark.asyncio
async def test_control_compact_route_generates_framework_summary(
    app: FastAPI,
    fresh_store: ProjectStore,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Node Project", "initial_idea": "Build it"},
        )
        project_id = create_resp.json()["id"]
        project = fresh_store.get(project_id)
        assert project is not None
        (project.project_dir / "package.json").write_text(
            '{"name":"node-project","packageManager":"npm@10","scripts":{"dev":"vite","test":"vitest"}}',
            encoding="utf-8",
        )
        (project.project_dir / "PRD.md").write_text("# PRD\n\nShip the thing.\n", encoding="utf-8")
        memory_dir = project.project_dir / ".orchestrator" / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        (memory_dir / "wake-up.md").write_text("Wake-up text from palace.", encoding="utf-8")

        response = await client.post(
            f"/api/projects/{project_id}/control/compact",
            json={"max_chars": 12000},
        )

    assert response.status_code == 200
    assert response.json()["path"] == ".orchestrator/control/context.compact.md"
    compact = (project.project_dir / ".orchestrator" / "control" / "context.compact.md").read_text(
        encoding="utf-8"
    )
    assert "npm/js project detected" in compact
    assert "PRD.md" in compact
    assert "Wake-up text from palace." in compact


@pytest.mark.asyncio
async def test_resume_route_passes_named_step_to_runner(app: FastAPI, fresh_store: ProjectStore) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Resume Project", "initial_idea": "Build it"},
        )
        project_id = create_resp.json()["id"]
        project = fresh_store.get(project_id)
        assert project is not None
        (project.project_dir / "package.json").write_text(
            '{"name":"resume-project","scripts":{"test":"pytest -q"}}',
            encoding="utf-8",
        )

        async def _fake_start(project_id: str, initial_idea=None, **kwargs):
            return True

        with patch("web.backend.runner.start_run_async", side_effect=_fake_start) as start_mock:
            response = await client.post(
                f"/api/projects/{project_id}/control/resume",
                json={
                    "start_at": "testing",
                    "instruction": "Prefer existing test commands.",
                    "compact_context": True,
                    "max_chars": 12000,
                },
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["started"] is True
    assert payload["start_at"] == "testing"
    assert start_mock.await_args.kwargs["start_at"] == "testing"


@pytest.mark.asyncio
async def test_workflow_route_can_enable_guru_escalation(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Workflow Project", "initial_idea": "Build it"},
        )
        project_id = create_resp.json()["id"]

        workflow_resp = await client.get(f"/api/projects/{project_id}/control/workflow")
        steps = workflow_resp.json()["steps"]
        for step in steps:
            if step["id"] == "guru_escalation":
                step["enabled"] = True
                step["config"] = {"providers": [{"kind": "openrouter", "model": "anthropic/claude-3.5-sonnet"}]}

        save_resp = await client.put(
            f"/api/projects/{project_id}/control/workflow",
            json={"steps": steps},
        )

    assert workflow_resp.status_code == 200
    assert save_resp.status_code == 200
    saved_steps = {step["id"]: step for step in save_resp.json()["steps"]}
    assert saved_steps["guru_escalation"]["enabled"] is True
    assert saved_steps["guru_escalation"]["config"]["providers"][0]["kind"] == "openrouter"


@pytest.mark.asyncio
async def test_persona_synthesis_route_updates_workflow(app: FastAPI, fresh_store: ProjectStore) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Game Project", "initial_idea": "Build a tactical game with combat."},
        )
        project_id = create_resp.json()["id"]
        project = fresh_store.get(project_id)
        assert project is not None
        (project.project_dir / "qwendea.md").write_text(
            "# Project\n\nBuild a tactical game with combat.\n",
            encoding="utf-8",
        )

        response = await client.post(f"/api/projects/{project_id}/control/personas/synthesize")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["personas"]) >= 4
    persona_step = next(step for step in payload["steps"] if step["id"] == "persona_forum")
    assert len(persona_step["config"]["personas"]) >= 4
    assert persona_step["config"]["personas"][0]["turn_order"] == 1
