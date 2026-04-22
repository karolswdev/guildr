"""Deterministic next-step packet generation."""

from __future__ import annotations

from typing import Any

from orchestrator.lib.event_schema import new_event_id
from orchestrator.lib.intents import queued_intents_for_step
from orchestrator.lib.loop_refs import refs_for_phase
from orchestrator.lib.memory_palace import memory_provenance
from orchestrator.lib.state import State
from orchestrator.lib.workflow import enabled_steps


def build_next_step_packet(
    state: State,
    *,
    completed_step: str | None = None,
    current_step: str | None = None,
) -> dict[str, Any] | None:
    """Build the authoritative packet for the next enabled workflow step."""
    step = select_next_step(state, completed_step=completed_step, current_step=current_step)
    if step is None:
        return None

    step_id = step["id"]
    refs = refs_for_phase(step_id, state, include_outputs=False)
    memory = memory_provenance(None, state.project_dir)
    memory_inputs = [
        {"kind": "memory", "ref": ref, "label": "Wake-up packet"}
        for ref in memory["memory_refs"]
    ]
    queued_intents = queued_intents_for_step(state.project_dir, step_id)
    artifact_inputs = [
        {"kind": "artifact", "ref": ref, "label": _label_for_ref(ref)}
        for ref in refs["memory_refs"]
        if ref not in memory["memory_refs"]
    ]

    return {
        "packet_id": f"next_{new_event_id()}",
        "step": step_id,
        "title": step.get("title") or step_id,
        "role": step.get("handler") or step_id,
        "objective": _objective_for_step(step),
        "why_now": _why_now(step_id, completed_step=completed_step, current_step=current_step),
        "inputs": [*artifact_inputs, *memory_inputs],
        "context_preview": _context_preview(step_id, refs, memory),
        "queued_intents": queued_intents,
        "intervention_options": ["interject", "intercept", "reroute", "skip"],
        "source_refs": [
            f"workflow:{step_id}",
            *[f"artifact:{ref}" for ref in refs["memory_refs"]],
            *[f"memory:{ref}" for ref in memory["memory_refs"]],
        ],
        "memory_provenance": memory,
    }


def select_next_step(
    state: State,
    *,
    completed_step: str | None = None,
    current_step: str | None = None,
) -> dict[str, Any] | None:
    """Return the next enabled step after the cursor, or the first incomplete step."""
    steps = enabled_steps(state.project_dir)
    if not steps:
        return None

    cursor = completed_step or current_step
    if cursor:
        for index, step in enumerate(steps):
            if step["id"] == cursor:
                if current_step:
                    return step
                return steps[index + 1] if index + 1 < len(steps) else None

    done = set(state.retries.keys())
    for step in steps:
        if step["type"] == "gate" and state.gates_approved.get(step["id"]):
            continue
        if step["type"] == "phase" and step["id"] in done:
            continue
        return step
    return None


def _objective_for_step(step: dict[str, Any]) -> str:
    title = step.get("title") or step["id"]
    if step["type"] == "gate":
        return f"Decide whether to approve {title}."
    if step["handler"] == "memory_refresh":
        return "Refresh project memory and produce the wake-up packet."
    if step["handler"] == "persona_forum":
        return "Update the founding-team context before planning."
    return f"Run {title}."


def _why_now(step_id: str, *, completed_step: str | None, current_step: str | None) -> str:
    if completed_step:
        return f"{completed_step} completed; {step_id} is the next enabled workflow step."
    if current_step:
        return f"{current_step} is active; {step_id} is queued after it."
    return f"{step_id} is the next enabled incomplete workflow step."


def _context_preview(step_id: str, refs: dict[str, list[str]], memory: dict[str, Any]) -> list[str]:
    preview = [f"Next step: {step_id}"]
    if refs["memory_refs"]:
        preview.append("Inputs: " + ", ".join(refs["memory_refs"][:4]))
    if memory.get("wake_up_hash"):
        preview.append(f"Memory wake-up hash: {str(memory['wake_up_hash'])[:12]}")
    return preview


def _label_for_ref(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]
