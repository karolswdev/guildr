"""Durable discussion log projections for operator and persona story state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from orchestrator.lib.event_schema import new_event_id, now_iso
from orchestrator.lib.scrub import scrub_payload, scrub_text


class DiscussionValidationError(ValueError):
    """Raised when a discussion row cannot be safely written or emitted."""


def discussion_dir(project_dir: Path) -> Path:
    path = project_dir / ".orchestrator" / "discussion"
    path.mkdir(parents=True, exist_ok=True)
    return path


def discussion_log_path(project_dir: Path) -> Path:
    return discussion_dir(project_dir) / "log.jsonl"


def discussion_highlights_path(project_dir: Path) -> Path:
    return discussion_dir(project_dir) / "highlights.jsonl"


def append_discussion_entry(
    project_dir: Path,
    *,
    speaker: str,
    text: str,
    entry_type: str,
    atom_id: str | None = None,
    source_refs: list[str] | None = None,
    artifact_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    event_bus: Any | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Append one scrubbed discussion entry and optionally emit its event."""
    row = {
        "discussion_entry_id": f"disc_{new_event_id()}",
        "ts": now_iso(),
        "speaker": scrub_text(speaker.strip() or "unknown"),
        "entry_type": scrub_text(entry_type.strip() or "note"),
        "atom_id": atom_id,
        "text": scrub_text(text.strip()),
        "source_refs": _dedupe(source_refs or []),
        "artifact_refs": _safe_artifact_refs(artifact_refs or []),
        "metadata": scrub_payload(metadata or {}),
    }
    validate_discussion_entry(row)
    _append_jsonl(discussion_log_path(project_dir), row)
    if event_bus is not None:
        event_bus.emit(
            "discussion_entry_created",
            project_id=project_id or project_dir.name,
            discussion_entry_id=row["discussion_entry_id"],
            entry=row,
            speaker=row["speaker"],
            entry_type=row["entry_type"],
            atom_id=row["atom_id"],
            text=row["text"],
            source_refs=row["source_refs"],
            artifact_refs=row["artifact_refs"],
        )
    return row


