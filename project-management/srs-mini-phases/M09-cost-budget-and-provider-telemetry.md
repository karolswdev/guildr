# M09 — Cost, Budget, And Provider Telemetry

## Purpose

Make cost a first-class replayable projection: every LLM / advisor / retry / escalation / session-assistant-message emits one `usage_recorded` with explicit source, confidence, and budget state. Budget gates halt runs; replay uses snapshotted rate cards.

## Why this phase exists

SRS §4.9, §8.1, §11, §14 M4. Cost truth is what separates "we have a run" from "we know what that run cost, why, and what we will pay next time." Current status: H4 shipped usage roundtrip; this phase extends to budgets, rate-card snapshots, provider telemetry, and advisor coverage.

## Required context files

- `docs/srs-council-engine.md` §4.9, §8.1, §11
- `docs/cost-tracking.md`
- `orchestrator/lib/usage_writer.py`, `usage_summary.py`
- `orchestrator/lib/opencode_audit.py`
- `QUALITY_GATES.md` G1, G7

## Implementation surface

- `orchestrator/lib/budget.py` (run / phase / provider / escalation / per-call caps)
- `orchestrator/lib/rate_cards/` (snapshots keyed by date + provider + model)
- `.orchestrator/costs/{run-summary.json, provider-ledger.jsonl, rate-cards/*.json}`
- Events: `usage_recorded` (existing), `budget_warned`, `budget_halted`, `budget_decided`
- PWA Economics panel + cost ripple visualization
- llama.cpp telemetry extractor (prompt tokens processed, cache tokens, timing, `/metrics`, `/slots`)

## Tasks

- [ ] Ensure every call site (SDLC role, narrator, advisor, retry, escalation) emits exactly one `usage_recorded`.
- [ ] Enforce explicit `cost.source ∈ {provider_reported, rate_card_estimate, local_estimate, unknown}`.
- [ ] Add `cost.extraction_path` string so replay can understand where each number came from.
- [ ] Snapshot rate card per run start into `.orchestrator/costs/rate-cards/<date>.json`; replay reads from snapshot, never current rates.
- [ ] Budget levels: project / run / phase / provider / escalation / per-call. All configurable in workflow; all can be `null`.
  - [x] Default runtime posture is permissive: `$100` advisory run budget, `$25` advisory phase budget, no hard caps, and `halt_on_hard_cap=false`.
  - [x] Hard-cap halting requires explicit operator configuration; advisory defaults may warn but must not halt execution.
- [ ] Budget state on every `usage_recorded`: `remaining_run_budget_usd`, `remaining_phase_budget_usd` (explicit null when unset).
  - [x] Central usage/opencode audit paths attach explicit `budget` state with run/phase caps and remaining values.
- [ ] Budget gate: on threshold, emit `budget_halted`; workflow pauses; operator resumes or cancels via existing gate path.
  - [x] PWA Economics sheet can decide open budget gates through the canonical `/gates/{gate}/decide` route.
  - [x] Budget gate decisions preserve explicit null budget fields when the operator continues without raising limits.
  - [x] Engine-side budget evaluation emits advisory warnings, hard-cap exceeded events, and opens/waits on budget gates only when hard caps plus `halt_on_hard_cap` are explicitly configured.
- [ ] Provider telemetry adapter for llama.cpp (local_estimate); keep OpenAI-compatible parsing for `provider_reported`.
- [ ] Provider health pings surfaced as events for PWA provider body state.
- [ ] PWA Economics lens: cost by provider / model / role / phase / atom; ripple on expensive paths; budget dial on HUD.
  - [x] First-pass map-native Economics sheet shows replay-folded effective/provider/estimated/unknown totals, budget state, source counts, and provider/model/role/phase/atom rails from `CostSnapshot`.
  - [x] Bottom HUD cost control opens the Economics sheet in the same PWA map surface and WebGL fallback renders the same summary.
  - [x] Add active budget dial/resume/cancel controls once backend budget gates are writable through the control path.
  - [ ] Add expensive-path ripple ranking beyond the existing per-atom cost ring.
- [ ] `rollup()` continues to join with zero orphans; add budget totals to the `RunSummary`.

