# Agent In-Progress Memory Dump

This file is a high-signal handoff packet for any agent picking up the Council
PWA sprint work. It is intentionally operational and copy/paste friendly.

## Current Sprint Thread

Primary sprint plan:

- `docs/sprint-plan-council-pwa.md`

The sprint goal is to make the Council Engine replayable from durable events,
with cost, local llama.cpp telemetry, SDLC loops, and eventually a Three.js PWA
map all driven by the same `EventEngine`.

The core idea to keep spreading through the codebase:

> The event ledger is the product spine. Live UI, replay UI, cost HUD, loop
> state, memory visualization, and the future Three.js map all fold the same
> durable event stream. No important run state should live only in mutable DOM
> state or only in transient Python objects.

## Completed In This Work Session

### Task 1 - Event Schema And Ledger Hardening

Implemented durable event identity and validation.

Important files:

- `orchestrator/lib/event_schema.py`
- `orchestrator/lib/events.py`
- `web/backend/routes/stream.py`
- `web/backend/routes/events.py`
- `web/backend/runner.py`
- `web/frontend/src/views/Progress.ts`
- `web/backend/tests/test_events.py`
- `tests/test_events.py`

What changed:

- Persisted project events now get `event_id`, `schema_version`, `ts`, `type`,
  and `run_id`.
- `event_id` is ULID-style Crockford base-32.
- History reads reject invalid ledger events and unknown future
  `schema_version`.
- History/SSE dedupe by `event_id`, not timestamp.
- The orchestrator bridge preserves event identity when mirroring internal
  events to the SSE bus.

### Task 2 - Provider Usage Event Emission

Implemented normalized usage/error event emission for existing LLM/advisor
call paths.

Important files:

- `orchestrator/lib/usage.py`
- `orchestrator/lib/llm.py`
- `orchestrator/lib/state.py`
- `orchestrator/roles/base.py`
- `orchestrator/roles/architect.py`
- `orchestrator/roles/persona_forum.py`
- `orchestrator/roles/guru_escalation.py`
- `orchestrator/ingestion/quiz.py`
- `tests/test_usage_events.py`

What changed:

- LLM/advisor paths emit `usage_recorded`.
- Failed provider calls emit `provider_call_error` and a zero/partial
  `usage_recorded` when available.
- Prompts, Authorization headers, API keys, and secret-like metadata are not
  included in usage payloads.
- Canonical cost fields are nested under `cost`, while older flat fields like
  `cost_usd`, `source`, and `confidence` remain for compatibility.

### Task 3 - llama.cpp Telemetry Normalization

Claude implemented this slice using:

```bash
claude -p --model opus --permission-mode acceptEdits --add-dir /Users/karol/dev/projects/llm-projects/build/workspace
```

No limit flags were passed.

Important files:

- `orchestrator/lib/llm.py`
- `orchestrator/lib/usage.py`
- `orchestrator/lib/local_cost.py`
- `tests/test_llamacpp_telemetry.py`

What changed:

- `LLMResponse` now carries `model`, `usage_metadata`, `cost_usd`, and
  `timings`.
- llama.cpp `timings` map:
  - `prompt_n` -> input/processed prompt tokens when OpenAI usage is absent.
  - `cache_n` -> `cache_read_tokens`.
  - `predicted_n` -> output tokens.
  - prompt/predicted ms and throughput -> `runtime.llamacpp`.
- Local cost estimate uses versioned local rate cards under
  `.orchestrator/costs/rate-cards/local-*.json`.
- `LLMClient.metrics()` fetches `/metrics` and `/slots` supplementally and
  returns `None` on failure.

### Task 4 - Budget Gates And Cost Folding

Implemented the first durable budget gate surface and additive frontend cost
folding.

Important files:

- `web/backend/routes/gates.py`
- `web/backend/tests/test_gates.py`
- `web/frontend/src/game/EventEngine.ts`
- `web/frontend/src/game/types.ts`

What changed:

- Budget gates (`budget*`, `budget_*`, `budget-*`) emit:
  - `budget_gate_opened`
  - `budget_gate_decided`
- `budget_gate_decided` records `budget_at_decision`, and replay must use that
  instead of recomputing remaining budget.
