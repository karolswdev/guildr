# Phase 8 - Release Hardening

## Goal

Prepare the zero-g orchestration PWA for real users: reliable setup, stable
runtime behavior, clear fallback paths, and complete documentation.

## Required Context

- `docs/getting-started.md`
- `docs/srs-council-engine.md`
- `project-management/STATUS.md`
- `project-management/AGENT_ONBOARDING.md`
- backend and frontend test suites

## Implementation Surface

- End-to-end tests.
- PWA service worker.
- Static asset policy.
- Error/fallback UX.
- User and developer docs.

## Task 8.1 - End-To-End Run Replay Fixture

Status: Not started

Actions:

- Add or update a fixture run that includes:
  - memory refresh,
  - persona forum,
  - plan,
  - build,
  - verify failure,
  - repair,
  - review gate,
  - usage/cost,
  - operator intent,
  - ship.
- Verify EventEngine folds it and map route can render it.

Acceptance:

- Replay fixture proves the core product story.
- Scrubbing backward changes flow direction/time state.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py
```

## Task 8.2 - WebGL And Asset Fallbacks

Status: Not started

Actions:

- Ensure WebGL failure shows usable fallback.
- Ensure missing optional GLBs do not break the map.
- Ensure service worker updates do not trap stale asset versions.

Acceptance:

- `?fallback=1` remains usable.
- Missing deferred model logs a warning and renders placeholder/silhouette.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_pwa.py web/backend/tests/test_pwa_serving.py
./web/frontend/build.sh
```

## Task 8.3 - User-Facing Getting Started

Status: Not started

Actions:

- Update docs with:
  - how to start the backend,
  - how to open the PWA map,
  - how to expose on `0.0.0.0` for mobile Safari,
  - how to clear service worker/cache if stale,
  - what Shape/Nudge/Intercept do.

Acceptance:

- A new user can run the app and open the map without reading chat history.

Evidence:

```bash
git diff --check
```

## Task 8.4 - Release Gate

Status: Not started

Actions:

- Run full relevant verification:

```bash
uv run pytest -q tests web/backend/tests web/frontend/tests
./web/frontend/build.sh
git diff --check
rg -n "Authorization|api_key|OPENROUTER_API_KEY" .orchestrator 2>/dev/null || true
```

- Record results in `project-management/STATUS.md`.
- Capture mobile Safari smoke result.

Acceptance:

- No known critical regressions.
- Remaining risks are documented.

## Phase Exit Criteria

- End-to-end replay story is tested.
- Fallbacks work.
- Setup and mobile usage docs are current.
- Release gate evidence is recorded.
