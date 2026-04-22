# Handover — Orchestration PWA Event Surface

Last updated: 2026-04-22 after completing M02B Steps 1-7, M02C packet refresh, M02D PWA client intent ids, M02E map intent packet visuals, M04A deterministic narrative digest spine, M04B durable discussion log projection, M05A narrator role contract/read-only opencode path, M05B narrator dialogue presentation surface, M05C narrator sidecar hook/refined packet emission, M05D narrator polish/workflow phase support, M06A Object Lens map sheet, M06B Story Lens first pass, and M06C Goal Core body/project brief sheet.

## Immediate Pickup

The next execution slice is **M06D Founding Team cluster / persona mind sheet** or **M06B polish for digest-level story scrubbing**, depending on whether the operator wants persona interaction or deeper replay browsing first.

Do this before coding:

1. Run `git status --short`.
2. Read this handover top-to-bottom.
3. Read `project-management/srs-mini-phases/M06-pwa-lenses-and-map-surface.md`.
4. Inspect `web/frontend/src/game/GameShell.ts`, `web/frontend/src/game/SceneManager.ts`, `web/frontend/src/game/EventEngine.ts`, and `web/frontend/src/game/types.ts`.
5. Preserve the current product distinction: the narrator model is a neutral summarizer; the PWA renders the summary in a visually game-grade dialogue shell.

M06A, M06B, and M06C have landed. Continue M06 in small sequential steps:

1. Add Founding Team cluster + persona mind sheet, or add digest-level Story Lens scrub controls.
2. Use existing folded `nextStepPacket`, digest, discussion, and intent lifecycle state.
3. Keep Goal Core, Object Lens, Story Lens, narrator dialogue overlay, and Next-Step Sheet as map-native surfaces.
4. Verify mobile portrait and desktop with the existing frontend tests/build before adding more visual complexity.

Quality gates for M06:

- No dashboard regression: new information appears as map lenses/sheets, not a separate progress page.
- UI state must fold from the event ledger.
- Mobile portrait must remain usable.
- Existing M02/M04/M05/M06 frontend and backend guards must remain green.

## Kickoff Prompt For A Fresh Context

> You are picking up the `guildr` SDLC orchestrator in `build/workspace/`. First read `project-management/STATUS.md`, `docs/pwa-narrative-replay-and-intervention-design.md`, `project-management/srs-mini-phases/M02-intent-lifecycle-and-next-step.md`, `project-management/srs-mini-phases/M02B-intent-lifecycle-execution-plan.md`, `project-management/srs-mini-phases/M04-narrative-digest-and-discussion-log.md`, `project-management/srs-mini-phases/M05-narrator-scribe-agent.md`, `project-management/srs-mini-phases/M06-pwa-lenses-and-map-surface.md`, and `project-management/HANDOVER_M02B.md`. M02B is complete as written, M02C now emits a fresh authoritative `next_step_packet_created` immediately after each accepted `operator_intent`, M02D makes the PWA generate `client_intent_id` before posting map intents, M02E renders ledger-derived queued/applied/ignored intent packet markers directly in the 3D map, M04A adds deterministic `narrative_digest_created` DWAs, M04B adds durable `discussion_entry_created` / `discussion_highlight_created` projection into `.orchestrator/discussion/`, M05A adds a bounded read-only narrator role that validates JSON before emitting upgraded digests, M05B renders neutral narrator/DWA summaries as an in-map dialogue layer, M05C adds `orchestrator/lib/narrator_sidecar.py` so phase/gate boundaries can emit narrator-refined next-step packets while operator intents only emit a fast non-blocking `narrator_sidecar_requested` event, M05D adds rejected-output diagnostics, optional workflow handler `narrator`, and a literal pre-step fallback trigger when no next-step packet can be built, M06A adds an in-scene Object Lens sheet over selected atoms, M06B adds a Story Lens sheet plus scene-level story focus/dimming over recent digest/discussion atoms, and M06C adds a backend-synthesized project brief endpoint plus a tappable Goal Core body/sheet. The JRPG reference is UI treatment only, not a narrator roleplay prompt. Operator intents persist to `.orchestrator/control/intents.jsonl`, attach to authoritative packets, get consumed into prompts exactly once or ignored with a terminal reason, fold into replayable PWA state, and render through the map's Goal Core/Next-Step Sheet/Object Lens/Story Lens alongside story/discussion context. Do not create a separate dashboard for this surface; the PWA map is the priority. Preserve backend-authoritative packets and event-ledger replay. Before editing, run `git status --short` and do not revert unrelated user changes.

