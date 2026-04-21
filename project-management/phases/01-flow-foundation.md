# Phase 1 - Flow Foundation

## Goal

Turn generic tethers and pulses into a testable flow system that can represent
sequence, memory, gate, review, repair, cost, replay, and operator intent.

## Required Context

- `docs/spatial-flow-universe-design.md`
- `web/frontend/src/game/SceneManager.ts`
- `web/frontend/src/game/atoms/EdgeMesh.ts`
- `web/frontend/src/game/EventEngine.ts`
- `web/frontend/src/game/types.ts`
- `web/frontend/tests/test_game_map.py`

## Implementation Surface

Create or evolve:

- `web/frontend/src/game/flows/FlowTypes.ts`
- `web/frontend/src/game/flows/FlowPath.ts`
- `web/frontend/src/game/flows/FlowParticles.ts`
- `web/frontend/src/game/flows/FlowDirector.ts`
- `web/frontend/src/game/atoms/EdgeMesh.ts`
- `web/frontend/src/game/SceneManager.ts`

## Task 1.1 - Define Flow Types

Status: Done

Actions:

- Add `FlowKind`:
  - `sequence`
  - `planning`
  - `implementation`
  - `gate`
  - `review`
  - `repair`
  - `memory`
  - `cost`
  - `intent`
  - `replay`
- Add `FlowMode`:
  - `idle`
  - `active`
  - `queued`
  - `blocked`
  - `reversing`
  - `selected`
- Add command types for path mode, pulse spawn, dust spawn, repair backflow,
  memory stream, and replay freeze/reverse.

Acceptance:

- Types compile and can be imported without bringing in Three.js.
- Flow command mapping can be unit tested outside WebGL.

Evidence:

```bash
./web/frontend/build.sh
```

## Task 1.2 - Promote EdgeMesh Into FlowPath

Status: Done

Actions:

- Move curve ownership from `EdgeMesh` into `FlowPath`.
- Preserve current visible curved tethers and pulse movement.
- Keep `EdgeMesh` as a thin compatibility wrapper if that reduces churn.
- Add mode-driven material/color behavior.

Acceptance:

- Current map still renders with curved tethers.
- Existing pulse behavior remains visible.
- `FlowPath.pointAt(t)` and tangent helpers exist.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Task 1.3 - Add FlowParticles Pool

Status: In progress

Actions:

- Replace ad hoc pulse sprite ownership in `SceneManager` with a pooled
  `FlowParticles` module.
- Support particle color, size, speed, lifetime, path id, and optional event id.
- Avoid per-frame object allocation.
- Keep mobile active-particle budget under 250.

Acceptance:

- Pulses still move along path curves.
- Old particles are reused or disposed deterministically.
- No particle creation occurs for every animation frame.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Task 1.4 - Add FlowDirector Event Mapping

Status: Not started

Actions:

- Add `FlowDirector` that receives `EngineSnapshot` and recent events.
- Map event types to flow commands:
  - `atom_started` / `phase_start`: active incoming pulse.
  - `atom_completed` / `phase_done`: outgoing completion pulse.
  - `usage_recorded`: cost dust.
  - `provider_call_error`: red fracture/backflow.
  - `loop_entered`: loop field activation.
  - `loop_blocked`: blocked/backflow.
  - `loop_repaired`: repair arc.
  - `budget_gate_opened`: amber queue.
  - `budget_gate_decided`: approve/reject burst.
  - `operator_intent`: user-origin pulse.
- Keep mapping pure enough for tests.

Current progress:

- `FlowDirector` maps ledger events to path, pulse, dust, backflow, intent, and
  replay commands.
- `SceneManager` consumes those commands to change tether mode/kind.
- Particle pooling is still pending, so visual pulses still use the existing
  scene-owned sprite path for now.

Acceptance:

- Event-to-command mapping is tested without WebGL.
- SceneManager no longer contains ad hoc event-specific flow logic.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Phase Exit Criteria

- FlowPath, FlowParticles, and FlowDirector exist.
- Current visuals are preserved or improved.
- Flow command mapping is tested.
- Mobile map smoke remains nonblank and interactive.
