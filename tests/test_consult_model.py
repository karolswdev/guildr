"""Tests for the model-backed consult renderer (A-8.5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.lib.consult import (
    ConsultTrigger,
    Persona,
    personas_from_dicts,
)
from orchestrator.lib.consult_model import (
    ConsultParseError,
    ModelPolicy,
    render_consult_model,
)


def _personas() -> list[Persona]:
    return personas_from_dicts([
        {"name": "Founder", "perspective": "business owner", "mandate": "Guard scope.", "turn_order": 1},
        {"name": "Player Advocate", "perspective": "client", "mandate": "Protect delight.", "turn_order": 2},
    ])


def _valid_response() -> str:
    return json.dumps({
        "statements": [
            {"persona_id": "persona_founder", "text": "Keep the plan tight."},
            {"persona_id": "persona_player_advocate", "text": "Prove delight early."},
        ],
        "convergence": "Team agrees: tight scope, early proof.",
    })


def test_model_mode_calls_runner_once_and_produces_result() -> None:
    calls: list[tuple[str, str]] = []

    def fake_call(system: str, user: str) -> str:
        calls.append((system, user))
        return _valid_response()

    trigger = ConsultTrigger(tag="architect_plan_done", summary="plan landed")
    result = render_consult_model(
        trigger, _personas(), [], model_call=fake_call, policy=ModelPolicy()
    )
    assert len(calls) == 1
    assert result.mode == "model"
    assert len(result.statements) == 2
    assert result.convergence.startswith("Team agrees")
    assert result.fallback_used is False


def test_schema_violation_triggers_fallback() -> None:
    def fake_call(system: str, user: str) -> str:
        return "not even json"

    trigger = ConsultTrigger(tag="reviewer_done", summary="review posted")
    result = render_consult_model(
        trigger, _personas(), [], model_call=fake_call, policy=ModelPolicy()
    )
    assert result.mode == "deterministic"
    assert result.fallback_used is True
    assert result.fallback_reason
    assert len(result.statements) == 2


def test_runner_exception_triggers_fallback() -> None:
    def fake_call(system: str, user: str) -> str:
        raise TimeoutError("endpoint unresponsive")

    trigger = ConsultTrigger(tag="coder_done", summary="coder done")
    result = render_consult_model(
        trigger, _personas(), [], model_call=fake_call, policy=ModelPolicy()
    )
    assert result.fallback_used is True
    assert "endpoint unresponsive" in (result.fallback_reason or "")


def test_fallback_on_error_false_raises() -> None:
    def fake_call(system: str, user: str) -> str:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        render_consult_model(
            ConsultTrigger(tag="tester_done", summary="x"),
            _personas(),
            [],
            model_call=fake_call,
            policy=ModelPolicy(fallback_on_error=False),
        )


def test_unknown_persona_id_rejected_as_schema_violation() -> None:
    def fake_call(system: str, user: str) -> str:
        return json.dumps({
            "statements": [
                {"persona_id": "persona_not_a_real_one", "text": "hi"},
            ],
            "convergence": "ok",
        })

    result = render_consult_model(
        ConsultTrigger(tag="coder_done", summary="x"),
        _personas(),
        [],
        model_call=fake_call,
        policy=ModelPolicy(),
    )
    assert result.fallback_used is True


def test_text_too_long_rejected_as_schema_violation() -> None:
    def fake_call(system: str, user: str) -> str:
        return json.dumps({
            "statements": [
                {"persona_id": "persona_founder", "text": "x" * 201},
                {"persona_id": "persona_player_advocate", "text": "ok"},
            ],
            "convergence": "ok",
        })

    result = render_consult_model(
        ConsultTrigger(tag="coder_done", summary="x"),
        _personas(),
        [],
        model_call=fake_call,
        policy=ModelPolicy(),
    )
    assert result.fallback_used is True


def test_heroes_tagged_hero_speaker_kind() -> None:
    class FakeHero:
        hero_id = "hero_security_xyz"
        name = "Security Reviewer"
        mission = "Find abuse paths"
        watch_for = "auth gaps"

    def fake_call(system: str, user: str) -> str:
        return json.dumps({
            "statements": [
                {"persona_id": "persona_founder", "text": "Keep scope tight."},
                {"persona_id": "persona_player_advocate", "text": "Delight matters."},
                {"persona_id": "hero_security_xyz", "text": "Check token handling."},
            ],
            "convergence": "Ship narrow, prove delight, audit tokens.",
        })

    result = render_consult_model(
        ConsultTrigger(tag="reviewer_done", summary="review"),
        _personas(),
        [FakeHero()],
        model_call=fake_call,
        policy=ModelPolicy(),
    )
    hero_stmts = [s for s in result.statements if s.speaker_kind == "hero"]
    assert len(hero_stmts) == 1
    assert hero_stmts[0].persona_id == "hero_security_xyz"


def test_code_fenced_response_is_stripped() -> None:
    def fake_call(system: str, user: str) -> str:
        return "```json\n" + _valid_response() + "\n```"

    result = render_consult_model(
        ConsultTrigger(tag="coder_done", summary="x"),
        _personas(),
        [],
        model_call=fake_call,
        policy=ModelPolicy(),
    )
    assert result.fallback_used is False
    assert result.mode == "model"


def test_prompt_includes_trigger_context_truncated() -> None:
    captured: dict[str, str] = {}

    def fake_call(system: str, user: str) -> str:
        captured["user"] = user
        return _valid_response()

    long_ctx = "c" * 5000
    trigger = ConsultTrigger(
        tag="architect_plan_done", summary="plan", context=long_ctx
    )
    render_consult_model(
        trigger, _personas(), [], model_call=fake_call, policy=ModelPolicy()
    )
    # Context is truncated to 800 chars.
    assert "c" * 800 in captured["user"]
    assert "c" * 801 not in captured["user"]
