# Three.js Orchestration Client - Architecture Overview

## Purpose

This document defines the architecture for replacing the current tab-based HTML/CSS Progress view with a Three.js-based strategy-game client. The client is mobile-first, native-feeling, and treats the workflow run as a living map of atoms, connections, memory, and events - not a log viewer.

The current `web/frontend/src/views/Progress.ts` remains the reference data model and API contract. The Three.js client is a new rendering layer on top of the same SSE stream and event-history endpoints.

---

## Mental Model: The Orchestration Map

Every run is a **directed graph of atoms** executing through time. The player (operator) views this graph from above - a top-down strategy map - and can zoom into any atom to inspect its state, memory access, inputs, and outputs. Time is the third axis: scrubbing the replay timeline moves atoms backward and forward through their states.

```
World Space (Three.js Scene)
||| OrchestrationMap          <- primary view, always visible
|   ||| AtomNode[]            <- one per workflow step
|   ||| EdgeMesh[]            <- directed connections between atoms
|   ||| GateNode[]            <- decision gates (require input)
|   ||| MemPalaceOverlay      <- floating memory wing above the map
|   ||| ArtifactLayer         <- outputs anchored to producing atoms
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
|  Canvas mount * Orientation * Safe Areas    |
|||||||||||||||||||||||||||||||||||||||||||||||
|  Three.js Scene  |   React-free UI overlay  |
|  (canvas layer)  |   (DOM layer, z-index +1) |
|                  |   HUD * Panels * Dialogs  |
|||||||||||||||||||||||||||||||||||||||||||||||
|           EventEngine (EventEngine.ts)       |
|  SSE consumer * history loader * atom FSM   |
|||||||||||||||||||||||||||||||||||||||||||||||
|           Backend API (unchanged)            |
|  /stream * /events * /control * /memory     |
|||||||||||||||||||||||||||||||||||||||||||||||
```

### Layer responsibilities

**GameShell.ts** - mounts the `<canvas>`, manages `THREE.WebGLRenderer`, handles `devicePixelRatio`, safe-area insets, orientation changes, and hands off input events to the scene manager.

**SceneManager.ts** - owns the `THREE.Scene`, `THREE.Camera`, animation loop (`requestAnimationFrame`), and the set of renderable objects. Translates abstract state changes (atom activated, gate opened) into scene mutations.

**EventEngine.ts** - single source of truth for run state. Connects to `/api/projects/{id}/stream` via EventSource. On load, fetches `/api/projects/{id}/events?limit=500` to prime history. Drives an `AtomStateMap` (keyed by step id -> FSM state). The Three.js scene reads from this map; it never calls the API itself.

**HUDLayer (DOM overlay)** - thin HTML elements absolutely positioned over the canvas for text-heavy content: event detail pane, instruction input, memory search. Styled with CSS variables that mirror the Three.js color grammar. These elements are `pointer-events: none` by default; only active panels capture input.

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
||| ParticleSystem          (event pulses travelling along edges)
||| PostProcessing
    ||| BloomPass           (active atoms glow)
    ||| FXAAPass
```

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
|   ||| atoms/
|   |   ||| AtomNode.ts
|   |   ||| GateNode.ts
|   |   ||| EdgeMesh.ts
|   ||| memory/
|   |   ||| MemPalaceGroup.ts
|   |   ||| MemoryOrb.ts
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
