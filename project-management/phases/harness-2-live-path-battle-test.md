# Harness 2 — Live-Path Battle Test

## Goal

Run a real project, end-to-end, against live llama-server endpoints
through opencode, with gates on, from the PWA. Capture the artifacts
as a reference run so future regressions of the live path are detectable.

## Why this is next

Harness 0 gives us audit trails. Harness 1 gives us control. Harness 6
replaced the custom pool with opencode SessionRunners — every SDLC role
now runs under opencode with its own subprocess. The dry-run pipeline
is proven green (482 tests). The live path has not been executed
end-to-end since the opencode migration. Until it has, we cannot honestly
market "first-class review / follow / intervene" — the claim has never
been executed against real model output.

## Required Context

- Memory: `project_orchestrator.md` — PRIMARY (192.168.1.13) and ALIEN
  (192.168.1.70), Qwen3.6-35B-A3B Q5/Q6, 131072 ctx ceiling, LAN-only PWA.
- `orchestrator/cli/run.py::_build_opencode_session_runners` — reads
  `endpoints:` + `routing:` YAML, writes per-project `opencode.json`,
  spawns one `OpencodeSession` per role. This is the live entry point.
- `web/backend/runner.py::_run_orchestrator` — background-thread bridge
  from the PWA. Uses the same opencode wiring when `ORCHESTRATOR_CONFIG`
  points at a YAML with an `endpoints:` block; else falls back to
  `dry_run=True`.
- `config.example.yaml` — template for declaring endpoints and per-role
  routing. The legacy single-endpoint path is gone.
- Harness 0 (`raw-io.jsonl`) and Harness 1 (gate registry) must still be
  green — both land before H2 is meaningful.

## Implementation Surface

- No product code changes expected. If any land, they are fixes surfaced
  by running live.
- New test: `tests/test_integration_h2_live_stub.py` — opencode wiring
  smoke test against a fake llama-compatible HTTP stub, CI-safe.
- New directory: `docs/reference-run/` — frozen artifacts from one real
  run, checked in as a regression anchor.

## Task H2.1 — Programmatic Rehearsal (Gated Dry-Run)

Status: **Done.** `tests/test_integration_h2_1_rehearsal.py` drives the
same `_run_orchestrator` + HTTP-decide code path a human hits from the
PWA. Keep it green before/after the manual walk.

Pick-up notes for the manual half (still pending):

- `./web/frontend/build.sh` → start the PWA on `0.0.0.0` on LAN.
- Create a project with a small `qwendea.md` (e.g. "python CLI that
  formats JSON with sorted keys"). Toggle "Gate my approval at each phase"
  ON. Start the run.
- Approve each gate as it surfaces. Confirm `run_complete` fires and
  inspect `<project>/.orchestrator/logs/raw-io.jsonl`.
- Evidence: screenshot per gate, `wc -l raw-io.jsonl`, final phase event
  timeline.

Acceptance:

- Full dry-run pipeline completes via PWA with gates approved manually.
- `raw-io.jsonl` contains one record per opencode session call
  (per-role), with prompts and responses both present.

## Task H2.2 — Opencode Wiring Smoke (Headless, CI-Safe)

Status: Not started.

Rationale: before booking a real llama-server session, we want a
regression guard that exercises `_build_opencode_session_runners` and
the per-project `opencode.json` writer end-to-end against a local stub.
Catches config-shape drift without needing a live endpoint.

Actions:

- Stand up a tiny FastAPI stub that speaks enough of the OpenAI-compatible
  chat-completions API to satisfy opencode's contract (echo the last
  message, emit a usage block). Start it on a free port in a fixture.
- Write a config YAML pointing one `endpoints:` entry at the stub, with
  a routing table covering all six SDLC roles.
- Drive `cmd_run` or `_run_orchestrator` against a throwaway project dir.
- Assert: each role's opencode session produced a row in `raw-io.jsonl`,
  `opencode.json` was written with the expected providers, and
  `run_complete` fires.

Acceptance:

- `tests/test_integration_h2_live_stub.py` passes in CI (no LAN dep).
- The test fails loudly if `_build_opencode_session_runners` stops
  wiring a role, or if `opencode.json` schema drifts.

## Task H2.3 — Live Run Against PRIMARY

Status: Not started. Requires human with iPhone + LAN + llama-server.

Actions:

- Same `qwendea.md` as H2.1 (keep it small; this is a truth test, not a
  capacity test).
