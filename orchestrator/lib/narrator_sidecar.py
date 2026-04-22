"""Narrator sidecar coordination for sourced digest and packet refinement."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import fcntl

from orchestrator.lib.event_schema import new_event_id
from orchestrator.lib.narrative import emit_narrative_digest
from orchestrator.lib.next_step import emit_next_step_packet_event
from orchestrator.lib.state import State
from orchestrator.roles.narrator import Narrator

TRIGGER_TYPES = {
    "phase_done",
    "gate_decided",
    "phase_error",
    "operator_intent",
    "narrator_pre_step",
    "narrator_phase_requested",
}
URGENT_TRIGGER_TYPES = {
    "gate_decided",
    "phase_error",
    "operator_intent",
    "narrator_pre_step",
    "narrator_phase_requested",
}


class SidecarOutcome(str, Enum):
    """Terminal narrator sidecar outcomes."""

    SKIPPED = "skipped"
    RUNNER_UNAVAILABLE = "runner_unavailable"
    FALLBACK = "fallback"
    COMPLETED = "completed"


@dataclass(frozen=True)
class NarratorSidecarResult:
    """Result of one sidecar trigger attempt."""

    status: str
    reason: str
    digest_id: str | None = None
    packet_id: str | None = None
    outcome: SidecarOutcome | None = None


def run_narrator_sidecar(
    state: State,
    event_bus: Any,
    source_events: list[dict[str, Any]],
    *,
    next_step_packet: dict[str, Any] | None,
    runner: Any | None,
    project_id: str | None = None,
) -> NarratorSidecarResult | None:
    """Run narrator after a meaningful ledger event, with deterministic fallback."""
    events = [event for event in source_events if isinstance(event, dict)]
    if not events:
        return None
    trigger_event = events[-1]
    if str(trigger_event.get("type") or "") not in TRIGGER_TYPES:
        return None

    run_id = project_id or state.project_dir.name
    event_count = _event_count(event_bus)
    decision = should_run_sidecar(state.project_dir, trigger_event, event_count=event_count)
    if not decision.run:
        return _finish_sidecar_outcome(
            state,
            event_bus,
            outcome=SidecarOutcome.SKIPPED,
            run_id=run_id,
            trigger_event=trigger_event,
            event_count=event_count,
            reason=decision.reason,
            next_step_packet=next_step_packet,
            digest_id=None,
            packet_id=None,
        )

    state.events = event_bus
    if runner is None:
        emitted = emit_narrative_digest(
            event_bus,
            state.project_dir,
            events,
            next_step_packet=next_step_packet,
        )
        return _finish_sidecar_outcome(
            state,
            event_bus,
            outcome=SidecarOutcome.RUNNER_UNAVAILABLE,
            run_id=run_id,
            trigger_event=trigger_event,
            event_count=event_count,
            reason="narrator_runner_unavailable",
            next_step_packet=next_step_packet,
            digest_id=_string(emitted.get("digest_id")) if isinstance(emitted, dict) else None,
            packet_id=None,
        )

    digest = Narrator(runner, state).execute(
        events,
        next_step_packet=next_step_packet,
        emit=True,
    )
    if digest.get("fallback_used"):
        emitted = emit_narrative_digest(
            event_bus,
            state.project_dir,
            events,
            next_step_packet=next_step_packet,
        )
        reason = _string(digest.get("fallback_reason")) or "fallback_used"
        return _finish_sidecar_outcome(
            state,
            event_bus,
            outcome=SidecarOutcome.FALLBACK,
            run_id=run_id,
            trigger_event=trigger_event,
            event_count=event_count,
            reason=reason,
            next_step_packet=next_step_packet,
            digest_id=_string(emitted.get("digest_id")) if isinstance(emitted, dict) else None,
            packet_id=None,
            artifact_refs=_strings(digest.get("diagnostic_artifact_refs")),
        )

    packet_id: str | None = None
    if next_step_packet is not None:
        refined = build_narrator_refined_packet(next_step_packet, digest)
        emit_next_step_packet_event(event_bus, run_id, refined)
        packet_id = _string(refined.get("packet_id"))

    return _finish_sidecar_outcome(
        state,
        event_bus,
        outcome=SidecarOutcome.COMPLETED,
        run_id=run_id,
        trigger_event=trigger_event,
        event_count=event_count,
        reason="completed",
        next_step_packet=next_step_packet,
        digest_id=_string(digest.get("digest_id")),
        packet_id=packet_id,
    )


def _finish_sidecar_outcome(
    state: State,
    event_bus: Any,
    *,
    outcome: SidecarOutcome,
    run_id: str,
    trigger_event: dict[str, Any],
    event_count: int | None,
    reason: str,
    next_step_packet: dict[str, Any] | None,
    digest_id: str | None,
    packet_id: str | None,
    artifact_refs: list[str] | None = None,
) -> NarratorSidecarResult:
    """Emit and persist the sidecar outcome contract from one place."""
    event_type = {
        SidecarOutcome.RUNNER_UNAVAILABLE: "narrator_sidecar_skipped",
        SidecarOutcome.FALLBACK: "narrator_sidecar_fallback",
        SidecarOutcome.COMPLETED: "narrator_sidecar_completed",
    }.get(outcome)
    if event_type is not None:
        _emit_sidecar_event(
            event_bus,
            event_type,
            run_id,
            trigger_event,
            reason=reason,
            next_step_packet=next_step_packet,
            digest_id=digest_id,
            refined_packet_id=packet_id if outcome == SidecarOutcome.COMPLETED else None,
            artifact_refs=artifact_refs,
        )
        record_sidecar_trigger(
            state.project_dir,
            trigger_event,
            event_count=event_count,
            status=_sidecar_state_status(outcome, reason),
        )

    return NarratorSidecarResult(
        status=_sidecar_result_status(outcome),
        reason=reason,
        digest_id=digest_id,
        packet_id=packet_id,
        outcome=outcome,
    )


def _sidecar_result_status(outcome: SidecarOutcome) -> str:
    if outcome == SidecarOutcome.RUNNER_UNAVAILABLE:
        return "fallback"
    return outcome.value


def _sidecar_state_status(outcome: SidecarOutcome, reason: str) -> str:
    if outcome == SidecarOutcome.RUNNER_UNAVAILABLE:
        return "runner_unavailable"
    if outcome == SidecarOutcome.FALLBACK:
        return f"fallback:{reason}"
    return outcome.value


@dataclass(frozen=True)
class SidecarDecision:
    run: bool
    reason: str


def should_run_sidecar(
    project_dir: Path,
    trigger_event: dict[str, Any],
    *,
    event_count: int | None = None,
) -> SidecarDecision:
    """Return whether a trigger should run the narrator sidecar."""
    trigger_type = _string(trigger_event.get("type"))
    if trigger_type not in TRIGGER_TYPES:
        return SidecarDecision(False, "unsupported_trigger")

    state = load_sidecar_state(project_dir)
    trigger_event_id = _string(trigger_event.get("event_id"))
    if trigger_event_id and trigger_event_id in state.get("processed_event_ids", []):
        return SidecarDecision(False, "trigger_already_processed")

    if trigger_type == "phase_done":
        phase = _string(trigger_event.get("name")) or _string(trigger_event.get("step"))
        phase_key = f"phase_done:{phase}"
        if phase and phase_key in state.get("phase_keys", []):
            return SidecarDecision(False, "phase_already_summarized")

    if trigger_type in URGENT_TRIGGER_TYPES:
        return SidecarDecision(True, "urgent_trigger")

    last_event_count = int(state.get("last_event_count") or 0)
    if event_count is None or event_count - last_event_count >= 10:
        return SidecarDecision(True, "event_window_ready")

    if trigger_type == "phase_done":
        return SidecarDecision(True, "phase_boundary")
    return SidecarDecision(False, "debounced")


def record_sidecar_trigger(
    project_dir: Path,
    trigger_event: dict[str, Any],
    *,
    event_count: int | None,
    status: str,
) -> None:
    """Persist sidecar debounce state for later triggers."""
    with _locked_sidecar_state(project_dir):
        state = load_sidecar_state(project_dir)
        processed = list(dict.fromkeys([
            *state.get("processed_event_ids", []),
            _string(trigger_event.get("event_id")),
        ]))
        phase_keys = list(state.get("phase_keys", []))
        if _string(trigger_event.get("type")) == "phase_done":
            phase = _string(trigger_event.get("name")) or _string(trigger_event.get("step"))
            if phase:
                phase_keys = list(dict.fromkeys([*phase_keys, f"phase_done:{phase}"]))
        state.update({
            "processed_event_ids": [item for item in processed if item][-80:],
            "phase_keys": phase_keys[-80:],
            "last_event_count": int(event_count or state.get("last_event_count") or 0),
            "last_status": status,
        })
        _write_sidecar_state_atomic(project_dir, state)


def build_narrator_refined_packet(
    base_packet: dict[str, Any],
    digest: dict[str, Any],
) -> dict[str, Any]:
    """Return a next-step packet copy with validated narrator language attached."""
    refined = dict(base_packet)
    base_packet_id = _string(base_packet.get("packet_id"))
    digest_id = _string(digest.get("digest_id"))
    source_event_ids = [item for item in _strings(digest.get("source_event_ids")) if item]
    digest_artifacts = [item for item in _strings(digest.get("artifact_refs")) if item]
    summary = _string(digest.get("summary"))
    highlights = [
        _string(highlight.get("text"))
        for highlight in digest.get("highlights", [])
        if isinstance(highlight, dict) and _string(highlight.get("text"))
    ]
    base_preview = [item for item in _strings(base_packet.get("context_preview")) if item]
    narrator_preview = [item for item in [summary, *highlights[:2]] if item]
    source_refs = [
        *_strings(base_packet.get("source_refs")),
        *[f"event:{event_id}" for event_id in source_event_ids],
        *[f"artifact:{ref}" for ref in digest_artifacts],
    ]
    refined.update({
        "packet_id": f"next_{new_event_id()}",
        "base_packet_id": base_packet_id,
        "refined_by": "narrator",
        "narrative_digest_id": digest_id,
        "context_preview": _dedupe([*narrator_preview, *base_preview])[:8],
        "source_refs": _dedupe(source_refs),
    })
    return refined


def emit_narrator_sidecar_requested(
    event_bus: Any,
    *,
    project_id: str,
    trigger_event: dict[str, Any],
    next_step_packet: dict[str, Any] | None,
    reason: str,
) -> None:
    """Emit a fast request event for async narrator work."""
    _emit_sidecar_event(
        event_bus,
        "narrator_sidecar_requested",
        project_id,
        trigger_event,
        reason=reason,
        next_step_packet=next_step_packet,
    )


def load_sidecar_state(project_dir: Path) -> dict[str, Any]:
    """Load persisted sidecar debounce state."""
    path = sidecar_state_path(project_dir)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def sidecar_state_path(project_dir: Path) -> Path:
    return project_dir / ".orchestrator" / "narrative" / "sidecar-state.json"


def _sidecar_lock_path(project_dir: Path) -> Path:
    return project_dir / ".orchestrator" / "narrative" / "sidecar-state.lock"


@contextmanager
def _locked_sidecar_state(project_dir: Path):
    """Serialize sidecar state read-modify-write updates on POSIX."""
    lock_path = _sidecar_lock_path(project_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_sidecar_state_atomic(project_dir: Path, state: dict[str, Any]) -> None:
    """Persist sidecar state via same-directory temp file + atomic replace."""
    path = sidecar_state_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def _emit_sidecar_event(
    event_bus: Any,
    event_type: str,
    project_id: str,
    trigger_event: dict[str, Any],
    *,
    reason: str,
    next_step_packet: dict[str, Any] | None,
    digest_id: str | None = None,
    refined_packet_id: str | None = None,
    artifact_refs: list[str] | None = None,
) -> None:
    trigger_event_id = _string(trigger_event.get("event_id"))
    packet_id = _string((next_step_packet or {}).get("packet_id"))
    event_bus.emit(
        event_type,
        project_id=project_id,
        trigger_event_id=trigger_event_id,
        trigger_type=_string(trigger_event.get("type")),
        reason=reason,
        packet_id=packet_id or None,
        digest_id=digest_id,
        refined_packet_id=refined_packet_id,
        source_refs=[f"event:{trigger_event_id}"] if trigger_event_id else [],
        artifact_refs=artifact_refs or [],
    )


def _event_count(event_bus: Any) -> int | None:
    events = getattr(event_bus, "events", None)
    return len(events) if isinstance(events, list) else None


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
