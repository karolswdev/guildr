# Agent Onboarding

This is the canonical handover for a fresh-context agent picking up work on
`guildr`. If you read only this file and the two it points to
(`STATUS.md`, `DIRECTION_GUARDRAILS.md`), you should be able to land a
commit without blundering into a known trap.

Working directory for every command below: `build/workspace/` (the repo root).

## What this project actually is

- A self-hosted SDLC orchestrator that runs a multi-role LLM pipeline
  (architect → coder → tester → reviewer → deployer) against a local
  `llama.cpp` server. Target model: Qwen (128 KiB context ceiling).
- The primary surface is a **LAN-only PWA** with a zero-g Three.js map —
  users watch roles work, review artifacts, and intervene on gates.
- CLI (`orchestrator …`) is the scriptable surface and the happy path for
  every agent test. The PWA wraps the same engine.
- **Two tracks of work coexist** in `project-management/phases/`:
  - `harness-*.md` — trust-in-the-stack guardrails (H0..H5). **These block
    all visual-map work.** Do not resume Phase 1+ until the harness is
    honestly green (see STATUS).
  - `00-*.md .. 08-*.md` — zero-g visual map phases. Paused behind H2.

## Read order (≈ 10 minutes)

1. `project-management/STATUS.md` — ground truth for what is done,
   blocked, and next. Evidence log is append-only; trust the latest rows.
2. `project-management/DIRECTION_GUARDRAILS.md` — the product-shaped
   rules a passing test cannot protect (zero-g map, no dashboards, Ultimate
   Space Kit used semantically, mobile-first).
3. The phase file for whatever task you pick up
   (`project-management/phases/…`). Each task lists acceptance criteria
   and context pointers.
4. `git log --oneline -20` to see the last week's shape of work.

Only then open code. Do not start by grepping.

## Repo layout (mental model)

```
build/workspace/
├── orchestrator/          # Engine + roles + libs (pure Python, sync-ish)
│   ├── engine.py          # State machine driving role phases
│   ├── roles/             # architect, coder, tester, reviewer, deployer
│   ├── lib/
│   │   ├── llm.py         # LLMClient interface + LLMResponse dataclass
│   │   ├── pool.py        # UpstreamPool (async) — PRIMARY/ALIEN routing
│   │   ├── sync_pool.py   # SyncPoolClient — sync facade roles call through (H5.1)
│   │   ├── pool_log.py    # pool.jsonl decision persistence (H3)
│   │   ├── raw_io.py      # raw-io.jsonl per-call prompt/response audit (H0)
│   │   ├── usage_writer.py# usage.jsonl per-call cost/tokens (H4)
│   │   ├── usage_summary.py # rollup() joins raw-io + usage on call_id
│   │   ├── gates.py       # Canonical GateRegistry + GateRegistryStore
│   │   └── event_schema.py# new_event_id() — 26-char ULID-ish, the join key
│   └── cli/               # `orchestrator run|inspect|…`
├── web/
│   ├── backend/           # FastAPI; mounts /assets, /dist, /api, SSE
│   └── frontend/          # TS + Three.js PWA; esbuild bundle → dist/app.js
├── assets/                # Vendored only; served at /assets/…
│   └── poly-pizza/ultimate-space-kit/   # 87 GLB models, CC0, Quaternius
├── tests/                 # Python tests. Integration tests live here too.
├── project-management/    # THIS FOLDER — phases, status, guardrails
└── docs/                  # Design notes, architecture, cost tracking
```

On-disk audit files (per project run, under
`<project_dir>/.orchestrator/logs/`):

- `raw-io.jsonl` — every LLM round-trip (messages in + response out).
- `usage.jsonl` — per-call tokens + cost + latency.
- `pool.jsonl` — which endpoint each call landed on, fallback state.

These three join on `call_id` (also written as `request_id` in raw-io and
`log_llm_call`). That shared id is the load-bearing primitive H4 introduced.

## Glossary of moving parts

- **Role** — one stage of the SDLC pipeline. Each role calls the LLM via
  `self.llm.chat(...)` synchronously today. See §Known traps.
