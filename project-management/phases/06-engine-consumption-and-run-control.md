# Phase 6 - Engine Consumption And Run Control

## Goal

Close the loop between visible operator intent and the live orchestration
engine. The PWA should not merely record interventions; it should be able to
shape a running session.

## Required Context

- `web/backend/routes/intents.py`
- `web/backend/routes/control.py`
- `orchestrator/engine.py`
- `orchestrator/lib/control.py`
- `orchestrator/lib/events.py`
- `docs/srs-council-engine.md`
- `docs/spatial-flow-universe-design.md`

## Implementation Surface

- Backend intent persistence and state.
- Orchestrator run loop interruption points.
- Control routes.
- Event emission for intent applied/rejected.
- Frontend EventEngine folding.

## Task 6.1 - Define Intent Lifecycle Events

Status: Not started

Actions:

- Keep existing `operator_intent`.
- Add durable lifecycle events:
  - `operator_intent_applied`
  - `operator_intent_rejected`
  - `operator_intent_expired`
- Include:
  - `operator_intent_id`
  - `client_intent_id`
  - `kind`
  - `target_atom_id`
  - `reason`
  - `applied_at_phase`
  - `caused_by_event_id` when available.

Acceptance:

- Replay can distinguish submitted, applied, rejected, and expired intents.
- Events avoid secrets and oversized prompt payloads.

Evidence:

```bash
uv run pytest -q web/backend/tests/test_intents.py tests/test_events.py
```

## Task 6.2 - Add Engine Checkpoints For Intents

Status: Not started

Actions:

- Add safe interrupt checkpoints between phases and before gates.
- Consume pending intents for:
  - `intercept`
  - `resume`
  - `retry`
  - `skip`
  - `reroute`
  - `interject`
- Keep behavior deterministic and auditable.

Acceptance:

- `intercept` can pause/halt at a safe boundary.
- `interject` appends operator context for the relevant phase.
- Unsupported intent kinds emit rejected lifecycle events.

Evidence:

```bash
uv run pytest -q tests/test_engine.py web/backend/tests/test_intents.py
```

## Task 6.3 - Wire Reroute And Retry Semantics

Status: Not started

Actions:

- Define exact semantics for rerouting a phase or artifact dependency.
- Keep reroute conservative: propose next phase/target, do not mutate history.
- Add retry semantics using existing control and phase retry behavior.
- Emit lifecycle events for each outcome.

Acceptance:

- Reroute has explicit constraints and rejection reasons.
- Retry produces a visible repair loop event.

Evidence:

```bash
uv run pytest -q tests/test_engine.py web/backend/tests
```

## Task 6.4 - Reflect Intent Outcomes In PWA

Status: Not started

Actions:

- Fold lifecycle events into `EventEngine`.
- Update flow/intent visuals:
  - applied turns teal/green,
  - rejected snaps red/amber back to source,
  - expired fades to grey.

Acceptance:

- User can tell whether their intervention changed the run.
- Replay shows intent outcome at the correct point in time.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Phase Exit Criteria

- Operator intents affect live orchestration at safe boundaries.
- Outcomes are durable and replayable.
- PWA visual state matches backend/engine decisions.
