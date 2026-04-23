"""Model-backed consult renderer (A-8.5).

One bounded call per consult, returning structured JSON for all persona
statements plus a single convergence line. Falls back to the deterministic
renderer on timeout, schema violation, or any unhandled error.

The caller supplies a ``ModelCall`` — any callable taking ``(system,
user)`` prompts and returning a raw string. This keeps the module
decoupled from opencode/session-runner specifics and makes testing
trivial (pass a fake callable).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from orchestrator.lib.consult import (
    ConsultResult,
    ConsultStatement,
    ConsultTrigger,
    Persona,
    TRIGGER_TAGS,
    render_consult_deterministic,
    _persona_id,
    _slug,
)

logger = logging.getLogger(__name__)


ModelCall = Callable[[str, str], str]
"""(system_prompt, user_prompt) -> raw response string."""


PROMPT_SYSTEM = (
    "You are simulating a founding-team consult. Produce ONE short statement per "
    "persona (<=180 chars each) plus a single convergence line (<=240 chars). "
    "Do not debate across personas. Return ONLY valid JSON matching the schema "
    "below. No prose, no code fences.\n"
    "{\n"
    '  "statements": [{"persona_id": str, "text": str}, ...],\n'
    '  "convergence": str\n'
    "}"
)


class ConsultParseError(ValueError):
    pass


@dataclass
class ModelPolicy:
    provider: str = "primary"
    model: str = "qwen2.5-coder-32b"
    max_tokens: int = 1200
    temperature: float = 0.4
    timeout_s: float = 45.0
    fallback_on_error: bool = True


def render_consult_model(
    trigger: ConsultTrigger,
    personas: Sequence[Persona],
    heroes: Sequence[Any] | None,
    *,
    model_call: ModelCall,
    policy: ModelPolicy,
) -> ConsultResult:
    heroes = list(heroes or [])
    prompt = _build_prompt(trigger, list(personas), heroes)
    started = time.monotonic()
    try:
        raw = model_call(PROMPT_SYSTEM, prompt)
    except Exception as exc:  # noqa: BLE001 — any runner error falls back
        if policy.fallback_on_error:
            logger.warning(
                "consult_model call failed (%s); falling back to deterministic",
                exc,
            )
            return _fallback(trigger, personas, heroes, reason=f"model_call_error:{exc}")
        raise
    try:
        parsed = _parse_and_validate(raw, personas, heroes)
    except ConsultParseError as exc:
        if policy.fallback_on_error:
            logger.warning(
                "consult_model response rejected (%s); falling back to deterministic",
                exc,
            )
            return _fallback(trigger, personas, heroes, reason=f"schema_violation:{exc}")
        raise
    latency_ms = int((time.monotonic() - started) * 1000)
    statements = [
        ConsultStatement(
            persona_id=entry["persona_id"],
            speaker=entry["speaker"],
            speaker_kind=entry["speaker_kind"],
            text=entry["text"],
        )
        for entry in parsed["statements"]
    ]
    result = ConsultResult(
        trigger=trigger,
        statements=statements,
        convergence=parsed["convergence"],
        mode="model",
    )
    # Stash latency for downstream telemetry; not part of the schema.
    result.discussion_entries = []
    setattr(result, "_latency_ms", latency_ms)
    return result


def _fallback(
    trigger: ConsultTrigger,
    personas: Sequence[Persona],
    heroes: Sequence[Any],
    *,
    reason: str,
) -> ConsultResult:
    result = render_consult_deterministic(trigger, personas, heroes)
    result.mode = "deterministic"
    result.fallback_used = True
    result.fallback_reason = reason
    return result


def _build_prompt(
    trigger: ConsultTrigger, personas: list[Persona], heroes: list[Any]
) -> str:
    tag_line = TRIGGER_TAGS.get(trigger.tag, trigger.tag)
    lines = [f"TRIGGER: {trigger.tag} — {tag_line}", f"SUMMARY: {trigger.summary}"]
    if trigger.context:
        lines.append(f"CONTEXT: {trigger.context[:800]}")
    lines.append("")
    lines.append("PERSONAS:")
    for p in sorted(personas, key=lambda x: x.turn_order):
        lines.append(
            f"- {_persona_id(p.name)} ({p.name} / {p.perspective}): "
            f"mandate={p.mandate[:120]}; veto={p.veto_scope}"
        )
    if heroes:
        lines.append("")
        lines.append("HEROES (advisory, term-bound):")
        for h in heroes:
            hero_id = getattr(h, "hero_id", f"hero_{_slug(getattr(h, 'name', 'hero'))}")
            lines.append(
                f"- {hero_id} ({getattr(h, 'name', 'Hero')}): "
                f"mission={getattr(h, 'mission', '')[:120]}; "
                f"watch_for={getattr(h, 'watch_for', '')[:120]}"
            )
    lines.append("")
    lines.append("Produce JSON only. <=180 chars per statement. <=240 chars convergence.")
    return "\n".join(lines)


def _parse_and_validate(
    raw: str,
    personas: Sequence[Persona],
    heroes: Sequence[Any],
) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        # Strip fences defensively even though prompt forbids them.
        text = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("```")
        )
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConsultParseError(f"not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConsultParseError("top-level JSON must be an object")
    statements_raw = data.get("statements")
    convergence = data.get("convergence", "")
    if not isinstance(statements_raw, list):
        raise ConsultParseError("'statements' must be a list")
    if not isinstance(convergence, str):
        raise ConsultParseError("'convergence' must be a string")

    persona_lookup = {_persona_id(p.name): p for p in personas}
    hero_lookup = {
        getattr(h, "hero_id", f"hero_{_slug(getattr(h, 'name', 'hero'))}"): h
        for h in heroes
    }

    out_statements: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for entry in statements_raw:
        if not isinstance(entry, dict):
            raise ConsultParseError("statement entries must be objects")
        persona_id = entry.get("persona_id")
        text_field = entry.get("text")
        if not isinstance(persona_id, str) or not persona_id:
            raise ConsultParseError("statement missing persona_id")
        if not isinstance(text_field, str) or not text_field.strip():
            raise ConsultParseError("statement missing text")
        if len(text_field) > 200:
            raise ConsultParseError(
                f"statement text too long ({len(text_field)} > 200)"
            )
        if persona_id in seen_ids:
            raise ConsultParseError(f"duplicate persona_id: {persona_id}")
        if persona_id in persona_lookup:
            speaker = persona_lookup[persona_id].name
            speaker_kind = "persona"
        elif persona_id in hero_lookup:
            speaker = getattr(hero_lookup[persona_id], "name", persona_id)
            speaker_kind = "hero"
        else:
            raise ConsultParseError(f"unknown persona_id: {persona_id}")
        seen_ids.add(persona_id)
        out_statements.append(
            {
                "persona_id": persona_id,
                "speaker": speaker,
                "speaker_kind": speaker_kind,
                "text": text_field.strip(),
            }
        )
    if len(convergence) > 260:
        raise ConsultParseError(f"convergence too long ({len(convergence)} > 260)")
    return {"statements": out_statements, "convergence": convergence.strip()}
