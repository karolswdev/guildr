# Phase 6: Web API + PWA

Put a single-user, LAN-only PWA in front of the orchestrator. FastAPI
backend + vanilla TypeScript + Service Worker frontend. Same repo.

## Dependencies

- Phases 1-5 complete.

## Scope

- FastAPI backend exposing project lifecycle + gates + event stream.
- LAN-only middleware (mandatory, see `reference/security.md`).
- PWA frontend: new project, quiz, approve gates, watch progress,
  inspect artifacts.
- Installable on iOS/Android home screen.
- `/metrics` passthrough from llama-server for observability.

## Out of scope

- Auth (single-user, LAN-only — no login).
- Push notifications (nice-to-have; deferred).
- Multiple simultaneous projects (v1: one active, others archived).

## Repo layout (addition to existing)

```
llm-projects/
├── orchestrator/           # phases 1-5
├── web/
│   ├── backend/
│   │   ├── __init__.py
│   │   ├── app.py          # FastAPI instance
│   │   ├── middleware.py   # LAN-only
│   │   ├── routes/
│   │   │   ├── projects.py
│   │   │   ├── quiz.py
│   │   │   ├── gates.py
│   │   │   └── stream.py
│   │   └── tests/
│   └── frontend/
│       ├── index.html
│       ├── manifest.json   # PWA manifest
│       ├── sw.js           # service worker
│       ├── src/
│       │   ├── app.ts
│       │   ├── api.ts
│       │   ├── views/
│       │   │   ├── NewProject.ts
│       │   │   ├── Quiz.ts
│       │   │   ├── Progress.ts
│       │   │   └── Gate.ts
│       │   └── components/
│       └── package.json    # bundler (esbuild or vite)
```

## API surface

### Projects

- `POST   /api/projects` — create. Body: `{name, initial_idea?}`.
  Returns `{id, needs_quiz: bool}`.
- `GET    /api/projects/{id}` — metadata + current phase.
- `GET    /api/projects` — list.
- `POST   /api/projects/{id}/start` — begin orchestrator run.

### Quiz

- `GET    /api/projects/{id}/quiz/next` — returns
  `{question: str} | {done: true, qwendea: str}`.
- `POST   /api/projects/{id}/quiz/answer` — body: `{answer: str}`.
  Returns same shape as `/next` after recording.
- `POST   /api/projects/{id}/quiz/edit` — body:
  `{turn: int, answer: str}`. Replaces a prior answer and truncates
  subsequent turns.
- `POST   /api/projects/{id}/quiz/commit` — body:
  `{qwendea_md: str}`. Writes `qwendea.md` (possibly user-edited) and
  returns.

### Gates

- `GET    /api/projects/{id}/gates` — list pending/decided gates.
- `GET    /api/projects/{id}/gates/{name}` — get gate + artifact.
- `POST   /api/projects/{id}/gates/{name}/decide` — body:
  `{decision: "approved"|"rejected", reason?: str}`.

### Stream

- `GET    /api/projects/{id}/stream` — Server-Sent Events of the
  orchestrator event bus. Types documented in
  `phase-5-orchestrator.md`.

### Artifacts

- `GET    /api/projects/{id}/artifacts/{name}` — fetch any of
  `qwendea.md`, `sprint-plan.md`, `TEST_REPORT.md`, `REVIEW.md`,
  `DEPLOY.md`, or a source file.
- `GET    /api/projects/{id}/tree` — project file tree.

### Observability

- `GET    /api/llama/metrics` — passthrough from llama-server
  `/metrics` (Prometheus format). PWA can render tok/s, VRAM, queue
  depth.
- `GET    /api/llama/health` — passthrough.

## LAN-only middleware

Per `reference/security.md`:

```python
# web/backend/middleware.py
import ipaddress
from fastapi import Request
from starlette.responses import JSONResponse

RFC1918 = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
]

async def lan_only(request: Request, call_next):
    if os.environ.get("ORCHESTRATOR_EXPOSE_PUBLIC") == "1":
        return await call_next(request)
    ip = ipaddress.ip_address(request.client.host)
    if not any(ip in n for n in RFC1918):
        return JSONResponse({"error": "LAN-only"}, status_code=403)
    return await call_next(request)
```

Mount **before** any route:

```python
app.middleware("http")(lan_only)
```

Log a WARNING at startup if `ORCHESTRATOR_EXPOSE_PUBLIC=1`.

## PWA frontend

### Minimal stack

- **Build**: esbuild (no framework needed for a single-user tool).
- **DOM**: vanilla TS + small component functions. No React/Vue —
  keeps the bundle tiny and the cognitive load low for opencode agents
  maintaining it.
- **Routing**: hash-based (`#/projects`, `#/project/{id}/quiz`, etc.).
- **State**: single module-level store, events via `EventTarget`.
- **PWA**:
  - `manifest.json` — installable on iOS/Android.
  - Service worker caches the app shell for offline load (API calls
    still need LAN access).

### Views

1. **New project** — name + paste `qwendea.md` OR start quiz.
2. **Quiz** — one question at a time. Previous answers editable.
   Submit final → review synthesized `qwendea.md` → commit.
3. **Progress** — phase indicator, current task, live event log,
   tok/s gauge, VRAM gauge.
