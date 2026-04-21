# Product Direction: Guildr As A Strategy Game

## Position

Guildr is not an admin console for agents. It is a strategy game about making
software with agents, memory, events, and human intervention.

The user is the operator. The project is the battlefield. Workflow steps are
atoms. Agents are specialists. MemPalace is the memory spine. The event stream
is time. Cost is the run economy. Replay is how the operator learns from a run
and proves what happened.

This direction is not decorative. It is the product architecture.

## Non-Negotiables

1. The primary project run view must become a Three.js map.
   The current HTML progress view can remain as fallback and inspector surface,
   but it cannot remain the main experience.

2. MemPalace must be visible in the map.
   Memory is not a settings tab. It is part of the world model.

3. Events must drive the world.
   Live SSE and durable event history must flow through one EventEngine that
   updates both the Three.js scene and fallback DOM.

4. Replay must be first-class.
   A past run should be scrubbed like a timeline in a tactics game. The user
   must be able to see atoms activate, gates open, memory sync, agents fail,
   escalations happen, costs accumulate, and artifacts crystallize.

5. The phone is the reference device.
   Desktop can be richer, but iOS portrait must feel native: safe areas,
   thumb reach, bottom controls, sheets, spring motion, and no wall of forms.

6. Text belongs in DOM overlays.
   Three.js renders space, state, motion, relationships, pulses, and replay.
   DOM renders readable text, forms, accessibility, and precise controls.

7. Every visible object must answer "why am I here?"
   An atom is not just a node. It must expose goal, inputs, memory, events,
   artifact outputs, current state, and next valid operator actions.

## My Architecture Call

The correct architecture is a hybrid game shell:

- `GameShell` owns canvas lifecycle, renderer sizing, device pixel ratio,
  orientation, safe area behavior, and fallback detection.
- `EventEngine` owns all run state and all event replay logic.
- `SceneManager` owns Three.js objects and receives snapshots from
  `EventEngine`.
- `HudLayer` owns native-feeling DOM overlays: command sheets, focus panels,
  memory search, cost panels, replay controls, and logs.
- `FallbackProgressView` remains available for accessibility, old devices,
  testing, and emergency operation.

The map is not a separate gimmick route forever. It starts as a parallel route
or tab for safety, but the long-term default project run view is the game map.

## World Model

The scene should be built from five core object types:

- Atom nodes: executable workflow units.
- Edges: dependencies, handoffs, or traceability links.
- Memory structures: MemPalace wing, rooms, drawers, search results, wake-up
  packet state.
- Artifacts: PRD, sprint plan, phase files, test report, review, deploy notes.
- Cost markers: spend rings, budget gates, source confidence, and burn-rate
  traces.
- Event pulses: live or replayed state transitions moving through the graph.

The graph should not look like a generic flowchart. It should look like an
operational board where each atom has power, state, history, and relationships.

## Replay Model

Replay must re-derive state from the durable event ledger. Do not store scene
history as mutable graphics state.

Required flow:

1. Load workflow.
2. Load event history.
3. Build idle atom map.
4. Replay events from index zero to target index.
5. Fold usage and budget events into the cost snapshot.
6. Emit snapshot.
7. Scene renders snapshot.
8. DOM overlays render selected detail.

This makes replay deterministic, testable, and compatible with low-context
debugging.

## Interaction Model

On iPhone:

- Tap atom: open bottom sheet with atom detail.
- Long press atom: open action sheet.
- Drag canvas: pan.
- Pinch: zoom.
- Double tap: fit map.
- Swipe up timeline: expand replay controls.
- Drag timeline: scrub.
- Tap memory arc: open memory search sheet.
- Tap gate atom: open decision sheet.
- Tap cost badge: open economics sheet.

On desktop:

- Same model, but focus panel can dock on right.
- Keyboard shortcuts can augment, not replace, touch actions.

## Implementation Bias

Build this in thin layers. Do not rewrite the whole PWA at once.

Order:

1. Extract `EventEngine`.
2. Keep current Progress view working from `EventEngine`.
3. Add a Three.js canvas shell with static workflow atoms.
4. Bind atom states to event snapshots.
5. Add cost snapshots and budget HUD.
6. Add replay scrubber.
7. Add memory arc.
8. Add artifact crystals.
9. Replace default Progress route with game shell when stable.

This gives the council-facing experience without sacrificing the current
operator controls.

## What Claude Got Right

- EventEngine as the only adapter is the correct spine.
- DOM overlay plus Three.js scene is the right split.
- Replay should be a camera/time operation, not a log filter.
- Phase 0 must be non-breaking.
- Mobile safe-area and bottom controls are mandatory.

## What I Am Adding

- The map is the eventual default, not a nice extra.
- MemPalace must be spatially persistent, not hidden in a tab.
- Every atom must expose goal, memory, events, artifacts, and operator actions.
- Replay must be deterministic from event history and testable as a pure FSM.
- Cost must be event-sourced so replay shows spend, tokens, source, and budget
  state exactly as the operator saw it.
- The iPhone experience is the baseline, not a later polish pass.

## Acceptance Test For The Direction

If a user opens a project on an iPhone, they should immediately understand:

- what the system is doing now,
- which atom is active,
- where memory is coming from,
- what has already happened,
- what failed or is waiting,
- what the current run has spent,
- what they can touch,
- how to replay the run,
- and how to intervene.

If the screen feels like an admin dashboard, the design failed.
