# Visual Grammar - Atoms, Memory, Agents, Gates, Artifacts, Loops, Events, Replay

## Design Language

The visual grammar is **functional minimalism with biological warmth**. Atoms are cells. Edges are axons. SDLC loops are orbiting lifecycle bands. MemPalace is a sky structure. Gates are checkpoints. Artifacts are crystallized outputs. Events are pulses of energy. The overall aesthetic: dark environment, glowing active elements, subtle particle flow - closer to Monument Valley or Reigns than to a Gantt chart.

---

## Color System

```
Background (platform)   #0D0F14   near-black with blue undertone
Grid lines              #1A1E2A   subtle hex grid
Inactive atom           #1E2235   dark blue-grey solid
Active atom             #2E4AFF   electric blue with bloom
Done atom               #1A8C5A   deep teal-green
Error atom              #CC3333   deep red
Waiting atom (gate)     #E09B2A   amber
Skipped atom            #2A2D3A   muted grey, dashed outline
Edge (inactive)         #272B3D   near-invisible
Edge (active pulse)     #4D6FFF   bright blue travelling dot
Edge (done)             #1E5C42   settled green
MemPalace arc           #5B3FBF   indigo-purple, semi-transparent
Memory orb              #9B7EFF   lavender glow
Artifact card           #2A3A2E   dark green panel
Cost ring               #D9B84D   muted gold, thin
Budget warning          #E09B2A   amber pulse
Budget exceeded         #CC3333   red pulse
Loop discover           #41C7C7   cyan arc
Loop plan               #4D6FFF   blue arc
Loop build              #E8EAF0   white arc
Loop verify             #1A8C5A   green arc
Loop repair             #E09B2A   amber arc, red on hard failure
Loop review             #7A5CFF   purple arc
Loop ship               #28B8A8   teal arc
Loop learn              #9B7EFF   lavender arc to MemPalace
Gate (waiting)          #E09B2A   amber
Gate (decided/pass)     #1A8C5A
Gate (decided/fail)     #CC3333
Event pulse             #FFD966   yellow-gold travelling particle
Text primary            #E8EAF0
Text secondary          #7A7E92
Accent / action         #4D6FFF
Danger                  #CC3333
Success                 #1A8C5A
```

---

## Atom Nodes

Each workflow step renders as an **AtomNode**: a rounded-rectangle platform (or pill shape) floating slightly above the ground plane, with a label underneath.

### Geometry
- Shape: `RoundedBoxGeometry` (width 1.6, height 0.18, depth 1.0, radius 0.12)
- Normal state: flat-shaded with slight bevel
- Active state: emissive glow (bloom pass amplifies it)
- Label: `CanvasTexture` with step title, rendered below the mesh
- Material assets: `assets/atom-meshes/flat-normal.png` for baseline normal
  data and `assets/atom-meshes/canvas-grain.png` for restrained surface grain.
  State color remains dominant; texture never reduces status readability.

### State Visuals

| State | Fill | Emissive | Outline | Animation |
|---|---|---|---|---|
| `idle` | `#1E2235` | none | none | none |
| `active` | `#2E4AFF` | `#1A2A99` (0.4) | none | slow breathing scale (+/-2%, 2.4s) |
| `done` | `#1A8C5A` | `#0A3A28` (0.2) | none | brief scale-up flash on transition |
| `error` | `#CC3333` | `#660000` (0.3) | `#FF4444` dashed | brief shake (+/-0.05 x, 200ms) |
| `waiting` | `#E09B2A` | `#7A4A00` (0.4) | none | rhythmic scale pulse (1.05x / 1s) |
| `skipped` | `#2A2D3A` | none | `#3A3D4A` dashed | none |

### Atom Type Badges

Small icon rendered in the top-left corner of each atom face (via `CanvasTexture`):

Icons come from `assets/icon-sprites/tabler-icons.woff2`. Scene code uses
semantic icon ids; glyph mappings stay centralized in the asset/icon manifest.

| Type | Icon | Color |
|---|---|---|
| `phase` | `diamond` diamond | white |
| `gate` | `hex` hexagon | amber |
| `checkpoint` | `check` checkmark | teal |
| `memory_refresh` | `cycle` cycle | lavender |
| `persona_forum` | `target` target | cyan |
| `architect` | `pentagon` blueprint | blue |
| `micro_task_breakdown` | `grid` grid | white |
| `implementation` | `play` play | blue |
| `testing` | `circle` circle-in-circle | green |
| `guru_escalation` | `up` upward arrow | gold |
| `review` | `diamond` layered diamond | purple |
| `deployment` | `upload` upload | teal |

