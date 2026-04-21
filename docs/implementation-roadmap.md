# Phased Implementation Roadmap - Three.js Strategy Client

## How to Read This Document

Each phase is a self-contained unit of work. Phases are ordered by dependency: complete Phase N before starting Phase N+1. Within a phase, tasks are atomic - each can be assigned to a low-context agent with no knowledge of other tasks. Each task includes the exact files to create or modify and a done condition an agent can verify without running the UI.

---

## Phase 0 - Foundation Setup (No UI Change)

**Goal:** Install Three.js, scaffold the `game/` directory, extract EventEngine from Progress.ts, and define replayable cost types. The existing Progress.ts view continues to work unchanged.

**Done condition for this phase:** `npm run build` succeeds, existing Progress.ts tests pass, EventEngine unit tests pass.

---

### Task 0.1 - Add Three.js dependency

**Files:** `web/frontend/package.json`

**Actions:**
- Add `"three": "^0.165.0"` and `"@types/three": "^0.165.0"` to `dependencies` / `devDependencies`.
- Run `npm install` in `web/frontend/`.

**Done:** `import * as THREE from 'three'` compiles without TypeScript error.

---

### Task 0.2 - Create game/ directory scaffold

**Files to create:**
```
web/frontend/src/game/
  GameShell.ts          (empty export class GameShell {})
  SceneManager.ts       (empty export class SceneManager {})
  EventEngine.ts        (empty export class EventEngine {})
  atoms/AtomNode.ts     (empty export class AtomNode {})
  atoms/GateNode.ts     (empty export class GateNode {})
  atoms/EdgeMesh.ts     (empty export class EdgeMesh {})
  memory/MemPalaceGroup.ts   (empty)
  memory/MemoryOrb.ts        (empty)
  hud/ReplayTimeline.ts      (empty)
  hud/FocusPanel.ts          (empty)
  hud/CommandBar.ts          (empty)
  hud/MinimapWidget.ts       (empty)
  accessibility/AccessibilityTree.ts  (empty)
```

**Done:** All files exist, TypeScript compiles without errors.

---

### Task 0.3 - Define shared types

**File to create:** `web/frontend/src/game/types.ts`

**Content:** The full TypeScript type definitions from the "API surface emitted by EventEngine" section of `docs/threejs-integration-plan.md`. Include: `AtomState`, `AtomStatus`, `RunEvent` (with `event_id: string` and `schema_version: number` as required fields), `EngineSnapshot`, `MemPalaceStatus`, `WorkflowStep`, `CostSource`, `CostConfidence`, `CostBucket`, `CostSnapshot` (with `phaseBudgetUsd`, `remainingPhaseBudgetUsd`, `runHalted`, `burnRateUsdPerHour`).

**Done:** All game/ files can `import { AtomState } from '../types'` without error.

---

### Task 0.4 - Extract EventEngine from Progress.ts

**Files to modify:** `web/frontend/src/game/EventEngine.ts`

**Actions:**
1. Read `Progress.ts` lines ~1006-1137 (history fetch, SSE connect, `applyStreamEvent` function, `stepStatuses` state).
2. Implement `EventEngine` class per the spec in `docs/threejs-integration-plan.md`.
3. The `applyEvent` FSM must match `applyStreamEvent` logic exactly. Copy the switch/case, do not rewrite.
4. Wire `engine.on('snapshot', ...)` back into Progress.ts so existing view continues to work.

**Do not remove or break existing Progress.ts code.** EventEngine is additive.

**Done:** `EventEngine` class instantiated in a test file processes a fixture event sequence and produces correct `AtomStatus` output. Verify by running existing backend event fixtures through the engine.

---

### Task 0.5 - AccessibilityTree implementation

**File:** `web/frontend/src/game/accessibility/AccessibilityTree.ts`

**Actions:**
1. Implement `AccessibilityTree` that accepts a DOM container and `EventEngine`.
2. On `engine.on('snapshot')`, rebuild the hidden `<ul>` with correct `aria-label` attributes.
3. Wrap in `<div aria-live="polite" aria-relevant="text">`.
4. Style with `.sr-only` CSS class (clip-path hidden, position absolute).

**Done:** Mounting `AccessibilityTree` and emitting a fixture snapshot produces the correct ARIA list in the DOM. Additionally: using VoiceOver (macOS) or TalkBack (Android emulator), a screen reader user can navigate to a gate atom and read its question text without touching the canvas. This test must pass before Phase 2 begins.

---

