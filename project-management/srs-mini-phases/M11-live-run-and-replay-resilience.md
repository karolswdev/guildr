# M11 — Live Run And Replay Resilience

## Purpose

Make runs survive: PWA refresh, server restart, SSE reconnect, partial crashes, and mid-phase interruptions leave durable, replayable state. Replay supports play/pause/scrub/filter/export over every projection (narrative, intent, cost, SDLC loop).

## Why this phase exists

SRS §13 Reliability + §8 Replay. A tactical command room that forgets on refresh is theater. Loop state (§8.2) must be derivable from events — folding, not UI state. This phase is where "follow/review/intervene" finally becomes honest end-to-end.

## Required context files

- `docs/srs-council-engine.md` §8, §8.2, §13
- `docs/sdlc-loop-visualization.md`
- `web/backend/routes/stream.py` (SSE)
- `web/frontend/src/engine/EventEngine.ts`
- `M01-event-ledger-foundation.md` (must be done)
- `QUALITY_GATES.md` G2, G9

## Implementation surface

- Backend SSE: `Last-Event-ID` header support; replay buffer keyed on `event_id`.
- `orchestrator/lib/loops.py` (fold events into loop state: discover/plan/build/verify/repair/review/ship/learn)
- Events: `loop_entered`, `loop_blocked`, `loop_repaired`, `loop_completed` (some exist; extend)
- Replay viewer: play / pause / ff / rewind / scrub / filter / export bundle
- Export bundle: `.orchestrator/exports/<run_id>.zip` containing events, artifacts, rate-cards, memory wake-up hash

## Tasks

- [ ] SSE resume: client sends `Last-Event-ID`; server replays from that point.
- [ ] PWA reboot: load `GET /events?since=<latest_known_event_id>` then open SSE with `Last-Event-ID`.
- [ ] Loop state derivation: pure fold of events. Failed verification visibly transitions atom into repair. Guru escalation = repair sub-loop. MemPalace sync = learn loop.
- [ ] SDLC loop lane/band visual (owned by M06, data contract owned here).
- [ ] Replay controls: play/pause/ff/rewind/scrub by event index or time, filter by phase/role/type/error/gate/memory/advisor/loop stage.
- [ ] Artifact diff view when event carries `artifact_refs`.
- [ ] Cost/token counters + budget state shown as of replay point (via M09 snapshot).
- [ ] Export replay bundle: events, referenced artifacts, rate-card snapshot, workflow JSON, memory wake-up hash — zipped.
- [ ] Crash resilience: engine on restart reads last good state from events; never requires recomputing filesystem state.
- [ ] Regression test: kill the server mid-phase, restart, confirm replay reconstructs UI identically.

## Quality gates

- [ ] G2 Replay determinism — snapshot(events[0..N]) identical live vs. replay.
- [ ] G9 Accessibility — replay controls keyboard navigable; scrubber has textual fallback.
- [ ] G1 Event integrity on loop events.
- [ ] G3 Mobile — scrubber and filter UI usable in portrait.

## Evidence commands / checks

```bash
uv run pytest -q tests/test_loop_fold.py tests/test_sse_reconnect.py tests/test_replay_export_bundle.py
uv run pytest -q tests/test_integration_crash_resilience.py
# manual: refresh PWA mid-run; confirm UI reconstructs without re-running
```

## Done means

- [ ] Refreshing the PWA mid-run reconstructs identical UI from history + SSE resume.
- [ ] Server restart preserves history; replay produces the same projection.
- [ ] Loop state = pure fold; no mutable UI state leaks into lane rendering.
- [ ] Replay scrub shows narrative, cost, loop, next-step snapshots as of the selected event.
- [ ] Export bundle opens offline and renders the full run (events + artifacts + rate-cards).

## Known traps

- Deduping on `ts` instead of `event_id` causes "missing events after reconnect" — hard invariant.
- Replay that mutates live workflow config is a design bug; replay is read-only.
- Loop state computed from mutable UI toggles regresses the whole principle. Derive, never store.

## Handoff notes

- M06 consumes loop stages for the SDLC band visual.
- M09 snapshot is the cost source for replay; do not bypass.
- M12 release gate requires a green crash-resilience test.
