"""Tests for runtime budget evaluation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from orchestrator.lib.budget import (
    BudgetConfig,
    BudgetHalted,
    apply_budget_to_usage,
    emit_budget_events,
)


class _CollectingBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event_type: str, **fields: object) -> None:
        self.events.append((event_type, dict(fields)))


class _GateRegistry:
    def __init__(self, decision: str = "approved") -> None:
        self.decision = decision
        self.opened: list[tuple[str, str]] = []
        self.waited: list[str] = []

    def open_gate(self, gate_id: str, artifact: str = "") -> None:
        self.opened.append((gate_id, artifact))

    def wait(self, gate_id: str, timeout_sec: int = 0) -> str:
        self.waited.append(gate_id)
        return self.decision


def _payload(cost: float, *, step: str = "implementation") -> dict:
    return {
        "step": step,
        "cost_usd": cost,
        "cost": {"effective_cost": cost},
    }


def test_default_budget_is_advisory_and_does_not_emit_events() -> None:
    state = SimpleNamespace()
    payload = _payload(1.25)

    evaluation = apply_budget_to_usage(state, payload)

    assert payload["budget"]["budget_configured"] is True
    assert payload["budget"]["run_budget_usd"] == 100.0
    assert payload["budget"]["phase_budget_usd"] == 25.0
    assert payload["budget"]["remaining_run_budget_usd"] == 98.75
    assert payload["budget"]["remaining_phase_budget_usd"] == 23.75
    assert evaluation.events == []


def test_advisory_threshold_warns_once_without_gate() -> None:
    state = SimpleNamespace(
        budget_config=BudgetConfig(advisory_run_budget_usd=2.0, advisory_phase_budget_usd=None)
    )
    bus = _CollectingBus()

    first = apply_budget_to_usage(state, _payload(1.5))
    emit_budget_events(state, bus, first)
    second = apply_budget_to_usage(state, _payload(0.75))
    emit_budget_events(state, bus, second)
    third = apply_budget_to_usage(state, _payload(0.25))
    emit_budget_events(state, bus, third)

    assert [event_type for event_type, _ in bus.events] == ["budget_warning"]
    assert bus.events[0][1]["level"] == "run"
    assert bus.events[0][1]["gate_id"] == "budget_run"


def test_hard_cap_without_halt_emits_exceeded_but_no_gate() -> None:
    state = SimpleNamespace(
        budget_config=BudgetConfig(
            advisory_run_budget_usd=None,
            advisory_phase_budget_usd=None,
            hard_run_budget_usd=2.0,
            halt_on_hard_cap=False,
        )
    )
    bus = _CollectingBus()

    evaluation = apply_budget_to_usage(state, _payload(2.1))
    emit_budget_events(state, bus, evaluation)

    assert [event_type for event_type, _ in bus.events] == ["budget_exceeded"]
    assert bus.events[0][1]["remaining_usd"] == pytest.approx(-0.1)


def test_hard_cap_with_halt_opens_and_waits_for_gate() -> None:
    registry = _GateRegistry(decision="approved")
    state = SimpleNamespace(
        budget_config=BudgetConfig(
            advisory_run_budget_usd=None,
            advisory_phase_budget_usd=None,
            hard_run_budget_usd=2.0,
            halt_on_hard_cap=True,
        ),
        gate_registry=registry,
    )
    bus = _CollectingBus()

    evaluation = apply_budget_to_usage(state, _payload(2.1))
    emit_budget_events(state, bus, evaluation)

    assert [event_type for event_type, _ in bus.events] == ["budget_exceeded", "budget_gate_opened"]
    assert registry.opened[0][0] == "budget_run"
    assert registry.waited == ["budget_run"]


def test_rejected_hard_cap_gate_raises_budget_halted() -> None:
    registry = _GateRegistry(decision="rejected")
    state = SimpleNamespace(
        budget_config=BudgetConfig(
            advisory_run_budget_usd=None,
            advisory_phase_budget_usd=None,
            hard_run_budget_usd=2.0,
            halt_on_hard_cap=True,
        ),
        gate_registry=registry,
    )
    bus = _CollectingBus()

    evaluation = apply_budget_to_usage(state, _payload(2.1))
    with pytest.raises(BudgetHalted):
        emit_budget_events(state, bus, evaluation)
