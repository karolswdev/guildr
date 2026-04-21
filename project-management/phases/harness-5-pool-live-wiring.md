# Harness 5 - Pool Live Wiring

## Goal

Make `UpstreamPool` actually reachable from the live role call path.
Today the pool is an `async def chat(...)` object, but roles invoke
`self.llm.chat(...)` synchronously and the engine passes `pool.chat` in
as an LLMClient-like shim. **A real live run against PRIMARY would fail
on first call.** H5 closes that gap so H2.2 can be attempted for real.

## Why this is a harness phase (and why it is separate)

H3 locks down what the pool primitive *does*. H5 is about the plumbing
around it. Keeping them separate prevents the observability/guardrail
work from being held hostage to a plumbing refactor, and makes the
plumbing change independently reviewable.

**H2.2 (live run against PRIMARY) cannot be attempted until H5 lands.**
Mark this dependency in `STATUS.md`.

## Known Context

- `orchestrator/lib/pool.py:UpstreamPool.chat` — `async def`, uses
  `asyncio.to_thread` internally.
- `orchestrator/engine.py` lines 384/416/440/451/477/488 — pattern:
  `llm = self._fake_llm or (self._pool.chat if self._pool else None)`.
  This hands an async callable to sync code.
- `orchestrator/roles/base.py:_chat` — calls `self.llm.chat(messages, **kw)`
  synchronously and timestamps with `time.monotonic()`.
- `orchestrator/lib/config.py` — single `llama_server_url`; no
  PRIMARY/ALIEN multi-endpoint plumbing.
- Config env vars to plumb: `BUILD_PRIMARY_URL`, `BUILD_ALIEN_URL`.

## Likely Task Shape (TBD when H5 is activated)

- **H5.1 — Sync facade for UpstreamPool.** A thin wrapper that wraps
  `asyncio.run(pool.chat(...))` behind a sync `.chat(...)` method, so
  roles keep their sync interface. Alternative: refactor roles to be
  async — bigger blast radius, likely out of scope.
- **H5.2 — Config + env plumbing.** Parse PRIMARY/ALIEN URLs from env,
  build an `UpstreamPool` with a default routing dict in `cli/run.py`
  and `web/backend/runner.py`.
- **H5.3 — End-to-end wire-up test.** Dry-run-ish test that boots a fake
  pool with two endpoints, runs the engine, verifies each role landed on
  the expected endpoint in `pool.jsonl` (produced by H3.2).

## Phase Exit Criteria

- A live run can reach both endpoints without TypeError/coroutine errors.
- Routing decisions land in `pool.jsonl` for real runs, not just tests.
- `STATUS.md` updates H2.2's blocking dependency once H5 is green.