### Task 0.6 - Define cost snapshot types

**Files to modify:**
```
web/frontend/src/game/types.ts
web/frontend/src/game/EventEngine.ts
```

**Actions:**
1. Add `CostSource`, `CostBucket`, and `CostSnapshot` from `docs/threejs-integration-plan.md`.
2. Add `cost: CostSnapshot` to `EngineSnapshot`.
3. Add an `emptyCostSnapshot()` helper.
4. Do not render cost yet.

**Done:** EventEngine emits snapshots with a zeroed `cost` object. Existing Progress behavior is unchanged.

---

### Task 0.7 - Define SDLC loop snapshot types

**Files to modify:**
```
web/frontend/src/game/types.ts
web/frontend/src/game/EventEngine.ts
```

**Actions:**
1. Add `LoopStage`, `AtomLoopStatus`, and `LoopSnapshot` from
   `docs/threejs-integration-plan.md`.
2. Add `loops: LoopSnapshot` to `EngineSnapshot`.
3. Add an `emptyLoopSnapshot()` helper.
4. Do not render loops yet.

**Done:** EventEngine emits snapshots with a zeroed `loops` object. Existing
Progress behavior is unchanged.

---

## Phase 1 - Basic Three.js Scene

**Goal:** Render the workflow graph as a static 3D scene with no animation or live data. Camera navigation works on mobile.

**Done condition:** Running the app shows the Three.js canvas with atom nodes laid out in workflow order, camera pan/zoom works via touch, no console errors. Additionally all three of the following performance gates must pass:
- First Contentful Paint < 2s on a simulated mid-range Android device (Chrome DevTools: 4x CPU slowdown, Fast 3G). Measure with Lighthouse or `performance.now()` from script load to first canvas render.
- Sustained 60fps during pan and pinch on an iPhone 12 or equivalent (Chrome DevTools touch simulation at 2x CPU throttle is the minimum bar; real device test before Phase 2).
- WebGL context must initialize without error on iOS Safari 17 (test via BrowserStack or real device). The fallback AccessibilityTree must render correctly when WebGL is disabled in Safari's experimental settings.

---

### Task 1.1 - GameShell bootstrap

**File:** `web/frontend/src/game/GameShell.ts`

**Actions:**
1. Implement `GameShell` constructor: create `<canvas>`, detect WebGL support, mount canvas to container.
2. If no WebGL: mount `FallbackView` (a styled `AccessibilityTree`) and return.
3. Initialize `THREE.WebGLRenderer` with `{ antialias: true, powerPreference: 'high-performance' }`.
4. Handle `devicePixelRatio` capping at 2x for performance.
5. Handle `resize` events using `ResizeObserver`.
6. Handle safe-area insets via CSS `env(safe-area-inset-*)` - set canvas padding/margin accordingly.

**Done:** Canvas mounts, renderer runs `requestAnimationFrame` loop, no WebGL errors.

---

### Task 1.2 - SceneManager init with static atom layout

**File:** `web/frontend/src/game/SceneManager.ts`

**Actions:**
1. Implement `SceneManager` constructor: create `THREE.Scene`, `THREE.OrthographicCamera`, `AmbientLight`, `DirectionalLight`.
2. On `buildFromWorkflow(steps: WorkflowStep[])`: create one `AtomNode` per step, lay them out in a vertical line spaced 2.5 units apart.
3. Create `EdgeMesh` between consecutive steps.
4. Add all nodes and edges to scene.
5. Run animation loop (no animation yet - just a static render).

**Done:** Scene renders atom nodes in a column. Camera default view shows all atoms.

---

### Task 1.3 - AtomNode mesh

**File:** `web/frontend/src/game/atoms/AtomNode.ts`

**Actions:**
1. Implement `AtomNode` using `BoxGeometry` (1.6 x 0.18 x 1.0) for Phase 1 (defer `RoundedBoxGeometry` to Phase 3).
2. Material: `MeshStandardMaterial` with color from `STATE_MATERIALS['idle']`.
3. Implement `setState(status: AtomStatus)`: immediately (no tween) sets material color to match state.
4. Add label using `CanvasTexture` on a `PlaneGeometry` child mesh below the atom.

**Done:** AtomNode renders with correct idle color and step title label.

---

### Task 1.4 - EdgeMesh

**File:** `web/frontend/src/game/atoms/EdgeMesh.ts`

**Actions:**
1. Implement `EdgeMesh` using `TubeGeometry` along a straight line between two `Vector3` points.
2. Material: `MeshBasicMaterial` color `#272B3D`.
3. No animation yet.

