# Phase 3 - Model Catalog And Actors

## Goal

Use the Ultimate Space Kit as a semantic visual language for the orchestration
engine: astronauts, mechs, rovers, ships, planets, facilities, tokens, and
connectors should mean specific things.

## Required Context

- `docs/spatial-flow-universe-design.md`
- `assets/poly-pizza/ultimate-space-kit/README.md`
- `assets/poly-pizza/ultimate-space-kit/manifest.json`
- `web/frontend/src/game/assets/manifest.ts`
- `web/frontend/src/game/assets/AssetManager.ts`
- `web/frontend/src/game/SceneManager.ts`

## Implementation Surface

- `web/frontend/src/game/models/ModelCatalog.ts`
- `web/frontend/src/game/models/CharacterActor.ts`
- `web/frontend/src/game/models/AnimationDirector.ts`
- `web/frontend/src/game/assets/manifest.ts`
- `web/frontend/src/game/SceneManager.ts`
- frontend asset tests

## Task 3.1 - Add Ultimate Space Kit To Runtime Manifest

Status: Not started

Actions:

- Add selected deferred model entries for the first semantic subset:
  - one astronaut,
  - one mech,
  - one rover or round rover,
  - one spaceship,
  - one connector,
  - one geodesic dome or radar,
  - two or three planet variants.
- Keep `ultimate-space-kit/manifest.json` itself fetchable as deferred data.
- Do not add these assets to service-worker precache.

Acceptance:

- AssetManager can fetch the semantic subset by id.
- Service worker still precaches only core assets.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_asset_manager.py web/backend/tests/test_pwa_serving.py
./web/frontend/build.sh
```

## Task 3.2 - Implement ModelCatalog

Status: Not started

Actions:

- Load and cache `ultimate-space-kit/manifest.json`.
- Expose semantic queries:
  - `modelsForCategory(category)`
  - `modelsForStage(loopStage)`
  - `modelForRole(role)`
- Include path, bytes, animation metadata, and design role.
- Fail gracefully if manifest is unavailable.

Acceptance:

- Tests can query `implementation/build -> mech`, `testing/verify -> rover`,
  `deployment/ship -> spaceship`, and `operator/review -> astronaut`.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_asset_manager.py
./web/frontend/build.sh
```

## Task 3.3 - Implement CharacterActor

Status: Not started

Actions:

- Wrap GLTF scene loading, scale normalization, and origin normalization.
- Add `AnimationMixer` support.
- Provide high-level states:
  - `idle`
  - `working`
  - `approving`
  - `rejecting`
  - `blocked`
  - `repairing`
  - `selected`
- Map those states to available animation names.

Acceptance:

- Astronaut can play `Idle`, `Wave`, `Yes`, `No`, and `HitReact` when present.
- Mech can play `Idle`, `Run`, `Pickup`, `Shoot_*`, and `HitRecieve_*` when
  present.
- Missing animation names fall back to `Idle` without crashing.

Evidence:

```bash
./web/frontend/build.sh
```

## Task 3.4 - Implement AnimationDirector

Status: Not started

Actions:

- Convert `EngineSnapshot` and recent events into actor animation states.
- Stage examples:
  - `phase_start implementation`: mech `working`.
  - `phase_start testing`: rover active/patrol motion.
  - `gate_decided approved`: astronaut `Yes`.
  - `gate_decided rejected`: astronaut `No`, artifact repair backflow.
  - `provider_call_error`: actor `blocked`.
  - `operator_intent`: operator astronaut `Wave` or touch beam.
- On mobile, animate only focused or active cluster actors at full rate.

Acceptance:

- Focused active stage has a visible semantic actor.
- Other stages remain lightweight static props or silhouettes.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Phase Exit Criteria

- Ultimate Space Kit semantic subset is in the asset manifest.
- ModelCatalog and CharacterActor exist.
- At least one actor appears and animates for a real engine stage.
- Mobile does not load or animate the full kit.
