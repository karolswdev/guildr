"""Operator intent routes for live map controls."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orchestrator.lib.discussion import append_discussion_entry
from orchestrator.lib.event_schema import new_event_id
from orchestrator.lib.intents import create_queued_intent
from orchestrator.lib.narrator_sidecar import emit_narrator_sidecar_requested
from orchestrator.lib.next_step import build_next_step_packet, emit_next_step_packet_event
from orchestrator.lib.scrub import is_secret_key, scrub_payload
from orchestrator.lib.state import State
from web.backend.routes.projects import get_store
from web.backend.routes.stream import get_event_store

__all__ = ["router", "is_secret_key", "scrub_payload"]

router = APIRouter()

IntentKind = Literal["intercept", "resume", "interject", "skip", "retry", "reroute", "note", "invite_hero"]


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

    intent_event_id = new_event_id()
    row = create_queued_intent(
        project.project_dir,
        kind=body.kind,
        atom_id=body.atom_id,
        payload=body.payload,
        client_intent_id=body.client_intent_id,
        intent_event_id=intent_event_id,
    )
    event_fields = {
        "event_id": intent_event_id,
        "project_id": project_id,
        "kind": body.kind,
        "atom_id": body.atom_id,
        "payload": row["payload"],
        "client_intent_id": row["client_intent_id"],
    }

    event_bus = get_event_store().get_or_create(project_id)
    operator_event = event_bus.emit("operator_intent", **event_fields)
    if body.kind == "note":
        append_discussion_entry(
            project.project_dir,
            speaker="operator",
            entry_type="operator_note",
            atom_id=body.atom_id,
            text=_intent_note_text(row["payload"]),
            source_refs=[f"event:{intent_event_id}"],
            artifact_refs=[".orchestrator/control/intents.jsonl"],
            metadata={"client_intent_id": row["client_intent_id"]},
            event_bus=event_bus,
            project_id=project_id,
        )
    packet = _emit_refreshed_next_step_packet(event_bus, project_id, project.project_dir)
    emit_narrator_sidecar_requested(
        event_bus,
        project_id=project_id,
        trigger_event=operator_event,
        next_step_packet=packet,
        reason="operator_intent",
    )
    return {
        "project_id": project_id,
        "accepted": True,
        "kind": body.kind,
        "atom_id": body.atom_id,
        "client_intent_id": row["client_intent_id"],
    }


def _emit_refreshed_next_step_packet(event_bus: Any, project_id: str, project_dir: Path) -> dict[str, Any] | None:
    state = State(project_dir)
    state.load()
    packet = build_next_step_packet(
        state,
        current_step=state.current_phase,
    )
    if packet is None:
        return None
    emit_next_step_packet_event(event_bus, project_id, packet)
    return packet


def _intent_note_text(payload: dict[str, Any]) -> str:
    for key in ("instruction", "message", "text", "note"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Operator note"