**Done:** Edges render between consecutive atom nodes.

---

### Task 1.5 - Mobile camera gestures

**File:** `web/frontend/src/game/SceneManager.ts`

**Actions:**
1. Add `pointerdown`, `pointermove`, `pointerup` listeners on the canvas.
2. Single pointer drag -> pan orthographic camera.
3. Two-pointer pinch -> zoom (change `camera.zoom`, call `camera.updateProjectionMatrix()`).
4. Double tap (two taps < 300ms, < 8px) -> call `fitAll()` which resets camera to show all atoms.

**Done:** Pan and pinch work on a mobile device (or Chrome DevTools touch simulation).

---

## Phase 2 - Live Data Binding

**Goal:** EventEngine drives SceneManager. Atom states update in real-time from SSE stream. Replay timeline is functional.

**Done condition:** Opening a live run shows atom states changing as the run progresses. History loads and shows correct states on page open. Additionally all of the following boundary tests must pass as unit tests in EventEngine:
- Scrub to index 0: all atoms in `idle` state, CostSnapshot.effectiveUsd === 0, unknownCostCount === 0.
- Scrub to final index on a completed run: all atoms in `done` or `error` or `skipped` state.
- Scrub to final index on an error run: at least one atom in `error` state.
- Economics sheet opened at scrub index 0 shows $0.00 total and no line items.
- Economics sheet opened at scrub index N shows totals that sum to CostSnapshot.effectiveUsd at that index.
These tests run against fixture event sequences; no running backend is required.

---

### Task 2.1 - Wire EventEngine to SceneManager

**File:** `web/frontend/src/game/SceneManager.ts`

**Actions:**
1. Accept `EventEngine` in constructor.
2. Subscribe to `engine.on('snapshot')` -> call `_applyFullSnapshot()`.
3. Subscribe to `engine.on('event')` -> call `_onEvent()`.
4. `_applyFullSnapshot`: iterate `snapshot.atoms`, call `atom.setState()` for each.
5. `_onEvent`: call `atom.setState()` only for the affected step id.

**Done:** Starting a run causes atom nodes to change color as phases progress.

---

### Task 2.2 - Top bar HUD

**File:** `web/frontend/src/game/hud/CommandBar.ts`

**Actions:**
1. Implement DOM overlay div: fixed position top, respects safe-area-inset-top.
2. Shows project name (left), `LIVE` pulse indicator (center-right), settings button (right).
3. `LIVE` indicator: green circle that pulses via CSS animation when `engine.connectionState === 'live'`.
4. Reads connection state from `engine.on('connection')`.

**Done:** Top bar mounts over canvas, `LIVE` pulses on live SSE connection.

---

### Task 2.3 - ReplayTimeline HUD

**File:** `web/frontend/src/game/hud/ReplayTimeline.ts`

**Actions:**
1. Implement collapsed bar (56pt): shows thin event density line + scrubber track.
2. Swipe-up gesture expands to 180pt: shows histogram + timestamp labels + play/stop controls.
3. Scrubber drag calls `engine.scrubTo(index)`.
4. `>` button calls `engine.resumeLive()`.
5. Histogram: divide `engine.events` into 60 equal time buckets, count events per bucket, draw as `<canvas 2D>` bar chart.

**Done:** Timeline scrubber correctly triggers `engine.scrubTo()`, atom states update visually.

---

### Task 2.4 - FocusPanel HUD

**File:** `web/frontend/src/game/hud/FocusPanel.ts`

**Actions:**
1. Implement bottom-sheet panel (portrait) / right-drawer (landscape) in DOM overlay.
2. Slide animation: CSS `transform: translateY(100%)` -> `translateY(0)` with spring (use Web Animations API with `easing: 'cubic-bezier(0.34, 1.56, 0.64, 1)'` as spring approximation).
3. Content sections: atom header, state badge + elapsed time, last event narrative, memory accesses list, telemetry row, action buttons.
4. Wire to `SceneManager` raycaster: on atom tap, open panel with `status` data.
5. Gate state: replace action buttons with `Approve`, `Reject`, `Escalate` (56pt height minimum).
6. Gate button actions: POST to `/api/projects/{id}/gates/{gate_id}/decide`.

**Done:** Tapping an atom opens FocusPanel with correct data. Gate buttons submit to API.

---

### Task 2.5 - Raycaster tap detection

**File:** `web/frontend/src/game/SceneManager.ts`

