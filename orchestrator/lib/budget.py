"""Budget policy primitives.

Budgets are advisory by default. A run should only be halted when an operator
explicitly configures hard caps and enables halting for those caps.
"""

from __future__ import annotations

from dataclasses import dataclass


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