## Current State

M02B closed the gap between "operator submits an intent" and "the PWA can prove what happened to it."

The lifecycle is now:

1. PWA/backend receives `operator_intent`.
2. Backend writes a scrubbed queued row into `.orchestrator/control/intents.jsonl`.
3. GameShell includes a PWA-generated `client_intent_id` for map compose submissions.
4. `POST /intents` emits a fresh `next_step_packet_created` for the active/current next step.
5. `build_next_step_packet()` attaches queued intents relevant to the authoritative next step.
6. Prompt assembly consumes supported queued intents (`interject`, `intercept`, `reroute`) exactly once.
7. Prompt consumption emits `operator_intent_applied`.
8. Phase/gate completion ignores stale targeted intents and unsupported prompt kinds, emitting `operator_intent_ignored`.
9. EventEngine folds `operator_intent`, `operator_intent_applied`, and `operator_intent_ignored` into replayable `pendingIntents`, `appliedIntents`, and `ignoredIntents`.
10. SceneManager renders queued/applied/ignored intent packet markers above target atoms.
11. Engine emits deterministic `narrative_digest_created` DWAs after durable phase/gate boundaries.
12. EventEngine folds `digests`/`latestDigest`; GameShell renders the latest story inside the map Next-Step Sheet.
13. Operator instructions, map `note` intents, and persona statements emit durable discussion entries/highlights.
14. EventEngine folds `discussion`/`discussionHighlights`; GameShell renders recent discussion rows inside the map Next-Step Sheet.
15. GameShell renders latest digest/discussion narration through an in-world `narrator-dialogue` overlay with typewriter reveal and replay/skip controls.
16. Engine phase/gate boundaries run the narrator sidecar when a runner exists, producing narrator-refined `next_step_packet_created` events.
17. Backend operator intents emit `narrator_sidecar_requested` after the refreshed packet, without running the narrator in the HTTP request.
18. GameShell renders Object Lens as an in-scene sheet for selected atoms: what, consumed, produced, story, next relation, intents, and intervention controls.
19. GameShell renders Story Lens as an in-scene sheet over replay-folded digests, discussion highlights, source refs, artifact refs, and next-step relation.
20. SceneManager supports story focus over recent narrative atoms and dims unrelated atoms without creating a second scene.
21. Backend exposes `GET /api/projects/{project_id}/brief` as a scrubbed, synthesized project brief; the frontend does not scrape raw project files.
22. SceneManager renders a tappable Goal Core body in the same Three.js scene; GameShell renders a map-native project brief sheet from that body/HUD control.
23. GameShell renders `snapshot.nextStepPacket` through the bottom HUD `Next:` control and compact map sheet.

## What Landed

### M02a — Authoritative Next-Step Packets

Files:

- `orchestrator/lib/next_step.py`
- `orchestrator/engine.py`
- `web/frontend/src/game/EventEngine.ts`
- `web/frontend/src/game/types.ts`
- `tests/test_next_step.py`
- `tests/test_engine.py`
- `web/frontend/tests/test_event_engine.py`

Behavior:

- Selects the next enabled incomplete workflow step deterministically.
- Emits `next_step_packet_created` before a phase starts and after phase/gate approval.
- Includes M08 memory provenance through `memory_provenance()`.
- Frontend replay shows the packet known at that event index.

### M02B Steps 1-2 — Durable Queue + Packet Attachment

Files:

- `orchestrator/lib/intents.py`
- `web/backend/routes/intents.py`
- `orchestrator/lib/next_step.py`
- `web/frontend/src/game/EventEngine.ts`
- `web/frontend/src/game/types.ts`
- `tests/test_intents.py`
- `web/backend/tests/test_intents.py`
- `tests/test_next_step.py`
- `web/frontend/tests/test_event_engine.py`

Behavior:

- `POST /api/projects/{project_id}/intents` returns/preserves `client_intent_id`.
- Accepted intents persist as scrubbed queued rows.
- `next_step_packet_created.packet.queued_intents` includes rows where `atom_id == step` or `atom_id == null`.
- EventEngine exposes `nextStepPacket.queuedIntents`.

### M02B Step 3 — Prompt Intent Application

Files:

- `orchestrator/lib/intents.py`
- `orchestrator/lib/control.py`
- `orchestrator/roles/architect.py`
- `orchestrator/roles/coder.py`
- `orchestrator/roles/tester.py`
- `orchestrator/roles/reviewer.py`
- `orchestrator/roles/deployer.py`
- `tests/test_intents.py`
- `tests/test_coder.py`

