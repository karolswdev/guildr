# UX Interaction Model - Mobile-First, iOS-Native Feel

## Guiding Principles

1. **Touch-first, pointer-enhanced.** Every action must be completable with one thumb. Mouse/trackpad is an enhancement, not the primary surface.
2. **Physics and spring, not linear.** Transitions use spring curves (stiffness ~300, damping ~30). Snapping feels physical, not mechanical.
3. **Progressive disclosure.** The map starts sparse. Atom detail, SDLC loop state, memory, logs, artifacts, local telemetry, and cost reveal themselves as the user zooms and taps.
4. **Operator, not spectator.** The UI never reads as a passive log viewer. Every visible element is tappable, inspectable, or actionable.
5. **Safe area awareness.** All HUD elements respect `env(safe-area-inset-*)`. Bottom bar sits above home indicator. Top elements clear the notch/Dynamic Island.

---

## Screen Layout (portrait, iPhone 14 reference)

```
||||||||||||||||||||||||||||||  <- safe area top
| [menu] Guildr  $0.42 [*LIVE] [gear] | <- top bar (44pt)
||||||||||||||||||||||||||||||
|                            |
|                            |
|      Three.js Canvas       |  <- fills remaining viewport
|      (OrchestrationMap)    |
|                            |
|                            |
||||||||||||||||||||||||||||||
|  #### #### #### #### ####  |  <- replay timeline (collapsed: 56pt)
|  [<<] [>] [[]] |||||||| o  |
||||||||||||||||||||||||||||||  <- safe area bottom
```

**Landscape:** canvas expands. Minimap moves to bottom-left. FocusPanel slides in from the right at 320pt width. ReplayTimeline stays at the bottom in landscape; its height collapses to 44pt when FocusPanel is open to avoid overlap. The minimap moves to bottom-left clear of the timeline scrubber thumb.

---

## Core Interaction Flows

### 1. Opening a Run

1. User taps project card -> router navigates to `/project/:id/run`.
2. `GameShell` mounts canvas, starts renderer.
3. `EventEngine` fetches history (`/events?limit=500`), primes `AtomStateMap`.
4. `EventEngine` folds usage events into `CostSnapshot`.
5. `EventEngine` folds loop events into `LoopSnapshot`.
6. Camera auto-frames the full workflow graph with a 400ms spring-in zoom.
7. If run is live: `EventEngine` opens SSE connection. `LIVE` indicator pulses green in top bar.
8. If run is history: `LIVE` indicator is absent. Timeline is pre-loaded. Replay controls are immediately active.

### 2. Tapping an Atom

1. Tap detected via `Raycaster` on pointer-up (< 200ms, < 8px movement = tap).
2. Camera springs to center the atom with slight zoom-in (0.6x the full-map zoom, 300ms).
3. `FocusPanel` slides up from bottom (portrait) or from right (landscape) - 320ms spring.
4. Panel shows: atom name, current state, SDLC loop stage, last event detail, token count, elapsed time, memory accesses, local inference telemetry when available, and atom cost.
5. If atom is `waiting` (gate): panel shows approve/reject/escalate buttons prominently.
6. Tap outside FocusPanel or tap same atom again -> panel dismisses with reverse spring.

**Swipe-to-dismiss:** Dragging the FocusPanel handle downward (portrait) or leftward (landscape) dismisses it. Dismiss fires when velocity > 300px/s OR displacement > 40% of panel height. Below threshold, snap back with the same spring as open (300/28). Never let the panel float at partial open - it is either fully open or fully dismissed.

**Double-tap disambiguation:** A double-tap (two taps < 300ms apart, < 8px drift) on empty canvas resets the camera (fit-all). A double-tap where the first tap hits an atom mesh fires a single atom focus instead. The fit-all gesture must never trigger when a raycaster hit returns an atom or gate on either tap.

### 3. Long-Press an Atom

During the 500ms hold, a radial arc grows clockwise around the atom perimeter
(rendered in the DOM overlay, not the Three.js scene). The arc completes at
500ms and triggers the sheet. If the pointer moves more than 8px before 500ms,
cancel the long-press and treat as a drag. This feedback is mandatory - a bare
500ms delay with no indication is invisible on iOS and will feel broken.

Long-press (500ms) opens a context sheet (iOS-style action sheet from bottom):
- **Inspect memory** - opens MemPalace search scoped to this atom's phase
- **View logs** - scrollable log panel slides over FocusPanel
- **Skip step** - only if run is paused at a gate preceding this atom
- **Re-run from here** - calls `/api/projects/{id}/control/resume` with `start_at` = this step id
- **Copy event JSON** - copies last event payload to clipboard

### 4. Replay Scrubbing

1. Swipe up on bottom bar -> timeline expands to 180pt, showing event density histogram.
2. Drag scrubber thumb left/right -> `EventEngine.scrubTo(index)` replays atom states to that point.
3. Atoms animate backward/forward through their state transitions.
4. Edges animate particle direction (forward or backward).
5. FocusPanel, if open, updates to show event at scrub position.
6. Cost HUD and economics sheet update to the selected replay point.
7. SDLC loop bands and the loop timeline lane update to the selected replay point.
8. Tap `>` to resume live following from current scrub position.
9. Tap `[]` to return to map overview.

### 5. Memory Search

1. Tap MemPalaceGroup arc (floating above map) or use `[M]` top-bar button.
2. A search input slides down from top (like iOS Spotlight).
3. User types query -> debounced POST to `/api/projects/{id}/memory/search`.
4. Results render as `MemoryOrb` nodes that float up and orbit matching atoms.
5. Tapping an orb opens the memory fragment in FocusPanel.
6. Dismiss by swiping down or tapping outside.

### 6. Injecting an Instruction

1. Tap `[+]` in CommandBar or long-press the current active atom.
2. Text field slides up with keyboard (uses `scrollIntoView` + `visualViewport` API to avoid being covered).
3. Submit sends POST to `/api/projects/{id}/control/instructions`.
4. Confirmation haptic (if available via `navigator.vibrate`) + brief green flash on the active atom.

### 7. Gate Decision

1. Gate node pulses amber with a rhythmic scale animation when in `waiting` state.
2. Tapping the gate node opens FocusPanel with the gate's question and three large tap targets: **Approve**, **Reject**, **Escalate**.
3. Buttons are min 56pt tall (Apple HIG minimum for critical actions).
4. After decision: gate node animates to `done` or `error` state, SSE continues.

### 8. Economics Sheet

1. Tap the top-bar cost badge or an atom cost ring.
2. Bottom sheet opens. The **default view is a summary card**, not a table:
   - Run total (large type), budget remaining bar, and source confidence badge.
   - Top 3 atoms by spend as a compact ranked list.
   - Any unknown-cost count shown as a warning chip.
   - A single "Breakdown" button expands to the group-by table view.
   This default view must fit in the top 40% of the sheet so the user sees it
   without scrolling. The sheet is not a finance dashboard by default.
3. Breakdown view: user can switch group by provider, model, role, phase, or atom.
   Only one group-by is active at a time. Render as a flat list, not nested tables.
4. Hosted provider-reported cost, rate-card estimate, local estimate, and
   unknown cost are visually distinct (solid gold / dashed gold / lavender / red
   chip - same encoding as the cost ring).
5. In replay mode, all values are computed from events up to the scrub index.
   The sheet header shows the replay timestamp so the operator knows what time
   the snapshot represents.
6. Budget gates appear as normal gate decisions with extra spend context.

### 9. SDLC Loop Lens

1. Tap the loop lane in the replay timeline or the loop band around an atom.
2. Bottom sheet opens with the atom's current loop stage, previous stage, next
   expected stage, repair count, artifact refs, evidence refs, and memory refs.
3. User can filter the map by discover, plan, build, verify, repair, review,
   ship, or learn. Filtering fades unrelated atoms instead of hiding them.
4. In replay mode, loop bands rewind and advance with the scrubber.
5. A failed verify loop visibly bends into repair. Returning to verify animates
   forward again so the operator can see the recovery path.

### 10. Local Provider Telemetry

1. Tap a llama.cpp-backed atom or provider badge.
2. FocusPanel shows a compact local telemetry row:
   `ctx 272 | cache 236 | prompt 32 tok/s | gen 53 tok/s`.
3. If `/metrics` or `/slots` are disabled, show `metrics off` only in detail
   view. Do not show an error badge when response timings are still available.
4. Local telemetry is visualized as context pressure and throughput, separate
   from dollar cost.

---

## Gesture Reference Table

| Gesture | Target | Action |
|---|---|---|
| Single tap | Atom / Gate | Focus + open FocusPanel |
| Double tap | Canvas (empty) | Reset camera to fit-all |
| Long press | Atom | Context action sheet |
| Pinch | Canvas | Zoom in/out |
| One-finger drag | Canvas | Pan camera |
| Swipe up | Bottom bar | Expand replay timeline |
| Swipe down | FocusPanel | Dismiss panel |
| Drag | Timeline scrubber | Replay scrub |
| Tap | MemPalace arc | Open memory search |
| Tap | Cost badge / cost ring | Open economics sheet |
| Tap | Loop band / loop lane | Open SDLC loop lens |
| Tap | Local provider badge | Open local telemetry detail |
| Two-finger swipe | Timeline (expanded) | Fast scrub |

---

## Motion Design Specs

All animations use spring physics. Suggested values (adjust to taste):

| Interaction | Duration | Spring (stiffness/damping) |
|---|---|---|
| Panel slide-in | - | 300 / 28 |
| Camera focus zoom | - | 250 / 30 |
| Atom state change | - | 400 / 35 |
| Timeline expand | - | 350 / 32 |
| Memory orb float-in | - | 200 / 20 |
| Gate pulse (loop) | 1.4s | n/a (CSS keyframe) |

Never use `ease-in-out` cubic bezier for interactive elements. Reserve it only for loading transitions where physics feels wrong.

---

## Haptic Feedback

Use `navigator.vibrate()` where available (Android). On iOS, haptics are not available in PWA; rely on visual feedback instead. Do not require haptics for any critical state communication.

| Event | Haptic pattern |
|---|---|
| Atom completes | `[10]` (short pulse) |
| Gate opens | `[30, 50, 30]` (double tap) |
| Error | `[100]` (single firm) |
| Instruction injected | `[10]` (short) |

---

## Typography and Text

- Use `system-ui, -apple-system, BlinkMacSystemFont, sans-serif` stack - renders as SF Pro on iOS.
- Minimum body font: 15px. Labels on atoms: 11px bold, uppercase.
- FocusPanel text: 15px regular for content, 13px for metadata.
- Never render text directly in Three.js for primary UI. Use DOM overlay for all readable text. Three.js canvas text (via `CanvasTexture`) only for atom labels that must stay world-anchored.

---

## Offline and Loading States

- Service Worker pre-caches app shell. Canvas loads instantly.
- On offline: `EventEngine` shows last known state from `localStorage` cache. `OFFLINE` badge replaces `LIVE` indicator.
- Skeleton state: atoms render as dim grey nodes before history loads. Fade to their real state over 300ms when data arrives.
- SSE reconnect: silent auto-retry (3s backoff). `RECONNECTING...` replaces `LIVE` only after 5s.