- `EventEngine` folds usage and budget events into `CostSnapshot`.
- Rejected budget gates set `runHalted`, but replay continues folding later
  events for display.

### Task 5 - SDLC Loop Event Emission

Implemented loop event emission at phase lifecycle boundaries.

Important files:

- `orchestrator/lib/loops.py`
- `orchestrator/engine.py`
- `tests/test_engine.py`

What changed:

- Phase starts emit `loop_entered`.
- Phase completions emit `loop_completed`.
- Exceptions emit `loop_blocked`.
- Validator retries emit `loop_blocked` for the current stage and
  `loop_repaired` with `loop_stage="repair"`.
- `memory_refresh` maps to `learn`.
- `guru_escalation` maps to `repair`.
- Gates emit review loop events when the blocking gate path is active.

### Task 6 - Started / Partially Integrated

Current turn started Task 6: EventEngine extraction/integration, and completed
the first safe integration slice. A follow-up continuation also landed more
Progress integration.

Important files now being touched:

- `web/frontend/src/game/EventEngine.ts`
- `web/frontend/src/game/types.ts`
- `web/frontend/src/views/Progress.ts`
- `web/frontend/tests/test_event_engine.py`

Current direction:

- `EventEngine` is becoming the single pure frontend reducer for:
  - event history and SSE dedupe,
  - atom state,
  - cost state,
  - loop state,
  - memory status,
  - `scrubTo(index)` and `resumeLive()`.
- Progress still keeps its existing DOM renderers, but now mirrors workflow
  board state from `EventEngine` snapshots.
- Progress now loads history before opening SSE.
- `web/frontend/tests/test_event_engine.py` bundles `EventEngine.ts` with
  esbuild and runs Node fixture tests for atom replay, cost replay, and loop
  replay.
- Progress timeline/detail/focus now consume `EventEngine` snapshots instead
  of maintaining a parallel event-history/dedupe/fold path.
- Progress has a scrub range control; clicking a timeline event calls
  `EventEngine.scrubTo(index)`, and Follow Live calls `resumeLive()`.
- `EventEngine.applyEvent()` emits a snapshot when live events arrive while
  replay is scrubbed, so history length advances without moving the replay
  cursor.

Important next step:

- Continue tightening Progress around `EventEngine` snapshots for cost/loop HUD
  surfaces if those get visible UI. Keep the current UI behavior intact. Do not
  do Three.js rendering yet.

### Task 7 - AssetManager And Runtime Asset Manifest

Implemented the first asset-management foundation for the future Three.js map.

Important files:

- `web/frontend/src/game/assets/manifest.ts`
- `web/frontend/src/game/assets/AssetManager.ts`
- `web/frontend/src/app.ts`
- `web/frontend/sw.js`
- `web/backend/app.py`
- `web/backend/tests/test_pwa_serving.py`
- `web/frontend/tests/test_asset_manager.py`
- `web/frontend/tests/test_pwa.py`

What changed:

- Centralized vendored runtime asset paths under `/assets`.
- Backend now serves the repo-root `assets/` directory at `/assets`.
- `AssetManager` loads and caches core/deferred assets through `fetch`, exposes
  progress, returns placeholders for missing optional assets, and rejects
  reference-only runtime loads.
- App shell starts preloading core visual assets and exposes loading progress.
- Service worker precaches only runtime-critical core assets.
- HDRI is deferred; `post-processing-refs/lensDirt1.png` is reference-only and
  excluded from core/service-worker loading.

Important next step:

- Task 8 can start the first Three.js map route using `AssetManager` and
  `EventEngine` snapshots. Keep WebGL fallback usable and do not frame the
  scene in a decorative card.

### Task 8 - First Three.js Map Route

Implemented the first tangible map route with a minimal Three.js scene and DOM
fallback.

Claude/Opus was used as a read-only parallel reviewer for the Task 8 shape. It
flagged the Three.js dependency/build path, iPhone DPR/safe-area risks,
WebGL fallback, context-loss handling, and avoiding unbounded scene rebuilds.
Concrete items from that review were folded into the slice.

Important files:

- `web/frontend/package.json`
- `web/frontend/build.sh`
- `web/frontend/src/views/Map.ts`
- `web/frontend/src/game/GameShell.ts`
- `web/frontend/src/game/SceneManager.ts`
- `web/frontend/src/game/layout.ts`
- `web/frontend/src/game/atoms/AtomNode.ts`
- `web/frontend/src/game/atoms/EdgeMesh.ts`
- `web/frontend/src/app.ts`
- `web/frontend/tests/test_game_map.py`

