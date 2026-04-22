# M02 — Intent Lifecycle And Next-Step Packets

## Purpose

Make the next slated step inspectable and editable before it runs, and close the loop between "operator dropped in an intent" and "the system used it." This is the most useful operator moment — the one the map must always surface.

## Why this phase exists

SRS §4.6 and §9 require the operator can intervene. The PWA narrative design calls out Next-Step Control as a first-class layer. Today, intents are submitted but have no terminal outcome event, and there is no authoritative next-step packet. Intervention is theater without this phase.

## Required context files

- `docs/pwa-narrative-replay-and-intervention-design.md` §Next-Step Control Layer, §Intent Packet, Implementation Slices 1 & 5
- `docs/srs-council-engine.md` §4.6, §9
- `orchestrator/lib/workflow.py`
- `orchestrator/lib/control.py`
- `web/backend/routes/intents.py`
- `M01-event-ledger-foundation.md` (must be done)
- `QUALITY_GATES.md` G1, G6

## Implementation surface

- `orchestrator/lib/next_step.py` (deterministic packet generator)
- `orchestrator/lib/control.py` (intent outcome emission)
- `web/backend/routes/intents.py` (`client_intent_id` round-trip)
- `web/frontend/src/engine/EventEngine.ts` (`pendingIntents`, `appliedIntents`, `nextStepPacket` fold)
- `web/frontend/src/ui/NextStepSheet.tsx` (or equivalent)
- `.orchestrator/control/instructions.jsonl` (intent projection)

## Tasks

- [x] Define `next_step_packet_created` event schema (see design doc). Land in `event_schema.py`.
- [x] Build deterministic next-step selector: workflow state → next enabled incomplete step.
- [x] Emit `next_step_packet_created` at phase boundaries (after `phase_done`, after `gate_decided`, before a new phase opens, after `operator_intent`).
- [x] Assign `client_intent_id` in PWA; backend preserves it on every outcome event.
- [x] When `append_operator_context` (or whichever consumer) uses an instruction, emit `operator_intent_applied` with `applied_to`/`artifact_refs`.
- [x] If an intent is dropped (stale, step already done, scope mismatch), emit `operator_intent_ignored` with `reason`.
- [x] Frontend fold: `pendingIntents`, `appliedIntents[client_intent_id]`, `nextStepPacket`.
- [x] Frontend: Next-Step Sheet showing objective / why_now / context_preview / inputs / queued intents / actions.
- [x] Frontend: intent packet visual — queued → applied/ignored lifecycle on map.
- [x] Bottom HUD `Next: <step>` control always present.

## Quality gates

- [x] G6 Intent lifecycle — every submitted intent gets exactly one terminal outcome.
- [x] G1 Event integrity on all new event types.
- [x] G2 Replay — in replay mode the next-step packet shown is the one known at that event index.
- [x] G3 Mobile — Next-Step Sheet fits iPhone portrait; no overlap with HUD or map.
- [x] G4 No-dashboard — Next-Step surface is a sheet/lens over the map, not a table.

## Evidence commands / checks

```bash
uv run pytest -q tests/test_next_step.py tests/test_intents.py web/backend/tests/test_intents.py
uv run pytest -q web/frontend/tests/test_next_step_sheet.py web/frontend/tests/test_intent_lifecycle.py
./web/frontend/build.sh
# manual: drop an intent, confirm packet appears queued, then applied after next phase starts
```

## Done means

- [ ] Opening the PWA always shows `Next: <step>` in the bottom HUD.
- [x] Tapping `Next` opens a sheet with objective, inputs, context preview, and an intent composer.
- [x] Submitted intents become visible packets; state advances queued → applied/ignored.
- [x] Replay scrubbing shows the next-step packet that was known at that point.
- [x] No intent exits the system without a terminal outcome event.

## Known traps

- Generating the next-step packet purely on the frontend creates divergence between live and replay. Backend is authoritative; frontend may derive a tentative packet only as fallback when no `next_step_packet_created` has fired.
- An intent "used" by context assembly is not the same as "applied to a prompt." Emit `operator_intent_applied` only at the real consumption point.
- Do not silently coalesce two intents into one application without emitting one outcome per `client_intent_id`.

## Handoff notes

- M06 consumes the next-step packet to render the Next-Step Beam and Object View outgoing arcs.
- M05 (narrator) may overwrite the packet with richer `why_now`/`context_preview`; preserve intent lifecycle independently.

## Evidence log