**Actions:**
1. On `pointerup`: if movement < 8px and duration < 200ms, fire a raycast.
2. Raycast against all `AtomNode` meshes.
3. On hit: animate camera to center on atom, notify `FocusPanel.open(atomStatus)`.
4. On miss: call `FocusPanel.dismiss()`.

**Done:** Tapping atoms opens FocusPanel. Tapping empty space closes it.

---

### Task 2.6 - Fold usage and budget events

**File:** `web/frontend/src/game/EventEngine.ts`

**Actions:**
1. Handle `usage_recorded`, `budget_warning`, `budget_exceeded`,
   `budget_gate_opened`, and `budget_gate_decided`.
2. Fold usage events into `CostSnapshot` using recorded event payloads only.
3. Group totals by provider, model, role, and atom.
4. Recompute cost from scratch during `scrubTo(index)`.
5. Add fixture tests where replay index changes the visible cost total.

**Done:** Live snapshots and replay snapshots produce identical cost totals for
the same event prefix. No pricing API is called during replay.

---

### Task 2.7 - Cost HUD and economics sheet

**Files to create or modify:**
```
web/frontend/src/game/hud/CostHud.ts
web/frontend/src/game/hud/EconomicsSheet.ts
web/frontend/src/game/hud/CommandBar.ts
```

**Actions:**
1. Show run cost, budget remaining, and unknown-cost count in the top HUD.
2. Add a tap target that opens the economics sheet.
3. Economics sheet groups by provider, model, role, phase, and atom.
4. Each row shows source: provider-reported, estimate, local estimate, or
   unknown.
5. On mobile, render as a bottom sheet with 56pt minimum touch targets.

**Done:** Opening a replay at different indexes updates the economics sheet to
the selected point in time.

---

### Task 2.8 - Fold SDLC loop events

**File:** `web/frontend/src/game/EventEngine.ts`

**Actions:**
1. Handle `loop_entered`, `loop_progressed`, `loop_blocked`,
   `loop_repaired`, `loop_completed`, and `loop_reopened`.
2. Fold loop events into `LoopSnapshot` using recorded event payloads only.
3. Recompute loop state from scratch during `scrubTo(index)`.
4. Add fixture tests for build -> verify -> repair -> verify -> review.
5. Add fixture tests for MemPalace sync appearing as the learn loop.

**Done:** Live snapshots and replay snapshots produce identical loop state for
the same event prefix.

---

### Task 2.9 - llama.cpp telemetry adapter contract

**Files to modify:**
```
orchestrator/lib/providers/*.py
web/frontend/src/game/types.ts
web/frontend/src/game/EventEngine.ts
```

**Actions:**
1. Normalize llama.cpp OpenAI-compatible `usage` fields when present.
2. Normalize llama.cpp `timings` fields when present.
3. Preserve `runtime.llamacpp` for focus panel and local inference health UI.
4. Treat `/metrics` and `/slots` as supplemental only; do not require them for
   correctness.
5. Emit `usage_recorded` with `cost.extraction_path` set to one of the
   llama.cpp extraction paths from `docs/cost-tracking.md`.

**Done:** A fixture llama.cpp response with `timings` produces input tokens,
output tokens, cache tokens, context tokens, throughput, and local estimated
cost without calling a live llama.cpp server.

---

## Phase 3 - Particle System and Animation

**Goal:** Events produce visible particles. State transitions animate. The scene feels alive.

**Done condition:** Particles travel between nodes on events. Active atoms breathe. Completed atoms flash on transition.

---

### Task 3.1 - Particle system implementation

**File:** `web/frontend/src/game/atoms/ParticleSystem.ts` (new file)

**Actions:**
1. Implement `ParticlePool` with 500-particle `Float32Array` (position XYZ + alpha + lifetime).
2. `spawn(position, config)`: find idle slot in pool, set initial values.
3. Per-frame `tick(dt)`: update positions, decrement lifetime, zero-out expired particles.
4. `THREE.Points` with `ShaderMaterial` (vertex: position + alpha attributes; fragment: soft circle + alpha).
5. Wire `SceneManager._onEvent()` to call `this._particles.emit(event)`.

**Done:** Phase transitions emit visible particles. No memory leaks after 1000+ events (pool recycles).

---

### Task 3.2 - Atom state animations

**File:** `web/frontend/src/game/atoms/AtomNode.ts`

