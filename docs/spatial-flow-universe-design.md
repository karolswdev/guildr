# Spatial Flow Universe Design

## Purpose

The zero-g map must show orchestration as a living universe. Objects float in
space, but the product value comes from seeing the flows between them: work,
memory, review pressure, cost, repair, replay, and human intervention.

This document defines the next design and implementation plan for representing
those flows in the Three.js PWA.

## Current Baseline

Already implemented:

- Perspective zero-g graph in `SceneManager`.
- Floating atom/gate objects in `AtomNode`.
- Curved `CatmullRomCurve3` tethers in `EdgeMesh`.
- Travelling pulse sprites on tethers.
- Soft loop halos and labels.
- Poly Pizza GLB props loaded as deferred scene objects.
- Mobile HUD and radial action ring for Shape/Nudge/Intercept.
- EventEngine snapshots for atom, cost, loop, and replay state.

Known gaps:

- Flow visuals are still mostly generic pulses.
- The scene does not yet distinguish normal work, memory, gates, review,
  repair, cost, operator intent, or replay direction strongly enough.
- Flow particles are per-edge sprites, not a scalable system.
- User gestures do not yet create physical ghost tethers or visible intent
  energy.

## Product Principle

Flows are not diagram edges. They are physical phenomena:

- Dependencies are tension.
- Active work is traffic.
- Memory is atmosphere.
- Review is pressure.
- Cost is dust.
- Failure is fracture.
- Human intervention is force.
- Replay is time direction.

The operator should be able to understand the run from motion before reading
any panel.

## Universe Object Types

| Object | Scene role | Current file | Planned behavior |
| --- | --- | --- | --- |
| Atom | Workflow unit | `atoms/AtomNode.ts` | Status body, selection halo, local flow ports |
| Gate | Approval/review lock | `atoms/AtomNode.ts` | Amber shield, charge buildup, accept/reject burst |
| FlowPath | Dependency / relationship | `atoms/EdgeMesh.ts` now | New first-class path owning curve, material, particles |
| FlowParticle | Event packet | `SceneManager.ts` now | Instanced/sprite pool driven by event stream |
| LoopField | Local lifecycle gravity | `layout.ts`, `SceneManager.ts` | Soft field around related atoms, no hard rails |
| MemoryField | Context source | future | Teal mist and recall streams into atoms |
| Artifact | Output body | future | Crystallized objects emitted by atoms |
| ContentPreview | Generated content surface | future | Tangent preview patch on an atom/artifact, expands by zoom/selection |
| SpeechTail | Agent utterance | future | Short comet-like text ribbon from speaker toward recipient |
| OperatorIntent | Human intervention | `GameShell.ts` + `/intents` | Gesture beam, ghost tether, persistent intent pulse |
| SceneProp | Spatial ambience | Poly Pizza GLBs | Deferred context bodies, never first-frame blockers |

## Loop Cluster Layout Language

Loops must read as physical groupings, not as drawn UI rails. The operator
should be able to tell that a loop is a loop because its members share motion,
field color, barycenter, and transfer paths.

### Core Metaphor

A loop is a small gravitational system:

- The loop has an invisible barycenter.
- Member atoms are small planets, moons, or crystals orbiting the barycenter at
  different radii and inclinations.
- Minor events become motes or satellites around the member that produced them.
- The loop field is a soft volumetric haze, not a hard circle.
- Repeated iterations leave faint orbit trails. Three trips around the loop
  should look like three history traces, not like three identical rings.

Nested loops become moon systems inside a larger loop. For example, a persona
forum inside a build phase should look like several small bodies orbiting one
agent body, while that whole local system also participates in the wider SDLC
loop.

### Logical Placement

The first pass should use a deterministic authored galaxy layout rather than a
general physics solver. It needs to be stable enough for muscle memory.

Recommended cluster placement:

