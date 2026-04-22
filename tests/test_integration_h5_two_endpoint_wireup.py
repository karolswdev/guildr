"""H5.3 — end-to-end two-endpoint pool wire-up.

Builds an ``UpstreamPool`` with two endpoints, each wrapped around the
same content-aware fake the dry-run CLI uses, then drives the full
Orchestrator pipeline through the sync pool facade. This is the only
integration test that exercises the live-path shape without hitting a
real llama-server: ``Orchestrator(pool=...)`` → ``SyncPoolClient`` →
``asyncio.run(pool.chat(...))`` → endpoint client → response.

Guards the invariant H5 was filed to defend — a role's sync
``self.llm.chat(...)`` reaches the pool without a coroutine leak, and
every call lands one row in ``pool.jsonl`` tagged with the endpoint
label the routing table declared.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator.cli.run import _build_dry_run_llm
from orchestrator.engine import Orchestrator
from orchestrator.lib.config import Config
from orchestrator.lib.endpoints import RouteEntry
from orchestrator.lib.pool import Endpoint, UpstreamPool
from orchestrator.lib.pool_log import pool_log_path
from orchestrator.roles.architect_dryrun import (
    DryRunArchitectRunner,
    DryRunJudgeRunner,
)
from orchestrator.roles.coder_dryrun import DryRunCoderRunner
from orchestrator.roles.deployer_dryrun import DryRunDeployerRunner
from orchestrator.roles.tester_dryrun import DryRunTesterRunner
from orchestrator.roles.reviewer_dryrun import DryRunReviewerRunner


class _EndpointFake:
    """LLMClient-shaped wrapper around the content-aware dry-run fake.

    Reusing ``_build_dry_run_llm`` keeps every role's response shape
    (plan markdown, judge JSON, coder JSON, ...) correct so the engine
    advances through every phase — the test can then assert on
    ``pool.jsonl`` rather than chasing role-specific fixtures.
    """

    def __init__(self, label: str, default_model: str) -> None:
        from orchestrator.lib.llm import LLMResponse
        from orchestrator.lib.llm_fake import FakeLLMClient
        self.label = label
        self.default_model = default_model
        self._inner = FakeLLMClient(responses={
            "default": LLMResponse(
                content="ok",
                reasoning="",
                prompt_tokens=1,
                completion_tokens=1,
                reasoning_tokens=0,
                finish_reason="stop",
            )
        })
        self.call_count = 0

    def chat(self, messages: list[dict[str, Any]], **kw: Any) -> Any:
        self.call_count += 1
        return self._inner.chat(messages, **kw)

    def health(self) -> bool:
        return True


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    pd = tmp_path / "proj"
    pd.mkdir()
    (pd / "qwendea.md").write_text(
        "# Project: Tiny CLI\n\nBuild a one-command CLI that prints hello.\n"
    )
    return pd


def test_two_endpoint_pool_drives_full_pipeline(project_dir: Path) -> None:
    """Engine + pool + sync facade reach every role and log each landing."""
    big = _EndpointFake("big-model", default_model="qwen3-coder:30b")
    small = _EndpointFake("small-model", default_model="qwen3-coder:3b")

    pool = UpstreamPool(
        endpoints=[
            Endpoint(label="big-model", client=big),
            Endpoint(label="small-model", client=small),
        ],
        routing={
            "architect": [RouteEntry(endpoint="big-model")],
            "judge": [RouteEntry(endpoint="small-model")],
            "coder": [RouteEntry(endpoint="big-model", model="qwen3-coder:30b-override")],
            "tester": [RouteEntry(endpoint="small-model")],
            "reviewer": [RouteEntry(endpoint="small-model")],
            "deployer": [RouteEntry(endpoint="small-model")],
        },
    )

    cfg = Config(
        llama_server_url="http://unused",
        project_dir=project_dir,
        require_human_approval=False,
        max_retries=2,
        architect_max_passes=2,
    )

    # Coder no longer calls the pool (H6.3a — runs via opencode session).
    # Inject a dry-run SessionRunner so the pipeline can still reach the
    # tester/reviewer/deployer phases that *do* still ride the pool.
    from orchestrator.lib.state import State
    state_for_runners = State(project_dir)
    runners = {
        "architect": DryRunArchitectRunner(state_for_runners),
        "judge": DryRunJudgeRunner(state_for_runners),
        "coder": DryRunCoderRunner(state_for_runners),
        "tester": DryRunTesterRunner(state_for_runners),
        "reviewer": DryRunReviewerRunner(state_for_runners),
        "deployer": DryRunDeployerRunner(state_for_runners),
    }
    Orchestrator(config=cfg, pool=pool, session_runners=runners).run()

    # Pipeline advanced through every phase.
    for required in ("sprint-plan.md", "TEST_REPORT.md", "REVIEW.md", "DEPLOY.md"):
        assert (project_dir / required).exists(), f"{required} missing — pipeline halted"

    # After H6.3a–e every SDLC-shaped role rides an opencode SessionRunner,
    # so no role in the SDLC pipeline lands on the pool in dry-run. The
    # remaining pool traffic comes from pre-phase roles (persona_forum,
    # memory_refresh, guru_escalation) when they're enabled. Guard the
    # invariant that the H6-migrated roles stay off the pool, rather than
    # asserting a role still reaches it.
    decisions = [
        json.loads(line)
        for line in pool_log_path(project_dir).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_role: dict[str, list[dict]] = {}
    for d in decisions:
        by_role.setdefault(d["role"], []).append(d)

    for migrated in ("architect", "judge", "coder", "tester", "reviewer", "deployer"):
        assert migrated not in by_role, (
            f"{migrated} was expected to bypass the pool (opencode session, H6.3), "
            f"but appeared in pool.jsonl"
        )


def test_fallback_when_preferred_endpoint_raises(project_dir: Path) -> None:
    """When the preferred endpoint raises ConnectionError, the pool falls
    back to the next route entry and records ``fell_back=True`` in
    pool.jsonl. Exercised via ``SyncPoolClient`` directly now that every
    SDLC role rides an opencode SessionRunner (H6.3a–e) and no longer
    reaches the pool through ``_llm_for``.
    """
    from orchestrator.lib.sync_pool import SyncPoolClient

    class _FlakyClient(_EndpointFake):
        def __init__(self, label: str, default_model: str) -> None:
            super().__init__(label, default_model)
            self.raised = 0

        def chat(self, messages: list[dict[str, Any]], **kw: Any) -> Any:
            self.raised += 1
            raise ConnectionError(f"{self.label} down")

    flaky = _FlakyClient("flaky", default_model="any")
    healthy = _EndpointFake("healthy", default_model="any")
    pool = UpstreamPool(
        endpoints=[
            Endpoint(label="flaky", client=flaky),
            Endpoint(label="healthy", client=healthy),
        ],
        routing={
            "persona_forum": [
                RouteEntry(endpoint="flaky"),
                RouteEntry(endpoint="healthy"),
            ],
        },
    )

    client = SyncPoolClient(pool, "persona_forum", project_dir=project_dir)
    client.chat([{"role": "user", "content": "hi"}])

    decisions = [
        json.loads(line)
        for line in pool_log_path(project_dir).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    routed = [d for d in decisions if d.get("chosen_endpoint") is not None]
    assert routed, "no routed decisions landed in pool.jsonl"

    first = routed[0]
    assert first["fell_back"] is True
    assert first["chosen_endpoint"] == "healthy"
    assert first["attempted_endpoints"][0] == "flaky"
    assert flaky.raised >= 1
    assert healthy.call_count >= 1
