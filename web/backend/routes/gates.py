"""Gate routes for human approval gates.

GET    /api/projects/{id}/gates                        — list gates
GET    /api/projects/{id}/gates/{name}                  — get gate + artifact
POST   /api/projects/{id}/gates/{name}/decide           — decide gate

This module is a thin HTTP facade over ``orchestrator.lib.gates`` — the
``GateRegistry`` class here previously was a shadow implementation that
never synchronised with the engine's registry, which is why PWA gate
decisions silently did nothing. Now the registry *is* the engine's.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel

from orchestrator.lib.gates import GateRegistryStore

logger = logging.getLogger(__name__)


class DecideRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str = ""
    new_run_budget_usd: float | None = None
    new_phase_budget_usd: float | None = None
    budget_at_decision: dict[str, float | None] | None = None


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


# Module-level store. The runner (web/backend/runner.py) will reach in and
# publish the same instance on app.state so it can hand individual project
# registries to the orchestrator it starts.
_gate_store = GateRegistryStore()


def get_gate_store() -> GateRegistryStore:
    return _gate_store


def _serialize(gate) -> GateResponse:
    return GateResponse(
        name=gate.name,
        status=gate.decision,  # canonical field; HTTP calls it status
        artifact=gate.artifact or None,
        reason=gate.reason,
        decided_at=gate.decided_at,
    )


def _setup_routes(router_obj: Any) -> Any:
    from fastapi import APIRouter

    router_obj = APIRouter()

    @router_obj.get("/{project_id}/gates", response_model=GateListResponse)
    async def list_gates(project_id: str) -> GateListResponse:
        store = get_gate_store()
        registry = store.get(project_id)
        if registry is None:
            return GateListResponse(gates=[])
        return GateListResponse(gates=[_serialize(g) for g in registry.list_gates()])

    @router_obj.get("/{project_id}/gates/{gate_name}", response_model=GateResponse)
    async def get_gate(project_id: str, gate_name: str) -> GateResponse:
        store = get_gate_store()
        registry = store.get(project_id)
        gate = registry.get_gate(gate_name) if registry is not None else None
        if gate is None:
            raise HTTPException(status_code=404, detail="Gate not found")
        return _serialize(gate)

    @router_obj.post(
        "/{project_id}/gates/{gate_name}/decide", response_model=GateDecideResponse
    )
    async def decide_gate(
        project_id: str, gate_name: str, body: DecideRequest
    ) -> GateDecideResponse:
        store = get_gate_store()
        registry = store.ensure(project_id)
        before = registry.get_gate(gate_name)
        before_status = before.decision if before is not None else "pending"
        gate = registry.decide(gate_name, body.decision, body.reason)
        if _is_budget_gate(gate_name) and before_status == "pending":
            _emit_budget_gate_decided(project_id, gate_name, body)
        logger.info(
            "Gate '%s' for project '%s' decided: %s (reason: %s)",
            gate_name, project_id, body.decision, body.reason,
        )
        return GateDecideResponse(decided=True, gate=_serialize(gate))

    return router_obj


def _is_budget_gate(gate_name: str) -> bool:
    return (
        gate_name.startswith("budget")
        or gate_name.startswith("budget_")
        or gate_name.startswith("budget-")
    )


def _emit_budget_gate_opened(project_id: str, gate_name: str) -> None:
    from web.backend.routes.stream import get_event_store

    get_event_store().get_or_create(project_id).emit(
        "budget_gate_opened",
        project_id=project_id,
        gate_id=gate_name,
        level="run",
    )


def _emit_budget_gate_decided(project_id: str, gate_name: str, body: DecideRequest) -> None:
    from web.backend.routes.stream import get_event_store

    budget_at_decision = body.budget_at_decision or {
        "run_budget_usd": body.new_run_budget_usd,
        "phase_budget_usd": body.new_phase_budget_usd,
        "remaining_run_budget_usd": body.new_run_budget_usd,
        "remaining_phase_budget_usd": body.new_phase_budget_usd,
    }
    budget_at_decision.setdefault("remaining_run_budget_usd", None)
    budget_at_decision.setdefault("remaining_phase_budget_usd", None)
    get_event_store().get_or_create(project_id).emit(
        "budget_gate_decided",
        project_id=project_id,
        gate_id=gate_name,
        decision=body.decision,
        new_run_budget_usd=body.new_run_budget_usd,
        new_phase_budget_usd=body.new_phase_budget_usd,
        operator_note=body.reason,
        budget_at_decision=budget_at_decision,
    )


router = _setup_routes(None)