---

## Edges (Connections Between Atoms)

Edges represent workflow order dependencies.

### Geometry
- `TubeGeometry` along a catmull-rom curve between atom center points
- Tube radius: 0.04 (inactive), 0.06 (active)
- Segments: 20 (enough for smooth curve without overdraw)

### Animation
- **Idle:** No animation. Near-invisible dark color.
- **Active path:** Travelling dot particle using `assets/edge-particle-sprites/disc.png` moves along the edge at 0.8 units/sec. Multiple particles stagger for visual flow.
- **Done path:** Edge color transitions to done-green over 600ms. Particles stop.
- **Blocked path:** Edge remains idle-dark.

### Branching
Gates with multiple outgoing edges show all branches. The taken branch animates; unchosen branches fade further.

---

## Gate Nodes

Gates are a distinct visual from phase atoms.

### Geometry
- `OctahedronGeometry` (radius 0.5) - diamond/crystal shape
- Floats 0.3 units above platform level
- Slow continuous Y-axis rotation (0.3 rad/sec)

### State Visuals

| State | Color | Effect |
|---|---|---|
| `waiting` | Amber `#E09B2A` | Rhythmic bloom pulse, amber particles orbit |
| `approved` | Teal `#1A8C5A` | Brief burst expand, then settles |
| `rejected` | Red `#CC3333` | Brief shake, red particle burst |
| `skipped` | Muted grey | No animation |

### Decision Prompt
When `waiting`, a floating text bubble above the gate shows the gate's question (truncated to 60 chars). Full text in FocusPanel.

---

## MemPalace Overlay

MemPalace is the project's memory spine. It renders as a **persistent arc structure** floating above and behind the workflow map - always visible, never occluding atoms.

### Geometry
- `TorusGeometry` (radius 8, tube 0.12, arc 180 degrees) - a half-ring arc
- Positioned at Y+4 above the map center, tilted back 20 degrees away from camera
- Semi-transparent (`opacity: 0.35`, `transparent: true`)
- Color: indigo-purple `#5B3FBF`
- Slow continuous rotation around Y axis (0.05 rad/sec)

### Status Indicators
- Three small orbs sit on the arc: **initialized**, **synced**, **wake-up active**
- Lit orbs (`#9B7EFF`) = active; dark orbs (`#2A2040`) = inactive
- Tapping the arc triggers memory search UX

### Memory Orbs (search results)
- `SphereGeometry` radius 0.12, material `#9B7EFF` with bloom
- Use `assets/mempalace/radial-alpha-gradient.png` for arc masking and
  `assets/mempalace/lensflare0.png` for restrained orb highlights.
- On search result: orbs float down from arc, orbit the relevant atom for 3s, then drift back
- Tapping an orb freezes it and opens the memory fragment in FocusPanel

---

## Artifact Cards

Artifacts are outputs produced by atoms (sprint plan, test report, review, deploy manifest).

### Geometry
- `PlaneGeometry` (1.2 x 0.7) - flat card anchored below and to the right of the producing atom
- Material: `#2A3A2E` dark green with a thin `#3A8C5A` border
- Material asset: `assets/artifact-textures/canvas-grain.png`
- Slight tilt (5 degrees toward camera)
- Artifact type icon + name rendered via `CanvasTexture`
- Tap to open full artifact text in FocusPanel

### Artifact Types and Icons

| Artifact | Icon | Color |
|---|---|---|
| `sprint-plan.md` | `clipboard` | teal |
| `phase-files/` | `grid` grid | white |
| `TEST_REPORT.md` | `circle` | green |
| `REVIEW.md` | `diamond` | purple |
| `DEPLOY.md` | `upload` | cyan |
| `PERSONA_FORUM.md` | `target` | amber |
| `FOUNDING_TEAM.json` | `targettargettarget` | gold |

---

## SDLC Loop Bands

SDLC loops render as thin orbit bands around atoms. They make lifecycle state
physically visible without adding another table.

### Geometry

- `TorusGeometry` or line-loop ring slightly larger than the atom footprint.
- Each loop stage occupies a different vertical offset around the atom base.
- Active stage band thickness: 0.035 world units.
- Inactive historical band thickness: 0.015 world units.
- Maximum visible bands per atom on iPhone: 3. Older inactive bands collapse
  into a single history tick in FocusPanel.

### Stage Visuals

