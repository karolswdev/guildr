# M01 — Event Ledger And Replay Foundation

## Purpose

Make `.orchestrator/events.jsonl` the canonical run stream: every SSE event durable, every event self-describing, every reader safe against unknown schema versions. Every downstream mini-phase folds from here.

## Why this phase exists

All narrative, intent, cost, and loop state is a projection over events. If the ledger is lossy, untyped, or missing `event_id`/`schema_version`, every downstream lens lies. SRS §4.5, §8, §14 M1 all depend on this.

## Required context files

- `docs/srs-council-engine.md` §3, §4.5, §8, §14 M1
- `docs/pwa-narrative-replay-and-intervention-design.md` (Event Architecture section)
- `orchestrator/lib/event_schema.py`
- `orchestrator/lib/raw_io.py`
- `web/backend/routes/stream.py`
- `web/frontend/src/engine/EventEngine.ts` (or equivalent fold)
- `QUALITY_GATES.md` G1, G2

## Implementation surface

- `orchestrator/lib/events.py` (central emitter, if not present; otherwise extend)
- `orchestrator/lib/event_schema.py` (schema_version constants, validators)
- `.orchestrator/events.jsonl` (persistence contract)
- `web/backend/routes/events.py` + `stream.py` (history API, SSE)
- `web/frontend/src/engine/EventEngine.ts` (fold, dedup-by-event_id)
- Tests in `tests/` and `web/frontend/tests/`

## Tasks

- [ ] Audit every current emit site. List the ones that don't write `event_id`, `schema_version`, `ts`, `type`, `run_id`.
- [ ] Add a single `emit_event()` helper that enforces the five required fields and routes to both SSE bus and `events.jsonl`.
- [ ] Migrate emitters to the helper. Delete ad-hoc dict construction at call sites.
- [ ] Add `SCHEMA_VERSION = 1` constant; readers must raise on unknown values.
- [ ] Backend: persist every SSE event. Never stream without persisting.
- [ ] Backend: `GET /api/projects/{id}/events?since=<event_id>&types=<csv>&step=<id>` history API.
- [ ] Frontend `EventEngine`: dedupe strictly by `event_id`; do not use `ts`.
- [ ] Frontend: on boot, load history via `GET /events` before opening SSE (concat, dedupe, fold).
- [ ] Document the event registry (types + schemas) in `orchestrator/lib/event_schema.py` docstring.
- [ ] Reject events that reference absolute paths; enforce relative-to-project-root.

## Quality gates

- [ ] G1 Event integrity — all five required fields on every event type.
- [ ] G2 Replay determinism — folding events [0..N] is pure; no wall-clock, no random.
- [ ] G8 Security — scrub runs before persistence; no secrets in `events.jsonl`.
- [ ] G10 Handoff — glossary updated if new primitives.

## Evidence commands / checks

```bash
uv run pytest -q tests/test_events.py web/backend/tests/test_events.py
uv run pytest -q web/frontend/tests/test_event_engine.py
git diff --check
jq -c 'select(.event_id == null or .schema_version == null or .ts == null or .type == null or .run_id == null)' \
  <project>/.orchestrator/events.jsonl   # must return zero lines
```

## Done means

- [ ] Every event in a fresh dry-run carries the five required fields.
- [ ] History API returns the same records that SSE streamed, in order.
- [ ] Frontend recovers full UI state after a refresh using only history API + SSE.
- [ ] A stray `schema_version: 99` event causes a loud reader error, not silent drop.
- [ ] `rollup()` and existing `raw-io`/`usage` joins still pass.

## Known traps

- SSE emits that bypass `events.jsonl` — any new emit site added later will silently regress replay. Enforce via a single helper.
- `ts` is not unique within a run: never dedupe on it.
- Event payload secret leakage: scrub at emit, not at render.
- Async emission ordering: persist synchronously before SSE fan-out so history never lags live.

## Handoff notes

- Register new event types introduced by M02–M05 here (they add payloads, not required fields).
- Add a glossary entry in `../AGENT_ONBOARDING.md` under "event_id" and "schema_version" if not present.
- Surface M01 in STATUS.md Evidence Log with exact pytest pass counts.