Behavior:

- `consume_prompt_intents(project_dir, step)` consumes supported queued intents.
- `append_operator_context(..., events=state.events)` injects `## Operator Intent` into role prompts.
- Rows become `status="applied"` and emit `operator_intent_applied`.
- Re-running context assembly does not double-apply.
- If `events` is omitted, context assembly does not silently consume the intent.

### M02B Step 4 — Ignored Terminal Outcomes

Files:

- `orchestrator/lib/intents.py`
- `orchestrator/engine.py`
- `tests/test_intents.py`
- `tests/test_engine.py`

Behavior:

- `ignore_queued_intents_for_passed_step(project_dir, step)` marks stale targeted intents ignored with `target_step_passed`.
- Unsupported prompt kinds (`note`, `resume`, `skip`, `retry`) are ignored with `unsupported_kind` unless another subsystem handles them later.
- Engine emits `operator_intent_ignored` after phase/gate completion before emitting the next packet.

### M02B Step 5 — Frontend Lifecycle Fold

Files:

- `web/frontend/src/game/EventEngine.ts`
- `web/frontend/src/game/types.ts`
- `web/frontend/tests/test_event_engine.py`

Behavior:

- `EngineSnapshot` now includes:
  - `pendingIntents`
  - `appliedIntents`
  - `ignoredIntents`
- Replay scrub reconstructs queued/applied/ignored state exactly at the chosen event index.
- Current next-step packets merge relevant pending intents submitted after packet creation.

### M02B Step 6 — PWA Next-Step Sheet

Files:

- `web/frontend/src/game/GameShell.ts`
- `web/frontend/tests/test_game_map.py`

Behavior:

- Bottom HUD has an always-present `Next:` control backed by `snapshot.nextStepPacket`.
- Tapping it opens `data-role="next-step-sheet"` over the map, not a separate dashboard.
- Sheet shows:
  - next step title/role
  - objective
  - why now
  - context preview
  - inputs
  - memory refs
  - source refs
  - queued/applied/ignored intents
  - `Nudge` action, wired into the existing compose dock for the next step
- Browser visual check passed on desktop and iPhone-size `393x852`; no sheet/HUD overlap, sheet inside viewport, canvas nonblank.

### M02B Step 7 — End-To-End Rehearsal

Files:

- `tests/test_integration_m02b_intent_lifecycle_rehearsal.py`
- `project-management/STATUS.md`
- M02/M02B plan docs

Behavior covered:

- Backend project intent submission through ASGI.
- Durable queued registry rows.
- Engine emits next-step packet for current and following steps.
- Targeted intent becomes `operator_intent_ignored` after its step passes.
- Global intent remains queued for the following packet.
- EventEngine folds the combined ledger into replayable frontend state.

### M02C — Packet Refresh After Intent Submission

Files:

- `web/backend/routes/intents.py`
- `web/backend/tests/test_intents.py`
- `tests/test_integration_m02b_intent_lifecycle_rehearsal.py`
- `project-management/srs-mini-phases/M02-intent-lifecycle-and-next-step.md`

Behavior:

- `POST /api/projects/{project_id}/intents` now emits `operator_intent`, then immediately emits a refreshed `next_step_packet_created`.
- The packet is built from `State(project_dir)` and uses `current_step=state.current_phase` when the run has an active phase.
- The refreshed packet carries queued intents for the authoritative current/next step.
- The end-to-end rehearsal proves packet refresh after each intent before engine phase execution continues.

### M02D — PWA-Side Client Intent Id

Files:

- `web/frontend/src/game/GameShell.ts`
- `web/frontend/tests/test_game_map.py`
- `project-management/srs-mini-phases/M02-intent-lifecycle-and-next-step.md`

Behavior:

- `GameShell.queueCompose()` now generates a `client_intent_id` before posting to `/intents`.
- The id is included for `interject`, `intercept`, and `reroute` map actions.
- Backend preservation remains the authoritative round-trip check.

### M02E — 3D Map Intent Packet Visuals

Files:

- `web/frontend/src/game/SceneManager.ts`
- `web/frontend/tests/test_game_map.py`
- `project-management/srs-mini-phases/M02-intent-lifecycle-and-next-step.md`

Behavior:

- `SceneManager.applySnapshot()` syncs persistent intent packet sprites from `pendingIntents`, `appliedIntents`, and `ignoredIntents`.
- Sprites are ledger-derived scene objects anchored above the target atom, not a separate DOM dashboard.
- Queued/applied/ignored states have distinct billboard glyphs and colors.
- Missing/obsolete markers are removed when replay scrub changes the folded state.

