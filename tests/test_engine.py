"""Tests for orchestrator.engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.engine import Orchestrator, PhaseFailure
from orchestrator.lib.config import Config
from orchestrator.lib.intents import create_queued_intent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    return tmp_path


@pytest.fixture
def config(tmp_project: Path) -> Config:
    """Create a minimal Config."""
    return Config(
        llama_server_url="http://127.0.0.1:8080",
        project_dir=tmp_project,
        max_retries=3,
    )


@pytest.fixture
def qwendea(tmp_project: Path) -> Path:
    """Create a qwendea.md file so _ensure_qwendea passes."""
    qwendea = tmp_project / "qwendea.md"
    qwendea.write_text("# Test Project\n\nDescription.", encoding="utf-8")
    return qwendea


@pytest.fixture
def sprint_plan(tmp_project: Path) -> Path:
    """Create a sprint-plan.md with Evidence Required sections."""
    plan = tmp_project / "sprint-plan.md"
    plan.write_text(
        "# Sprint Plan\n\n"
        "## Architecture Decisions\n- Use FastAPI\n\n"
        "## Tasks\n\n"
        "### Task 1: Setup\n"
        "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `app/__init__.py`\n\n"
        "**Acceptance Criteria:**\n- [ ] Imports\n\n"
        "**Evidence Required:**\n- Run `python -c 'import app'`\n\n"
        "**Evidence Log:**\n- [ ] Done\n\n"
        "## Risks & Mitigations\n1. Risk — Mitigation\n",
        encoding="utf-8",
    )
    return plan


@pytest.fixture
def mock_git_ops(tmp_project: Path) -> MagicMock:
    """Mock GitOps so git operations don't touch the real filesystem."""
    ops = MagicMock()
    ops.ensure_repo = MagicMock()
    ops.assert_clean = MagicMock()
    ops.commit_task = MagicMock(return_value="abc1234")
    ops.tag_phase = MagicMock()
    ops.rollback_to = MagicMock()
    return ops


class CaptureEvents:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, **fields) -> None:
        self.events.append({"type": event_type, **fields})


class ReturningCaptureEvents(CaptureEvents):
    def emit(self, event_type: str, **fields) -> dict:
        event = {
            "type": event_type,
            "event_id": f"evt-{len(self.events) + 1}",
            "schema_version": 1,
            "ts": "2026-04-22T00:00:00Z",
            **fields,
        }
        self.events.append(event)
        return event


# ---------------------------------------------------------------------------
# Tests: run() calls phases in correct order
# ---------------------------------------------------------------------------


