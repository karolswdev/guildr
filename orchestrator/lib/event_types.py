"""Canonical durable event type registry."""

from __future__ import annotations

from typing import Final


RUN_STARTED: Final = "run_started"
RUN_COMPLETE: Final = "run_complete"
RUN_ERROR: Final = "run_error"

PHASE_START: Final = "phase_start"
PHASE_DONE: Final = "phase_done"
PHASE_RETRY: Final = "phase_retry"
PHASE_ERROR: Final = "phase_error"
CHECKPOINT: Final = "checkpoint"

GATE_OPENED: Final = "gate_opened"
GATE_DECIDED: Final = "gate_decided"

USAGE_RECORDED: Final = "usage_recorded"
PROVIDER_CALL_ERROR: Final = "provider_call_error"

BUDGET_WARNING: Final = "budget_warning"
BUDGET_EXCEEDED: Final = "budget_exceeded"
BUDGET_GATE_OPENED: Final = "budget_gate_opened"
BUDGET_GATE_DECIDED: Final = "budget_gate_decided"

LOOP_ENTERED: Final = "loop_entered"
LOOP_PROGRESSED: Final = "loop_progressed"
LOOP_BLOCKED: Final = "loop_blocked"
LOOP_REPAIRED: Final = "loop_repaired"
LOOP_COMPLETED: Final = "loop_completed"
LOOP_REOPENED: Final = "loop_reopened"

MEMORY_STATUS: Final = "memory_status"
MEMORY_REFRESHED: Final = "memory_refreshed"
MEMORY_SEARCH_COMPLETED: Final = "memory_search_completed"
MEMORY_ERROR: Final = "memory_error"
MEMORY_DIFF: Final = "memory_diff"

NEXT_STEP_PACKET_CREATED: Final = "next_step_packet_created"
NARRATIVE_DIGEST_CREATED: Final = "narrative_digest_created"
DISCUSSION_ENTRY_CREATED: Final = "discussion_entry_created"
DISCUSSION_HIGHLIGHT_CREATED: Final = "discussion_highlight_created"

PERSONA_FORUM_CREATED: Final = "persona_forum_created"
CONSULT_REQUESTED: Final = "consult_requested"
CONSULT_COMPLETED: Final = "consult_completed"
HERO_INVITED: Final = "hero_invited"
HERO_RETIRED: Final = "hero_retired"

OPERATOR_INTENT: Final = "operator_intent"
OPERATOR_INTENT_APPLIED: Final = "operator_intent_applied"
OPERATOR_INTENT_IGNORED: Final = "operator_intent_ignored"

NARRATOR_SIDECAR_REQUESTED: Final = "narrator_sidecar_requested"
NARRATOR_SIDECAR_SKIPPED: Final = "narrator_sidecar_skipped"
NARRATOR_SIDECAR_FALLBACK: Final = "narrator_sidecar_fallback"
NARRATOR_SIDECAR_COMPLETED: Final = "narrator_sidecar_completed"

ATOM_STARTED: Final = "atom_started"
ATOM_COMPLETED: Final = "atom_completed"

DEMO_PLANNED: Final = "demo_planned"
DEMO_SKIPPED: Final = "demo_skipped"
DEMO_CAPTURE_STARTED: Final = "demo_capture_started"
DEMO_ARTIFACT_CREATED: Final = "demo_artifact_created"
DEMO_CAPTURE_FAILED: Final = "demo_capture_failed"
DEMO_PRESENTED: Final = "demo_presented"

ARTIFACT_PREVIEW_CREATED: Final = "artifact_preview_created"

EVENT_TYPES: frozenset[str] = frozenset({
    RUN_STARTED,
    RUN_COMPLETE,
    RUN_ERROR,
    PHASE_START,
    PHASE_DONE,
    PHASE_RETRY,
    PHASE_ERROR,
    CHECKPOINT,
    GATE_OPENED,
    GATE_DECIDED,
    USAGE_RECORDED,
    PROVIDER_CALL_ERROR,
    BUDGET_WARNING,
    BUDGET_EXCEEDED,
    BUDGET_GATE_OPENED,
    BUDGET_GATE_DECIDED,
    LOOP_ENTERED,
    LOOP_PROGRESSED,
    LOOP_BLOCKED,
    LOOP_REPAIRED,
    LOOP_COMPLETED,
    LOOP_REOPENED,
    MEMORY_STATUS,
    MEMORY_REFRESHED,
    MEMORY_SEARCH_COMPLETED,
    MEMORY_ERROR,
    MEMORY_DIFF,
    NEXT_STEP_PACKET_CREATED,
    NARRATIVE_DIGEST_CREATED,
    DISCUSSION_ENTRY_CREATED,
    DISCUSSION_HIGHLIGHT_CREATED,
    PERSONA_FORUM_CREATED,
    CONSULT_REQUESTED,
    CONSULT_COMPLETED,
    HERO_INVITED,
    HERO_RETIRED,
    OPERATOR_INTENT,
    OPERATOR_INTENT_APPLIED,
    OPERATOR_INTENT_IGNORED,
    NARRATOR_SIDECAR_REQUESTED,
    NARRATOR_SIDECAR_SKIPPED,
    NARRATOR_SIDECAR_FALLBACK,
    NARRATOR_SIDECAR_COMPLETED,
    ATOM_STARTED,
    ATOM_COMPLETED,
    DEMO_PLANNED,
    DEMO_SKIPPED,
    DEMO_CAPTURE_STARTED,
    DEMO_ARTIFACT_CREATED,
    DEMO_CAPTURE_FAILED,
    DEMO_PRESENTED,
    ARTIFACT_PREVIEW_CREATED,
})


def is_known_event_type(event_type: str) -> bool:
    return event_type in EVENT_TYPES