### M04A — Deterministic Narrative Digest Spine

Files:

- `orchestrator/lib/narrative.py`
- `orchestrator/engine.py`
- `web/frontend/src/game/EventEngine.ts`
- `web/frontend/src/game/types.ts`
- `web/frontend/src/game/GameShell.ts`
- `tests/test_narrative_digest.py`
- `tests/test_engine.py`
- `web/frontend/tests/test_event_engine.py`
- `web/frontend/tests/test_game_map.py`
- `project-management/srs-mini-phases/M04-narrative-digest-and-discussion-log.md`

Behavior:

- `build_narrative_digest()` creates deterministic DWA payloads with `window`, `title`, `summary`, `highlights`, `risks`, `open_questions`, `next_step_hint`, `source_event_ids`, and `artifact_refs`.
- Digest validation rejects unknown source events, unsourced highlights, unsafe artifact refs, and overlong summaries.
- `emit_narrative_digest()` writes `.orchestrator/narrative/digests/{digest_id}.json` and `.md`, then emits `narrative_digest_created`.
- Engine emits a digest after completed phase/gate boundaries when the event bus returns durable event ids.
- EventEngine folds `narrative_digest_created` into replayable `digests` and `latestDigest`.
- GameShell renders `snapshot.latestDigest` inside the existing map Next-Step Sheet and fallback surface.

### M04B — Durable Discussion Log Projection

Files:

- `orchestrator/lib/discussion.py`
- `orchestrator/roles/persona_forum.py`
- `web/backend/routes/control.py`
- `web/backend/routes/intents.py`
- `web/frontend/src/game/EventEngine.ts`
- `web/frontend/src/game/types.ts`
- `web/frontend/src/game/GameShell.ts`
- `tests/test_discussion.py`
- `web/backend/tests/test_control.py`
- `web/backend/tests/test_intents.py`
- `web/frontend/tests/test_event_engine.py`
- `web/frontend/tests/test_game_map.py`
- `project-management/srs-mini-phases/M04-narrative-digest-and-discussion-log.md`

Behavior:

- `append_discussion_entry()` writes scrubbed `.orchestrator/discussion/log.jsonl` rows and can emit `discussion_entry_created`.
- `append_discussion_highlight()` writes `.orchestrator/discussion/highlights.jsonl` rows and can emit `discussion_highlight_created`.
- `python -m orchestrator.lib.discussion --rebuild <project_dir>` rebuilds projection files from `.orchestrator/events.jsonl`.
- `POST /control/instructions` emits an operator discussion entry.
- Map `note` intents emit discussion entries sourced to the originating `operator_intent`.
- Persona synthesis and `PersonaForum.execute()` emit one persona statement per persona plus a sourced highlight.
- EventEngine folds discussion entries/highlights with replay scrub support.
- GameShell renders recent discussion rows and highlights inside the existing map Next-Step Sheet and fallback surface.

### M05A — Narrator Role Contract + Read-Only Opencode Path

Files:

- `orchestrator/roles/narrator.py`
- `orchestrator/roles/narrator_dryrun.py`
- `orchestrator/roles/prompts/narrator/generate.txt`
- `orchestrator/lib/opencode_config.py`
- `orchestrator/cli/run.py`
- `tests/test_narrator.py`
- `tests/test_opencode_config.py`
- `tests/test_cli_run.py`
- `project-management/srs-mini-phases/M05-narrator-scribe-agent.md`

Behavior:

- `build_narrator_packet()` creates a bounded, scrubbed packet from project goal, workflow, recent events, next-step packet, deterministic digest, discussion rows, and short artifact excerpts.
- `parse_narrator_digest()` requires JSON, known `source_event_ids`, safe relative `artifact_refs`, sourced highlights, and summary length inherited from M04 validation.
- `Narrator.execute()` audits the opencode session, writes/emits a validated narrator digest, and emits one `discussion_entry_created` summary.
- Invalid narrator JSON or failed sessions return the deterministic M04 digest with `fallback_used=True` and do not emit corrupt digest/discussion events.
- `DryRunNarratorRunner` returns a valid sourced JSON payload without an opencode binary.
- `opencode_config.build_agent_definitions()` now includes a `narrator` agent with only `read` and `grep` enabled.
- The live runner builder can route `narrator` through opencode when `routing.narrator` is declared.

### M05B — Narrator Dialogue Presentation Surface

Files:

