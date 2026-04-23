# M10 Functional Orchestration Surface

## Purpose

Turn the event spine into a daily-use orchestration product. The PWA should
not only show what happened; it should let the operator understand the project,
choose the next functional move, intervene at the right time, and review the
proof that a mini-sprint actually produced value.

This file complements `srs-mini-phases/M10-hookability-and-workflow-control.md`.
That file owns programmable hooks and advisor boundaries. This file owns the
operator-facing functional workflows that make those boundaries useful.

## Product Thesis

The core product is a command surface for semi-automatic software delivery:

- The operator can open a project and immediately understand the goal, founding
  team, current run state, last meaningful work, and next functional action.
- The engine can execute a mini-sprint through planning, implementation,
  testing, artifact preview, optional demo ceremony, review, and memory update.
- The operator can interject with a bounded intent or Hero reviewer without
  turning the run into an unbounded debate.
- Every functional decision is replayable from events, with artifacts, demos,
  memory refs, usage, cost, and discussion evidence attached.

## Current Inputs Already Available

- `next_step_packet_created` gives an authoritative upcoming step with queued
  intents and provenance.
- `operator_intent`, `operator_intent_applied`, and `operator_intent_ignored`
  provide durable intervention lifecycle.
- `artifact_preview_created` makes phase outputs visible in replay.
- `demo_planned`, `demo_artifact_created`, and related demo events define the
  first demo ceremony contract.
- `memory_refreshed`, `memory_diff`, and MemPalace wake-up refs provide project
  memory context.
- `discussion_entry_created` and `discussion_highlight_created` provide a
  replayable council/story layer.
- `usage_recorded`, budget events, and rate-card refs provide spend truth.

## Core User Jobs

1. **Orient**
   - What are we building?
   - Who is shaping the product?
   - What is the current status?
   - What just changed?
   - What is the next slated action?

2. **Steer**
   - Add a constraint before the next step.
   - Ask for a specific artifact or evidence.
   - Drop in a Hero reviewer with mission, watch-for list, model/provider, and
     term.
   - Pause, continue, reroute, or cancel a run through explicit gates.

3. **Execute**
   - Run a bounded mini-sprint.
   - Preserve atomic tasks, acceptance criteria, evidence requirements, memory
     context, and cost/budget state.
   - Convert failures into repair loops or advisor escalation without losing
     provenance.

4. **Review**
   - Inspect artifacts and source refs.
   - Watch demo evidence when the task is web/PWA compatible.
   - Inspect founding-team/council input and operator interventions.
   - Confirm whether the work meets acceptance gates.

5. **Remember**
   - Update project memory after a meaningful slice.
   - Show what changed in memory and why.
   - Let replay explain the project as a sequence of decisions, evidence, and
     outcomes.

## Primary PWA Surfaces

All surfaces remain map-native lenses or sheets. Do not add a dashboard route.

### Command Core

Default first-viewport surface.

Shows:

- project goal and brief,
- founding-team count and latest stance,
- current run state,
- active/next atom,
- last meaningful event,
- latest narrative digest,
- cost/budget chip,
- memory freshness chip,
- intervention entry point.

Events consumed:

- `run_started`, `phase_start`, `phase_done`, `phase_error`, `run_complete`,
- `project_mythos_updated`, `persona_stance_updated`,
- `next_step_packet_created`,
- `narrative_digest_created`,
- `memory_*`,
- `usage_recorded`, budget events.

### Next Move Sheet

The operator's main functional control surface.

Shows:

- next step title, role, objective, and why now,
- inputs and source refs,
- memory refs and wake-up hash,
- artifact refs that the step will consume,
- queued intents targeting the step,
- acceptance criteria,
- evidence expected,
- allowed interventions for this moment.

Controls:

- Interject: add instruction/context to next prompt.
- Intercept: require gate before step starts.
- Reroute: propose alternate next step or phase.
- Invite Hero: add a temporary high-signal reviewer.
- Request demo: require demo ceremony if compatible.
- Raise/continue/stop budget gate where applicable.

### Mini-Sprint Lane

Functional execution view over the existing atom map.

Shows:

- plan atom,
- implementation atom,
- test atom,
- review atom,
- artifact preview nodes,
- demo ceremony node when applicable,
- repair/advisor loop band when failure happens,
- memory refresh node after meaningful completion.