4. **Gate** — full artifact (markdown rendered), Approve / Reject
   buttons, reject-reason textarea.
5. **Artifacts** — file tree + markdown/code viewer.

### Mobile-first

- Viewport meta + responsive CSS.
- Tap targets ≥ 44px.
- Gate screen especially: big Approve button, clear artifact preview.
  This is the "approve the sprint plan from the bus stop" UX.

## Tasks

### Task 1: FastAPI skeleton + LAN middleware
- **Priority**: P0
- **Files**: `web/backend/app.py`, `web/backend/middleware.py`,
  `web/backend/tests/test_middleware.py`

**Acceptance Criteria:**
- [ ] Server starts on `0.0.0.0:8000`
- [ ] Requests from `192.168.0.0/16` succeed
- [ ] Requests from `8.8.8.8` return 403
- [ ] `ORCHESTRATOR_EXPOSE_PUBLIC=1` bypasses the check
- [ ] Startup log contains WARNING when bypass enabled

**Evidence Required:**
- `pytest web/backend/tests/test_middleware.py -v`
- Manual: `curl -H "X-Forwarded-For: 8.8.8.8" ...` returns 403 when
  middleware honors X-Forwarded-For (decide via config — default OFF)

### Task 2: Project routes
- **Priority**: P0
- **Dependencies**: Task 1, Phase 5
- **Files**: `web/backend/routes/projects.py`, tests

**Acceptance Criteria:**
- [ ] Create / list / get / start endpoints return documented shapes
- [ ] Creating a project writes project dir
- [ ] `start` enqueues the orchestrator run in the background

**Evidence Required:**
- `pytest web/backend/tests/test_projects.py -v`

### Task 3: Quiz routes
- **Priority**: P0
- **Dependencies**: Task 2, Phase 2
- **Files**: `web/backend/routes/quiz.py`, tests

**Acceptance Criteria:**
- [ ] `/next` returns next seed, then adaptive, then `done:true` with
      synthesized `qwendea`
- [ ] `/edit` truncates subsequent turns correctly
- [ ] `/commit` writes `qwendea.md` to project dir

**Evidence Required:**
- Integration test: scripted answer sequence produces valid `qwendea.md`

### Task 4: Gate routes
- **Priority**: P0
- **Dependencies**: Task 2
- **Files**: `web/backend/routes/gates.py`, tests

**Acceptance Criteria:**
- [ ] List returns pending + decided gates
- [ ] Decide unblocks `Gate.wait()` in orchestrator
- [ ] Deciding an already-decided gate is idempotent (returns current)

**Evidence Required:**
- `pytest web/backend/tests/test_gates.py -v`
- Async test: open gate, call decide, orchestrator proceeds

### Task 5: SSE stream
- **Priority**: P1
- **Dependencies**: Task 2, Phase 5 EventBus
- **Files**: `web/backend/routes/stream.py`, tests

**Acceptance Criteria:**
- [ ] SSE endpoint streams orchestrator events live
- [ ] Client reconnect doesn't crash server
- [ ] Multiple subscribers all receive events

**Evidence Required:**
- `pytest web/backend/tests/test_stream.py -v`
- Manual: two `curl -N` subscribers, emit event, both receive

### Task 6: Metrics passthrough
- **Priority**: P2
- **Dependencies**: Task 1
- **Files**: `web/backend/routes/metrics.py`, tests

**Acceptance Criteria:**
- [ ] `/api/llama/metrics` returns llama-server's raw metrics
- [ ] `/api/llama/health` returns llama-server's health JSON
- [ ] Upstream errors → 502 with useful message

**Evidence Required:**
- `pytest web/backend/tests/test_metrics.py -v`

### Task 7: PWA shell + manifest + SW
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `web/frontend/index.html`, `manifest.json`, `sw.js`,
  `src/app.ts`

**Acceptance Criteria:**
- [ ] `manifest.json` has icons, name, start_url, display=standalone
- [ ] Service worker caches app shell
- [ ] Installs to home screen on iOS Safari and Android Chrome
- [ ] Offline load shows "you are offline — needs LAN" message

**Evidence Required:**
- Lighthouse PWA audit score ≥ 90
- Manual install test on a phone on the LAN

### Task 8: Views (NewProject, Quiz, Progress, Gate, Artifacts)
- **Priority**: P0
- **Dependencies**: Task 7 + backend routes
- **Files**: `web/frontend/src/views/*.ts`

**Acceptance Criteria:**
- [ ] New project view: create → quiz-or-paste flow
- [ ] Quiz view: Q&A with back-edit
- [ ] Progress view: live event log + phase indicator + metrics gauge
- [ ] Gate view: markdown artifact + approve/reject with reason
- [ ] Mobile-responsive at 375px

**Evidence Required:**
- Manual end-to-end on a phone: new project → quiz → approve
  sprint-plan → watch Coder progress
- Screenshot fixtures for regression

## Phase exit criteria

- All 8 tasks' Evidence Logs verified.
- End-to-end on LAN: phone opens `http://<host>:8000`, creates
  project, completes quiz, approves sprint-plan, watches orchestration
  complete.
- Lighthouse PWA audit passes.

## What's next

Phase 7 (`phase-7-polish.md`) — logging, `/metrics`, dry-run, docs.
