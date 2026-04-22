# M07 — Artifact Previews And Source Refs

## Purpose

Make generated artifacts visible in-world: bounded preview cards anchored to the producing atom, linked from event/digest source refs. Every `artifact_refs` entry in the narrative layer must resolve to a renderable preview.

## Why this phase exists

SRS §4.8 (UI shows causality) and §8 (events link artifacts) demand visible lineage. Without previews, DWAs are abstract. Design doc F8 Artifact Preview Cards. Also: artifact references are the main channel for "who made this, from what, feeding what."

## Required context files

- `docs/pwa-narrative-replay-and-intervention-design.md` §F8 Artifact Preview Cards, §Visual Grammar
- `docs/demo-ceremony-and-replay-evidence.md`
- `docs/srs-council-engine.md` §4.8, §8, §12 Data And Artifacts
- `web/backend/routes/artifacts.py` (existing artifact route)
- `M04-narrative-digest-and-discussion-log.md` (owns source refs)
- `QUALITY_GATES.md` G5, G8

## Implementation surface

- `web/backend/routes/artifacts.py` (bounded preview endpoint — size cap, mime sniff)
- `orchestrator/lib/artifact_preview.py` (generate preview excerpt, hash, size)
- Event: `artifact_preview_created` (payload: `artifact_ref`, `excerpt`, `hash`, `bytes`, `producing_atom_id`)
- Demo events: `demo_planned`, `demo_skipped`, `demo_capture_started`,
  `demo_artifact_created`, `demo_capture_failed`, `demo_presented` (payloads
  defined in `docs/demo-ceremony-and-replay-evidence.md`; web/PWA demos use
  the `playwright_web` adapter plan)
- Frontend `ArtifactPreviewCard.tsx` — markdown / code / JSON snippet rendering
- Frontend scene anchor: preview body tethered to producing atom; dimmed when stale

## Tasks

- [ ] Define `artifact_preview_created` event schema. Register.
- [ ] Emit `artifact_preview_created` after each role produces its canonical artifact (sprint-plan, phase-files, TEST_REPORT, REVIEW, DEPLOY, digest markdowns).
- [ ] Cap preview excerpt size (e.g., 8 KiB text, 2 KiB for code tail). Larger artifacts surface a "open full" link.
- [ ] Artifact route: enforce project path traversal guard; return `Content-Type` by extension; 404 on absent.
- [ ] Hash each preview (sha256 of the full artifact) so replay can detect "same ref, changed content" divergence.
- [ ] Frontend fetches preview on demand; caches by `(artifact_ref, hash)`.
- [ ] Anchor preview body to producing atom via tether; shrink/fade when older than N events.
- [ ] In Story/Object views, tapping a source `artifact:<ref>` opens the preview card.
- [x] Detect demoable tasks from acceptance criteria / evidence requirements
  and select a demo adapter, starting with `playwright_web`. **Landed (A-10
  slice 1, `9e8b5bc`)** via `orchestrator/lib/demo.detect_playwright_demo_plan`
  with five confidence tiers (`explicit_playwright`, `operator_requested`,
  `inferred_interactive_web`, `static_visual`, `not_demoable`).
- [x] Emit `demo_planned` or `demo_skipped` for compatible mini-sprint tasks.
  **Landed (A-10 slice 1)** via `orchestrator/lib/demo.emit_demo_plan`, with
  deterministic `demo_id` seeded from
  `(task_id|atom_id, adapter, spec_path, trigger_event_id)` for retry
  idempotency. A-9 `wake_up_hash` + `memory_refs` stamped on every event.
- [x] Store demo artifacts under `.orchestrator/demos/<demo_id>/` with
  metadata, hashes, source refs, memory provenance, and the exact test command
  / spec path when a Playwright web demo is used. **Landed (A-10 slices 2 +
  2b, `d5215df` / `830e37a`)** via `orchestrator/lib/demo_capture.py`
  (sha256 + byte hashing, project-relative `artifact_ref`,
  `write_demo_metadata`) and `orchestrator/lib/demo_runner.py` (end-to-end
  lifecycle writing `.orchestrator/demos/<demo_id>/metadata.json` with plan
  / capture event ids, log tail, artifact refs, A-9 provenance).
- [x] Render demo cards in Story/Object lenses as proof artifacts tied to the
  producing atom. **Landed (A-10 slice 3, `2df8d3f`)** via
  `storyDemoCard(demo, projectId)` in `web/frontend/src/game/GameShell.ts` +
  new `data-role="story-demo-rail"` (latest 3 demos) and
  `data-role="object-demo-rail"` (atom-filtered latest 2 demos). Thumbnails
  and artifact links stream through the slice-2b
  `/api/projects/{id}/demos/{demo_id}/{name:path}` route; all state folds
  from the replay snapshot so scrub reproduces the card state at any
  earlier event index.

## Quality gates

- [ ] G5 Source-ref credibility — every preview event carries `producing_atom_id` and `hash`.
- [ ] G8 Security — path traversal blocked; preview route refuses absolute paths.
- [ ] G1 Event integrity on `artifact_preview_created`.
- [ ] G3 Mobile — preview card fits portrait, code wraps or truncates; no horizontal scroll required for the essential identity.
- [x] Demo ceremony boundedness — visual capture is optional evidence, not a
  hard requirement for non-visual/backend-only work. **Enforced** by the
  detection step emitting `demo_skipped` with a source-backed reason for
  `static_visual` and `not_demoable` confidences.
- [x] Web demo integrity — GIF/video/trace artifacts for web/PWA work are
  captured from the same Playwright spec that asserts the acceptance
  criteria. **Enforced** by the runner plumbing `test_command` + `spec_path`
  from the plan event through to the captured metadata, and by the detector
  requiring explicit / inferred Playwright signals before planning a
  `playwright_web` demo.
- [x] Replay proof — demo cards render from recorded demo artifacts, not from
  current live page state. **Verified** by slice-3 cards reading strictly
  from `EngineSnapshot.demos` and streaming media through the bounded
  `/api/projects/{id}/demos/{demo_id}/…` route; jsdom test asserts the
  presented-demo path renders the recorded artifact URL.

## Evidence commands / checks

```bash
uv run pytest -q tests/test_artifact_preview.py web/backend/tests/test_artifacts.py
uv run pytest -q tests/test_demo_ceremony.py web/frontend/tests/test_event_engine.py
uv run pytest -q web/frontend/tests/test_artifact_preview_card.py
# path traversal test must refuse `..` and absolute paths
```

## Done means

- [ ] Every canonical SDLC artifact emits an `artifact_preview_created` event after write.
- [ ] DWA highlight with `artifact:<ref>` renders a preview on tap.
- [ ] Previews are size-capped; large artifacts surface an "open full" control without blowing memory.
- [ ] Preview hash mismatch between event and fetched content surfaces a visible "stale" state.
- [~] Demoable frontend work produces at least one durable demo card or a
  source-backed `demo_skipped` reason. **Code path delivered** (detector +
  emitter + runner + lens card); still blocked on wiring a real Playwright
  spec into a shipped mini-sprint so a live run produces the first durable
  demo card against a real browser.
- [x] Web/PWA demo cards identify the `playwright_web` adapter, spec path,
  test command, route, viewport, and captured `demo.gif` or
  `interaction.webm` when available. **Landed (slice 3)** — `storyDemoCard`
  renders adapter + route + viewport in the header, test command + spec
  path via the plan fields, and thumbnails off the first available `gif` /
  `screenshot` artifact with fallback chips for every other captured
  artifact kind (webm, trace, screenshot).

## Known traps

- Emitting preview with absolute path: violates G8 and breaks cross-machine replay.
- Returning binary artifacts (GLBs, images) through the text preview path: detect by mime and render a placeholder.
- Caching previews indefinitely on the frontend: key on hash, not on ref alone.
- Capturing a polished browser path that is not asserted by the acceptance spec:
  web/PWA ceremony media must come from the Playwright demo/acceptance run.
- Generating GIF/video for non-interactive or backend-only tasks: use adapter
  qualification and emit `demo_skipped` when there is no useful visual surface.

## Handoff notes

- M04 digests must include `artifact_refs`; M07 ensures they resolve.
- M06 owns the visual anchor rules; M07 owns payload + rendering contract.
- M11 replay export bundles should include demo artifacts and metadata.