| Stage | Color | Motion |
|---|---|---|
| discover | cyan `#41C7C7` | slow clockwise scan |
| plan | blue `#4D6FFF` | segmented orbit |
| build | white `#E8EAF0` | steady forward rotation |
| verify | green `#1A8C5A` | pulse when checks run |
| repair | amber `#E09B2A` | reverse arc back toward build |
| review | purple `#7A5CFF` | slow gate-like pulse |
| ship | teal `#28B8A8` | outward release pulse |
| learn | lavender `#9B7EFF` | beam toward MemPalace arc |

Repair is special: when verification fails, the verify band bends into a
repair arc and physically pulls the atom backward along the timeline before it
returns to build or verify. Guru escalation appears inside this repair arc.

### Loop Lane

The replay timeline includes a compact SDLC lane. Each bucket shows the
dominant stage color. Reopened atoms get a small amber notch. Repair cycles get
count pips, capped at 3 pips with `3+` in the FocusPanel.

---

## Cost And Budget Layer

Cost is visible but secondary. It must inform the operator without turning the
map into a finance dashboard.

### Atom Cost Rings

Atoms with recorded usage render a thin ring around their base.

- Ring thickness: 0.03 world units.
- Ring color: muted gold `#D9B84D`.
- Ring progress: proportional to phase budget consumed when a phase budget is
  configured; otherwise proportional to that atom's share of run spend.
- Provider-reported cost uses a solid ring.
- Estimated local or rate-card cost uses a dashed ring.
- Unknown cost adds a small red notch at the top of the ring.

### Budget States

| Budget State | Visual |
|---|---|
| normal | static muted-gold ring |
| warning | amber pulse every 1.5s |
| exceeded | red pulse plus budget gate marker |
| approved continuation | ring returns to amber with a small check notch |
| rejected continuation | ring stays red and atom enters blocked state |

### Cost HUD

The top HUD shows a single line on iPhone portrait (44pt bar):

  $0.42  |  $9.58 left  |  phase: $0.11  [!2]  [>]

Fields in order: run cost, budget remaining (omit if no budget), current phase
cost (omit if no phase budget), unknown-cost count badge [!N] when N > 0, and
a tap target for the economics sheet. No provider or model name in the top bar.

Detailed tables live in the economics bottom sheet, not in the HUD. See
cost-tracking.md and ux-interaction-model.md section 8 for sheet layout.

### Replay Cost Density

The replay timeline can switch from event density to cost density. Cost density
bars use muted gold for provider-reported cost, lavender for local estimates,
and red ticks for unknown cost.

Cost density bars use a square-root scale, not linear. A $0.001 call must not
be invisible next to a $1.00 call, and a $1.00 call must not dwarf everything
else. The bar height for bucket `b` is `sqrt(b.effectiveUsd) / sqrt(max_bucket_cost)`.
Label the y-axis with the max bucket cost so the operator can interpret scale.
Unknown-cost events always add a fixed-height red tick regardless of dollar
value, since their cost cannot be placed on any scale.

---

## Event Particles

Events from the SSE stream manifest as **travelling particles** in the scene.

### Particle Types

| Event Type | Particle Color | Behaviour |
|---|---|---|
| `phase_start` | `#4D6FFF` blue | Spawns at map entry, travels edge to atom |
| `phase_done` | `#1A8C5A` teal | Expands outward from atom, fades |
| `phase_error` | `#CC3333` red | Scatter-burst from atom |
| `phase_retry` | `#E09B2A` amber | Orbit around atom, re-enter |
| `gate_opened` | `#E09B2A` amber | Orbit gate crystal |
| `gate_decided` | `#1A8C5A` or `#CC3333` | Expand outward from gate |
| `run_started` | `#FFD966` gold | Cascade from top of map downward |
| `run_complete` | `#1A8C5A` teal | Full-map ring-expand |
| `run_error` | `#CC3333` red | Full-map shake + red flash |
| `memory_refresh` | `#9B7EFF` lavender | Arc-to-atom beam |
| `checkpoint` | `#FFD966` gold | Upward burst from atom |
| `loop_entered` | stage color | Ignites atom loop band |
| `loop_repaired` | amber | Reverse arc into repair band |
| `loop_completed` | stage color | Band closes and fades to history |

### Particle System Implementation
- Use `THREE.Points` with a custom `ShaderMaterial` for performance
- Maximum 500 simultaneous particles (recycle pool)
- Each particle has: position, velocity, color, lifetime, curve-follow flag
- Particle sprites come from `assets/edge-particle-sprites/disc.png` for
  steady travel and `assets/edge-particle-sprites/spark1.png` for bursts.

---

## Environment Assets

