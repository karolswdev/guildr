"""Operator intent routes for live map controls."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orchestrator.lib.scrub import is_secret_key, scrub_payload
from web.backend.routes.projects import get_store
from web.backend.routes.stream import get_event_store

__all__ = ["router", "is_secret_key", "scrub_payload"]

router = APIRouter()

IntentKind = Literal["intercept", "resume", "interject", "skip", "retry", "reroute", "note"]


class OperatorIntentRequest(BaseModel):
    kind: IntentKind
    atom_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    client_intent_id: str | None = None


@router.post("/{project_id}/intents")
async def create_operator_intent(project_id: str, body: OperatorIntentRequest) -> dict[str, Any]:
    project = get_store().get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    event_fields = {
        "project_id": project_id,
        "kind": body.kind,
        "atom_id": body.atom_id,
        "payload": scrub_payload(body.payload),
    }
    if body.client_intent_id:
        event_fields["client_intent_id"] = body.client_intent_id

    get_event_store().get_or_create(project_id).emit("operator_intent", **event_fields)
    return {
        "project_id": project_id,
        "accepted": True,
        "kind": body.kind,
        "atom_id": body.atom_id,
    }


