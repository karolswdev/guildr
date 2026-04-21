# Project Status

Last updated: 2026-04-21

## Honest Current State

**The product claim is "first-class orchestration — review, follow, intervene."
Today, only "follow" is true end-to-end. "Review" has a deceptive gap, and
"intervene" is cosmetic.** The visual Three.js map is legitimate product
surface work, but it has been getting built on top of a harness that silently
auto-approves every gate and discards every LLM prompt/response. That has to
be fixed first.

### What actually works

- **Follow.** SSE streaming (`web/backend/routes/stream.py`) is real-time,
  replay buffer included. PWA sees live phase events.
- **Dry-run pipeline.** 438 tests passing, ~90% coverage — but this is
  `FakeLLMClient` only. The dry-run is a genuine artifact machine; the live
  llama-server path has never been battle-tested.
- **Orchestrator internals.** `engine.py` is a clean 514-line state machine.
  Roles are independent. `pool.py` routes PRIMARY/ALIEN correctly on paper.
- **Visual map.** Zero-g Three.js route with orbit/pinch, atoms, tethers,
  pulses, radial action ring, Poly Pizza props, view-level HUD, first flow
  primitives.

### Load-bearing gaps (must fix before more product work)

1. **Prompt/response discarding.** `orchestrator/lib/logger.py:138`
   `log_llm_call` accepts `messages` and `response` parameters and discards
   them — writes only token counts + latency. There is no record of what any
   role was actually asked or what it answered. "Review" is theater.
2. **Two separate `GateRegistry` classes.** `orchestrator/lib/gates.py:34`
   (canonical, used by engine) and `web/backend/routes/gates.py:60`
   (module-level singleton `_gate_registry = GateRegistry()`, used by HTTP
   routes). They are never synchronized. A PWA gate decision never reaches
   the engine.
3. **Gates hardcoded off in PWA.** `web/backend/runner.py:160` sets
   `require_human_approval=False` with a literal comment: "PWA gate flow not
   wired yet — see TODO in projects.py." Every PWA run auto-approves every
   gate.
4. **Live path never verified.** All tests exercise `FakeLLMClient` with
   gates disabled. The real PRIMARY/ALIEN path with gates on has never been
   executed end-to-end in practice.

## Phase Board

Harness phases block all downstream visual-map phases. Visual map phases
(the old Phase 0-8) remain valuable but are paused until the harness is
honest.

| Phase | Status | Owner | Notes |
| --- | --- | --- | --- |
| **H0 Capture Everything** | Done | Claude | All tasks shipped 2026-04-21. Raw LLM I/O now lands on disk with a guarding end-to-end test |
| **H1 Single Gate Registry** | Done | Claude | H1.1 + H1.2 + H1.3 done 2026-04-21. `require_human_approval` is now a per-run opt-in end-to-end (PWA toggle, HTTP body, CLI `--gate`). Idle-RPG default preserved |
| **H2 Live-Path Battle Test** | Blocked | Claude | H2.1 programmatic rehearsal done 2026-04-21 (commit 6fbd055). **Pick-up item: manual PWA walk-through** (deferred — requires human at the device). H2.2/H2.3 require live PRIMARY/ALIEN endpoints *and* H5 plumbing (pool async/sync mismatch means a live run would TypeError on first call) |
| **H3 Live-Pool Routing Guardrail** | Done | Claude | All tasks shipped 2026-04-21. Async pool tests (routing/serialization/fallback/health), `pool.jsonl` decision log, observability integration test. Does not fix the H5 plumbing gap |
| **H4 Cost/Usage Roundtrip Guardrail** | Done | Claude | All tasks shipped 2026-04-21. raw-io ↔ usage share a join key; usage.jsonl persisted; `rollup()` + `inspect --costs` expose a per-run summary; integration test guards the bijection |
| **H5 Pool Live Wiring** | Not started | Unassigned | Blocks H2.2. Wire the async `UpstreamPool` into the sync role call path (sync facade or async roles); parse PRIMARY/ALIEN URLs from env; ensure engine can actually reach a pool endpoint |
| 0 Baseline And Invariants | In progress | Claude | Task 0.1 done 2026-04-21; 0.2 and 0.3 pending. Resumes after H2 |
| 1 Flow Foundation | In progress | Codex | FlowTypes, FlowPath, first FlowDirector mapping landed. Paused after H0-H2 |
| 2 Orbital Loop Layout | Not started | Unassigned | Paused until harness ships |
| 3 Model Catalog And Actors | Not started | Unassigned | Paused until harness ships |
| 4 Content Previews Speech Artifacts | Not started | Unassigned | Paused until harness ships |
| 5 Operator Touch Control | Not started | Unassigned | Paused until harness ships |
| 6 Engine Consumption And Run Control | Not started | Unassigned | Depends on H1 (real intent → live run) |
| 7 Mobile Performance And Polish | Not started | Unassigned | Paused until harness ships |
| 8 Release Hardening | Not started | Unassigned | Cannot ship honestly until H2 green |