- `docs/pwa-narrative-replay-and-intervention-design.md`
- `project-management/srs-mini-phases/M05-narrator-scribe-agent.md`
- `project-management/srs-mini-phases/M06-pwa-lenses-and-map-surface.md`
- `web/frontend/src/game/GameShell.ts`
- `web/frontend/tests/test_game_map.py`

Behavior:

- Design docs now define narrator output as neutral sourced project synthesis, not workflow authority and not a JRPG roleplay persona.
- The docs explicitly allow independent `routing.narrator` model selection, including OpenRouter for cheap narration while coder/tester run local or on-prem.
- GameShell now mounts `data-role="narrator-dialogue"` over the map.
- The dialogue derives from replay-folded `latestDigest`, falling back to the latest discussion row when no digest exists.
- Presentation includes speaker identity (`Run Narrator` for digest narration), title, source label, live/replay label, typewriter reveal, replay, skip/done, and reduced-motion fallback.
- The narrator overlay hides when the operator is actively using the next-step sheet, action ring, or compose dock.
- The WebGL fallback route renders the same narrator cue as an accessible dialogue block.

### M05C — Narrator Sidecar Hook + Packet Refinement

Files:

- `orchestrator/lib/narrator_sidecar.py`
- `orchestrator/engine.py`
- `web/backend/routes/intents.py`
- `web/backend/routes/stream.py`
- `tests/test_narrator_sidecar.py`
- `tests/test_engine.py`
- `web/backend/tests/test_intents.py`
- `tests/test_integration_m02b_intent_lifecycle_rehearsal.py`
- `project-management/srs-mini-phases/M05-narrator-scribe-agent.md`

Behavior:

- `run_narrator_sidecar()` owns debounce, narrator execution, deterministic fallback, and refined packet emission.
- Debounce state persists at `.orchestrator/narrative/sidecar-state.json`.
- Engine `phase_done`, `gate_decided`, and `phase_error` now call the sidecar.
- With a narrator runner, the sidecar emits narrator digest/discussion events and a narrator-refined `next_step_packet_created`.
- The refined packet carries `refined_by="narrator"`, `base_packet_id`, `narrative_digest_id`, source-backed `context_preview`, and merged `source_refs`.
- Without a narrator runner, deterministic M04 digest emission remains intact and `narrator_sidecar_skipped` records why.
- Invalid narrator JSON falls back to deterministic digest and emits `narrator_sidecar_fallback`; no refined packet is emitted.
- `SimpleEventBus.emit()` now returns the normalized event, allowing follow-up events to source-link to the originating event.
- `POST /intents` emits `narrator_sidecar_requested` after the refreshed authoritative packet. It does not run a narrator session in the HTTP request.

### M05D — Narrator Polish + Workflow Phase Support

Files:

- `orchestrator/roles/narrator.py`
- `orchestrator/lib/narrator_sidecar.py`
- `orchestrator/lib/workflow.py`
- `orchestrator/engine.py`
- `tests/test_narrator.py`
- `tests/test_narrator_sidecar.py`
- `tests/test_engine.py`
- `orchestrator/tests/test_workflow.py`
- `project-management/srs-mini-phases/M05-narrator-scribe-agent.md`

Behavior:

- Rejected narrator output now writes JSON diagnostics under `.orchestrator/narrative/diagnostics/`.
- Workflow phase handlers now include optional `narrator` support.
- Engine pre-step fallback can trigger a literal narrator handoff when no next-step packet can be built.
- Deterministic sidecar fallback keeps artifact refs so the PWA still has sourced narrative context when a live narrator fails.

### M06A — Object Lens Map Sheet

Files:

- `web/frontend/src/game/GameShell.ts`
- `web/frontend/tests/test_game_map.py`
- `project-management/srs-mini-phases/M06-pwa-lenses-and-map-surface.md`
- `project-management/STATUS.md`
- `project-management/HANDOVER_M02B.md`

Behavior:

- Selecting an atom, pressing the Object lens control, or returning to surface focus now opens `data-role="object-lens-sheet"` over the existing map.
- The lens uses the folded `EngineSnapshot`; it does not create a separate route or dashboard.
- The sheet shows object identity, lifecycle state, what it represents, consumed packet inputs/memory refs, produced artifact refs, local digest/discussion story, relation to the current next step, and queued/applied/ignored intents.
- Shape, Nudge, and Intercept actions reuse the existing compose dock with object context already selected.
- Object Lens, Next-Step Sheet, compose dock, action ring, and narrator dialogue now hide/show around each other so mobile and desktop do not stack competing overlays.
- The WebGL fallback remains list-based and does not depend on Object Lens DOM being active.

