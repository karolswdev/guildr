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
  `demo_artifact_created`, `demo_presented` (payloads defined in
  `docs/demo-ceremony-and-replay-evidence.md`)
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
- [ ] Detect demoable tasks from acceptance criteria / evidence requirements.
- [ ] Emit `demo_planned` or `demo_skipped` for compatible mini-sprint tasks.
- [ ] Store demo artifacts under `.orchestrator/demos/<demo_id>/` with
  metadata, hashes, source refs, and memory provenance.
- [ ] Render demo cards in Story/Object lenses as proof artifacts tied to the
  producing atom.

## Quality gates

- [ ] G5 Source-ref credibility — every preview event carries `producing_atom_id` and `hash`.
- [ ] G8 Security — path traversal blocked; preview route refuses absolute paths.
- [ ] G1 Event integrity on `artifact_preview_created`.
- [ ] G3 Mobile — preview card fits portrait, code wraps or truncates; no horizontal scroll required for the essential identity.
- [ ] Demo ceremony boundedness — visual capture is optional evidence, not a
  hard requirement for non-visual/backend-only work.
- [ ] Replay proof — demo cards render from recorded demo artifacts, not from
  current live page state.

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
- [ ] Demoable frontend work produces at least one durable demo card or a
  source-backed `demo_skipped` reason.

## Known traps

- Emitting preview with absolute path: violates G8 and breaks cross-machine replay.
- Returning binary artifacts (GLBs, images) through the text preview path: detect by mime and render a placeholder.
- Caching previews indefinitely on the frontend: key on hash, not on ref alone.
- Generating GIF/video eagerly for every task: start with screenshots and only
  capture heavier media when interaction is part of the evidence.

## Handoff notes

- M04 digests must include `artifact_refs`; M07 ensures they resolve.
- M06 owns the visual anchor rules; M07 owns payload + rendering contract.
- M11 replay export bundles should include demo artifacts and metadata.
