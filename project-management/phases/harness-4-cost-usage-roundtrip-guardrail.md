# Harness 4 - Cost/Usage Roundtrip Guardrail

## Goal

Every token and dollar the orchestrator spends must land in a durable log
and roll up into a queryable per-run summary, with a regression test that
proves the roundtrip survives end-to-end. Today tokens land in
`raw-io.jsonl` but cost doesn't; cost lands on the event bus but is never
persisted; nothing reconciles the two.

## Why this is a harness phase

H0 made the audit trail honest ("what was asked, what was answered"). H1
made control honest (gates actually block). H2 will prove the live path.
H4 closes the remaining load-bearing gap on the "review" claim: you can
see prompts and you can pause runs, but you cannot yet answer "how much
did this cost and where did it go" without hand-joining two logs that
don't share a key. This phase makes that question trivially answerable
and guards it with a test.

## Required Context

- `orchestrator/lib/raw_io.py` — writes `.orchestrator/logs/raw-io.jsonl`;
  `request_id` generated in `log_llm_call` (16-hex from `uuid.uuid4()`).
- `orchestrator/lib/usage.py` — emits `usage_recorded` events; `call_id`
  generated via `new_event_id()` (separate, uncorrelated).
- `orchestrator/lib/logger.py:log_llm_call` — accepts `request_id` kwarg
  (default None → auto-generated).
- `orchestrator/lib/local_cost.py` — rate-card backed local cost estimates.
- `orchestrator/cli/inspect.py:show_tokens` — partial token rollup from
  phase logs (no cost; no cross-file reconciliation).
- Tests that this phase must keep green: `tests/test_raw_io.py`,
  `tests/test_usage_events.py`, `tests/test_llamacpp_telemetry.py`.

## Implementation Surface

- New `orchestrator/lib/usage_writer.py` — append `usage_recorded` events
  to `.orchestrator/logs/usage.jsonl`.
- New `orchestrator/lib/usage_summary.py` — rollup function that joins
  `raw-io.jsonl` + `usage.jsonl` on the shared id.
- Existing emit/log pair sites (~9 call sites) — generate one `call_id`,
  thread to both `emit_llm_usage` and `log_llm_call`.
- New `tests/test_integration_h4_usage_roundtrip.py` — end-to-end
  guardrail.

## Task H4.0 - Unify the join key across raw-io and usage events

Status: Not started

Actions:

- At each of the 9 emit/log pair sites (base.py `_chat` try+except;
  architect.py ×5; persona_forum.py ×2; quiz.py ×1), generate
  `call_id = new_event_id()` before the `llm.chat` call.
- Pass `call_id=call_id` to `emit_llm_usage`.
- Pass `request_id=call_id` to `log_llm_call`.
- Same id is used for the success path and the error-path
  `emit_llm_usage(..., status="error")`.

Acceptance:

- For every LLM call in a dry run, the `request_id` in `raw-io.jsonl`
  matches the `call_id` in the `usage_recorded` event for that call.
- Existing tests stay green.

Evidence:

```bash
uv run pytest -q tests/test_raw_io.py tests/test_usage_events.py tests/test_llamacpp_telemetry.py
```

## Task H4.1 - Persist usage events to usage.jsonl

Status: Not started

Actions:

- New `orchestrator/lib/usage_writer.py` with
  `write_usage(project_dir, payload) -> None` that appends one JSON line
  to `.orchestrator/logs/usage.jsonl`.
- Subscribe to the event bus from the runner (or hook inside `usage.py`
  immediately after `event_bus.emit`) so every `usage_recorded` payload
  is persisted.
- Do not scrub cost/token fields; the file is an internal audit trail.

Acceptance:

- Unit test: synthetic payload goes in, JSON line comes back out
  bit-for-bit.
- Integration: a dry-run pipeline writes one usage line per LLM call; the
  line count matches `raw-io.jsonl` line count.

Evidence:

```bash
uv run pytest -q tests/test_usage_writer.py
```

## Task H4.2 - Rollup function + CLI surface

Status: Not started

Actions:

- New `orchestrator/lib/usage_summary.py` exposing
  `rollup(project_dir) -> RunSummary` where `RunSummary` is a dataclass
  with `per_role: dict[str, RoleTotals]`, `per_phase: dict[str, PhaseTotals]`,
  and `totals: Totals` (tokens, cost_usd, latency_ms, call_count).
- Reconcile by joining `usage.jsonl` entries to `raw-io.jsonl` entries on
  `call_id == request_id`.
- Extend `orchestrator/cli/inspect.py` with a `show-costs` subcommand (or
  extend `show_tokens`) that prints the rollup.

Acceptance:

- Rollup totals match the sum of the underlying records (no drift).
- Calls missing from either file are surfaced, not silently dropped.

Evidence:

```bash
uv run pytest -q tests/test_usage_summary.py
uv run python -m orchestrator.cli.inspect show-costs <project_dir>
```

## Task H4.3 - End-to-end roundtrip guardrail

Status: Not started

Actions:

- New `tests/test_integration_h4_usage_roundtrip.py` runs the full
  dry-run pipeline (as H0.3 does) and asserts:
  - every `request_id` in `raw-io.jsonl` appears in `usage.jsonl` as a
    `call_id`, and vice versa (bijection).
  - `rollup(project_dir).totals.total_tokens` equals the sum of
    `prompt + completion + reasoning` across `raw-io.jsonl`.
  - `rollup(project_dir).totals.cost_usd` equals the sum of
    `cost.effective_cost` across `usage.jsonl`.
  - Per-role totals match per-role sums from the raw files.

Acceptance:

- Test is the regression anchor for "what did this run cost."
- `git diff --check` clean.

Evidence:

```bash
uv run pytest -q tests/test_integration_h4_usage_roundtrip.py
uv run pytest -q  # full suite still green
```

## Phase Exit Criteria

- `raw-io.jsonl` and `usage.jsonl` share a join key at every call site.
- `rollup()` returns a lossless per-run summary; the CLI exposes it.
- The H4.3 integration test passes and guards the bijection.
- `STATUS.md` records H4 as Done with evidence links.