**Actions:**
1. Add tweened material transitions: lerp `color` and `emissiveIntensity` over 300-400ms per state change. Use a simple `requestAnimationFrame` lerp (no library needed).
2. `active` state: breathing scale animation (`scale.x/z` oscillates +/-2% over 2.4s loop).
3. `done` state: brief scale-up flash (1.0 -> 1.12 -> 1.0 over 400ms) on entry.
4. `error` state: shake on entry (translate x by +/-0.05, 200ms total).

**Done:** State transitions animate visibly. No dropped frames (keep < 4ms per update).

---

### Task 3.3 - GateNode mesh

**File:** `web/frontend/src/game/atoms/GateNode.ts`

**Actions:**
1. `OctahedronGeometry(0.5)` with `MeshStandardMaterial`.
2. Continuous slow Y-rotation.
3. `waiting` state: amber color + bloom-emissive + scale pulse loop.
4. Gate nodes are created for `WorkflowStep.type === 'gate'` steps in SceneManager.

**Done:** Gate nodes render distinctly from phase atoms. Waiting gates pulse amber.

---

### Task 3.4 - MemPalace overlay

**File:** `web/frontend/src/game/memory/MemPalaceGroup.ts`

**Actions:**
1. `TorusGeometry(8, 0.12, 8, 48, Math.PI)` - half-arc.
2. Position: Y+4, tilted back 20 degrees on X axis.
3. `MeshBasicMaterial({ color: '#5B3FBF', transparent: true, opacity: 0.35 })`.
4. Slow Y-rotation (0.05 rad/sec in animation loop).
5. Three status orbs on arc surface: `SphereGeometry(0.15)` at arc positions 20%, 50%, 80%.
6. On `engine.on('snapshot')` where `snapshot.memPalaceStatus` changes: update orb colors.
7. Tap detection via raycaster -> notify `FocusPanel` to open memory search mode.

**Done:** Arc renders above map. Orb colors reflect MemPalace status from API.

---

### Task 3.5 - Post-processing bloom (CSS fallback)

**File:** `web/frontend/src/game/GameShell.ts`

**Actions:**
1. Do NOT use `EffectComposer` or Three.js bloom pass yet.
2. Instead: apply `filter: blur(0px)` to the canvas in normal state.
3. When an atom enters `active` state, briefly set canvas `filter: brightness(1.2)` for 200ms.
4. This is a placeholder for Phase 4 GPU bloom - document this clearly in code with `// TODO: replace with EffectComposer BloomPass after performance baseline`.

**Done:** Active atoms appear visually brighter without GPU post-processing overhead.

---

### Task 3.6 - CostLayer visual rings

**Files to create or modify:**
```
web/frontend/src/game/cost/CostLayer.ts
web/frontend/src/game/cost/CostRing.ts
web/frontend/src/game/SceneManager.ts
```

**Actions:**
1. Render a thin ring around atoms with recorded usage.
2. Use solid rings for provider-reported cost and dashed rings for estimates.
3. Add a red notch for unknown cost.
4. Animate warning and exceeded budget states.
5. Keep labels and numeric detail in DOM overlays only.

**Done:** Cost rings update from `CostSnapshot.byAtom` during live execution and
replay scrubbing.

---

### Task 3.7 - LoopLayer visual bands

**Files to create or modify:**
```
web/frontend/src/game/loops/LoopLayer.ts
web/frontend/src/game/loops/AtomLoopBand.ts
web/frontend/src/game/loops/RepairArc.ts
web/frontend/src/game/SceneManager.ts
web/frontend/src/game/hud/ReplayTimeline.ts
```

**Actions:**
1. Render active SDLC loop bands around atoms from `LoopSnapshot.byAtom`.
2. Render verify -> repair -> verify cycles as a reverse repair arc.
3. Connect learn loop events to the MemPalace arc.
4. Add a compact loop lane to ReplayTimeline.
5. Cap visible loop bands per atom to preserve iPhone readability.

**Done:** A fixture run physically shows build, verify, repair, review, ship,
and learn transitions during replay scrubbing.

---

## Phase 4 - Polish and Native Feel

**Goal:** Performance targets met, offline works, transitions feel iOS-native.

---

### Task 4.1 - RoundedBoxGeometry for atoms

Replace `BoxGeometry` with `RoundedBoxGeometry` from `three/addons`. Verify no performance regression (profile with Chrome DevTools).

---

### Task 4.2 - True spring animation