## Next Recommended Task

**When a human is at the device:** Resume H2.1 manual PWA walk-through
(see `phases/harness-2-live-path-battle-test.md`, Task H2.1 pick-up notes),
then H2.2 live run against PRIMARY.

**When working headless (no device, no live endpoints):** H2 is blocked on
manual/hardware. Pick a scriptable parallel track instead — candidates
that don't violate the "harness before visual phases" rule:

- A new harness phase (e.g. live-pool routing guardrail, cost/usage
  roundtrip guardrail) — agree scope with the operator first.
- Phase 0 Task 0.2 (Ultimate Space Kit asset test guardrails) or 0.3
  (mobile smoke procedure docs). These were paused pending H2 but are
  safe to land in parallel because they don't touch harness surfaces.

Do not resume Phase 1+ visual-map work until H2 is fully green.

## Current Verification Commands

Run from `build/workspace/` (repo root). These are the narrowest commands that
cover each surface; use them for UI/asset edits instead of the full suite.

| Surface | Command |
| --- | --- |
| Backend event + static asset serving | `uv run pytest -q web/backend/tests/test_pwa_serving.py web/backend/tests/test_events.py` |
| Frontend game asset manager | `uv run pytest -q web/frontend/tests/test_asset_manager.py` |
| Frontend map route | `uv run pytest -q web/frontend/tests/test_game_map.py` |
| Full frontend bundle | `./web/frontend/build.sh` |
| Full backend + frontend test suite | `uv run pytest -q` |

All four narrow commands verified green on 2026-04-21 (`git diff --check` clean).

## Latest Asset Facts

Ultimate Space Kit:

- Source: https://poly.pizza/bundle/Ultimate-Space-Kit-YWh743lqGX
- Creator: Quaternius
- License: CC0 1.0 Public Domain
- 87 GLB models
- 11,361,152 bytes extracted
- Animated: 3 astronauts, 4 mechs, 3 enemies
- Manifest: `assets/poly-pizza/ultimate-space-kit/manifest.json`

## Known Risks

### Harness (blocking)

- **Pool primitive is not actually wireable today.** `UpstreamPool.chat` is
  `async def`, roles call `self.llm.chat` synchronously, engine passes
  `pool.chat` in as an LLMClient-like shim. A real live run would TypeError
  on first call. Tracked as H5; H2.2 depends on it.
- Live llama-server path has never been executed with gates on (tracked as H2,
  now blocked on H5 plumbing).
- ~~Raw LLM I/O not captured~~ (fixed H0).
- ~~Two `GateRegistry` instances with zero sync~~ (fixed H1.1).
- ~~`require_human_approval` hardcoded in PWA runner~~ (fixed H1.3 — now a
  per-run opt-in threaded through the start route and CLI).

### Product (after harness ships)

- Current visual flow system is still generic pulses.
- Current loop visuals can still read as decorative unless replaced by cluster
  motion and transfer corridors.
- Full model kit must not be loaded all at once on mobile.
- Operator intents are visible/persisted but not yet a complete live-run
  control plane (blocked on H1).
- DOM overlays for readable previews must be pooled and collision-managed.

## Evidence Log

Append new evidence here instead of burying it in chat.