class TestRunOrder:
    """Test that Orchestrator.run() calls phases in the correct order."""

    def test_run_calls_phases_in_order(self, config, qwendea, mock_git_ops):
        """run() calls phases in the correct SDLC order."""
        # Provide a sprint-plan.md so architect validator passes
        (config.project_dir / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [x] Done\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )

        # Create TEST_REPORT.md and REVIEW.md so validators pass
        (config.project_dir / "a.py").write_text("# code\n", encoding="utf-8")
        (config.project_dir / "TEST_REPORT.md").write_text("All tests passed.", encoding="utf-8")
        (config.project_dir / "REVIEW.md").write_text("APPROVED", encoding="utf-8")

        # Mock the roles to track call order
        call_order = []

        def mock_architect_plan():
            call_order.append("architect_plan")

        def mock_architect_refine():
            call_order.append("architect_refine")

        def mock_persona_forum():
            call_order.append("persona_forum")

        def mock_micro_task_breakdown():
            call_order.append("micro_task_breakdown")

        def mock_guru_escalation():
            call_order.append("guru_escalation")

        def mock_coder():
            call_order.append("implementation")

        def mock_tester():
            call_order.append("testing")

        def mock_reviewer():
            call_order.append("review")

        def mock_deployer():
            call_order.append("deployment")

        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )

        # Patch gate to auto-approve
        orchestrator._gate = MagicMock()

        # Patch role methods
        orchestrator._persona_forum = mock_persona_forum
        orchestrator._architect_plan = mock_architect_plan
        orchestrator._architect_refine = mock_architect_refine
        orchestrator._micro_task_breakdown = mock_micro_task_breakdown
        orchestrator._coder = mock_coder
        orchestrator._tester = mock_tester
        orchestrator._guru_escalation = mock_guru_escalation
        orchestrator._reviewer = mock_reviewer
        orchestrator._deployer = mock_deployer

        orchestrator.run()

        assert call_order == [
            "persona_forum",
            "architect_plan",
            "architect_refine",
            "micro_task_breakdown",
            "implementation",
            "testing",
            "review",
            "deployment",
        ]

    def test_run_calls_ensure_git_repo(self, config, qwendea, mock_git_ops):
        """run() calls _ensure_git_repo first."""
        (config.project_dir / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [x] Done\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )
        (config.project_dir / "a.py").write_text("# code\n", encoding="utf-8")
        (config.project_dir / "TEST_REPORT.md").write_text("All tests passed.", encoding="utf-8")
        (config.project_dir / "REVIEW.md").write_text("APPROVED", encoding="utf-8")

        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        orchestrator._gate = MagicMock()
        orchestrator._persona_forum = MagicMock()
        orchestrator._architect = MagicMock()
        orchestrator._architect_plan = MagicMock()
        orchestrator._architect_refine = MagicMock()
        orchestrator._micro_task_breakdown = MagicMock()
        orchestrator._coder = MagicMock()
        orchestrator._tester = MagicMock()
        orchestrator._guru_escalation = MagicMock()
        orchestrator._reviewer = MagicMock()
        orchestrator._deployer = MagicMock()

        orchestrator.run()

        mock_git_ops.ensure_repo.assert_called_once()


    def test_run_calls_ensure_qwendea(self, config, qwendea, mock_git_ops):
        """run() calls _ensure_qwendea after git repo setup."""
        (config.project_dir / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [x] Done\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )
        (config.project_dir / "a.py").write_text("# code\n", encoding="utf-8")
        (config.project_dir / "TEST_REPORT.md").write_text("All tests passed.", encoding="utf-8")
        (config.project_dir / "REVIEW.md").write_text("APPROVED", encoding="utf-8")

        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        orchestrator._gate = MagicMock()
        orchestrator._persona_forum = MagicMock()
        orchestrator._architect = MagicMock()
        orchestrator._architect_plan = MagicMock()
        orchestrator._architect_refine = MagicMock()
        orchestrator._micro_task_breakdown = MagicMock()
        orchestrator._coder = MagicMock()
        orchestrator._tester = MagicMock()
        orchestrator._guru_escalation = MagicMock()
        orchestrator._reviewer = MagicMock()
        orchestrator._deployer = MagicMock()

        orchestrator.run()

        # _ensure_qwendea should have been called (no exception raised)
        # If qwendea.md exists, it silently passes
        assert config.project_dir.exists()