The Mini-Sprint Lane is not a new workflow engine. It is a lens over existing
workflow steps plus additional event-backed ceremony nodes.

### Council And Hero Sheet

Bounded advisory layer for founding-team and temporary Hero input.

Shows:

- trigger reason,
- current project goal/scope,
- accepted prior decisions,
- relevant memory refs,
- persona statements,
- Hero statement with mission and term,
- convergence/highlight,
- scope-delta warning when advice expands scope.

Controls:

- invite Hero,
- dismiss Hero,
- renew Hero term,
- promote suggestion to operator intent,
- require operator decision for scope expansion.

### Evidence And Demo Sheet

Review surface for output proof.

Shows:

- artifact previews by atom,
- test report summary,
- demo card if captured,
- screenshot/video/trace/GIF refs,
- source refs and producing atom id,
- reviewer verdict,
- acceptance criteria status.

## Functional Event Contracts

The current event spine is sufficient for a first implementation, but the
functional surface needs a few higher-level events to avoid inferring product
semantics from low-level rows.

### `functional_goal_updated`

Purpose: durable product goal/constraint update.

Required fields:

- `goal_id`
- `title`
- `summary`
- `constraints[]`
- `source_refs[]`
- `changed_by`: `operator | founding_team | system`

### `mini_sprint_planned`

Purpose: declare a bounded unit of functional work.

Required fields:

- `mini_sprint_id`
- `title`
- `objective`
- `scope_refs[]`
- `acceptance_criteria[]`
- `evidence_required[]`
- `demo_requested`
- `demo_compatibility`: `eligible | ineligible | unknown`
- `source_refs[]`

### `mini_sprint_step_completed`

Purpose: functional progress marker over one or more low-level phase events.

Required fields:

- `mini_sprint_id`
- `step_id`
- `step_kind`: `plan | build | test | review | demo | memory | ship`
- `status`: `done | failed | skipped`
- `artifact_refs[]`
- `evidence_refs[]`
- `source_event_ids[]`

### `functional_acceptance_evaluated`

Purpose: explicit acceptance gate for user-facing value.

Required fields:

- `mini_sprint_id`
- `criteria_results[]`
- `passed`
- `blocking_findings[]`
- `review_artifact_ref`
- `source_refs[]`

### `hero_invitation_requested`

Purpose: operator-visible Hero lifecycle start. This may map to existing
`operator_intent` rows, but the PWA benefits from a typed event when accepted.

Required fields:

- `hero_id`
- `originating_intent_id`
- `mission`
- `watch_for[]`
- `model_ref`
- `term_mode`
- `target_step`
- `source_refs[]`

## Context Passed To Functional Agents

Any functional agent or advisor should receive a bounded packet:

- current project goal and constraints,
- current mini-sprint objective,
- accepted prior decisions,
- relevant founding-team stance,
- queued operator intents,
- active Heroes and terms,
- memory wake-up hash and short memory refs,
- artifact refs from prior steps,
- acceptance criteria,
- evidence required,
- budget/provider state,
- explicit forbidden behavior: do not expand scope without
  `operator_decision_required`.

The packet should reference artifacts and memory by path/hash rather than
injecting unbounded file contents.

## Hero And Council Guardrails

- A Hero is temporary unless explicitly promoted later.
- Hero advice is advisory discussion state until consumed through an operator
  intent, gate decision, or explicit workflow update.
- Founding-team consultation may clarify, narrow, defer, or request evidence.
- Scope expansion cannot directly alter the mini-sprint; it becomes an
  operator decision requirement.
- Prior accepted decisions are binding context unless the consultation clearly
  explains why they should be reopened.
- Every model-backed Hero/council call emits `usage_recorded`.

## Demo Ceremony Rule

If a mini-sprint produces or changes a web/PWA-compatible user workflow, the
system should evaluate demo compatibility.

First implementation:

- Detect eligibility from changed paths, acceptance criteria, and evidence text.
- If eligible, request or generate a Playwright spec.
- Capture screenshot/video/trace, and optionally GIF when tooling is present.
- Emit demo events already defined by M07/A-10.
- Render demo cards in Evidence And Demo Sheet.
- Replay never re-runs the app; it references recorded demo artifacts.

