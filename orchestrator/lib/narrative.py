"""Deterministic narrative digests for replayable PWA story state."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.lib.memory_palace import memory_event_fields
from orchestrator.lib.scrub import scrub_text


class NarrativeValidationError(ValueError):
    """Raised when a digest cannot be safely emitted or persisted."""


def build_narrative_digest(
    project_dir: Path,
    events: list[dict[str, Any]],
    *,
    next_step_packet: dict[str, Any] | None = None,
    memory_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact deterministic digest from a bounded event window."""
    source_events = [event for event in events if isinstance(event, dict)]
    event_ids = [
        event_id for event_id in (_string(event.get("event_id")) for event in source_events)
        if event_id
    ]
    title = _title_for_window(source_events)
    highlights = _highlights_for_events(source_events)
    artifact_refs = _artifact_refs(source_events, next_step_packet)
    provenance = memory_fields or {}
    digest = {
        "digest_id": _digest_id(source_events, next_step_packet),
        "window": {
            "from_event_id": event_ids[0] if event_ids else None,
            "to_event_id": event_ids[-1] if event_ids else None,
            "event_count": len(source_events),
        },
        "title": title,
        "summary": _summary_for_window(source_events, next_step_packet),
        "highlights": highlights,
        "risks": _risks_for_events(source_events),
        "open_questions": _open_questions_for_events(source_events),
        "next_step_hint": _next_step_hint(next_step_packet),
        "source_event_ids": event_ids,
        "artifact_refs": artifact_refs,
        "wake_up_hash": provenance.get("wake_up_hash"),
        "memory_refs": list(provenance.get("memory_refs") or []),
    }
    validate_narrative_digest(digest, source_events)
    return digest


def emit_narrative_digest(
    event_bus: Any,
    project_dir: Path,
    events: list[dict[str, Any]],
    *,
    next_step_packet: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any] | None:
    """Persist and emit a deterministic digest event if the window has content."""
    source_events = [event for event in events if isinstance(event, dict)]
    if not source_events:
        return None
    memory_fields = memory_event_fields(project_id or project_dir.name, project_dir)
    digest = build_narrative_digest(
        project_dir,
        source_events,
        next_step_packet=next_step_packet,
        memory_fields=memory_fields,
    )
    written = write_narrative_digest(project_dir, digest)
    artifact_refs = [str(path.relative_to(project_dir)) for path in written]
    return event_bus.emit(
        "narrative_digest_created",
        project_id=project_id or project_dir.name,
        digest_id=digest["digest_id"],
        window=digest["window"],
        title=digest["title"],
        summary=digest["summary"],
        highlights=digest["highlights"],
        risks=digest["risks"],
        open_questions=digest["open_questions"],
        next_step_hint=digest["next_step_hint"],
        source_event_ids=digest["source_event_ids"],
        artifact_refs=artifact_refs,
        source_refs=[
            *[f"event:{event_id}" for event_id in digest["source_event_ids"]],
            *[f"artifact:{ref}" for ref in artifact_refs],
        ],
        wake_up_hash=memory_fields["wake_up_hash"],
        memory_refs=list(memory_fields["memory_refs"]),
        digest=digest,
    )


