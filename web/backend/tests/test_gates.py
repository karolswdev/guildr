"""Tests for gate routes.

The routes are a thin HTTP facade over the canonical
``orchestrator.lib.gates.GateRegistry`` held in a per-project
``GateRegistryStore``. These tests patch the module-level store so each
test gets a fresh container; production wiring happens in the runner.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from orchestrator.lib.gates import GateRegistryStore
from web.backend.app import create_app
from web.backend.routes.stream import EventStore, event_log_path


@pytest.fixture
def fresh_store() -> GateRegistryStore:
    return GateRegistryStore()


@pytest.fixture
def app(fresh_store: GateRegistryStore) -> FastAPI:
    with patch("web.backend.routes.gates.get_gate_store", return_value=fresh_store):
        yield create_app()


@pytest.mark.asyncio
async def test_list_gates_empty(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/projects/test-project/gates")
    assert response.status_code == 200
    assert response.json()["gates"] == []


@pytest.mark.asyncio
async def test_list_gates_returns_pending_and_decided(
    app: FastAPI, fresh_store: GateRegistryStore
) -> None:
    registry = fresh_store.ensure("proj-1")
    registry.open_gate("approve_sprint_plan", "artifact content")
    registry.decide("approve_sprint_plan", "approved")
    registry.open_gate("approve_review", "review artifact")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/projects/proj-1/gates")

    assert response.status_code == 200
    data = response.json()
    assert len(data["gates"]) == 2
    statuses = {g["status"] for g in data["gates"]}
    assert statuses == {"approved", "pending"}


@pytest.mark.asyncio
async def test_get_gate(app: FastAPI, fresh_store: GateRegistryStore) -> None:
    fresh_store.ensure("proj-2").open_gate("test_gate", "some artifact text")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/projects/proj-2/gates/test_gate")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test_gate"
    assert data["status"] == "pending"
    assert data["artifact"] == "some artifact text"


@pytest.mark.asyncio
async def test_get_gate_not_found(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/projects/proj-3/gates/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_decide_gate(app: FastAPI, fresh_store: GateRegistryStore) -> None:
    fresh_store.ensure("proj-4").open_gate("approve_sprint_plan", "sprint plan content")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/projects/proj-4/gates/approve_sprint_plan/decide",
            json={"decision": "approved", "reason": "Looks good"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["decided"] is True
    assert data["gate"]["status"] == "approved"
    assert data["gate"]["reason"] == "Looks good"
    assert data["gate"]["decided_at"] is not None


@pytest.mark.asyncio
async def test_decide_rejected_gate(app: FastAPI, fresh_store: GateRegistryStore) -> None:
    fresh_store.ensure("proj-5").open_gate("approve_review")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/projects/proj-5/gates/approve_review/decide",
            json={"decision": "rejected", "reason": "Missing tests"},
        )
    assert response.status_code == 200
    assert response.json()["gate"]["status"] == "rejected"


@pytest.mark.asyncio
async def test_decide_is_idempotent(app: FastAPI, fresh_store: GateRegistryStore) -> None:
    fresh_store.ensure("proj-6").open_gate("gate_a")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp1 = await client.post(
            "/api/projects/proj-6/gates/gate_a/decide",
            json={"decision": "approved", "reason": "First"},
        )
        first_time = resp1.json()["gate"]["decided_at"]
        resp2 = await client.post(
            "/api/projects/proj-6/gates/gate_a/decide",
            json={"decision": "rejected", "reason": "Second"},
        )
    assert resp2.status_code == 200
    assert resp2.json()["gate"]["status"] == "approved"
    assert resp2.json()["gate"]["decided_at"] == first_time


@pytest.mark.asyncio
async def test_budget_gate_decision_emits_budget_events(
    app: FastAPI,
    fresh_store: GateRegistryStore,
    tmp_path: Path,
) -> None:
    """Budget gate decision persists a replayable ``budget_gate_decided`` event.

    The ``budget_gate_opened`` event is emitted by whoever opens the gate
    (in production: the engine/runner). The test opens the gate via the
    canonical registry and emits the open event explicitly to model that
    contract — the registry itself is pure and does not side-effect events.
    """
    fresh_store.ensure("proj-budget").open_gate("budget_run")

    event_store = EventStore()
    transport = ASGITransport(app=app)
    with (
        patch("web.backend.routes.stream.get_event_store", return_value=event_store),
        patch("web.backend.routes.stream._projects_base", return_value=tmp_path),
    ):
        event_store.get_or_create("proj-budget").emit(
            "budget_gate_opened",
            project_id="proj-budget",
            gate_id="budget_run",
            level="run",
        )
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/projects/proj-budget/gates/budget_run/decide",
                json={
                    "decision": "rejected",
                    "reason": "Stop spend",
                    "new_run_budget_usd": 15.0,
                    "budget_at_decision": {
                        "run_budget_usd": 15.0,
                        "phase_budget_usd": None,
                        "remaining_run_budget_usd": 7.5,
                        "remaining_phase_budget_usd": None,
                    },
                },
            )
        events = [
            json.loads(line)
            for line in event_log_path("proj-budget").read_text(encoding="utf-8").splitlines()
        ]

    assert response.status_code == 200
    assert [event["type"] for event in events] == ["budget_gate_opened", "budget_gate_decided"]
    decided = events[1]
    assert decided["event_id"]
    assert decided["schema_version"] == 1
    assert decided["run_id"] == "proj-budget"
    assert decided["gate_id"] == "budget_run"
    assert decided["decision"] == "rejected"
    assert decided["budget_at_decision"]["remaining_run_budget_usd"] == 7.5


@pytest.mark.asyncio
async def test_budget_gate_decision_without_raise_keeps_budget_fields_explicit(
    app: FastAPI,
    fresh_store: GateRegistryStore,
    tmp_path: Path,
) -> None:
    fresh_store.ensure("proj-budget-approve").open_gate("budget_run")

    event_store = EventStore()
    transport = ASGITransport(app=app)
    with (
        patch("web.backend.routes.stream.get_event_store", return_value=event_store),
        patch("web.backend.routes.stream._projects_base", return_value=tmp_path),
    ):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/projects/proj-budget-approve/gates/budget_run/decide",
                json={"decision": "approved", "reason": "Continue without raising"},
            )
        events = [
            json.loads(line)
            for line in event_log_path("proj-budget-approve").read_text(encoding="utf-8").splitlines()
        ]

    assert response.status_code == 200
    assert [event["type"] for event in events] == ["budget_gate_decided"]
    decided = events[0]
    assert decided["decision"] == "approved"
    assert decided["new_run_budget_usd"] is None
    assert decided["new_phase_budget_usd"] is None
    assert decided["budget_at_decision"]["run_budget_usd"] is None
    assert decided["budget_at_decision"]["phase_budget_usd"] is None
    assert decided["budget_at_decision"]["remaining_run_budget_usd"] is None
    assert decided["budget_at_decision"]["remaining_phase_budget_usd"] is None


class TestGateRegistryStore:
    """Unit tests for the per-project store container."""

    def test_ensure_creates_registry(self) -> None:
        store = GateRegistryStore()
        reg = store.ensure("proj")
        assert reg is store.ensure("proj")

    def test_ensure_different_projects(self) -> None:
        store = GateRegistryStore()
        assert store.ensure("a") is not store.ensure("b")

    def test_get_returns_none_for_unknown(self) -> None:
        assert GateRegistryStore().get("unknown") is None

    def test_open_gate_returns_gate(self) -> None:
        reg = GateRegistryStore().ensure("proj")
        gate = reg.open_gate("gate1", "artifact")
        assert gate.decision == "pending"
        assert gate.artifact == "artifact"

    def test_open_already_decided_raises(self) -> None:
        reg = GateRegistryStore().ensure("proj")
        reg.open_gate("gate1")
        reg.decide("gate1", "approved")
        with pytest.raises(ValueError, match="already approved"):
            reg.open_gate("gate1")

    def test_decide_creates_if_missing(self) -> None:
        reg = GateRegistryStore().ensure("proj")
        gate = reg.decide("new_gate", "approved")
        assert gate.decision == "approved"
        assert gate.name == "new_gate"

    def test_get_gate_returns_none_for_missing(self) -> None:
        assert GateRegistryStore().ensure("proj").get_gate("missing") is None

    def test_list_gates_empty(self) -> None:
        assert GateRegistryStore().ensure("proj").list_gates() == []

    def test_list_gates_multiple(self) -> None:
        reg = GateRegistryStore().ensure("proj")
        reg.open_gate("gate1")
        reg.open_gate("gate2")
        names = {g.name for g in reg.list_gates()}
        assert names == {"gate1", "gate2"}