### M06B — Story Lens First Pass

Files:

- `web/frontend/src/game/GameShell.ts`
- `web/frontend/src/game/SceneManager.ts`
- `web/frontend/src/game/atoms/AtomNode.ts`
- `web/frontend/tests/test_game_map.py`
- `project-management/srs-mini-phases/M06-pwa-lenses-and-map-surface.md`
- `project-management/STATUS.md`
- `project-management/HANDOVER_M02B.md`

Behavior:

- Bottom HUD now includes `Story: <count>` as a map lens control, backed by folded digest/highlight state.
- `GameShell` mounts `data-role="story-lens-sheet"` over the existing map; no route reload or dashboard surface is introduced.
- Story Lens renders recent narrative digests as `story-card` entries with summary, highlights, risks, source refs, artifact refs, recent discussion rows/highlights, and next-step/nudge context.
- `SceneManager` now accepts `SpatialViewLevel = "story"` and `setStoryFocus(...)`.
- Story focus derives from recent digest source events, discussion atom ids, the current next-step atom, and the active atom.
- `AtomNode.setLensDimmed(...)` reduces unrelated atom prominence while keeping the same scene, camera, and replay state.
- Moving from Story into Object, Next, or Compose clears the story dimming immediately; closing Compose restores the Story Lens when appropriate.

### M06C — Goal Core Body + Project Brief Sheet

Files:

- `web/backend/routes/projects.py`
- `web/backend/tests/test_projects.py`
- `web/frontend/src/views/Map.ts`
- `web/frontend/src/game/GameShell.ts`
- `web/frontend/src/game/SceneManager.ts`
- `web/frontend/tests/test_game_map.py`
- `project-management/srs-mini-phases/M06-pwa-lenses-and-map-surface.md`
- `project-management/STATUS.md`
- `project-management/HANDOVER_M02B.md`

Behavior:

- Backend now exposes `GET /api/projects/{project_id}/brief`, returning a scrubbed project title/summary, founding team personas, forum excerpt, and source refs.
- The frontend loads that synthesized brief beside workflow data; it does not read `qwendea.md` or persona artifacts directly.
- `SceneManager` renders a tappable `goal-core:body` in the existing Three.js scene and exposes `focusGoalCore()`.
- Bottom HUD now includes a `Goal` control that opens `data-role="goal-core-sheet"`.
- Goal Core sheet renders project brief, founding team cards, forum pulse, source refs, progress, latest story, next-step relation, and a Nudge action.
- WebGL fallback renders the same goal brief as an accessible block.

## Verification Already Run

Key commands and results:

```bash
uv run pytest -q tests/test_next_step.py tests/test_intents.py web/backend/tests/test_intents.py web/frontend/tests/test_event_engine.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py
# 22 passed

uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py
# 14 passed

uv run pytest -q tests/test_narrative_digest.py tests/test_engine.py::TestLoopEvents::test_phase_completion_emits_narrative_digest
# 4 passed

uv run pytest -q tests/test_narrative_digest.py tests/test_engine.py tests/test_next_step.py tests/test_intents.py web/backend/tests/test_intents.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py
# 48 passed

uv run pytest -q web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py
# 15 passed

uv run pytest -q tests/test_discussion.py tests/test_narrative_digest.py web/backend/tests/test_control.py web/backend/tests/test_intents.py orchestrator/tests/test_workflow.py tests/test_engine.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py
# 55 passed

uv run pytest -q web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py
# 16 passed

uv run pytest -q tests/test_narrator.py tests/test_opencode_config.py::test_narrator_agent_is_read_only tests/test_cli_run.py::test_live_runner_builder_includes_narrator
# 8 passed

uv run python -m py_compile orchestrator/roles/narrator.py orchestrator/roles/narrator_dryrun.py
# passed

uv run pytest -q tests/test_narrator.py tests/test_opencode_config.py tests/test_cli_run.py tests/test_opencode_audit.py
# 29 passed

uv run pytest -q tests/test_narrator.py tests/test_discussion.py tests/test_narrative_digest.py tests/test_opencode_config.py tests/test_cli_run.py tests/test_opencode_audit.py web/backend/tests/test_control.py web/backend/tests/test_intents.py orchestrator/tests/test_workflow.py tests/test_engine.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py
# 84 passed

uv run pytest -q tests/test_narrator_sidecar.py tests/test_narrator.py tests/test_engine.py::TestLoopEvents web/backend/tests/test_intents.py
# 19 passed after M05C

uv run pytest -q tests/test_narrator.py tests/test_narrator_sidecar.py tests/test_engine.py::TestLoopEvents orchestrator/tests/test_workflow.py
# 28 passed after M05D

uv run pytest -q tests/test_narrator_sidecar.py tests/test_narrator.py tests/test_discussion.py tests/test_narrative_digest.py tests/test_opencode_config.py tests/test_cli_run.py tests/test_opencode_audit.py web/backend/tests/test_control.py web/backend/tests/test_intents.py orchestrator/tests/test_workflow.py tests/test_engine.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py
# 92 passed after M05D

uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py
# 16 passed after M05C

uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py
# 16 passed after M06A

uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py
# 16 passed after M06B

uv run pytest -q web/backend/tests/test_projects.py web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py
# 34 passed after M06C

uv run python -m py_compile orchestrator/lib/narrator_sidecar.py orchestrator/engine.py web/backend/routes/intents.py web/backend/routes/stream.py
# passed after M05C

uv run python -m py_compile orchestrator/lib/narrator_sidecar.py orchestrator/roles/narrator.py orchestrator/engine.py orchestrator/lib/workflow.py
# passed after M05D

uv run pytest -q tests/test_narrator_sidecar.py tests/test_narrator.py tests/test_discussion.py tests/test_narrative_digest.py tests/test_opencode_config.py tests/test_cli_run.py tests/test_opencode_audit.py web/backend/tests/test_control.py web/backend/tests/test_intents.py orchestrator/tests/test_workflow.py tests/test_engine.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py
# 92 passed after M06A

uv run pytest -q tests/test_narrator_sidecar.py tests/test_narrator.py tests/test_discussion.py tests/test_narrative_digest.py tests/test_opencode_config.py tests/test_cli_run.py tests/test_opencode_audit.py web/backend/tests/test_control.py web/backend/tests/test_intents.py orchestrator/tests/test_workflow.py tests/test_engine.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py
# 92 passed after M06B

uv run pytest -q tests/test_narrator_sidecar.py tests/test_narrator.py tests/test_discussion.py tests/test_narrative_digest.py tests/test_opencode_config.py tests/test_cli_run.py tests/test_opencode_audit.py web/backend/tests/test_control.py web/backend/tests/test_intents.py web/backend/tests/test_projects.py orchestrator/tests/test_workflow.py tests/test_engine.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py
# 110 passed after M06C

./web/frontend/build.sh
# passed after M06C, dist/app.js 1,309,596 bytes

git diff --check
# clean after M06C handover/status refresh
```

Browser visual evidence from Step 6:

- `/tmp/m02b-step6-desktop.png`
- `/tmp/m02b-step6-mobile.png`
- Desktop canvas signal: `100312`
- Mobile `393x852` canvas signal: `96573`

M05B narrator dialogue screenshots:

- `/tmp/m05b-narrator-desktop.png` (`1440x900`)
- `/tmp/m05b-narrator-mobile.png` (`393x852`)

Earlier slice evidence is in:

- `project-management/STATUS.md`
- `project-management/srs-mini-phases/M02-intent-lifecycle-and-next-step.md`
- `project-management/srs-mini-phases/M02B-intent-lifecycle-execution-plan.md`

## Worktree Cautions

Run this first:

```bash
git status --short
```

At handover time, the worktree is intentionally dirty with this ongoing feature
branch. Expected related changes include:

- `M project-management/STATUS.md`
- `M docs/pwa-narrative-replay-and-intervention-design.md`
- `M project-management/srs-mini-phases/M02-intent-lifecycle-and-next-step.md`
- `M project-management/srs-mini-phases/M02B-intent-lifecycle-execution-plan.md`
- `M project-management/srs-mini-phases/M04-narrative-digest-and-discussion-log.md`
- `M project-management/srs-mini-phases/M05-narrator-scribe-agent.md`
- `M project-management/srs-mini-phases/M06-pwa-lenses-and-map-surface.md`
- `M orchestrator/cli/run.py`
- `M orchestrator/engine.py`
- `M orchestrator/lib/opencode_config.py`
- `M orchestrator/roles/persona_forum.py`
- `M tests/test_cli_run.py`
- `M tests/test_engine.py`
- `M tests/test_opencode_config.py`
- `M web/backend/routes/control.py`
- `M web/backend/routes/intents.py`
- `M web/backend/routes/stream.py`
- `M web/backend/tests/test_control.py`
- `M web/backend/tests/test_intents.py`
- `M web/frontend/src/game/EventEngine.ts`
- `M web/frontend/src/game/GameShell.ts`
- `M web/frontend/src/game/SceneManager.ts`
- `M web/frontend/src/game/types.ts`
- `M web/frontend/tests/test_event_engine.py`
- `M web/frontend/tests/test_game_map.py`
- `?? orchestrator/lib/discussion.py`
- `?? orchestrator/lib/narrative.py`
- `?? orchestrator/lib/narrator_sidecar.py`
- `?? orchestrator/roles/narrator.py`
- `?? orchestrator/roles/narrator_dryrun.py`
- `?? orchestrator/roles/prompts/narrator/`
- `?? tests/test_discussion.py`
- `?? tests/test_integration_m02b_intent_lifecycle_rehearsal.py`
- `?? tests/test_narrative_digest.py`
- `?? tests/test_narrator_sidecar.py`
- `?? tests/test_narrator.py`
- `?? project-management/HANDOVER_M02B.md`