class TestLoopEvents:
    """SDLC loop event emission."""

    def test_validator_retry_emits_verify_repair_verify_loop(
        self,
        config: Config,
        mock_git_ops: MagicMock,
    ) -> None:
        events = CaptureEvents()
        orchestrator = Orchestrator(config=config, git_ops=mock_git_ops, events=events)
        validation_results = iter([False, True])
        orchestrator._validate = MagicMock(side_effect=lambda name: next(validation_results))

        orchestrator._run_phase("testing", lambda: None)

        loop_events = [event for event in events.events if event["type"].startswith("loop_")]
        assert [(event["type"], event["loop_stage"]) for event in loop_events] == [
            ("loop_entered", "verify"),
            ("loop_blocked", "verify"),
            ("loop_repaired", "repair"),
            ("loop_entered", "verify"),
            ("loop_completed", "verify"),
        ]
        assert all(event["step"] == "testing" for event in loop_events)
        assert all("loop_id" in event for event in loop_events)

    def test_memory_refresh_maps_to_learn_loop(
        self,
        config: Config,
        mock_git_ops: MagicMock,
    ) -> None:
        events = CaptureEvents()
        orchestrator = Orchestrator(config=config, git_ops=mock_git_ops, events=events)
        orchestrator._validate = MagicMock(return_value=True)

        orchestrator._run_phase("memory_refresh", lambda: None)

        loop_events = [event for event in events.events if event["type"].startswith("loop_")]
        assert [(event["type"], event["loop_stage"]) for event in loop_events] == [
            ("loop_entered", "learn"),
            ("loop_completed", "learn"),
        ]

    def test_phase_boundaries_emit_next_step_packets(
        self,
        config: Config,
        mock_git_ops: MagicMock,
    ) -> None:
        events = CaptureEvents()
        orchestrator = Orchestrator(config=config, git_ops=mock_git_ops, events=events)
        orchestrator._validate = MagicMock(return_value=True)

        orchestrator._run_phase("memory_refresh", lambda: None)

        packet_events = [event for event in events.events if event["type"] == "next_step_packet_created"]
        assert [event["packet"]["step"] for event in packet_events] == [
            "memory_refresh",
            "persona_forum",
        ]
        assert packet_events[0]["packet_id"].startswith("next_")
        assert packet_events[0]["source_refs"]

    def test_phase_boundaries_emit_memory_diff_when_wakeup_changes(
        self,
        config: Config,
        mock_git_ops: MagicMock,
    ) -> None:
        memory_dir = config.project_dir / ".orchestrator" / "memory"
        memory_dir.mkdir(parents=True)
        wakeup = memory_dir / "wake-up.md"
        wakeup.write_text("initial memory", encoding="utf-8")
        events = ReturningCaptureEvents()
        orchestrator = Orchestrator(config=config, git_ops=mock_git_ops, events=events)
        orchestrator._validate = MagicMock(return_value=True)

        orchestrator._run_phase("architect", lambda: None)
        wakeup.write_text("changed memory", encoding="utf-8")
        orchestrator._run_phase("testing", lambda: None)

        diff_events = [event for event in events.events if event["type"] == "memory_diff"]
        assert len(diff_events) == 2
        assert diff_events[0]["step"] == "architect"
        assert diff_events[0]["previous_wake_up_hash"] is None
        assert diff_events[0]["hash_changed"] is False
        assert diff_events[0]["wake_up_hash"]
        assert diff_events[0]["memory_refs"] == [".orchestrator/memory/wake-up.md"]
        assert diff_events[0]["source_refs"][0].startswith("event:")
        assert diff_events[1]["step"] == "testing"
        assert diff_events[1]["previous_wake_up_hash"] == diff_events[0]["wake_up_hash"]
        assert diff_events[1]["wake_up_hash"] != diff_events[0]["wake_up_hash"]
        assert diff_events[1]["hash_changed"] is True

    def test_phase_completion_emits_narrative_digest(
        self,
        config: Config,
        mock_git_ops: MagicMock,
    ) -> None:
        events = ReturningCaptureEvents()
        orchestrator = Orchestrator(config=config, git_ops=mock_git_ops, events=events)
        orchestrator._validate = MagicMock(return_value=True)

        orchestrator._run_phase("memory_refresh", lambda: None)

        digest_events = [event for event in events.events if event["type"] == "narrative_digest_created"]
        assert len(digest_events) == 1
        digest = digest_events[0]["digest"]
        assert digest["title"] == "memory_refresh completed"
        assert digest["source_event_ids"] == [
            event["event_id"] for event in events.events if event["type"] == "phase_done"
        ]
        assert digest["next_step_hint"] == "Founding Team Forum (persona_forum)"
        assert digest_events[0]["artifact_refs"][0].startswith(".orchestrator/narrative/digests/")

    def test_phase_completion_with_narrator_runner_emits_refined_packet(
        self,
        config: Config,
        mock_git_ops: MagicMock,
    ) -> None:
        events = ReturningCaptureEvents()
        orchestrator = Orchestrator(config=config, git_ops=mock_git_ops, events=events, dry_run=True)
        orchestrator._validate = MagicMock(return_value=True)

        orchestrator._run_phase("memory_refresh", lambda: None)

        digest_events = [event for event in events.events if event["type"] == "narrative_digest_created"]
        assert digest_events[-1]["generated_by"] == "narrator"
        refined_packets = [
            event for event in events.events
            if event["type"] == "next_step_packet_created"
            and event["packet"].get("refined_by") == "narrator"
        ]
        assert len(refined_packets) == 1
        assert refined_packets[0]["packet"]["base_packet_id"].startswith("next_")
        assert refined_packets[0]["packet"]["narrative_digest_id"] == digest_events[-1]["digest_id"]
        assert "narrator_sidecar_completed" in [event["type"] for event in events.events]

    def test_optional_narrator_phase_runs_sidecar_without_duplicate_completion_sidecar(
        self,
        config: Config,
        mock_git_ops: MagicMock,
    ) -> None:
        events = ReturningCaptureEvents()
        orchestrator = Orchestrator(config=config, git_ops=mock_git_ops, events=events, dry_run=True)
        orchestrator._validate = MagicMock(return_value=True)

        orchestrator._run_phase("narrator", orchestrator._resolve_phase_handler("narrator"))

        event_types = [event["type"] for event in events.events]
        assert "narrator_phase_requested" in event_types
        assert event_types.count("narrator_sidecar_completed") == 1
        refined_packets = [
            event for event in events.events
            if event["type"] == "next_step_packet_created"
            and event["packet"].get("refined_by") == "narrator"
        ]
        assert len(refined_packets) == 1

    def test_missing_pre_step_packet_triggers_narrator_sidecar(
        self,
        config: Config,
        mock_git_ops: MagicMock,
    ) -> None:
        events = ReturningCaptureEvents()
        orchestrator = Orchestrator(config=config, git_ops=mock_git_ops, events=events, dry_run=True)
        orchestrator._validate = MagicMock(return_value=True)
        orchestrator._emit_next_step_packet = MagicMock(return_value=None)

        orchestrator._run_phase("memory_refresh", lambda: None)

        event_types = [event["type"] for event in events.events]
        assert "narrator_pre_step" in event_types
        assert "narrator_sidecar_completed" in event_types

    def test_phase_completion_ignores_stale_targeted_intent(
        self,
        config: Config,
        mock_git_ops: MagicMock,
    ) -> None:
        events = CaptureEvents()
        orchestrator = Orchestrator(config=config, git_ops=mock_git_ops, events=events)
        orchestrator._validate = MagicMock(return_value=True)
        create_queued_intent(
            config.project_dir,
            kind="interject",
            atom_id="memory_refresh",
            payload={"instruction": "Too late"},
            client_intent_id="client-1",
            intent_event_id="event-1",
        )

        orchestrator._run_phase("memory_refresh", lambda: None)

        ignored = [event for event in events.events if event["type"] == "operator_intent_ignored"]
        assert ignored
        assert ignored[0]["client_intent_id"] == "client-1"
        assert ignored[0]["reason"] == "target_step_passed"


