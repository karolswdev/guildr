# Handover — 2026-04-22 Brain Dump

You are picking up `guildr`, an SDLC/orchestration PWA, after a large audit and
product-surface integration checkpoint.

Working directory:

```bash
/Users/karol/dev/projects/llm-projects/build/workspace
```

Current committed checkpoint:

```bash
25637fd Integrate orchestration audit and PWA lenses
```

The working tree was clean immediately after that commit.

## First Commands

Run these before touching anything:

```bash
git status --short
git log -1 --oneline
```

If the tree is dirty, treat all existing changes as user/agent work. Do not
revert them unless explicitly asked.

## Read These First

Read in this order:

1. `project-management/STATUS.md`
2. `analysis/04-22-2026-FEEDBACK.md`
3. `docs/founding-team-consultation-design.md`
4. `project-management/srs-mini-phases/M03-project-mythos-and-founding-team.md`
5. `project-management/srs-mini-phases/M08-memory-spine-and-mempalace.md`
6. `project-management/HANDOVER_M02B.md`

The long `HANDOVER_M02B.md` is still useful for broad project context. This
file is the latest compact brain dump for what to do next.

## What This System Is

The product goal is first-class orchestration: follow, review, intervene.

- **Follow:** durable event ledger, SSE replay, frontend replay folding.
- **Review:** raw opencode session audit, usage rows, narrative digests,
  discussion logs, source refs.
- **Intervene:** operator intents are durable, attach to next-step packets,
  get consumed into prompts once, and end as applied or ignored.

The PWA map is the primary surface. Do not build a separate dashboard when a
map-native lens, sheet, body, or overlay can do the job.

The narrator is neutral project synthesis. The JRPG reference is visual
treatment only: dialogue frame, typewriter pacing, replay controls. It is not a
roleplay prompt.

## What Just Changed

The latest checkpoint integrated the audit wave and the PWA lens work.

Major areas now in place:

- Central backend event registry and frontend mirror:
  - `orchestrator/lib/event_types.py`
  - `web/frontend/src/game/eventTypes.ts`
  - `tests/test_event_schema.py`
- Canonical next-step packet emitter:
  - `orchestrator/lib/next_step.py`
  - engine, intents route, and narrator sidecar use it.
- Durable intent lifecycle:
  - queued/applied/ignored intents,
  - prompt-context consumption,
  - terminal outcome events,
  - replay fold into the PWA.
- Narrative/discussion spine:
  - `orchestrator/lib/narrative.py`
  - `orchestrator/lib/discussion.py`
  - deterministic digest artifacts,
  - discussion entries and highlights.
- Narrator agent and sidecar:
  - `orchestrator/roles/narrator.py`
  - `orchestrator/roles/narrator_dryrun.py`
  - `orchestrator/lib/narrator_sidecar.py`
  - fallback diagnostics,
  - sidecar outcome normalization,
  - state-file locking,
  - retry idempotency for `narrator_pre_step`.
- PWA map lenses:
  - Next-Step sheet,
  - Object Lens,
  - Story Lens,
  - Goal Core body/sheet,
  - narrator dialogue overlay.
- Usage convergence:
  - opencode audit rows now route through shared `_usage_payload(...)`,
  - opencode rows carry finish/error/provider metadata,
  - local provider cost estimates can use local rate-card versions.
- SSE cleanup:
  - failed subscribers are logged and pruned,
  - replay eviction no longer shadows the emitted `event_id`.
- A-8 design:
  - `docs/founding-team-consultation-design.md` now defines bounded recurring
    founding-team consultation and temporary Hero reviewers.

## Important Files By Surface

Backend orchestration:

- `orchestrator/engine.py`
- `orchestrator/lib/next_step.py`
- `orchestrator/lib/intents.py`
- `orchestrator/lib/session_runners.py`
- `orchestrator/lib/event_schema.py`
- `orchestrator/lib/event_types.py`

Narrative and discussion:

- `orchestrator/lib/narrative.py`
- `orchestrator/lib/discussion.py`
- `orchestrator/lib/narrator_sidecar.py`
- `orchestrator/roles/narrator.py`
- `orchestrator/roles/narrator_dryrun.py`

Founding team:

