"""End-to-end proof that POST /decide unblocks a waiting engine.

The engine's ``_gate()`` opens a gate on the shared ``GateRegistry`` and
blocks in ``wait()``. A POST to the HTTP decide route must resolve the
same registry and unblock the engine thread. If these tests fail, the
"intervene" pillar is broken — the PWA gate UI is cosmetic again.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from orchestrator.engine import Orchestrator, PhaseFailure
from orchestrator.lib.config import Config
from orchestrator.lib.gates import GateRegistryStore
from web.backend.app import create_app


@pytest.fixture
def fresh_store() -> GateRegistryStore:
    return GateRegistryStore()


@pytest.fixture
def client(fresh_store: GateRegistryStore, monkeypatch):
    # TestClient sets request.client.host="testclient", which the LanOnly
    # middleware rejects as non-RFC1918. In-process tests are inherently
    # local, so flip the public-expose flag to short-circuit the check.
    monkeypatch.setenv("ORCHESTRATOR_EXPOSE_PUBLIC", "1")
    with patch("web.backend.routes.gates.get_gate_store", return_value=fresh_store):
        with TestClient(create_app()) as c:
            yield c


def _make_orchestrator(project_dir: Path, registry) -> Orchestrator:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "qwendea.md").write_text("# test\n")
    config = Config(
        llama_server_url="http://unused",
        project_dir=project_dir,
        require_human_approval=True,
    )
    return Orchestrator(config=config, gate_registry=registry)


def _wait_open(registry, name: str, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if registry.is_open(name):
            return True
        time.sleep(0.02)
    return False


def test_posted_approval_unblocks_waiting_engine(
    tmp_path: Path, fresh_store: GateRegistryStore, client: TestClient
) -> None:
    project_id = "it-approve"
    registry = fresh_store.ensure(project_id)
    orch = _make_orchestrator(tmp_path / project_id, registry)

    errors: list[BaseException] = []
    done = threading.Event()

    def run_gate() -> None:
        try:
            orch._gate("approve_sprint_plan")
            done.set()
        except BaseException as e:  # noqa: BLE001 — capture everything for the assertion
            errors.append(e)

    t = threading.Thread(target=run_gate, daemon=True)
    t.start()

    assert _wait_open(registry, "approve_sprint_plan"), "engine never opened the gate"

    resp = client.post(
        f"/api/projects/{project_id}/gates/approve_sprint_plan/decide",
        json={"decision": "approved", "reason": "lgtm"},
    )
    assert resp.status_code == 200
    assert resp.json()["gate"]["status"] == "approved"

    t.join(timeout=3.0)
    assert not t.is_alive(), "engine thread did not unblock after HTTP approval"
    assert errors == []
    assert done.is_set()
    assert orch.state.gates_approved.get("approve_sprint_plan") is True


def test_posted_rejection_aborts_engine_phase_with_reason(
    tmp_path: Path, fresh_store: GateRegistryStore, client: TestClient
) -> None:
    project_id = "it-reject"
    registry = fresh_store.ensure(project_id)
    orch = _make_orchestrator(tmp_path / project_id, registry)

    captured: dict[str, BaseException] = {}

    def run_gate() -> None:
        try:
            orch._gate("approve_sprint_plan")
        except BaseException as e:  # noqa: BLE001
            captured["err"] = e

    t = threading.Thread(target=run_gate, daemon=True)
    t.start()

    assert _wait_open(registry, "approve_sprint_plan"), "engine never opened the gate"

    resp = client.post(
        f"/api/projects/{project_id}/gates/approve_sprint_plan/decide",
        json={"decision": "rejected", "reason": "plan too thin"},
    )
    assert resp.status_code == 200

    t.join(timeout=3.0)
    assert not t.is_alive(), "engine thread did not unblock after HTTP rejection"

    err = captured.get("err")
    assert isinstance(err, PhaseFailure), f"expected PhaseFailure, got {type(err).__name__}"
    assert "plan too thin" in str(err)
    assert orch.state.gates_approved.get("approve_sprint_plan") is False


def test_runner_pulls_same_registry_store_as_routes() -> None:
    """Sanity check: runner and HTTP routes import the same store."""
    from web.backend.routes.gates import get_gate_store as routes_store
    from web.backend.runner import get_gate_store as runner_store

    assert routes_store() is runner_store()