## Quality gates

- [ ] G7 Cost truth — full bijection raw-io ↔ usage.
- [ ] G1 Event integrity on all cost/budget events.
- [ ] G2 Replay determinism — replay cost snapshot uses recorded rate card, not today's prices.
- [ ] G8 Security — no API keys in `provider-ledger.jsonl`.

## Evidence commands / checks

```bash
uv run pytest -q tests/test_usage_writer.py tests/test_usage_summary.py tests/test_budget.py tests/test_rate_card_snapshot.py
uv run orchestrator inspect <project> --costs
jq -c 'select(.cost.source == null or (.remaining_run_budget_usd == null and .remaining_phase_budget_usd == null and .budget_configured == true))' \
  <project>/.orchestrator/logs/usage.jsonl
```

## Done means

- [ ] Every call emits one and only one `usage_recorded` with explicit source + budget fields.
- [ ] `orchestrator inspect --costs` matches the sum of per-record effective costs exactly.
- [ ] A run with a run-budget hitting 0 emits `budget_halted` and the workflow actually pauses.
- [x] Replay cost panel at event N matches the frontend `CostSnapshot` folded from replayed `usage_recorded` / budget events.
- [x] PWA Economics lens is a map lens, not a table route.

## Evidence log

- 2026-04-22 M09 slice A: PWA Economics surface landed in `web/frontend/src/game/GameShell.ts`. The HUD cost chip is now `cost-control` and opens `cost-sheet`; `costSummaryCard()` renders effective/provider/estimated/unknown totals, token totals, budget state, source counts, and provider/model/role/phase/atom rails. WebGL fallback includes the same cost summary. Evidence: `uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py` -> 27 passed; `./web/frontend/build.sh` -> `dist/app.js` 1,354,618 bytes.
- 2026-04-23 M09 slice B0: permissive budget defaults landed. `orchestrator.lib.budget.BudgetConfig` defines high advisory defaults (`$100` run / `$25` phase), no hard caps, and `halt_on_hard_cap=false`; `Config` loads YAML/env overrides without allowing surprise halts. Evidence: `uv run pytest -q tests/test_config.py` -> 18 passed.
- 2026-04-23 M09 slice B1: PWA budget gate controls landed. `GameShell` now renders `budget-gate-control` inside the Economics sheet whenever `CostSnapshot.openBudgetGateIds` is non-empty, with Continue, Raise, and Stop actions posting to the existing gate decision route. The decision payload carries the folded budget snapshot so replay remains event-ledger driven. Backend tests now prove approving without a raise keeps budget fields explicitly null. Evidence: `uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py web/backend/tests/test_gates.py` -> 45 passed; `./web/frontend/build.sh` -> `dist/app.js` 1,359,926 bytes.
- 2026-04-23 M09 slice B2: runtime hard-cap enforcement landed. `BudgetRuntime` tracks cumulative run/phase spend across central `usage_recorded` emitters, attaches explicit budget state to each payload, emits `budget_warning` for advisory thresholds, emits `budget_exceeded` for hard caps, and opens/waits on `budget_gate_opened` only when `halt_on_hard_cap=true`. Opencode session audit uses the same evaluator, and the engine treats rejected budget gates as a halt rather than a retryable phase failure. Evidence: `uv run pytest -q tests/test_budget.py tests/test_config.py tests/test_opencode_audit.py web/frontend/tests/test_event_engine.py tests/test_engine.py` -> 83 passed; `uv run pytest -q tests/test_usage_summary.py tests/test_usage_writer.py tests/test_events.py web/backend/tests/test_gates.py` -> 33 passed; `./web/frontend/build.sh` -> `dist/app.js` 1,360,210 bytes.

## Known traps

- Double-emitting `usage_recorded` after a retry; the retry itself is its own call with its own `call_id`.
- Rate-card drift: tests must lock to the snapshot file, not to current pricing.
- `null` vs absent budget fields: enforce explicit null when unset, never omit.

## Handoff notes

- M10 (hookability) consumes budget gate hooks (`before_advisor_escalation`).
- M11 replay scrub surfaces the cost snapshot at that point.