## Execution Slices

### Slice F1 — Functional Plan File And Board Wiring

- Create this file.
- Link it from `STATUS.md`.
- Define first implementation sequence.
- No code behavior changes.

Quality gate:

- The file gives a contextless agent enough detail to start implementation
  without re-reading the full chat.

### Slice F2 — Command Core Readiness Audit

- [x] Audit current `GameShell` first viewport against the Core User Jobs.
- [x] Add the first missing functional fields to the authoritative Next-Step
  packet fold: acceptance criteria, evidence required, demo request, and demo
  compatibility.
- [x] Render those fields in the map-native Next-Step sheet under a functional
  readiness section.
- [x] Add tests that assert the bundle contains the required Command Core /
  Next Move roles.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

Landed 2026-04-23: `EventEngine` now folds next-step acceptance/evidence/demo
fields, and `GameShell` renders them in `functional-readiness` inside the
existing Next-Step sheet. Evidence: `uv run pytest -q web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py` -> 27 passed; `./web/frontend/build.sh` -> `dist/app.js` 1,363,053 bytes.

### Slice F3 — Mini-Sprint Event Skeleton

- [x] Register `mini_sprint_planned`, `mini_sprint_step_completed`, and
  `functional_acceptance_evaluated`.
- [x] Add deterministic emitter helpers.
- [x] Add EventEngine fold fields:
  - `snapshot.functional.currentMiniSprint`
  - `snapshot.functional.acceptance`
  - `snapshot.functional.evidenceRefs`

Evidence:

```bash
uv run pytest -q tests/test_event_schema.py tests/test_functional_orchestration.py web/frontend/tests/test_event_engine.py
```

Landed 2026-04-23: backend/frontend event registries now include the three
functional events, `orchestrator.lib.functional` provides deterministic mini-
sprint emitters, and `EventEngine` folds functional mini-sprint, step, evidence,
and acceptance state. Evidence: `uv run pytest -q tests/test_event_schema.py tests/test_functional_orchestration.py` -> 6 passed; `uv run pytest -q web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py` -> 28 passed; `./web/frontend/build.sh` -> `dist/app.js` 1,368,724 bytes.

### Slice F4 — Next Move Sheet Upgrade

- [x] Add acceptance/evidence/demo readiness rows to the existing Next-Step
  surface.
- [x] Add mini-sprint evidence, functional step status, acceptance verdict, and
  blocking findings from `snapshot.functional`.
- [x] Keep backend-authoritative `next_step_packet_created` and functional
  event folds as source.