def append_discussion_highlight(
    project_dir: Path,
    *,
    text: str,
    highlight_type: str = "notable",
    atom_id: str | None = None,
    source_refs: list[str] | None = None,
    artifact_refs: list[str] | None = None,
    event_bus: Any | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Append one sourced discussion highlight and optionally emit its event."""
    row = {
        "discussion_highlight_id": f"high_{new_event_id()}",
        "ts": now_iso(),
        "highlight_type": scrub_text(highlight_type.strip() or "notable"),
        "atom_id": atom_id,
        "text": scrub_text(text.strip()),
        "source_refs": _dedupe(source_refs or []),
        "artifact_refs": _safe_artifact_refs(artifact_refs or []),
    }
    validate_discussion_highlight(row)
    _append_jsonl(discussion_highlights_path(project_dir), row)
    if event_bus is not None:
        event_bus.emit(
            "discussion_highlight_created",
            project_id=project_id or project_dir.name,
            discussion_highlight_id=row["discussion_highlight_id"],
            highlight=row,
            highlight_type=row["highlight_type"],
            atom_id=row["atom_id"],
            text=row["text"],
            source_refs=row["source_refs"],
            artifact_refs=row["artifact_refs"],
        )
    return row


def append_persona_discussion_entries(
    project_dir: Path,
    personas: list[dict[str, Any]],
    *,
    event_bus: Any | None = None,
    project_id: str | None = None,
    source_refs: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Project persona mandates into the durable discussion log."""
    rows: list[dict[str, Any]] = []
    refs = source_refs or ["artifact:FOUNDING_TEAM.json", "artifact:PERSONA_FORUM.md"]
    for persona in sorted(personas, key=lambda item: int(item.get("turn_order", 0) or 0)):
        name = _string(persona.get("name")) or "Persona"
        mandate = _string(persona.get("mandate")) or "Provide concise review feedback."
        perspective = _string(persona.get("perspective")) or "stakeholder"
        veto_scope = _string(persona.get("veto_scope")) or "advisory"
        rows.append(append_discussion_entry(
            project_dir,
            speaker=name,
            entry_type="persona_statement",
            atom_id="persona_forum",
            text=f"{mandate} Perspective: {perspective}. Veto scope: {veto_scope}.",
            source_refs=refs,
            artifact_refs=["FOUNDING_TEAM.json", "PERSONA_FORUM.md"],
            metadata={"persona": scrub_payload(persona)},
            event_bus=event_bus,
            project_id=project_id,
        ))
    if rows:
        append_discussion_highlight(
            project_dir,
            text=f"Founding team discussion captured {len(rows)} persona statements.",
            highlight_type="persona_forum",
            atom_id="persona_forum",
            source_refs=[f"entry:{row['discussion_entry_id']}" for row in rows],
            artifact_refs=["PERSONA_FORUM.md"],
            event_bus=event_bus,
            project_id=project_id,
        )
    return rows


def rebuild_projection(project_dir: Path, events: list[dict[str, Any]]) -> dict[str, Path]:
    """Rebuild discussion projection files from durable events."""
    entries: list[dict[str, Any]] = []
    highlights: list[dict[str, Any]] = []
    for event in events:
        event_type = _string(event.get("type"))
        if event_type == "discussion_entry_created":
            entry = event.get("entry") if isinstance(event.get("entry"), dict) else {
                "discussion_entry_id": event.get("discussion_entry_id"),
                "ts": event.get("ts"),
                "speaker": event.get("speaker"),
                "entry_type": event.get("entry_type"),
                "atom_id": event.get("atom_id"),
                "text": event.get("text"),
                "source_refs": event.get("source_refs"),
                "artifact_refs": event.get("artifact_refs"),
                "metadata": {},
            }
            if isinstance(entry, dict):
                validate_discussion_entry(entry)
                entries.append(entry)
        if event_type == "discussion_highlight_created":
            highlight = event.get("highlight") if isinstance(event.get("highlight"), dict) else {
                "discussion_highlight_id": event.get("discussion_highlight_id"),
                "ts": event.get("ts"),
                "highlight_type": event.get("highlight_type"),
                "atom_id": event.get("atom_id"),
                "text": event.get("text"),
                "source_refs": event.get("source_refs"),
                "artifact_refs": event.get("artifact_refs"),
            }
            if isinstance(highlight, dict):
                validate_discussion_highlight(highlight)
                highlights.append(highlight)

    out_dir = discussion_dir(project_dir)
    log_rebuilt = out_dir / "log.jsonl.rebuilt"
    highlights_rebuilt = out_dir / "highlights.jsonl.rebuilt"
    _write_jsonl(log_rebuilt, entries)
    _write_jsonl(highlights_rebuilt, highlights)
    return {"log": log_rebuilt, "highlights": highlights_rebuilt}


def validate_discussion_entry(row: dict[str, Any]) -> None:
    if not _string(row.get("discussion_entry_id")):
        raise DiscussionValidationError("discussion_entry_id is required")
    if not _string(row.get("speaker")):
        raise DiscussionValidationError("speaker is required")
    if not _string(row.get("text")):
        raise DiscussionValidationError("text is required")
    if len(_string(row.get("text"))) > 1200:
        raise DiscussionValidationError("text exceeds 1200 characters")
    _validate_refs(row)


def validate_discussion_highlight(row: dict[str, Any]) -> None:
    if not _string(row.get("discussion_highlight_id")):
        raise DiscussionValidationError("discussion_highlight_id is required")
    if not _string(row.get("text")):
        raise DiscussionValidationError("text is required")
    _validate_refs(row)


def read_events(project_dir: Path) -> list[dict[str, Any]]:
    path = project_dir / ".orchestrator" / "events.jsonl"
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discussion projection tools")
    parser.add_argument("--rebuild", metavar="PROJECT_DIR", help="rebuild projection files from .orchestrator/events.jsonl")
    args = parser.parse_args(argv)
    if args.rebuild:
        project_dir = Path(args.rebuild)
        paths = rebuild_projection(project_dir, read_events(project_dir))
        print(paths["log"])
        print(paths["highlights"])
        return 0
    parser.print_help()
    return 2


def _validate_refs(row: dict[str, Any]) -> None:
    refs = _strings(row.get("source_refs"))
    if not refs:
        raise DiscussionValidationError("source_refs are required")
    for ref in refs:
        if ref.startswith("artifact:"):
            if not _safe_relative_ref(ref.removeprefix("artifact:")):
                raise DiscussionValidationError(f"unsafe artifact ref: {ref}")
            continue
        if ref.startswith(("event:", "entry:", "intent:", "workflow:", "memory:")):
            continue
        raise DiscussionValidationError(f"unsupported source ref: {ref}")
    for ref in _strings(row.get("artifact_refs")):
        if not _safe_relative_ref(ref):
            raise DiscussionValidationError(f"unsafe artifact ref: {ref}")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _safe_artifact_refs(refs: list[str]) -> list[str]:
    return _dedupe([ref for ref in refs if _safe_relative_ref(ref)])


def _safe_relative_ref(ref: str) -> bool:
    path = Path(ref)
    return bool(ref) and not ref.startswith(("/", "\\")) and not path.is_absolute() and ".." not in path.parts


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


if __name__ == "__main__":
    raise SystemExit(main())
