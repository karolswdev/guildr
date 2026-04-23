"""Tests for hero invitation lifecycle (A-8.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.lib.heroes import (
    HERO_TERM_MODES,
    active_heroes_for_trigger,
    heroes_path,
    increment_consultations_attended,
    invite_hero_from_intent,
    read_heroes,
    retire_heroes_for_deliverable,
    retire_heroes_for_step,
    dismiss_hero_from_intent,
)


def _invite_payload(
    *,
    name: str = "Security Reviewer",
    term_mode: str = "single_consultation",
    step: str | None = None,
    deliverable: str | None = None,
    trigger: str | None = None,
) -> dict:
    return {
        "client_intent_id": "intent_abc123",
        "intent_event_id": "evt_abc123",
        "kind": "invite_hero",
        "payload": {
            "hero": {
                "name": name,
                "provider": "primary",
                "model": "qwen2.5-coder-32b",
                "mission": "Find abuse paths",
                "watch_for": "auth gaps",
                "term": {"mode": term_mode},
            },
            "target": {
                "step": step,
                "deliverable": deliverable,
                "consultation_trigger": trigger,
            },
        },
    }


def test_invite_hero_persists_and_reads_back(tmp_path: Path) -> None:
    hero = invite_hero_from_intent(
        tmp_path, _invite_payload(), now_iso="2026-04-22T10:00:00Z"
    )
    assert hero is not None
    assert hero.status == "active"
    assert hero.term_mode == "single_consultation"
    heroes = read_heroes(tmp_path)
    assert len(heroes) == 1
    assert heroes[0].hero_id == hero.hero_id


def test_single_consultation_retires_after_one_attendance(tmp_path: Path) -> None:
    hero = invite_hero_from_intent(
        tmp_path, _invite_payload(), now_iso="2026-04-22T10:00:00Z"
    )
    assert hero is not None
    increment_consultations_attended(
        tmp_path, [hero.hero_id], now_iso="2026-04-22T10:05:00Z"
    )
    heroes = read_heroes(tmp_path)
    assert heroes[0].status == "retired"
    assert heroes[0].retired_reason == "single_consultation_complete"
    assert heroes[0].consultations_attended == 1


def test_until_step_complete_retires_on_matching_step(tmp_path: Path) -> None:
    hero = invite_hero_from_intent(
        tmp_path,
        _invite_payload(term_mode="until_step_complete", step="coder"),
        now_iso="2026-04-22T10:00:00Z",
    )
    assert hero is not None
    retired = retire_heroes_for_step(
        tmp_path, "tester", now_iso="2026-04-22T10:05:00Z"
    )
    assert retired == []  # wrong step
    retired = retire_heroes_for_step(
        tmp_path, "coder", now_iso="2026-04-22T10:06:00Z"
    )
    assert len(retired) == 1
    assert read_heroes(tmp_path)[0].status == "retired"


def test_until_deliverable_retires(tmp_path: Path) -> None:
    invite_hero_from_intent(
        tmp_path,
        _invite_payload(
            term_mode="until_deliverable", deliverable="sprint-plan.md"
        ),
        now_iso="2026-04-22T10:00:00Z",
    )
    retired = retire_heroes_for_deliverable(
        tmp_path, "sprint-plan.md", now_iso="2026-04-22T10:10:00Z"
    )
    assert len(retired) == 1


def test_manual_dismissal_requires_intent(tmp_path: Path) -> None:
    hero = invite_hero_from_intent(
        tmp_path,
        _invite_payload(term_mode="manual_dismissal"),
        now_iso="2026-04-22T10:00:00Z",
    )
    assert hero is not None
    # Step/deliverable triggers are no-ops.
    assert retire_heroes_for_step(tmp_path, "coder", now_iso="z") == []
    # Dismiss via intent.
    dismissed = dismiss_hero_from_intent(
        tmp_path,
        {"kind": "dismiss_hero", "payload": {"hero_id": hero.hero_id}},
        now_iso="2026-04-22T10:15:00Z",
    )
    assert dismissed is not None
    assert read_heroes(tmp_path)[0].status == "retired"


def test_active_heroes_for_trigger_filters_by_trigger_tag(tmp_path: Path) -> None:
    invite_hero_from_intent(
        tmp_path,
        _invite_payload(name="A", trigger="reviewer_done"),
        now_iso="2026-04-22T10:00:00Z",
    )
    invite_hero_from_intent(
        tmp_path,
        _invite_payload(name="B", trigger=None),
        now_iso="2026-04-22T10:00:01Z",
    )
    both = active_heroes_for_trigger(tmp_path, "reviewer_done")
    assert {h.name for h in both} == {"A", "B"}
    only_b = active_heroes_for_trigger(tmp_path, "coder_done")
    assert {h.name for h in only_b} == {"B"}


def test_invite_rejects_missing_name(tmp_path: Path) -> None:
    intent = _invite_payload(name="")
    assert invite_hero_from_intent(tmp_path, intent, now_iso="z") is None
    assert read_heroes(tmp_path) == []


def test_invalid_term_mode_falls_back_to_single_consultation(tmp_path: Path) -> None:
    intent = _invite_payload(term_mode="bogus_mode")
    hero = invite_hero_from_intent(tmp_path, intent, now_iso="z")
    assert hero is not None
    assert hero.term_mode == "single_consultation"


def test_term_modes_registry_is_exhaustive() -> None:
    assert HERO_TERM_MODES == {
        "single_consultation",
        "until_step_complete",
        "until_deliverable",
        "manual_dismissal",
    }
