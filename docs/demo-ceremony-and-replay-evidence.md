# Demo Ceremony And Replay Evidence

Last updated: 2026-04-22

## Purpose

The orchestrator should not only build software and log events. When the work
is visually or interactively demoable, the run should produce a durable "show
the work" artifact: screenshot, video, trace, or compact replay card. This makes
the system more useful as an engineering tool and more enjoyable to watch as a
PWA experience.

The demo ceremony becomes part of the mini-sprint record:

- the team decides whether a task is demoable,
- a deterministic scenario is run,
- visual proof is captured,
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

## Demoable Work Detection

The first implementation should be conservative. A task is demoable when one of
these is true:

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

- `explicit`: acceptance criteria or evidence required asks for it.
- `inferred`: frontend/web files plus runnable route are detected.
- `operator_requested`: operator intent asked for it.
- `not_demoable`: no useful visual surface found.

## Ceremony Flow

1. **Plan**
   - Parse acceptance criteria and evidence requirements.
   - Decide whether a demo is required, suggested, or skipped.
   - Emit `demo_planned`.

2. **Prepare**
   - Resolve start command or static HTML target.
   - Start or reuse a dev server when needed.
   - Decide viewport(s): desktop, mobile, or both.
   - Emit `demo_capture_started`.

3. **Capture**
   - Use Playwright when possible.
   - Capture screenshot by default.
   - Capture video or trace when interaction matters.
   - Optional GIF generation can be a later derived artifact, not the default.
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
  "confidence": "explicit",
  "reason": "acceptance criteria requested Playwright screenshot",
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
  "route": "http://127.0.0.1:5173/game",
  "viewport": {"width": 393, "height": 852, "name": "mobile"},
  "artifact_refs": [
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
      desktop.png
      mobile.png
      interaction.webm
      trace.zip
      summary.md
```

`metadata.json` should include:

- demo id,
- run id / project id,
- task id / atom id,
- trigger event id,
- capture command,
- start command,
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
- [ ] Demo: capture mobile and desktop screenshots of the map route.

**Evidence Required:**
- Run `uv run pytest -q web/frontend/tests/test_game_map.py`
- Run `./web/frontend/build.sh`
- Capture Playwright screenshots for 393x852 and 1440x900.
```

Later, this can become structured metadata:

```yaml
demo:
  required: true
  route: /game
  viewports: [mobile, desktop]
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

- Demo capture is evidence, not an assertion. Tests still decide pass/fail.
- Never block non-visual backend work on a visual demo.
- Skip with a durable reason when no route or server can be found.
- Store artifacts by hash/ref; replay must show recorded artifacts, not current
  page state.
- Keep captures bounded: default screenshots, optional video/trace only when
  useful.
- Redact secrets from URLs, console logs, and traces.
- Do not start long-lived dev servers without cleanup.
- If another server already owns the target port, use another port and record
  it in metadata.

## First Implementation Slice

1. Add a small `orchestrator/lib/demo.py` module:
   - detect demoable tasks from acceptance/evidence text,
   - create `demo_id`,
   - write metadata,
   - emit `demo_planned` / `demo_skipped`.
2. Register demo event types in backend and frontend registries.
3. Add a backend test for detection and event shape.
4. Add a frontend EventEngine fold for demo events.
5. Render demo cards in Story Lens from folded events.

Only after that should Playwright capture be automated.

## Second Implementation Slice

1. Add `demo_capture.py` or a CLI helper that can:
   - start a configured command,
   - wait for route readiness,
   - capture screenshot(s),
   - optionally capture trace/video,
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
- Should GIFs be generated eagerly, or derived lazily from webm/trace only when
  the PWA needs them?
- How should demo artifacts be garbage-collected across long-running projects?
