# Demo Ceremony And Replay Evidence

Last updated: 2026-04-22

## Purpose

The orchestrator should not only build software and log events. When the work
is visually or interactively demoable, the run should produce a durable "show
the work" artifact tied to the same evidence that proves the task. For web apps
and PWAs, that means a Playwright acceptance/demo spec first, then a GIF, video,
trace, screenshot, or compact replay card captured from that spec run. This
makes the system more useful as an engineering tool and more enjoyable to watch
as a PWA experience.

The demo ceremony becomes part of the mini-sprint record:

- the team decides whether a task is demoable,
- a deterministic scenario is run by the right demo adapter,
- visual proof is captured from that scenario,
- the proof is linked into the event ledger,
- the PWA can replay or open the demo later.

Replay still does not time-travel the filesystem. It shows recorded demo
artifacts and the event context that produced them.

## Product Thesis

Every successful mini-sprint should answer three questions:

1. What changed?
2. How was it verified?
3. Can I see it working?

For backend-only work, the answer may be tests and logs. For web apps, games,
visual tools, dashboards, editors, maps, or UI-affecting tasks, the answer
should include a demo artifact whenever practical.

For web apps specifically, the gold path is not a free-floating screenshot. It
is a Playwright test that asserts the acceptance criteria and also produces
ceremony media. The test result decides pass/fail. The captured GIF/video makes
the proof legible and replayable.

## Demoable Work Detection

The first implementation should be conservative. Detection should return a demo
adapter plan, not just a boolean. A task is demoable when one of these is true:

- the sprint-plan task explicitly asks for a demo, screenshot, visual proof,
  Playwright check, or browser validation;
- acceptance criteria mention UI, page, route, app, canvas, form, game, map,
  dashboard, visual state, or mobile viewport;
- evidence required includes Playwright, screenshot, video, browser, or PWA;
- changed files include frontend surfaces and a known route can be started;
- the operator submits an intent requesting a demo.

If confidence is low, emit `demo_skipped` with a reason instead of forcing a
fragile ceremony.

Recommended confidence values:

- `explicit_playwright`: acceptance criteria or evidence required includes a
  Playwright spec, browser test, route check, or demo capture.
- `inferred_interactive_web`: frontend/web files plus runnable route are
  detected and acceptance criteria mention visible behavior.
- `static_visual`: a static page or artifact can be rendered, but no meaningful
  interaction is known yet.
- `operator_requested`: operator intent asked for it.
- `not_demoable`: no useful visual surface found.

## Demo Adapters

A demo adapter owns framework-specific qualification and capture. The adapter
plan should be recorded before capture so operators and replay can understand
why a demo did or did not happen.

Adapter plan fields:

- `adapter`: stable id such as `playwright_web`.
- `confidence`: one of the confidence values above.
- `start_command`: command used to serve the app, if needed.
- `test_command`: command used to run the acceptance/demo spec.
- `spec_path`: Playwright or framework test file used for the demo.
- `route`: route under test.
- `viewports`: requested viewport names/sizes.
- `capture_policy`: `gif`, `webm`, `trace`, `screenshot`, or combinations.
- `skip_reason`: source-backed reason when the adapter declines.

### `playwright_web`

This is the default adapter for web apps and PWAs.

It qualifies when:

- acceptance criteria or evidence mention Playwright, browser checks, routes,
  screenshots, videos, GIFs, canvas, mobile layout, forms, or UI behavior;
- the repo contains a Playwright config or web test directory;
- frontend files changed and a known app start command can be resolved;
- the operator explicitly requests an interactive web demo.

It should prefer this evidence chain:

1. Run or create a deterministic Playwright spec that asserts the acceptance
   criteria.
2. Capture Playwright video, trace, and screenshots from that same spec run.
3. Derive `demo.gif` from the captured video when size and tooling allow.
4. Emit the demo as passed only when the Playwright spec passed. If it fails,
   keep failure media as `demo_capture_failed` evidence.

The adapter must not capture a separate happy path that was not asserted by the
test. If a demo spec does not yet exist, the orchestrator can propose or create
one as part of the task, but the capture still runs through that spec.

Future adapters can be added without changing the ceremony contract:

- `storybook_web`: component-state demos from Storybook stories.
- `cli_snapshot`: terminal output or TUI transcript capture.
- `api_contract`: request/response transcript plus contract test evidence.
- `game_canvas`: canvas/WebGL frame and interaction capture, usually still via
  Playwright for browser games.
- `desktop_app`: platform-specific screen capture around an app smoke test.

## Ceremony Flow

1. **Plan**
   - Parse acceptance criteria and evidence requirements.
   - Select a demo adapter and decide whether a demo is required, suggested, or
     skipped.
   - Emit `demo_planned`.

2. **Prepare**
   - Resolve start command, static HTML target, or framework-native runner.
   - For web/PWA work, resolve the Playwright config and demo spec.
   - Start or reuse a dev server when needed.
   - Decide viewport(s): desktop, mobile, or both.
   - Emit `demo_capture_started`.

3. **Capture**
   - Invoke the selected adapter.
   - For `playwright_web`, run the Playwright spec and capture media from that
     same run.
   - Prefer `demo.gif` or `interaction.webm` for interactive web work; keep
     screenshots as fallback/static evidence.
   - Store artifacts under `.orchestrator/demos/<demo_id>/`.
   - Emit `demo_artifact_created`.

4. **Present**
   - Add a compact demo card to the narrative/story surface.
   - Link source events, task id, acceptance criteria, route, viewport, and
     artifacts.
   - Emit `demo_presented`.

5. **Replay**
   - Replay fold shows the demo card at the event index where it was created.
   - Opening the card shows recorded artifacts, not current live state.

## Event Contract

The events should be durable and replayable.

```json
{
  "type": "demo_planned",
  "demo_id": "demo_evt_123",
  "project_id": "project-1",
  "atom_id": "implementation",
  "task_id": "task-001",
  "adapter": "playwright_web",
  "confidence": "explicit_playwright",
  "reason": "acceptance criteria requested a Playwright-backed mobile demo",
  "start_command": "npm run dev -- --host 127.0.0.1",
  "test_command": "npx playwright test tests/demo/game-map.spec.ts --project=chromium",
  "spec_path": "tests/demo/game-map.spec.ts",
  "route": "/game",
  "capture_policy": ["gif", "webm", "trace", "screenshot"],
  "source_refs": ["event:evt_123", "artifact:sprint-plan.md"],
  "artifact_refs": []
}
```

```json
{
  "type": "demo_artifact_created",
  "demo_id": "demo_evt_123",
  "project_id": "project-1",
  "atom_id": "implementation",
  "task_id": "task-001",
  "adapter": "playwright_web",
  "test_command": "npx playwright test tests/demo/game-map.spec.ts --project=chromium",
  "spec_path": "tests/demo/game-map.spec.ts",
  "test_status": "passed",
  "route": "http://127.0.0.1:5173/game",
  "viewport": {"width": 393, "height": 852, "name": "mobile"},
  "artifact_refs": [
    ".orchestrator/demos/demo_evt_123/demo.gif",
    ".orchestrator/demos/demo_evt_123/interaction.webm",
    ".orchestrator/demos/demo_evt_123/mobile.png",
    ".orchestrator/demos/demo_evt_123/trace.zip"
  ],
  "source_refs": ["event:evt_123", "artifact:sprint-plan.md"],
  "memory_refs": [".orchestrator/memory/wake-up.md"],
  "wake_up_hash": "sha256..."
}
```

```json
{
  "type": "demo_skipped",
  "demo_id": "demo_evt_123",
  "project_id": "project-1",
  "atom_id": "review",
  "adapter": "playwright_web",
  "confidence": "not_demoable",
  "reason": "no runnable visual surface detected",
  "source_refs": ["event:evt_123"]
}
```

## Artifact Layout

Store demo artifacts in project-local orchestrator state:

```text
.orchestrator/
  demos/
    demo_evt_123/
      metadata.json
      demo.gif
      interaction.webm
      desktop.png
      mobile.png
      trace.zip
      playwright-report/
      summary.md
```

`metadata.json` should include:

- demo id,
- run id / project id,
- task id / atom id,
- trigger event id,
- adapter id,
- capture command,
- start command,
- test command,
- spec path,
- test status,
- route,
- viewport,
- source refs,
- artifact hashes,
- memory provenance.