# ---------------------------------------------------------------------------
# Tests: _run_phase retries on validator failure
# ---------------------------------------------------------------------------


class TestRunPhaseRetries:
    """Test that _run_phase retries on validator failure."""

    def test_retries_on_validator_failure(self, config, qwendea, mock_git_ops):
        """_run_phase retries when validator returns False."""
        (config.project_dir / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [ ] Done\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )

        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )

        call_count = 0

        def failing_then_passing():
            nonlocal call_count
            call_count += 1
            plan = config.project_dir / "sprint-plan.md"
            if call_count < 3:
                # Remove sprint-plan to make validator fail
                if plan.exists():
                    plan.unlink()
            else:
                # Put it back so validator passes
                plan.write_text(
                    "# Sprint Plan\n\n"
                    "## Architecture Decisions\n- None\n\n"
                    "## Tasks\n\n"
                    "### Task 1: Setup\n"
                    "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
                    "**Acceptance Criteria:**\n- [ ] Works\n\n"
                    "**Evidence Required:**\n- Run `pytest`\n\n"
                    "**Evidence Log:**\n- [x] Done\n\n"
                    "## Risks & Mitigations\n1. Risk — Mitigation\n",
                    encoding="utf-8",
                )

        orchestrator._run_phase("architect", failing_then_passing)

        assert call_count == 3

    def test_retries_exhausted_raises_phase_failure(self, config, qwendea, mock_git_ops):
        """PhaseFailure raised after exhausting retries."""
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )

        def always_fail():
            # Remove sprint-plan so architect validator fails
            plan = config.project_dir / "sprint-plan.md"
            if plan.exists():
                plan.unlink()

        with pytest.raises(PhaseFailure, match="architect"):
            orchestrator._run_phase("architect", always_fail)

    def test_missing_pre_step_packet_emits_once_across_retries(self, config, qwendea, mock_git_ops):
        """Pre-step narrator trigger is tied to the logical step, not each retry."""
        events = ReturningCaptureEvents()
        orchestrator = Orchestrator(
            config=config,
            git_ops=mock_git_ops,
            events=events,
            dry_run=True,
        )
        orchestrator._emit_next_step_packet = MagicMock(return_value=None)
        orchestrator._validate = MagicMock(return_value=False)

        with pytest.raises(PhaseFailure, match="architect"):
            orchestrator._run_phase("architect", lambda: None)

        pre_step_events = [
            event for event in events.events
            if event["type"] == "narrator_pre_step"
        ]
        assert len(pre_step_events) == 1
        assert [
            event["attempt"] for event in events.events
            if event["type"] == "phase_start"
        ] == [0, 1, 2]


