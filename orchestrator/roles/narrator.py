"""Narrator / Scribe role for sourced narrative digest upgrades."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.lib.discussion import append_discussion_entry
from orchestrator.lib.memory_palace import memory_event_fields
from orchestrator.lib.narrative import (
    build_narrative_digest,
    validate_narrative_digest,
    write_narrative_digest,
)
from orchestrator.lib.opencode import SessionRunner
from orchestrator.lib.opencode_audit import emit_session_audit
from orchestrator.lib.scrub import scrub_payload, scrub_text
from orchestrator.lib.state import State
from orchestrator.lib.workflow import load_workflow

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts" / "narrator"


class NarratorError(Exception):
    """Raised when a narrator session fails before fallback can be used."""


class Narrator:
    """Runs a bounded read-only narrator session and validates JSON output."""

    _phase = "narrator"
    _role = "narrator"

    def __init__(self, runner: SessionRunner, state: State) -> None:
        self.runner = runner
        self.state = state

    def execute(
        self,
        events: list[dict[str, Any]],
        *,
        next_step_packet: dict[str, Any] | None = None,
        emit: bool = True,
    ) -> dict[str, Any]:
        """Return a validated narrator digest or deterministic fallback."""
        deterministic = build_narrative_digest(
            self.state.project_dir,
            events,
            next_step_packet=next_step_packet,
        )
        packet = build_narrator_packet(
            self.state,
            events,
            next_step_packet=next_step_packet,
            deterministic_digest=deterministic,
        )
        prompt = self._load_prompt().format(packet_json=json.dumps(packet, indent=2, sort_keys=True))

        try:
            result = self.runner.run(prompt)
        except Exception:
            return {**deterministic, "fallback_used": True, "fallback_reason": "runner_error"}

        emit_session_audit(
            self.state,
            result,
            role=self._role,
            phase=self._phase,
            step=self._phase,
            prompt=prompt,
        )
        if result.exit_code != 0 or not result.assistant_text.strip():
            diagnostic = write_narrator_diagnostic(
                self.state.project_dir,
                reason="empty_or_failed_session",
                raw_output=result.assistant_text,
                source_events=events,
            )
            return {
                **deterministic,
                "fallback_used": True,
                "fallback_reason": "empty_or_failed_session",
                "diagnostic_artifact_refs": [diagnostic],
            }

        try:
            digest = parse_narrator_digest(result.assistant_text, packet)
        except Exception as exc:
            diagnostic = write_narrator_diagnostic(
                self.state.project_dir,
                reason="invalid_narrator_json",
                raw_output=result.assistant_text,
                source_events=events,
                error=str(exc),
            )
            return {
                **deterministic,
                "fallback_used": True,
                "fallback_reason": "invalid_narrator_json",
                "diagnostic_artifact_refs": [diagnostic],
            }

        digest["generated_by"] = "narrator"
        provenance = memory_event_fields(None, self.state.project_dir)
        digest.setdefault("wake_up_hash", provenance["wake_up_hash"])
        digest.setdefault("memory_refs", list(provenance["memory_refs"]))
        write_narrative_digest(self.state.project_dir, digest)
        if emit:
            self._emit_digest(digest)
            self._emit_discussion_entry(digest)
        return digest

    @staticmethod
    def _load_prompt() -> str:
        return (_PROMPT_DIR / "generate.txt").read_text(encoding="utf-8")

    def _emit_digest(self, digest: dict[str, Any]) -> None:
        event_bus = getattr(self.state, "events", None)
        if event_bus is None:
            return
        artifact_refs = [
            f".orchestrator/narrative/digests/{digest['digest_id']}.json",
            f".orchestrator/narrative/digests/{digest['digest_id']}.md",
        ]
        event_bus.emit(
            "narrative_digest_created",
            project_id=self.state.project_dir.name,
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
            wake_up_hash=digest.get("wake_up_hash"),
            memory_refs=list(digest.get("memory_refs") or []),
            digest=digest,
            generated_by="narrator",
        )

    def _emit_discussion_entry(self, digest: dict[str, Any]) -> None:
        event_bus = getattr(self.state, "events", None)
        if event_bus is None:
            return
        append_discussion_entry(
            self.state.project_dir,
            speaker="Narrator",
            entry_type="agent_summary",
            atom_id=None,
            text=str(digest.get("summary") or ""),
            source_refs=[f"event:{event_id}" for event_id in digest["source_event_ids"]],
            artifact_refs=[f".orchestrator/narrative/digests/{digest['digest_id']}.json"],
            metadata={"digest_id": digest["digest_id"], "generated_by": "narrator"},
            event_bus=event_bus,
            project_id=self.state.project_dir.name,
        )


def build_narrator_packet(
    state: State,
    events: list[dict[str, Any]],
    *,
    next_step_packet: dict[str, Any] | None = None,
    deterministic_digest: dict[str, Any] | None = None,
    max_events: int = 10,
) -> dict[str, Any]:
    """Build the bounded packet passed to the narrator agent."""
    recent = [scrub_payload(_event_view(event)) for event in events[-max_events:]]
    return {
        "project_goal": scrub_text(_read_text(state.project_dir / "qwendea.md", limit=1200)),
        "workflow": [
            {
                "id": step.get("id"),
                "title": step.get("title"),
                "type": step.get("type"),
                "handler": step.get("handler"),
                "enabled": step.get("enabled"),
            }
            for step in load_workflow(state.project_dir)
        ],
        "events": recent,
        "next_step_packet": scrub_payload(next_step_packet or {}),
        "deterministic_digest": scrub_payload(deterministic_digest or {}),
        "discussion": _recent_jsonl(state.project_dir / ".orchestrator" / "discussion" / "log.jsonl", limit=8),
        "artifacts": _artifact_excerpts(state.project_dir),
    }


def parse_narrator_digest(raw: str, packet: dict[str, Any]) -> dict[str, Any]:
    """Parse, scrub, and validate a narrator JSON digest."""
    parsed = json.loads(_json_object_text(raw))
    if not isinstance(parsed, dict):
        raise NarratorError("narrator output must be an object")

    event_ids = {
        event_id
        for event_id in (event.get("event_id") for event in packet.get("events", []) if isinstance(event, dict))
        if isinstance(event_id, str)
    }
    source_events = [
        {"event_id": event_id}
        for event_id in sorted(event_ids)
    ]
    digest = {
        "digest_id": f"narrator_{_stable_hash(parsed)[:16]}",
        "window": {
            "from_event_id": min(event_ids) if event_ids else None,
            "to_event_id": max(event_ids) if event_ids else None,
            "event_count": len(event_ids),
        },
        "title": scrub_text(_string(parsed.get("title")) or "Narrator digest"),
        "summary": scrub_text(_string(parsed.get("summary"))),
        "highlights": scrub_payload(parsed.get("highlights") if isinstance(parsed.get("highlights"), list) else []),
        "risks": [scrub_text(item) for item in _strings(parsed.get("risks"))][:4],
        "open_questions": [scrub_text(item) for item in _strings(parsed.get("open_questions"))][:4],
        "next_step_hint": scrub_text(_string(parsed.get("next_step_hint"))),
        "source_event_ids": _strings(parsed.get("source_event_ids")),
        "artifact_refs": _validated_artifact_refs(_strings(parsed.get("artifact_refs"))),
    }
    validate_narrative_digest(digest, source_events)
    return digest


def write_narrator_diagnostic(
    project_dir: Path,
    *,
    reason: str,
    raw_output: str,
    source_events: list[dict[str, Any]],
    error: str | None = None,
) -> str:
    """Persist rejected narrator output without emitting it as ledger truth."""
    event_ids = [
        event_id
        for event_id in (_string(event.get("event_id")) for event in source_events)
        if event_id
    ]
    seed = {
        "reason": reason,
        "source_event_ids": event_ids,
        "raw_output": raw_output[:2000],
        "error": error or "",
    }
    diagnostic_id = f"narrator_diag_{_stable_hash(seed)[:16]}"
    rel = f".orchestrator/narrative/diagnostics/{diagnostic_id}.json"
    path = project_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "diagnostic_id": diagnostic_id,
        "reason": scrub_text(reason),
        "error": scrub_text(error or ""),
        "source_event_ids": event_ids,
        "raw_output_excerpt": scrub_text(raw_output[:2000]),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rel


def _event_view(event: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "event_id",
        "type",
        "ts",
        "name",
        "step",
        "gate",
        "decision",
        "kind",
        "atom_id",
        "summary",
        "title",
        "source_refs",
        "artifact_refs",
    )
    return {key: event[key] for key in keep if key in event}


def _artifact_excerpts(project_dir: Path) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for ref in ("qwendea.md", "PERSONA_FORUM.md", "FOUNDING_TEAM.json"):
        path = project_dir / ref
        if path.exists() and path.is_file():
            out.append({"ref": ref, "excerpt": scrub_text(_read_text(path, limit=1000))})
    return out


def _recent_jsonl(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(scrub_payload(item))
    return rows


def _read_text(path: Path, *, limit: int) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except FileNotFoundError:
        return ""


def _json_object_text(raw: str) -> str:
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise NarratorError("narrator output did not contain a JSON object")
    return raw[start:end + 1]


def _stable_hash(value: dict[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _validated_artifact_refs(refs: list[str]) -> list[str]:
    out: list[str] = []
    for ref in refs:
        path = Path(ref)
        if not ref or ref.startswith(("/", "\\")) or path.is_absolute() or ".." in path.parts:
            raise NarratorError(f"unsafe artifact ref: {ref}")
        out.append(ref)
    return out


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []
