# Three.js Orchestration Client - Architecture Overview

## Purpose

This document defines the architecture for replacing the current tab-based HTML/CSS Progress view with a Three.js-based strategy-game client. The client is mobile-first, native-feeling, and treats the workflow run as a living map of atoms, connections, memory, cost, and events - not a log viewer.

The current `web/frontend/src/views/Progress.ts` remains the reference data model and API contract. The Three.js client is a new rendering layer on top of the same SSE stream and event-history endpoints.

---

## Mental Model: The Orchestration Map

Every run is a **directed graph of atoms** executing through time. The player (operator) views this graph from above - a top-down strategy map - and can zoom into any atom to inspect its state, memory access, SDLC loop, inputs, and outputs. Time is the third axis: scrubbing the replay timeline moves atoms backward and forward through their states.

```
World Space (Three.js Scene)
||| OrchestrationMap          <- primary view, always visible
|   ||| AtomNode[]            <- one per workflow step
|   ||| EdgeMesh[]            <- directed connections between atoms
|   ||| GateNode[]            <- decision gates (require input)
|   ||| MemPalaceOverlay      <- floating memory wing above the map
|   ||| ArtifactLayer         <- outputs anchored to producing atoms
|   ||| CostLayer             <- spend rings, budget gates, burn-rate traces
|   ||| LoopLayer             <- SDLC loop bands and repair cycles
||| ReplayTimeline            <- bottom HUD bar
||| FocusPanel                <- right side-drawer (atom detail)
||| CommandBar                <- top input area (inject instruction)
||| MinimapWidget             <- bottom-left corner (iOS-style)
```

---

## Layered Architecture

```
|||||||||||||||||||||||||||||||||||||||||||||||
|             PWA Shell (index.html)           |
|   Service Worker * Routing * Offline Cache   |
|||||||||||||||||||||||||||||||||||||||||||||||
|          GameShell (GameShell.ts)            |
|  Canvas mount * Orientation * Assets * Safe Areas |
|||||||||||||||||||||||||||||||||||||||||||||||
|  Three.js Scene  |   React-free UI overlay  |
|  (canvas layer)  |   (DOM layer, z-index +1) |
|                  |   HUD * Panels * Dialogs  |
|||||||||||||||||||||||||||||||||||||||||||||||
|           EventEngine (EventEngine.ts)       |
|  SSE consumer * history loader * atom/cost/loop FSM |
|||||||||||||||||||||||||||||||||||||||||||||||
|           Backend API (unchanged)            |
|  /stream * /events * /control * /memory     |
|||||||||||||||||||||||||||||||||||||||||||||||
```

### Layer responsibilities

**GameShell.ts** - mounts the `<canvas>`, manages `THREE.WebGLRenderer`, handles `devicePixelRatio`, safe-area insets, orientation changes, initializes `AssetManager`, and hands off input events to the scene manager.

**SceneManager.ts** - owns the `THREE.Scene`, `THREE.Camera`, animation loop (`requestAnimationFrame`), and the set of renderable objects. Translates abstract state changes (atom activated, gate opened) into scene mutations.

**AssetManager.ts** - owns the runtime visual asset manifest, loads vendored assets from `assets/`, caches textures/fonts, exposes placeholders for optional failures, and reports load progress to the PWA shell. Scene systems do not hard-code asset paths.

**EventEngine.ts** - single source of truth for run state. Connects to `/api/projects/{id}/stream` via EventSource. On load, fetches `/api/projects/{id}/events?limit=500` to prime history. Drives an `AtomStateMap` (keyed by step id -> FSM state), `CostSnapshot` (folded from usage and budget events), and `LoopSnapshot` (folded from SDLC loop events). The Three.js scene reads from this map; it never calls the API itself.

**HUDLayer (DOM overlay)** - thin HTML elements absolutely positioned over the canvas for text-heavy content: event detail pane, instruction input, memory search, and economics panels. Styled with CSS variables that mirror the Three.js color grammar. These elements are `pointer-events: none` by default; only active panels capture input.

**AccessibilityTree** - hidden `<ul>` updated in sync with AtomStateMap. Screen readers and fallback-no-WebGL users use this. It mirrors the current tab-based Progress view structure.

---

## Scene Graph Structure

```
Scene
||| AmbientLight
||| DirectionalLight (top-down, soft shadows)
||| MapGroup
|   ||| PlatformMesh        (ground plane, hex grid texture)
|   ||| AtomGroup
|   |   ||| AtomNode[N]     (instanced if >20 atoms)
|   ||| EdgeGroup
|   |   ||| EdgeMesh[N]     (tube geometry, animated dash)
|   ||| GateGroup
|       ||| GateNode[N]
||| MemPalaceGroup
|   ||| WingHalo            (floating arc above map)
|   ||| MemoryOrb[N]        (one per loaded memory fragment)
||| ArtifactGroup
|   ||| ArtifactCard[N]     (flat planes anchored to atoms)
||| CostGroup
|   ||| AtomCostRing[N]     (thin rings around atoms that spent budget)
|   ||| BudgetGate[N]       (warning/approval markers)
|   ||| BurnRateTrace       (optional replay timeline overlay source)
||| LoopGroup
|   ||| AtomLoopBand[N]     (orbit bands for active lifecycle stages)
|   ||| RepairArc[N]        (verify -> repair -> verify cycles)
|   ||| LoopLaneTrace       (replay timeline loop lane source)
||| ParticleSystem          (event pulses travelling along edges)
||| PostProcessing
    ||| BloomPass           (active atoms glow)
    ||| FXAAPass
```

---

## Asset Integration

The Three.js client must use the vendored asset kit documented in
`assets/README.md` and governed by `docs/threejs-asset-pipeline.md`.

Runtime rules:

- `AssetManager` is the only loader for scene assets.
- Texture paths come from a typed manifest, not scattered string literals.
- The first scene render uses the hex grid substrate, atom material grain,
  particle disc, and core fonts.
- HDRI lighting is allowed after first render unless profiling proves it can
  fit the initial mobile budget.
- The post-processing lens dirt texture is reference-only until a mobile-sized
  derivative exists.
- If optional assets fail, the scene falls back to flat materials and DOM
  labels while keeping EventEngine interaction intact.

Asset-to-system map:

- Platform: `assets/environments/hex-grid.png`.
- Atom and gate materials: `assets/atom-meshes/flat-normal.png` and
  `assets/atom-meshes/canvas-grain.png`.
- Particles: `assets/edge-particle-sprites/disc.png` and `spark1.png`.
- Memory arc/orbs: `assets/mempalace/radial-alpha-gradient.png` and
  `lensflare0.png`.
- Artifact cards: `assets/artifact-textures/canvas-grain.png`.
- Icons and fonts: `assets/icon-sprites/tabler-icons.woff2`,
  `assets/fonts/InterVariable.woff2`, and
  `assets/fonts/JetBrainsMono-Regular.woff2`.

---

## Camera and Navigation

**Default view:** Orthographic projection, top-down 60 degrees tilt, auto-framing the full workflow graph on load.

**Gestures (mobile-first):**
- Single finger drag -> pan camera
- Pinch -> zoom
- Double tap atom -> focus zoom + open FocusPanel
- Long press atom -> context menu (inspect, skip, re-run)
- Swipe up from bottom -> expand ReplayTimeline
- Two-finger swipe left/right on timeline -> scrub replay

**Camera animation:** All camera moves use `gsap` tweens (or a minimal custom easer) so transitions feel native-smooth, not jarring.

---

## State Machine per Atom

Each atom node runs through this FSM, driven by EventEngine:

```
idle -> active -> done
              -> error -> (retry) -> active
              -> waiting          (gate)
waiting -> done
        -> error
```

