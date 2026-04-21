# Technical Integration Plan - SSE/Event-History to Three.js

## Objective

Consume the existing SSE stream (`/api/projects/{id}/stream`) and event-history API (`/api/projects/{id}/events`) and render the resulting state in Three.js without breaking accessibility or the fallback HTML view.

The backend is unchanged. This document specifies only the frontend integration.

---

## EventEngine - The Data Contract

`EventEngine.ts` is the single data adapter between the backend APIs and all rendering. Neither the Three.js scene nor the DOM overlay calls the API directly.

### API surface emitted by EventEngine

```typescript
// EventEngine.ts
export type AtomState = 'idle' | 'active' | 'done' | 'error' | 'waiting' | 'skipped'

export interface AtomStatus {
  id: string
  state: AtomState
  attempt: number
  startedAt: number | null      // unix ms
  completedAt: number | null
  lastEvent: RunEvent | null
}

export interface RunEvent {
  type: string
  ts: string                    // ISO8601
  [key: string]: unknown
}

export interface EngineSnapshot {
  projectId: string
  runId: string | null
  atoms: Record<string, AtomStatus>   // keyed by step id
  events: RunEvent[]                  // full ordered history
  scrubIndex: number                  // -1 = live
  isLive: boolean
  memPalaceStatus: MemPalaceStatus | null
  cost: CostSnapshot
}

export interface MemPalaceStatus {
  initialized: boolean
  wing: string | null
  cached_wakeup: string | null
  last_search: string | null
}

export type CostSource = 'provider_reported' | 'rate_card_estimate' | 'local_estimate' | 'unknown'

export interface CostBucket {
  effectiveUsd: number
  providerReportedUsd: number
  estimatedUsd: number
  inputTokens: number
  outputTokens: number
  cacheReadTokens: number
  cacheWriteTokens: number
  reasoningTokens: number
  unknownCostCount: number
}

export interface CostSnapshot extends CostBucket {
  currency: 'USD'
  remainingRunBudgetUsd: number | null
  byProvider: Record<string, CostBucket>
  byModel: Record<string, CostBucket>
  byRole: Record<string, CostBucket>
  byAtom: Record<string, CostBucket>
  sources: Record<CostSource, number>
  lastUsageEvent: RunEvent | null
}

// EventEngine is an EventEmitter
engine.on('snapshot', (s: EngineSnapshot) => { /* re-render */ })
engine.on('event', (e: RunEvent, snapshot: EngineSnapshot) => { /* incremental update */ })
engine.on('scrub', (index: number, snapshot: EngineSnapshot) => { /* replay frame */ })
engine.on('connection', (state: 'live' | 'reconnecting' | 'offline' | 'history') => {})
```

### EventEngine internals

```typescript
class EventEngine extends EventEmitter {
  private _projectId: string
  private _eventSource: EventSource | null = null
  private _history: RunEvent[] = []
  private _atoms: Record<string, AtomStatus> = {}
  private _cost: CostSnapshot = emptyCostSnapshot()
  private _scrubIndex = -1            // -1 = live tail

  async init(projectId: string, workflow: WorkflowStep[]) {
    // 1. Build idle atom map from workflow definition
    // 2. Fetch history: GET /api/projects/{id}/events?limit=500
    // 3. Replay all history events through applyEvent() to prime atom states
    // 4. Emit initial 'snapshot'
    // 5. Open SSE: GET /api/projects/{id}/stream
  }

  private applyEvent(e: RunEvent) {
    // Pure FSM transitions - same logic as current Progress.ts applyStreamEvent()
    // Extracted verbatim, no changes to business logic
    switch (e.type) {
      case 'run_started':   this._resetAllAtoms(); break
      case 'phase_start':   this._setAtomState(e.step, 'active', e); break
      case 'phase_done':    this._setAtomState(e.step, 'done', e); break
      case 'phase_error':   this._setAtomState(e.step, 'error', e); break
      case 'phase_retry':   this._incrementAttempt(e.step, e); break
      case 'gate_opened':   this._setAtomState(e.step, 'waiting', e); break
      case 'gate_decided':  this._applyGateDecision(e); break
      case 'checkpoint':    this._setAtomState(e.step, 'done', e); break
      case 'usage_recorded': this._applyUsage(e); break
      case 'budget_warning':
      case 'budget_exceeded':
      case 'budget_gate_opened':
      case 'budget_gate_decided': this._applyBudgetEvent(e); break
    }
  }

  scrubTo(index: number) {
    // Recompute atom and cost states by replaying _history[0..index]
    this._atoms = this._buildIdleAtoms()
    this._cost = emptyCostSnapshot()
    for (let i = 0; i <= index; i++) this.applyEvent(this._history[i])
    this._scrubIndex = index
    this.emit('scrub', index, this.snapshot())
  }

  resumeLive() {
    this._scrubIndex = -1
    this.emit('snapshot', this.snapshot())
  }
}
```

