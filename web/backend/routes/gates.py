"""Gate routes for human approval gates.

GET    /api/projects/{id}/gates                        — list gates
GET    /api/projects/{id}/gates/{name}                  — get gate + artifact
POST   /api/projects/{id}/gates/{name}/decide           — decide gate
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# -- models ------------------------------------------------------------------


class DecideRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str = ""


class GateResponse(BaseModel):
    name: str
    status: Literal["pending", "approved", "rejected"]
    artifact: str | None = None
    reason: str = ""
    decided_at: float | None = None


class GateListResponse(BaseModel):
    gates: list[GateResponse]


class GateDecideResponse(BaseModel):
    decided: bool
    gate: GateResponse


# -- in-memory gate store per project ----------------------------------------


@dataclass
class Gate:
    name: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    artifact: str | None = None
    reason: str = ""
    decided_at: float | None = None


class GateRegistry:
    """Per-project gate registry."""

    def __init__(self) -> None:
        self._gates: dict[str, dict[str, Gate]] = {}

    def get_or_create(self, project_id: str, gate_name: str) -> Gate:
        if project_id not in self._gates:
            self._gates[project_id] = {}
        if gate_name not in self._gates[project_id]:
            self._gates[project_id][gate_name] = Gate(name=gate_name)
        return self._gates[project_id][gate_name]

    def list_gates(self, project_id: str) -> list[Gate]:
        return list(self._gates.get(project_id, {}).values())

    def decide(self, project_id: str, gate_name: str, decision: str, reason: str = "") -> Gate:
        gate = self.get_or_create(project_id, gate_name)
        # Idempotent: if already decided, return current state
        if gate.status != "pending":
            return gate
        gate.status = decision
        gate.reason = reason
        gate.decided_at = time.time()
        return gate

    def get_gate(self, project_id: str, gate_name: str) -> Gate | None:
        return self._gates.get(project_id, {}).get(gate_name)

    def open_gate(self, project_id: str, gate_name: str, artifact: str = "") -> Gate:
        gate = self.get_or_create(project_id, gate_name)
        if gate.status != "pending":
            raise ValueError(f"Gate '{gate_name}' is already {gate.status}")
        gate.artifact = artifact
        return gate


# -- singleton store ---------------------------------------------------------

_gate_registry = GateRegistry()


def get_gate_registry() -> GateRegistry:
    return _gate_registry


# -- routes ------------------------------------------------------------------


def _setup_routes(router_obj: Any) -> Any:
    """Attach routes to the given router."""
    from fastapi import APIRouter

    router_obj = APIRouter()

    @router_obj.get("/{project_id}/gates", response_model=GateListResponse)
    async def list_gates(project_id: str) -> GateListResponse:
        registry = get_gate_registry()
        gates = registry.list_gates(project_id)
        return GateListResponse(
            gates=[
                GateResponse(
                    name=g.name,
                    status=g.status,
                    artifact=g.artifact,
                    reason=g.reason,
                    decided_at=g.decided_at,
                )
                for g in gates
            ]
        )

    @router_obj.get("/{project_id}/gates/{gate_name}", response_model=GateResponse)
    async def get_gate(project_id: str, gate_name: str) -> GateResponse:
        registry = get_gate_registry()
        gate = registry.get_gate(project_id, gate_name)
        if gate is None:
            raise HTTPException(status_code=404, detail="Gate not found")
        return GateResponse(
            name=gate.name,
            status=gate.status,
            artifact=gate.artifact,
            reason=gate.reason,
            decided_at=gate.decided_at,
        )

    @router_obj.post("/{project_id}/gates/{gate_name}/decide", response_model=GateDecideResponse)
    async def decide_gate(
        project_id: str, gate_name: str, body: DecideRequest
    ) -> GateDecideResponse:
        registry = get_gate_registry()
        gate = registry.decide(project_id, gate_name, body.decision, body.reason)
        logger.info(
            "Gate '%s' for project '%s' decided: %s (reason: %s)",
            gate_name, project_id, body.decision, body.reason,
        )
        return GateDecideResponse(
            decided=True,
            gate=GateResponse(
                name=gate.name,
                status=gate.status,
                artifact=gate.artifact,
                reason=gate.reason,
                decided_at=gate.decided_at,
            ),
        )

    return router_obj


router = _setup_routes(None)
