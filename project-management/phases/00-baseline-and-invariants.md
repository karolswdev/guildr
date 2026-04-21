# Phase 0 - Baseline And Invariants

## Goal

Lock the current working baseline so future agents can safely iterate on the
zero-g map without guessing what "working" means.

## Required Context

- `project-management/STATUS.md`
- `docs/AGENT_IN_PROGRESS_MEMORY_DUMP.md`
- `docs/spatial-flow-universe-design.md`
- `assets/README.md`
- `assets/poly-pizza/ultimate-space-kit/README.md`

## Implementation Surface

- Test and smoke scripts.
- Project-management status evidence.
- Asset-serving and manifest tests.
- Existing map route only if a smoke hook is missing.

## Task 0.1 - Capture Current Verification Commands

Status: Not started

Actions:

- Identify the narrowest current build/test commands for:
  - backend event/static asset serving,
  - frontend game asset manager,
  - frontend map route,
  - full frontend build.
- Add them to `project-management/STATUS.md` under an explicit "Current
  Verification Commands" section.
- Do not change product code unless a listed command is stale.

Acceptance:

- A fresh agent can copy/paste verification commands from `STATUS.md`.
- Commands are scoped and do not require a full test suite for every UI edit.

Evidence:

```bash
git diff --check
```

## Task 0.2 - Add Ultimate Space Kit Asset Tests

Status: Not started

Actions:

- Extend existing frontend/backend asset tests or add a small focused test.
- Assert `assets/poly-pizza/ultimate-space-kit/manifest.json` is valid.
- Assert representative GLB paths are served with `model/gltf-binary`.
- Assert Ultimate Space Kit models are not service-worker precached.

Candidate files:

- `web/backend/tests/test_pwa_serving.py`
- `web/frontend/tests/test_asset_manager.py`
- `web/frontend/src/game/assets/manifest.ts`

Acceptance:

- Test fails if a runtime model path is missing or served with wrong MIME.
- Test fails if a heavy Ultimate Space Kit model is added to core/precache.

Evidence:

```bash
uv run pytest -q web/backend/tests/test_pwa_serving.py web/frontend/tests/test_asset_manager.py
```

## Task 0.3 - Stabilize Mobile Smoke Procedure

Status: Not started

Actions:

- Document how to start the dev server on `0.0.0.0`.
- Document the LAN URL pattern for mobile Safari.
- Add a repeatable Playwright or manual smoke checklist:
  - map route loads,
  - canvas is nonblank,
  - touch pan/pinch works,
  - radial action ring opens,
  - GLB requests return 200,
  - no HUD overlap on iPhone portrait.

Candidate files:

- `project-management/STATUS.md`
- `project-management/AGENT_ONBOARDING.md`
- optionally `web/frontend/tests/test_game_map.py`

Acceptance:

- Future agents can verify mobile regressions without asking for tribal
  knowledge.

Evidence:

```bash
./web/frontend/build.sh
uv run pytest -q web/frontend/tests/test_game_map.py
```

## Phase Exit Criteria

- Current verification commands are documented.
- Ultimate Space Kit asset serving/precache behavior is guarded.
- Mobile smoke procedure is documented.
- `project-management/STATUS.md` is updated with evidence.