What changed:

- Added `#project/:id/map` as a parallel route, leaving Progress intact.
- Added a project detail "Map" button.
- `GameShell` loads core assets, initializes an `EventEngine`, detects WebGL,
  caps device pixel ratio at 2, handles resize, and exposes a DOM fallback.
- `SceneManager` renders a vendored hex-grid substrate, visible axial hex
  lattice cells, workflow atom nodes, edges, orthographic camera fit-all,
  pointer pan, pinch zoom, tap-to-focus, and double-tap fit-all.
- Workflow atoms now occupy geospatial axial hex coordinates (`q/r`) instead
  of a vertical list or arbitrary spread. The route has visible hex cells
  surrounding occupied coordinates.
- Atom meshes update from `EventEngine` snapshots without rebuilding the scene.
- `?fallback=1` forces the DOM fallback for evidence; `?capture=1` preserves
  the drawing buffer for automated canvas pixel checks.
- Build now installs ignored frontend dependencies from `web/frontend/package.json`
  when missing so local `three` is bundled with no runtime hotlink.

Browser smoke evidence:

- Local server: `http://127.0.0.1:8765`
- Smoke project: `febb8d8522c5`
- Mobile canvas screenshot: `/tmp/council-map-mobile.png`
- Forced fallback screenshot: `/tmp/council-map-fallback.png`
- Canvas pixel check: `780x1688`, `576` sampled nonblack pixels.
- Geospatial hex lattice screenshot: `/tmp/council-map-hex-lattice.png`

Important next step:

- Continue Task 9: richer replay density, cost HUD interactions, loop lane
  filtering, visual repair/verify paths, and local llama telemetry in focus
  detail. Route-level code splitting remains needed so non-map routes do not
  pay the full Three.js bundle cost.

### Task 9 - Started: Replay HUD, Cost HUD, And Loop Lane

Started the first map-native operational HUD slice.

Important files:

- `web/frontend/src/game/GameShell.ts`
- `web/frontend/tests/test_game_map.py`
- `web/frontend/sw.js`

What changed:

- Added a map replay strip with range input wired to `EventEngine.scrubTo()`.
- Added a Live button wired to `EventEngine.resumeLive()`.
- Added a compact loop lane fed by `LoopSnapshot.activeStageCounts`.
- Map HUD now shows active atom, completion count, total cost, remaining run
  budget when present, and unknown-cost count.
- Atom focus panel now includes attempt, loop stage, atom cost, token summary,
  repair count, and event narrative from the folded snapshot.
- Service worker cache bumped to `orchestrator-v5-replay-hud`.

Browser smoke evidence:

- Replay HUD screenshot: `/tmp/council-map-replay-hud.png`
- Canvas pixel check: `780x1688`, `1024` sampled nonblack pixels.

## Current Verification Baseline

After the current Task 6 slice, all of this passed:

```bash
uv run pytest -q tests web/backend/tests web/frontend/tests
./web/frontend/build.sh
git diff --check
```

Most recent known good full result:

- `517 passed, 1 skipped, 3 warnings`
- frontend build passed
- `git diff --check` passed
- `.orchestrator` secret scan for `Authorization|api_key|OPENROUTER_API_KEY`
  returned no matches

Known warnings are pre-existing:

- `pytest.mark.integration` is unregistered.
- `orchestrator.roles.tester.Tester` and `TesterError` are collected warnings
  because their names start with `Test` and have constructors.

## Design Invariants To Preserve

- Every persisted run event has `event_id`, `schema_version`, `run_id`, `ts`,
  and `type`.
- Replay folds events. It must not call provider pricing APIs or depend on
  current mutable UI state.
- Historical cost replay uses recorded `cost` fields and recorded rate-card
  versions.
- `usage_recorded` is the only normal model/advisor usage event.
- `provider_call_error` is for failure diagnostics, not for cost totals.
- llama.cpp telemetry is local inference health first, dollar estimate second.
- Budget gate decisions use recorded `budget_at_decision` values.
- SDLC loop stage is event-sourced via `loop_*` events.
- The PWA baseline target is iPhone portrait. Avoid bloated HUDs and text
  overflow.
