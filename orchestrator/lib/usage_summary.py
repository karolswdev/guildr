"""Per-run cost + token rollup from raw-io.jsonl and usage.jsonl.

Joins the two durable audit trails on the shared call id to answer
"how much did this run cost, per role and per phase." Calls that appear
in only one file are surfaced in ``orphans`` instead of being silently
dropped — those are the bugs this phase is here to catch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.lib.raw_io import raw_io_path
from orchestrator.lib.usage_writer import usage_path


@dataclass
class Totals:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    call_count: int = 0


@dataclass
class RunSummary:
    per_role: dict[str, Totals] = field(default_factory=dict)
    per_phase: dict[str, Totals] = field(default_factory=dict)
    totals: Totals = field(default_factory=Totals)
    orphans: dict[str, list[str]] = field(
        default_factory=lambda: {"raw_io_only": [], "usage_only": []}
    )


def rollup(project_dir: Path) -> RunSummary:
    """Read raw-io + usage and return a joined per-run summary."""
    raw = _load_by_id(raw_io_path(project_dir), id_key="request_id")
    usage = _load_by_id(usage_path(project_dir), id_key="call_id")

    summary = RunSummary()
    summary.orphans["raw_io_only"] = sorted(set(raw) - set(usage))
    summary.orphans["usage_only"] = sorted(set(usage) - set(raw))

    for call_id in set(raw) & set(usage):
        raw_record = raw[call_id]
        usage_record = usage[call_id]
        role = raw_record.get("role") or usage_record.get("role") or "unknown"
        phase = raw_record.get("phase") or usage_record.get("step") or "unknown"

        raw_usage = raw_record.get("usage") or {}
        prompt = int(raw_usage.get("prompt_tokens", 0) or 0)
        completion = int(raw_usage.get("completion_tokens", 0) or 0)
        reasoning = int(raw_usage.get("reasoning_tokens", 0) or 0)
        latency = float(raw_record.get("latency_ms", 0.0) or 0.0)

        cost_block = usage_record.get("cost") or {}
        effective = cost_block.get("effective_cost")
        if effective is None:
            effective = usage_record.get("cost_usd")
        cost = float(effective or 0.0)

        _accumulate(summary.per_role.setdefault(role, Totals()),
                    prompt, completion, reasoning, cost, latency)
        _accumulate(summary.per_phase.setdefault(phase, Totals()),
                    prompt, completion, reasoning, cost, latency)
        _accumulate(summary.totals, prompt, completion, reasoning, cost, latency)

    return summary


def _accumulate(
    bucket: Totals,
    prompt: int,
    completion: int,
    reasoning: int,
    cost: float,
    latency: float,
) -> None:
    bucket.prompt_tokens += prompt
    bucket.completion_tokens += completion
    bucket.reasoning_tokens += reasoning
    bucket.total_tokens += prompt + completion + reasoning
    bucket.cost_usd += cost
    bucket.latency_ms += latency
    bucket.call_count += 1


def _load_by_id(path: Path, *, id_key: str) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = record.get(id_key)
        if isinstance(key, str) and key:
            records[key] = record
    return records
