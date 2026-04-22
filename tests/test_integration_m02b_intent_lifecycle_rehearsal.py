"""M02B Step 7 — end-to-end intent lifecycle rehearsal."""

from __future__ import annotations

import asyncio
import json
import subprocess
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from orchestrator.engine import Orchestrator
from orchestrator.lib.config import Config
from web.backend.app import create_app
from web.backend.routes.stream import event_log_path


ROOT = Path(__file__).resolve().parents[1]
ENGINE_TS = ROOT / "web" / "frontend" / "src" / "game" / "EventEngine.ts"


class CaptureEvents:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, **fields) -> None:
        self.events.append({"type": event_type, **fields})


def _bundle_event_engine(tmp_path: Path) -> Path:
    bundle = tmp_path / "event-engine.mjs"
    subprocess.run(
        [
            "npx",
            "--yes",
            "esbuild@0.24.0",
            str(ENGINE_TS),
            "--bundle",
            "--format=esm",
            "--platform=node",
            "--target=es2020",
            f"--outfile={bundle}",
            "--log-level=warning",
        ],
        cwd=ROOT,
        check=True,
    )
    return bundle


def _assert_event_engine_replay(bundle: Path, events: list[dict]) -> None:
    subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            textwrap.dedent(
                """
                import assert from 'node:assert/strict';
                import { EventEngine } from '__BUNDLE__';
                const events = __EVENTS__;
                const engine = new EventEngine('demo', [
                  { id: 'memory_refresh', title: 'Memory', type: 'phase', handler: 'memory_refresh', enabled: true },
                  { id: 'persona_forum', title: 'Team', type: 'phase', handler: 'persona_forum', enabled: true },
                ]);
                engine.loadHistory(events);
                const live = engine.snapshot();
                assert.equal(live.nextStepPacket.step, 'persona_forum');
                assert.equal(live.ignoredIntents['client-route'].reason, 'target_step_passed');
                assert.equal(live.pendingIntents['client-global'].status, 'queued');
                assert.deepEqual(
                  live.nextStepPacket.queuedIntents.map((intent) => intent.client_intent_id),
                  ['client-global'],
                );

                const refreshedPacketIndex = events.findIndex((event) => (
                  event.type === 'next_step_packet_created' &&
                  event.packet &&
                  event.packet.step === 'memory_refresh' &&
                  event.packet.queued_intents &&
                  event.packet.queued_intents.length === 2
                ));
                engine.scrubTo(refreshedPacketIndex);
                const replayPacket = engine.snapshot().nextStepPacket;
                assert.equal(replayPacket.step, 'memory_refresh');
                assert.deepEqual(
                  replayPacket.queuedIntents.map((intent) => intent.client_intent_id),
                  ['client-route', 'client-global'],
                );
                assert.equal(Object.keys(engine.snapshot().ignoredIntents).length, 0);
                """
            )
            .replace("__BUNDLE__", bundle.as_posix())
            .replace("__EVENTS__", json.dumps(events)),
        ],
        cwd=ROOT,
        check=True,
    )


async def _post_intent(app: FastAPI, project_id: str) -> dict:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        targeted = await client.post(
            f"/api/projects/{project_id}/intents",
            json={
                "kind": "interject",
                "atom_id": "memory_refresh",
                "payload": {"instruction": "Please show this in replay."},
                "client_intent_id": "client-route",
            },
        )
        global_intent = await client.post(
            f"/api/projects/{project_id}/intents",
            json={
                "kind": "interject",
                "atom_id": None,
                "payload": {"instruction": "Global note for the next packet."},
                "client_intent_id": "client-global",
            },
        )
    assert targeted.status_code == 200
    assert global_intent.status_code == 200
    return targeted.json()


def test_project_intent_to_engine_outcome_to_frontend_replay(tmp_path: Path) -> None:
    from web.backend.routes.projects import ProjectStore

    store = ProjectStore(base_dir=tmp_path)
    project = store.create("Demo")
    events = CaptureEvents()
    config = Config(
        llama_server_url="http://127.0.0.1:8080",
        project_dir=project.project_dir,
        max_retries=1,
    )
    orchestrator = Orchestrator(config=config, events=events, git_ops=MagicMock())
    orchestrator._validate = MagicMock(return_value=True)

    with (
        patch("web.backend.routes.projects.get_store", return_value=store),
        patch("web.backend.routes.intents.get_store", return_value=store),
        patch("web.backend.routes.stream._projects_base", return_value=tmp_path),
    ):
        response = asyncio.run(_post_intent(create_app(), project.id))
        event_log = event_log_path(project.id)
        backend_events = [
            json.loads(line)
            for line in event_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    assert response["accepted"] is True
    assert response["client_intent_id"] == "client-route"
    assert [event["type"] for event in backend_events] == [
        "operator_intent",
        "next_step_packet_created",
        "narrator_sidecar_requested",
        "operator_intent",
        "next_step_packet_created",
        "narrator_sidecar_requested",
    ]
    assert backend_events[0]["client_intent_id"] == "client-route"
    assert backend_events[1]["packet"]["step"] == "memory_refresh"
    assert [row["client_intent_id"] for row in backend_events[1]["packet"]["queued_intents"]] == [
        "client-route"
    ]
    assert backend_events[2]["trigger_event_id"] == backend_events[0]["event_id"]
    assert backend_events[2]["packet_id"] == backend_events[1]["packet_id"]
    assert backend_events[3]["client_intent_id"] == "client-global"
    assert [row["client_intent_id"] for row in backend_events[4]["packet"]["queued_intents"]] == [
        "client-route",
        "client-global",
    ]
    assert backend_events[5]["trigger_event_id"] == backend_events[3]["event_id"]
    assert backend_events[5]["packet_id"] == backend_events[4]["packet_id"]

    with patch("orchestrator.lib.memory_palace.resolve_command", return_value=["mempalace"]):
        orchestrator._run_phase("memory_refresh", lambda: None)

    packet_events = [event for event in events.events if event["type"] == "next_step_packet_created"]
    assert [event["packet"]["step"] for event in packet_events] == ["memory_refresh", "persona_forum"]
    assert [row["client_intent_id"] for row in packet_events[0]["packet"]["queued_intents"]] == [
        "client-route",
        "client-global",
    ]
    assert [row["client_intent_id"] for row in packet_events[1]["packet"]["queued_intents"]] == ["client-global"]

    ignored = [event for event in events.events if event["type"] == "operator_intent_ignored"]
    assert len(ignored) == 1
    assert ignored[0]["project_id"] == project.project_dir.name
    assert ignored[0]["client_intent_id"] == "client-route"
    assert ignored[0]["intent_event_id"] == backend_events[0]["event_id"]
    assert ignored[0]["kind"] == "interject"
    assert ignored[0]["atom_id"] == "memory_refresh"
    assert ignored[0]["step"] == "memory_refresh"
    assert ignored[0]["reason"] == "target_step_passed"
    assert "artifact:.orchestrator/control/intents.jsonl" in ignored[0]["source_refs"]

    ledger = [*backend_events, *events.events]
    _assert_event_engine_replay(_bundle_event_engine(tmp_path), ledger)
