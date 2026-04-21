# Phase 5 - Operator Touch Control

## Goal

Make the user a visible force in the orchestration universe. Shape, Nudge, and
Intercept should start from spatial gestures and remain ergonomic on mobile
Safari.

## Required Context

- `docs/spatial-flow-universe-design.md`
- `web/frontend/src/game/GameShell.ts`
- `web/frontend/src/game/SceneManager.ts`
- `web/backend/routes/intents.py`
- `web/backend/tests/test_intents.py`

## Implementation Surface

- `web/frontend/src/game/interactions/GhostTether.ts`
- `web/frontend/src/game/GameShell.ts`
- `web/frontend/src/game/SceneManager.ts`
- `web/backend/routes/intents.py`
- frontend mobile map tests

## Task 5.1 - Long-Press Intercept

Status: Not started

Actions:

- Add long-press on atom/gate to open Intercept directly.
- While held, show amber stop shell around the target.
- On submit, persist `operator_intent(kind="intercept")`.
- Add haptic feedback where supported.

Acceptance:

- Touch interaction works on iPhone portrait dimensions.
- The visual shell appears before text confirmation.
- Canceling the compose dock removes pending shell state.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py web/backend/tests/test_intents.py
./web/frontend/build.sh
```

## Task 5.2 - Drag Atom To Atom Ghost Tether

Status: Not started

Actions:

- Implement `GhostTether`.
- Dragging from one atom creates a temporary curved tether.
- Hover/target atom highlights when reroute is valid.
- Release opens Shape compose dock.
- Submit persists `operator_intent(kind="reroute")`.

Acceptance:

- User can spatially express "send this work over there."
- Invalid targets visibly reject without errors.
- Ghost tether disappears cleanly on cancel.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py web/backend/tests/test_intents.py
./web/frontend/build.sh
```

## Task 5.3 - Drag Empty Space To Atom Nudge

Status: Not started

Actions:

- Drag from empty canvas toward an atom to create a user beam.
- Release opens Nudge compose dock.
- Submit persists `operator_intent(kind="interject")`.

Acceptance:

- The user can inject instruction without first opening a panel.
- Beam color/energy clearly differs from normal flow.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py web/backend/tests/test_intents.py
./web/frontend/build.sh
```

## Task 5.4 - Intent Replay State

Status: Not started

Actions:

- Fold pending/applied/rejected operator intent state into `EventEngine`.
- Show intent packets during replay.
- Scrubbing backward reverses or freezes intent packets correctly.

Acceptance:

- User can see what intervention happened and when.
- Replay does not depend on transient compose state.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Phase Exit Criteria

- Shape/Nudge/Intercept can be started spatially.
- Submitted intents are visible as physical events.
- Replay can explain interventions.
- Mobile touch behavior is reliable.
