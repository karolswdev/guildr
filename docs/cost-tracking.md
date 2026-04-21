# Replayable Cost Tracking

## Purpose

Cost tracking is first-class orchestration state. It is not a dashboard
calculation bolted on after a run. Every model call, advisor call, local model
execution, retry, and escalation must emit usage facts into the durable event
ledger so live views and replay views show the same counters the operator saw
at that point in time.

The core rule: replay never recomputes historical cost from today's pricing.
Replay uses the cost events and pricing snapshots that were recorded during the
run.

## Cost Sources

Each usage record must declare its source:

- `provider_reported`: the provider returned token usage and a cost amount.
- `rate_card_estimate`: the system estimated cost from recorded tokens and a
  provider rate card snapshot.
- `local_estimate`: the system estimated local execution cost from configured
  machine rates, wall time, and throughput.
- `unknown`: usage occurred, but cost could not be determined.

The UI must always show source and confidence. A provider-reported hosted call
and a local llama estimate are not the same quality of evidence.

## Event Schema

Model and advisor calls emit a `usage_recorded` event.

```json
{
  "type": "usage_recorded",
  "ts": "2026-04-21T20:15:11.000Z",
  "project_id": "f7508af9776b",
  "run_id": "run-20260421-201501",
  "step": "architect",
  "atom_id": "architect",
  "role": "architect",
  "call_id": "llmcall-01HX",
  "provider_kind": "openai_compatible",
  "provider_name": "openrouter",
  "model": "qwen/qwen3-coder",
  "usage": {
    "input_tokens": 42112,
    "output_tokens": 6144,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0
  },
  "cost": {
    "currency": "USD",
    "provider_reported_cost": 0.184,
    "estimated_cost": 0.0,
    "effective_cost": 0.184,
    "source": "provider_reported",
    "confidence": "high",
    "rate_card_version": "openrouter-2026-04-21T20:00:00Z"
  },
  "runtime": {
    "wall_ms": 138221,
    "tokens_per_second": 44.4,
    "gpu_seconds": null,
    "estimated_energy_wh": null
  },
  "budget": {
    "run_budget_usd": 10.0,
    "phase_budget_usd": 2.0,
    "remaining_run_budget_usd": 7.816
  }
}
```

Fields may be `null` when unavailable, but the field family must remain stable
so replay and exports can read old runs without guessing.

## Provider Adapters

Every provider adapter must return a normalized `UsageRecord`.

Required normalized fields:

- Provider kind, provider name, model, call id, role, step, atom id.
- Input tokens and output tokens when available.
- Cache read/write tokens when available.
- Reasoning tokens when available.
- Provider-reported cost when available.
- Pricing snapshot id or rate-card version when an estimate is used.
- Wall time and throughput.
- Error or partial-usage state when a call fails after consuming tokens.

OpenAI-compatible and OpenRouter-style adapters must preserve any provider
returned usage or cost metadata. CLI adapters such as `claude` and `codex` must
capture what the CLI reports and fall back to estimates only when the CLI does
not expose exact usage.

## Local Model Cost

Local calls still have cost. They may not have a provider invoice, but they
consume machine time and may block scarce hardware.

Local estimates use project or machine config:

```json
{
  "local_cost_profile": {
    "machine_id": "mac-studio",
    "hourly_cost_usd": 0.42,
    "energy_cost_usd_per_kwh": 0.18,
    "gpu_hourly_cost_usd": 0.0,
    "default_source": "local_estimate"
  }
}
```

For local llama calls, effective cost may be computed from wall time, optional
GPU seconds, optional energy, and configured machine cost. The UI must label
this as an estimate, not an invoice.

## Budgets And Gates

Budgets are configurable at multiple levels:

- Project budget.
- Run budget.
- Phase budget.
- Provider budget.
- Escalation budget.
- Per-call hard cap.

Budget crossing emits events:

- `budget_warning`: soft threshold crossed.
- `budget_exceeded`: hard threshold crossed.
- `budget_gate_opened`: operator approval required to continue.
- `budget_gate_decided`: operator approved, rejected, or changed budget.

Budget gates must be resumable like other gates. The decision becomes part of
the event ledger and replay state.

## Replay Behavior

Replay builds cost state by folding events in order:

1. Start with zero totals.
2. Apply `usage_recorded` events.
3. Apply budget events and gate decisions.
4. Emit a `CostSnapshot` for each replay index.

`CostSnapshot` must include:

- Total effective run cost.
- Provider-reported total.
- Estimated total.
- Unknown-cost count.
- Cost by provider, model, role, phase, and atom.
- Token totals by input, output, cache, and reasoning.
- Budget remaining at that replay index.
- Current burn rate when enough recent events exist.

The replay viewer must show the snapshot as of the selected event index, not as
of now.

## PWA Requirements

Mission Control needs a compact cost HUD:

- Current run cost.
- Budget remaining.
- Current phase cost.
- Provider/model currently spending.
- Warning badge for estimated or unknown usage.
- Tap target for full economics panel.

The Three.js map should represent economics without clutter:

- Thin cost ring around atoms that have spent budget.
- Budget warning pulse on atoms approaching phase budget.
- Provider lanes or color hints in the focus panel, not all over the map.
- Replay timeline overlay that can switch from event density to cost density.

The full economics panel must support:

- Group by provider, model, phase, role, or atom.
- Filter local vs hosted calls.
- Inspect a single call payload without exposing secrets.
- Export a cost report with source/confidence labels.
- Compare estimated vs provider-reported totals.

## Artifacts

The event ledger is canonical, but long-lived summaries may also be written to:

- `.orchestrator/costs/run-summary.json`
- `.orchestrator/costs/provider-ledger.jsonl`
- `.orchestrator/costs/rate-cards/*.json`

These files are derived artifacts. If they disagree with `.orchestrator/events.jsonl`,
the event ledger wins.

## Acceptance Criteria

- Every LLM or advisor call emits exactly one `usage_recorded` event.
- Failed calls emit usage when the provider or CLI reports partial usage.
- Replay shows cost totals changing as the scrubber moves.
- Hosted provider costs are separated from local estimates.
- Unknown costs are counted and visible.
- Budget gates can pause and resume a run.
- Cost exports include source and confidence per call.
- Historical replay does not change when provider pricing changes later.