| Date | Phase/task | Evidence |
| --- | --- | --- |
| 2026-04-21 | Poly Pizza display wiring | Frontend build passed; asset/game/backend smoke tests passed; GLB requests returned `200 model/gltf-binary`; screenshot `/tmp/council-map-poly-pizza-props.png` |
| 2026-04-21 | Ultimate Space Kit inventory | `jq` manifest validation passed; all 87 GLBs have `glTF` magic headers; `git diff --check` passed |
| 2026-04-21 | Phase 1 flow foundation + view levels | `uv run pytest -q web/frontend/tests/test_game_map.py` passed; `./web/frontend/build.sh` passed; mobile HUD now exposes Run/Loop/Object scales |
| 2026-04-21 | Phase 0 Task 0.1 — verification commands | `uv run pytest -q web/backend/tests/test_pwa_serving.py web/backend/tests/test_events.py` 10 passed; `uv run pytest -q web/frontend/tests/test_asset_manager.py web/frontend/tests/test_game_map.py` 9 passed; `./web/frontend/build.sh` built 1,237,754-byte `dist/app.js`; `git diff --check` clean |
| 2026-04-21 | Honest reset | Harness H0/H1/H2 phases inserted ahead of visual-map work. Verified firsthand: `runner.py:160` hardcodes auto-approve; two `GateRegistry` classes (`orchestrator/lib/gates.py:34`, `web/backend/routes/gates.py:60`); `logger.py:138` discards `messages`/`response` params |
| 2026-04-21 | Harness 0 Task H0.1 — raw I/O writer | New `orchestrator/lib/raw_io.py` + shared `orchestrator/lib/scrub.py` (also consumed by `web/backend/routes/intents.py`). `uv run pytest -q tests/test_raw_io.py web/backend/tests/test_intents.py` → 5 passed. Full suite `uv run pytest -q` → 494 passed, 1 skipped. `git diff --check` clean |
| 2026-04-21 | Harness 0 Task H0.2 — wire log_llm_call | `setup_phase_logger` now stashes `project_dir` on the logger; `log_llm_call` generates a `request_id`, writes the token summary to `<phase>.jsonl`, and appends the full round-trip (messages + response_content + reasoning_content + usage + endpoint) to `raw-io.jsonl`. Call sites (`roles/base.py`, `roles/architect.py` ×3) pass `endpoint=getattr(self.llm, "base_url", None)`. Full suite → 496 passed, 1 skipped. `git diff --check` clean |
| 2026-04-21 | Harness 0 Task H0.3 — end-to-end capture guard | New `tests/test_integration_raw_io.py` seeds `qwendea.md` and the fake LLM's reasoning with unique sentinels, runs the full dry-run pipeline, and asserts both sentinels, ≥1 known role, and unique `request_id`s in `raw-io.jsonl`. Full suite → 497 passed, 1 skipped. `git diff --check` clean. **Phase H0 complete.** |
| 2026-04-21 | Harness 1 Task H1.1 — consolidate GateRegistry | Deleted the shadow `GateRegistry` in `web/backend/routes/gates.py`. Canonical `orchestrator/lib/gates.GateRegistry` now carries `open_gate`, `list_gates`, `get_gate`, idempotent `decide(name, decision, reason)`, plus a new `GateRegistryStore` for multi-project HTTP traffic. Web routes become a thin facade. `rg "^class GateRegistry" → 1` match. `uv run pytest -q tests/test_gates.py web/backend/tests/test_gates.py` → 30 passed. Full suite → 500 passed, 1 skipped. `git diff --check` clean |
| 2026-04-21 | Harness 3 — live-pool routing guardrail | H3.1 rewrote `tests/test_pool.py` with 8 async tests that actually `await pool.chat`: preferred-endpoint routing, fallback on `ConnectionError` (with healthy flag flip), `NoHealthyEndpoint` on exhaustion, unknown-role raise, lock serialization within one endpoint (two concurrent calls delayed ≥ 2 × delay), parallelism across endpoints (< 1.8 × delay), health_check flag flip + recovery. H3.2 new `orchestrator/lib/pool_log.py` persists every routing decision to `.orchestrator/logs/pool.jsonl` with `call_id, role, chosen_endpoint, attempted_endpoints, fell_back, reason`; `UpstreamPool.chat` gained `project_dir` + `call_id` kwargs. H3.3 `tests/test_integration_h3_pool_observability.py` runs two `pool.chat` calls via `asyncio.gather` and asserts distinct endpoint labels land in `pool.jsonl`; a second test asserts `fell_back=True` when primary raises `ConnectionError`. Uncovered a critical gap en route: `UpstreamPool.chat` is `async def` but roles call `self.llm.chat` synchronously → a real live run would fail on first call. Filed as new phase **H5 Pool Live Wiring**, now blocking H2.2. Full suite → 529 passed, 1 skipped. **Phase H3 complete.** |
| 2026-04-21 | Harness 4 — cost/usage roundtrip guardrail | H4.0 unified the join key: every emit/log pair site in `roles/base.py` (_chat), `roles/architect.py` (×3 try blocks: draft, refine, judge), generates one `call_id = new_event_id()` and threads it to both `emit_llm_usage(call_id=...)` and `log_llm_call(request_id=...)`. H4.1 new `orchestrator/lib/usage_writer.py` persists every `usage_recorded` payload to `.orchestrator/logs/usage.jsonl`; hooks added to `emit_llm_usage` and `emit_advisor_usage` so the on-disk copy can't be forgotten. H4.2 new `orchestrator/lib/usage_summary.py:rollup(project_dir)` joins raw-io.jsonl + usage.jsonl on the shared id, returns `RunSummary` with `per_role`, `per_phase`, `totals`, and `orphans` (calls that fell out of one file). `orchestrator inspect <project> --costs` prints the rollup. H4.3 `tests/test_integration_h4_usage_roundtrip.py` runs the full dry-run pipeline and asserts every raw-io `request_id` has a matching usage `call_id`, rollup totals equal the underlying sums, and cost totals match the per-record effective costs. Full suite → 519 passed, 1 skipped. **Phase H4 complete.** |
| 2026-04-21 | Harness 2 Task H2.1 — programmatic gated dry-run rehearsal | New `tests/test_integration_h2_1_rehearsal.py` drives the full PWA-gated code path: starts `_run_orchestrator` on a daemon thread with `require_human_approval=True`, approves every pending gate via `POST /api/projects/{id}/gates/{name}/decide`, and asserts run_complete + all expected roles captured in `raw-io.jsonl` + unique request_ids. `uv run pytest -q tests/test_integration_h2_1_rehearsal.py` → 1 passed. Full suite → 510 passed, 1 skipped. Out-of-test rehearsal into `/tmp/guildr-rehearsal/` produced 5 raw-io records (architect×2, coder, reviewer, deployer — tester shells out to pytest and makes no LLM call). `git diff --check` clean. Manual PWA walk-through + H2.2 live-path run against PRIMARY are the next steps |
| 2026-04-21 | Harness 1 Task H1.3 — per-run gate opt-in | `require_human_approval` is now plumbed through `web/backend/runner.py` (default False), the HTTP start route (`StartRequest.require_human_approval: bool = False`), the PWA start panel (new "Gate my approval at each phase" checkbox, default off), and the CLI (`--gate` flag, mutually exclusive with `--no-gates`). Engine Config no longer hardcoded in runner. New tests: `test_web_runner_defaults_to_idle_rpg_mode`, `test_web_runner_threads_gate_opt_in_into_config`, `test_start_project_defaults_to_idle_rpg_mode`, `test_start_project_honors_gate_opt_in`, `test_gate_flag_forces_require_human_approval_true`, `test_gate_and_no_gates_are_mutually_exclusive`. Full suite → 509 passed, 1 skipped. `./web/frontend/build.sh` → `dist/app.js` 1,238,255 bytes. `git diff --check` clean. **Phase H1 complete.** |
| 2026-04-21 | Harness 1 Task H1.2 — inject registry from runner | `web/backend/runner.py` now pulls the per-project `GateRegistry` from `get_gate_store().ensure(project_id)` and passes it into `Orchestrator(gate_registry=...)`. Engine's lazy fallback kept but emits a prominent WARNING so mis-wired code is visible. New `web/backend/tests/test_gate_engine_integration.py` proves round-trip: engine thread calls `_gate()`, HTTP POST decides, engine thread unblocks (approval) or raises `PhaseFailure` with the reason (rejection); third test asserts `routes.gates.get_gate_store() is runner.get_gate_store()`. Fixed TestClient LAN-middleware block via `ORCHESTRATOR_EXPOSE_PUBLIC=1`; test threads made daemon. Updated `web/backend/tests/test_runner.py` fakes to accept `gate_registry` kwarg. `uv run pytest -q web/backend/tests/test_gate_engine_integration.py` → 3 passed. Full suite → 503 passed, 1 skipped. `git diff --check` clean. H1.3 reshaped around user feedback: PWA is an idle-RPG touch surface — gating is opt-in per run, not coerced on |
