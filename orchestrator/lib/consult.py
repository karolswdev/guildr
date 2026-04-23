"""Founding-team consult: deterministic and model-backed persona statements.

A consult is a bounded ceremony. Given a trigger (e.g. ``architect_plan_done``)
and a persona roster, it produces one statement per persona plus a single
convergence line and writes them to the discussion log. Callers (engine phase
handlers) don't know or care which mode produced the text — the output
contract is identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from orchestrator.lib.discussion import append_discussion_entry

TRIGGER_TAGS: dict[str, str] = {
    "architect_plan_done": "Architect landed plan.md",
    "architect_refine_done": "Architect refined plan",
    "micro_task_breakdown_done": "Sprint plan decomposed into micro tasks",
    "coder_done": "Coder produced implementation",
    "tester_done": "Tester produced test suite",
    "reviewer_done": "Reviewer posted review",
    "gate_rejected": "Quality gate rejected the phase",
}


@dataclass(frozen=True)
class ConsultTrigger:
    tag: str
    summary: str
    context: str | None = None


@dataclass
class Persona:
    name: str
    perspective: str
    mandate: str
    veto_scope: str = "advisory"
    turn_order: int = 0

    @classmethod
    def from_dict(cls, raw: dict[str, Any], default_turn_order: int = 0) -> "Persona":
        return cls(
            name=str(raw.get("name", "")).strip(),
            perspective=str(raw.get("perspective", "")).strip() or "stakeholder",
            mandate=str(raw.get("mandate", "")).strip()
            or "Provide concise feedback.",
            veto_scope=str(raw.get("veto_scope", "")).strip() or "advisory",
            turn_order=int(raw.get("turn_order", default_turn_order) or default_turn_order),
        )


@dataclass
class ConsultStatement:
    persona_id: str
    speaker: str
    speaker_kind: str
    text: str


@dataclass
class ConsultResult:
    trigger: ConsultTrigger
    statements: list[ConsultStatement]
    convergence: str
    mode: str
    fallback_used: bool = False
    fallback_reason: str | None = None
    discussion_entries: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def empty(cls, trigger: ConsultTrigger) -> "ConsultResult":
        return cls(trigger=trigger, statements=[], convergence="", mode="disabled")


RenderFn = Callable[[ConsultTrigger, list[Persona], list[Any]], "ConsultResult"]


def render_consult_deterministic(
    trigger: ConsultTrigger,
    personas: Sequence[Persona],
    heroes: Sequence[Any] | None = None,
) -> ConsultResult:
    """Produce statements from fixed templates — no model call."""
    statements: list[ConsultStatement] = []
    for persona in sorted(personas, key=lambda p: p.turn_order):
        text = _render_persona_statement(trigger, persona)
        statements.append(
            ConsultStatement(
                persona_id=_persona_id(persona.name),
                speaker=persona.name,
                speaker_kind="persona",
                text=text,
            )
        )
    for hero in heroes or []:
        statements.append(
            ConsultStatement(
                persona_id=getattr(hero, "hero_id", f"hero_{_slug(getattr(hero, 'name', 'hero'))}"),
                speaker=getattr(hero, "name", "Hero"),
                speaker_kind="hero",
                text=_render_hero_statement(trigger, hero),
            )
        )
    convergence = _render_convergence(trigger, personas)
    return ConsultResult(
        trigger=trigger,
        statements=statements,
        convergence=convergence,
        mode="deterministic",
    )


def consult(
    trigger: ConsultTrigger,
    personas: Sequence[Persona],
    *,
    project_dir: Path,
    heroes: Sequence[Any] | None = None,
    event_bus: Any | None = None,
    project_id: str | None = None,
    render: RenderFn = render_consult_deterministic,
    policy: Any | None = None,
) -> ConsultResult:
    """Run a consult and append its rows to the discussion log.

    ``render`` is the rendering strategy (deterministic or model-backed). The
    caller picks it (or a router picks it on their behalf). This function
    handles the universal bits: trigger validation, discussion-entry writes,
    event emission.
    """
    if trigger.tag not in TRIGGER_TAGS:
        raise ValueError(f"unknown consult trigger: {trigger.tag!r}")

    result = render(trigger, list(personas), list(heroes or []))
    result.discussion_entries = _write_entries(
        result,
        project_dir=project_dir,
        event_bus=event_bus,
        project_id=project_id,
        policy=policy,
    )
    return result


def _write_entries(
    result: ConsultResult,
    *,
    project_dir: Path,
    event_bus: Any | None,
    project_id: str | None,
    policy: Any | None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    base_source_refs = [
        "artifact:FOUNDING_TEAM.json",
        "artifact:PERSONA_FORUM.md",
    ]
    policy_meta = _policy_metadata(policy, result)
    for stmt in result.statements:
        metadata = {
            "trigger_tag": result.trigger.tag,
            "speaker_kind": stmt.speaker_kind,
            "persona_id": stmt.persona_id,
            "consult_mode": result.mode,
        }
        if result.fallback_used:
            metadata["fallback_used"] = True
            if result.fallback_reason:
                metadata["fallback_reason"] = result.fallback_reason
        metadata.update(policy_meta)
        entry = append_discussion_entry(
            project_dir,
            speaker=stmt.speaker,
            text=stmt.text,
            entry_type=f"consult_{stmt.speaker_kind}_statement",
            atom_id=f"consult_{result.trigger.tag}",
            source_refs=base_source_refs,
            metadata=metadata,
            event_bus=event_bus,
            project_id=project_id,
        )
        entries.append(entry)
    if result.convergence:
        metadata = {
            "trigger_tag": result.trigger.tag,
            "consult_mode": result.mode,
        }
        metadata.update(policy_meta)
        conv_entry = append_discussion_entry(
            project_dir,
            speaker="Founding Team",
            text=result.convergence,
            entry_type="consult_convergence",
            atom_id=f"consult_{result.trigger.tag}",
            source_refs=base_source_refs,
            metadata=metadata,
            event_bus=event_bus,
            project_id=project_id,
        )
        entries.append(conv_entry)
    return entries


def _policy_metadata(policy: Any, result: ConsultResult) -> dict[str, Any]:
    if policy is None:
        return {}
    provider = getattr(policy, "provider", None)
    model = getattr(policy, "model", None)
    mode = getattr(policy, "mode", None)
    meta: dict[str, Any] = {}
    if provider:
        meta["consult_provider"] = provider
    if model:
        meta["consult_model"] = model
    if mode:
        meta["consult_policy_mode"] = mode
    return meta


def _render_persona_statement(trigger: ConsultTrigger, persona: Persona) -> str:
    tag_line = TRIGGER_TAGS.get(trigger.tag, trigger.tag)
    return (
        f"[{tag_line}] From the {persona.perspective} seat, {persona.name} keeps the table "
        f"on {persona.mandate.lower().rstrip('.')} "
        f"(veto scope: {persona.veto_scope})."
    )[:1200]


def _render_hero_statement(trigger: ConsultTrigger, hero: Any) -> str:
    mission = getattr(hero, "mission", "advise the team")
    watch_for = getattr(hero, "watch_for", "risks and blind spots")
    name = getattr(hero, "name", "Hero")
    tag_line = TRIGGER_TAGS.get(trigger.tag, trigger.tag)
    return (
        f"[{tag_line}] Guest {name} is watching for {watch_for}. "
        f"Mission: {mission}."
    )[:1200]


def _render_convergence(trigger: ConsultTrigger, personas: Sequence[Persona]) -> str:
    if not personas:
        return ""
    names = ", ".join(p.name for p in sorted(personas, key=lambda p: p.turn_order))
    tag_line = TRIGGER_TAGS.get(trigger.tag, trigger.tag)
    return (
        f"[{tag_line}] Convergence: {names} agree the team keeps evidence legible, "
        f"scope bounded, and the next step implementable."
    )[:1200]


def _persona_id(name: str) -> str:
    return f"persona_{_slug(name)}"


def _slug(value: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in value).strip("_") or "unnamed"


def personas_from_dicts(raw: Iterable[dict[str, Any]]) -> list[Persona]:
    out: list[Persona] = []
    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        out.append(Persona.from_dict(item, default_turn_order=idx))
    return out