- `orchestrator/roles/persona_forum.py`
- `docs/founding-team-consultation-design.md`
- `project-management/srs-mini-phases/M03-project-mythos-and-founding-team.md`

Memory:

- `orchestrator/lib/memory_palace.py`
- `orchestrator/roles/memory_refresh.py`
- `project-management/srs-mini-phases/M08-memory-spine-and-mempalace.md`

PWA:

- `web/frontend/src/game/EventEngine.ts`
- `web/frontend/src/game/GameShell.ts`
- `web/frontend/src/game/SceneManager.ts`
- `web/frontend/src/game/types.ts`
- `web/frontend/src/views/Map.ts`

Backend routes:

- `web/backend/routes/intents.py`
- `web/backend/routes/projects.py`
- `web/backend/routes/stream.py`
- `web/backend/runner.py`

Tests worth running often:

- `uv run pytest -q tests/test_opencode_audit.py`
- `uv run pytest -q tests/test_narrator_sidecar.py`
- `uv run pytest -q tests/test_narrator.py`
- `uv run pytest -q tests/test_discussion.py tests/test_narrative_digest.py`
- `uv run pytest -q web/backend/tests/test_intents.py web/backend/tests/test_events.py web/backend/tests/test_stream.py`
- `uv run pytest -q web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py`
- `./web/frontend/build.sh`

Use full suite when touching `engine.py`, event schema/bus, sidecar, or frontend
fold contracts:

```bash
uv run pytest -q
```

## Current Truth

`project-management/STATUS.md` is now current enough to trust. It says:

- Follow is real.
- Review is real enough for audited opencode sessions but still needs a live
  attended provider walkthrough.
- Intervene is no longer cosmetic; intents are durable and terminal.
- Remaining high-value backend slices are A-8 and A-9.

The main audit checklist is:

```bash
analysis/04-22-2026-FEEDBACK.md
```

Closed items include A-1 through A-7, B-1/B-2/B-3/B-5/B-6/B-7/B-8/B-9/B-10,
and X-2. Do not redo those unless tests fail or the user asks.

## Best Next Slice

There are two good next moves. Pick one based on user intent.

### Option 1 — A-9 Provenance Parity

This is probably the best backend correctness slice.

Problem:

- `narrative_digest_created` and `discussion_entry_created` are user-facing
  review surfaces but do not carry `wake_up_hash` / `memory_refs`.
- The system vision says every user-facing claim should answer: "what memory
  informed this?"

Relevant audit section:

```bash
rg -n "A-9" analysis/04-22-2026-FEEDBACK.md
```

Likely implementation shape:

1. Add a small helper, probably in `orchestrator/lib/memory_palace.py` or a new
   projection helper:

   ```python
   def memory_event_fields(project_id: str | None, project_dir: Path) -> dict[str, Any]:
       provenance = memory_provenance(project_id, project_dir)
       return {
           "wake_up_hash": provenance["wake_up_hash"],
           "memory_refs": provenance["memory_refs"],
           "memory_provenance": provenance,
       }
   ```

2. Thread those fields into:
   - `orchestrator/lib/narrative.py` when emitting `narrative_digest_created`,
   - `orchestrator/lib/discussion.py` when emitting `discussion_entry_created`
     and probably `discussion_highlight_created`.

3. Update event schema / event type expectations if needed.

4. Update frontend fold types so digest/discussion rows can retain memory refs:
   - `web/frontend/src/game/types.ts`
   - `web/frontend/src/game/EventEngine.ts`

5. Add tests:
   - backend test emits narrative digest and discussion entry with an existing
     `.orchestrator/memory/wake-up.md`, asserts `wake_up_hash` and
     `memory_refs`,
   - frontend event-engine test proves discussion/digest fold preserves
     provenance.

6. Update A-9 matrix in `analysis/04-22-2026-FEEDBACK.md`.

Why do this first:

- It makes the review story stronger before adding more generated consultation
  rows.
- A-8 founding-team consultation will immediately benefit from provenance.

### Option 2 — A-8 Founding-Team Consultation

This is the product/vision slice.

Design source:

```bash
docs/founding-team-consultation-design.md
```

Core rules:

