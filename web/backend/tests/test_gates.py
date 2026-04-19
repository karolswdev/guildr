"""Tests for gate routes."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from web.backend.app import create_app
from web.backend.routes.gates import Gate, GateRegistry


@pytest.fixture
def fresh_registry() -> GateRegistry:
    return GateRegistry()


@pytest.fixture
def app(fresh_registry: GateRegistry) -> FastAPI:
    with patch("web.backend.routes.gates.get_gate_registry", return_value=fresh_registry):
        yield create_app()


@pytest.mark.asyncio
async def test_list_gates_empty(app: FastAPI) -> None:
    """GET /gates returns empty list when no gates exist."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/projects/test-project/gates")
    assert response.status_code == 200
    data = response.json()
    assert data["gates"] == []


@pytest.mark.asyncio
async def test_list_gates_returns_pending_and_decided(app: FastAPI) -> None:
    """GET /gates returns both pending and decided gates."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        registry = __import__("web.backend.routes.gates", fromlist=["get_gate_registry"]).get_gate_registry()
        registry.open_gate("proj-1", "approve_sprint_plan", "artifact content")
        registry.decide("proj-1", "approve_sprint_plan", "approved")
        registry.open_gate("proj-1", "approve_review", "review artifact")

        response = await client.get("/api/projects/proj-1/gates")
    assert response.status_code == 200
    data = response.json()
    assert len(data["gates"]) == 2
    statuses = {g["status"] for g in data["gates"]}
    assert statuses == {"approved", "pending"}


@pytest.mark.asyncio
async def test_get_gate(app: FastAPI) -> None:
    """GET /gates/{name} returns the gate with artifact."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        registry = __import__("web.backend.routes.gates", fromlist=["get_gate_registry"]).get_gate_registry()
        registry.open_gate("proj-2", "test_gate", "some artifact text")

        response = await client.get("/api/projects/proj-2/gates/test_gate")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test_gate"
    assert data["status"] == "pending"
    assert data["artifact"] == "some artifact text"


@pytest.mark.asyncio
async def test_get_gate_not_found(app: FastAPI) -> None:
    """GET /gates/{name} returns 404 for unknown gate."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/projects/proj-3/gates/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_decide_gate(app: FastAPI) -> None:
    """POST /gates/{name}/decide records the decision."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        registry = __import__("web.backend.routes.gates", fromlist=["get_gate_registry"]).get_gate_registry()
        registry.open_gate("proj-4", "approve_sprint_plan", "sprint plan content")

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
async def test_decide_rejected_gate(app: FastAPI) -> None:
    """POST /gates/{name}/decide with rejected decision."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        registry = __import__("web.backend.routes.gates", fromlist=["get_gate_registry"]).get_gate_registry()
        registry.open_gate("proj-5", "approve_review")

        response = await client.post(
            "/api/projects/proj-5/gates/approve_review/decide",
            json={"decision": "rejected", "reason": "Missing tests"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["gate"]["status"] == "rejected"


@pytest.mark.asyncio
async def test_decide_is_idempotent(app: FastAPI) -> None:
    """Deciding an already-decided gate returns current decision."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        registry = __import__("web.backend.routes.gates", fromlist=["get_gate_registry"]).get_gate_registry()
        registry.open_gate("proj-6", "gate_a")

        # First decision
        resp1 = await client.post(
            "/api/projects/proj-6/gates/gate_a/decide",
            json={"decision": "approved", "reason": "First"},
        )
        first_time = resp1.json()["gate"]["decided_at"]

        # Second decision (idempotent — should return current)
        resp2 = await client.post(
            "/api/projects/proj-6/gates/gate_a/decide",
            json={"decision": "rejected", "reason": "Second"},
        )

    assert resp2.status_code == 200
    # The gate should still be approved (idempotent — returns current state)
    assert resp2.json()["gate"]["status"] == "approved"
    # decided_at should not change
    assert resp2.json()["gate"]["decided_at"] == first_time


class TestGateRegistry:
    """Direct unit tests for GateRegistry."""

    def test_open_gate(self) -> None:
        reg = GateRegistry()
        gate = reg.open_gate("proj", "gate1", "artifact")
        assert gate.status == "pending"
        assert gate.artifact == "artifact"

    def test_open_already_decided_raises(self) -> None:
        reg = GateRegistry()
        reg.open_gate("proj", "gate1")
        reg.decide("proj", "gate1", "approved")
        with pytest.raises(ValueError, match="already approved"):
            reg.open_gate("proj", "gate1")

    def test_decide_creates_if_missing(self) -> None:
        reg = GateRegistry()
        gate = reg.decide("proj", "new_gate", "approved")
        assert gate.status == "approved"
        assert gate.name == "new_gate"

    def test_get_gate_returns_none_for_missing(self) -> None:
        reg = GateRegistry()
        assert reg.get_gate("proj", "missing") is None

    def test_list_gates_empty(self) -> None:
        reg = GateRegistry()
        assert reg.list_gates("proj") == []

    def test_list_gates_multiple(self) -> None:
        reg = GateRegistry()
        reg.open_gate("proj", "gate1")
        reg.open_gate("proj", "gate2")
        gates = reg.list_gates("proj")
        assert len(gates) == 2
        names = {g.name for g in gates}
        assert names == {"gate1", "gate2"}