- Runtime assets must be local/vendored; no hotlinks.

## Event Payload Notes

`usage_recorded` currently includes both compatibility flat fields and canonical
nested fields.

Canonical cost shape:

```json
{
  "cost": {
    "currency": "USD",
    "provider_reported_cost": null,
    "estimated_cost": 0.001,
    "effective_cost": 0.001,
    "source": "local_estimate",
    "confidence": "medium",
    "extraction_path": "llamacpp_timings",
    "rate_card_version": "local-mac-studio-2026-04-21T20:00:00Z"
  }
}
```

Valid cost sources:

- `provider_reported`
- `rate_card_estimate`
- `local_estimate`
- `unknown`

Valid confidence values:

- `high`
- `medium`
- `low`
- `none`

Loop stages:

- `discover`
- `plan`
- `build`
- `verify`
- `repair`
- `review`
- `ship`
- `learn`

## Likely Next Tasks

1. Task 10:
   - Replace the current tray with Claude's recommended three-state bottom
     sheet (`peek` / `standard` / `expanded`), scope chips, and preset chips.
   - Remove the native select from the map control path.
   - Keep the selected atom visible by biasing camera framing while controls
     are open.
2. Task 11:
   - Fold `operator_intent` / applied / rejected states into `EventEngine`
     snapshots so pending map actions have visible board state.
   - Add runner-side consumption for `intercept`, `resume`, `retry`, `skip`,
     and `reroute`; the current `/intents` route records the event but does
     not yet halt a live engine loop by itself.
3. Task 12:
   - Push the scene further into game language: stronger atom geometry,
     artifact cards, gate crystals, edge burst timing, and scene lighting
     tuned for mobile Safari.

## Commands To Run Before Handing Off

```bash
uv run pytest -q tests web/backend/tests web/frontend/tests
./web/frontend/build.sh
git diff --check
rg -n "Authorization|api_key|OPENROUTER_API_KEY" .orchestrator 2>/dev/null || true
```

If testing frontend TypeScript directly, existing tests bundle with:

```bash
npx --yes esbuild@0.24.0 web/frontend/src/game/EventEngine.ts --bundle --format=esm --platform=node --target=es2020 --outfile=/tmp/event-engine.mjs --log-level=warning
```

## Worktree Hygiene

- Do not run `git reset --hard` or checkout files.
- There are many intentional uncommitted files from Tasks 1-6.
- `uv run pytest` may regenerate `uv.lock`; remove it if it was not already
  tracked and no dependency changes were intended.
- Do not commit unless explicitly asked.

## 2026-04-21 Task 9/10 Slice

- Added backend operator intents:
  - `POST /api/projects/{project_id}/intents`
  - Persists `operator_intent` events through the existing stream/event ledger.
  - Scrubs secret-shaped payload keys such as `api_key`, `Authorization`,
    `token`, `password`, and `secret`.
- Wired the map to live control APIs:
  - Tap/Intercept opens the atom control tray.
  - `Intercept` posts `kind: "intercept"` to `/intents`.
  - `Inject` uses `/control/instructions`.
  - `Resume` uses `/control/resume`.
  - `Compact` uses `/control/compact`.
  - Gate atoms still expose approve/reject via `/gates/{gate}/decide`.
- Started using the vendored asset catalog in the Three.js scene:
  - Core edge pulse sprites from `assets/edge-particle-sprites/disc.png`.
  - Deferred spark sprites from `assets/edge-particle-sprites/spark1.png`.
  - Memory glow sprites from `assets/mempalace/radial-alpha-gradient.png`.
  - Deferred lensflare sprites from `assets/mempalace/lensflare0.png`.
  - Deferred HDR environment from `assets/hdris/kloppenheim-02-puresky-1k.hdr`.
- Added camera biasing while the tray is open so the selected atom remains
  visible above the mobile controls.
- Bumped service-worker cache to `orchestrator-v8-asset-scene-control`.
- Claude/Opus critique was used for the touch-control redesign direction.
- Latest mobile smoke:
  - Screenshot: `/tmp/council-map-final-mobile.png`
  - WebGL readback: `780x1328`, `1036` sampled nonblack pixels.
  - Persisted one `operator_intent` event from the map.
