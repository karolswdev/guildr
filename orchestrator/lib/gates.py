"""Human gate registry.

Full implementation in Task 4.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Literal


class GateTimeout(Exception):
    """Raised when a gate times out waiting for a decision."""

    def __init__(self, gate_name: str) -> None:
        self.gate_name = gate_name
        super().__init__(f"Gate '{gate_name}' timed out")


@dataclass
class Gate:
    """Represents a human approval gate."""

    name: str
    artifact_path: str
    decision: Literal["pending", "approved", "rejected"] = "pending"
    timeout_sec: int = 0
    decided_at: float | None = None
    reason: str = ""


class GateRegistry:
    """Manages human approval gates."""

    def __init__(self) -> None:
        self._gates: dict[str, Gate] = {}
        self._lock = threading.Lock()
        self._conditions: dict[str, threading.Condition] = {}

    def open(self, gate: Gate) -> None:
        """Open a new gate."""
        with self._lock:
            self._gates[gate.name] = gate
            self._conditions[gate.name] = threading.Condition(self._lock)

    def decide(self, name: str, decision: str) -> None:
        """Record a decision for a gate."""
        with self._lock:
            gate = self._gates.get(name)
            if gate is None:
                return
            gate.decision = decision
            gate.decided_at = time.time()
            if name in self._conditions:
                self._conditions[name].notify_all()

    def wait(self, name: str, timeout_sec: int = 0) -> str:
        """Block until the gate is decided.

        Returns the decision string.
        Raises GateTimeout if timeout_sec > 0 and timeout expires.
        """
        with self._lock:
            gate = self._gates.get(name)
            if gate is None:
                return "approved"

            cond = self._conditions.get(name)
            if cond is None:
                return "approved"

            deadline = None
            if timeout_sec > 0:
                deadline = time.time() + timeout_sec

            while gate.decision == "pending":
                if deadline is not None:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        raise GateTimeout(name)
                    cond.wait(timeout=remaining)
                else:
                    cond.wait(timeout=1.0)

            return gate.decision

    def get_rejection_reason(self, name: str) -> str:
        """Get the reason for a gate rejection."""
        gate = self._gates.get(name)
        if gate is None:
            return ""
        return gate.reason