| Cluster | Position bias | Visual tone | Meaning |
| --- | --- | --- | --- |
| Memory / Learn | rear-left / upper | teal haze | context source and long-term recall |
| Discover / Plan | upper-left | cyan / blue | decomposition, architecture, task shaping |
| Build | center | white / blue | active production and artifact accretion |
| Verify / Review | upper-right | amber / green | gates, tests, critique, approval |
| Repair | lower-center return arc | red to amber to green | recovery and reroute pressure |
| Ship | lower-right / outward | teal / white | release, handoff, deployment |

Transfer corridors connect clusters. Avoid all-to-all spaghetti. A normal run
should read as: memory feeds planning, planning transfers to build, build
pushes to verify/review, review either releases to ship or bends back into
repair/build.

### Orbit Behavior

Each loop member gets deterministic orbital parameters:

- `cluster_id`
- `barycenter`
- `orbit_radius`
- `orbit_inclination`
- `orbit_phase`
- `orbit_speed`
- `importance`
- `collapsed`

Importance controls level of detail. On mobile galaxy view, a cluster should
show three to five dominant bodies plus orbiting motes. Pinch or tap expands
the cluster so minor members resolve into individual planets.

Motion rules:

- Build and planning bodies orbit calmly.
- Waiting gates slow nearby bodies and create amber charge.
- Repair creates a visible return arc from verify/review back to build.
- Learning creates a slow outbound arc to the memory cluster.
- Active work slightly pulls the camera and nearby motes toward the active
  body, but never enough to break the stable cluster layout.

### Acceptance For Loops

A loop cluster works when a user can answer these without opening text:

- Which bodies belong to the same loop?
- Which stage is the loop in?
- How many recent iterations happened?
- Is the loop progressing forward, waiting, or bending back into repair?
- Which cluster will receive the next transfer?

If the answer depends on a label alone, the loop language is too weak.

## Content Preview And Speech Layer

Generated content must be visible in the world. The map should answer: who is
creating what, where is it going, and what depends on it.

### Planet-Surface Previews

Do not default to rectangular dashboard cards floating beside every atom. For
agent-owned work, the preview should look like content appearing on the
surface of the object that produced it.

Preview level of detail:

| Distance / focus | Rendering | Content |
| --- | --- | --- |
| Far | colored surface patch with glyph | type, rough size, activity |
| Mid | tangent slab facing camera | title plus two or three lines |
| Near / selected | readable preview surface | scrollable excerpt or diff summary |

This keeps content inside the zero-g metaphor. The content is terrain, not an
external web panel.

Preview types:

- Text/prose: soft paper-like slab on the source body.
- Code/diff: angular crystal facet with monospace excerpt.
- Test result: small verdict shard orbiting the artifact.
- Diagram: wireframe panel that assembles edge by edge.
- Memory snippet: translucent teal patch that drifts into the consumer.
- User intent: bright white/cyan mark injected into the target body.

### Artifact Accretion

An artifact under construction is a small body forming near its author.

Visual lifecycle:

1. Seed: faint mote appears near the agent when work starts.
2. Draft: particles stream from agent to mote and the body gains mass.
3. Review: amber/green inspection shards orbit the artifact.
4. Final: artifact stabilizes into an orbit or transfers to the next cluster.
5. Rework: artifact cracks, sheds red fragments, then accretes again.

File/content type controls silhouette:

- Code: angular crystal lattice growing face by face.
- Prose: folded slab or scroll-like sheet.
- Plan: blue architectural prism with clean edges.
- Test output: compact verdict capsule.
- Deployment artifact: brighter outbound satellite.

Progress bars should be avoided in the world layer. Progress is visible through
mass, completeness, and particle density.

### Speech Tails

Agent messages should not become a wall of chat bubbles. Treat speech as a
directional trail.

Visual:

- A short text ribbon curves from speaker toward recipient.
- The ribbon has comet-tail particles, so direction is obvious.
- Short messages are readable in-place for a few seconds.
- Longer reasoning compresses to a glowing streak until selected.
- Broadcasts drift toward the cluster barycenter instead of one recipient.

Lifecycle:

- Fresh speech is readable and bright.
- Recent speech fades into a compact streak.
- Historical speech collapses into a tiny replay marker on the flow path.
- Selecting a speech tail freezes it and opens the full event detail.

Mobile rules:

- At most one primary readable speech tail per focused cluster.
- Show up to two secondary speech chips as small off-axis streaks.
- Offscreen speech collapses into edge badges that can warp the camera to the
  speaker and recipient.
- A thin bottom "now" strip may show the last few utterances, but it should be
  peripheral awareness, not a dashboard takeover.

### Overlay Architecture

Readable text should be a DOM/WebGL hybrid:

- Three.js owns anchors, tethers, depth checks, and occlusion priority.
- A `WorldLabelLayer` or `ContentPreviewLayer` owns readable DOM text.
- Anchors project from world space to screen space each frame.
- DOM elements are pooled, not recreated per event.
- Labels collapse by priority before they overlap or cover the active body.

The first implementation can use DOM for text clarity and Three.js for the
physical attachment: tangent patch, tether line, glow, and selection state.

## Flow Between Content Objects

Flows should connect agents, artifacts, memories, and gates. When an artifact
is created by one body and consumed by another, the transfer should be visible
as a physical event.

Visual patterns:

- Artifact transfer: the artifact body detaches and drifts along a curved lane.
- Dependency: a faint tension line between artifact and consumer.
- Review request: amber inspection shards move from artifact to reviewer.
- Approved output: teal/green burst pushes the artifact toward the next
  cluster.
- Rejected output: red fracture travels back to the author and the artifact
  returns to draft orbit.

The key is causality. A user should be able to see "this agent made this
thing, this other agent inspected it, and this next cluster consumed it."

## Model-Backed Orchestration Design System

The asset language must model the orchestration engine, not merely decorate it.
The engine is a phase state machine with durable events, loop stages, gates,
usage/cost, artifacts, provider calls, and operator intents. Visual conventions
should attach to those concepts directly.

### Source Asset Kit

The Quaternius Ultimate Space Kit is a strong base pack because it is CC0, has
87 GLB models, and includes animated actors as well as ships, planets, rovers,
mechs, facilities, connectors, pickups, rocks, and telemetry-like props.

Vendored inventory:

- `assets/poly-pizza/ultimate-space-kit/manifest.json`
- `assets/poly-pizza/ultimate-space-kit/models/*.glb`

Runtime rule: this kit is deferred. It must not block first render and must not
be fully loaded on mobile. The scene loads a small semantic subset based on
visible loop clusters and current events.

### Engine Concept To Model Convention

| Engine concept | Loop stage | Primary model language | Behavior |
| --- | --- | --- | --- |
| `memory_refresh` | `learn` | antenna, radar, solar panel, teal habitat | emits slow memory mist and recall streams |
| `persona_forum` | `discover` | small astronaut council or clustered moons | emits multiple speech tails around one forum barycenter |
| `architect` | `plan` | geodesic dome, base, blueprint crystal | creates plan surfaces and clean transfer corridors |
| `micro_task_breakdown` | `plan` | connector, pickup crate, small task satellites | splits plan artifact into orbiting task packets |
| `implementation` | `build` | mech actor plus code-crystal artifacts | accretes code bodies and sends dense build traffic |
| `testing` | `verify` | rover / round rover, sensor props | patrols artifacts, emits verdict capsules |
| `guru_escalation` | `repair` | large mech, rescue ship, amber repair rig | pulls fractured artifacts into repair orbit |
| `review` | `review` | astronaut reviewer, gate dome, radar sweep | inspects artifacts, emits approve/reject speech tails |
| `deployment` | `ship` | spaceship / outbound base | carries finalized artifacts out of the cluster |
| human gate | `review` or `ship` | shielded dome or connector lock | queues amber pressure until decision |
| budget gate | any | pickup thunder / gold dust field | makes spend pressure visible around path or gate |
| `operator_intent` | any | user astronaut ghost / touch beam | injects visible force from screen edge into target |

These mappings are conventions, not hard identity. A role can keep its abstract
atom body at low LOD, then swap to a model actor when focused or active.

### Actor Animation Semantics

Animated models should turn event state into body language.

Astronaut animations:

- `Idle`: available or observing.
- `Wave`: operator presence, greeting, or attention request.
- `Yes`: approval, accepted gate, successful review.
- `No`: rejected gate, invalid route, blocked instruction.
- `Walk` / `Run`: moving toward active target or transfer lane.
- `Duck`: waiting under review/gate pressure.
- `HitReact`: provider error, validation failure, or failed test.
- `Death`: terminal failure only, used sparingly.

Mech animations:

- `Idle`: build worker ready.
- `Walk` / `Run`: active implementation or tool execution.
- `Pickup`: consumes a task packet or artifact input.
- `Shoot_Small`: emits focused tool/output packet.
- `Shoot_Big`: high-impact build burst or expensive operation.
- `HitRecieve_1` / `HitRecieve_2`: failed command, failed validation, or
  provider error.
- `Yes` / `No`: accepts/rejects a repair proposal.
- `Hello`: worker selected or summoned by operator.

Enemy animations are reserved for blockers, not for normal agents:

- `Flying_Idle`: unresolved risk nearby.
- `Fast_Flying`: urgent failure moving through a path.
- `Headbutt`: blocker colliding with a gate or artifact.
- `HitReact`: repair action affects the blocker.
- `Death`: blocker resolved.

Do not over-animate. On mobile, each focused cluster gets one primary animated
actor, one secondary actor at reduced update frequency, and the rest collapse
to static silhouettes or motes.

### Artifact And Token Conventions

Use pickups and small props as operational tokens:

- `Pickup Crate`: task packet or implementation work unit.
- `Pickup Key Card`: approval credential, permission, gate unlock.
- `Pickup Health`: repair patch or successful recovery.
- `Pickup Thunder`: budget/cost spike or high-energy operator force.
- `Pickup Sphere`: reusable context bundle or memory capsule.
- `Bullets Pickup`: queued tool calls or batch execution packet.
- `Connector`: reroute join, dependency socket, or path splice.

Artifacts should still accrete and stabilize as custom scene objects. The kit
tokens are the readable handles around them, not a replacement for generated
content previews.

### Facilities And Loop Landmarks

Use larger static props as stable landmarks so users do not get lost:

- `Geodesic Dome`: review chamber, council chamber, or gate shell.
- `Base Large`: project hub or current run root.
- `House Pod` / `House Cylinder`: memory habitat or isolated provider station.
- `Roof Radar`: reviewer or telemetry scanner.
- `Roof Antenna`: memory uplink or remote provider call.
- `Solar Panel*`: local compute, energy/cost budget, background runtime health.
- `Building L`: deployment or integration station.

Facilities should be sparse. They establish orientation at galaxy view and
should not compete with active actors.

### Loop Cluster Props

Use the 11 planet models as loop bodies and cluster anchors. A loop cluster can
mix:

- one large planet-like body for the loop barycenter,
- three to five visible member atoms in orbit,
- small task/artifact motes,
- a facility landmark when the cluster has a persistent meaning.

The old decorative planets remain useful as distant scene props, but the
Ultimate Space Kit planets should become the semantic loop vocabulary because
they come from the same coherent art direction as the actors.

### Camera And LOD Contract

The model system needs three camera layers:

1. Galaxy view: clusters resolve to planets, landmarks, and activity pulses.
2. Cluster view: actors, artifacts, speech tails, and transfer corridors become
   readable.
3. Surface view: selected body locks enough rotation for content preview text
   to resolve.

The user should never need to understand a large dashboard to know what is
happening. The camera should follow active actors and flows, while preserving
stable cluster orientation.

## Flow Visual Grammar

### Normal Sequence Flow

Purpose: show ordinary phase-to-phase progression.

Visual:

- Thin blue-white tether.
- One or two small pulse packets.
- Low opacity when idle.
- Brightness rises on active source or target.

Behavior:

- `atom_started` on target sends a pulse along incoming path.
- `atom_completed` sends a completion pulse along outgoing path.
- Pulse speed maps to recency: new pulses move fast, stale pulses fade.

### Planning Flow

Purpose: show deliberate architecture or decomposition work.

Visual:

- Cooler blue/cyan pulses.
- Higher arcing curve with cleaner geometric packets.
- Slightly slower than implementation flow.

Behavior:

- Architect and micro-task steps emit wide, sparse packets.
- Planning paths should look intentional, not noisy.

### Implementation Flow

Purpose: show code-production traffic.

Visual:

- Denser white/blue pulse traffic.
- Path briefly thickens with active tool/file events.
- Small sparks on file-write completion.

Behavior:

- Tool calls and file edits increase packet density.
- Repeated edits add short-lived traffic trails.

### Gate / Review Flow

Purpose: show blocked decision pressure.

Visual:

- Amber tether into gate.
- Pulses slow and queue near the gate.
- Gate forms a translucent shield/shell.
- Approved emits teal burst outward.
- Rejected emits red-orange backflow toward the source.

Behavior:

- `gate_opened` creates charge buildup.
- `gate_decided approved` releases forward.
- `gate_decided rejected` reverses flow and marks repair path.

### Error / Repair Flow

Purpose: show failure and recovery as a physical loop.

Visual:

- Red fracture pulse travels backward from failed atom.
- Repair path uses amber particles moving from failure to fixer/reviewer.
- If guru escalation occurs, draw a temporary high-energy arc to the
  escalation object.

Behavior:

- `loop_blocked` creates red crack effect on atom and backward pulse.
- `loop_repaired` creates amber-to-green transition on repair path.
- Repair loops should leave short ghost trails during replay.

### Memory Flow

Purpose: show context entering work.

Visual:

- Teal mist, not hard pellets.
- Wide translucent stream.
- Slow drift from memory loop/field into target atoms.
- Memory refresh sends a soft wave through the whole graph.

Behavior:

- `memory_refresh` creates global context wave.
- `memory_refs` on events create scoped streams into relevant atoms.
- Memory flow is visually secondary until selected or active.

### Cost / Token Flow

Purpose: make spend visible without turning the map into a finance dashboard.

Visual:

- Fine gold dust riding active paths.
- Dense gold = expensive operation.
- Unknown cost = red static mixed into gold dust.
- Local llama.cpp = lavender/blue pressure particles, not gold dollars.

Behavior:

- `usage_recorded` maps to cost particles at the atom that produced usage.
- Cost particles settle briefly around the atom, then fade into the HUD total.
- Budget gate warning adds amber vibration to expensive active path.

### Operator Intent Flow

Purpose: make the human visibly enter the universe.

Visual:

- User-origin color: bright white core with cyan/amber edge depending action.
- Gesture creates a beam from touch location to atom.
- Submitted intent becomes a persistent packet entering the selected path.
- Shape/reroute creates a ghost tether before submit.

Behavior:

- `interject`: short nudge pulse into selected atom.
- `intercept`: stronger amber stop pulse, gate-like shell forms around atom.
- `reroute`: ghost tether from source atom to target atom, then resolves into
  a new proposed flow path.

### Replay Flow

Purpose: show time as a manipulable dimension.

Visual:

- Forward replay: normal particles move forward.
- Reverse scrub: particles move backward and desaturate.
- Paused replay: particles freeze, with faint motion trails.
- Live mode: live indicator and active flow pulse breathe together.

Behavior:

- `EventEngine.scrubTo(index)` recomputes flow state up to the target event.
- Scene never stores replay-only truth outside the folded snapshot.

## Event Mapping

The first implementation should derive flow changes from existing or near-term
events:

| Event | Flow response |
| --- | --- |
| `atom_started` / phase start equivalent | Incoming active pulse, target glow |
| `atom_completed` | Outgoing completion pulse, atom settles |
| `usage_recorded` | Gold/local-cost particles around atom/path |
| `provider_call_error` | Red fracture pulse and atom error flare |
| `loop_entered` | Stage color activates in local flow field |
| `loop_blocked` | Backflow and repair route charge |
| `loop_repaired` | Amber repair packet turns green on arrival |
| `loop_completed` | Stage field collapses into history glow |
| `budget_gate_opened` | Amber cost pressure around gate/path |
| `budget_gate_decided` | Forward or backward release |
| `operator_intent` | User-origin packet enters atom/path |
| `memory_status` / memory refs | Teal mist stream |

If event names differ in current code, the reducer should adapt through a
small `FlowDirector`, not through ad hoc checks inside `SceneManager`.

## Technical Architecture

### New Modules

```text
web/frontend/src/game/flows/FlowPath.ts
web/frontend/src/game/flows/FlowDirector.ts
web/frontend/src/game/flows/FlowParticles.ts
web/frontend/src/game/flows/FlowTypes.ts
web/frontend/src/game/content/ContentPreviewLayer.ts
web/frontend/src/game/content/SpeechTailLayer.ts
web/frontend/src/game/content/ArtifactAccretion.ts
web/frontend/src/game/interactions/GhostTether.ts
web/frontend/src/game/layout/LoopClusterLayout.ts
web/frontend/src/game/models/ModelCatalog.ts
web/frontend/src/game/models/CharacterActor.ts
web/frontend/src/game/models/AnimationDirector.ts
```

### Responsibilities

`FlowPath`

- Owns one curve between two objects.
- Owns base tether mesh and material.
- Exposes `pointAt(t)` and tangent helpers.
- Maintains visual mode: idle, active, gate, memory, repair, cost, intent.

`FlowParticles`

- Uses pooled sprites or instanced points.
- Avoids creating new Three.js objects per event.
- Supports per-particle color, size, speed, lifetime, and path id.
- Samples `FlowPath.pointAt(t)` during animation.

`FlowDirector`

- Receives `EngineSnapshot` plus recent events.
- Converts events/state into declarative flow commands:
  - start pulse
  - set path mode
  - add cost dust
  - freeze for replay
  - reverse during scrub
  - create user intent packet
- Keeps event-to-visual mapping testable outside WebGL.

`GhostTether`

- Owns drag gesture preview.
- Projects finger position into scene space.
- Draws temporary curve from source atom to hover target or free point.
- Emits `reroute` intent when confirmed.

`ContentPreviewLayer`

- Owns readable DOM/WebGL hybrid labels for content previews.
- Projects selected world anchors into screen space.
- Applies LOD rules for far, mid, and near preview states.
- Collapses labels before overlap becomes unreadable.

`SpeechTailLayer`

- Owns short-lived comet-text ribbons.
- Anchors each utterance to speaker and recipient when known.
- Collapses old speech into replay markers.

`ArtifactAccretion`

- Owns generated artifact bodies and their lifecycle.
- Maps artifact events into seed, draft, review, final, and rework states.
- Emits transfer targets for FlowPath when artifacts move between clusters.

`LoopClusterLayout`

- Replaces fixed loop centers with deterministic orbital cluster parameters.
- Assigns barycenter, orbit radius, inclination, phase, speed, and LOD.
- Keeps cluster layout stable across replay and mobile focus changes.

`ModelCatalog`

- Loads `assets/poly-pizza/ultimate-space-kit/manifest.json`.
- Exposes semantic queries such as `modelsForRole("build")` or
  `modelsForCategory("character.operator")`.
- Keeps all kit models deferred and optional.

`CharacterActor`

- Wraps a GLB scene plus `AnimationMixer`.
- Normalizes scale/origin and exposes high-level states like `idle`,
  `working`, `approving`, `rejecting`, `blocked`, and `repairing`.

`AnimationDirector`

- Converts `EngineSnapshot` plus recent events into actor animation commands.
- Rate-limits animation updates on mobile.
- Ensures only the focused cluster receives full animation playback.

### SceneManager Changes

`SceneManager` should stop directly owning pulse sprites. It should:

- Build atom objects.
- Build `FlowPath` objects from layout edges.
- Hold `FlowDirector` and `FlowParticles`.
- Forward snapshots and recent events into `FlowDirector`.
- Render returned visual commands.

Current `EdgeMesh` can become the first `FlowPath` implementation rather than
being replaced all at once.

## Interaction Design

### Tap FlowPath

Target: tether between objects.

Result:

- Selects relationship, not either endpoint.
- Shows compact relationship ribbon:
  - source
  - target
  - recent events
  - cost on path
  - last failure or gate state

### Long-Press Atom

Target: atom/gate object.

Result:

- Opens Intercept mode directly.
- Visual: amber stop shell forms around atom while finger is held.
- On submit: `operator_intent(kind="intercept")`.

### Drag Atom To Atom

Target: source atom drag.

Result:

- Creates ghost tether from source to hovered target.
- Target highlights if reroute is valid.
- Releasing opens Shape compose dock.
- On submit: `operator_intent(kind="reroute", payload={from,to,instruction})`.

### Drag Empty Space To Atom

Target: empty canvas drag ending on atom.

Result:

- Creates user beam into atom.
- Opens Nudge compose dock.
- On submit: `operator_intent(kind="interject")`.

### Tap Pulse

Target: moving packet.

Result:

- Freezes pulse momentarily.
- Opens event detail for the underlying event id.

This is optional for first pass; pulse picking can wait until particles carry
event ids.

## Mobile Performance Plan

Reference device remains iPhone portrait.

Budgets:

- First scene render must not wait for GLBs.
- Flow particles target: under 250 active particles on mobile.
- Tether meshes target: one mesh per path, reused across states.
- No post-processing required for the first flow system.
- GLB scene props remain deferred and optional.

Implementation rules:

- Use object pools for particles.
- Use additive sprites for first pass, instancing later if needed.
- Avoid per-frame allocations inside animation loops.
- Avoid labels for every flow. Motion and color carry the meaning.
- Fade old flow history aggressively on mobile.

## Visual Priority Stack

When the scene gets busy, keep priority in this order:

1. Selected atom / selected path.
2. Active atom and active outgoing flow.
3. Waiting gate or error flow.
4. Operator intent pulse.
5. Cost dust.
6. Memory atmosphere.
7. Historical trails.
8. Ambient scene props.

If visual load exceeds budget, degrade from the bottom up.

## Implementation Roadmap

### Phase 1: FlowPath Foundation

Goal: make path state explicit and testable.

Tasks:

- Move `EdgeMesh` into `flows/FlowPath.ts`.
- Add `FlowKind` and `FlowMode` types.
- Replace `pulseSprites` storage with `FlowParticles`.
- Preserve current visible behavior.
- Add tests that bundle the flow modules and verify path command mapping.

Acceptance:

- Existing scene still renders.
- Build passes.
- Mobile screenshot nonblank.
- FlowPath can represent sequence, gate, loop, repair, memory, cost, and
  intent modes even if some modes share visuals initially.

### Phase 2: Event-To-Flow Director

Goal: flows respond to actual run state.

Tasks:

- Add `FlowDirector`.
- Feed recent events from `EventEngine` to `SceneManager`.
- Map atom state and loop/cost snapshots into path modes.
- Add usage/cost dust and gate charge.

Acceptance:

- Active atom has visibly active incoming/outgoing flow.
- Waiting gate visibly queues amber charge.
- Usage events create gold dust near the producing atom/path.

### Phase 3: Operator Force Gestures

Goal: human intervention becomes spatial.

Tasks:

- Add long-press intercept.
- Add ghost tether drag from atom to atom.
- Add drag empty-to-atom nudge.
- Keep compose dock as the text confirmation layer.

Acceptance:

- User can start Shape/Nudge/Intercept from spatial gestures.
- Submitted intents are visible as user-origin pulses.
- All gestures work on mobile Safari dimensions.

### Phase 4: Memory And Repair Atmosphere

Goal: context and recovery read differently from normal work.

Tasks:

- Add teal memory streams.
- Add red fracture/backflow for errors.
- Add amber repair arcs and guru escalation route.
- Add replay ghost trails for repair loops.

Acceptance:

- A blocked verify/repair cycle is understandable without opening a panel.
- Memory refresh reads as context entering the world, not as another line.

### Phase 5: Flow Inspection And Replay Polish

Goal: make flows inspectable and replayable.

Tasks:

- Add FlowPath picking.
- Add pulse/event id association.
- Tap path/pulse opens relationship/event detail.
- Scrub replay reverses/pauses particles.

Acceptance:

- Operator can answer: what moved here, when, why, and how much did it cost?
- Replay makes time direction physically visible.

### Phase 6: Content Previews And Speech Tails

Goal: generated work becomes visible in the universe.

Tasks:

- Add `ContentPreviewLayer` with world anchors and DOM pooling.
- Add far/mid/near preview LOD for artifacts and agent output.
- Add speech tails for recent agent/user messages.
- Add artifact accretion bodies for generated outputs.
- Map artifact refs and phase logs into preview summaries when available.

Acceptance:

- Operator can see who is producing content and where it will be consumed.
- Mobile shows at most one primary readable preview per focused cluster.
- Speech direction is clear without rectangular chat spam.

### Phase 7: Loop Cluster Layout And Model Actors

Goal: loops become obvious orbital systems, backed by the Ultimate Space Kit.

Tasks:

- Add `LoopClusterLayout`.
- Add `ModelCatalog` for the Ultimate Space Kit.
- Add first actor mappings:
  - astronaut for operator/review presence,
  - mech for implementation/build,
  - rover for testing/verify,
  - spaceship for deploy/ship,
  - dome/radar/antenna for gates, review, memory, and telemetry.
- Add `CharacterActor` and `AnimationDirector`.
- Keep all models deferred and LOD-gated.

Acceptance:

- A loop reads as a gravitational group of bodies, not a UI ring.
- Active engine stage has a matching actor/facility convention.
- Astronaut/mech animations respond to approve/reject/error/work states.
- iPhone portrait remains smooth with one focused animated actor.

## Required Data Additions

Nice-to-have event fields for richer flow rendering:

- `source_atom_id`
- `target_atom_id`
- `edge_id`
- `event_weight`
- `artifact_refs`
- `memory_refs`
- `cost_snapshot_ref`
- `operator_intent_id`
- `caused_by_event_id`

The renderer must work without these by inferring paths from current workflow
layout and atom id.

## Asset Usage

Current Poly Pizza assets are split into two usage tiers.

Use now:

- CC0 planets as background bodies.
- Ultimate Space Kit models as the semantic direction for the next actor and
  loop-cluster slice.
- Asteroid/probe/satellite only when attribution UI is ready, because those
  are CC-BY.

Future:

- Ultimate Space Kit actors become the primary semantic models for roles and
  loop stages.
- Planet-like props mark loop fields and cluster anchors.
- Probe/satellite can represent external tools, CI, deployment, or remote
  providers only after attribution UI exists.
- Asteroids and rocks represent blockers/errors.

Ultimate Space Kit runtime policy:

- CC0, no attribution required, but credit Quaternius in inventories.
- Keep first-frame load independent of the full kit.
- Load character actors only for focused or active clusters.
- Do not instantiate all 87 GLBs in one scene.
- Prefer semantic curation over random prop scatter.

## Testing Plan

Automated:

- Unit/bundle tests for `FlowDirector` event-to-command mapping.
- Asset manifest tests ensure GLB models remain deferred and not SW precached.
- Backend static test ensures `.glb` MIME remains `model/gltf-binary`.
- Playwright mobile smoke checks:
  - canvas nonblank
  - GLB requests succeed
  - particle system renders nonblank after events
  - no HUD overlap at iPhone viewport

Manual:

- Open live project on mobile Safari.
- Confirm active flow is readable at first glance.
- Tap atom, long-press atom, drag atom-to-atom.
- Scrub replay and confirm flow direction changes.

## Acceptance Criteria For The Flow Universe

The flow system is working when an operator can answer these questions without
opening a table:

- What is active right now?
- What is waiting?
- Where did the last failure originate?
- Is the system repairing, reviewing, building, or learning?
- Where is memory entering the run?
- Which path is expensive?
- What did my intervention change?
- What happened when I scrubbed backward?

If the map looks like a decorated flowchart, this design has failed. It should
feel like an operational universe where the user can touch the forces moving
the run.