- Current LAN URL:
  - `http://192.168.1.50:8000/?v=asset-scene-control#project/49f4afcbffc1/map`

## 2026-04-21 Floating Graph Pivot

- User rejected the hex/lattice metaphor explicitly:
  - Desired metaphor is connections, loops, and session objects floating in
    space, loosely connected to each other.
  - Claude/Opus was invoked again with that correction and returned a
    replacement spec: floating spatial graph, loop orbits as first-class
    objects, catenary-like tethers, perspective camera, and touch gestures for
    shape/interject/intercept.
- Implemented the first pivot slice:
  - `layout.ts` no longer exports axial `q/r`, `HEX_RADIUS`, cells, or lattice
    slots.
  - `layoutWorkflowAtoms()` now returns loop groups, 3D positions, edge kinds,
    and a bounding sphere.
  - SceneManager now uses a `PerspectiveCamera`, orbit/pinch controls, loop
    orbit rings, radial halos, loop labels, and no hex-cell meshes.
  - Atom bodies are now floating icosahedron/gate crystal objects with
    billboard labels rather than floor labels/slabs.
  - GameShell was simplified toward Claude's M1 direction: no big focus panel,
    no persistent replay card, no bottom Intercept button, no native select in
    the map bundle; top status pill + bottom chip cluster + hidden compose dock.
- Latest smoke:
  - Screenshot: `/tmp/council-map-floating-objects.png`
  - WebGL readback: `780x1328`, `1036` sampled nonblack pixels.
- Service worker cache bumped to `orchestrator-v9-floating-graph`.
- Next Claude-driven steps:
  - Radial action ring on selected atom.
  - Drag atom -> atom ghost tether for intercept/reroute.
  - Tap loop halo/orbit to select a loop as a first-class target.
  - Edge pulses should follow `CatmullRomCurve3` instead of linear interpolation.
  - Runner-side `operator_intent` consumption still needed.

## 2026-04-21 Zero-G Graph Refinement

- Invoked Claude/Opus again in prompt mode as design partner. Concrete critique:
  torus orbit rails and floor/vignette read as dashboard/orbit mechanics, not
  floating zero-g objects.
- Implemented the next slice from that critique:
  - Removed fixed loop torus rails from `SceneManager`.
  - Replaced the floor-like vignette with a sparse deterministic star field.
  - Kept only soft nebula loop halos and loop labels.
  - Added deterministic atom bob/drift fields in `layout.ts`.
  - SceneManager now animates atom drift while preserving touch orbit/pinch.
  - EdgeMesh now owns a `CatmullRomCurve3`; tethers are thinner, bowed, and
    edge pulses sample the actual tether curve.
  - Added a mobile `radial-action-ring`: tap atom -> Shape/Nudge/Intercept.
  - Shape posts a `reroute` operator intent; Nudge posts `interject`;
    Intercept posts `intercept`.
  - Removed idle per-atom torus rings so orbit visuals do not come back as the
    base metaphor.
- Verification:
  - `./web/frontend/build.sh` passed.
  - `uv run pytest -q web/frontend/tests/test_game_map.py web/backend/tests/test_intents.py`
    passed (`5 passed`).
  - Playwright mobile smoke passed with service workers blocked.
  - Screenshot: `/tmp/council-map-zero-g-mobile.png`.
  - WebGL readback: `780x1328`, `10359` sampled nonblack pixels.
- Service worker cache bumped to `orchestrator-v10-zero-g-graph`.
- Next work:
  - Long-press atom should open Intercept directly with haptics.
  - Drag from atom should create a ghost tether for reroute/shape.
  - Runner-side `operator_intent` consumption still needed.

## 2026-04-21 Poly Pizza Asset Discovery

- User asked to start asset discovery at https://poly.pizza/search/planet.
- Used Playwright to inspect the search page and model pages, including network
  calls. Useful endpoints observed:
  - `GET /api/model/{public_id}/suggested`
  - `GET /api/model/{public_id}/bundles`
  - `GET /api/model/{public_id}/gettoken`
  - model viewer uses `https://static.poly.pizza/{resource_id}.glb.br`;
    uncompressed GLB is available at `https://static.poly.pizza/{resource_id}.glb`.
