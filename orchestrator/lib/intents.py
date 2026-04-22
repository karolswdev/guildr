"""Durable operator intent registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.lib.event_schema import new_event_id, now_iso
from orchestrator.lib.scrub import scrub_payload

PROMPT_CONTEXT_KINDS = {"interject", "intercept", "reroute"}
UNSUPPORTED_PROMPT_KINDS = {"note", "resume", "skip", "retry"}


def intents_path(project_dir: Path) -> Path:
    path = project_dir / ".orchestrator" / "control" / "intents.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def create_queued_intent(
    project_dir: Path,
    *,
    kind: str,
    atom_id: str | None,
    payload: dict[str, Any],
    client_intent_id: str | None = None,
    intent_event_id: str | None = None,
) -> dict[str, Any]:
    """Persist one queued operator intent and return the registry row."""
    event_id = intent_event_id or new_event_id()
    row = {
        "ts": now_iso(),
        "client_intent_id": client_intent_id or f"intent_{event_id}",
        "intent_event_id": event_id,
        "kind": kind,
        "atom_id": atom_id,
        "payload": scrub_payload(payload),
        "status": "queued",
    }
    with intents_path(project_dir).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def read_intents(project_dir: Path) -> list[dict[str, Any]]:
    path = intents_path(project_dir)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def write_intents(project_dir: Path, rows: list[dict[str, Any]]) -> None:
    path = intents_path(project_dir)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def queued_intents_for_step(project_dir: Path, step: str) -> list[dict[str, Any]]:
    """Return queued intents that should be visible on a next-step packet."""
    out: list[dict[str, Any]] = []
    for item in read_intents(project_dir):
        if item.get("status") != "queued":
            continue
        atom_id = item.get("atom_id")
        if atom_id not in (None, "", step):
            continue
        out.append({
            "client_intent_id": item.get("client_intent_id"),
            "intent_event_id": item.get("intent_event_id"),
            "kind": item.get("kind"),
            "atom_id": atom_id,
            "payload": item.get("payload") if isinstance(item.get("payload"), dict) else {},
            "status": "queued",
        })
    return out


def consume_prompt_intents(
    project_dir: Path,
    step: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Mark queued prompt-context intents applied and return prompt lines/events."""
    rows = read_intents(project_dir)
    prompt_lines: list[str] = []
    applied_events: list[dict[str, Any]] = []
    changed = False
    applied_at = now_iso()

    for item in rows:
        if item.get("status") != "queued":
            continue
        if item.get("kind") not in PROMPT_CONTEXT_KINDS:
            continue
        atom_id = item.get("atom_id")
        if atom_id not in (None, "", step):
            continue

        instruction = _instruction_text(item.get("payload"))
        if not instruction:
            continue

        prompt_lines.append(f"- [{item.get('kind')}] {instruction}")
        item["status"] = "applied"
        item["applied_at"] = applied_at
        item["applied_to"] = "prompt_context"
        item["step"] = step
        changed = True
        applied_events.append({
            "client_intent_id": item.get("client_intent_id"),
            "intent_event_id": item.get("intent_event_id"),
            "kind": item.get("kind"),
            "atom_id": atom_id,
            "applied_to": "prompt_context",
            "step": step,
            "artifact_refs": [".orchestrator/control/intents.jsonl"],
            "source_refs": [
                f"event:{item.get('intent_event_id')}",
                "artifact:.orchestrator/control/intents.jsonl",
            ],
        })

    if changed:
        write_intents(project_dir, rows)
    return prompt_lines, applied_events


def ignore_queued_intents_for_passed_step(
    project_dir: Path,
    step: str,
) -> list[dict[str, Any]]:
    """Mark queued intents for a completed step ignored with terminal reasons."""
    rows = read_intents(project_dir)
    ignored_events: list[dict[str, Any]] = []
    changed = False
    ignored_at = now_iso()

    for item in rows:
        if item.get("status") != "queued":
            continue
        atom_id = item.get("atom_id")
        if atom_id not in (None, "", step):
            continue

        reason = "unsupported_kind" if item.get("kind") in UNSUPPORTED_PROMPT_KINDS else "target_step_passed"
        # Global intents stay queued until they are applied or a later full
        # lifecycle handler supersedes them. Only unsupported global intents
        # can be terminally ignored here.
        if atom_id in (None, "") and reason != "unsupported_kind":
            continue

        item["status"] = "ignored"
        item["ignored_at"] = ignored_at
        item["reason"] = reason
        item["step"] = step
        changed = True
        ignored_events.append({
            "client_intent_id": item.get("client_intent_id"),
            "intent_event_id": item.get("intent_event_id"),
            "kind": item.get("kind"),
            "atom_id": atom_id,
            "reason": reason,
            "step": step,
            "source_refs": [
                f"event:{item.get('intent_event_id')}",
                "artifact:.orchestrator/control/intents.jsonl",
            ],
        })

    if changed:
        write_intents(project_dir, rows)
    return ignored_events


def _instruction_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("instruction", "message", "text", "note"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if payload:
        return json.dumps(payload, sort_keys=True)
    return ""