# ---------------------------------------------------------------------------
# Tests: exception propagates as PhaseFailure after exhausting retries
# ---------------------------------------------------------------------------


class TestExceptionPropagation:
    """Test that exceptions propagate as PhaseFailure after exhausting retries."""

    def test_role_exception_wrapped_in_phase_failure(self, config, qwendea, mock_git_ops):
        """Exception in role propagates as PhaseFailure after max retries."""
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )

        # Provide sprint-plan so validator would pass, but role raises
        (config.project_dir / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [ ] Done\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )

        def role_raises():
            raise RuntimeError("Something went wrong")

        with pytest.raises(PhaseFailure, match="architect"):
            orchestrator._run_phase("architect", role_raises)

    def test_exception_preserves_cause(self, config, qwendea, mock_git_ops):
        """PhaseFailure preserves the original exception as __cause__."""
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )

        (config.project_dir / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [ ] Done\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )

        original_error = ValueError("original error")

        def role_raises():
            raise original_error

        with pytest.raises(PhaseFailure) as exc_info:
            orchestrator._run_phase("architect", role_raises)

        assert exc_info.value.__cause__ is original_error


# ---------------------------------------------------------------------------
# Tests: state persisted after every phase transition
# ---------------------------------------------------------------------------


class TestStatePersistence:
    """Test that state is persisted after every phase transition."""

    def test_state_saved_on_phase_start(self, config, qwendea, mock_git_ops):
        """State.current_phase is saved when _run_phase starts."""
        (config.project_dir / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [ ] Done\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )

        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )

        orchestrator._run_phase("architect", MagicMock())

        # State should have been saved with current_phase = "architect"
        state_file = config.project_dir / ".orchestrator" / "state.json"
        assert state_file.exists()
        import json
        data = json.loads(state_file.read_text())
        assert data["current_phase"] == "architect"

    def test_state_saved_on_phase_done(self, config, qwendea, mock_git_ops):
        """State.save() is called when phase passes validation."""
        (config.project_dir / "sprint-plan.md").write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [x] Done\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )

        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )

        orchestrator._run_phase("architect", MagicMock())

        state_file = config.project_dir / ".orchestrator" / "state.json"
        import json
        data = json.loads(state_file.read_text())
        assert data["retries"]["architect"] == 1

    def test_state_persists_between_retries(self, config, qwendea, mock_git_ops):
        """State is re-saved on each retry attempt."""
        # Start with no sprint-plan so validator fails first 2 attempts
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )

        call_count = 0

        def fails_then_passes():
            nonlocal call_count
            call_count += 1
            plan = config.project_dir / "sprint-plan.md"
            if call_count < 3:
                if plan.exists():
                    plan.unlink()
            else:
                plan.write_text(
                    "# Sprint Plan\n\n"
                    "## Architecture Decisions\n- None\n\n"
                    "## Tasks\n\n"
                    "### Task 1: Setup\n"
                    "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
                    "**Acceptance Criteria:**\n- [ ] Works\n\n"
                    "**Evidence Required:**\n- Run `pytest`\n\n"
                    "**Evidence Log:**\n- [x] Done\n\n"
                    "## Risks & Mitigations\n1. Risk — Mitigation\n",
                    encoding="utf-8",
                )

        orchestrator._run_phase("architect", fails_then_passes)

        state_file = config.project_dir / ".orchestrator" / "state.json"
        import json
        data = json.loads(state_file.read_text())
        assert data["current_phase"] == "architect"
        assert data["retries"]["architect"] == 3


# ---------------------------------------------------------------------------
# Tests: _ensure_qwendea
# ---------------------------------------------------------------------------


class TestEnsureQwendea:
    """Test _ensure_qwendea behavior."""

    def test_passes_when_qwendea_exists(self, config, qwendea, mock_git_ops):
        """No exception when qwendea.md exists."""
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        orchestrator._ensure_qwendea()  # should not raise

    def test_raises_when_qwendea_missing(self, config, mock_git_ops):
        """Raises FileNotFoundError when qwendea.md is missing."""
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        with pytest.raises(FileNotFoundError, match="qwendea.md not found"):
            orchestrator._ensure_qwendea()


# ---------------------------------------------------------------------------
# Tests: _validate
# ---------------------------------------------------------------------------


