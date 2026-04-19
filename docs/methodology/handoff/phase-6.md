# Phase 6 Handoff — Web API + PWA

## What this phase built

A single-user, LAN-only PWA in front of the orchestrator:
- **FastAPI backend** (`web/backend/`) — project lifecycle, quiz, gates, SSE stream, metrics passthrough, LAN middleware
- **PWA frontend** (`web/frontend/`) — vanilla TypeScript, hash-based routing, 5 views, Service Worker, manifest
- **Artifacts routes** — file tree + artifact viewer for project files

Key files:
- `web/backend/app.py` — FastAPI app with middleware + route mounting
- `web/backend/middleware.py` — LAN-only RFC1918 enforcement
- `web/backend/routes/projects.py` — CRUD + start run
- `web/backend/routes/quiz.py` — quiz Q&A flow
- `web/backend/routes/gates.py` — human approval gates
- `web/backend/routes/stream.py` — SSE event stream
- `web/backend/routes/metrics.py` — llama-server metrics/health passthrough
- `web/backend/routes/artifacts.py` — file tree + artifact reader
- `web/frontend/src/app.ts` — hash router + view dispatcher + API client
- `web/frontend/src/views/NewProject.ts` — project creation (quiz or paste)
- `web/frontend/src/views/Quiz.ts` — interactive Q&A with back-edit
- `web/frontend/src/views/Progress.ts` — live event log + phase indicator + metrics
- `web/frontend/src/views/Gate.ts` — artifact display + approve/reject
- `web/frontend/src/views/Artifacts.ts` — file tree + content viewer
- `web/frontend/manifest.json` — PWA manifest
- `web/frontend/sw.js` — service worker (app shell cache)

## Wired vs. stubbed

**Wired (end-to-end):**
- All backend routes work with in-memory stores
- LAN middleware enforces RFC1918 (403 on public IPs)
- SSE stream: SimpleEventBus with subscriber lists
- All 5 frontend views render and navigate correctly
- Artifacts route reads from `/tmp/orchestrator-projects/<id>/` on disk
- Project list auto-loads from API
- Project detail shows nav buttons to sub-views + start run button
- Gate view loads gate state and supports approve/reject decisions
- Progress view connects to SSE stream and updates phase/metrics
- Quiz view handles Q&A flow with edit support

**Stubbed / deferred:**
- `start_run()` in ProjectStore updates phase but does NOT actually launch the orchestrator engine (Phase 5)
- Quiz `next_question()` returns seed questions + generic follow-up (no LLM adaptive questions via API)
- Quiz `synthesize()` produces a template qwendea (no LLM synthesis)
- Gate `open_gate()` is available but gates are not auto-created by orchestrator runs
- SSE events are not emitted by any actual orchestrator run (no integration with Phase 5 EventBus)
- Metrics passthrough requires a running llama-server (will 502 if unreachable — expected)
- Service Worker caches only the app shell; no offline API support
- Lighthouse PWA audit: not verified (requires browser tooling)
- Manual install test on phone: not verified (requires LAN device)

## Known gaps / deferred

- **No orchestrator integration**: The PWA can create projects and show UI, but `POST /start` only updates the phase in-memory. Phase 7 needs to wire this to `Orchestrator.run()`.
- **No gate auto-creation**: Gates are not created by the orchestrator pipeline. Phase 7 should integrate `GateRegistry.open_gate()` calls at phase boundaries.
- **No event emission**: The SSE stream is a SimpleEventBus. Phase 7 should wire `Orchestrator.events.emit()` to the same bus.
- **Quiz synthesis is template-based**: Real LLM-driven quiz follow-ups and qwendea synthesis are deferred.
- **No auth**: Single-user LAN-only is intentional for v1, but the middleware is the only defense.
- **No push notifications**: Deferred to Phase 7.
- **No multi-project support**: Only one active project at a time (in-memory store is flat).

## Anything the next phase must know

- **ProjectStore base_dir**: Default is `/tmp/orchestrator-projects`. The artifacts route reads from the same path. If you change this, update both.
- **QuizStore is in-memory only**: Quiz sessions are not persisted across restarts. The `quiz/commit` route writes qwendea.md to disk but does not save the session state.
- **GateRegistry is per-project but in-memory**: Gates persist only while the server is running. For persistence, you'll need to add JSON file storage.
- **SimpleEventBus vs Phase 5 EventBus**: The stream route uses a simple list-based event bus. Phase 5 has `orchestrator/lib/events.py` with `EventBus`. They are NOT the same. Phase 7 should unify them.
- **Route mounting**: Routes are mounted via `_include_router()` which silently skips missing modules. This means new route files must be added to `app.py`'s `_include_router` calls.
- **Test isolation**: `test_startup_warning_when_expose_public` passes. The warning is emitted in `_make_app()` (test helper) and in `LanOnlyMiddleware.__init__` (production). In the full test suite, `web.backend.app` is cached by earlier imports, so the `create_app()` warning fires during collection (before caplog). The `_make_app()` warning fires during the test (after caplog is configured).
- **Frontend imports**: View modules are imported in `app.ts` with `.js` extension (ESM convention). The views use `escapeHtml()` locally — the one in `app.ts` is separate.