The platform ground uses `assets/environments/hex-grid.png` as a quiet
substrate. It must stay low contrast; atom, loop, memory, and cost state must
read above it at all times.

The HDRI `assets/hdris/kloppenheim-02-puresky-1k.hdr` is used for image-based
lighting after first render unless mobile profiling proves it fits the initial
payload. If HDRI loading is delayed or fails, use ambient + directional light
with the same color grammar.

`assets/post-processing-refs/lensDirt1.png` is reference-only. It must not be
loaded by Phase 1 or included in the service worker precache until a mobile
runtime derivative is produced.

---

## Replay Timeline HUD

The bottom timeline renders the event history as a **density histogram** + **state lane**.

### Structure (expanded state)

```
|||||||||||||||||||||||||||||||||||||||||||||||
| #######################################   | <- event density
| ||||||||||||||||||||||||||||||||||||||||||  | <- scrub track
|  [<<] [>/[]] |||||||*|||||||||||||||| LIVE  |
|  14:23:01                         14:31:44  |
|||||||||||||||||||||||||||||||||||||||||||||||
```

- Density bars: taller = more events per time bucket. Colored by event type mix.
- Scrubber thumb: `*` 24pt diameter, draggable
- Left side: timestamp of leftmost visible event
- Right side: `LIVE` (live mode) or timestamp (history)

### Collapsed state (56pt bar)
Shows only the scrubber track with event density as a thin gradient line. Swipe up to expand.

---

## FocusPanel

The FocusPanel is a DOM overlay (not Three.js) that slides in from the bottom (portrait) or right (landscape).

### Layout

```
||||||||||||||||||||||
| diamond architect        |  <- atom icon + name
| * ACTIVE  2m 14s   |  <- state badge + elapsed
||||||||||||||||||||||
| Last event         |
| phase_start        |  <- event type
| "Generating arch..." |  <- narrative
||||||||||||||||||||||
| Memory accesses    |
| o entities.json    |  <- memory refs, tappable
| o sprint-plan.md   |
||||||||||||||||||||||
| 1,240 tok/s  12GB  |  <- telemetry (if available)
||||||||||||||||||||||
| $0.04 provider_rep |  <- atom cost + source badge (omit if zero)
||||||||||||||||||||||
| loop: verify -> repair x2 | <- lifecycle state
||||||||||||||||||||||
| [View Logs] [JSON] |  <- action buttons
||||||||||||||||||||||
```

For gates, the approve/reject/escalate buttons replace the bottom actions and are full-width, min 56pt height.

---

## Color Usage Rules

1. **Never use more than 3 colors simultaneously on atom faces.** State color + label + badge only.
2. **Bloom is additive.** Active atoms appear brighter in dark surroundings. Do not add bloom to idle atoms.
3. **Error red is reserved for errors.** Do not use red for decorative elements.
4. **MemPalace arc must always be visible.** Never occlude it with atom layout.
5. **Particle alpha fades over lifetime.** Start at 0.9, end at 0.0. Never abrupt pop.
6. **Text on canvas is always high-contrast.** Atom labels: `#E8EAF0` on dark background. Never text on active-blue without testing contrast ratio >= 4.5:1.

## Contrast Ratio Table (WCAG AA minimum 4.5:1)

These are the safety-critical text-on-background pairs. All must pass before
shipping Phase 3. Verify with a tool such as the Colour Contrast Analyser.

| Text color    | Background         | Pair name                    | Min required |
|---------------|--------------------|------------------------------|-------------|
| `#E8EAF0`     | `#1E2235` (idle)   | atom label on idle           | 4.5:1       |
| `#E8EAF0`     | `#2E4AFF` (active) | atom label on active-blue    | 4.5:1       |
| `#E8EAF0`     | `#1A8C5A` (done)   | atom label on done-green     | 4.5:1       |
| `#E8EAF0`     | `#CC3333` (error)  | atom label on error-red      | 4.5:1       |
| `#E8EAF0`     | `#E09B2A` (waiting)| atom label on gate-amber     | 4.5:1       |
| `#E8EAF0`     | `#0D0F14` (bg)     | FocusPanel body text on bg   | 7:1         |
| `#7A7E92`     | `#0D0F14` (bg)     | secondary text on bg         | 4.5:1       |
| `#E8EAF0`     | `#2A3A2E` (artifact)| artifact label on card      | 4.5:1       |

If `#E8EAF0` on `#2E4AFF` fails 4.5:1 (active-blue is borderline), use white
`#FFFFFF` for the label text only on active atoms. Do not change the atom fill.