- **Phase** — a role's execution within a run (roles may run multiple
  passes, e.g. architect draft/refine/judge).
- **Harness phases (H0..H5)** — separately numbered from the visual-map
  phases. They exist because the original pipeline silently discarded
  prompts/responses and auto-approved every gate. The harness work is
  about making "review/intervene" honest before we extend "follow".
- **`call_id`** — 26-char id from `new_event_id()`. The universal join key
  across raw-io.jsonl, usage.jsonl, pool.jsonl, and the `log_llm_call`
  token summary. Generate once at the call site, thread everywhere.
- **GateRegistry** — canonical in `orchestrator/lib/gates.py`. There used
  to be a shadow copy in `web/backend/routes/gates.py`; it is gone (H1.1).
  HTTP routes now facade through `GateRegistryStore`.
- **UpstreamPool** — routes a role request to PRIMARY or ALIEN endpoint,
  serializes per-endpoint via `asyncio.Lock` (honors llama.cpp `-np 1`),
  runs cross-endpoint in parallel. Writes one `pool.jsonl` record per call.
- **SyncPoolClient** (`orchestrator/lib/sync_pool.py`) — per-role sync
  adapter over `UpstreamPool`. Exposes `.chat(messages, *, call_id=None,
  **kw)`, threads `call_id` into the pool so `pool.jsonl` joins cleanly
  on the H4 key, and sets `self.base_url` to the chosen endpoint label
  after a successful call. Built by `Orchestrator._llm_for(role)`.
- **Ultimate Space Kit** — 87 CC0 GLB models. Used *semantically* (see
  DIRECTION_GUARDRAILS): astronaut=operator, mech=builder, rover=CI, etc.
  Never precache the whole kit in the service worker.

## Current state snapshot

STATUS.md is the source of truth; repeating it here rots. At time of
writing (2026-04-21):

- H0/H1/H3/H4 done. H2 blocked on manual walk + live endpoints + H5.
- H5.1 done (sync facade lands; engine wires it per-role). H5.2/H5.3
  pending — env URL plumbing + an end-to-end two-endpoint wire-up test
  are what remain between the project and a real live run.
- Phase 0 tasks 0.1 and 0.2 done; 0.3 pending.
- Visual phases 1..8 paused behind the harness.

Read STATUS's "Phase Board" + "Next Recommended Task" before picking work.

## Verification commands

Run from `build/workspace/`. Prefer narrow commands scoped to what you
touched; only run the full suite before a commit.

| Surface | Command |
| --- | --- |
| Full Python suite | `uv run pytest -q` |
| Backend event + static asset | `uv run pytest -q web/backend/tests/test_pwa_serving.py web/backend/tests/test_events.py` |
| Frontend game + asset manager | `uv run pytest -q web/frontend/tests/test_asset_manager.py web/frontend/tests/test_game_map.py` |
| Pool / usage / raw-io guardrails | `uv run pytest -q tests/test_pool.py tests/test_pool_log.py tests/test_usage_writer.py tests/test_usage_summary.py tests/test_integration_h3_pool_observability.py tests/test_integration_h4_usage_roundtrip.py tests/test_integration_raw_io.py` |
| Manifest / space-kit guardrails | `uv run pytest -q tests/test_ultimate_space_kit_manifest.py web/backend/tests/test_pwa_serving.py` |
| Frontend bundle | `./web/frontend/build.sh` |
| Whitespace hygiene | `git diff --check` |

Never commit without running at least one narrow test that touches what
you changed, plus `git diff --check`.

## Known traps (learn these before they bite)

1. **Pool async vs. role sync mismatch (H5).** `UpstreamPool.chat` is
   `async def`. Roles call `self.llm.chat(...)` synchronously. H5.1
   landed `SyncPoolClient` (`orchestrator/lib/sync_pool.py`) — the engine
   now builds one per role via `Orchestrator._llm_for(role)` and the
   facade `asyncio.run`s `pool.chat(role, messages, ...)`. The live path
   still needs H5.2 (parse `PRIMARY_URL`/`ALIEN_URL` env + construct a
   pool in `runner.py`/`cli/run.py`) before H2.2 can be attempted. If
   you see a role receive `pool.chat` directly, something un-did H5.1.