- Downloaded 14 GLB models plus previews into `assets/poly-pizza/`.
  - 10 CC0 models, mostly Quaternius planets plus one AstroJar pixel planet.
  - 4 CC-BY 3.0 scene objects from Poly by Google: Planets, Asteroid, Space
    probe, Satellite orbiting Earth.
  - Machine-readable inventory: `assets/poly-pizza/manifest.json`.
  - Per-asset metadata: `assets/poly-pizza/*/metadata.json`.
  - Human inventory/attribution guidance: `assets/poly-pizza/README.md`.
- Backend now registers `.glb` as `model/gltf-binary` and `.gltf` as
  `model/gltf+json` before mounting static assets.
- Verification:
  - `jq` validated the pack manifest and all metadata files.
  - All GLB files start with the `glTF` magic header.
  - `uv run pytest -q web/backend/tests/test_pwa_serving.py web/frontend/tests/test_pwa.py`
    passed (`25 passed`).
  - `git diff --check` passed.
- Next asset work:
  - Add a `PolyPizzaModelCatalog`/loader that loads a small CC0 subset after
    first render.
  - Replace a few generic atom meshes with planet/asteroid/probe silhouettes.
  - Add in-app attribution only when CC-BY models are used in a published view.

## 2026-04-21 Poly Pizza Display Wiring

- User asked whether the models were being displayed. They were only downloaded
  and served, so this slice wired a small CC0 subset into the Three.js scene.
- Added `model` asset kind and three deferred model assets:
  - `polyPizza.planetA`
  - `polyPizza.planetB`
  - `polyPizza.pixelPlanet`
- SceneManager now imports `GLTFLoader`, normalizes GLB scene scale, wraps each
  model in a space-prop group, and animates slow bob/spin after first render.
- Playwright mobile smoke verified all three GLB requests returned `200` with
  `model/gltf-binary`.
- Screenshot with displayed props:
  - `/tmp/council-map-poly-pizza-props.png`
- Verification:
  - `./web/frontend/build.sh` passed.
  - `uv run pytest -q web/frontend/tests/test_asset_manager.py web/frontend/tests/test_game_map.py web/backend/tests/test_pwa_serving.py`
    passed (`12 passed`).

## 2026-04-21 Zero-G Flow/Preview Design Plan

- User pushed the design toward:
  - flows between floating objects,
  - content previews showing who creates what and where it goes,
  - speech bubbles / agent utterance previews,
  - loop groups that read like small planetary/electron systems,
  - mobile-first zero-g interaction rather than dashboards or hex grids.
- Invoked Claude/Opus in prompt mode as a design partner with:
  - `claude -p --model opus --dangerously-skip-permissions --add-dir /Users/karol/dev/projects/llm-projects/build/workspace`
- Claude recommended:
  - planet-surface content previews instead of detached dashboard cards,
  - comet-tail speech ribbons instead of chat boxes,
  - artifacts accreting as small bodies near their author,
  - loop clusters as gravitational systems with barycenters and orbit trails,
  - mobile focus camera with galaxy/cluster/surface zoom levels.
- Added detailed design doc:
  - `docs/spatial-flow-universe-design.md`
- The doc now covers:
  - first-class flow visual grammar,
  - loop cluster layout language,
  - content previews, speech tails, and artifact accretion,
  - flow causality between agents/artifacts/memory/gates,
  - planned modules for `FlowPath`, `FlowDirector`, `ContentPreviewLayer`,
    `SpeechTailLayer`, `ArtifactAccretion`, `LoopClusterLayout`,
    `ModelCatalog`, `CharacterActor`, and `AnimationDirector`,
  - a phased roadmap through flow foundation, event-driven flows, operator
    force gestures, memory/repair atmosphere, replay polish, content previews,
    and model-backed loop actors.

## 2026-04-21 Ultimate Space Kit Discovery

- User pointed at:
  - https://poly.pizza/bundle/Ultimate-Space-Kit-YWh743lqGX
- Confirmed from Poly Pizza page:
  - Creator: Quaternius.
  - License: Public Domain / CC0.
  - Updated: 2023-03-13.
  - 87 GLB models.
