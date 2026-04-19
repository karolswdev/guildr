"""Tests for orchestrator.lib.gates."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from orchestrator.lib.gates import Gate, GateRegistry, GateTimeout


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    return tmp_path


class TestGate:
    """Test Gate dataclass."""

    def test_gate_has_required_fields(self):
        """Gate has name, artifact_path, and decision fields."""
        gate = Gate(name="approve_sprint_plan", artifact_path="sprint-plan.md")
        assert gate.name == "approve_sprint_plan"
        assert gate.artifact_path == "sprint-plan.md"
        assert gate.decision == "pending"

    def test_gate_default_decision_is_pending(self):
        """Gate.decision defaults to 'pending'."""
        gate = Gate(name="approve_review", artifact_path="review.md")
        assert gate.decision == "pending"

    def test_gate_has_reason_field(self):
        """Gate has a reason field."""
        gate = Gate(name="approve_sprint_plan", artifact_path="sprint-plan.md")
        assert gate.reason == ""


class TestGateRegistry:
    """Test GateRegistry operations."""

    def test_open_creates_gate(self, tmp_project):
        """open() creates a gate in the registry."""
        registry = GateRegistry()
        gate = Gate(name="approve_sprint_plan", artifact_path="sprint-plan.md")
        registry.open(gate)
        assert registry.is_open("approve_sprint_plan")

    def test_decide_sets_decision(self, tmp_project):
        """decide() records the decision."""
        registry = GateRegistry()
        gate = Gate(name="approve_sprint_plan", artifact_path="sprint-plan.md")
        registry.open(gate)
        registry.decide("approve_sprint_plan", "approved")
        assert registry.is_open("approve_sprint_plan") is False

    def test_decide_sets_rejection_reason(self, tmp_project):
        """decide() stores the rejection reason when rejected."""
        registry = GateRegistry()
        gate = Gate(name="approve_sprint_plan", artifact_path="sprint-plan.md")
        registry.open(gate)
        gate.reason = "Not ready"
        registry.decide("approve_sprint_plan", "rejected")
        reason = registry.get_rejection_reason("approve_sprint_plan")
        assert reason == "Not ready"

    def test_wait_returns_decision_when_already_decided(self, tmp_project):
        """wait() returns immediately if gate was already decided."""
        registry = GateRegistry()
        gate = Gate(name="approve_sprint_plan", artifact_path="sprint-plan.md")
        registry.open(gate)
        registry.decide("approve_sprint_plan", "approved")
        decision = registry.wait("approve_sprint_plan", timeout_sec=0)
        assert decision == "approved"

    def test_wait_times_out_when_no_decision(self, tmp_project):
        """wait() raises GateTimeout when timeout > 0 and no decision."""
        registry = GateRegistry()
        gate = Gate(name="approve_review", artifact_path="review.md")
        registry.open(gate)
        with pytest.raises(GateTimeout):
            registry.wait("approve_review", timeout_sec=1)

    def test_wait_returns_rejected(self, tmp_project):
        """wait() returns 'rejected' when gate was decided rejected."""
        registry = GateRegistry()
        gate = Gate(name="approve_sprint_plan", artifact_path="sprint-plan.md")
        registry.open(gate)
        registry.decide("approve_sprint_plan", "rejected")
        decision = registry.wait("approve_sprint_plan", timeout_sec=0)
        assert decision == "rejected"

    def test_is_open_returns_false_after_decide(self, tmp_project):
        """is_open() returns False after the gate is decided."""
        registry = GateRegistry()
        gate = Gate(name="approve_sprint_plan", artifact_path="sprint-plan.md")
        registry.open(gate)
        assert registry.is_open("approve_sprint_plan") is True
        registry.decide("approve_sprint_plan", "approved")
        assert registry.is_open("approve_sprint_plan") is False

    def test_get_rejection_reason_returns_empty_for_approved(self, tmp_project):
        """get_rejection_reason() returns '' for approved gates."""
        registry = GateRegistry()
        gate = Gate(name="approve_sprint_plan", artifact_path="sprint-plan.md")
        registry.open(gate)
        registry.decide("approve_sprint_plan", "approved")
        assert registry.get_rejection_reason("approve_sprint_plan") == ""

    def test_get_rejection_reason_returns_empty_for_unknown_gate(self, tmp_project):
        """get_rejection_reason() returns '' for unknown gates."""
        registry = GateRegistry()
        assert registry.get_rejection_reason("nonexistent_gate") == ""

    def test_concurrent_decide_and_wait(self, tmp_project):
        """Thread-safe: decide() unblocks a waiting wait()."""
        registry = GateRegistry()
        gate = Gate(name="approve_sprint_plan", artifact_path="sprint-plan.md")
        registry.open(gate)

        decision_holder = []
        error_holder = []

        def waiter():
            try:
                decision = registry.wait("approve_sprint_plan", timeout_sec=5)
                decision_holder.append(decision)
            except Exception as e:
                error_holder.append(e)

        thread = threading.Thread(target=waiter)
        thread.start()

        time.sleep(0.2)  # Let waiter start
        registry.decide("approve_sprint_plan", "approved")

        thread.join(timeout=5)
        assert len(error_holder) == 0
        assert decision_holder == ["approved"]