2. **Python 3.14 on this Mac cannot reach the LAN.** Build venvs on 3.13.
   If a script silently fails to hit a `192.168.x` llama-server from
   Python, you are probably on 3.14. (See user memory.)
3. **Manifest paths are URL-encoded.** `assets/.../manifest.json` writes
   spaces as `%20`. `unquote()` before `Path(...).is_file()`. Caught
   during Phase 0 Task 0.2.
4. **Two shell tools must agree.** Frontend tests shell out to `esbuild`
   + `node`; backend tests to `pytest`. If you run a subset, say so.
5. **`LLMResponse` required positional args.** `content, reasoning,
   model, prompt_tokens, completion_tokens, reasoning_tokens,
   finish_reason`. Fakes that omit any will TypeError at construction.
6. **Do not service-worker-precache poly-pizza models.** A Python test
   (`test_ultimate_space_kit_manifest.py::test_no_kit_model_is_in_service_worker_precache`)
   now guards this. If you add a model to `STATIC_ASSETS` in `sw.js`,
   that test will fail — fix the list, not the test.
7. **Gates default to off on the PWA and on in the CLI.** PWA is an
   idle-RPG touch surface (H1.3). The `--gate` CLI flag opts into gating
   per-run. `require_human_approval` is no longer hardcoded anywhere.
8. **`call_id` must be generated once per call site.** If you see two
   sibling writes with different ids, the join key is broken and the
   rollup will surface orphans. Thread the same id to
   `emit_llm_usage(call_id=...)` and `log_llm_call(request_id=...)`.

## Picking up a blocked item

For each pending item in STATUS, here is the concrete unblock path:

- **H2.1 manual PWA walk-through** — requires a human at the device
  (desktop browser + mobile Safari). See `harness-2-…md` for the script.
  Programmatic rehearsal (`tests/test_integration_h2_1_rehearsal.py`)
  already covers the automatable surface.
- **H2.2 live run against PRIMARY** — blocked on H5. Do H5 first.
- **H5 pool live wiring** — H5.1 shipped the sync facade (`SyncPoolClient`).
  Remaining work:
  - **H5.2** — parse `PRIMARY_URL` / `ALIEN_URL` from env in
    `web/backend/runner.py` and `orchestrator/cli/run.py`, build an
    `UpstreamPool` with a default role→endpoint routing dict, and pass
    it in as `Orchestrator(pool=...)` instead of `fake_llm=...`.
  - **H5.3** — end-to-end test that boots a two-endpoint pool against
    fake inner clients, runs the engine, asserts each role's call
    landed on the expected endpoint in `pool.jsonl`.
- **Phase 0 Task 0.3** — write the mobile smoke procedure in
  `project-management/phases/00-baseline-and-invariants.md`.
  Scriptable only insofar as the *document* is the deliverable; the
  actual smoke is manual.

## Handoff format (what "done" looks like)

Before handing off:

1. Append one row to `STATUS.md` "Evidence Log" with the exact commands
   you ran and their pass counts. Include `git diff --check` result.
2. Update the "Phase Board" status cell if a phase changed state.
3. If you changed a load-bearing primitive (pool, raw-io, usage, gates,
   call_id), add or update an entry in §Glossary here.
4. If you discovered a new trap, add it to §Known traps.
5. Commit with a message that references the phase/task id
   (e.g., `H3.3 pool routing observability guardrail`).

## Don't

- Don't add a test that depends on live network or a real llama-server
  without clearly marking it `@pytest.mark.live` and keeping it out of
  the default suite.
- Don't "fix" harness-related warnings by hiding them — they are there
  to surface the engine's lazy fallbacks (see the WARNING in
  `engine.py`'s gate registry path, H1.2).
- Don't reintroduce shadow state (another GateRegistry instance,
  another call_id source). If you catch yourself doing it, stop.
- Don't touch `_run_orchestrator`'s gate defaults without reading H1.3 —
  the PWA is an idle-RPG by design.
- Don't bundle a visual-map change with a harness change in one commit.