- Used Playwright from `web/frontend/node_modules` to click `Download GLTF`.
  - Real download endpoint:
    `https://poly.pizza/api/list/YWh743lqGX/download/glb`
  - Real static zip:
    `https://static.poly.pizza/list/YWh743lqGX-glb-676332404.zip`
  - Zip size from response: `5,785,836` bytes.
- Downloaded and extracted the kit:
  - `assets/poly-pizza/ultimate-space-kit/models/*.glb`
  - `assets/poly-pizza/ultimate-space-kit/manifest.json`
  - `assets/poly-pizza/ultimate-space-kit/README.md`
- Generated manifest summary:
  - 87 GLB models.
  - 11,361,152 bytes extracted.
  - 3 astronaut operator models.
  - 4 mech heavy-agent models.
  - 3 rover/tool-runner models.
  - 4 spaceship transfer/deploy models.
  - 11 planet/loop-body models.
  - 9 facility/cluster-anchor models.
  - 7 artifact/status token models.
  - 5 provider/telemetry models.
  - 7 blocker/asteroid models.
  - 1 connector model.
  - 27 optional biome props.
- Parsed GLB animation metadata:
  - Astronaut models each have 18 animations.
  - Mech models each have 17 animations.
  - Enemy models have 8-14 animations.
- Updated `docs/spatial-flow-universe-design.md` with model-backed
  orchestration conventions mapped to the engine:
  - `memory_refresh -> learn`
  - `persona_forum -> discover`
  - `architect` / `micro_task_breakdown -> plan`
  - `implementation -> build`
  - `testing -> verify`
  - `guru_escalation -> repair`
  - `review -> review`
  - `deployment -> ship`
- Updated `assets/README.md` with the Ultimate Space Kit inventory row.

## 2026-04-21 Project Management Pack

- User asked for an actual phase-based plan under `project-management/` so
  agents can onboard, check status, and continue task-by-task toward a usable
  system.
- Added:
  - `project-management/README.md`
  - `project-management/STATUS.md`
  - `project-management/AGENT_ONBOARDING.md`
  - `project-management/DIRECTION_GUARDRAILS.md`
  - `project-management/phases/00-baseline-and-invariants.md`
  - `project-management/phases/01-flow-foundation.md`
  - `project-management/phases/02-orbital-loop-layout.md`
  - `project-management/phases/03-model-catalog-and-actors.md`
  - `project-management/phases/04-content-previews-speech-artifacts.md`
  - `project-management/phases/05-operator-touch-control.md`
  - `project-management/phases/06-engine-consumption-and-run-control.md`
  - `project-management/phases/07-mobile-performance-and-polish.md`
  - `project-management/phases/08-release-hardening.md`
- The project-management pack now defines:
  - phase order,
  - next recommended task,
  - task statuses,
  - context files,
  - implementation surfaces,
  - acceptance criteria,
  - evidence commands,
  - design guardrails to prevent random/meaningless visuals.
- Important use rule:
  - Future agents should read `project-management/STATUS.md`,
    `project-management/DIRECTION_GUARDRAILS.md`, then the next unfinished
    phase file before editing code.

## 2026-04-21 Flow Foundation And Multi-Scale PWA Views

- User clarified the map cannot be one crowded space on mobile:
  - Needs global-level orientation.
  - Needs drill-down into loop clusters / sub-spaces.
  - Needs object-level surfaces for local work and intervention.
- Implemented first Phase 1 flow foundation slice:
  - Added pure `FlowTypes` with `FlowKind`, `FlowMode`, and `FlowCommand`.
  - Added `FlowPath` as the Three.js owner of curved tether geometry, point
    sampling, tangents, and mode-driven style.
  - Kept `EdgeMesh` as a compatibility wrapper over `FlowPath`.
  - Added `FlowDirector` to map durable run events to flow commands.
  - `SceneManager` now consumes flow commands for active, cost, repair, gate,
    operator-intent, and replay states.
- Implemented first multi-scale navigation slice:
  - `SceneManager` now supports `global`, `cluster`, and `surface` view levels.
  - Map HUD exposes compact Run / Loop / Object controls.
  - `global` fits the whole run, `cluster` frames the selected or active loop,
    and `surface` frames the selected or active atom.
- Verification:
  - `uv run pytest -q web/frontend/tests/test_game_map.py` passed (`7 passed`).
  - `./web/frontend/build.sh` passed.
