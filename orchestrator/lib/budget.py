"""Budget policy primitives.

Budgets are advisory by default. A run should only be halted when an operator
explicitly configures hard caps and enables halting for those caps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BudgetConfig:
    """Cost budget posture for a run.

    The defaults are intentionally permissive: high advisory budgets give the
    PWA useful context, while unset hard caps prevent surprise execution halts.
    """

    advisory_run_budget_usd: float | None = 100.0
    advisory_phase_budget_usd: float | None = 25.0
    hard_run_budget_usd: float | None = None
    hard_phase_budget_usd: float | None = None
    per_call_hard_cap_usd: float | None = None
    halt_on_hard_cap: bool = False

    @property
    def can_halt_execution(self) -> bool:
        """True only when hard caps and explicit halting are both configured."""
        return self.halt_on_hard_cap and any(
            value is not None
            for value in (
                self.hard_run_budget_usd,
                self.hard_phase_budget_usd,
                self.per_call_hard_cap_usd,
            )
        )

    @property
    def has_advisory_budget(self) -> bool:
        return (
            self.advisory_run_budget_usd is not None
            or self.advisory_phase_budget_usd is not None
        )

    @property
    def has_budget(self) -> bool:
        return self.has_advisory_budget or any(
            value is not None
            for value in (
                self.hard_run_budget_usd,
                self.hard_phase_budget_usd,
                self.per_call_hard_cap_usd,
            )
        )


@dataclass
class BudgetRuntime:
    run_spend_usd: float = 0.0
    phase_spend_usd: dict[str, float] = field(default_factory=dict)
    warned: set[str] = field(default_factory=set)
    exceeded: set[str] = field(default_factory=set)
    opened_gates: set[str] = field(default_factory=set)


@dataclass
class BudgetEvaluation:
    budget: dict[str, Any]
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


class BudgetHalted(RuntimeError):
    """Raised when an explicitly configured hard budget gate is rejected."""

    def __init__(self, gate_id: str) -> None:
        self.gate_id = gate_id
        super().__init__(f"Budget gate '{gate_id}' rejected")


def apply_budget_to_usage(state: Any, payload: dict[str, Any]) -> BudgetEvaluation:
    """Update runtime budget state, attach explicit budget fields, and return events."""
    config = budget_config_for_state(state)
    runtime = budget_runtime_for_state(state)
    cost = _effective_cost(payload)
    step = _step(payload)

    runtime.run_spend_usd += cost
    runtime.phase_spend_usd[step] = runtime.phase_spend_usd.get(step, 0.0) + cost

    run_budget = config.hard_run_budget_usd if config.hard_run_budget_usd is not None else config.advisory_run_budget_usd
    phase_budget = config.hard_phase_budget_usd if config.hard_phase_budget_usd is not None else config.advisory_phase_budget_usd
    remaining_run = _remaining(run_budget, runtime.run_spend_usd)
    remaining_phase = _remaining(phase_budget, runtime.phase_spend_usd[step])

    budget = {
        "budget_configured": config.has_budget,
        "run_budget_usd": run_budget,
        "phase_budget_usd": phase_budget,
        "remaining_run_budget_usd": remaining_run,
        "remaining_phase_budget_usd": remaining_phase,
        "advisory_run_budget_usd": config.advisory_run_budget_usd,
        "advisory_phase_budget_usd": config.advisory_phase_budget_usd,
        "hard_run_budget_usd": config.hard_run_budget_usd,
        "hard_phase_budget_usd": config.hard_phase_budget_usd,
        "per_call_hard_cap_usd": config.per_call_hard_cap_usd,
        "halt_on_hard_cap": config.halt_on_hard_cap,
    }
    payload["budget"] = budget

    events: list[tuple[str, dict[str, Any]]] = []
    _append_threshold_events(
        events,
        runtime,
        level="run",
        spend=runtime.run_spend_usd,
        advisory_budget=config.advisory_run_budget_usd,
        hard_budget=config.hard_run_budget_usd,
        remaining=remaining_run,
        gate_id="budget_run",
        config=config,
    )
    _append_threshold_events(
        events,
        runtime,
        level="phase",
        spend=runtime.phase_spend_usd[step],
        advisory_budget=config.advisory_phase_budget_usd,
        hard_budget=config.hard_phase_budget_usd,
        remaining=remaining_phase,
        gate_id=f"budget_phase_{_safe_gate_part(step)}",
        config=config,
    )
    if (
        config.per_call_hard_cap_usd is not None
        and cost >= config.per_call_hard_cap_usd
        and "per_call" not in runtime.exceeded
    ):
        runtime.exceeded.add("per_call")
        fields = _budget_event_fields(
            level="per_call",
            remaining=0.0,
            gate_id="budget_per_call",
            budget_usd=config.per_call_hard_cap_usd,
        )
        events.append(("budget_exceeded", fields))
        if config.can_halt_execution and "budget_per_call" not in runtime.opened_gates:
            runtime.opened_gates.add("budget_per_call")
            events.append(("budget_gate_opened", fields))

    return BudgetEvaluation(budget=budget, events=events)


def emit_budget_events(state: Any, event_bus: Any, evaluation: BudgetEvaluation) -> None:
    """Emit budget warning/exceeded/gate events and block only on explicit hard gates."""
    for event_type, fields in evaluation.events:
        event_bus.emit(event_type, **fields)
        if event_type != "budget_gate_opened":
            continue
        config = budget_config_for_state(state)
        if not config.can_halt_execution:
            continue
        registry = getattr(state, "gate_registry", None)
        gate_id = str(fields.get("gate_id") or "budget")
        if registry is None:
            continue
        if hasattr(registry, "open_gate"):
            try:
                registry.open_gate(gate_id, f"Budget gate opened at {fields.get('level', 'run')} level.")
            except ValueError:
                pass
        if hasattr(registry, "wait"):
            decision = registry.wait(gate_id, timeout_sec=0)
            if decision == "rejected":
                raise BudgetHalted(gate_id)


def budget_config_for_state(state: Any) -> BudgetConfig:
    config = getattr(state, "budget_config", None)
    if isinstance(config, BudgetConfig):
        return config
    owner_config = getattr(state, "config", None)
    config = getattr(owner_config, "budget", None)
    if isinstance(config, BudgetConfig):
        return config
    return BudgetConfig()


def budget_runtime_for_state(state: Any) -> BudgetRuntime:
    runtime = getattr(state, "_budget_runtime", None)
    if isinstance(runtime, BudgetRuntime):
        return runtime
    runtime = BudgetRuntime()
    setattr(state, "_budget_runtime", runtime)
    return runtime


def _append_threshold_events(
    events: list[tuple[str, dict[str, Any]]],
    runtime: BudgetRuntime,
    *,
    level: str,
    spend: float,
    advisory_budget: float | None,
    hard_budget: float | None,
    remaining: float | None,
    gate_id: str,
    config: BudgetConfig,
) -> None:
    if advisory_budget is not None and spend >= advisory_budget and level not in runtime.warned:
        runtime.warned.add(level)
        events.append((
            "budget_warning",
            _budget_event_fields(level=level, remaining=remaining, gate_id=gate_id, budget_usd=advisory_budget),
        ))
    if hard_budget is None or spend < hard_budget or level in runtime.exceeded:
        return
    runtime.exceeded.add(level)
    fields = _budget_event_fields(level=level, remaining=remaining, gate_id=gate_id, budget_usd=hard_budget)
    events.append(("budget_exceeded", fields))
    if config.can_halt_execution and gate_id not in runtime.opened_gates:
        runtime.opened_gates.add(gate_id)
        events.append(("budget_gate_opened", fields))


def _budget_event_fields(
    *,
    level: str,
    remaining: float | None,
    gate_id: str,
    budget_usd: float | None,
) -> dict[str, Any]:
    return {
        "level": level,
        "gate_id": gate_id,
        "budget_usd": budget_usd,
        "remaining_usd": remaining,
    }


def _effective_cost(payload: dict[str, Any]) -> float:
    cost = payload.get("cost")
    if isinstance(cost, dict) and isinstance(cost.get("effective_cost"), (int, float)):
        return max(0.0, float(cost["effective_cost"]))
    value = payload.get("cost_usd")
    return max(0.0, float(value)) if isinstance(value, (int, float)) else 0.0


def _step(payload: dict[str, Any]) -> str:
    value = payload.get("step") or payload.get("atom_id") or "run"
    return str(value)


def _remaining(budget: float | None, spend: float) -> float | None:
    return None if budget is None else round(budget - spend, 6)


def _safe_gate_part(value: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in value.strip().lower())
    return safe.strip("_") or "run"
