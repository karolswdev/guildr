# Phase 2 - Orbital Loop Layout

## Goal

Make loops visually obvious as gravitational groups of objects orbiting shared
barycenters, with stable logical placement and mobile level of detail.

## Required Context

- `docs/spatial-flow-universe-design.md`
- `orchestrator/lib/loops.py`
- `web/frontend/src/game/layout.ts`
- `web/frontend/src/game/SceneManager.ts`
- `web/frontend/src/game/EventEngine.ts`

## Implementation Surface

- `web/frontend/src/game/layout/LoopClusterLayout.ts`
- `web/frontend/src/game/layout.ts`
- `web/frontend/src/game/SceneManager.ts`
- frontend layout tests

## Task 2.1 - Define LoopClusterLayout Data Model

Status: Not started

Actions:

- Add `LoopCluster`, `ClusterMember`, and orbital parameter types.
- Include:
  - `cluster_id`
  - `loop_stage`
  - `barycenter`
  - `orbit_radius`
  - `orbit_inclination`
  - `orbit_phase`
  - `orbit_speed`
  - `importance`
  - `collapsed`
- Map engine stages:
  - `learn`, `discover`, `plan`, `build`, `verify`, `repair`, `review`,
    `ship`.

Acceptance:

- Layout output is deterministic for the same workflow/event snapshot.
- No Three.js dependency in the pure layout module.

Evidence:

```bash
./web/frontend/build.sh
```

## Task 2.2 - Replace Static Loop Centers With Cluster Placement

Status: Not started

Actions:

- Update current layout to place loop clusters by logical stage:
  - memory/learn rear-left or upper,
  - discover/plan upper-left,
  - build center,
  - verify/review upper-right,
  - repair return arc lower-center,
  - ship lower-right/outward.
- Preserve stable camera fit and bounding sphere.
- Avoid all-to-all edges; use transfer corridors between clusters.

Acceptance:

- A normal run reads as memory -> plan -> build -> verify/review -> ship, with
  repair bending back toward build.
- Cluster membership is legible without relying only on labels.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Task 2.3 - Add Orbital Motion And Trail Language

Status: Not started

Actions:

- Animate members around barycenters using deterministic phase/speed.
- Add faint history trails for repeated loop iterations.
- Slow bodies near waiting gates.
- Show repair as return arc and learn as slow memory arc.
- Collapse minor bodies into motes on mobile galaxy view.

Acceptance:

- A loop looks like a physical grouping of orbiting bodies.
- Iterations leave visible history without hard rings.
- Mobile view shows only dominant bodies plus motes.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Task 2.4 - Add Loop Selection

Status: Not started

Actions:

- Make a loop cluster selectable as a first-class target.
- Tapping a loop field focuses camera on that cluster.
- Selected cluster exposes current stage, active members, recent iterations,
  and next transfer target.
- Keep controls spatial and compact on mobile.

Acceptance:

- User can tap a loop group and understand its current lifecycle state.
- Selection does not open a bulky dashboard panel.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Phase Exit Criteria

- Loops are cluster systems with barycenters and orbital motion.
- Logical engine stages have stable spatial placement.
- Mobile galaxy/cluster LOD exists.
- Loop selection is implemented.