- Write `config.live.yaml` with one `endpoints:` entry for PRIMARY
  (`http://192.168.1.13:8080`, Qwen3.6-35B-A3B, 131072 ctx) and routing
  that sends every role to PRIMARY.
- `export ORCHESTRATOR_CONFIG=$(pwd)/config.live.yaml` and launch the
  PWA. Create project via iPhone on LAN. Gates ON. Start.
- Record wall-clock per phase, per-role token counts from `usage.jsonl`,
  any retries, any gate rejections/edits.

Acceptance:

- Pipeline reaches a green Reviewer verdict OR an honest failure with
  captured reason. Either is acceptable — what matters is that review /
  follow / intervene all worked as advertised throughout.
- No silent auto-approvals. No missing log lines. No hung phases.
- `usage.jsonl` shows realistic token counts (non-zero prompt + output).

Evidence:

```bash
ls /tmp/guildr-live-h2/.orchestrator/artifacts/
wc -l /tmp/guildr-live-h2/.orchestrator/logs/raw-io.jsonl
wc -l /tmp/guildr-live-h2/.orchestrator/events.jsonl
jq -s 'length' /tmp/guildr-live-h2/.orchestrator/usage.jsonl
```

## Task H2.4 — Multi-Endpoint Routing (PRIMARY + ALIEN)

Status: Not started. Replaces the old "pool parallelism" framing.

Rationale: opencode doesn't share a pool — each role spawns its own
subprocess. But the routing table in `endpoints:` lets us send different
roles to different endpoints (e.g. Coder → PRIMARY, Reviewer → ALIEN).
The win is no longer "concurrency via scheduling"; it's "role-appropriate
models and per-endpoint isolation."

Actions:

- Repeat H2.3's project with `config.live.yaml` declaring both PRIMARY
  and ALIEN, routing Coder/Tester/Deployer to PRIMARY and
  Architect/Reviewer/Judge to ALIEN (or whatever split makes sense for
  the two machines' specs).
- Confirm via `usage.jsonl` that each role's rows reference the expected
  endpoint.

Acceptance:

- `usage.jsonl` shows rows tagged to both endpoints within the same run.
- No endpoint errors, no config-shape drift between the two.
- `opencode.json` for the project declares both providers.

Evidence:

```bash
jq -c '{role: .role, provider: .provider.name}' \
  /tmp/guildr-live-h2-multi/.orchestrator/usage.jsonl | sort -u
```

## Task H2.5 — Freeze Reference Run

Status: Not started. Depends on H2.3 succeeding.

Actions:

- Copy the H2.3 run's `.orchestrator/` tree into `docs/reference-run/`.
- Write `docs/reference-run/README.md` describing the qwendea, the
  endpoint(s), the date, the wall-clock, and the outcome.
- Add `tests/test_reference_run_schema.py` that re-parses
  `events.jsonl`, `raw-io.jsonl`, and `usage.jsonl` with the current
  event/usage schemas. Guards against schema drift.

Acceptance:

- `docs/reference-run/` is checked in with artifacts + raw-io + events +
  usage.
- Schema validation test passes on the frozen reference.

Evidence:

```bash
uv run pytest -q tests/test_reference_run_schema.py
ls docs/reference-run/.orchestrator/
```

## Phase Exit Criteria

- One real project has been built end-to-end through the PWA against a
  live llama-server via opencode, with gates on.
- Multi-endpoint routing has been observed in practice (PRIMARY + ALIEN).
- A reference run is frozen in the repo as a regression anchor.
- `STATUS.md` headline can honestly say "live path verified end-to-end
  via opencode" — because it has been.

## Changes From The Pre-Opencode Plan

For anyone tracing git history:

- H2.3 in the old plan was "pool parallelism across LLMClient endpoints."
  That code is gone (pool machinery sunset). Reframed as H2.4
  "multi-endpoint routing" — same goal (prove both endpoints exercised),
  different mechanism (opencode per-role sessions, not a shared pool).
- Old H2.1 had a programmatic half and a manual half; the programmatic
  half landed in commit `6fbd055`. The manual half is still open.
- New H2.2 "opencode wiring smoke" did not exist in the old plan; it
  fills the gap between pure dry-run and real-LAN runs.
- `FakeLLMClient` is gone. Dry-run now means `dry_run=True`, which
  auto-wires `*_dryrun` SessionRunners per role.
