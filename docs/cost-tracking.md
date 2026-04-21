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

Each usage record must also declare a confidence level:

- `high`: provider-reported cost from a reliable API response.
- `medium`: rate-card estimate with a current, verified rate card.
- `low`: local estimate, stale rate card, or CLI-parsed output.
- `none`: source is unknown or cost could not be estimated at all.

Valid values are exactly these four strings. No other values are permitted.
The confidence enum must be defined as `CostConfidence` in all typed clients.

## OpenRouter Cost Extraction

When the provider is OpenRouter, cost must be extracted in this priority order:

1. `usage.cost` and token detail fields in the non-streaming response body.
   Source: `provider_reported`, confidence: `high`.
2. `usage.cost` and token detail fields in the final streaming SSE message.
   Source: `provider_reported`, confidence: `high`.
3. Follow-up call to `/api/v1/generation?id=<generation_id>` using the response
   `id`. Use this when usage was not captured from the original response or
   when an audit refresh is explicitly requested. Source: `provider_reported`,
   confidence: `medium` if fetched asynchronously after the run.
4. Rate-card estimate from stored OpenRouter pricing. Source:
   `rate_card_estimate`, confidence: `medium`.

Adapters must record which extraction path was used in the event payload as
`cost.extraction_path` (`response_usage`, `stream_usage`, `generation_api`,
`rate_card`). This allows replay and audit to understand why costs differ
across calls.

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

For local llama calls, effective cost is computed using this formula:

```
compute_cost = hourly_cost_usd * (wall_ms / 3_600_000)
energy_cost  = energy_cost_usd_per_kwh * (estimated_energy_wh / 1000)
gpu_cost     = gpu_hourly_cost_usd * (gpu_seconds / 3600)
effective_cost = compute_cost + energy_cost + gpu_cost
```

When `estimated_energy_wh` or `gpu_seconds` are null, those terms are zero.
This formula and the `machine_id` must be recorded in `cost.rate_card_version`
so replay always uses the formula that was active at run time, not the current
machine config.

The UI must label this as an estimate, not an invoice.

## Rate Card Immutability

Rate-card files under `.orchestrator/costs/rate-cards/` must be treated as
write-once. A rate card is identified by its `rate_card_version` field (an
ISO8601 timestamp of when the card was fetched or configured). Once written,
a rate-card file must not be modified. If pricing changes, a new file with a
new timestamp is written. Old files remain so historical replay can resolve
the version string from any prior event.

Implementations must verify that the rate card referenced in a replayed event
exists on disk. If it is missing, the replay viewer must show a warning and
fall back to `source: "unknown"`, `confidence: "none"` for affected calls.
Replay must never silently substitute a newer rate card.

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

The `budget_gate_decided` event schema:

```json
{
  "type": "budget_gate_decided",
  "ts": "2026-04-21T20:18:00.000Z",
  "run_id": "run-20260421-201501",
  "gate_id": "budget-gate-01HY",
  "decision": "approved",
  "new_run_budget_usd": 15.0,
  "new_phase_budget_usd": null,
  "operator_note": "Increasing budget for escalation phase.",
  "budget_at_decision": {
    "run_budget_usd": 15.0,
    "phase_budget_usd": null,
    "remaining_run_budget_usd": 7.816
  }
}
```

Field rules:

- `decision`: one of `approved`, `rejected`. `rejected` halts the run.
- `new_run_budget_usd`: present and non-null when the operator increased (or
  decreased) the run budget. Null if the decision was approval without a
  budget change.
- `new_phase_budget_usd`: same semantics for the current phase budget.
- `budget_at_decision`: the effective budget state immediately after the
  decision is applied. Replay must update `remainingRunBudgetUsd` from this
  field when folding a `budget_gate_decided` event. This is the authoritative
  post-gate budget state, not re-derived from prior usage totals.

The EventEngine fold rule for `budget_gate_decided`:
1. If `decision === "rejected"`: mark run as halted. No further usage events
   should appear, but replay must tolerate them if they do.
2. If `new_run_budget_usd` is present: update the effective run cap to
   `new_run_budget_usd`.
3. Always update `remainingRunBudgetUsd` from `budget_at_decision.remaining_run_budget_usd`.

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
