# Agent Onboarding

This is the minimum context for a fresh agent continuing the zero-g PWA work.

## First 10 Minutes

1. Read `project-management/STATUS.md`.
2. Read `project-management/DIRECTION_GUARDRAILS.md`.
3. Read the phase file for the next unfinished task.
4. Read only the context files named by that task.
5. Run a narrow status check:

```bash
git status --short
```

5. Do not revert unrelated changes.

## Current Architecture Shape

Backend:

- Durable events are the product spine.
- `/api/projects/{project_id}/events` and SSE feed history/live updates.
- `/api/projects/{project_id}/intents` records `operator_intent` events.
- Gates and budget events are persisted and folded by replay.

Frontend:

- `web/frontend/src/game/EventEngine.ts` folds events into snapshots.
- `web/frontend/src/game/GameShell.ts` owns the map route UI shell.
- `web/frontend/src/game/SceneManager.ts` owns the Three.js scene.
- `web/frontend/src/game/layout.ts` currently provides zero-g graph layout.
- `web/frontend/src/game/atoms/EdgeMesh.ts` owns curved tethers.
- `web/frontend/src/game/assets/AssetManager.ts` loads local assets.

Assets:

- `assets/poly-pizza/` is served by the backend at `/assets/poly-pizza/...`.
- `assets/poly-pizza/ultimate-space-kit/` is the CC0 semantic model pack.
- Models are deferred; never service-worker-precache the whole kit.

## Core Invariants

- Replay state must come from folding events, not mutable UI-only state.
- Events must carry stable identity fields: `event_id`, `schema_version`,
  `run_id`, `ts`, and `type` where applicable.
- Runtime assets must be vendored. No hotlinks.
- Mobile Safari portrait is the baseline interaction target.
- The map is a zero-g operational universe, not a dashboard, hex board, or
  marketing page.

## Required Verification Before Handoff

Run the narrow tests for the files you touched. At minimum:

```bash
git diff --check
./web/frontend/build.sh
```

When backend/event behavior changes:

```bash
uv run pytest -q web/backend/tests tests
```

When frontend game behavior changes:

```bash
uv run pytest -q web/frontend/tests
```

When assets change:

```bash
jq empty assets/poly-pizza/ultimate-space-kit/manifest.json
```

## Handoff Format

Update `project-management/STATUS.md` with:

- phase and task touched,
- files changed,
- verification run,
- screenshots or LAN URL if relevant,
- known risks or skipped tests.

Then update `docs/AGENT_IN_PROGRESS_MEMORY_DUMP.md` only for durable context
that future agents need outside this project-management pack.
