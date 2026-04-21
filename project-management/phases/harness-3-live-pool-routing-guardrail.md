# Harness 3 - Live-Pool Routing Guardrail

## Goal

Lock down the `UpstreamPool` primitive so that, by the time a live run
reaches it, "which endpoint served which call" is observable, testable,
and impossible to silently mis-route. Parallelism across PRIMARY + ALIEN
is the selling point; this phase proves it can't lie.

## Why this is a harness phase

H2 proved the gated pipeline works end-to-end in dry run but did not touch
the live path. Before H2.2 (live run against PRIMARY) is safe to attempt,
the pool primitive itself needs tests that actually await `chat`, assert
the lock, and cover the fallback branch. Today `tests/test_pool.py` has
four tests, none of which exercise `pool.chat()` at all. The pool is
effectively untested.

This is scoped to the **pool primitive**. Wiring the async pool into the
sync role call path is deferred to H5; until that lands, the pool is not
actually used in production runs.

## Required Context

- `orchestrator/lib/pool.py` — `UpstreamPool`, `Endpoint`, `NoHealthyEndpoint`.
- `tests/test_pool.py` — the stubs this phase replaces.
- `orchestrator/lib/raw_io.py` — has an `endpoint` field already; pool
  decisions need to land in it once wiring exists.
- `orchestrator/lib/usage_writer.py` — companion persistence model for
  `pool_routed` events.

## Implementation Surface

- Rewrite `tests/test_pool.py` with async tests that actually `await`.
- New `orchestrator/lib/pool_log.py` that persists pool-routing decisions
  to `.orchestrator/logs/pool.jsonl`.
- Hook into `UpstreamPool.chat` so every routing decision lands on disk.
- New `tests/test_integration_h3_pool_observability.py` — guardrail that
  two concurrent `pool.chat` calls produce two distinct endpoint labels
  in the pool log.

## Task H3.1 - Pool Primitive Test Coverage

Status: Not started

Actions:

- Rewrite `tests/test_pool.py` using `@pytest.mark.asyncio`:
  - happy-path routing: `await pool.chat("architect", msgs)` → response,
    `resp.endpoint == "primary"`, underlying client called once.
  - lock serialization: two concurrent `pool.chat` against the same
    endpoint observe the lock (slow client; assert start/end timestamps
    don't overlap).
  - fallback on `ConnectionError`: primary raises, alien returns, response
    carries `endpoint="alien"`, primary marked unhealthy.
  - `NoHealthyEndpoint` raised when every candidate is unhealthy.
  - `health_check` flips the healthy flag based on client.health() result.

Acceptance:

- All new tests fail if the corresponding behavior in `pool.py` regresses.
- Old stub tests removed.

Evidence:

```bash
uv run pytest -q tests/test_pool.py
```

## Task H3.2 - Pool Decision Log

Status: Not started

Actions:

- New `orchestrator/lib/pool_log.py` with
  `write_decision(project_dir, payload)` that appends one JSON line to
  `.orchestrator/logs/pool.jsonl`. Payload fields: `ts, call_id, role,
  chosen_endpoint, attempted_endpoints, fell_back, reason`.
- Extend `UpstreamPool.chat` to accept an optional `project_dir` +
  `call_id` pair and write a decision record per call. When absent, skip
  the write (same pattern as `usage_writer`).
- Unit test: feed a routing scenario, verify the JSONL line contents.

Acceptance:

- Every successful or fallback routing decision emits one record.
- Records are linkable to raw-io / usage via `call_id`.

Evidence:

```bash
uv run pytest -q tests/test_pool_log.py
```

## Task H3.3 - Observability Guardrail

Status: Not started

Actions:

- New `tests/test_integration_h3_pool_observability.py`:
  - construct `UpstreamPool` with two fake clients (primary, alien) that
    record their call timestamps.
  - run two `pool.chat` calls concurrently via `asyncio.gather`, one for
    a role routed to primary, one for a role routed to alien.
  - assert `pool.jsonl` has two decisions, one per endpoint, both
    successful and not fell_back.
  - assert a third concurrent call on the same endpoint serializes
    (timestamps don't overlap).
- Extend `orchestrator/lib/usage_summary.py` with a `pool_decisions`
  view, or a sibling helper, so the CLI can answer "where did each call
  land?"

Acceptance:

- The test passes today against the current pool primitive.
- The CLI (or a helper) prints per-call endpoint decisions.

Evidence:

```bash
uv run pytest -q tests/test_integration_h3_pool_observability.py
```

## Phase Exit Criteria

- Pool primitive test coverage includes routing, lock serialization,
  fallback, and health.
- Every `pool.chat` call emits a decision record to `pool.jsonl`.
- An integration test guards the "two endpoints, two concurrent calls,
  two distinct labels" promise.
- H5 is filed with the sync/async wiring work so H2.2 doesn't get
  attempted prematurely.
