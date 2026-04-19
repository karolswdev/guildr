"""Orchestrator engine — phase state machine, retries, validators, gates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from orchestrator.lib.config import Config
from orchestrator.lib.state import State

logger = logging.getLogger(__name__)


class PhaseFailure(Exception):
    """Raised when a phase exhausts all retries without passing validation."""

    def __init__(self, phase_name: str) -> None:
        self.phase_name = phase_name
        super().__init__(f"Phase '{phase_name}' failed after exhausting retries")


class Orchestrator:
    """Executes the full SDLC pipeline through phase roles.

    May pause at human gates. Retries failed phases up to max_retries.
    """

    def __init__(
        self,
        config: Config,
        pool: object | None = None,
        gate_registry: object | None = None,
        events: object | None = None,
        git_ops: object | None = None,
        fake_llm: object | None = None,
    ) -> None:
        # All dependent modules are imported lazily so the engine skeleton
        # can be committed independently of Tasks 2-6.
        self.config = config
        self.state = State(config.project_dir)
        self.state.load()
        self._pool = pool
        self._gate_registry = gate_registry
        self._events = events
        self._git_ops = git_ops
        self._fake_llm = fake_llm

    # -- lazy accessors (import on first use) --------------------------------

    @property
    def _events_obj(self) -> Any:
        if self._events is None:
            from orchestrator.lib.events import EventBus
            self._events = EventBus()
        return self._events

    @property
    def _gate_registry_obj(self) -> Any:
        if self._gate_registry is None:
            from orchestrator.lib.gates import GateRegistry
            self._gate_registry = GateRegistry()
        return self._gate_registry

    @property
    def _git_ops_obj(self) -> Any:
        if self._git_ops is None:
            from orchestrator.lib.git import GitOps
            self._git_ops = GitOps(self.config.project_dir)
        return self._git_ops

    # -- public API ----------------------------------------------------------

    def run(self) -> None:
        """Execute the full SDLC pipeline. May pause at gates."""
        self._ensure_git_repo()
        self._ensure_qwendea()
        self._run_phase("architect", self._architect)
        self._gate("approve_sprint_plan")
        self._run_phase("implementation", self._coder)
        self._run_phase("testing", self._tester)
        self._run_phase("review", self._reviewer)
        self._gate("approve_review")
        self._run_phase("deployment", self._deployer)

    # -- phase execution -----------------------------------------------------

    def _run_phase(self, name: str, fn: Callable) -> None:
        """Run a phase function with retry logic and validation.

        Retries on validator failure up to config.max_retries.
        Raises PhaseFailure if all retries exhausted.
        """
        for attempt in range(self.config.max_retries):
            self.state.current_phase = name
            self.state.save()
            self._events_obj.emit("phase_start", name=name, attempt=attempt)
            try:
                fn()
            except Exception as e:
                self._events_obj.emit("phase_error", name=name, error=str(e))
                if attempt == self.config.max_retries - 1:
                    raise PhaseFailure(name) from e
                continue

            if self._validate(name):
                self._events_obj.emit("phase_done", name=name)
                self.state.retries[name] = attempt + 1
                self.state.save()
                return

            # Validator failed — retry with failure context
            self._events_obj.emit("phase_retry", name=name, attempt=attempt + 1)
            logger.warning(
                "Phase '%s' validator failed (attempt %d/%d), retrying",
                name, attempt + 1, self.config.max_retries,
            )

        raise PhaseFailure(name)

    def _validate(self, name: str) -> bool:
        """Run the validator for a phase. Returns True if passed."""
        from orchestrator.lib.validators import (
            validate_architect,
            validate_implementation,
            validate_review,
            validate_testing,
        )

        validators = {
            "architect": validate_architect,
            "implementation": validate_implementation,
            "testing": validate_testing,
            "review": validate_review,
        }
        validator = validators.get(name)
        if validator is None:
            # No validator defined — assume pass
            return True
        passed, reason = validator(self.state)
        if not passed:
            logger.debug("Validator for '%s' failed: %s", name, reason)
        return passed

    # -- human gates ---------------------------------------------------------

    def _gate(self, name: str) -> None:
        """Block until PWA records an approval decision."""
        from orchestrator.lib.gates import Gate, GateTimeout

        if not self.config.require_human_approval:
            logger.info("Gate '%s' skipped (require_human_approval=False)", name)
            self._gate_registry_obj.decide(name, "approved")
            return

        gate = Gate(name=name, artifact_path=f"{name}-artifact.md")
        self._gate_registry_obj.open(gate)
        self._events_obj.emit("gate_opened", gate=name)

        try:
            decision = self._gate_registry_obj.wait(name, timeout_sec=0)
        except GateTimeout:
            decision = "rejected"
            self._gate_registry_obj.decide(name, "rejected")

        self.state.gates_approved[name] = decision == "approved"
        self.state.save()
        self._events_obj.emit("gate_decided", gate=name, decision=decision)

        if decision == "rejected":
            reason = self._gate_registry_obj.get_rejection_reason(name)
            raise PhaseFailure(
                f"Gate '{name}' rejected: {reason}"
            )

    # -- setup helpers -------------------------------------------------------

    def _ensure_git_repo(self) -> None:
        """Initialize git repo if needed; seed .gitignore."""
        self._git_ops_obj.ensure_repo(self.config.project_dir)

    def _ensure_qwendea(self) -> None:
        """Verify qwendea.md exists. Raises if missing."""
        qwendea_path = self.config.project_dir / "qwendea.md"
        if not qwendea_path.exists():
            raise FileNotFoundError(
                f"qwendea.md not found at {qwendea_path}. "
                "Run ingestion phase first."
            )

    # -- role phase functions ------------------------------------------------

    def _architect(self) -> None:
        """Run the Architect role."""
        from orchestrator.roles.architect import Architect

        llm = self._fake_llm or (self._pool.chat if self._pool else None)
        if llm is None:
            raise PhaseFailure("architect")

        architect = Architect(llm, self.state, self.config)
        plan_text = architect.execute()
        self.state.write_file("sprint-plan.md", plan_text)

    def _coder(self) -> None:
        """Run the Coder role."""
        from orchestrator.roles.coder import Coder

        llm = self._fake_llm or (self._pool.chat if self._pool else None)
        if llm is None:
            raise PhaseFailure("implementation")

        coder = Coder(llm, self.state)
        coder.execute("sprint-plan.md")

    def _tester(self) -> None:
        """Run the Tester role."""
        from orchestrator.roles.tester import Tester

        llm = self._fake_llm or (self._pool.chat if self._pool else None)
        if llm is None:
            raise PhaseFailure("testing")

        tester = Tester(llm, self.state)
        tester.execute("sprint-plan.md")

    def _reviewer(self) -> None:
        """Run the Reviewer role."""
        from orchestrator.roles.reviewer import Reviewer

        llm = self._fake_llm or (self._pool.chat if self._pool else None)
        if llm is None:
            raise PhaseFailure("review")

        reviewer = Reviewer(llm, self.state)
        reviewer.execute("sprint-plan.md")

    def _deployer(self) -> None:
        """Run the Deployer role."""
        from orchestrator.roles.deployer import Deployer

        llm = self._fake_llm or (self._pool.chat if self._pool else None)
        if llm is None:
            raise PhaseFailure("deployment")

        deployer = Deployer(llm, self.state)
        deployer.execute("REVIEW.md")

    # -- pool access ---------------------------------------------------------

    @property
    def pool(self) -> Any | None:
        """Access the upstream pool (set after init if created externally)."""
        return self._pool

    @pool.setter
    def pool(self, value: Any) -> None:
        """Set the upstream pool."""
        self._pool = value
        if self._pool is not None:
            set_orchestrator = getattr(self._pool, "set_orchestrator", None)
            if set_orchestrator is not None:
                set_orchestrator(self)

    @property
    def fake_llm(self) -> Any | None:
        """Access the fake LLM client (used in dry-run mode)."""
        return self._fake_llm

    @fake_llm.setter
    def fake_llm(self, value: Any) -> None:
        """Set the fake LLM client."""
        self._fake_llm = value

    def is_dry_run(self) -> bool:
        """Return True if the fake LLM client is set."""
        return self._fake_llm is not None