def validate_narrative_digest(
    digest: dict[str, Any],
    source_events: list[dict[str, Any]],
) -> None:
    """Validate source credibility and replay-safe path references."""
    source_ids = {
        event_id for event_id in (_string(event.get("event_id")) for event in source_events)
        if event_id
    }
    digest_ids = set(_strings(digest.get("source_event_ids")))
    if not digest_ids.issubset(source_ids):
        missing = sorted(digest_ids - source_ids)
        raise NarrativeValidationError(f"digest references unknown source events: {missing}")

    if len(_string(digest.get("summary"))) > 360:
        raise NarrativeValidationError("digest summary exceeds 360 characters")

    for ref in _strings(digest.get("artifact_refs")):
        if not _safe_relative_ref(ref):
            raise NarrativeValidationError(f"unsafe artifact ref: {ref}")

    highlights = digest.get("highlights")
    if not isinstance(highlights, list):
        raise NarrativeValidationError("digest highlights must be a list")
    for highlight in highlights:
        if not isinstance(highlight, dict):
            raise NarrativeValidationError("digest highlight must be an object")
        refs = _strings(highlight.get("source_refs"))
        if not refs:
            raise NarrativeValidationError("digest highlight is missing source_refs")
        for ref in refs:
            if ref.startswith("event:") and ref.removeprefix("event:") not in source_ids:
                raise NarrativeValidationError(f"highlight references unknown event: {ref}")
            if ref.startswith("artifact:") and not _safe_relative_ref(ref.removeprefix("artifact:")):
                raise NarrativeValidationError(f"highlight references unsafe artifact: {ref}")
            if not ref.startswith(("event:", "artifact:")):
                raise NarrativeValidationError(f"unsupported highlight source ref: {ref}")


