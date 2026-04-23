"""Tests for the deterministic founding-team consult renderer (A-8.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.lib.consult import (
    ConsultTrigger,
    Persona,
    TRIGGER_TAGS,
    consult,
    personas_from_dicts,
    render_consult_deterministic,
)
from orchestrator.lib.discussion import discussion_log_path
from orchestrator.lib.events import EventBus


def _sample_personas() -> list[Persona]:
    return personas_from_dicts([
        {"name": "Founder", "perspective": "business owner", "mandate": "Guard scope.", "veto_scope": "scope drift", "turn_order": 1},
        {"name": "Player Advocate", "perspective": "client", "mandate": "Protect delight.", "veto_scope": "ux regression", "turn_order": 2},
    ])


def test_deterministic_produces_one_statement_per_persona() -> None:
    trigger = ConsultTrigger(tag="architect_plan_done", summary="plan.md landed")
    result = render_consult_deterministic(trigger, _sample_personas())
    assert len(result.statements) == 2
    assert result.mode == "deterministic"
    assert result.convergence
    assert all(s.speaker_kind == "persona" for s in result.statements)


def test_consult_writes_discussion_entries(tmp_path: Path) -> None:
    trigger = ConsultTrigger(tag="reviewer_done", summary="reviewer posted review")
    bus = EventBus()
    result = consult(
        trigger,
        _sample_personas(),
        project_dir=tmp_path,
        event_bus=bus,
        project_id="project-x",
    )
    assert len(result.discussion_entries) == 3  # 2 statements + convergence
    log = discussion_log_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(log) == 3
    first = json.loads(log[0])
    assert first["entry_type"] == "consult_persona_statement"
    assert first["atom_id"] == "consult_reviewer_done"
    assert first["metadata"]["trigger_tag"] == "reviewer_done"
    assert first["metadata"]["consult_mode"] == "deterministic"


def test_consult_rejects_unknown_trigger(tmp_path: Path) -> None:
    trigger = ConsultTrigger(tag="not_a_trigger", summary="")
    with pytest.raises(ValueError):
        consult(trigger, _sample_personas(), project_dir=tmp_path)


def test_consult_orders_statements_by_turn_order(tmp_path: Path) -> None:
    trigger = ConsultTrigger(tag="coder_done", summary="coder done")
    result = consult(trigger, _sample_personas(), project_dir=tmp_path)
    assert result.statements[0].speaker == "Founder"
    assert result.statements[1].speaker == "Player Advocate"


def test_consult_handles_heroes_with_speaker_kind(tmp_path: Path) -> None:
    class FakeHero:
        hero_id = "hero_security_reviewer_deadbeef"
        name = "Security Reviewer"
        mission = "Find abuse paths"
        watch_for = "auth gaps"

    trigger = ConsultTrigger(tag="gate_rejected", summary="gate rejected")
    result = consult(
        trigger,
        _sample_personas(),
        project_dir=tmp_path,
        heroes=[FakeHero()],
    )
    hero_stmts = [s for s in result.statements if s.speaker_kind == "hero"]
    assert len(hero_stmts) == 1
    assert hero_stmts[0].persona_id == "hero_security_reviewer_deadbeef"


def test_trigger_tags_cover_all_seven_sites() -> None:
    expected = {
        "architect_plan_done",
        "architect_refine_done",
        "micro_task_breakdown_done",
        "coder_done",
        "tester_done",
        "reviewer_done",
        "gate_rejected",
    }
    assert expected == set(TRIGGER_TAGS.keys())