- Bounded roundtable, not open-ended debate.
- One trigger event -> one statement per persona + one convergence highlight.
- Prior accepted decisions are binding context.
- Scope expansion becomes `operator_decision_required`, never silent mutation.
- Project memory is injected through `memory_provenance()`, `wake_up_hash`,
  `memory_refs`, and a bounded wake-up excerpt.
- Persona memory is rebuilt from durable state:
  - `FOUNDING_TEAM.json`,
  - `PERSONA_FORUM.md`,
  - discussion rows/highlights,
  - future `persona_stance_updated`.
- Heroes are temporary operator-invited reviewers with mission, watch-for list,
  provider/model, originating intent id, and term limit.

Recommended first implementation:

1. Add `PersonaForum.consult(...)` in `orchestrator/roles/persona_forum.py`.
2. Keep v1 deterministic. Do not call a model yet.
3. Load personas from `FOUNDING_TEAM.json`; if missing, return no-op or a clear
   skipped result. Do not silently synthesize unless the workflow is explicitly
   running persona synthesis.
4. Build a bounded `FoundingTeamConsultation` packet with:
   - trigger event id/type,
   - current step,
   - project goal/title,
   - memory provenance,
   - persona memory summaries,
   - prior decisions/convergence,
   - artifact refs/source refs,
   - optional queued `invite_hero` intents.
5. Emit:
   - one `discussion_entry_created` per persona,
   - one `discussion_highlight_created` convergence note.
6. Add idempotency per trigger event id. Suggested artifact:

   ```bash
   .orchestrator/discussion/founding-consultations.json
   ```

   or a consultation id in metadata that can be checked before writing.

7. Wire only safest triggers first:
   - `phase_error`,
   - validator retry advisory,
   - rejected `gate_decided`.

8. Add tests:
   - no personas -> no-op/skipped,
   - one trigger emits N persona rows + one highlight,
   - repeated same trigger is idempotent,
   - rows have `source_refs`,
   - metadata has `consultation_id`, `trigger_event_id`, `allowed_motion`,
     `scope_delta`,
   - Hero intent metadata is included as temporary advisory context.

Important: A-8 should not mutate workflow, task scope, or artifacts. It writes
discussion state only. Any scope expansion must become
`operator_decision_required`.

## How To Avoid Breaking The Product

- Do not make a dashboard. Use map-native PWA surfaces.
- Do not make the narrator a roleplay character.
- Do not add a multi-agent recursive council loop. The consultation contract is
  bounded by design.
- Do not use current filesystem state when replay semantics require event-index
  state. When in doubt, store source refs and provenance with emitted events.
- Do not let a Hero become a permanent persona unless an explicit operator
  update promotes it.
- Do not silently expand scope from generated text.

## Verification Expectations

For A-9:

```bash
uv run pytest -q tests/test_narrative_digest.py tests/test_discussion.py web/frontend/tests/test_event_engine.py
uv run pytest -q web/backend/tests/test_events.py web/backend/tests/test_stream.py
git diff --check
```

For A-8:

```bash
uv run pytest -q tests/test_discussion.py tests/test_engine.py tests/test_integration_m02b_intent_lifecycle_rehearsal.py
uv run pytest -q web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py
git diff --check
```

If touching `engine.py`, sidecar, event schema, or broad PWA fold behavior:

```bash
uv run pytest -q
```

## Last Known Test Evidence

Before the latest commit:

- `uv run pytest -q` -> 539 passed, 2 warnings.
- X-2 focused test:
  `uv run pytest -q web/backend/tests/test_stream.py::TestSimpleEventBus::test_emit_prunes_failed_subscribers web/backend/tests/test_stream.py web/backend/tests/test_events.py`
  -> 14 passed.
- `git diff --check` clean.

Warnings are existing pytest collection warnings for classes in
`orchestrator/roles/tester.py`.

## Final Advice For The Next Agent

Start by choosing A-9 unless the user explicitly asks for founding-team behavior
first. A-9 makes every later consultation more credible because generated
persona/founding-team statements will carry memory provenance from day one.

If implementing A-8, keep it boring in the backend and rich in the PWA. The
backend should produce small, source-backed, deterministic discussion rows. The
PWA can make that feel like a powerful council moment.