- 2026-04-22 M02a deterministic packet slice: added `orchestrator/lib/next_step.py`, engine `next_step_packet_created` emission before phase start and after phase/gate approval, and EventEngine `nextStepPacket` replay fold. Packets include `memory_provenance()` output from M08. Evidence: `uv run pytest -q tests/test_next_step.py tests/test_engine.py web/frontend/tests/test_event_engine.py` -> 37 passed; `uv run pytest -q tests/test_next_step.py web/backend/tests/test_intents.py web/backend/tests/test_memory.py tests/test_memory_palace.py` -> 11 passed; `./web/frontend/build.sh` passed; `git diff --check` clean.
- 2026-04-22 M02B Steps 1-2: added durable `.orchestrator/control/intents.jsonl` registry, backend-generated `client_intent_id`, and `queued_intents` on next-step packets; EventEngine exposes `nextStepPacket.queuedIntents` in replay. Evidence: `uv run pytest -q web/backend/tests/test_intents.py tests/test_intents.py tests/test_next_step.py web/frontend/tests/test_event_engine.py` -> 13 passed; `./web/frontend/build.sh` passed; `git diff --check` clean.
- 2026-04-22 M02B Step 3: queued `interject` / `intercept` / `reroute` intents are consumed by prompt context assembly, marked `applied`, injected once, and emit `operator_intent_applied` when an event bus is present. Opencode-backed roles pass `state.events` through prompt augmentation. Evidence: `uv run pytest -q tests/test_intents.py tests/test_coder.py tests/test_reviewer.py tests/test_tester.py tests/test_deployer.py tests/test_architect_judge.py` -> 99 passed; `uv run pytest -q web/backend/tests/test_intents.py tests/test_next_step.py web/frontend/tests/test_event_engine.py` -> 11 passed; `./web/frontend/build.sh` passed; `git diff --check` clean.
- 2026-04-22 M02B Step 4: phase/gate completion scans queued intents and emits `operator_intent_ignored` for stale targeted intents or unsupported prompt kinds, updating registry rows idempotently. Evidence: `uv run pytest -q tests/test_intents.py tests/test_engine.py` -> 36 passed; `uv run pytest -q tests/test_coder.py tests/test_reviewer.py tests/test_tester.py tests/test_deployer.py tests/test_architect_judge.py web/frontend/tests/test_event_engine.py` -> 99 passed; `./web/frontend/build.sh` passed; `git diff --check` clean.
- 2026-04-22 M02B Step 5: EventEngine now folds `operator_intent`, `operator_intent_applied`, and `operator_intent_ignored` into replayable `pendingIntents`, `appliedIntents`, and `ignoredIntents`; current next-step packets also attach matching pending intents known after packet creation. Evidence: `uv run pytest -q web/frontend/tests/test_event_engine.py` -> 7 passed; `./web/frontend/build.sh` passed; `git diff --check` clean.
- 2026-04-22 M02B Step 6: GameShell bottom HUD now exposes an always-present `Next:` control backed by `snapshot.nextStepPacket`; tapping it opens a compact map sheet with objective, why-now, context, input/memory/source refs, queued/applied/ignored intents, and a `Nudge` action that opens the existing compose dock for the next step. Evidence: `uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py` -> 14 passed; `./web/frontend/build.sh` passed; Playwright desktop and mobile 393x852 checks showed no sheet/HUD overlap, sheet within viewport, and nonblank canvas signals; `git diff --check` clean.
- 2026-04-22 M02B Step 7: Added an end-to-end rehearsal covering backend project intent submission, durable queued registry rows, engine next-step packet emission, stale targeted intent terminal ignore, global intent retention for the next packet, and EventEngine replay folding from the combined ledger. Evidence: `uv run pytest -q tests/test_next_step.py tests/test_intents.py web/backend/tests/test_intents.py web/frontend/tests/test_event_engine.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py` -> 21 passed; `./web/frontend/build.sh` passed; `git diff --check` clean.
- 2026-04-22 M02C: `POST /intents` now emits a refreshed authoritative `next_step_packet_created` immediately after `operator_intent`, using the current project state/current phase when present. The end-to-end rehearsal now proves packet refresh after each submitted intent before engine execution continues. Evidence: `uv run pytest -q web/backend/tests/test_intents.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py` -> 3 passed; `uv run pytest -q tests/test_next_step.py tests/test_intents.py web/backend/tests/test_intents.py web/frontend/tests/test_event_engine.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py` -> 22 passed; `./web/frontend/build.sh` passed; `git diff --check` clean.
- 2026-04-22 M02D: GameShell now generates a `client_intent_id` before every map compose submission and includes it in the `POST /intents` body for `interject`, `intercept`, and `reroute` actions. Evidence: `uv run pytest -q web/frontend/tests/test_game_map.py` -> 7 passed; `uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py web/backend/tests/test_intents.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py` -> 17 passed; `./web/frontend/build.sh` passed; `git diff --check` clean.
- 2026-04-22 M02E: SceneManager now renders persistent 3D intent packet sprites above target atoms from snapshot `pendingIntents`, `appliedIntents`, and `ignoredIntents`; queued/applied/ignored states use distinct billboard glyphs and remain ledger-derived. Evidence: `uv run pytest -q web/frontend/tests/test_game_map.py` -> 7 passed; `uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py` -> 14 passed; `./web/frontend/build.sh` passed; Playwright desktop and mobile 393x852 checks showed no sheet/HUD overlap, sheet within viewport, and nonblank canvas signals 103408/107370; `git diff --check` clean.