- [x] Do not create a new route.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py
./web/frontend/build.sh
```

Landed 2026-04-23: the existing map-native Next-Step sheet now includes a
`functional-mini-sprint` panel with planned sprint objective, functional step
status, evidence refs, acceptance verdict, and blocking findings. Evidence:
`uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py` -> 29 passed; `./web/frontend/build.sh` -> `dist/app.js` 1,370,300 bytes.

### Slice F5 — Hero Invite Intent UI

- Add an `invite_hero` intent mode to the compose surface.
- Persist mission, watch_for, provider/model, term, and target step.
- Fold accepted Hero rows into replay state.
- Render Hero presence in the map-native orchestration surface.

Evidence:

```bash
uv run pytest -q web/backend/tests/test_intents.py tests/test_heroes_lifecycle.py
uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py
./web/frontend/build.sh
git diff --check -- web/backend/routes/intents.py web/backend/tests/test_intents.py web/frontend/src/game/types.ts web/frontend/src/game/EventEngine.ts web/frontend/src/game/GameShell.ts web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py
```

Delivered 2026-04-23:

- `web/backend/routes/intents.py` accepts `invite_hero` through the same durable
  operator intent route as interject/intercept/reroute.
- `GameShell` adds a `Hero` action in the Next Move Sheet and a Hero compose
  mode with fields for name, watch-for, provider, model, term, scope, and
  mission.
- `heroInvitePayload(...)` emits the lifecycle shape consumed by
  `orchestrator.lib.heroes`.
- `EventEngine` folds `hero_invited` and `hero_retired` into
  `snapshot.heroes`, with active/retired rows preserved through replay scrub.
- The Next Move Sheet renders a replay-backed Hero roster panel so accepted
  Hero presence is visible next to mini-sprint evidence and queued intents.

Remaining depth for a later Hero/Council slice:

- dedicated dismiss/renew controls,
- promotion of a Hero suggestion into a follow-up operator intent,
- council-specific scope expansion warnings.

### Slice F6 — Demo Compatibility Gate

- Add a deterministic adapter that marks a mini-sprint as demo eligible,
  ineligible, or unknown.
- Hook it to existing demo events.
- Show the requested demo state in the Evidence And Demo Sheet / demo cards.

Evidence:

```bash
uv run pytest -q tests/test_demo.py tests/test_functional_orchestration.py tests/test_demo_runner.py
uv run pytest -q web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py
./web/frontend/build.sh
git diff --check -- orchestrator/lib/demo.py orchestrator/lib/functional.py tests/test_demo.py tests/test_functional_orchestration.py web/frontend/src/game/types.ts web/frontend/src/game/EventEngine.ts web/frontend/src/game/GameShell.ts web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py
```

Delivered 2026-04-23:

- `orchestrator.lib.demo.demo_compatibility_from_plan(...)` maps adapter
  confidence to product gate values:
  - `explicit_playwright`, `operator_requested`, `inferred_interactive_web` ->
    `eligible`
  - `not_demoable` -> `ineligible`
  - static/ambiguous visual proof -> `unknown`
- `emit_demo_plan(...)` now stamps `demo_requested` and
  `demo_compatibility` on `demo_planned` / `demo_skipped`.
- `orchestrator.lib.functional.build_demo_compatibility_gate(...)` converts
  mini-sprint acceptance/evidence text, touched files, commands, route, and
  viewport hints into a replay-safe gate payload.
- `build_mini_sprint_plan(...)` can thread that gate into
  `mini_sprint_planned` without requiring free-form inference in the PWA.
- `EventEngine` folds demo gate metadata into `snapshot.functional` and
  `snapshot.demos`; `GameShell` renders the gate beside mini-sprint acceptance
  and on demo cards.

### Slice F7 — Functional Acceptance Gate

- Emit `functional_acceptance_evaluated` after test/review/demo evidence.
- The PWA shows pass/fail criteria and blocking findings.
- A failed gate offers repair loop, Hero review, or operator override.

Evidence:

```bash
uv run pytest -q tests/test_functional_orchestration.py tests/test_engine.py web/frontend/tests/test_event_engine.py
```

## Quality Gates

- Event integrity: every new functional event is registered in backend and
  frontend event registries.
- Replay determinism: functional state folds from events only.
- No-dashboard: all controls live in the map, HUD, or map-native sheets.
- Mobile first: Command Core and Next Move Sheet work at 375x812.
- Source credibility: every functional claim carries source refs.
- Memory boundedness: agents get refs/hashes/excerpts, not unbounded logs.
- Scope safety: no council/Hero output directly expands scope.
- Cost truth: every model-backed Hero/advisor/council call emits
  `usage_recorded`.
- Demo evidence: replay references recorded artifacts, never re-runs a demo.

## Done Means

- Opening the PWA answers: what are we building, who is shaping it, what just
  happened, what is next, and how can I intervene?
- A mini-sprint can be planned, executed, reviewed, and accepted from events.
- Operator interventions and Hero reviewers are bounded, visible, and
  replayable.
- Demo evidence appears when applicable.
- Functional acceptance is explicit and evidence-backed.
- Replay tells the story of a project as decisions plus proof, not raw log spam.

## Known Traps

- Building a second dashboard route because it is faster than extending the map.
- Letting Hero/council advice mutate scope directly.
- Treating a demo as a live rerun instead of recorded evidence.
- Hiding acceptance criteria inside free-form narrative.
- Letting next-step packets drift from backend authority.
- Injecting full memory or discussion logs into every agent prompt.
- Showing a beautiful replay that cannot explain which artifacts or evidence
  justified acceptance.

## Immediate Next Step

Run Slice F7: turn accumulated mini-sprint evidence, tests, preview/demo refs,
and review findings into an explicit functional acceptance gate with repair,
Hero review, or operator override as the blocked-state actions.