class TestValidate:
    """Test _validate method."""

    def test_architect_validator_passes(self, config, qwendea, mock_git_ops, sprint_plan):
        """validate_architect returns True when sprint-plan.md exists with Evidence Required."""
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        assert orchestrator._validate("architect") is True

    def test_architect_validator_fails_missing_file(self, config, qwendea, mock_git_ops):
        """validate_architect returns False when sprint-plan.md is missing."""
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        assert orchestrator._validate("architect") is False

    def test_architect_validator_fails_no_evidence_required(self, config, qwendea, mock_git_ops):
        """validate_architect returns False when sprint-plan.md lacks Evidence Required."""
        plan = config.project_dir / "sprint-plan.md"
        plan.write_text("# Sprint Plan\n\nNo evidence sections here.", encoding="utf-8")
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        assert orchestrator._validate("architect") is False

    def test_unknown_phase_returns_true(self, config, qwendea, mock_git_ops):
        """Unknown phase names return True (no validator defined)."""
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        assert orchestrator._validate("deployment") is True

    def test_implementation_validator_passes(self, config, qwendea, mock_git_ops):
        """validate_implementation returns True when all declared files exist."""
        plan = config.project_dir / "sprint-plan.md"
        plan.write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [x] Done\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )
        (config.project_dir / "a.py").write_text("# code\n", encoding="utf-8")
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        assert orchestrator._validate("implementation") is True

    def test_implementation_validator_fails_missing_declared_file(self, config, qwendea, mock_git_ops):
        """validate_implementation returns False when declared files are missing."""
        plan = config.project_dir / "sprint-plan.md"
        plan.write_text(
            "# Sprint Plan\n\n"
            "## Architecture Decisions\n- None\n\n"
            "## Tasks\n\n"
            "### Task 1: Setup\n"
            "- **Priority**: P0\n- **Dependencies**: none\n- **Files**: `a.py`\n\n"
            "**Acceptance Criteria:**\n- [ ] Works\n\n"
            "**Evidence Required:**\n- Run `pytest`\n\n"
            "**Evidence Log:**\n- [ ] Not done\n\n"
            "## Risks & Mitigations\n1. Risk — Mitigation\n",
            encoding="utf-8",
        )
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        assert orchestrator._validate("implementation") is False

    def test_testing_validator_passes(self, config, qwendea, mock_git_ops):
        """validate_testing returns True when TEST_REPORT.md has no failures."""
        (config.project_dir / "TEST_REPORT.md").write_text("All tests passed.", encoding="utf-8")
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        assert orchestrator._validate("testing") is True

    def test_testing_validator_fails_mismatch(self, config, qwendea, mock_git_ops):
        """validate_testing returns False when TEST_REPORT contains MISMATCH."""
        (config.project_dir / "TEST_REPORT.md").write_text("MISMATCH found in task 2.", encoding="utf-8")
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        assert orchestrator._validate("testing") is False

    def test_testing_validator_fails_rerun_failed(self, config, qwendea, mock_git_ops):
        """validate_testing returns False when TEST_REPORT contains RERUN_FAILED."""
        (config.project_dir / "TEST_REPORT.md").write_text("RERUN_FAILED in task 3.", encoding="utf-8")
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        assert orchestrator._validate("testing") is False

    def test_review_validator_passes_approved(self, config, qwendea, mock_git_ops):
        """validate_review returns True when REVIEW.md verdict is APPROVED."""
        (config.project_dir / "REVIEW.md").write_text("APPROVED", encoding="utf-8")
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        assert orchestrator._validate("review") is True

    def test_review_validator_passes_with_notes(self, config, qwendea, mock_git_ops):
        """validate_review returns True when REVIEW.md verdict is APPROVED WITH NOTES."""
        (config.project_dir / "REVIEW.md").write_text("APPROVED WITH NOTES", encoding="utf-8")
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        assert orchestrator._validate("review") is True

    def test_review_validator_fails_critical(self, config, qwendea, mock_git_ops):
        """validate_review returns False when REVIEW.md contains CRITICAL."""
        (config.project_dir / "REVIEW.md").write_text("CRITICAL: Major issues found", encoding="utf-8")
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        assert orchestrator._validate("review") is False

    def test_review_validator_fails_changes_requested(self, config, qwendea, mock_git_ops):
        """validate_review returns False when REVIEW.md contains CHANGES REQUESTED."""
        (config.project_dir / "REVIEW.md").write_text("CHANGES REQUESTED: Fix these issues", encoding="utf-8")
        orchestrator = Orchestrator(
            config=config,

            git_ops=mock_git_ops,
        )
        assert orchestrator._validate("review") is False
