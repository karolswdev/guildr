"""Tests for operator intent routes."""

from __future__ import annotations

import tempfile
import json
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
async def test_operator_intent_route_persists_scrubbed_event(app: FastAPI, fresh_store: ProjectStore) -> None:
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
    assert payload["client_intent_id"].startswith("intent_")

    event_text = event_log_path(project_id).read_text(encoding="utf-8")
    assert "operator_intent" in event_text
    assert "implementation" in event_text
    assert "Pause after this atom" in event_text
    assert "sk-live-value" not in event_text
    assert "Bearer secret" not in event_text
    assert "[redacted]" in event_text

    project = fresh_store.get(project_id)
    assert project is not None
    rows = [
        json.loads(line)
        for line in (project.project_dir / ".orchestrator" / "control" / "intents.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["client_intent_id"] == payload["client_intent_id"]
    assert rows[0]["intent_event_id"] in event_text
    assert rows[0]["status"] == "queued"


@pytest.mark.asyncio
async def test_operator_intent_route_refreshes_authoritative_next_step_packet(
    app: FastAPI,
    fresh_store: ProjectStore,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post("/api/projects", json={"name": "Packet Refresh"})
        project_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/projects/{project_id}/intents",
            json={
                "kind": "interject",
                "atom_id": "memory_refresh",
                "payload": {"instruction": "Show this on the next packet."},
                "client_intent_id": "client-refresh",
            },
        )

    assert response.status_code == 200
    events = [
        json.loads(line)
        for line in event_log_path(project_id).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [event["type"] for event in events] == [
        "operator_intent",
        "next_step_packet_created",
        "narrator_sidecar_requested",
    ]
    assert events[0]["client_intent_id"] == "client-refresh"
    assert events[1]["schema_version"] == 1
    assert events[1]["run_id"] == project_id
    assert events[1]["packet"]["step"] == "memory_refresh"
    assert events[1]["packet"]["queued_intents"] == [
        {
            "client_intent_id": "client-refresh",
            "intent_event_id": events[0]["event_id"],
            "kind": "interject",
            "atom_id": "memory_refresh",
            "payload": {"instruction": "Show this on the next packet."},
            "status": "queued",
        }
    ]
    assert events[2]["trigger_event_id"] == events[0]["event_id"]
    assert events[2]["packet_id"] == events[1]["packet_id"]
    assert events[2]["reason"] == "operator_intent"


@pytest.mark.asyncio
async def test_invite_hero_intent_route_refreshes_packet_with_hero_payload(
    app: FastAPI,
    fresh_store: ProjectStore,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post("/api/projects", json={"name": "Hero Invite"})
        project_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/projects/{project_id}/intents",
            json={
                "kind": "invite_hero",
                "atom_id": "memory_refresh",
                "payload": {
                    "instruction": "Review the next memory refresh for auth bypasses.",
                    "api_key": "sk-live-secret",
                    "hero": {
                        "name": "Security Reviewer",
                        "provider": "openrouter",
                        "model": "qwen2.5-coder-32b",
                        "mission": "Review the next memory refresh for auth bypasses.",
                        "watch_for": "auth gaps",
                        "term": {"mode": "single_consultation"},
                    },
                    "target": {
                        "step": "memory_refresh",
                        "deliverable": None,
                        "consultation_trigger": None,
                    },
                },
                "client_intent_id": "client-hero",
            },
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "invite_hero"
    events = [
        json.loads(line)
        for line in event_log_path(project_id).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [event["type"] for event in events] == [
        "operator_intent",
        "next_step_packet_created",
        "narrator_sidecar_requested",
    ]
    assert events[0]["kind"] == "invite_hero"
    assert events[0]["payload"]["hero"]["name"] == "Security Reviewer"
    assert events[0]["payload"]["api_key"] == "[redacted]"
    assert events[1]["packet"]["queued_intents"][0]["kind"] == "invite_hero"
    assert events[1]["packet"]["queued_intents"][0]["payload"]["hero"]["watch_for"] == "auth gaps"
    assert "sk-live-secret" not in event_log_path(project_id).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_note_intent_creates_discussion_entry(app: FastAPI, fresh_store: ProjectStore) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post("/api/projects", json={"name": "Note Intent"})
        project_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/projects/{project_id}/intents",
            json={
                "kind": "note",
                "atom_id": "testing",
                "payload": {"note": "Remember token=sk-live-secret-value must stay hidden."},
                "client_intent_id": "client-note",
            },
        )

    assert response.status_code == 200
    project = fresh_store.get(project_id)
    assert project is not None
    discussion_text = (project.project_dir / ".orchestrator" / "discussion" / "log.jsonl").read_text(
        encoding="utf-8"
    )
    assert "sk-live-secret-value" not in discussion_text
    row = json.loads(discussion_text)
    assert row["entry_type"] == "operator_note"
    assert row["speaker"] == "operator"
    assert row["atom_id"] == "testing"

    events = [
        json.loads(line)
        for line in event_log_path(project_id).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [event["type"] for event in events] == [
        "operator_intent",
        "discussion_entry_created",
        "next_step_packet_created",
        "narrator_sidecar_requested",
    ]
    assert events[1]["entry"]["source_refs"] == [f"event:{events[0]['event_id']}"]
    assert events[3]["trigger_event_id"] == events[0]["event_id"]