Replace Web Animations API spring approximation with a real spring integrator (< 50 lines, no library):
```typescript
function springTick(current, target, velocity, stiffness, damping, dt) {
  const force = -stiffness * (current - target) - damping * velocity
  velocity += force * dt
  current += velocity * dt
  return { current, velocity }
}
```
Apply to camera moves, panel slides, atom transitions.

---

### Task 4.3 - Service Worker offline cache

Configure the Service Worker (already in place) to cache:
- Three.js bundle
- Game assets (CanvasTexture sources)
- Last known project state (store `engine.snapshot()` in IndexedDB on each snapshot)

On offline: load from cache, show `OFFLINE` badge, disable controls.

---

### Task 4.4 - EffectComposer bloom

Add `EffectComposer` + `UnrealBloomPass` once Phase 3 performance baseline is confirmed. Gate behind: `gl.getParameter(gl.MAX_TEXTURE_IMAGE_UNITS) > 16` check to exclude low-end GPUs.

---

### Task 4.5 - MinimapWidget

**File:** `web/frontend/src/game/hud/MinimapWidget.ts`

Bottom-left corner, 96x96pt. Renders a 2D `<canvas>` projection of atom positions as dots. Shows camera viewport rectangle. Tap to pan camera to that position.

---

### Task 4.6 - Budget gates and cost replay export

**Files to modify:**
```
web/frontend/src/game/EventEngine.ts
web/frontend/src/game/hud/ReplayTimeline.ts
web/frontend/src/game/hud/EconomicsSheet.ts
```

**Actions:**
1. Add a replay timeline toggle for event density vs cost density.
2. Render budget gate events as timeline markers.
3. Add export for replay economics: totals, groups, source/confidence labels,
   and unknown-cost events.
4. Verify exported totals match `CostSnapshot` at the selected replay index.

**Done:** A replay bundle can prove what the run spent, what was estimated, and
what was unknown at the selected point in time.

---

### Task 4.7 - SDLC loop replay export and filters

**Files to modify:**
```
web/frontend/src/game/EventEngine.ts
web/frontend/src/game/hud/ReplayTimeline.ts
web/frontend/src/game/hud/FocusPanel.ts
```

**Actions:**
1. Add replay filters for discover, plan, build, verify, repair, review, ship,
   and learn.
2. Add loop state to replay export bundles.
3. Show repair count and reopened count in FocusPanel.
4. Verify loop export matches `LoopSnapshot` at the selected replay index.

**Done:** A replay bundle can prove which lifecycle stage every atom occupied
at the selected point in time.

---

## Dependency Graph (Phases)

Phase 0 must complete fully before Phase 1 starts. Within Phase 0, tasks are
sequential. Within later phases, some tasks can be parallelized (see notes).

```
Phase 0 (all sequential):
  0.1 -> 0.2 -> 0.3 -> 0.4 -> 0.5 -> 0.6 -> 0.7
                                          |
                                          v
Phase 1 (0.6 must be done; within phase: 1.2 requires 1.3 importable first):
  1.1 -> 1.2 -> 1.3 -> 1.4 -> 1.5
                                  |
                                  v
Phase 2 (1.5 must be done; 2.4 focus panel integration depends on 2.5 raycaster):
  2.1 -> 2.2 -> 2.3 -> 2.5 -> 2.4 -> 2.6 -> 2.7 -> 2.8 -> 2.9
                                              |
                                              v
Phase 3 (2.9 must be done):
  3.1 -> 3.2 -> 3.3 -> 3.4 -> 3.5 -> 3.6 -> 3.7
                                        |
                                        v
Phase 4 (3.7 must be done):
  4.1 -> 4.2 -> 4.3 -> 4.4 -> 4.5 -> 4.6 -> 4.7
```

Notes:
- 1.3 (AtomNode mesh) must exist before 1.2 (SceneManager) can import it.
- 2.5 (raycaster) must exist before 2.4 (FocusPanel) can use it.
- 0.6 (cost snapshot types) and 0.7 (loop snapshot types) can be done after
  0.4 (EventEngine) and do not need visual work.

---

## Agent Assignment Notes

Each numbered task above can be executed by a low-context agent given:
1. The task block from this document (exact files, exact actions, done condition)
2. The relevant section of `docs/threejs-integration-plan.md` for data contracts
3. The relevant section of `docs/visual-grammar.md` for colors and geometry specs
4. Access to `web/frontend/src/views/Progress.ts` for reference logic

Agents should not need to read the full codebase. The done condition is verifiable without running the full UI (TypeScript compilation + unit test for logic tasks; screenshot/DevTools for visual tasks).
