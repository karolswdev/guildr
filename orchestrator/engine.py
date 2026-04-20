"""Orchestrator engine — phase state machine, retries, validators, gates."""

from __future__ import annotations

import logging
import inspect
from pathlib import Path
from typing import Any, Callable

from orchestrator.lib.config import Config
from orchestrator.lib.control import RUN_STEPS
from orchestrator.lib.logger import setup_phase_logger
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

    def run(self, *, start_at: str | None = None) -> None:
        """Execute the full SDLC pipeline, optionally resuming at one step."""
        self._ensure_git_repo()
        self._ensure_qwendea()
        steps: list[tuple[str, str, Callable[..., None]]] = [
            ("architect", "phase", self._architect),
            ("approve_sprint_plan", "gate", self._gate),
            ("implementation", "phase", self._coder),
            ("testing", "phase", self._tester),
            ("review", "phase", self._reviewer),
            ("approve_review", "gate", self._gate),
            ("deployment", "phase", self._deployer),
        ]
        start_index = 0
        if start_at is not None:
            if start_at not in RUN_STEPS:
                allowed = ", ".join(RUN_STEPS)
                raise ValueError(f"Unknown run step '{start_at}'. Expected one of: {allowed}")
            start_index = next(i for i, (name, _, _) in enumerate(steps) if name == start_at)

        for name, kind, fn in steps[start_index:]:
            if kind == "phase":
                self._run_phase(name, fn)
            else:
                fn(name)

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
            phase_logger = self._make_phase_logger(name)
            self._log_phase_event(
                phase_logger,
                logging.INFO,
                "phase_start",
                f"Starting phase '{name}' (attempt {attempt + 1}/{self.config.max_retries})",
                attempt=attempt,
            )
            try:
                if self._accepts_phase_logger(fn):
                    fn(phase_logger=phase_logger)
                else:
                    fn()
            except Exception as e:
                self._events_obj.emit("phase_error", name=name, error=str(e))
                self._log_phase_event(
                    phase_logger,
                    logging.ERROR,
                    "phase_error",
                    f"Phase '{name}' failed: {e}",
                    error=str(e),
                )
                if attempt == self.config.max_retries - 1:
                    raise PhaseFailure(name) from e
                continue

            if self._validate(name):
                self._events_obj.emit("phase_done", name=name)
                self._log_phase_event(
                    phase_logger,
                    logging.INFO,
                    "phase_done",
                    f"Phase '{name}' completed",
                )
                self.state.retries[name] = attempt + 1
                self.state.save()
                return

            # Validator failed — retry with failure context
            self._events_obj.emit("phase_retry", name=name, attempt=attempt + 1)
            next_attempt = min(attempt + 2, self.config.max_retries)
            self._log_phase_event(
                phase_logger,
                logging.WARNING,
                "phase_retry",
                f"Phase '{name}' validator failed; scheduling retry {next_attempt}",
                attempt=attempt + 1,
            )
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

    def _make_phase_logger(self, phase: str) -> logging.Logger:
        return setup_phase_logger(
            self.config.project_dir,
            phase,
            console=False,
        )

    @staticmethod
    def _accepts_phase_logger(fn: Callable[..., Any]) -> bool:
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return False
        for param in sig.parameters.values():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                return True
            if param.name == "phase_logger":
                return True
        return False

    @staticmethod
    def _log_phase_event(
        phase_logger: logging.Logger,
        level: int,
        event: str,
        message: str,
        **fields: Any,
    ) -> None:
        record = phase_logger.makeRecord(
            phase_logger.name,
            level,
            "",
            0,
            message,
            (),
            None,
        )
        setattr(record, "event", event)
        for key, value in fields.items():
            setattr(record, key, value)
        phase_logger.handle(record)

    def _architect(self, *, phase_logger: logging.Logger | None = None) -> None:
        """Run the Architect role."""
        from orchestrator.roles.architect import Architect

        llm = self._fake_llm or (self._pool.chat if self._pool else None)
        if llm is None:
            raise PhaseFailure("architect")

        architect = Architect(llm, self.state, self.config, _phase_logger=phase_logger)
        # Architect.execute() writes sprint-plan.md itself and returns the
        # path. Don't overwrite the file with the returned string.
        architect.execute()

    def _coder(self, *, phase_logger: logging.Logger | None = None) -> None:
        """Run the Coder role."""
        from orchestrator.roles.coder import Coder

        llm = self._fake_llm or (self._pool.chat if self._pool else None)
        if llm is None:
            raise PhaseFailure("implementation")

        coder = Coder(llm, self.state, phase_logger=phase_logger)
        coder.execute("sprint-plan.md")

    def _tester(self, *, phase_logger: logging.Logger | None = None) -> None:
        """Run the Tester role."""
        from orchestrator.roles.tester import Tester

        llm = self._fake_llm or (self._pool.chat if self._pool else None)
        if llm is None:
            raise PhaseFailure("testing")

        tester = Tester(llm, self.state, phase_logger=phase_logger)
        tester.execute("sprint-plan.md")

    def _reviewer(self, *, phase_logger: logging.Logger | None = None) -> None:
        """Run the Reviewer role."""
        from orchestrator.roles.reviewer import Reviewer

        llm = self._fake_llm or (self._pool.chat if self._pool else None)
        if llm is None:
            raise PhaseFailure("review")

        reviewer = Reviewer(llm, self.state, phase_logger=phase_logger)
        reviewer.execute("sprint-plan.md")

    def _deployer(self, *, phase_logger: logging.Logger | None = None) -> None:
        """Run the Deployer role."""
        from orchestrator.roles.deployer import Deployer

        llm = self._fake_llm or (self._pool.chat if self._pool else None)
        if llm is None:
            raise PhaseFailure("deployment")

        deployer = Deployer(llm, self.state, phase_logger=phase_logger)
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