The PWA should fetch demo artifacts through a bounded backend artifact route,
not by reading arbitrary filesystem paths.

## Acceptance Criteria Integration

Sprint-plan tasks can request demos explicitly:

```markdown
**Acceptance Criteria:**
- [ ] The map opens on mobile without HUD overlap.
- [ ] Demo: run the Playwright map spec and capture the mobile interaction as a GIF.

**Evidence Required:**
- Run `npx playwright test web/frontend/tests/demo/game-map.spec.ts --project=chromium`
- Run `./web/frontend/build.sh`
- Store `demo.gif`, `interaction.webm`, `trace.zip`, and viewport screenshots
  from that Playwright run.
```

Later, this can become structured metadata:

```yaml
demo:
  required: true
  adapter: playwright_web
  spec: web/frontend/tests/demo/game-map.spec.ts
  route: /game
  viewports: [mobile, desktop]
  capture: [gif, webm, trace, screenshot]
  interactions:
    - tap: "[data-role='next-step-control']"
    - screenshot: next-step-sheet
```

Do not require structured metadata for v1. Inference from text is enough.

## PWA Presentation

The demo should feel like a ceremony, not an attachment list.

Map surface:

- Demo card appears near the atom that produced it.
- Story Lens shows a "Demo" section with thumbnail, viewport badges, and source
  chips.
- Object Lens for the task shows "Proof: tests, review, demo".
- Replay timeline marks demo events with a recognizable symbol.

Demo detail:

- thumbnail or video,
- acceptance criteria it proves,
- route and viewport,
- event/source refs,
- artifact hashes,
- memory provenance,
- "open artifact" and "replay interaction" controls when available.

## Guardrails

- Demo capture is visual evidence, not a replacement for assertions. Tests
  still decide pass/fail.
- For web/PWA demos, do not capture a path that is not exercised by the
  Playwright acceptance/demo spec.
- Never block non-visual backend work on a visual demo.
- Skip with a durable reason when no route or server can be found.
- Store artifacts by hash/ref; replay must show recorded artifacts, not current
  page state.
- Keep captures bounded: GIF/video/trace for interactive web demos, screenshots
  for static visual proof and fallback.
- Redact secrets from URLs, console logs, and traces.
- Do not start long-lived dev servers without cleanup.
- If another server already owns the target port, use another port and record
  it in metadata.

## First Implementation Slice

1. Add a small `orchestrator/lib/demo.py` module:
   - detect demoable tasks from acceptance/evidence text,
   - select an adapter plan, starting with `playwright_web`,
   - create `demo_id`,
   - write metadata,
   - emit `demo_planned` / `demo_skipped`.
2. Register demo event types in backend and frontend registries.
3. Add a backend test for detection and event shape.
4. Add a frontend EventEngine fold for demo events.
5. Render demo cards in Story Lens from folded events.

Only after that should Playwright media capture be automated. The first slice
can plan `playwright_web` demos without launching browsers.

## Second Implementation Slice

1. Add `demo_capture.py` or a CLI helper that can:
   - start a configured command,
   - wait for route readiness,
   - run the selected Playwright spec,
   - capture video, trace, screenshot(s), and derived GIF when configured,
   - write `.orchestrator/demos/<demo_id>/metadata.json`.
2. Emit `demo_capture_started`, `demo_artifact_created`, and
   `demo_capture_failed`.
3. Add tests using a minimal local HTML/server fixture.
4. Attach demo artifacts to narrative digest / discussion story rows.

## Relationship To Existing Phases

- **M07 Artifact Previews:** demo artifacts are rich artifact previews with
  stronger ceremony semantics.
- **M11 Replay Resilience:** replay export bundles should include demo
  artifacts and metadata.
- **M12 Release Hardening:** final release should include a self-demo path and
  recorded evidence.

## Open Questions

- Should demo capture run after tester, after reviewer, or as its own optional
  workflow phase?
- Should model agents be allowed to propose the demo script, with deterministic
  validation before execution?
- For Playwright web demos, should `demo.gif` be generated eagerly at capture
  time, or lazily from `interaction.webm` with size and duration caps?
- How should demo artifacts be garbage-collected across long-running projects?
