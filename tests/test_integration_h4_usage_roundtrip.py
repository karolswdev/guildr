"""H4.3 — end-to-end cost/usage roundtrip guardrail.

Runs the full dry-run pipeline and asserts:

- every ``request_id`` in raw-io.jsonl appears as a ``call_id`` in usage.jsonl
  (bijection on the join key for reconciled calls).
- ``rollup(project_dir).totals`` equals the sum of the underlying records
  (no drift between the durable files and the summary).

If this regresses, "how much did this run cost" becomes un-answerable
without manually replaying the event bus.
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.cli.run import _build_dry_run_llm
from orchestrator.engine import Orchestrator
from orchestrator.lib.config import Config
from orchestrator.lib.raw_io import raw_io_path
from orchestrator.lib.usage_summary import rollup
from orchestrator.lib.usage_writer import usage_path


def test_usage_and_raw_io_reconcile_end_to_end(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "qwendea.md").write_text(
        "# Tiny CLI\n\nBuild a one-command CLI that prints hello.\n"
    )

    config = Config(
        llama_server_url="http://unused-in-dry-run",
        project_dir=project_dir,
        require_human_approval=False,
        max_retries=2,
        architect_max_passes=2,
    )
    Orchestrator(config=config, fake_llm=_build_dry_run_llm()).run()

    raw_path = raw_io_path(project_dir)
    u_path = usage_path(project_dir)
    assert raw_path.exists(), "raw-io.jsonl missing"
    assert u_path.exists(), "usage.jsonl missing — H4.1 regression"

    raw_records = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line]
    usage_records = [json.loads(line) for line in u_path.read_text(encoding="utf-8").splitlines() if line]

    raw_ids = {r["request_id"] for r in raw_records}
    usage_ids = {u["call_id"] for u in usage_records}

    # Every raw-io entry must have a matching usage entry. The reverse is
    # not required (persona_forum/quiz emit usage without a raw-io pair),
    # but the raw→usage direction is the contract H4 enforces.
    missing = raw_ids - usage_ids
    assert not missing, f"raw-io entries without a usage match: {missing}"

    # Rollup totals must equal the sum of the underlying raw-io records
    # for reconciled ids.
    reconciled_ids = raw_ids & usage_ids
    expected_prompt = sum(
        int(r["usage"].get("prompt_tokens", 0) or 0)
        for r in raw_records if r["request_id"] in reconciled_ids
    )
    expected_completion = sum(
        int(r["usage"].get("completion_tokens", 0) or 0)
        for r in raw_records if r["request_id"] in reconciled_ids
    )
    expected_reasoning = sum(
        int(r["usage"].get("reasoning_tokens", 0) or 0)
        for r in raw_records if r["request_id"] in reconciled_ids
    )

    summary = rollup(project_dir)
    assert summary.totals.prompt_tokens == expected_prompt
    assert summary.totals.completion_tokens == expected_completion
    assert summary.totals.reasoning_tokens == expected_reasoning
    assert summary.totals.total_tokens == expected_prompt + expected_completion + expected_reasoning
    assert summary.totals.call_count == len(reconciled_ids)

    # Rollup cost equals the sum of effective_cost across reconciled usage records.
    usage_by_id = {u["call_id"]: u for u in usage_records}
    expected_cost = 0.0
    for call_id in reconciled_ids:
        cost_block = usage_by_id[call_id].get("cost") or {}
        effective = cost_block.get("effective_cost")
        if effective is None:
            effective = usage_by_id[call_id].get("cost_usd")
        expected_cost += float(effective or 0.0)
    assert round(summary.totals.cost_usd, 6) == round(expected_cost, 6)

    # Per-role totals should partition the grand total.
    per_role_prompt = sum(t.prompt_tokens for t in summary.per_role.values())
    per_role_completion = sum(t.completion_tokens for t in summary.per_role.values())
    assert per_role_prompt == summary.totals.prompt_tokens
    assert per_role_completion == summary.totals.completion_tokens
