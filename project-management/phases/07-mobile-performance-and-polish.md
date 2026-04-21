# Phase 7 - Mobile Performance And Polish

## Goal

Make the zero-g universe feel intentional, readable, and fast on mobile Safari.
This phase turns prototypes into a product surface.

## Required Context

- `docs/spatial-flow-universe-design.md`
- `docs/threejs-asset-pipeline.md`
- `assets/README.md`
- `web/frontend/src/game/GameShell.ts`
- `web/frontend/src/game/SceneManager.ts`
- `web/frontend/src/game/assets/AssetManager.ts`

## Implementation Surface

- Camera behavior.
- LOD rules.
- Asset load policy.
- HUD/overlay collision rules.
- Playwright/mobile smoke tests.

## Task 7.1 - Galaxy, Cluster, Surface Camera Modes

Status: Not started

Actions:

- Add camera modes:
  - galaxy view,
  - cluster focus,
  - selected surface/preview focus.
- Mobile defaults to cluster focus.
- Swipe/cycle moves between clusters.
- Pinch zooms out/in without free 6DOF disorientation.

Acceptance:

- User does not get lost on iPhone portrait.
- Active cluster remains framed while controls are open.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Task 7.2 - Mobile LOD And Animation Budget

Status: Not started

Actions:

- Enforce mobile budgets:
  - under 250 active particles,
  - one primary animated actor,
  - one secondary actor at reduced update frequency,
  - collapsed motes for low-priority bodies,
  - no full-kit GLB load.
- Add debug counters behind a non-production flag.

Acceptance:

- Scene remains smooth during pan/pinch.
- Visual priority degrades from ambient props upward, never from active target
  downward.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Task 7.3 - Overlay Collision And Text Fit

Status: Not started

Actions:

- Add collision/priority rules for:
  - atom labels,
  - content previews,
  - speech tails,
  - bottom now strip,
  - compose dock.
- Ensure text never overlaps incoherently or escapes controls.

Acceptance:

- iPhone portrait screenshot has no text overlap.
- Long labels collapse or truncate cleanly.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Task 7.4 - Visual Direction Pass

Status: Not started

Actions:

- Review the whole scene against the design principles:
  - zero-g universe,
  - model-backed orchestration semantics,
  - no dashboard takeover,
  - no hex/lattice return,
  - no random prop scatter.
- Tune lighting, scale, color, and motion until engine state reads first.

Acceptance:

- A first-time user can identify active work, blocked work, and next transfer
  from the scene before opening details.

Evidence:

```bash
./web/frontend/build.sh
```

Add current screenshots to `docs/screenshots/` only if they are useful for
handoff; otherwise record `/tmp/...` screenshot paths in `STATUS.md`.

## Phase Exit Criteria

- Mobile camera modes work.
- LOD budgets are enforced.
- Overlay text remains readable.
- Visual design matches the orchestration model.
