"""Unit tests for the cost/token rollup."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.lib.raw_io import raw_io_path
from orchestrator.lib.usage_summary import rollup
from orchestrator.lib.usage_writer import usage_path


def _raw(call_id: str, *, role: str, phase: str, prompt: int, completion: int,
         reasoning: int = 0, latency_ms: float = 10.0) -> dict:
    return {
        "request_id": call_id,
        "role": role,
        "phase": phase,
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "reasoning_tokens": reasoning,
        },
        "latency_ms": latency_ms,
    }


def _usage(call_id: str, *, role: str, step: str, cost: float) -> dict:
    return {
        "call_id": call_id,
        "role": role,
        "step": step,
        "cost": {"effective_cost": cost, "currency": "USD"},
        "cost_usd": cost,
    }


def _seed(project_dir: Path, raw_records: list[dict], usage_records: list[dict]) -> None:
    raw_path = raw_io_path(project_dir)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("".join(json.dumps(r) + "\n" for r in raw_records), encoding="utf-8")
    u_path = usage_path(project_dir)
    u_path.write_text("".join(json.dumps(r) + "\n" for r in usage_records), encoding="utf-8")


def test_rollup_joins_on_shared_id(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        raw_records=[
            _raw("id-a", role="coder", phase="implementation", prompt=10, completion=20),
            _raw("id-b", role="reviewer", phase="review", prompt=5, completion=7, reasoning=3),
        ],
        usage_records=[
            _usage("id-a", role="coder", step="implementation", cost=0.01),
            _usage("id-b", role="reviewer", step="review", cost=0.02),
        ],
    )

    summary = rollup(tmp_path)

    assert summary.totals.call_count == 2
    assert summary.totals.prompt_tokens == 15
    assert summary.totals.completion_tokens == 27
    assert summary.totals.reasoning_tokens == 3
    assert summary.totals.total_tokens == 45
    assert summary.totals.cost_usd == 0.03
    assert summary.orphans == {"raw_io_only": [], "usage_only": []}


def test_rollup_surfaces_orphans(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        raw_records=[_raw("raw-only", role="coder", phase="implementation", prompt=1, completion=1)],
        usage_records=[_usage("usage-only", role="coder", step="implementation", cost=0.1)],
    )

    summary = rollup(tmp_path)

    assert summary.totals.call_count == 0
    assert summary.orphans["raw_io_only"] == ["raw-only"]
    assert summary.orphans["usage_only"] == ["usage-only"]


def test_rollup_per_role_and_phase(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        raw_records=[
            _raw("a", role="coder", phase="implementation", prompt=10, completion=10),
            _raw("b", role="coder", phase="implementation", prompt=5, completion=5),
            _raw("c", role="reviewer", phase="review", prompt=3, completion=3),
        ],
        usage_records=[
            _usage("a", role="coder", step="implementation", cost=0.01),
            _usage("b", role="coder", step="implementation", cost=0.02),
            _usage("c", role="reviewer", step="review", cost=0.05),
        ],
    )

    summary = rollup(tmp_path)

    assert summary.per_role["coder"].call_count == 2
    assert summary.per_role["coder"].total_tokens == 30
    assert round(summary.per_role["coder"].cost_usd, 6) == 0.03
    assert summary.per_phase["implementation"].call_count == 2
    assert summary.per_phase["review"].call_count == 1


def test_rollup_empty_when_files_missing(tmp_path: Path) -> None:
    summary = rollup(tmp_path)
    assert summary.totals.call_count == 0
    assert summary.orphans == {"raw_io_only": [], "usage_only": []}
