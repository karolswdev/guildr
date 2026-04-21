"""H0.3 — end-to-end guard that raw LLM I/O is captured on disk.

Runs the full dry-run pipeline with a unique sentinel embedded in both the
qwendea prompt and the fake LLM's reasoning trace, then asserts the
`.orchestrator/logs/raw-io.jsonl` file contains both halves of the
round-trip. If this test regresses, the "review" pillar is broken — the
audit trail is silent.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from orchestrator.cli.run import _build_dry_run_llm
from orchestrator.engine import Orchestrator
from orchestrator.lib.config import Config
from orchestrator.lib.raw_io import raw_io_path


_QWENDEA_SENTINEL = "QWENDEA-SENTINEL-a7f39c4"
_RESPONSE_SENTINEL = "RESPONSE-SENTINEL-b21e8d6"


def _sentinel_fake():
    inner = _build_dry_run_llm()
    inner_chat = inner.chat

    def chat(messages, **kw):
        response = inner_chat(messages, **kw)
        return replace(response, reasoning=f"{_RESPONSE_SENTINEL} // {response.reasoning}")

    inner.chat = chat  # type: ignore[assignment]
    return inner


def test_raw_io_captures_prompts_and_responses_end_to_end(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "qwendea.md").write_text(
        f"# Tiny CLI\n\n{_QWENDEA_SENTINEL}: build a one-command CLI that prints hello.\n"
    )

    config = Config(
        llama_server_url="http://unused-in-dry-run",
        project_dir=project_dir,
        require_human_approval=False,
        max_retries=2,
        architect_max_passes=2,
    )

    Orchestrator(config=config, fake_llm=_sentinel_fake()).run()

    path = raw_io_path(project_dir)
    assert path.exists(), "raw-io.jsonl was not written"

    raw = path.read_text(encoding="utf-8")
    assert _QWENDEA_SENTINEL in raw, (
        "prompt sentinel missing from raw-io.jsonl — qwendea.md content is not flowing into captured messages"
    )
    assert _RESPONSE_SENTINEL in raw, (
        "response sentinel missing from raw-io.jsonl — responses are not being captured"
    )

    records = [json.loads(line) for line in raw.splitlines() if line]
    assert len(records) > 0, "raw-io.jsonl has no records"

    roles_seen = {r["role"] for r in records}
    assert roles_seen & {"architect", "coder", "tester", "reviewer", "deployer"}, (
        f"no recognised orchestrator roles in raw-io.jsonl (got {roles_seen})"
    )

    request_ids = [r["request_id"] for r in records]
    assert len(set(request_ids)) == len(request_ids), "request_ids are not unique"

    prompt_hits = sum(1 for r in records if _QWENDEA_SENTINEL in json.dumps(r["messages"]))
    response_hits = sum(1 for r in records if _RESPONSE_SENTINEL in (r.get("reasoning_content") or ""))
    assert prompt_hits >= 1, "at least one captured record should carry qwendea prompt content"
    assert response_hits >= 1, "at least one captured record should carry response reasoning content"