If the actual status contains additional files, treat unknown changes as
user-owned unless you can prove they are yours. Do not clean, reset, or revert
without explicit operator direction.

## Important Invariants

- Backend packets are authoritative. Do not derive the next step purely on the frontend when a packet exists.
- The event ledger is the replay source. UI state must fold from events, not from hidden local caches.
- `operator_intent_applied` must only fire when an intent actually affects prompt/context/artifact/control.
- Every submitted `client_intent_id` should get one terminal outcome unless it is still validly queued for a future step.
- Prompt-facing payload text must go through the scrubber before storage/logging/prompt use.
- The PWA map is the primary surface. Avoid dashboard/table-first implementation for next-step or intent lifecycle UI.
- Keep GameShell overlays compact and mobile-safe; use the existing bottom HUD, action ring, compose dock, timeline ribbon, and sheet patterns.
- The narrator prompt must remain neutral and summarizer-oriented. "JRPG" refers to visual dialogue treatment only, not model persona or system-prompt roleplay.
- `Run Narrator` is the current digest speaker label in the PWA. It is intentionally generic.

## Remaining Open Items

From M02:

- "Opening the PWA always shows `Next: <step>`" has a fallback label of `Next: No packet` until the backend emits a packet. Decide whether this is acceptable or whether a tentative fallback packet should be clearly labeled.

Recommended next concrete slices:

1. **M06D Founding Team cluster or Story Lens digest scrubber.**
   - Founding Team cluster should render persona bodies around the Goal Core/discovery region and open a persona mind sheet.
   - Digest scrubber should let the Story Lens scrub digest/story-card windows directly, not only raw event indexes.
   - Keep Goal Core, Object Lens, Story Lens, narrator dialogue, and Next-Step Sheet as coordinated map overlays.

2. **M05 async sidecar worker, if desired.**
   - Consider whether `narrator_sidecar_requested` should be consumed by a background worker in the PWA runner.
   - Keep the current HTTP behavior non-blocking.

3. **M03/M04 polish.**
   - Add `latestDigestByAtom` and richer persona/object targeting.
   - Register discussion artifact paths in onboarding/handoff docs.

## Fast Pickup Commands

```bash
# See current worktree without disturbing user changes
git status --short

# Core M02B guard
uv run pytest -q tests/test_next_step.py tests/test_intents.py web/backend/tests/test_intents.py web/frontend/tests/test_event_engine.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py

# PWA map/sheet guard
uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py

# Narrative digest guard
uv run pytest -q tests/test_narrative_digest.py tests/test_engine.py::TestLoopEvents::test_phase_completion_emits_narrative_digest

# Discussion projection guard
uv run pytest -q tests/test_discussion.py web/backend/tests/test_control.py web/backend/tests/test_intents.py

# Narrator contract guard
uv run pytest -q tests/test_narrator.py tests/test_opencode_config.py tests/test_cli_run.py tests/test_opencode_audit.py

# Narrator sidecar guard
uv run pytest -q tests/test_narrator_sidecar.py tests/test_engine.py::TestLoopEvents web/backend/tests/test_intents.py

# Bundle check
./web/frontend/build.sh

# Whitespace safety
git diff --check
```

## Mental Model

Think of the orchestration framework as an event-sourced control room:

- The backend writes facts.
- The engine moves workflow and emits packets/outcomes.
- The PWA folds facts into a live/replayable operator surface.
- The operator can interrupt the upcoming step, and the system must later prove whether that intervention mattered.

M02B made that loop real enough to build on.
