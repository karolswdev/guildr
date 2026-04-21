# UX Interaction Model - Mobile-First, iOS-Native Feel

## Guiding Principles

1. **Touch-first, pointer-enhanced.** Every action must be completable with one thumb. Mouse/trackpad is an enhancement, not the primary surface.
2. **Physics and spring, not linear.** Transitions use spring curves (stiffness ~300, damping ~30). Snapping feels physical, not mechanical.
3. **Progressive disclosure.** The map starts sparse. Atom detail, memory, logs, and artifacts reveal themselves as the user zooms and taps.
4. **Operator, not spectator.** The UI never reads as a passive log viewer. Every visible element is tappable, inspectable, or actionable.
5. **Safe area awareness.** All HUD elements respect `env(safe-area-inset-*)`. Bottom bar sits above home indicator. Top elements clear the notch/Dynamic Island.

---

## Screen Layout (portrait, iPhone 14 reference)

```
||||||||||||||||||||||||||||||  <- safe area top
|  [menu] Guildr    [*LIVE] [gear] |  <- top bar (44pt)
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

**Landscape:** canvas expands. Minimap moves to bottom-left. FocusPanel slides in from the right at 320pt width.

---

## Core Interaction Flows

### 1. Opening a Run

1. User taps project card -> router navigates to `/project/:id/run`.
2. `GameShell` mounts canvas, starts renderer.
3. `EventEngine` fetches history (`/events?limit=500`), primes `AtomStateMap`.
4. Camera auto-frames the full workflow graph with a 400ms spring-in zoom.
5. If run is live: `EventEngine` opens SSE connection. `LIVE` indicator pulses green in top bar.
6. If run is history: `LIVE` indicator is absent. Timeline is pre-loaded. Replay controls are immediately active.

### 2. Tapping an Atom

1. Tap detected via `Raycaster` on pointer-up (< 200ms, < 8px movement = tap).
2. Camera springs to center the atom with slight zoom-in (0.6x the full-map zoom, 300ms).
3. `FocusPanel` slides up from bottom (portrait) or from right (landscape) - 320ms spring.
4. Panel shows: atom name, current state, last event detail, token count, elapsed time, memory accesses.
5. If atom is `waiting` (gate): panel shows approve/reject/escalate buttons prominently.
6. Tap outside FocusPanel or tap same atom again -> panel dismisses with reverse spring.

### 3. Long-Press an Atom

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
6. Tap `>` to resume live following from current scrub position.
7. Tap `[]` to return to map overview.

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