def write_narrative_digest(project_dir: Path, digest: dict[str, Any]) -> list[Path]:
    """Write JSON and Markdown projections for a digest."""
    digest_dir = project_dir / ".orchestrator" / "narrative" / "digests"
    digest_dir.mkdir(parents=True, exist_ok=True)
    digest_id = _string(digest.get("digest_id")) or "digest"
    json_path = digest_dir / f"{digest_id}.json"
    md_path = digest_dir / f"{digest_id}.md"
    json_path.write_text(json.dumps(digest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_digest_markdown(digest), encoding="utf-8")
    return [json_path, md_path]


def _digest_id(events: list[dict[str, Any]], next_step_packet: dict[str, Any] | None) -> str:
    seed = {
        "events": [
            {
                "event_id": event.get("event_id"),
                "type": event.get("type"),
                "name": event.get("name"),
                "gate": event.get("gate"),
                "decision": event.get("decision"),
            }
            for event in events
        ],
        "next_step": next_step_packet.get("step") if isinstance(next_step_packet, dict) else None,
    }
    digest = hashlib.sha256(json.dumps(seed, sort_keys=True).encode("utf-8")).hexdigest()
    return f"dwa_{digest[:16]}"


def _title_for_window(events: list[dict[str, Any]]) -> str:
    if not events:
        return "No events yet"
    last = events[-1]
    event_type = _string(last.get("type"))
    if event_type == "phase_done":
        return f"{_subject(last)} completed"
    if event_type == "gate_decided":
        return f"{_subject(last)} gate decided"
    if event_type == "operator_intent":
        return "Operator intent queued"
    if event_type == "phase_error":
        return f"{_subject(last)} hit an error"
    return f"{event_type or 'event'} update"


def _summary_for_window(
    events: list[dict[str, Any]],
    next_step_packet: dict[str, Any] | None,
) -> str:
    counts: dict[str, int] = {}
    for event in events:
        event_type = _string(event.get("type")) or "event"
        counts[event_type] = counts.get(event_type, 0) + 1
    parts = [f"{count} {event_type}" for event_type, count in sorted(counts.items())]
    next_hint = _next_step_hint(next_step_packet)
    suffix = f" Next: {next_hint}." if next_hint else ""
    return scrub_text(f"Recent ledger window: {', '.join(parts)}.{suffix}")[:360]


def _highlights_for_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    highlights: list[dict[str, Any]] = []
    for event in events[-6:]:
        event_id = _string(event.get("event_id"))
        if not event_id:
            continue
        text = _highlight_text(event)
        if not text:
            continue
        highlights.append({
            "text": scrub_text(text),
            "source_refs": [f"event:{event_id}"],
        })
    if highlights:
        return highlights
    event_ids = [
        event_id for event_id in (_string(event.get("event_id")) for event in events)
        if event_id
    ]
    if event_ids:
        return [{"text": "Ledger window captured.", "source_refs": [f"event:{event_ids[-1]}"]}]
    return []


def _highlight_text(event: dict[str, Any]) -> str:
    event_type = _string(event.get("type"))
    subject = _subject(event)
    if event_type == "phase_start":
        return f"Started {subject}."
    if event_type == "phase_done":
        return f"Completed {subject}."
    if event_type == "phase_error":
        return f"{subject} reported an error."
    if event_type == "gate_decided":
        return f"Gate {subject} was {_string(event.get('decision')) or 'decided'}."
    if event_type == "next_step_packet_created":
        packet = event.get("packet") if isinstance(event.get("packet"), dict) else {}
        title = _string(packet.get("title")) or _string(event.get("title")) or subject
        return f"Next step packet points to {title}."
    if event_type == "operator_intent":
        return f"Operator queued a {_string(event.get('kind')) or 'control'} intent for {subject}."
    if event_type == "operator_intent_applied":
        return f"Operator intent affected {_string(event.get('applied_to')) or subject}."
    if event_type == "operator_intent_ignored":
        return f"Operator intent ended as ignored: {_string(event.get('reason')) or 'no reason'}."
    if event_type.startswith("loop_"):
        return f"Loop state moved through {_string(event.get('loop_stage')) or subject}."
    return ""


def _risks_for_events(events: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    for event in events:
        event_type = _string(event.get("type"))
        if event_type == "phase_error":
            risks.append(scrub_text(f"{_subject(event)} error: {_string(event.get('error')) or 'unknown error'}"))
        if event_type == "gate_decided" and event.get("decision") == "rejected":
            risks.append(f"{_subject(event)} gate rejected.")
        if event_type == "operator_intent_ignored":
            risks.append(f"Intent ignored: {_string(event.get('reason')) or 'unknown reason'}.")
    return _dedupe(risks)[:4]


def _open_questions_for_events(events: list[dict[str, Any]]) -> list[str]:
    if any(_string(event.get("type")) == "operator_intent" for event in events):
        return ["Does the queued operator intent need a terminal applied or ignored outcome?"]
    if any(_string(event.get("type")) == "gate_opened" for event in events):
        return ["Is the open gate ready for an operator decision?"]
    return []


def _next_step_hint(next_step_packet: dict[str, Any] | None) -> str | None:
    if not isinstance(next_step_packet, dict):
        return None
    step = _string(next_step_packet.get("step"))
    title = _string(next_step_packet.get("title")) or step
    if not step:
        return None
    return title if title == step else f"{title} ({step})"


def _artifact_refs(
    events: list[dict[str, Any]],
    next_step_packet: dict[str, Any] | None,
) -> list[str]:
    refs: list[str] = []
    for event in events:
        refs.extend(_strings(event.get("artifact_refs")))
    if isinstance(next_step_packet, dict):
        for ref in _strings(next_step_packet.get("source_refs")):
            if ref.startswith("artifact:"):
                refs.append(ref.removeprefix("artifact:"))
    return _dedupe([ref for ref in refs if _safe_relative_ref(ref)])[:10]


def _digest_markdown(digest: dict[str, Any]) -> str:
    highlights = digest.get("highlights") if isinstance(digest.get("highlights"), list) else []
    lines = [
        f"# {_string(digest.get('title')) or 'Narrative Digest'}",
        "",
        _string(digest.get("summary")),
        "",
        "## Highlights",
    ]
    if highlights:
        for highlight in highlights:
            text = _string(highlight.get("text")) if isinstance(highlight, dict) else ""
            lines.append(f"- {text}")
    else:
        lines.append("- No sourced highlights.")
    return "\n".join(lines).rstrip() + "\n"


def _subject(event: dict[str, Any]) -> str:
    return (
        _string(event.get("name"))
        or _string(event.get("step"))
        or _string(event.get("gate"))
        or _string(event.get("atom_id"))
        or "run"
    )


def _safe_relative_ref(ref: str) -> bool:
    if not ref or ref.startswith(("/", "\\")):
        return False
    path = Path(ref)
    return not path.is_absolute() and ".." not in path.parts


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
