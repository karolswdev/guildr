"""H2.1 — programmatic rehearsal of the full PWA-gated dry-run path.

Drives the same code path a human would hit from the PWA: ``start_run``
launches the engine on a background thread with ``require_human_approval=True``;
gate decisions come in over HTTP. Verifies:

- every `approve_*` gate that opens gets decided through the HTTP route
  (not by direct registry access) — proving H1.1+H1.2+H1.3 are wired
- ``raw-io.jsonl`` captures at least one record per expected role — proving
  H0 wiring survives a gated run
- the run finishes cleanly (``run_complete`` event, not ``run_error``)

This is the scriptable half of H2.1. The manual PWA walk-through is a
separate exercise; this test is the regression guard that survives in CI.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from orchestrator.lib.gates import GateRegistryStore
from orchestrator.lib.raw_io import raw_io_path
from web.backend.app import create_app
from web.backend.routes.stream import SimpleEventBus
from web.backend.runner import _run_orchestrator


_EXPECTED_GATES = ("approve_sprint_plan", "approve_review")
# Roles that land a row in raw-io.jsonl during the dry-run pipeline.
# Coder / Reviewer / Deployer / Tester ride an opencode SessionRunner after
# H6.3a–d; each emits via ``emit_session_audit`` which mirrors the opencode
# session into raw-io.jsonl + usage.jsonl. Architect still uses the direct
# LLMClient path.
_EXPECTED_ROLES = {"architect", "judge", "coder", "tester", "reviewer", "deployer"}


def _wait_for(predicate, timeout: float = 30.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.fixture
def fresh_store() -> GateRegistryStore:
    return GateRegistryStore()


@pytest.fixture
def client(fresh_store: GateRegistryStore, monkeypatch: pytest.MonkeyPatch):
    # TestClient's X-Client-Host is "testclient" which the LAN-only
    # middleware rejects; short-circuit via the public-expose flag.
    monkeypatch.setenv("ORCHESTRATOR_EXPOSE_PUBLIC", "1")
    with patch("web.backend.routes.gates.get_gate_store", return_value=fresh_store):
        with TestClient(create_app()) as c:
            yield c


def test_pwa_gated_dry_run_rehearsal(
    tmp_path: Path, fresh_store: GateRegistryStore, client: TestClient
) -> None:
    project_id = "h2-1-rehearsal"
    project_dir = tmp_path / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "qwendea.md").write_text(
        "# JSON Formatter CLI\n\n"
        "Build a one-command Python CLI that reads JSON on stdin and "
        "prints it back with sorted keys and two-space indent.\n"
    )

    registry = fresh_store.ensure(project_id)
    bus = SimpleEventBus(project_id=project_id)
    events: list[dict] = bus.subscribe()

    def run() -> None:
        _run_orchestrator(
            project_id,
            project_dir,
            bus,
            dry_run=True,
            llama_url="http://unused-in-dry-run",
            require_human_approval=True,
        )

    # Plumb the same per-project registry the runner would pull, so the
    # HTTP decide POST and the engine's wait() see the same Gate instances.
    with patch("web.backend.runner.get_gate_store") as runner_store:
        runner_store.return_value.ensure.return_value = registry
        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        approved: list[str] = []
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline and thread.is_alive():
            pending = [
                g.name
                for g in registry.list_gates()
                if g.decision == "pending" and g.name not in approved
            ]
            if not pending:
                time.sleep(0.05)
                continue
            for name in pending:
                resp = client.post(
                    f"/api/projects/{project_id}/gates/{name}/decide",
                    json={"decision": "approved", "reason": "h2.1 rehearsal"},
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["gate"]["status"] == "approved"
                approved.append(name)

        thread.join(timeout=10.0)

    assert not thread.is_alive(), "engine thread did not finish within 70s"

    # All expected gates were decided through HTTP.
    assert set(_EXPECTED_GATES).issubset(set(approved)), (
        f"expected gates {_EXPECTED_GATES} to be approved via HTTP, got {approved}"
    )

    # Run finished cleanly. SimpleEventBus.subscribe() returns a list of
    # SSE wire-format strings (``data: {...}\\n\\n``); parse the JSON payload.
    parsed = []
    for frame in events:
        for line in frame.splitlines():
            if line.startswith("data: "):
                try:
                    parsed.append(json.loads(line[len("data: "):]))
                except json.JSONDecodeError:
                    pass
    event_types = [e.get("type") for e in parsed]
    assert "run_complete" in event_types, (
        f"run did not complete cleanly. events observed: {event_types}"
    )
    assert "run_error" not in event_types, (
        f"run surfaced an error. events: {[e for e in parsed if e.get('type') == 'run_error']}"
    )

    # Raw I/O capture survived the gated run.
    path = raw_io_path(project_dir)
    assert path.exists(), "raw-io.jsonl was not written — H0 capture regressed under gated run"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert records, "raw-io.jsonl is empty"

    roles_seen = {r["role"] for r in records}
    assert _EXPECTED_ROLES.issubset(roles_seen), (
        f"raw-io.jsonl missing roles. got {roles_seen}, expected superset of {_EXPECTED_ROLES}"
    )

    request_ids = [r["request_id"] for r in records]
    assert len(set(request_ids)) == len(request_ids), "raw-io request_ids are not unique"