Each state maps to a distinct visual representation (see visual grammar doc).

---

## MemPalace Integration

MemPalace is not optional. The `MemPalaceGroup` is always visible in the scene, rendered as a semi-transparent arc floating above and behind the workflow map. Its state is polled from `/api/projects/{id}/memory/status` on load and after each `memory_refresh` phase completion.

Memory search results surface as `MemoryOrb` nodes that briefly orbit the relevant atom before fading.

---

## Cost Integration

Cost is rendered from the event ledger, not from live-only counters. `EventEngine`
folds `usage_recorded`, `budget_warning`, `budget_exceeded`,
`budget_gate_opened`, and `budget_gate_decided` events into a `CostSnapshot`.

Scene responsibilities:

- `CostLayer` renders a thin spend ring around each atom that has usage.
- Budget warnings pulse the atom ring, not the whole scene.
- Budget gates render as gate nodes with a cost badge and require the same
  resumable decision flow as other gates.
- The replay timeline can switch between event density and cost density.

DOM overlay responsibilities:

- The top HUD shows run cost, budget remaining, and unknown-cost count.
- The focus panel shows atom cost by provider, model, source, and confidence.
- The economics sheet groups spend by provider, model, role, phase, and atom.

Replay behavior:

- Scrubbing to event index `N` recomputes cost by folding events `0..N`.
- Historical cost never changes when current provider pricing changes.
- Provider-reported cost and local estimates stay visually distinct.

---

## SDLC Loop Integration

SDLC loops are rendered from event history. `EventEngine` folds `loop_entered`,
`loop_progressed`, `loop_blocked`, `loop_repaired`, `loop_completed`, and
`loop_reopened` events into a `LoopSnapshot`.

Scene responsibilities:

- `LoopLayer` renders lifecycle bands around atoms.
- Active loop bands animate; inactive loop bands remain thin and quiet.
- Failed verify loops physically route into repair arcs.
- Guru escalation appears inside repair, not as an unrelated node.
- MemPalace sync appears as the learn loop and connects to the memory arc.

DOM overlay responsibilities:

- The focus panel shows current loop, next expected loop, evidence required,
  artifact emitted, repair count, and reopened state.
- The replay timeline has a loop lane that can filter to build, verify, repair,
  review, ship, or learn.

Replay behavior:

- Scrubbing to event index `N` recomputes loop state by folding events `0..N`.
- Loop animation must be deterministic from event order and `event_id`.
- Loop state must remain readable on iPhone portrait with cost rings enabled.

---

## Fallback

If `WebGL` is unavailable or the user opts out, `GameShell.ts` renders the `AccessibilityTree` as a styled HTML list - functionally equivalent to the current tab-based Progress view. No logic is duplicated; both views consume `EventEngine`.

---

## File Layout (proposed)

```
web/frontend/src/
||| game/
|   ||| GameShell.ts
|   ||| SceneManager.ts
|   ||| EventEngine.ts
|   ||| assets/
|   |   ||| AssetManager.ts
|   |   ||| manifest.ts
|   ||| atoms/
|   |   ||| AtomNode.ts
|   |   ||| GateNode.ts
|   |   ||| EdgeMesh.ts
|   ||| memory/
|   |   ||| MemPalaceGroup.ts
|   |   ||| MemoryOrb.ts
|   ||| cost/
|   |   ||| CostLayer.ts
|   |   ||| CostRing.ts
|   ||| loops/
|   |   ||| LoopLayer.ts
|   |   ||| AtomLoopBand.ts
|   |   ||| RepairArc.ts
|   ||| hud/
|   |   ||| ReplayTimeline.ts
|   |   ||| FocusPanel.ts
|   |   ||| CommandBar.ts
|   |   ||| MinimapWidget.ts
|   ||| accessibility/
|       ||| AccessibilityTree.ts
||| views/
    ||| Progress.ts             <- kept; EventEngine extracted from it
```
