"""Orchestrator engine — phase state machine, retries, validators, gates."""

from __future__ import annotations

import logging
import inspect
from pathlib import Path
from typing import Any, Callable

from orchestrator.lib.config import Config
from orchestrator.lib.logger import setup_phase_logger
from orchestrator.lib.loop_refs import refs_for_phase
from orchestrator.lib.loops import emit_loop_event, loop_stage_for_step
from orchestrator.lib.state import State
from orchestrator.lib.workflow import enabled_steps

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
        session_runners: dict[str, Any] | None = None,
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
        # Roles migrated to the opencode runtime (H6.3a+) resolve their
        # runner here instead of via self._llm_for(). Dry-run and the
        # H5.3 integration test inject fakes; production wiring builds
        # one ``OpencodeSession`` per opencode-driven role.
        self._session_runners: dict[str, Any] = dict(session_runners or {})
        self.state.events = events

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
            # Fallback lets isolated unit tests run without the full wiring;
            # in production this means nothing on the outside (PWA, runner)
            # can see or decide the gates this engine opens. Anything running
            # with human gates enabled and hitting this branch is mis-wired.
            logger.warning(
                "Orchestrator constructed without gate_registry — falling back "
                "to a detached GateRegistry. No PWA/HTTP client can decide "
                "gates opened by this engine."
            )
            self._gate_registry = GateRegistry()
        return self._gate_registry

    @property
    def _git_ops_obj(self) -> Any:
        if self._git_ops is None:
            from orchestrator.lib.git import GitOps
            self._git_ops = GitOps(self.config.project_dir)
        return self._git_ops

    def _session_runner_for(self, role: str) -> Any:
        """Return the opencode-style session runner for an opencode-driven role.

        Resolution order:

        1. Runner explicitly injected via ``session_runners[role]`` — the
           production path (built from endpoints routing) and the
           H5-style integration tests that bring their own fake.
        2. Auto-provided dry-run runner when ``fake_llm`` is set — so
           existing dry-run tests don't each need to hand-build one.
           Only applies for the ``coder`` role for now (H6.3a); when
           tester/reviewer/deployer migrate, add auto-runners for them.
        3. ``None`` when nothing matches — caller raises ``PhaseFailure``.
        """
        if role in self._session_runners:
            return self._session_runners[role]
        if self._fake_llm is not None and role == "coder":
            from orchestrator.roles.coder_dryrun import DryRunCoderRunner
            runner = DryRunCoderRunner(self.state)
            self._session_runners[role] = runner
            return runner
        if self._fake_llm is not None and role == "reviewer":
            from orchestrator.roles.reviewer_dryrun import DryRunReviewerRunner
            runner = DryRunReviewerRunner(self.state)
            self._session_runners[role] = runner
            return runner
        if self._fake_llm is not None and role == "deployer":
            from orchestrator.roles.deployer_dryrun import DryRunDeployerRunner
            runner = DryRunDeployerRunner(self.state)
            self._session_runners[role] = runner
            return runner
        if self._fake_llm is not None and role == "tester":
            from orchestrator.roles.tester_dryrun import DryRunTesterRunner
            runner = DryRunTesterRunner(self.state)
            self._session_runners[role] = runner
            return runner
        if self._fake_llm is not None and role == "architect":
            from orchestrator.roles.architect_dryrun import DryRunArchitectRunner
            runner = DryRunArchitectRunner(self.state)
            self._session_runners[role] = runner
            return runner
        if self._fake_llm is not None and role == "judge":
            from orchestrator.roles.architect_dryrun import DryRunJudgeRunner
            runner = DryRunJudgeRunner(self.state)
            self._session_runners[role] = runner
            return runner
        return None

    def _llm_for(self, role: str) -> Any:
        """Return the LLM-shaped object a role should call.

        - ``fake_llm`` wins when set (test / dry-run path).
        - Otherwise wrap the async ``UpstreamPool`` in a per-role
          ``SyncPoolClient`` so the role's sync ``self.llm.chat(...)`` call
          reaches the pool without a coroutine leak (H5).
        - ``None`` when neither is configured — caller raises ``PhaseFailure``.
        """
        if self._fake_llm is not None:
            return self._fake_llm
        if self._pool is None:
            return None
        from orchestrator.lib.sync_pool import SyncPoolClient
        return SyncPoolClient(self._pool, role, project_dir=self.state.project_dir)

    # -- public API ----------------------------------------------------------

    def run(self, *, start_at: str | None = None) -> None:
        """Execute the full SDLC pipeline, optionally resuming at one step."""
        self.state.events = self._events_obj
        self._ensure_git_repo()
        self._ensure_qwendea()
        steps = enabled_steps(self.config.project_dir)
        start_index = 0
        if start_at is not None:
            valid_steps = [step["id"] for step in steps]
            if start_at not in valid_steps:
                allowed = ", ".join(valid_steps)
                raise ValueError(f"Unknown run step '{start_at}'. Expected one of: {allowed}")
            start_index = next(i for i, step in enumerate(steps) if step["id"] == start_at)

        for step in steps[start_index:]:
            if step["type"] == "phase":
                self._run_phase(step["id"], self._resolve_phase_handler(step["handler"]), step=step)
            else:
                self._run_gate_or_checkpoint(step)

    # -- phase execution -----------------------------------------------------

    def _run_phase(self, name: str, fn: Callable, *, step: dict[str, Any] | None = None) -> None:
        """Run a phase function with retry logic and validation.

        Retries on validator failure up to config.max_retries.
        Raises PhaseFailure if all retries exhausted.
        """
        for attempt in range(self.config.max_retries):
            self.state.current_phase = name
            self.state.save()
            self._events_obj.emit("phase_start", name=name, attempt=attempt)
            emit_loop_event(
                self._events_obj,
                "loop_entered",
                step=name,
                attempt=attempt,
                **refs_for_phase(name, self.state, include_outputs=False),
            )
            phase_logger = self._make_phase_logger(name)
            self._log_phase_event(
                phase_logger,
                logging.INFO,
                "phase_start",
                f"Starting phase '{name}' (attempt {attempt + 1}/{self.config.max_retries})",
                attempt=attempt,
            )
            try:
                self._invoke_handler(fn, phase_logger=phase_logger, step=step)
            except Exception as e:
                self._events_obj.emit("phase_error", name=name, error=str(e))
                emit_loop_event(
                    self._events_obj,
                    "loop_blocked",
                    step=name,
                    error=str(e),
                    attempt=attempt,
                    **refs_for_phase(name, self.state, include_outputs=False),
                )
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
                emit_loop_event(
                    self._events_obj,
                    "loop_completed",
                    step=name,
                    attempt=attempt,
                    **refs_for_phase(name, self.state, include_outputs=True),
                )
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
            stage = loop_stage_for_step(name)
            emit_loop_event(
                self._events_obj,
                "loop_blocked",
                step=name,
                loop_stage=stage,
                attempt=attempt,
                reason="validator_failed",
                **refs_for_phase(name, self.state, include_outputs=True),
            )
            emit_loop_event(
                self._events_obj,
                "loop_repaired",
                step=name,
                loop_stage="repair",
                attempt=attempt + 1,
                reason="validator_failed",
                **refs_for_phase(name, self.state, include_outputs=False),
            )
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

    def _resolve_phase_handler(self, handler_name: str) -> Callable[..., None]:
        mapping: dict[str, Callable[..., None]] = {
            "memory_refresh": self._memory_refresh,
            "persona_forum": self._persona_forum,
            "architect": self._architect,
            "architect_plan": self._architect_plan,
            "architect_refine": self._architect_refine,
            "micro_task_breakdown": self._micro_task_breakdown,
            "implementation": self._coder,
            "testing": self._tester,
            "guru_escalation": self._guru_escalation,
            "review": self._reviewer,
            "deployment": self._deployer,
        }
        try:
            return mapping[handler_name]
        except KeyError as exc:
            raise ValueError(f"Unsupported phase handler '{handler_name}'") from exc

    def _run_gate_or_checkpoint(self, step: dict[str, Any]) -> None:
        handler = step["handler"]
        if step["type"] == "gate":
            if handler == "approve_plan_draft" and self._plan_draft_auto_approved():
                logger.info(
                    "Gate 'approve_plan_draft' auto-approved (pass-1 plan already passed rubric)"
                )
                self._gate_registry_obj.decide(handler, "approved")
                self.state.gates_approved[handler] = True
                self.state.save()
                self._events_obj.emit("gate_decided", gate=handler, decision="approved")
                return
            self._gate(handler)
            return
        if handler == "operator_checkpoint":
            phase_logger = self._make_phase_logger(step["id"])
            self._log_phase_event(
                phase_logger,
                logging.INFO,
                "checkpoint",
                step.get("description") or f"Checkpoint '{step['id']}' reached",
            )
            self._events_obj.emit("checkpoint", name=step["id"], title=step.get("title", step["id"]))
            return
        raise ValueError(f"Unsupported workflow checkpoint handler '{handler}'")

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
            "architect_refine": validate_architect,
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
        emit_loop_event(
            self._events_obj,
            "loop_entered",
            step=name,
            atom_id=name,
            loop_stage="review",
            artifact_refs=[gate.artifact_path],
        )

        try:
            decision = self._gate_registry_obj.wait(name, timeout_sec=0)
        except GateTimeout:
            decision = "rejected"
            self._gate_registry_obj.decide(name, "rejected")

        self.state.gates_approved[name] = decision == "approved"
        self.state.save()
        self._events_obj.emit("gate_decided", gate=name, decision=decision)
        emit_loop_event(
            self._events_obj,
            "loop_completed" if decision == "approved" else "loop_blocked",
            step=name,
            atom_id=name,
            loop_stage="review",
            artifact_refs=[gate.artifact_path],
            decision=decision,
        )

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
    def _accepts_kwarg(fn: Callable[..., Any], name: str) -> bool:
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return False
        for param in sig.parameters.values():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                return True
            if param.name == name:
                return True
        return False

    def _invoke_handler(self, fn: Callable[..., Any], **kwargs: Any) -> Any:
        accepted = {
            key: value for key, value in kwargs.items()
            if self._accepts_kwarg(fn, key)
        }
        return fn(**accepted)

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

    def _build_architect(
        self, phase: str, phase_logger: logging.Logger | None
    ) -> Any:
        from orchestrator.roles.architect import Architect

        runner = self._session_runner_for("architect")
        judge_runner = self._session_runner_for("judge")
        if runner is None or judge_runner is None:
            raise PhaseFailure(phase)

        return Architect(
            runner=runner,
            judge_runner=judge_runner,
            state=self.state,
            config=self.config,
            _phase_logger=phase_logger,
            _phase=phase,
        )

    def _architect(self, *, phase_logger: logging.Logger | None = None) -> None:
        """Legacy combined architect phase (plan + refine in one step)."""
        self._build_architect("architect", phase_logger).execute()

    def _architect_plan(self, *, phase_logger: logging.Logger | None = None) -> None:
        """Run architect pass 1 only (H6.5). Stashes draft + status for
        ``approve_plan_draft`` gate and the ``architect_refine`` phase."""
        self._build_architect("architect_plan", phase_logger).plan()

    def _plan_draft_auto_approved(self) -> bool:
        """True when pass-1 already produced sprint-plan.md — skip gate."""
        import json as _json

        status_path = (
            self.state.project_dir / ".orchestrator" / "drafts" / "architect-plan-status.json"
        )
        if not status_path.exists():
            return False
        try:
            status = _json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return status.get("status") == "done"

    def _architect_refine(self, *, phase_logger: logging.Logger | None = None) -> None:
        """Run architect refinement passes (H6.5). No-op when pass 1
        already produced sprint-plan.md."""
        self._build_architect("architect_refine", phase_logger).refine()

    def _memory_refresh(
        self,
        *,
        phase_logger: logging.Logger | None = None,
        step: dict[str, Any] | None = None,
    ) -> None:
        from orchestrator.roles.memory_refresh import MemoryRefresh

        memory = MemoryRefresh(
            self.state,
            step_config=(step or {}).get("config") if step else None,
            _phase_logger=phase_logger,
        )
        memory.execute()

    def _persona_forum(
        self,
        *,
        phase_logger: logging.Logger | None = None,
        step: dict[str, Any] | None = None,
    ) -> None:
        from orchestrator.roles.persona_forum import PersonaForum

        llm = self._llm_for("persona_forum")
        forum = PersonaForum(
            llm,
            self.state,
            step_config=(step or {}).get("config") if step else None,
            _phase_logger=phase_logger,
        )
        forum.execute()

    def _micro_task_breakdown(
        self,
        *,
        phase_logger: logging.Logger | None = None,
        step: dict[str, Any] | None = None,
    ) -> None:
        from orchestrator.roles.micro_task_breaker import MicroTaskBreaker

        breaker = MicroTaskBreaker(self.state, _phase_logger=phase_logger)
        breaker.execute("sprint-plan.md")

    def _coder(self, *, phase_logger: logging.Logger | None = None) -> None:
        """Run the Coder role via an opencode session runner (H6.3a)."""
        from orchestrator.roles.coder import Coder

        runner = self._session_runner_for("coder")
        if runner is None:
            raise PhaseFailure("implementation")

        coder = Coder(runner, self.state, phase_logger=phase_logger)
        coder.execute("sprint-plan.md")

    def _tester(self, *, phase_logger: logging.Logger | None = None) -> None:
        """Run the Tester role via an opencode session runner (H6.3b)."""
        from orchestrator.roles.tester import Tester

        runner = self._session_runner_for("tester")
        if runner is None:
            raise PhaseFailure("testing")

        tester = Tester(runner, self.state, phase_logger=phase_logger)
        tester.execute("sprint-plan.md")

    def _guru_escalation(
        self,
        *,
        phase_logger: logging.Logger | None = None,
        step: dict[str, Any] | None = None,
    ) -> None:
        from orchestrator.roles.guru_escalation import GuruEscalation

        escalation = GuruEscalation(
            self.state,
            step_config=(step or {}).get("config") if step else None,
            _phase_logger=phase_logger,
        )
        escalation.execute()

    def _reviewer(self, *, phase_logger: logging.Logger | None = None) -> None:
        """Run the Reviewer via an opencode session runner (H6.3c)."""
        from orchestrator.roles.reviewer import Reviewer

        runner = self._session_runner_for("reviewer")
        if runner is None:
            raise PhaseFailure("review")

        reviewer = Reviewer(runner, self.state, phase_logger=phase_logger)
        reviewer.execute("sprint-plan.md")

    def _deployer(self, *, phase_logger: logging.Logger | None = None) -> None:
        """Run the Deployer via an opencode session runner (H6.3d)."""
        from orchestrator.roles.deployer import Deployer

        runner = self._session_runner_for("deployer")
        if runner is None:
            raise PhaseFailure("deployment")

        deployer = Deployer(runner, self.state, phase_logger=phase_logger)
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
