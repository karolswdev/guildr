"""Hero reviewer lifecycle (A-8.4).

Heroes are operator-invited advisory voices with a bounded term. Unlike
founding personas, they are not permanent roster members — they attend one
or more consults then retire. Term modes:

- ``single_consultation``: retire after 1 consult attended
- ``until_step_complete``: retire when the target step completes
- ``until_deliverable``: retire when the target deliverable ships
- ``manual_dismissal``: only operator intent can retire
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

HEROES_DIR = ".orchestrator"
HEROES_FILE = "heroes.jsonl"

HERO_TERM_MODES = {
    "single_consultation",
    "until_step_complete",
    "until_deliverable",
    "manual_dismissal",
}

HERO_LIFECYCLE_KINDS = {"invite_hero", "dismiss_hero"}


@dataclass
class HeroInvitation:
    hero_id: str
    name: str
    provider: str
    model: str
    mission: str
    watch_for: str
    term_mode: str
    target_step: str | None = None
    target_deliverable: str | None = None
    consultation_trigger: str | None = None
    invited_at: str | None = None
    status: str = "active"
    consultations_attended: int = 0
    retired_at: str | None = None
    retired_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


def heroes_path(project_dir: Path) -> Path:
    p = project_dir / HEROES_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p / HEROES_FILE


def read_heroes(project_dir: Path) -> list[HeroInvitation]:
    """Fold the heroes log by hero_id; return the latest row per hero."""
    path = heroes_path(project_dir)
    if not path.exists():
        return []
    latest: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        hero_id = row.get("hero_id")
        if not isinstance(hero_id, str):
            continue
        latest[hero_id] = row
    out: list[HeroInvitation] = []
    for row in latest.values():
        try:
            out.append(_row_to_invitation(row))
        except (TypeError, ValueError):
            continue
    return out


def active_heroes_for_trigger(
    project_dir: Path, trigger_tag: str
) -> list[HeroInvitation]:
    """Heroes that should attend this trigger (active, matching target)."""
    out: list[HeroInvitation] = []
    for hero in read_heroes(project_dir):
        if hero.status != "active":
            continue
        if hero.consultation_trigger and hero.consultation_trigger != trigger_tag:
            continue
        out.append(hero)
    return out


def invite_hero_from_intent(
    project_dir: Path, intent: dict[str, Any], *, now_iso: str
) -> HeroInvitation | None:
    """Materialize a hero invitation from an ``invite_hero`` intent payload."""
    payload = intent.get("payload") or {}
    if not isinstance(payload, dict):
        return None
    hero_payload = payload.get("hero") or {}
    if not isinstance(hero_payload, dict):
        return None
    name = str(hero_payload.get("name", "")).strip()
    if not name:
        return None
    target = payload.get("target") or {}
    if not isinstance(target, dict):
        target = {}
    term = hero_payload.get("term") or {}
    if not isinstance(term, dict):
        term = {}
    term_mode = str(term.get("mode", "single_consultation")).strip()
    if term_mode not in HERO_TERM_MODES:
        term_mode = "single_consultation"
    client_intent_id = intent.get("client_intent_id") or intent.get("intent_event_id") or ""
    hero = HeroInvitation(
        hero_id=f"hero_{_slug(name)}_{_short(client_intent_id)}",
        name=name,
        provider=str(hero_payload.get("provider", "primary")).strip() or "primary",
        model=str(hero_payload.get("model", "")).strip(),
        mission=str(hero_payload.get("mission", "")).strip() or "Advise the team.",
        watch_for=str(hero_payload.get("watch_for", "")).strip() or "risks and blind spots",
        term_mode=term_mode,
        target_step=_opt_str(target.get("step")),
        target_deliverable=_opt_str(target.get("deliverable")),
        consultation_trigger=_opt_str(target.get("consultation_trigger")),
        invited_at=now_iso,
    )
    _append_hero_row(project_dir, hero)
    return hero


def dismiss_hero_from_intent(
    project_dir: Path, intent: dict[str, Any], *, now_iso: str
) -> HeroInvitation | None:
    payload = intent.get("payload") or {}
    if not isinstance(payload, dict):
        return None
    hero_id = payload.get("hero_id")
    if not isinstance(hero_id, str) or not hero_id:
        return None
    return _retire_hero(
        project_dir,
        hero_id=hero_id,
        now_iso=now_iso,
        reason=str(payload.get("reason", "manual_dismissal")),
    )


def increment_consultations_attended(
    project_dir: Path, hero_ids: Iterable[str], *, now_iso: str
) -> None:
    """Called after a consult: bump attendance and retire single_consultation."""
    heroes = {h.hero_id: h for h in read_heroes(project_dir)}
    for hero_id in hero_ids:
        hero = heroes.get(hero_id)
        if hero is None or hero.status != "active":
            continue
        hero.consultations_attended += 1
        if hero.term_mode == "single_consultation":
            hero.status = "retired"
            hero.retired_at = now_iso
            hero.retired_reason = "single_consultation_complete"
        _append_hero_row(project_dir, hero)


def retire_heroes_for_step(
    project_dir: Path, step: str, *, now_iso: str
) -> list[HeroInvitation]:
    retired: list[HeroInvitation] = []
    for hero in read_heroes(project_dir):
        if hero.status != "active":
            continue
        if hero.term_mode == "until_step_complete" and hero.target_step == step:
            updated = _retire_hero(
                project_dir,
                hero_id=hero.hero_id,
                now_iso=now_iso,
                reason=f"step_complete:{step}",
            )
            if updated:
                retired.append(updated)
    return retired


def retire_heroes_for_deliverable(
    project_dir: Path, deliverable: str, *, now_iso: str
) -> list[HeroInvitation]:
    retired: list[HeroInvitation] = []
    for hero in read_heroes(project_dir):
        if hero.status != "active":
            continue
        if hero.term_mode == "until_deliverable" and hero.target_deliverable == deliverable:
            updated = _retire_hero(
                project_dir,
                hero_id=hero.hero_id,
                now_iso=now_iso,
                reason=f"deliverable_shipped:{deliverable}",
            )
            if updated:
                retired.append(updated)
    return retired


def _retire_hero(
    project_dir: Path, *, hero_id: str, now_iso: str, reason: str
) -> HeroInvitation | None:
    heroes = {h.hero_id: h for h in read_heroes(project_dir)}
    hero = heroes.get(hero_id)
    if hero is None or hero.status != "active":
        return None
    hero.status = "retired"
    hero.retired_at = now_iso
    hero.retired_reason = reason
    _append_hero_row(project_dir, hero)
    return hero


def _append_hero_row(project_dir: Path, hero: HeroInvitation) -> None:
    path = heroes_path(project_dir)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(hero.as_row(), ensure_ascii=False) + "\n")


def _row_to_invitation(row: dict[str, Any]) -> HeroInvitation:
    return HeroInvitation(
        hero_id=str(row["hero_id"]),
        name=str(row.get("name", "")),
        provider=str(row.get("provider", "primary")),
        model=str(row.get("model", "")),
        mission=str(row.get("mission", "")),
        watch_for=str(row.get("watch_for", "")),
        term_mode=str(row.get("term_mode", "single_consultation")),
        target_step=row.get("target_step"),
        target_deliverable=row.get("target_deliverable"),
        consultation_trigger=row.get("consultation_trigger"),
        invited_at=row.get("invited_at"),
        status=str(row.get("status", "active")),
        consultations_attended=int(row.get("consultations_attended", 0) or 0),
        retired_at=row.get("retired_at"),
        retired_reason=row.get("retired_reason"),
        notes=list(row.get("notes") or []),
    )


def _slug(value: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in value).strip("_") or "hero"


def _short(value: str) -> str:
    return value[-8:] if value else "xxxxxxxx"


def _opt_str(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    return text or None
