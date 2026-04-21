# Harness 2 - Live-Path Battle Test

## Goal

Run a real project, end-to-end, against the live llama-server pool with
gates on, from the PWA. Capture the artifacts as a reference run so future
regressions of the live path are detectable.

## Why this is third

Harness 0 gives us audit trails. Harness 1 gives us control. This phase
proves both work under real LLM load, not just `FakeLLMClient`. The 438
passing tests today prove the dry-run pipeline works; they do not prove the
live path works. Without this phase, we cannot honestly market "first-class
review / follow / intervene" — the claim has never been executed.

## Required Context

- Memory: `project_orchestrator.md` — PRIMARY (192.168.1.13) and ALIEN
  (192.168.1.70) endpoint facts, Qwen3.6-35B-A3B Q5/Q6, 131072 ctx
- `orchestrator/lib/pool.py` — role → endpoint routing
- `web/backend/runner.py` — the live-path entry point
- The just-completed Harness 0 (`raw-io.jsonl`) and Harness 1 (single gate
  registry) — both must be in before this phase starts

## Implementation Surface

- No product code changes expected. If any land, they're fixes surfaced by
  the run.
- New directory: `docs/reference-run/` — frozen artifacts from one real run
  checked into the repo as a regression anchor.

## Task H2.1 - Dry-Run Rehearsal With Real Capture

Status: Programmatic half done 2026-04-21 (commit 6fbd055). Manual PWA walk-through pending.

Actions:

- Pick a deliberately small `qwendea.md` (single-file utility, e.g.
  "python CLI that formats JSON with sorted keys").
- Run the full pipeline against `FakeLLMClient` with Harness 0 and Harness 1
  shipped.
- Verify `raw-io.jsonl` line count matches expected role calls.
- Verify each gate can be approved from the PWA.

Pick-up notes for the manual half:

- Programmatic guard: `tests/test_integration_h2_1_rehearsal.py` drives the
  same `_run_orchestrator` + HTTP-decide code path a human hits from the
  PWA. Keep it green before/after the manual walk.
- Manual walk still required: `./web/frontend/build.sh` → start the PWA on
  `0.0.0.0` on LAN → create a project with the JSON-formatter qwendea →
  toggle "Gate my approval at each phase" ON → Start → approve each gate
  as it surfaces → confirm run_complete and inspect
  `<project>/.orchestrator/logs/raw-io.jsonl`.
- Capture evidence: screenshot of each gate prompt, `wc -l` of
  `raw-io.jsonl`, and the final phase event timeline.

Acceptance:

- Full pipeline completes via PWA with human gates approved manually.
- `raw-io.jsonl` contains one record per LLM call, prompts and responses
  both present.

Evidence:

```bash
wc -l /tmp/guildr-rehearsal/.orchestrator/logs/raw-io.jsonl
uv run pytest -q  # full suite still green
```

## Task H2.2 - Live Run Against PRIMARY

Status: Not started

Actions:

- Same `qwendea.md` as H2.1.
- Point the runner at PRIMARY (192.168.1.13:8080) with `BUILD_PRIMARY=primary`.
- Execute through the PWA on an iPhone, on LAN, with gates on.
- Record wall-clock time per phase, per-role token counts, any retries,
  any gate rejections/edits.

Acceptance:

- Pipeline reaches a green Reviewer verdict or an honest failure with a
  captured reason. Either outcome is acceptable — what matters is that
  review / follow / intervene all worked as advertised throughout.
- No silent auto-approvals. No missing log lines. No hung phases.

Evidence:

```bash
# run captured in .orchestrator/logs and artifacts
ls /tmp/guildr-live-h2/.orchestrator/artifacts/
wc -l /tmp/guildr-live-h2/.orchestrator/logs/raw-io.jsonl
wc -l /tmp/guildr-live-h2/.orchestrator/events.jsonl
```

## Task H2.3 - Parallel Run Across Pool

Status: Not started

Actions:

- Repeat H2.2 but with a `qwendea.md` that produces a sprint plan large
  enough that Coder and Reviewer can overlap.
- Confirm PRIMARY handles Coder while ALIEN handles Reviewer concurrently
  (see `upstream-contract.md` routing).
- Measure wall-clock savings vs. a serialized run.

Acceptance:

- Pool routing logs show both endpoints active in the same wall-clock window.
- No endpoint serialization violations (each endpoint still `-np 1`).

Evidence:

```bash
# filter pool.py logs for endpoint assignments
grep -E "endpoint=(primary|alien)" /tmp/guildr-live-h2-parallel/.orchestrator/logs/*.jsonl | head
```

## Task H2.4 - Freeze Reference Run

Status: Not started

Actions:

- Copy the H2.2 run's `.orchestrator/` tree into `docs/reference-run/`.
- Write `docs/reference-run/README.md` describing the qwendea, the endpoint,
  the date, the wall-clock, and the outcome.
- Add a lightweight test that validates the reference run structure still
  parses with current event schemas (guards against future schema drift).

Acceptance:

- `docs/reference-run/` is checked in with artifacts + raw-io + events.
- Schema validation test passes on the frozen reference.

Evidence:

```bash
uv run pytest -q tests/test_reference_run_schema.py
ls docs/reference-run/.orchestrator/
```

## Phase Exit Criteria

- One real project has been built end-to-end through the PWA against a live
  llama-server with gates on.
- Pool parallelism has been observed in practice.
- A reference run is frozen in the repo as a regression anchor.
- `STATUS.md` headline can honestly say "live path verified end-to-end" —
  because it has been.