### Cost folding rules

`usage_recorded` events are folded into `CostSnapshot` using recorded values
only. EventEngine must not call a pricing API during replay.

Rules:

- `cost.effective_cost` increments `effectiveUsd`.
- `cost.provider_reported_cost` increments `providerReportedUsd`.
- `cost.estimated_cost` increments `estimatedUsd`.
- Missing cost increments `unknownCostCount`.
- Token fields increment both top-level totals and grouped buckets.
- Group keys are provider name, model, role, and atom id.
- Budget fields update `remainingRunBudgetUsd` when present.
- Source counters increment from `cost.source`.

The same fold runs for live mode and replay mode, so the HUD and timeline never
diverge.

### Migration from Progress.ts

The `applyStreamEvent` logic in `Progress.ts` (lines ~1066-1137) is moved verbatim into `EventEngine.applyEvent()`. Progress.ts then listens to `engine.on('snapshot', ...)` instead of calling `applyStreamEvent` directly. This is the only code change to the existing file during Phase 1.

---

## Three.js Scene Binding

`SceneManager.ts` subscribes to `EventEngine` and mutates scene objects in response.

```typescript
class SceneManager {
  private _engine: EventEngine
  private _atoms: Map<string, AtomNode> = new Map()
  private _edges: Map<string, EdgeMesh> = new Map()
  private _particles: ParticleSystem

  constructor(engine: EventEngine, canvas: HTMLCanvasElement) {
    this._engine = engine
    engine.on('event', (e, snapshot) => this._onEvent(e, snapshot))
    engine.on('snapshot', (snapshot) => this._applyFullSnapshot(snapshot))
    engine.on('scrub', (index, snapshot) => this._applyFullSnapshot(snapshot))
  }

  private _onEvent(e: RunEvent, snapshot: EngineSnapshot) {
    // Incremental update: only touch atoms affected by this event
    const atom = this._atoms.get(e.step)
    if (atom) atom.setState(snapshot.atoms[e.step])
    this._particles.emit(e)
  }

  private _applyFullSnapshot(snapshot: EngineSnapshot) {
    // Full redraw: used on history load and replay scrub
    for (const [id, status] of Object.entries(snapshot.atoms)) {
      this._atoms.get(id)?.setState(status)
    }
  }
}
```

---

## AtomNode State -> Three.js Material

`AtomNode.setState(status: AtomStatus)` mutates the mesh material. Use `TWEEN` or a custom lerp to animate material property changes - never set them immediately.

```typescript
setState(status: AtomStatus) {
  const target = STATE_MATERIALS[status.state]  // pre-computed material configs
  
  // Tween: current emissiveIntensity -> target.emissiveIntensity over 400ms
  // Tween: current color -> target.color over 300ms
  // Trigger state-specific animations (shake, pulse, flash)
  
  this._label.update(status)   // CanvasTexture label refresh
}
```

`STATE_MATERIALS` is a static map - avoids material object allocation per event.

---

## Particle System

The particle system uses a single `THREE.Points` object with a custom `ShaderMaterial` to avoid per-particle draw calls.

