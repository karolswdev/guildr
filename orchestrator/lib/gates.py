"""Human gate registry — single source of truth.

One class, two callers: the engine opens gates and waits on decisions; the
web backend lists/decides via HTTP. Previously each side owned a separate
in-memory registry so PWA decisions never reached a running engine. This
module is the canonical implementation both sides now share.

Multi-project web traffic is served by ``GateRegistryStore`` (this module),
which hands out a per-project ``GateRegistry`` instance — the engine
consumes that same instance directly, so a POSTed decision unblocks the
engine's ``wait()``.
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
    """Represents a human approval gate.

    ``artifact_path`` is the engine-facing filesystem path to the markdown
    artifact (``sprint-plan.md`` etc.). ``artifact`` holds inline content
    that the web layer passes in when opening a gate via HTTP. Both fields
    coexist because the two use cases are distinct.
    """

    name: str
    artifact_path: str = ""
    artifact: str = ""
    decision: Literal["pending", "approved", "rejected"] = "pending"
    timeout_sec: int = 0
    decided_at: float | None = None
    reason: str = ""

    @property
    def status(self) -> str:
        """HTTP-facing alias for ``decision`` — same values."""
        return self.decision


class GateRegistry:
    """Manages human approval gates for a single project.

    Thread-safe. ``wait()`` blocks until ``decide()`` is called, which is
    how the engine pauses until the PWA (or CLI) approves/rejects.
    """

    def __init__(self) -> None:
        self._gates: dict[str, Gate] = {}
        self._lock = threading.Lock()
        self._conditions: dict[str, threading.Condition] = {}

    def open(self, gate: Gate) -> None:
        """Open a gate (engine-style: caller supplies the Gate object)."""
        with self._lock:
            self._gates[gate.name] = gate
            self._conditions[gate.name] = threading.Condition(self._lock)

    def open_gate(self, gate_name: str, artifact: str = "") -> Gate:
        """Open a gate by name (web-style: inline artifact content).

        Raises ``ValueError`` if the gate exists and is already decided —
        the HTTP layer relies on this for idempotency semantics.
        """
        with self._lock:
            existing = self._gates.get(gate_name)
            if existing is not None and existing.decision != "pending":
                raise ValueError(f"Gate '{gate_name}' is already {existing.decision}")
            gate = existing or Gate(name=gate_name)
            gate.artifact = artifact
            self._gates[gate_name] = gate
            self._conditions.setdefault(gate_name, threading.Condition(self._lock))
            return gate

    def decide(self, name: str, decision: str, reason: str = "") -> Gate | None:
        """Record a decision. Idempotent — a decision on an already-decided
        gate returns the current state without overwriting.

        Creates the gate if missing so the HTTP layer can decide gates that
        weren't explicitly opened first (rare but tested).
        """
        with self._lock:
            gate = self._gates.get(name)
            if gate is None:
                gate = Gate(name=name)
                self._gates[name] = gate
                self._conditions[name] = threading.Condition(self._lock)
            if gate.decision != "pending":
                return gate
            gate.decision = decision  # type: ignore[assignment]
            gate.decided_at = time.time()
            if reason:
                gate.reason = reason
            cond = self._conditions.get(name)
            if cond is not None:
                cond.notify_all()
            return gate

    def wait(self, name: str, timeout_sec: int = 0) -> str:
        """Block until the gate is decided.

        Returns the decision string. Raises GateTimeout if ``timeout_sec > 0``
        and the deadline expires.
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

    def is_open(self, name: str) -> bool:
        """True if the gate exists and is still pending."""
        gate = self._gates.get(name)
        if gate is None:
            return False
        return gate.decision == "pending"

    def get_gate(self, name: str) -> Gate | None:
        return self._gates.get(name)

    def list_gates(self) -> list[Gate]:
        return list(self._gates.values())

    def get_rejection_reason(self, name: str) -> str:
        gate = self._gates.get(name)
        if gate is None:
            return ""
        return gate.reason


class GateRegistryStore:
    """Per-project container over ``GateRegistry``.

    The web backend holds one ``GateRegistryStore`` at app-state scope; each
    project gets its own ``GateRegistry`` on first touch. When the runner
    starts an orchestrator for a project it pulls the same registry out of
    the store and passes it to ``Orchestrator(gate_registry=...)`` — one
    instance, two readers.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._registries: dict[str, GateRegistry] = {}

    def ensure(self, project_id: str) -> GateRegistry:
        with self._lock:
            reg = self._registries.get(project_id)
            if reg is None:
                reg = GateRegistry()
                self._registries[project_id] = reg
            return reg

    def get(self, project_id: str) -> GateRegistry | None:
        with self._lock:
            return self._registries.get(project_id)