```typescript
// ParticleSystem.ts
// Vertex shader: reads per-particle position and alpha from Float32Array attributes
// Fragment shader: draws a soft circle, modulates alpha by lifetime

class ParticleSystem {
  private _pool: ParticlePool  // Fixed-size Float32Array, 500 particles max
  private _points: THREE.Points

  emit(event: RunEvent) {
    const config = EVENT_PARTICLE_CONFIG[event.type]
    if (!config) return
    const startPos = this._resolveAtomPosition(event.step ?? event.project_id)
    this._pool.spawn(startPos, config)
  }

  update(dt: number) {
    this._pool.tick(dt)
    this._points.geometry.attributes.position.needsUpdate = true
    this._points.geometry.attributes.alpha.needsUpdate = true
  }
}
```

---

## Accessibility Tree

`AccessibilityTree.ts` maintains a hidden `<ul>` in the DOM that mirrors AtomStateMap. It is updated by the same `engine.on('snapshot')` listener. Screen readers consume this tree. It is never `display: none` - only visually hidden via `clip-path` and `position: absolute`.

```html
<!-- Generated by AccessibilityTree.ts -->
<ul aria-label="Workflow run status" class="sr-only">
  <li aria-label="memory_refresh: done">Memory Refresh - completed</li>
  <li aria-label="architect: active">Architect - in progress</li>
  <li aria-label="implementation: idle">Implementation - waiting</li>
  ...
</ul>
```

Live region: wrap the `<ul>` in `<div aria-live="polite" aria-relevant="text">` so state changes are announced.

---

## Fallback HTML View

When WebGL is unavailable, `GameShell.ts` skips canvas initialization and instead mounts a `FallbackView` that renders `AccessibilityTree` content as a visible styled list - equivalent to the current Progress.ts tab view. The same `EventEngine` drives it, so no logic is duplicated.

```typescript
// GameShell.ts
const canvas = document.createElement('canvas')
const gl = canvas.getContext('webgl2') || canvas.getContext('webgl')

if (!gl) {
  new FallbackView(engine, container)
} else {
  new SceneManager(engine, canvas)
  container.appendChild(canvas)
}
```

---

## SSE Edge Cases

**Race condition on page load:** EventEngine fetches history before opening SSE. The backend's `SimpleEventBus` pre-seeds subscribers with the last 256 events on connect, so no events are dropped in the gap. EventEngine deduplicates by timestamp on SSE connect.

**Reconnect:** `EventSource` auto-reconnects. On reconnect, EventEngine re-fetches history (last 500 events), diffs against current `_history` array, and appends only new events. Atom states are re-derived from the full history to avoid drift.

**Scrub then reconnect:** If user is in scrub mode when SSE reconnects, EventEngine buffers new events silently. Resuming live (`resumeLive()`) catches up by replaying buffered events at 10x speed.

**Large histories (> 5000 events):** EventEngine loads only the last 500 events for state derivation. For replay beyond that, it fetches additional pages lazily on `scrubTo(index < loaded_start)`.

---

## Three.js Dependencies

Add to `package.json`:

```json
{
  "three": "^0.165.0",
  "@types/three": "^0.165.0"
}
```

No Three.js addons or contrib packages required for Phase 1. `OrbitControls` is an optional addition for desktop; mobile uses custom gesture handling.

Avoid `three/examples/jsm/postprocessing/EffectComposer` for Phase 1 - use CSS filter bloom (`filter: blur`) on the canvas as a cheaper approximation until profiling confirms WebGL post-processing is safe on low-end mobile.

---

## Performance Targets

| Metric | Target |
|---|---|
| Initial render (history load + scene build) | < 800ms on iPhone 12 |
| Per-event update (incremental) | < 4ms (fits in 16ms frame) |
| Full snapshot redraw (scrub) | < 16ms for <= 30 atoms |
| Memory usage (JS heap) | < 80MB |
| Particle pool | 500 max, recycled |
| Draw calls per frame | < 20 (instanced atoms, single Points) |

---

## Testing Strategy

- `EventEngine` is pure TypeScript with no DOM or Three.js dependency. Unit-test the FSM transitions with a mock event stream (reuse fixtures from `web/backend/tests/`).
- `SceneManager` integration: snapshot-test scene state after replaying a fixture event sequence.
- `AccessibilityTree`: assert ARIA labels update correctly on each event type using jsdom.
- No mocks of the backend - use the existing test event fixtures.
